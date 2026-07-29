"""Bulk-import real full-text PDFs from the original project into this system.

Source of truth:
  * ``local_fulltext_index.json`` — machine-readable index of every locally
    downloaded PDF (file name, source_id, absolute path, batch).
  * ``literature_expansion_2026_05_31.yaml`` — rich metadata for the 100-paper
    "literature expansion" batch (title, journal, year, doi, topic_bucket,
    publication_types, allowed_uses, …).

Two groups of PDFs:
  * **matched** — the PDF's ``source_id`` already exists in this project's
    catalog. Just copy the PDF into ``library/<topic>/`` and record the upload.
  * **expansion** (``litexp_*``) — not yet in the catalog. Register each as a new
    source (metadata mapped from the expansion YAML, topic/evidence_class/
    screening auto-derived and flagged for human review), then copy its PDF.

Governance is preserved: PDFs land only in the git-ignored ``library/`` store;
the committed ``fulltext_uploads.yaml`` records metadata + sha256 only; a
one-shot vector rebuild happens at the end (not once per file).

Usage:
    python scripts/import_local_fulltext.py --dry-run            # preview
    python scripts/import_local_fulltext.py --scope matched      # only the 68
    python scripts/import_local_fulltext.py --scope all          # 68 + register 100
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.services.config_loader import resolve_project_path
from app.services.fulltext_vector_index import build_fulltext_vector_index, library_pdf_target
from app.services.library_manager import LibraryManager
from app.services.source_catalog import ALLOWED_USES, load_source_catalog, validate_source

DEFAULT_INDEX = "/Users/lianghao/Work/high blood pressure RAG/knowledge_base/sources/local_fulltext_index.json"
DEFAULT_EXPANSION = "knowledge_base/sources/literature_expansion_2026_05_31.yaml"
UPLOADS_REGISTRY = "knowledge_base/sources/fulltext_uploads.yaml"
REVIEW_SHEET = "knowledge_base/processed/literature_expansion_import_review.md"

# topic_bucket -> catalog topic.
_TOPIC_MAP = {
    "ppg_cuffless_bp": "cuffless_ppg_limitations",
    "bp_measurement_monitoring": "home_bp_monitoring",
    "hypertension_cvd_context": "research_context",
    "hypertension_general": "research_context",
}
_REVIEW_TYPES = {"review", "review-article", "systematic review", "meta-analysis", "narrative review"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _derive_evidence_class(pub_types: List[str]) -> str:
    low = {str(t).lower() for t in (pub_types or [])}
    if low & _REVIEW_TYPES:
        return "review"
    return "research_context"  # conservative Tier C default


def _derive_source_type(pub_types: List[str]) -> str:
    low = {str(t).lower() for t in (pub_types or [])}
    if "systematic review" in low or "meta-analysis" in low:
        return "systematic_review"
    if low & {"review", "review-article"}:
        return "review"
    if "randomized controlled trial" in low:
        return "randomized_controlled_trial"
    return "research_article"


def _derive_screening(journal_tier: Optional[int], year: Optional[int]) -> Dict[str, int]:
    authority = {1: 4, 2: 3, 3: 2}.get(int(journal_tier or 3), 2)
    if year and year >= 2024:
        recency = 5
    elif year and year >= 2020:
        recency = 4
    elif year and year >= 2015:
        recency = 3
    else:
        recency = 2
    return {
        "authority": authority,
        "recency": recency,
        "relevance": 4,
        "accessibility": 4,
        "safety_applicability": 3,
    }


def _expansion_to_source(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Map an expansion-batch entry to a catalog source dict."""

    topic = _TOPIC_MAP.get(str(meta.get("topic_bucket")), "research_context")
    uses = [u for u in (meta.get("allowed_uses") or []) if u in ALLOWED_USES] or ["research_background"]
    screening = _derive_screening(meta.get("journal_tier"), meta.get("year"))
    score = sum(screening.values())
    doi = meta.get("doi") or ""
    url = meta.get("doi_url") or meta.get("source_url") or (f"https://doi.org/{doi}" if doi else "")
    return {
        "source_id": meta["source_id"],
        "title": (meta.get("title") or "").rstrip(". "),
        "organization": meta.get("journal") or "Unknown",
        "journal": meta.get("journal") or "",
        "journal_tier": meta.get("journal_tier"),
        "url": url,
        "doi": doi,
        "pmid": str(meta.get("pmid") or ""),
        "year": meta.get("year"),
        "language": "en",
        "region": "global",
        "topic": topic,
        "evidence_class": _derive_evidence_class(meta.get("publication_types")),
        "source_type": _derive_source_type(meta.get("publication_types")),
        # Below-threshold entries register as excluded (visible, not retrieved).
        "include": score >= 18,
        "allowed_uses": uses,
        "copyright_note": "Imported full text; local vector use only, summary + citation committed.",
        "access_note": "local PDF imported from literature_expansion batch",
        "last_accessed": date.today().isoformat(),
        "screening": screening,
        "notes": {"summary": meta.get("screening_reason") or meta.get("title") or ""},
    }


def _load_uploads() -> Dict[str, Any]:
    path = resolve_project_path(UPLOADS_REGISTRY)
    if not path.exists():
        return {"version": 1, "uploads": []}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {"version": 1, "uploads": []}


