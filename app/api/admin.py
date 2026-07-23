"""Authenticated internal administration API.

The patient-facing report/advisor contracts remain in ``app.api.routes``.
This router owns only governance and operations: accounts, literature drafts,
config releases, provider integrations, jobs, freshness, metrics and audit.
"""

from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.admin.audit import write_audit
from app.admin.config_service import (
    CONFIG_SPECS,
    ConfigConflictError,
    ConfigValidationError,
    create_config_draft,
    current_revision,
    draft_dict as config_draft_dict,
    list_configs,
    publish_config_draft,
    revision_dict,
)
from app.admin.db import get_db
from app.admin.draft_service import (
    create_literature_draft,
    draft_dict as literature_draft_dict,
    LiteratureDraftConflictError,
    list_literature_drafts,
    publish_literature_draft,
    reject_literature_draft,
    update_literature_draft,
    validate_literature_draft,
)
from app.admin.freshness import artifact_freshness
from app.admin.integration_service import (
    SecretConfigurationError,
    clear_integration_secret,
    list_integrations,
    set_integration_secret,
    test_integration,
    update_integration,
)
from app.admin.job_service import (
    cancel_job,
    create_job,
    job_dict,
    retry_job,
)
from app.admin.metrics import metrics_summary
from app.admin.models import (
    AdminJob,
    AdminSession,
    AdminUser,
    ApiClient,
    AuditEvent,
    ConfigDraft,
    ConfigRevision,
    JobEvent,
    LiteratureDraft,
    utcnow,
)
from app.admin.schemas import (
    ApiClientCreate,
    ConfigDraftCreate,
    ConfigPublishRequest,
    ConfigRollbackRequest,
    IntegrationSecretUpdate,
    IntegrationUpdate,
    JobCreate,
    LiteratureDraftCreate,
    LiteratureDraftPatch,
    LiteratureRejectRequest,
    LoginRequest,
    UserCreate,
    UserUpdate,
)
from app.admin.security import (
    AdminPrincipal,
    check_login_rate_limit,
    clear_login_failures,
    clear_login_session,
    create_login_session,
    csrf_protect,
    generate_api_client_key,
    get_current_principal,
    hash_password,
    hash_token,
    record_login_failure,
    scopes_json,
    verify_password,
)
from app.services.config_loader import load_yaml_config, resolve_project_path
from app.services.library_manager import LibraryConflictError, LibraryError, LibraryManager
from app.services.retriever import last_retrieval_backend, retrieve_knowledge


router = APIRouter(tags=["admin"])
_PROCESSED = "knowledge_base/processed"

# Kept as a public module constant for compatibility with existing tests and
# tooling. Config publishing uses the richer CONFIG_SPECS registry.
CONFIG_FILES: Dict[str, Dict[str, str]] = {
    key: {"path": spec["path"], "read_by": spec["read_by"]}
    for key, spec in CONFIG_SPECS.items()
}


class AdminRetrievalRequest(BaseModel):
    queries: List[str] = Field(min_length=1, max_length=10)
    top_k: int = Field(default=5, ge=1, le=20)
    allowed_uses: Optional[List[str]] = None
    evidence_classes: Optional[List[str]] = None
    min_quality_score: Optional[float] = None


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", ""))


def _require(principal: AdminPrincipal, *roles: str) -> None:
    if principal.role not in set(roles):
        raise HTTPException(status_code=403, detail="权限不足")


def _read_json(rel_path: str) -> Optional[Dict[str, Any]]:
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


def _dt(value) -> Optional[str]:
    return value.isoformat() if value else None


def _user_dict(user: AdminUser) -> Dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "active": user.active,
        "created_at": _dt(user.created_at),
        "updated_at": _dt(user.updated_at),
        "last_login_at": _dt(user.last_login_at),
    }


def _api_client_dict(client: ApiClient) -> Dict[str, Any]:
    return {
        "id": client.id,
        "name": client.name,
        "key_prefix": client.key_prefix,
        "scopes": json.loads(client.scopes_json or "[]"),
        "rate_limit_per_minute": client.rate_limit_per_minute,
        "active": client.active,
        "expires_at": _dt(client.expires_at),
        "revoked_at": _dt(client.revoked_at),
        "created_at": _dt(client.created_at),
        "last_used_at": _dt(client.last_used_at),
    }


