"""Governed full-text management for the knowledge base.

Option "govern the full text": let an admin attach a source's full-text PDF and
make it retrievable, while keeping every existing governance guarantee intact.

What this layer does **not** relax:
* Only sources that are *included* in the catalog can get full text.
* The raw PDF is stored solely under the git-ignored, topic-classified
  ``knowledge_base/library/<topic>/`` (recycle bin: ``library/.trash/``) and the
  extracted text lives only in the git-ignored ``knowledge_base/vector_store/``
  — neither is ever committed
  (mirrors the project's copyright policy: commit citation metadata + Chinese
  summaries only).
* An ``access_mode`` must be declared per upload (the admin attests the copy is
  license-clean); credential-like metadata is rejected.
* Full-text chunks inherit the source's ``allowed_uses`` / ``evidence_class`` /
  ``topic`` (see :mod:`app.services.fulltext_vector_index`), so the Safety Agent
  and use-gating apply to full-text hits exactly as they do to summary notes.

Indexing reuses the existing pipeline: :func:`build_fulltext_vector_index`
extracts every ``downloads/{source_id}.pdf`` for an included source. This module
adds the *management surface* (attach / remove / status) plus a small committed
governance registry, ``knowledge_base/sources/fulltext_uploads.yaml`` (metadata
only — never full text).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.services.config_loader import resolve_project_path
from app.services.fulltext_candidates import (
    ALLOWED_ACCESS_MODES,
    PROTECTED_KEY_PATTERN,
    load_fulltext_catalog,
)
from app.services.fulltext_vector_index import (
    LIBRARY_ROOT,
    MANIFEST_PATH,
    build_fulltext_vector_index,
    governed_pdf_path,
    library_pdf_target,
)
from app.services.source_catalog import ALLOWED_USES, included_sources

UPLOADS_REGISTRY = "knowledge_base/sources/fulltext_uploads.yaml"

# Clinical boundary shown to admins; full text may strengthen explanation only.
GOVERNANCE_NOTE = (
    "全文仅用于强化对不确定性/局限/证据的解释，继承来源的 allowed_uses 与安全门控；"
    "不得据此扩展为诊断、治疗、调药、停药或替代经验证的血压测量。原始 PDF 只存本地、不提交。"
)


class FulltextAdminError(Exception):
    """Raised when a governed full-text operation is rejected."""


# --------------------------------------------------------------------------- #
# Registry I/O (metadata only — committed)
# --------------------------------------------------------------------------- #
def _load_uploads() -> Dict[str, Any]:
    path = resolve_project_path(UPLOADS_REGISTRY)
    if not path.exists():
        return {"version": 1, "uploads": []}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    data.setdefault("uploads", [])
    return data


def _save_uploads(registry: Dict[str, Any]) -> None:
    registry = dict(registry)
    registry["updated"] = date.today().isoformat()
    registry.setdefault("version", 1)
    registry["uploads"] = sorted(registry.get("uploads", []), key=lambda u: u.get("source_id", ""))
    path = resolve_project_path(UPLOADS_REGISTRY)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(
        registry, allow_unicode=True, sort_keys=False, default_flow_style=False, width=4096
    )
    path.write_text(text, encoding="utf-8")


def _uploads_by_source() -> Dict[str, Dict[str, Any]]:
    return {u["source_id"]: u for u in _load_uploads().get("uploads", []) if u.get("source_id")}


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #
def _included_by_id() -> Dict[str, Dict[str, Any]]:
    return {s["source_id"]: s for s in included_sources()}


def _candidate_access_by_source() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for cand in load_fulltext_catalog().get("candidates", []):
        sid = cand.get("source_id")
        if sid and cand.get("access_mode"):
            out[sid] = cand["access_mode"]
    return out


def _read_manifest() -> Dict[str, Any]:
    path = resolve_project_path(MANIFEST_PATH)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _indexed_chunk_counts() -> Dict[str, int]:
    manifest = _read_manifest()
    return {
        s.get("source_id"): int(s.get("chunk_count") or 0)
        for s in manifest.get("sources", [])
        if s.get("source_id")
    }


def _existing_pdf(source_id: str, topic: Optional[str] = None) -> Optional[Path]:
    """Resolve a source's live PDF (library/<topic>/ or legacy), or None."""

    return governed_pdf_path(source_id, topic)


def _trash_pdf_path(source_id: str) -> Path:
    return resolve_project_path(LIBRARY_ROOT) / ".trash" / f"{source_id}.pdf"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _validate_attach(source_id: str, access_mode: str, allowed_uses: List[str]) -> Dict[str, Any]:
    included = _included_by_id()
    source = included.get(source_id)
    if source is None:
        raise FulltextAdminError(
            f"仅允许对已收录(included)的来源附加全文：{source_id} 不在 included_sources 中"
        )
    if access_mode not in ALLOWED_ACCESS_MODES:
        raise FulltextAdminError(
            f"非法 access_mode: {access_mode}（可选：{', '.join(sorted(ALLOWED_ACCESS_MODES))}）"
        )
    invalid = sorted(set(allowed_uses) - ALLOWED_USES)
    if invalid:
        raise FulltextAdminError(f"非法 allowed_uses: {', '.join(invalid)}")
    return source


