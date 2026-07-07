"""Auto-fill literature metadata from a DOI / URL / title or an uploaded PDF.

The goal is to turn "here is a paper" into a ready-to-review catalog draft so an
admin no longer types every field by hand. Given a DOI/URL/title we query
Crossref; given a PDF we read its embedded DOI (or metadata) and enrich the same
way. The result is a *draft* — factual fields (title, organisation, year, doi,
url, source_id) are filled from the source, while the curation-sensitive fields
(``topic``, ``evidence_class``, ``screening``, ``allowed_uses``) are *suggested*
and flagged for human confirmation, matching this project's careful, auditable
curation of medical evidence.

Network: Crossref (``api.crossref.org``) over HTTPS. Degrades gracefully to a
title-only draft when offline. PDF parsing needs the optional ``pypdf`` dep.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import requests

CROSSREF_API = "https://api.crossref.org/works"
_MAILTO = "ppg-bp-rag@example.org"  # Crossref polite-pool contact
_TIMEOUT = 8

_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")

# topic (分类) keyword heuristics — first match wins, order matters.
_TOPIC_KEYWORDS: List[tuple] = [
    ("emergency", ["hypertensive crisis", "hypertensive emergency", "hypertensive urgency", "high blood pressure emergency"]),
    ("special_population", ["pregnan", "preeclampsia", "eclampsia", "gestational", "pediatric", "children", "elderly", "older adult", "diabetes", "chronic kidney", "ckd", "dialysis"]),
    ("medication_safety", ["antihypertensive", "medication adherence", "pharmacological", "drug therapy", "beta-blocker", "ace inhibitor", "diuretic"]),
    ("validated_devices", ["device validation", "validation protocol", "aami", "iso 81060", "esh", "oscillometric device", "device accuracy"]),
    ("cuffless_ppg_limitations", ["photoplethysmograph", "ppg", "cuffless", "pulse transit time", "pulse wave", "ptt", "seismocardiograph", "scg", "wearable blood pressure"]),
    ("home_bp_monitoring", ["home blood pressure", "self-measured", "self measured", "smbp", "home monitoring", "ambulatory blood pressure"]),
    ("measurement_quality", ["measurement accuracy", "signal quality", "motion artifact", "calibration", "measurement technique", "measurement error"]),
    ("bp_categories", ["blood pressure classification", "hypertension guideline", "blood pressure threshold", "bp category", "definition of hypertension"]),
    ("lifestyle", ["dash diet", "sodium", "physical activity", "exercise", "weight loss", "lifestyle", "dietary", "nutrition"]),
]

# topic -> default allowed_uses (all values are members of source_catalog.ALLOWED_USES).
_TOPIC_ALLOWED_USES: Dict[str, List[str]] = {
    "emergency": ["emergency_alert"],
    "special_population": ["special_population"],
    "medication_safety": ["medication_safety"],
    "validated_devices": ["device_advice", "home_bp_monitoring"],
    "cuffless_ppg_limitations": ["cuffless_ppg_limitations", "signal_quality"],
    "home_bp_monitoring": ["home_bp_monitoring", "remeasurement", "device_advice"],
    "measurement_quality": ["signal_quality", "remeasurement"],
    "bp_categories": ["bp_category_reference", "remeasurement"],
    "lifestyle": ["lifestyle"],
    "research_context": ["research_background"],
}

# Crossref work type -> catalog source_type (free text).
_CROSSREF_TYPE = {
    "journal-article": "research_article",
    "proceedings-article": "conference_paper",
    "posted-content": "preprint",
    "report": "report",
    "book": "book",
    "book-chapter": "book_chapter",
    "standard": "validation_standard",
    "dataset": "dataset",
}

_STOPWORDS = {
    "the", "a", "an", "of", "for", "and", "or", "in", "on", "to", "with", "using",
    "based", "via", "study", "analysis", "novel", "new", "approach", "method",
    "toward", "towards", "from", "by", "at", "is", "are",
}


# --------------------------------------------------------------------------- #
# source_id + helpers
# --------------------------------------------------------------------------- #
def slugify(text: str, max_words: int = 4) -> str:
    words = re.findall(r"[A-Za-z0-9]+", (text or "").lower())
    words = [w for w in words if w not in _STOPWORDS]
    return "_".join(words[:max_words])


def suggest_source_id(title: str, year: Optional[int], first_author: Optional[str] = None) -> str:
    """Build a readable, unique-ish id: ``author_year_titlekeywords``."""

    parts: List[str] = []
    if first_author:
        surname = re.findall(r"[A-Za-z]+", first_author.lower())
        if surname:
            parts.append(surname[-1])
    if year:
        parts.append(str(year))
    parts.append(slugify(title, max_words=3))
    slug = "_".join(p for p in parts if p)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "untitled_source"


def extract_doi(text: str) -> Optional[str]:
    if not text:
        return None
    match = _DOI_RE.search(text)
    if not match:
        return None
    # Trim trailing punctuation that regularly clings to inline DOIs.
    return match.group(0).rstrip(".,);]>")


# --------------------------------------------------------------------------- #
# Crossref
# --------------------------------------------------------------------------- #
def _crossref_get(url: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    params = dict(params, mailto=_MAILTO)
    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("message")
    except Exception:
        return None


def crossref_by_doi(doi: str) -> Optional[Dict[str, Any]]:
    return _crossref_get(f"{CROSSREF_API}/{doi}", {})


def crossref_search(title: str) -> Optional[Dict[str, Any]]:
    message = _crossref_get(CROSSREF_API, {"query.bibliographic": title, "rows": 1})
    if not message:
        return None
    items = message.get("items") or []
    return items[0] if items else None


def _first(values: Any) -> Optional[str]:
    if isinstance(values, list) and values:
        return str(values[0])
    if isinstance(values, str):
        return values
    return None


def _year_from(message: Dict[str, Any]) -> Optional[int]:
    for key in ("published", "published-print", "published-online", "issued", "created"):
        block = message.get(key) or {}
        parts = block.get("date-parts") or []
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def _organization_from(message: Dict[str, Any]) -> Optional[str]:
    authors = message.get("author") or []
    if authors:
        affil = authors[0].get("affiliation") or []
        if affil and affil[0].get("name"):
            return str(affil[0]["name"])
    container = _first(message.get("container-title"))
    if container:
        return container
    return message.get("publisher")


def _first_author_surname(message: Dict[str, Any]) -> Optional[str]:
    authors = message.get("author") or []
    if authors:
        return authors[0].get("family") or authors[0].get("name")
    return None


def message_to_draft(message: Dict[str, Any]) -> Dict[str, Any]:
    title = _first(message.get("title")) or "Untitled"
    year = _year_from(message)
    doi = message.get("DOI")
    container = _first(message.get("container-title"))
    text_for_topic = " ".join(filter(None, [title, container, message.get("abstract", "")]))

    draft = {
        "source_id": suggest_source_id(title, year, _first_author_surname(message)),
        "title": title,
        "organization": _organization_from(message) or "Unknown",
        "year": year,
        "doi": doi or None,
        "url": message.get("URL") or (f"https://doi.org/{doi}" if doi else None),
        "language": (message.get("language") or "en")[:2],
        "source_type": _CROSSREF_TYPE.get(message.get("type", ""), "research_article"),
        "container": container,
    }
    _apply_suggestions(draft, text_for_topic, crossref_type=message.get("type", ""))
    return draft


# --------------------------------------------------------------------------- #
# 分类 / 分级 suggestions (flagged for human confirmation)
# --------------------------------------------------------------------------- #
def suggest_topic(text: str) -> str:
    low = (text or "").lower()
    for topic, keywords in _TOPIC_KEYWORDS:
        if any(kw in low for kw in keywords):
            return topic
    return "research_context"


def suggest_evidence_class(text: str, crossref_type: str = "") -> str:
    low = (text or "").lower()
    if crossref_type == "standard":
        return "validation_standard"
    if any(k in low for k in ["guideline", "consensus statement", "scientific statement", "practice guideline"]):
        return "guideline"
    if any(k in low for k in ["systematic review", "meta-analysis", "meta analysis", "narrative review", " review"]):
        return "review"
    # Conservative default: background research (Tier C) so nothing over-claims trust.
    return "research_context"


def suggest_screening(year: Optional[int]) -> Dict[str, int]:
    if year and year >= 2024:
        recency = 5
    elif year and year >= 2020:
        recency = 4
    elif year and year >= 2015:
        recency = 3
    else:
        recency = 2
    # Neutral mid-values for the reviewer to adjust; recency is objective.
    return {
        "authority": 3,
        "recency": recency,
        "relevance": 3,
        "accessibility": 3,
        "safety_applicability": 3,
    }


def _apply_suggestions(draft: Dict[str, Any], text: str, crossref_type: str = "") -> None:
    topic = suggest_topic(text)
    draft["topic"] = topic
    draft["evidence_class"] = suggest_evidence_class(text, crossref_type)
    draft["allowed_uses"] = list(_TOPIC_ALLOWED_USES.get(topic, ["research_background"]))
    draft["screening"] = suggest_screening(draft.get("year"))
    draft["_suggested_fields"] = ["topic", "evidence_class", "allowed_uses", "screening"]
    draft["_note"] = "topic / evidence_class / allowed_uses / screening 为自动建议，请管理员确认后再添加。"


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def draft_from_query(query: str) -> Dict[str, Any]:
    """Build a draft from a DOI, an article URL, or a free-text title."""

    query = (query or "").strip()
    if not query:
        raise ValueError("empty query")

    doi = extract_doi(query)
    message = crossref_by_doi(doi) if doi else None
    if message is None:
        # URL without a DOI, or a plain title -> bibliographic search.
        if not doi:
            message = crossref_search(query)
    if message is None:
        # Offline / not found: return a minimal title-only draft to fill by hand.
        year = None
        draft = {
            "source_id": suggest_source_id(query, None),
            "title": query if not doi else "",
            "organization": "Unknown",
            "year": year,
            "doi": doi,
            "url": f"https://doi.org/{doi}" if doi else query if query.startswith("http") else None,
            "language": "en",
            "source_type": "research_article",
            "container": None,
        }
        _apply_suggestions(draft, draft["title"] or "")
        draft["_resolved"] = False
        draft["_warning"] = "未能从 Crossref 解析到元数据（可能离线或未收录），已生成占位草稿，请补全。"
        return draft

    draft = message_to_draft(message)
    draft["_resolved"] = True
    return draft


def read_pdf_text_and_doi(pdf_bytes: bytes) -> Dict[str, Any]:
    """Extract embedded DOI + metadata from PDF bytes (needs pypdf)."""

    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - optional dep
        raise RuntimeError(f"PDF 解析需要 pypdf（{exc.__class__.__name__}）") from None

    import io

    reader = PdfReader(io.BytesIO(pdf_bytes))
    meta = reader.metadata or {}
    pages_text = []
    for page in reader.pages[:3]:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n".join(pages_text)
    return {
        "doi": extract_doi(text) or extract_doi(str(meta.get("/doi", "")) if meta else ""),
        "title": (meta.get("/Title") if meta else None) or "",
        "author": (meta.get("/Author") if meta else None) or "",
        "text": text,
    }


def draft_from_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """Build a draft from an uploaded PDF: prefer embedded DOI -> Crossref."""

    parsed = read_pdf_text_and_doi(pdf_bytes)
    doi = parsed.get("doi")
    if doi:
        message = crossref_by_doi(doi)
        if message is not None:
            draft = message_to_draft(message)
            draft["_resolved"] = True
            draft["_source"] = "pdf+crossref"
            return draft

    # No DOI or Crossref miss: fall back to PDF metadata / first-page text.
    title = (parsed.get("title") or "").strip()
    text = parsed.get("text") or ""
    if not title:
        # First non-trivial line of extracted text is a decent title guess.
        for line in text.splitlines():
            line = line.strip()
            if len(line) > 12:
                title = line
                break
    author = (parsed.get("author") or "").strip() or None
    draft = {
        "source_id": suggest_source_id(title or "untitled", None, author),
        "title": title,
        "organization": author or "Unknown",
        "year": None,
        "doi": doi,
        "url": f"https://doi.org/{doi}" if doi else None,
        "language": "en",
        "source_type": "research_article",
        "container": None,
    }
    _apply_suggestions(draft, " ".join([title, text[:2000]]))
    draft["_resolved"] = bool(doi)
    draft["_source"] = "pdf"
    draft["_warning"] = "未能自动匹配 Crossref，年份/机构等可能需要补全。"
    return draft