@router.get("/admin", include_in_schema=False)
def admin_legacy_entry() -> RedirectResponse:
    return RedirectResponse(url="/admin/", status_code=302)


# ---------------------------------------------------------------------------
# Authentication and access control
# ---------------------------------------------------------------------------
@router.post("/admin/auth/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Response:
    remote = request.client.host if request.client else "unknown"
    check_login_rate_limit(remote)
    user = db.scalar(select(AdminUser).where(AdminUser.username == payload.username))
    if user is None or not user.active or not verify_password(user.password_hash, payload.password):
        record_login_failure(remote)
        write_audit(
            db,
            principal=None,
            action="auth.login",
            resource_type="admin_session",
            request_id=_request_id(request),
            status="failed",
            details={"username_hash": hash_token(payload.username)},
        )
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    clear_login_failures(remote)
    response = JSONResponse({"user": _user_dict(user)})
    create_login_session(db, user, request, response)
    write_audit(
        db,
        principal=AdminPrincipal(user.id, user.username, user.role),
        action="auth.login",
        resource_type="admin_session",
        request_id=_request_id(request),
    )
    return response


@router.get("/admin/auth/me")
def me(principal: AdminPrincipal = Depends(get_current_principal)) -> Dict[str, Any]:
    return {
        "id": principal.user_id,
        "username": principal.username,
        "role": principal.role,
        "auth_disabled": principal.auth_disabled,
    }


@router.post("/admin/auth/logout")
def logout(
    request: Request,
    response: Response,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, bool]:
    clear_login_session(db, request, response)
    write_audit(
        db,
        principal=principal,
        action="auth.logout",
        resource_type="admin_session",
        request_id=_request_id(request),
    )
    return {"ok": True}


@router.get("/admin/users")
def users(
    principal: AdminPrincipal = Depends(get_current_principal), db: Session = Depends(get_db)
) -> Dict[str, Any]:
    _require(principal, "admin")
    rows = db.scalars(select(AdminUser).order_by(AdminUser.username)).all()
    return {"users": [_user_dict(row) for row in rows]}


@router.post("/admin/users", status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    try:
        row = AdminUser(username=payload.username, password_hash=hash_password(payload.password), role=payload.role)
        db.add(row)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="用户名已存在") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail="密码不满足安全要求") from exc
    write_audit(
        db,
        principal=principal,
        action="user.create",
        resource_type="admin_user",
        resource_id=row.id,
        request_id=_request_id(request),
        after={"username": row.username, "role": row.role, "active": row.active},
    )
    return _user_dict(row)