def _reject_credentials(record: Dict[str, Any]) -> None:
    for key in record:
        if PROTECTED_KEY_PATTERN.search(str(key)):
            raise FulltextAdminError(f"禁止存储凭证类字段：{key}")


# --------------------------------------------------------------------------- #
# Operations
# --------------------------------------------------------------------------- #
def attach_pdf(
    source_id: str,
    pdf_bytes: bytes,
    access_mode: str,
    allowed_uses: Optional[List[str]] = None,
    institution_required: bool = False,
    license_attestation: Optional[str] = None,
    rebuild: bool = True,
) -> Dict[str, Any]:
    """Attach a full-text PDF to an included source and (re)build the index.

    The PDF is written under the git-ignored, topic-classified library folder
    (``library/<topic>/<source_id>.pdf``); only metadata is recorded in the
    committed uploads registry.
    """

    if not pdf_bytes:
        raise FulltextAdminError("空文件")
    if pdf_bytes[:5] != b"%PDF-":
        raise FulltextAdminError("不是有效的 PDF（缺少 %PDF- 头）")

    included = _included_by_id()
    source = included.get(source_id)
    # Default allowed_uses to the source's own scope when the admin omits them.
    uses = list(allowed_uses) if allowed_uses else list((source or {}).get("allowed_uses", []))
    source = _validate_attach(source_id, access_mode, uses)

    # Drop any stale copy in another topic folder, then write to the canonical slot.
    stale = _existing_pdf(source_id, source.get("topic"))
    pdf_path = library_pdf_target(source_id, source.get("topic"))
    if stale is not None and stale.resolve() != pdf_path.resolve():
        stale.unlink()
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_bytes)

    record = {
        "source_id": source_id,
        "title": source.get("title", ""),
        "access_mode": access_mode,
        "institution_required": bool(institution_required),
        "allowed_uses": uses,
        "pdf_sha256": _sha256(pdf_bytes),
        "pdf_bytes": len(pdf_bytes),
        "license_attestation": license_attestation or "admin asserts license-clean local use",
        "uploaded": date.today().isoformat(),
        "status": "attached",
    }
    _reject_credentials(record)

    registry = _load_uploads()
    registry["uploads"] = [u for u in registry.get("uploads", []) if u.get("source_id") != source_id]
    registry["uploads"].append(record)
    _save_uploads(registry)

    result: Dict[str, Any] = {"action": "attached", "source_id": source_id, "record": record}
    if rebuild:
        manifest = build_fulltext_vector_index()
        record["status"] = "indexed"
        _save_uploads(registry)
        result["indexed_chunk_count"] = _indexed_chunk_counts().get(source_id, 0)
        result["total_chunks"] = manifest.get("chunk_count", 0)
    return result


def remove_fulltext(source_id: str, rebuild: bool = True) -> Dict[str, Any]:
    """Delete a source's local PDF + upload record and rebuild the index."""

    pdf_path = _existing_pdf(source_id)
    existed = pdf_path is not None
    if existed:
        pdf_path.unlink()

    registry = _load_uploads()
    before = len(registry.get("uploads", []))
    registry["uploads"] = [u for u in registry.get("uploads", []) if u.get("source_id") != source_id]
    removed_record = before != len(registry["uploads"])
    if removed_record:
        _save_uploads(registry)

    if not existed and not removed_record:
        raise FulltextAdminError(f"该来源没有本地全文可移除：{source_id}")

    result = {"action": "removed", "source_id": source_id, "removed_pdf": existed}
    if rebuild:
        manifest = build_fulltext_vector_index()
        result["total_chunks"] = manifest.get("chunk_count", 0)
    return result


def trash_fulltext(source_id: str, rebuild: bool = True) -> Dict[str, Any]:
    """Move a source's local PDF into the recycle bin (library/.trash/).

    Recoverable via :func:`restore_fulltext`. The upload record is kept and
    marked ``trashed`` so metadata survives for restore. No-op if there is no
    local full text.
    """

    pdf_path = _existing_pdf(source_id)
    registry = _load_uploads()
    record = next((u for u in registry.get("uploads", []) if u.get("source_id") == source_id), None)
    if pdf_path is None and record is None:
        return {"action": "noop", "source_id": source_id}

    if pdf_path is not None:
        trash_path = _trash_pdf_path(source_id)
        trash_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.replace(trash_path)
    if record is not None:
        record["status"] = "trashed"
        _save_uploads(registry)

    result = {"action": "trashed", "source_id": source_id}
    if rebuild:
        build_fulltext_vector_index()
    return result


