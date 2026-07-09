"""Unified admin backend: the shell page + read-only aggregation endpoints.

The literature CRUD / full-text / ingest *action* endpoints already live in
``app/api/library.py`` and ``app/api/routes.py`` and are reused as-is. This
router only adds the shell HTML and three **read-only** aggregators that the
dashboard / ops / config modules render:

* ``GET /admin``           – the single-page Vue shell (sidebar + modules).
* ``GET /admin/overview``  – cross-module KPIs for the dashboard.
* ``GET /admin/manifests`` – index status (full-text / OpenAI vector manifests + chunk count).
* ``GET /admin/config``    – read-only view of the 6 governance YAMLs (no secrets).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.services.config_loader import load_yaml_config, resolve_project_path

router = APIRouter(tags=["admin"])

_SHELL_HTML = Path(__file__).resolve().parent.parent / "static" / "admin.html"
_PROCESSED = "knowledge_base/processed"

# name -> (relative path, one-line "read by" note for the config viewer)
CONFIG_FILES: Dict[str, Dict[str, str]] = {
    "settings": {"path": "config/settings.yaml", "read_by": "retriever（检索/向量后端/融合权重）、evaluation_runtime"},
    "screening_rules": {"path": "config/screening_rules.yaml", "read_by": "screening、generator（筛查建议引擎）"},
    "safety_terms": {"path": "config/safety_terms.yaml", "read_by": "safety、advisor、rule_engine、generator（安全红线）"},
    "bp_thresholds": {"path": "config/bp_thresholds.yaml", "read_by": "rule_engine（信号质量/血压分级/急症阈值）"},
    "advisor_questions": {"path": "config/advisor_questions.yaml", "read_by": "advisor（随访渐进提问题库）"},
    "field_mapping": {"path": "config/field_mapping.yaml", "read_by": "normalizer（输入字段别名归一化）"},
}


def _read_json(rel_path: str) -> Optional[Dict[str, Any]]:
    """Return the parsed JSON object, or None if missing/unparseable/not-an-object.

    Non-object JSON (arrays, scalars) collapses to None so callers can safely
    call ``.get`` without an AttributeError.
    """

    path = resolve_project_path(rel_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _count_jsonl(rel_path: str) -> int:
    path = resolve_project_path(rel_path)
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_shell() -> HTMLResponse:
    if not _SHELL_HTML.exists():
        return HTMLResponse("<h1>admin shell not found</h1>", status_code=404)
    return HTMLResponse(_SHELL_HTML.read_text(encoding="utf-8"))


@router.get("/admin/overview")
def overview() -> Dict[str, Any]:
    """Cross-module KPIs for the dashboard. Each block degrades gracefully."""

    out: Dict[str, Any] = {}

    # Each block degrades independently: on failure we surface a generic
    # "加载失败" marker (never a raw str(exc), which can embed absolute paths)
    # so the dashboard can render "—" / an error badge instead of crashing.
    try:
        from app.services.library_manager import LibraryManager

        out["library"] = LibraryManager(auto_rescreen=False).stats()
    except Exception:  # pragma: no cover - defensive
        out["library"] = {"error": "加载失败"}

    try:
        from app.services import fulltext_admin

        ft = fulltext_admin.fulltext_status()
        out["fulltext"] = {k: ft.get(k) for k in ("total_sources", "with_pdf", "indexed", "total_chunks")}
    except Exception:
        out["fulltext"] = {"error": "加载失败"}

    try:
        from app.services.kb_audit import audit_knowledge_base

        audit = audit_knowledge_base()
        out["audit"] = {
            "chunk_count": audit.get("chunk_count"),
            "source_count": audit.get("source_count"),
            "missing_topics": len(audit.get("missing_topics") or []),
            "orphan_source_ids": len(audit.get("orphan_source_ids") or []),
            "duplicate_source_hashes": len(audit.get("duplicate_source_hashes") or []),
            "unsafe_source_leakage": len(audit.get("unsafe_source_leakage") or []),
        }
    except Exception:
        out["audit"] = {"error": "加载失败"}

    try:
        gate = _read_json(f"{_PROCESSED}/quality_gate_report.json")
        if gate is None:
            out["quality_gate"] = {"status": "未运行"}
        else:
            stop = gate.get("stop_criteria") or gate.get("stop_criteria_status") or {}
            out["quality_gate"] = {"status": "已运行", "stop_criteria": stop, "timestamp": gate.get("timestamp")}
    except Exception:
        out["quality_gate"] = {"status": "未运行"}

    return out


@router.get("/admin/manifests")
def manifests() -> Dict[str, Any]:
    """Read-only index status from the committed manifests + chunk counts."""

    def _summ(m: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(m, dict):
            return None
        summary = {
            k: m.get(k)
            for k in ("source_count", "chunk_count", "page_count", "embedding_dims", "model", "timestamp", "duration_sec", "vector_path", "chunks_path")
            if k in m
        }
        # A manifest with none of the whitelisted keys yields {}, which is truthy
        # in JS and would render "undefined 源 / undefined chunks"; collapse to None.
        return summary or None

    return {
        "fulltext_vector": _summ(_read_json(f"{_PROCESSED}/fulltext_vector_manifest.json")),
        "openai_processed": _summ(_read_json(f"{_PROCESSED}/openai_embedding_manifest_processed_chunks.json")),
        "openai_fulltext": _summ(_read_json(f"{_PROCESSED}/openai_embedding_manifest_fulltext_chunks.json")),
        "chunks_jsonl_count": _count_jsonl(f"{_PROCESSED}/chunks.jsonl"),
        "fulltext_chunks_count": _count_jsonl("knowledge_base/vector_store/fulltext_chunks.jsonl"),
    }


@router.get("/admin/config")
def config_view() -> Dict[str, Any]:
    """Read-only view of the 6 governance YAMLs (parsed content, no secrets)."""

    files = {}
    for name, meta in CONFIG_FILES.items():
        files[name] = {
            "path": meta["path"],
            "read_by": meta["read_by"],
            "content": load_yaml_config(meta["path"]),
        }
    return {"files": files, "note": "只读；密钥在 .env、不在此展示。修改配置请直接改文件并重启。"}