@router.patch("/admin/users/{user_id}")
def update_user(
    user_id: str,
    payload: UserUpdate,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    row = db.get(AdminUser, user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    before = _user_dict(row)
    if payload.role is not None:
        if row.id == principal.user_id and payload.role != "admin":
            raise HTTPException(status_code=422, detail="不能降低当前管理员自己的角色")
        if row.role == "admin" and payload.role != "admin":
            other_admin = db.scalar(
                select(AdminUser.id).where(
                    AdminUser.role == "admin", AdminUser.active.is_(True), AdminUser.id != row.id
                ).limit(1)
            )
            if other_admin is None:
                raise HTTPException(status_code=422, detail="必须保留至少一个启用的管理员")
        row.role = payload.role
    if payload.active is not None:
        if row.id == principal.user_id and not payload.active:
            raise HTTPException(status_code=422, detail="不能停用当前账号")
        if row.role == "admin" and not payload.active:
            other_admin = db.scalar(
                select(AdminUser.id).where(
                    AdminUser.role == "admin", AdminUser.active.is_(True), AdminUser.id != row.id
                ).limit(1)
            )
            if other_admin is None:
                raise HTTPException(status_code=422, detail="必须保留至少一个启用的管理员")
        row.active = payload.active
    if payload.password is not None:
        row.password_hash = hash_password(payload.password)
    if payload.role is not None or payload.active is not None or payload.password is not None:
        for session in db.scalars(
            select(AdminSession).where(AdminSession.user_id == row.id, AdminSession.revoked_at.is_(None))
        ).all():
            session.revoked_at = utcnow()
    db.commit()
    write_audit(
        db,
        principal=principal,
        action="user.update",
        resource_type="admin_user",
        resource_id=row.id,
        request_id=_request_id(request),
        before=before,
        after=_user_dict(row),
    )
    return _user_dict(row)


@router.get("/admin/api-clients")
def api_clients(
    principal: AdminPrincipal = Depends(get_current_principal), db: Session = Depends(get_db)
) -> Dict[str, Any]:
    _require(principal, "admin")
    rows = db.scalars(select(ApiClient).order_by(ApiClient.created_at.desc())).all()
    return {"api_clients": [_api_client_dict(row) for row in rows]}


@router.post("/admin/api-clients", status_code=201)
def create_api_client(
    payload: ApiClientCreate,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    raw_key = generate_api_client_key()
    row = ApiClient(
        name=payload.name,
        key_prefix=raw_key[:12],
        key_hash=hash_token(raw_key),
        scopes_json=scopes_json(payload.scopes),
        rate_limit_per_minute=payload.rate_limit_per_minute,
        expires_at=payload.expires_at,
        created_by=principal.user_id,
    )
    try:
        db.add(row)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="API Client 名称重复") from exc
    write_audit(
        db,
        principal=principal,
        action="api_client.create",
        resource_type="api_client",
        resource_id=row.id,
        request_id=_request_id(request),
        after=_api_client_dict(row),
    )
    return {**_api_client_dict(row), "api_key": raw_key, "api_key_once": True}


@router.post("/admin/api-clients/{client_id}/revoke")
def revoke_api_client(
    client_id: str,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    row = db.get(ApiClient, client_id)
    if row is None:
        raise HTTPException(status_code=404, detail="API Client 不存在")
    before = _api_client_dict(row)
    row.active = False
    row.revoked_at = utcnow()
    db.commit()
    write_audit(
        db,
        principal=principal,
        action="api_client.revoke",
        resource_type="api_client",
        resource_id=row.id,
        request_id=_request_id(request),
        before=before,
        after=_api_client_dict(row),
    )
    return _api_client_dict(row)


# ---------------------------------------------------------------------------
# Existing dashboard aggregators
# ---------------------------------------------------------------------------
@router.get("/admin/overview")
def overview(
    principal: AdminPrincipal = Depends(get_current_principal), db: Session = Depends(get_db)
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        from app.services.library_manager import LibraryManager as RuntimeLibraryManager

        out["library"] = RuntimeLibraryManager(auto_rescreen=False).stats()
    except Exception:
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
    gate = _read_json(f"{_PROCESSED}/quality_gate_report.json")
    out["quality_gate"] = (
        {"status": "未运行"}
        if gate is None
        else {"status": "已运行", "passed": gate.get("passed"), "timestamp": gate.get("timestamp")}
    )
    freshness = artifact_freshness(db)
    out["freshness"] = {
        "items": freshness,
        "alert_count": sum(1 for item in freshness if item["status"] != "current"),
    }
    out["jobs"] = {
        "queued": len(db.scalars(select(AdminJob).where(AdminJob.status == "queued")).all()),
        "running": len(db.scalars(select(AdminJob).where(AdminJob.status == "running")).all()),
        "failed": len(db.scalars(select(AdminJob).where(AdminJob.status == "failed")).all()),
    }
    out["integrations"] = list_integrations(db)
    return out


@router.get("/admin/manifests")
def manifests(principal: AdminPrincipal = Depends(get_current_principal)) -> Dict[str, Any]:
    def summary(value: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(value, dict):
            return None
        allowed = (
            "source_count",
            "chunk_count",
            "page_count",
            "embedding_dims",
            "embedding_dimensions",
            "model",
            "model_requested",
            "timestamp",
            "duration_sec",
            "input_sha256",
            "input_fingerprint",
            "build_fingerprint",
            "upstream_build_fingerprint",
            "catalog_fingerprint",
            "status",
            "backend",
            "vector_path",
        )
        result = {key: value.get(key) for key in allowed if key in value}
        return result or None

    return {
        "chunks": summary(_read_json(f"{_PROCESSED}/chunks_manifest.json")),
        "processed_local_hashing": summary(_read_json(f"{_PROCESSED}/hashing_vector_manifest.json")),
        "chroma_bge": summary(_read_json(f"{_PROCESSED}/chroma_vector_manifest.json")),
        "fulltext_local_hashing": summary(_read_json(f"{_PROCESSED}/fulltext_vector_manifest.json")),
        "openai_processed": summary(_read_json(f"{_PROCESSED}/openai_embedding_manifest_processed_chunks.json")),
        "openai_fulltext": summary(_read_json(f"{_PROCESSED}/openai_embedding_manifest_fulltext_chunks.json")),
        # Legacy alias for one release.
        "fulltext_vector": summary(_read_json(f"{_PROCESSED}/fulltext_vector_manifest.json")),
        "chunks_jsonl_count": _count_jsonl(f"{_PROCESSED}/chunks.jsonl"),
        "fulltext_chunks_count": _count_jsonl("knowledge_base/vector_store/fulltext_chunks.jsonl"),
    }


@router.get("/admin/config")
def config_view(principal: AdminPrincipal = Depends(get_current_principal)) -> Dict[str, Any]:
    files = {
        item["key"]: {
            "path": item["path"],
            "read_by": item["read_by"],
            "risk_level": item["risk_level"],
            "revision": item["revision"],
            "content": item["content"],
        }
        for item in list_configs()
    }
    return {"files": files, "note": "配置通过草稿、校验、发布和回滚管理；密钥在集成模块中永不回显。"}


# ---------------------------------------------------------------------------
# Literature drafts
# ---------------------------------------------------------------------------
@router.get("/admin/library/drafts")
def literature_drafts(
    status_filter: str = Query("", alias="status"),
    principal: AdminPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin", "curator", "reviewer", "viewer")
    rows = list_literature_drafts(db, status=status_filter)
    return {"count": len(rows), "drafts": rows}


@router.post("/admin/library/drafts", status_code=201)
def create_literature_draft_endpoint(
    payload: LiteratureDraftCreate,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin", "curator")
    try:
        row = create_literature_draft(db, payload.source, principal.user_id)
    except (LibraryError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        db,
        principal=principal,
        action="literature_draft.create",
        resource_type="literature_draft",
        resource_id=row.id,
        request_id=_request_id(request),
        after=payload.source,
    )
    return literature_draft_dict(row)


@router.patch("/admin/library/drafts/{draft_id}")
def update_literature_draft_endpoint(
    draft_id: str,
    payload: LiteratureDraftPatch,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin", "curator")
    row = db.get(LiteratureDraft, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="草稿不存在")
    before = literature_draft_dict(row)["source"]
    try:
        row = update_literature_draft(db, row, payload.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        db,
        principal=principal,
        action="literature_draft.update",
        resource_type="literature_draft",
        resource_id=row.id,
        request_id=_request_id(request),
        before=before,
        after=payload.source,
    )
    return literature_draft_dict(row)


@router.post("/admin/library/drafts/{draft_id}/validate")
def validate_literature_draft_endpoint(
    draft_id: str,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin", "curator", "reviewer")
    row = db.get(LiteratureDraft, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="草稿不存在")
    result = validate_literature_draft(db, row, LibraryManager(auto_rescreen=False))
    write_audit(
        db,
        principal=principal,
        action="literature_draft.validate",
        resource_type="literature_draft",
        resource_id=row.id,
        request_id=_request_id(request),
        status="success" if result["passed"] else "failed",
        details=result,
    )
    return {"draft": literature_draft_dict(row), "validation": result}


@router.post("/admin/library/drafts/{draft_id}/publish")
def publish_literature_draft_endpoint(
    draft_id: str,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin", "reviewer")
    row = db.get(LiteratureDraft, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        result = publish_literature_draft(
            db,
            row,
            LibraryManager(auto_rescreen=False),
            principal.user_id,
        )
    except (LiteratureDraftConflictError, LibraryConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, LibraryError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    screening_job = create_job(db, "rescreen", {}, principal.user_id)
    result["job"] = job_dict(screening_job)
    write_audit(
        db,
        principal=principal,
        action="literature_draft.publish",
        resource_type="literature_source",
        resource_id=result.get("source_id"),
        request_id=_request_id(request),
        after=result.get("source"),
        details={"screening_job_id": screening_job.id},
    )
    return result


@router.post("/admin/library/drafts/{draft_id}/reject")
def reject_literature_draft_endpoint(
    draft_id: str,
    payload: LiteratureRejectRequest,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin", "reviewer")
    row = db.get(LiteratureDraft, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        row = reject_literature_draft(db, row, principal.user_id, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        db,
        principal=principal,
        action="literature_draft.reject",
        resource_type="literature_draft",
        resource_id=row.id,
        request_id=_request_id(request),
        reason=payload.reason,
        after={"status": "rejected"},
    )
    return literature_draft_dict(row)


# ---------------------------------------------------------------------------
# Config releases
# ---------------------------------------------------------------------------
@router.get("/admin/configs")
def configs(principal: AdminPrincipal = Depends(get_current_principal)) -> Dict[str, Any]:
    return {"configs": list_configs()}


@router.post("/admin/configs/{config_key}/drafts", status_code=201)
def create_config_draft_endpoint(
    config_key: str,
    payload: ConfigDraftCreate,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    try:
        row = create_config_draft(db, config_key, payload.content, principal.user_id, payload.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="配置不存在") from exc
    except ConfigValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        db,
        principal=principal,
        action="config_draft.create",
        resource_type="config_draft",
        resource_id=row.id,
        request_id=_request_id(request),
        after={"config_key": config_key, "base_revision": row.base_revision},
    )
    return config_draft_dict(row)


@router.get("/admin/config-drafts")
def config_drafts(
    principal: AdminPrincipal = Depends(get_current_principal), db: Session = Depends(get_db)
) -> Dict[str, Any]:
    rows = db.scalars(select(ConfigDraft).order_by(ConfigDraft.updated_at.desc()).limit(200)).all()
    return {"drafts": [config_draft_dict(row) for row in rows]}


@router.post("/admin/config-drafts/{draft_id}/validate", status_code=202)
def validate_config_draft_endpoint(
    draft_id: str,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    row = db.get(ConfigDraft, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="配置草稿不存在")
    if row.status == "validating":
        raise HTTPException(status_code=409, detail="配置草稿已在校验队列中")
    row.status = "validating"
    db.commit()
    job = create_job(db, "validate_config_draft", {"draft_id": row.id}, principal.user_id)
    write_audit(
        db,
        principal=principal,
        action="config_draft.validation_enqueued",
        resource_type="config_draft",
        resource_id=row.id,
        request_id=_request_id(request),
        details={"job_id": job.id, "risk_level": row.risk_level},
    )
    return {"draft": config_draft_dict(row), "job": job_dict(job)}


@router.post("/admin/config-drafts/{draft_id}/publish")
def publish_config_draft_endpoint(
    draft_id: str,
    payload: ConfigPublishRequest,
    request: Request,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    row = db.get(ConfigDraft, draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="配置草稿不存在")
    before = {"config_key": row.config_key, "revision": row.base_revision}
    if not if_match:
        raise HTTPException(status_code=428, detail="配置发布必须提供 If-Match revision")
    header_revision = if_match.strip().strip('"')
    if header_revision != payload.expected_revision:
        raise HTTPException(status_code=409, detail="If-Match 与请求 revision 不一致")
    try:
        result = publish_config_draft(
            db,
            row,
            user_id=principal.user_id,
            reason=payload.reason,
            expected_revision=payload.expected_revision,
            confirmation=payload.confirmation,
        )
    except ConfigConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ConfigValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        db,
        principal=principal,
        action="config.publish",
        resource_type="config",
        resource_id=row.config_key,
        request_id=_request_id(request),
        reason=payload.reason,
        before=before,
        after=result,
    )
    return result


@router.get("/admin/config-revisions")
def config_revisions(
    config_key: str = "",
    principal: AdminPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    statement = select(ConfigRevision).order_by(ConfigRevision.created_at.desc()).limit(200)
    if config_key:
        statement = statement.where(ConfigRevision.config_key == config_key)
    rows = db.scalars(statement).all()
    return {"revisions": [revision_dict(row) for row in rows]}


@router.post("/admin/config-revisions/{revision_id}/rollback", status_code=202)
def rollback_config_endpoint(
    revision_id: str,
    payload: ConfigRollbackRequest,
    request: Request,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    row = db.get(ConfigRevision, revision_id)
    if row is None:
        raise HTTPException(status_code=404, detail="配置版本不存在")
    if not if_match:
        raise HTTPException(status_code=428, detail="安全回滚必须提供当前配置的 If-Match revision")
    expected_revision = if_match.strip().strip('"')
    if expected_revision != current_revision(row.config_key):
        raise HTTPException(status_code=409, detail="当前配置已变化，请刷新后重新确认回滚")
    job = create_job(
        db,
        "rollback_config_revision",
        {
            "revision_id": row.id,
            "reason": payload.reason,
            "expected_revision": expected_revision,
        },
        principal.user_id,
    )
    write_audit(
        db,
        principal=principal,
        action="config.rollback_enqueued",
        resource_type="config",
        resource_id=row.config_key,
        request_id=_request_id(request),
        reason=payload.reason,
        details={"job_id": job.id, "target_revision": row.revision},
    )
    return {"job": job_dict(job), "config_key": row.config_key, "target_revision": row.revision}


# ---------------------------------------------------------------------------
# Provider integrations
# ---------------------------------------------------------------------------
@router.get("/admin/integrations")
def integrations(
    principal: AdminPrincipal = Depends(get_current_principal), db: Session = Depends(get_db)
) -> Dict[str, Any]:
    return {"integrations": list_integrations(db)}


@router.put("/admin/integrations/{channel}")
def update_integration_endpoint(
    channel: str,
    payload: IntegrationUpdate,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    before = next((item for item in list_integrations(db) if item["channel"] == channel), None)
    try:
        result = update_integration(db, channel, payload.model_dump(), principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="集成通道不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        db,
        principal=principal,
        action="integration.update",
        resource_type="integration",
        resource_id=channel,
        request_id=_request_id(request),
        before=before,
        after=result,
    )
    return result


@router.put("/admin/integrations/{channel}/secret")
def update_integration_secret_endpoint(
    channel: str,
    payload: IntegrationSecretUpdate,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    try:
        result = set_integration_secret(db, channel, payload.secret, principal.user_id)
    except (ValueError, SecretConfigurationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        db,
        principal=principal,
        action="integration.secret.rotate",
        resource_type="integration",
        resource_id=channel,
        request_id=_request_id(request),
        details={"secret_configured": True},
    )
    return result


@router.delete("/admin/integrations/{channel}/secret")
def delete_integration_secret_endpoint(
    channel: str,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    try:
        result = clear_integration_secret(db, channel, principal.user_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="集成通道不存在") from exc
    write_audit(
        db,
        principal=principal,
        action="integration.secret.clear",
        resource_type="integration",
        resource_id=channel,
        request_id=_request_id(request),
    )
    return result


@router.post("/admin/integrations/{channel}/test")
def test_integration_endpoint(
    channel: str,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    try:
        result = test_integration(db, channel)
    except (KeyError, SecretConfigurationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        db,
        principal=principal,
        action="integration.test",
        resource_type="integration",
        resource_id=channel,
        request_id=_request_id(request),
        status="success" if result.get("ok") else "failed",
        details=result,
    )
    return result


# ---------------------------------------------------------------------------
# Jobs, freshness, quality, metrics and audit
# ---------------------------------------------------------------------------
@router.get("/admin/jobs")
def jobs(
    status_filter: str = Query("", alias="status"),
    principal: AdminPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    statement = select(AdminJob).order_by(AdminJob.created_at.desc()).limit(200)
    if status_filter:
        statement = statement.where(AdminJob.status == status_filter)
    rows = db.scalars(statement).all()
    return {"jobs": [job_dict(row) for row in rows]}


@router.post("/admin/jobs", status_code=202)
def enqueue_job(
    payload: JobCreate,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    if payload.job_type in {"quality_gate", "retrieval_evaluation", "report_evaluation", "api_experiment", "kb_audit"}:
        _require(principal, "admin", "reviewer")
    else:
        _require(principal, "admin")
    try:
        row = create_job(db, payload.job_type, payload.parameters, principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        db,
        principal=principal,
        action="job.enqueue",
        resource_type="admin_job",
        resource_id=row.id,
        request_id=_request_id(request),
        details={"job_type": row.job_type, "resource_lock": row.resource_lock},
    )
    return job_dict(row)


@router.get("/admin/jobs/{job_id}")
def get_job(
    job_id: str,
    principal: AdminPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    row = db.get(AdminJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job_dict(row)


@router.get("/admin/jobs/{job_id}/events")
def job_events(
    job_id: str,
    principal: AdminPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    rows = db.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.sequence)).all()
    return {
        "events": [
            {"sequence": row.sequence, "created_at": _dt(row.created_at), "level": row.level, "message": row.message}
            for row in rows
        ]
    }


@router.post("/admin/jobs/{job_id}/retry", status_code=202)
def retry_job_endpoint(
    job_id: str,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    row = db.get(AdminJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if row.job_type in {"quality_gate", "retrieval_evaluation", "report_evaluation", "api_experiment", "kb_audit"}:
        _require(principal, "admin", "reviewer")
    else:
        # Retrying must preserve the same authorization boundary as enqueueing;
        # otherwise a reviewer could restart an administrator-only index job.
        _require(principal, "admin")
    try:
        clone = retry_job(db, row, principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        db,
        principal=principal,
        action="job.retry",
        resource_type="admin_job",
        resource_id=clone.id,
        request_id=_request_id(request),
        details={"parent_id": row.id},
    )
    return job_dict(clone)


@router.post("/admin/jobs/{job_id}/cancel")
def cancel_job_endpoint(
    job_id: str,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin")
    row = db.get(AdminJob, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        row = cancel_job(db, row)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    write_audit(
        db,
        principal=principal,
        action="job.cancel",
        resource_type="admin_job",
        resource_id=row.id,
        request_id=_request_id(request),
    )
    return job_dict(row)


@router.get("/admin/freshness")
def freshness(
    principal: AdminPrincipal = Depends(get_current_principal), db: Session = Depends(get_db)
) -> Dict[str, Any]:
    items = artifact_freshness(db)
    return {"items": items, "alert_count": sum(1 for item in items if item["status"] != "current")}


@router.post("/admin/retrieval/search")
def admin_retrieval_search(
    payload: AdminRetrievalRequest,
    request: Request,
    principal: AdminPrincipal = Depends(csrf_protect),
) -> Dict[str, Any]:
    result = retrieve_knowledge(
        payload.queries,
        top_k=payload.top_k,
        allowed_uses=payload.allowed_uses,
        evidence_classes=payload.evidence_classes,
        min_quality_score=payload.min_quality_score,
    )
    backend = last_retrieval_backend()
    request.state.retrieval_backend = backend
    return {
        "evidence": [item.model_dump() for item in result.evidence],
        "warnings": result.warnings,
        "backend": backend,
    }


@router.get("/admin/quality/runs")
def quality_runs(principal: AdminPrincipal = Depends(get_current_principal)) -> Dict[str, Any]:
    return {
        "quality_gate": _read_json(f"{_PROCESSED}/quality_gate_report.json"),
        "trust_calibration": _read_json(f"{_PROCESSED}/rag_trust_calibration_report.json"),
        "retrieval": _read_json(f"{_PROCESSED}/retrieval_evaluation.json"),
        "report": _read_json(f"{_PROCESSED}/evaluation_results.json"),
        "benchmark": _read_json(f"{_PROCESSED}/report_benchmark.json"),
        "metric_policy": {
            "primary_retrieval": "calibrated_query_only",
            "safety_check": "metadata_filter_safety",
            "note": "两类指标必须分开展示；均不代表 PPG 血压估算准确性验证。",
        },
    }


@router.get("/admin/metrics/summary")
def metric_summary_endpoint(
    hours: int = Query(24, ge=1, le=720),
    principal: AdminPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    return metrics_summary(db, hours=hours)


@router.get("/admin/audit-events")
def audit_events(
    action: str = "",
    limit: int = Query(100, ge=1, le=500),
    principal: AdminPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    _require(principal, "admin", "viewer", "reviewer")
    statement = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if action:
        statement = statement.where(AuditEvent.action == action)
    rows = db.scalars(statement).all()
    return {
        "events": [
            {
                "id": row.id,
                "created_at": _dt(row.created_at),
                "actor_type": row.actor_type,
                "actor_id": row.actor_id,
                "actor_name": row.actor_name,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "request_id": row.request_id,
                "reason": row.reason,
                "before_hash": row.before_hash,
                "after_hash": row.after_hash,
                "status": row.status,
                "details": json.loads(row.details_json or "{}"),
            }
            for row in rows
        ]
    }