def restore_fulltext(source_id: str, rebuild: bool = True) -> Dict[str, Any]:
    """Move a source's PDF back from the recycle bin and reindex."""

    trash_path = _trash_pdf_path(source_id)
    if not trash_path.exists():
        return {"action": "noop", "source_id": source_id}
    topic = (_included_by_id().get(source_id) or {}).get("topic")
    pdf_path = library_pdf_target(source_id, topic)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    trash_path.replace(pdf_path)

    registry = _load_uploads()
    record = next((u for u in registry.get("uploads", []) if u.get("source_id") == source_id), None)
    if record is not None:
        record["status"] = "attached"
        _save_uploads(registry)

    result = {"action": "restored", "source_id": source_id}
    if rebuild:
        build_fulltext_vector_index()
    return result


def purge_fulltext(source_id: str) -> Dict[str, Any]:
    """Permanently delete a source's trashed PDF and drop its upload record."""

    purged = False
    live = _existing_pdf(source_id)
    for path in (_trash_pdf_path(source_id), live):
        if path is not None and path.exists():
            path.unlink()
            purged = True
    registry = _load_uploads()
    before = len(registry.get("uploads", []))
    registry["uploads"] = [u for u in registry.get("uploads", []) if u.get("source_id") != source_id]
    if before != len(registry["uploads"]):
        _save_uploads(registry)
        purged = True
    return {"action": "purged", "source_id": source_id, "purged": purged}


def build_fulltext(source_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    """(Re)build the local full-text vector index from downloaded PDFs."""

    manifest = build_fulltext_vector_index(source_ids=source_ids)
    # Sync upload records to 'indexed' where chunks were produced.
    counts = _indexed_chunk_counts()
    registry = _load_uploads()
    changed = False
    for record in registry.get("uploads", []):
        want = "indexed" if counts.get(record.get("source_id"), 0) > 0 else "attached"
        if record.get("status") != want:
            record["status"] = want
            changed = True
    if changed:
        _save_uploads(registry)
    return {
        "source_count": manifest.get("source_count", 0),
        "chunk_count": manifest.get("chunk_count", 0),
        "page_count": manifest.get("page_count", 0),
        "skipped": manifest.get("skipped", []),
    }


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #
def source_fulltext_status(source_id: str) -> Dict[str, Any]:
    included = _included_by_id()
    if source_id not in included:
        raise FulltextAdminError(f"未收录来源：{source_id}")
    uploads = _uploads_by_source()
    counts = _indexed_chunk_counts()
    cand_access = _candidate_access_by_source()
    source = included[source_id]
    upload = uploads.get(source_id)
    return {
        "source_id": source_id,
        "title": source.get("title", ""),
        "has_pdf": _existing_pdf(source_id, source.get("topic")) is not None,
        "indexed": counts.get(source_id, 0) > 0,
        "chunk_count": counts.get(source_id, 0),
        "access_mode": (upload or {}).get("access_mode") or cand_access.get(source_id),
        "managed_by": "upload" if upload else ("curated_candidate" if source_id in cand_access else "none"),
        "allowed_uses": (upload or {}).get("allowed_uses") or source.get("allowed_uses", []),
    }


def fulltext_status() -> Dict[str, Any]:
    """Per-source full-text status across all included sources, plus totals."""

    included = _included_by_id()
    uploads = _uploads_by_source()
    counts = _indexed_chunk_counts()
    cand_access = _candidate_access_by_source()

    rows: List[Dict[str, Any]] = []
    for source_id, source in included.items():
        upload = uploads.get(source_id)
        has_pdf = _existing_pdf(source_id, source.get("topic")) is not None
        chunk_count = counts.get(source_id, 0)
        if not (upload or has_pdf or chunk_count or source_id in cand_access):
            managed_by = "none"
        else:
            managed_by = "upload" if upload else ("curated_candidate" if source_id in cand_access else "none")
        rows.append(
            {
                "source_id": source_id,
                "title": source.get("title", ""),
                "has_pdf": has_pdf,
                "indexed": chunk_count > 0,
                "chunk_count": chunk_count,
                "access_mode": (upload or {}).get("access_mode") or cand_access.get(source_id),
                "managed_by": managed_by,
            }
        )
    rows.sort(key=lambda r: (not r["indexed"], not r["has_pdf"], r["source_id"]))
    return {
        "total_sources": len(rows),
        "with_pdf": sum(1 for r in rows if r["has_pdf"]),
        "indexed": sum(1 for r in rows if r["indexed"]),
        "total_chunks": sum(r["chunk_count"] for r in rows),
        "uploads": len(uploads),
        "governance_note": GOVERNANCE_NOTE,
        "access_modes": sorted(ALLOWED_ACCESS_MODES),
        "sources": rows,
    }
