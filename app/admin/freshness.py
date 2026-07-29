from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import AdminJob
from app.services.config_loader import resolve_project_path
from app.services.fingerprints import combine_fingerprints, catalog_fingerprint, config_fingerprint, fingerprint_paths, sha256_file
from app.services.fulltext_vector_index import current_fulltext_input_fingerprint


def _json(path: str) -> Dict[str, Any]:
    file_path = resolve_project_path(path)
    if not file_path.exists():
        return {}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _mtime(path: str) -> float:
    file_path = resolve_project_path(path)
    try:
        return file_path.stat().st_mtime
    except OSError:
        return 0.0


def _latest_job_status(db: Optional[Session], locks: List[str]) -> Optional[str]:
    if db is None:
        return None
    row = db.scalar(
        select(AdminJob)
        .where(AdminJob.resource_lock.in_(locks))
        .order_by(AdminJob.created_at.desc())
        .limit(1)
    )
    return row.status if row else None


def _item(
    *,
    key: str,
    label: str,
    exists: bool,
    expected: str,
    actual: str,
    last_built_at: Optional[Any] = None,
    job_status: Optional[str] = None,
    artifact_status: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if job_status in {"queued", "running"}:
        status = "building"
    elif not exists:
        status = "missing"
    elif job_status == "failed" or artifact_status == "failed":
        status = "failed"
    else:
        status = "current" if expected and expected == actual else "stale"
    return {
        "artifact": key,
        "label": label,
        "status": status,
        "input_fingerprint": expected,
        "build_fingerprint": actual,
        "last_built_at": last_built_at,
        "details": details or {},
    }


def artifact_freshness(db: Optional[Session] = None) -> List[Dict[str, Any]]:
    catalog_hash = catalog_fingerprint()
    config_hash = config_fingerprint()
    chunks_hash = sha256_file("knowledge_base/processed/chunks.jsonl")
    raw_hash = fingerprint_paths(["knowledge_base/raw/expanded"])
    chunks_expected = combine_fingerprints({"governed_notes": raw_hash, "catalog": catalog_hash})
    processed_vector_expected = combine_fingerprints(
        {"chunks_sha256": chunks_hash, "chunks_build_fingerprint": chunks_expected}
    )
    fulltext_expected = current_fulltext_input_fingerprint()
    fulltext_chunks_hash = sha256_file("knowledge_base/vector_store/fulltext_chunks.jsonl")

    screen = _json("knowledge_base/processed/source_screening_report.json")
    chunks_manifest = _json("knowledge_base/processed/chunks_manifest.json")
    hashing_processed = _json("knowledge_base/processed/hashing_vector_manifest.json")
    chroma_bge = _json("knowledge_base/processed/chroma_vector_manifest.json")
    openai_processed = _json("knowledge_base/processed/openai_embedding_manifest_processed_chunks.json")
    fulltext = _json("knowledge_base/processed/fulltext_vector_manifest.json")
    openai_fulltext = _json("knowledge_base/processed/openai_embedding_manifest_fulltext_chunks.json")
    quality = _json("knowledge_base/processed/quality_gate_report.json")

    result = [
        _item(
            key="screening",
            label="来源筛选产物",
            exists=bool(screen),
            expected=catalog_hash,
            actual=str(screen.get("input_fingerprint") or ""),
            details={"included_sources": screen.get("included_count")},
            job_status=_latest_job_status(db, ["catalog_write"]),
        ),
        _item(
            key="chunks",
            label="摘要 chunks",
            exists=bool(chunks_hash),
            expected=chunks_expected,
            actual=str(chunks_manifest.get("build_fingerprint") or ""),
            last_built_at=chunks_manifest.get("timestamp"),
            details={"chunk_count": chunks_manifest.get("chunk_count")},
            job_status=_latest_job_status(db, ["kb_write"]),
        ),
        _item(
            key="hashing_processed",
            label="本地哈希向量（摘要）",
            exists=bool(_mtime("knowledge_base/vector_store/processed_hashing_vectors.npz")),
            expected=processed_vector_expected,
            actual=str(hashing_processed.get("input_fingerprint") or "") if hashing_processed.get("status") == "current" else "",
            last_built_at=hashing_processed.get("timestamp"),
            details={"build_status": hashing_processed.get("status")},
            artifact_status=hashing_processed.get("status"),
            job_status=_latest_job_status(db, ["kb_write"]),
        ),
        _item(
            key="chroma_bge",
            label="Chroma / BGE 本地向量",
            exists=bool(_mtime("knowledge_base/vector_store/chroma.sqlite3")),
            expected=processed_vector_expected,
            actual=str(chroma_bge.get("input_fingerprint") or "") if chroma_bge.get("status") == "current" else "",
            last_built_at=chroma_bge.get("timestamp"),
            details={"build_status": chroma_bge.get("status"), "model": chroma_bge.get("model")},
            artifact_status=chroma_bge.get("status"),
            job_status=_latest_job_status(db, ["kb_write"]),
        ),
        _item(
            key="openai_processed",
            label="OpenAI Embedding（摘要）",
            exists=bool(openai_processed),
            expected=combine_fingerprints(
                {"chunks_sha256": chunks_hash, "upstream_build_fingerprint": chunks_expected}
            ),
            actual=str(openai_processed.get("input_fingerprint") or ""),
            last_built_at=openai_processed.get("timestamp"),
            details={"source_count": openai_processed.get("source_count"), "chunk_count": openai_processed.get("chunk_count")},
            job_status=_latest_job_status(db, ["openai_processed"]),
        ),
        _item(
            key="fulltext_local",
            label="本地全文切块 / 哈希向量",
            exists=bool(fulltext),
            expected=fulltext_expected,
            actual=str(fulltext.get("input_fingerprint") or ""),
            last_built_at=fulltext.get("timestamp"),
            details={"source_count": fulltext.get("source_count"), "chunk_count": fulltext.get("chunk_count")},
            artifact_status=fulltext.get("status"),
            job_status=_latest_job_status(db, ["fulltext_index"]),
        ),
        _item(
            key="openai_fulltext",
            label="OpenAI Embedding（全文）",
            exists=bool(openai_fulltext),
            expected=combine_fingerprints(
                {"chunks_sha256": fulltext_chunks_hash, "upstream_build_fingerprint": fulltext_expected}
            ),
            actual=str(openai_fulltext.get("input_fingerprint") or ""),
            last_built_at=openai_fulltext.get("timestamp"),
            details={"source_count": openai_fulltext.get("source_count"), "chunk_count": openai_fulltext.get("chunk_count")},
            job_status=_latest_job_status(db, ["openai_fulltext"]),
        ),
    ]

    quality_inputs = quality.get("input_fingerprints") or {}
    expected_quality = hashlib.sha256(
        json.dumps({"catalog": catalog_hash, "config": config_hash, "chunks": chunks_hash}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    actual_quality = hashlib.sha256(
        json.dumps(
            {
                "catalog": quality_inputs.get("catalog", ""),
                "config": quality_inputs.get("config", ""),
                "chunks": quality_inputs.get("chunks", ""),
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest() if quality_inputs else ""
    result.append(
        _item(
            key="quality_gate",
            label="严格质量门报告",
            exists=bool(quality),
            expected=expected_quality,
            actual=actual_quality,
            last_built_at=quality.get("timestamp"),
            details={"passed": quality.get("passed")},
            job_status=_latest_job_status(db, ["quality_gate"]),
        )
    )
    return result