def _save_uploads(registry: Dict[str, Any]) -> None:
    registry["updated"] = date.today().isoformat()
    registry["uploads"] = sorted(registry.get("uploads", []), key=lambda u: u.get("source_id", ""))
    path = resolve_project_path(UPLOADS_REGISTRY)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(registry, allow_unicode=True, sort_keys=False, default_flow_style=False, width=4096),
        encoding="utf-8",
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Import real full-text PDFs from the original project.")
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument("--expansion", default=DEFAULT_EXPANSION)
    parser.add_argument("--scope", choices=["matched", "expansion", "all"], default="all")
    parser.add_argument("--access-mode", default="public_pdf", help="declared access mode for imported PDFs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-build", action="store_true", help="skip the vector index rebuild")
    args = parser.parse_args(argv)

    index = json.loads(Path(args.index).read_text(encoding="utf-8"))
    entries = index["entries"]
    catalog_topic = {s.get("source_id"): s.get("topic") for s in load_source_catalog().get("sources", [])}
    expansion = {
        str(e["source_id"]): e
        for e in (yaml.safe_load(resolve_project_path(args.expansion).read_text(encoding="utf-8")) or {}).get("entries", [])
    }

    matched = [e for e in entries if e["source_id"] in catalog_topic]
    litexp = [e for e in entries if e["source_id"] not in catalog_topic]

    manager = LibraryManager(auto_rescreen=False, manage_fulltext=False)
    registry = _load_uploads()
    upload_by_id = {u["source_id"]: u for u in registry.get("uploads", [])}

    stats = {"registered": 0, "reg_skipped": 0, "copied": 0, "copy_missing": 0, "included": 0}
    review_rows: List[Dict[str, Any]] = []

    do_expansion = args.scope in ("expansion", "all")
    do_matched = args.scope in ("matched", "all")

    # 1) Register the expansion papers as new catalog sources.
    if do_expansion:
        for entry in litexp:
            sid = entry["source_id"]
            meta = expansion.get(sid)
            if not meta:
                continue
            source = _expansion_to_source(meta)
            review_rows.append(
                {"source_id": sid, "topic": source["topic"], "evidence_class": source["evidence_class"],
                 "include": source["include"], "score": sum(source["screening"].values()), "title": source["title"][:70]}
            )
            if source["include"]:
                stats["included"] += 1
            errors = [i.message for i in validate_source(source) if i.severity == "error"]
            if errors:
                stats.setdefault("validation_errors", []).append({"source_id": sid, "errors": errors})
                continue
            if manager.exists(sid):
                stats["reg_skipped"] += 1
                continue
            if not args.dry_run:
                manager.add_source(source, skip_duplicate_check=True)
            stats["registered"] += 1

    # 2) Copy PDFs into library/<topic>/ and record uploads.
    scope_entries = (matched if do_matched else []) + (litexp if do_expansion else [])
    for entry in scope_entries:
        sid = entry["source_id"]
        topic = catalog_topic.get(sid) or _TOPIC_MAP.get(
            str((expansion.get(sid) or {}).get("topic_bucket")), "research_context"
        )
        src = Path(entry["abs_path"])
        if not src.exists():
            stats["copy_missing"] += 1
            continue
        dest = library_pdf_target(sid, topic)
        if not args.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            upload_by_id[sid] = {
                "source_id": sid,
                "title": (expansion.get(sid) or {}).get("title", entry.get("file", "")),
                "access_mode": args.access_mode,
                "institution_required": False,
                "allowed_uses": (expansion.get(sid) or {}).get("allowed_uses") or ["research_background"],
                "pdf_sha256": _sha256(dest),
                "pdf_bytes": dest.stat().st_size,
                "license_attestation": "imported from local_fulltext_index; admin to verify license",
                "uploaded": date.today().isoformat(),
                "status": "attached",
            }
        stats["copied"] += 1

    if not args.dry_run:
        registry["uploads"] = list(upload_by_id.values())
        _save_uploads(registry)
        manager.rescreen()

    # 3) One-shot vector index rebuild.
    if not args.dry_run and not args.no_build:
        manifest = build_fulltext_vector_index()
        stats["indexed_sources"] = manifest.get("source_count", 0)
        stats["indexed_chunks"] = manifest.get("chunk_count", 0)
        # Mark indexed upload records.
        indexed = {s["source_id"] for s in manifest.get("sources", []) if s.get("chunk_count", 0) > 0}
        for record in registry["uploads"]:
            record["status"] = "indexed" if record["source_id"] in indexed else "attached"
        _save_uploads(registry)

    # 4) Review sheet.
    if not args.dry_run and review_rows:
        lines = [
            "# 文献扩展批导入 · 人工复核表",
            "",
            f"- 生成日期：{date.today().isoformat()}",
            f"- 新登记来源：{stats['registered']}（{stats['included']} included / 其余低于阈值设为 excluded）",
            "- 请复核每条的 **topic / evidence_class / include**，可在后台 `/api/v1/library/admin` 直接调整。",
            "- 导入 PDF 的 access_mode 统一暂设 `" + args.access_mode + "`，请按实际版权核实。",
            "",
            "| source_id | topic | evidence_class | include | score | title |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for r in sorted(review_rows, key=lambda x: (x["topic"], x["source_id"])):
            lines.append(
                f"| {r['source_id']} | {r['topic']} | {r['evidence_class']} | "
                f"{'✓' if r['include'] else '—'} | {r['score']} | {r['title']} |"
            )
        out = resolve_project_path(REVIEW_SHEET)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        stats["review_sheet"] = str(out)

    print(json.dumps({
        "dry_run": args.dry_run,
        "scope": args.scope,
        "matched_pdfs": len(matched),
        "expansion_pdfs": len(litexp),
        **stats,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
