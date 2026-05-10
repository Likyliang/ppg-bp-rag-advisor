from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import yaml

from app.services.config_loader import resolve_project_path


CATALOG_PATH = "knowledge_base/sources/source_catalog.yaml"
SCREEN_THRESHOLD = 18

ALLOWED_EVIDENCE_CLASSES = {
    "guideline",
    "official_health_education",
    "scientific_statement",
    "validation_standard",
    "review",
    "safety_rule",
    "patient_education",
    "research_context",
}

ALLOWED_USES = {
    "bp_category_reference",
    "home_bp_monitoring",
    "remeasurement",
    "device_advice",
    "cuffless_ppg_limitations",
    "signal_quality",
    "lifestyle",
    "emergency_alert",
    "medication_safety",
    "special_population",
    "research_background",
    "disclaimer",
}

EXPECTED_TOPICS = {
    "bp_categories",
    "home_bp_monitoring",
    "cuffless_ppg_limitations",
    "measurement_quality",
    "validated_devices",
    "lifestyle",
    "emergency",
    "medication_safety",
    "special_population",
}

HIGH_TRUST_EVIDENCE_CLASSES = {
    "guideline",
    "official_health_education",
    "scientific_statement",
    "validation_standard",
    "safety_rule",
}


@dataclass
class CatalogIssue:
    source_id: str
    severity: str
    message: str


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _jsonable(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def load_source_catalog(path: str = CATALOG_PATH) -> Dict[str, Any]:
    catalog_path = resolve_project_path(path)
    if not catalog_path.exists():
        return {"sources": []}
    with catalog_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {"sources": []}


def source_identity_hash(source: Dict[str, Any]) -> str:
    identity = {
        "title": source.get("title", ""),
        "url": source.get("url", ""),
        "doi": source.get("doi", ""),
        "pmid": source.get("pmid", ""),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def screening_score(source: Dict[str, Any]) -> int:
    screening = source.get("screening") or {}
    return int(
        screening.get("authority", 0)
        + screening.get("recency", 0)
        + screening.get("relevance", 0)
        + screening.get("accessibility", 0)
        + screening.get("safety_applicability", 0)
    )


def validate_source(source: Dict[str, Any]) -> List[CatalogIssue]:
    source_id = str(source.get("source_id") or "<missing>")
    issues: List[CatalogIssue] = []

    required = ["source_id", "title", "organization", "year", "language", "region", "topic", "evidence_class", "allowed_uses"]
    for field in required:
        if source.get(field) in (None, "", []):
            issues.append(CatalogIssue(source_id, "error", f"missing required field: {field}"))

    if not source.get("url") and not source.get("doi") and not source.get("pmid") and source.get("evidence_class") != "safety_rule":
        issues.append(CatalogIssue(source_id, "error", "source must have url, doi, pmid, or be a safety_rule"))

    evidence_class = source.get("evidence_class")
    if evidence_class and evidence_class not in ALLOWED_EVIDENCE_CLASSES:
        issues.append(CatalogIssue(source_id, "error", f"invalid evidence_class: {evidence_class}"))

    invalid_uses = sorted(set(_as_list(source.get("allowed_uses"))) - ALLOWED_USES)
    if invalid_uses:
        issues.append(CatalogIssue(source_id, "error", f"invalid allowed_uses: {', '.join(invalid_uses)}"))

    score = screening_score(source)
    included = bool(source.get("include"))
    if included and score < SCREEN_THRESHOLD:
        issues.append(CatalogIssue(source_id, "error", f"included source below threshold: {score} < {SCREEN_THRESHOLD}"))

    if source.get("topic") not in EXPECTED_TOPICS and source.get("topic") not in {"research_context", "disclaimer"}:
        issues.append(CatalogIssue(source_id, "warning", f"unexpected topic: {source.get('topic')}"))

    return issues


def screen_sources(catalog: Dict[str, Any] = None) -> Dict[str, Any]:
    catalog = catalog or load_source_catalog()
    sources = catalog.get("sources", [])
    included = []
    excluded = []
    issues: List[CatalogIssue] = []

    seen_ids = set()
    hashes = Counter()
    for source in sources:
        source = _jsonable(dict(source))
        source["source_quality_score"] = screening_score(source)
        source["source_hash"] = source_identity_hash(source)
        source["allowed_uses"] = _as_list(source.get("allowed_uses"))
        source["review_status"] = "included" if source.get("include") else "excluded"

        if source["source_id"] in seen_ids:
            issues.append(CatalogIssue(source["source_id"], "error", "duplicate source_id"))
        seen_ids.add(source["source_id"])
        hashes[source["source_hash"]] += 1
        issues.extend(validate_source(source))

        if source.get("include") and source["source_quality_score"] >= SCREEN_THRESHOLD:
            included.append(source)
        else:
            excluded.append(source)

    duplicate_hashes = sorted(hash_value for hash_value, count in hashes.items() if count > 1)
    summary = {
        "total_sources": len(sources),
        "included_count": len(included),
        "excluded_count": len(excluded),
        "threshold": SCREEN_THRESHOLD,
        "issues": [issue.__dict__ for issue in issues],
        "duplicate_source_hashes": duplicate_hashes,
        "topic_counts": dict(Counter(source.get("topic") for source in included)),
        "evidence_class_counts": dict(Counter(source.get("evidence_class") for source in included)),
        "included_sources": included,
        "excluded_sources": excluded,
    }
    return summary


def write_screening_outputs(output_dir: str = "knowledge_base/processed") -> Dict[str, str]:
    result = screen_sources()
    out_dir = resolve_project_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "screening_report": out_dir / "source_screening_report.json",
        "included_sources": out_dir / "included_sources.json",
        "excluded_sources": out_dir / "excluded_sources.json",
    }
    files["screening_report"].write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    files["included_sources"].write_text(json.dumps(result["included_sources"], ensure_ascii=False, indent=2), encoding="utf-8")
    files["excluded_sources"].write_text(json.dumps(result["excluded_sources"], ensure_ascii=False, indent=2), encoding="utf-8")
    return {key: str(path) for key, path in files.items()}


def included_sources() -> List[Dict[str, Any]]:
    return screen_sources()["included_sources"]
