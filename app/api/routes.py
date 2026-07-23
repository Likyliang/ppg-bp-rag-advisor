from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError

from app.agents.workflow import generate_report, preview_rules
from app.schemas.conversation import AdvisorTurnResponse, AdvisorUserMessage
from app.schemas.report import HealthReport
from app.schemas.rule_result import RuleResult
from app.services.advisor import advisor_turn, create_session, get_session_store
from app.services.kb_audit import audit_knowledge_base
from app.services.report_builder import report_to_json
from app.services.retriever import last_retrieval_backend, retrieve_knowledge
from app.services.source_catalog import screen_sources
from scripts.ingest_kb import ingest_knowledge_base
from app.admin.security import management_request_guard, require_api_client


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
def preview_rules_endpoint(payload: Dict[str, Any] = Body(openapi_examples={
    "high_bp": {
        "summary": "偏高估算值",
        "value": {
            "estimated_sbp": 145,
            "estimated_dbp": 92,
            "heart_rate": 82,
            "signal_quality_score": 0.86,
            "confidence": 0.68,
            "capture_duration_sec": 30,
            "ppg_source": "camera_finger",
            "algorithm_version": "miniapp-bp-v1.0",
        },
    },
    "emergency": {
        "summary": "严重偏高且胸痛",
        "value": {"estimated_sbp": 185, "estimated_dbp": 122, "signal_quality_score": 0.9, "symptoms": {"chest_pain": True}},
    },
}), _client=Depends(require_api_client("reports:write"))) -> RuleResult:
    try:
        return preview_rules(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reports/generate")
def generate_report_endpoint(request: Request, payload: Dict[str, Any] = Body(openapi_examples={
    "flat_payload": {
        "summary": "小程序扁平字段输入",
        "value": {
            "SBP": 142,
            "DBP": 91,
            "HR": 78,
            "quality_score": 0.86,
            "quality": "good",
            "conf": 0.7,
            "duration": 30,
            "sensor_source": "camera_finger",
            "model_version": "miniapp-bp-v1.0",
            "age": 45,
        },
    },
    "nested_payload": {
        "summary": "标准嵌套输入",
        "value": {
            "measurement": {
                "estimated_sbp": 145,
                "estimated_dbp": 92,
                "heart_rate": 82,
                "signal_quality_score": 0.86,
                "confidence": 0.68,
                "capture_duration_sec": 30,
                "ppg_source": "camera_finger",
                "algorithm_version": "miniapp-bp-v1.0",
            },
            "user_profile": {"age": 45, "antihypertensive_medication": False},
            "symptoms": {"chest_pain": False, "shortness_of_breath": False},
        },
    },
}), _client=Depends(require_api_client("reports:write"))) -> Dict[str, Any]:
    try:
        report: HealthReport = generate_report(payload)
        request.state.generation_mode = report.generation_mode
        request.state.retrieval_backend = last_retrieval_backend()
        request.state.safety_fallback = "fallback" in report.generation_mode
        return report_to_json(report)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/advisor/sessions")
def create_advisor_session_endpoint(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    _client=Depends(require_api_client("advisor:write")),
) -> Dict[str, Any]:
    """Generate the measurement report AND open the follow-up conversation.

    Returns the full report plus the advisor's opening message and first
    gentle intake questions, so the client renders report -> conversation in
    one round trip.
    """
    try:
        report = generate_report(payload)
        session, opening = create_session(payload, report=report)
        request.state.generation_mode = report.generation_mode
        request.state.retrieval_backend = last_retrieval_backend()
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "session_id": session.session_id,
        "report": report_to_json(report),
        "opening": opening.model_dump(),
    }


@router.post("/advisor/sessions/{session_id}/messages", response_model=AdvisorTurnResponse)
def advisor_message_endpoint(
    session_id: str,
    message: AdvisorUserMessage,
    request: Request,
    _client=Depends(require_api_client("advisor:write")),
) -> AdvisorTurnResponse:
    try:
        result = advisor_turn(session_id, message)
        request.state.generation_mode = result.generation_mode
        request.state.retrieval_backend = last_retrieval_backend()
        request.state.safety_fallback = not result.safety.passed or "fallback" in result.generation_mode
        return result
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/advisor/sessions/{session_id}")
def advisor_session_endpoint(
    session_id: str, _client=Depends(require_api_client("advisor:write"))
) -> Dict[str, Any]:
    session = get_session_store().get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"advisor session not found: {session_id}")
    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "stage": session.stage,
        "closed": session.closed,
        "profile": session.profile.model_dump(),
        "asked_question_ids": session.asked_question_ids,
        "answered_question_ids": session.answered_question_ids,
        "declined_question_ids": session.declined_question_ids,
        "history": [turn.model_dump() for turn in session.history],
        "report_id": session.report_id,
    }


@router.delete("/advisor/sessions/{session_id}")
def delete_advisor_session_endpoint(
    session_id: str, _client=Depends(require_api_client("advisor:write"))
) -> Dict[str, Any]:
    deleted = get_session_store().delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"advisor session not found: {session_id}")
    return {"session_id": session_id, "deleted": True}


@router.post("/kb/ingest", deprecated=True)
def ingest_kb_endpoint(
    request: IngestRequest, _principal=Depends(management_request_guard)
) -> Dict[str, Any]:
    if request.raw_dir or request.output_path:
        raise HTTPException(status_code=422, detail="不再接受自定义磁盘路径")
    raise HTTPException(status_code=410, detail="请通过 /api/v1/admin/jobs 创建 ingest_chunks 任务")


@router.get("/kb/sources")
def kb_sources_endpoint(_principal=Depends(management_request_guard)) -> Dict[str, Any]:
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
def kb_audit_endpoint(_principal=Depends(management_request_guard)) -> Dict[str, Any]:
    return audit_knowledge_base()


@router.post("/kb/search")
def kb_search_endpoint(
    request: KbSearchRequest, _client=Depends(require_api_client("kb:search"))
) -> Dict[str, Any]:
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
