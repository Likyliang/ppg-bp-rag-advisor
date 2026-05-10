from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from app.agents.workflow import generate_report, preview_rules
from app.schemas.report import HealthReport
from app.schemas.rule_result import RuleResult
from app.services.kb_audit import audit_knowledge_base
from app.services.report_builder import report_to_json
from app.services.retriever import retrieve_knowledge
from app.services.source_catalog import screen_sources
from scripts.ingest_kb import ingest_knowledge_base


router = APIRouter()


class IngestRequest(BaseModel):
    raw_dir: Optional[str] = None
    output_path: Optional[str] = None


class KbSearchRequest(BaseModel):
    queries: list[str]
    top_k: Optional[int] = 5
    allowed_uses: Optional[list[str]] = None
    evidence_classes: Optional[list[str]] = None
    min_quality_score: Optional[float] = None


@router.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "ppg-bp-rag-agent"}


@router.post("/reports/preview-rules", response_model=RuleResult)
def preview_rules_endpoint(payload: Dict[str, Any]) -> RuleResult:
    try:
        return preview_rules(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reports/generate")
def generate_report_endpoint(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        report: HealthReport = generate_report(payload)
        return report_to_json(report)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/kb/ingest")
def ingest_kb_endpoint(request: IngestRequest) -> Dict[str, Any]:
    return ingest_knowledge_base(raw_dir=request.raw_dir, output_path=request.output_path)


@router.get("/kb/sources")
def kb_sources_endpoint() -> Dict[str, Any]:
    result = screen_sources()
    return {
        "total_sources": result["total_sources"],
        "included_count": result["included_count"],
        "excluded_count": result["excluded_count"],
        "topic_counts": result["topic_counts"],
        "evidence_class_counts": result["evidence_class_counts"],
        "issues": result["issues"],
        "included_sources": result["included_sources"],
        "excluded_sources": result["excluded_sources"],
    }


@router.get("/kb/audit")
def kb_audit_endpoint() -> Dict[str, Any]:
    return audit_knowledge_base()


@router.post("/kb/search")
def kb_search_endpoint(request: KbSearchRequest) -> Dict[str, Any]:
    result = retrieve_knowledge(
        request.queries,
        top_k=request.top_k,
        allowed_uses=request.allowed_uses,
        evidence_classes=request.evidence_classes,
        min_quality_score=request.min_quality_score,
    )
    return {
        "evidence": [item.model_dump() for item in result.evidence],
        "warnings": result.warnings,
    }
