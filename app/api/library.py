"""REST API for literature (source) management.

This router is the integration point for a future unified back-office admin
system ("统一后台管理系统"). It exposes the same operations as the CLI over HTTP:
browse/filter the catalog, inspect the controlled vocabularies (分类/分级),
and add / update / enable / disable / remove sources. Every mutation reuses
:class:`app.services.library_manager.LibraryManager`, so validation and
knowledge-base rescreening happen exactly as they do on the command line.

Mounted at ``/api/v1/library`` (see :mod:`app.main`).
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from app.services import dedup, fulltext_admin, literature_intake

from app.services.library_manager import (
    EVIDENCE_TIERS,
    DuplicateSourceError,
    LibraryConflictError,
    LibraryError,
    LibraryManager,
    SourceNotFoundError,
)
from app.admin.db import session_scope
from app.admin.audit import redact_sensitive_text
from app.admin.job_service import create_job, job_dict
from app.admin.security import admin_auth_disabled, management_request_guard
from scripts.ingest_kb import ingest_knowledge_base

router = APIRouter(tags=["library"], dependencies=[Depends(management_request_guard)])


def _manager() -> LibraryManager:
    return LibraryManager()


def _enqueue(request: Request, job_type: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    principal = getattr(request.state, "admin_principal", None)
    requested_by = getattr(principal, "user_id", "system")
    with session_scope() as db:
        return job_dict(create_job(db, job_type, parameters or {}, requested_by))


def _if_match(
    request: Request,
    manager: LibraryManager,
    source_id: Optional[str] = None,
    *,
    trash: bool = False,
) -> None:
    expected = request.headers.get("if-match")
    if not expected:
        if not admin_auth_disabled():
            raise HTTPException(status_code=428, detail="该写操作必须提供 If-Match revision")
        return
    expected = expected.strip().strip('"')
    actual = manager.trash_revision() if trash else (manager.source_revision(source_id) if source_id else manager.writable_revision())
    if expected != actual:
        raise HTTPException(status_code=409, detail="目录已被其他操作修改，请刷新后重试")


@router.get("/admin", include_in_schema=False)
def admin_page() -> RedirectResponse:
    """Legacy entry: the literature admin is now a module in the unified shell."""

    return RedirectResponse(url="/admin/", status_code=302)


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class ScreeningScores(BaseModel):
    authority: int = 0
    recency: int = 0
    relevance: int = 0
    accessibility: int = 0
    safety_applicability: int = 0


class SourceCreate(BaseModel):
    source_id: str
    title: str
    organization: str
    year: int
    region: str
    topic: str
    evidence_class: str
    allowed_uses: List[str]
    language: str = "en"
    url: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    journal: Optional[str] = None
    journal_tier: Optional[int] = None
    source_type: Optional[str] = None
    copyright_note: Optional[str] = None
    access_note: Optional[str] = None
    screening: Optional[ScreeningScores] = None
    notes: Optional[Dict[str, Any]] = None

    def to_source(self) -> Dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        if self.screening is not None:
            data["screening"] = self.screening.model_dump()
        return data


class SourceUpdate(BaseModel):
    """Partial update; only provided fields are changed."""

    title: Optional[str] = None
    organization: Optional[str] = None
    year: Optional[int] = None
    language: Optional[str] = None
    region: Optional[str] = None
    topic: Optional[str] = None
    evidence_class: Optional[str] = None
    source_type: Optional[str] = None
    url: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    journal: Optional[str] = None
    journal_tier: Optional[int] = None
    allowed_uses: Optional[List[str]] = None
    include: Optional[bool] = None
    copyright_note: Optional[str] = None
    access_note: Optional[str] = None
    screening: Optional[ScreeningScores] = None
    notes: Optional[Dict[str, Any]] = None

    def to_patch(self) -> Dict[str, Any]:
        data = self.model_dump(exclude_none=True)
        if self.screening is not None:
            data["screening"] = self.screening.model_dump()
        return data


class IncludeUpdate(BaseModel):
    include: bool = Field(..., description="true=enable, false=disable")


class AutofillQuery(BaseModel):
    query: str = Field(..., description="DOI, article URL, or paper title")


class AutofillBatchQuery(BaseModel):
    queries: List[str] = Field(..., description="DOIs / URLs / titles, one per item")


class SourcesBatchCreate(BaseModel):
    items: List[SourceCreate]
    overwrite: bool = False


class DuplicateCheckItem(BaseModel):
    """Minimal identity of a draft to check against the catalogue."""

    title: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    pmid: Optional[str] = None
    year: Optional[int] = None


class DuplicateCheckRequest(BaseModel):
    items: List[DuplicateCheckItem]


# --------------------------------------------------------------------------- #
# Auto-fill (intake) endpoints
# --------------------------------------------------------------------------- #
@router.post("/autofill")
def autofill(payload: AutofillQuery) -> Dict[str, Any]:
    """Build a catalog draft from a DOI / URL / title (Crossref-backed).

    Factual fields are resolved; ``topic`` / ``evidence_class`` / ``allowed_uses``
    / ``screening`` are *suggestions* to confirm before adding.
    """

    try:
        return literature_intake.draft_from_query(payload.query)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _batch_drafts(queries: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for query in queries:
        try:
            out.append(literature_intake.draft_from_query(query))
        except Exception as exc:  # keep going; flag the failed one
            out.append({"_query": query, "_resolved": False, "_warning": str(exc)})
    return out


@router.post("/autofill/batch")
async def autofill_batch(payload: AutofillBatchQuery) -> Dict[str, Any]:
    """Build drafts from many DOIs/URLs/titles at once (each flagged resolved/not)."""

    queries = [q.strip() for q in payload.queries if q and q.strip()]
    if not queries:
        raise HTTPException(status_code=422, detail="empty queries")
    drafts = await run_in_threadpool(_batch_drafts, queries)
    return {"count": len(drafts), "drafts": drafts}


@router.post("/autofill/pdf")
async def autofill_pdf(request: Request) -> Dict[str, Any]:
    """Build a draft from an uploaded PDF (raw request body = PDF bytes)."""

    body = await request.body()
    if not body:
        raise HTTPException(status_code=422, detail="empty upload")
    if len(body) > fulltext_admin.MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF 超过 50 MB 限制")
    try:
        # PDF parse + Crossref lookup are blocking; run off the event loop so
        # parallel batch identifies don't serialize / freeze the server.
        return await asyncio.wait_for(
            run_in_threadpool(literature_intake.draft_from_pdf, body),
            timeout=30.0,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="PDF 识别超过 30 秒限制") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:  # pragma: no cover - malformed PDF
        raise HTTPException(status_code=422, detail=f"无法解析 PDF：{exc}")


# --------------------------------------------------------------------------- #
# Read endpoints
# --------------------------------------------------------------------------- #
@router.get("/taxonomy")
def get_taxonomy() -> Dict[str, Any]:
    """Controlled vocabularies used to organise the library (分类/分级)."""

    return _manager().taxonomy()


@router.get("/stats")
def get_stats() -> Dict[str, Any]:
    """Aggregate counts by tier / topic / evidence_class / region."""

    return _manager().stats()


@router.get("/sources")
def list_sources(
    topic: Optional[str] = None,
    tier: Optional[str] = Query(None, description="A / B / C"),
    evidence_class: Optional[str] = None,
    region: Optional[str] = None,
    include: Optional[bool] = None,
    query: Optional[str] = Query(None, description="substring match on id/title/organization/journal"),
    journal: Optional[str] = Query(None, description="substring match on journal name"),
    journal_tier: Optional[int] = Query(None, description="journal quality tier 1/2/3"),
    limit: Optional[int] = Query(None, ge=1, le=500, description="page size; omit for all"),
    offset: int = Query(0, ge=0, description="page offset"),
) -> Dict[str, Any]:
    if tier is not None and tier not in EVIDENCE_TIERS:
        raise HTTPException(status_code=422, detail=f"invalid tier: {tier}")
    if journal_tier is not None and journal_tier not in (1, 2, 3):
        raise HTTPException(status_code=422, detail=f"invalid journal_tier: {journal_tier}")
    manager = _manager()
    all_sources = manager.list_sources(
        topic=topic,
        tier=tier,
        evidence_class=evidence_class,
        region=region,
        include=include,
        query=query,
        journal=journal,
        journal_tier=journal_tier,
    )
    page = all_sources[offset : offset + limit] if limit is not None else all_sources[offset:]
    return {"total": len(all_sources), "limit": limit, "offset": offset, "count": len(page), "revision": manager.writable_revision(), "sources": page}


@router.get("/sources/{source_id}")
def get_source(source_id: str, response: Response) -> Dict[str, Any]:
    try:
        item = _manager().get_source(source_id)
        response.headers["ETag"] = f'"{item["_revision"]}"'
        return item
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# --------------------------------------------------------------------------- #
# Write endpoints
# --------------------------------------------------------------------------- #
@router.post("/sources", status_code=201)
def create_source(payload: SourceCreate, request: Request, overwrite: bool = False) -> Dict[str, Any]:
    if not admin_auth_disabled():
        raise HTTPException(
            status_code=409,
            detail="认证部署禁止直接写目录；请创建文献草稿（/api/v1/admin/library/drafts）并由 reviewer 发布",
        )
    try:
        manager = _manager()
        _if_match(request, manager)
        result = manager.add_source(payload.to_source(), overwrite=overwrite)
    except (DuplicateSourceError, LibraryConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result.as_dict()


@router.post("/sources/batch", status_code=201)
def create_sources_batch(payload: SourcesBatchCreate, request: Request) -> Dict[str, Any]:
    """Add many confirmed drafts in one pass (single rescreen), returning a
    per-item outcome (added / duplicate / error). Never aborts on one bad item."""

    if not admin_auth_disabled():
        raise HTTPException(
            status_code=409,
            detail="认证部署的批量识别结果必须逐项进入文献草稿并由 reviewer 发布",
        )
    items = [item.to_source() for item in payload.items]
    manager = _manager()
    _if_match(request, manager)
    try:
        return manager.add_sources(items, overwrite=payload.overwrite)
    except LibraryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/sources/{source_id}")
def update_source(source_id: str, payload: SourceUpdate, request: Request) -> Dict[str, Any]:
    try:
        manager = _manager()
        _if_match(request, manager, source_id)
        result = manager.update_source(source_id, payload.to_patch())
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LibraryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result.as_dict()


@router.put("/sources/{source_id}/include")
def set_include(source_id: str, payload: IncludeUpdate, request: Request) -> Dict[str, Any]:
    try:
        manager = _manager()
        _if_match(request, manager, source_id)
        result = manager.set_include(source_id, payload.include)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LibraryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result.as_dict()


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, request: Request, reason: Optional[str] = None, hard: bool = False) -> Dict[str, Any]:
    """Delete a source. Default = soft delete into the recycle bin (recoverable).

    ``hard=true`` permanently removes it from the catalog (no recovery).
    """

    try:
        manager = _manager()
        _if_match(request, manager, source_id)
        result = manager.remove_source(source_id) if hard else manager.trash_source(
            source_id, reason=redact_sensitive_text(reason)
        )
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LibraryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result.as_dict()


# --------------------------------------------------------------------------- #
# Recycle bin (回收站 / 废纸篓)
# --------------------------------------------------------------------------- #
@router.get("/trash")
def list_trash(
    limit: Optional[int] = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> Dict[str, Any]:
    items = _manager().list_trash()
    page = items[offset : offset + limit] if limit is not None else items[offset:]
    return {"total": len(items), "limit": limit, "offset": offset, "count": len(page), "sources": page}


@router.post("/sources/{source_id}/restore")
def restore_source(source_id: str, request: Request) -> Dict[str, Any]:
    try:
        manager = _manager()
        _if_match(request, manager, trash=True)
        return manager.restore_source(source_id).as_dict()
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LibraryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/trash/{source_id}")
def purge_source(source_id: str, request: Request) -> Dict[str, Any]:
    """Permanently delete one item from the recycle bin (irreversible)."""

    try:
        manager = _manager()
        _if_match(request, manager, trash=True)
        return manager.purge_source(source_id).as_dict()
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LibraryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/trash/empty")
def empty_trash(request: Request) -> Dict[str, Any]:
    manager = _manager()
    _if_match(request, manager, trash=True)
    return manager.empty_trash()


@router.post("/rescreen")
def rescreen(request: Request) -> Any:
    if not admin_auth_disabled():
        return JSONResponse(status_code=202, content={"job": _enqueue(request, "rescreen")})
    return _manager().rescreen()


# --------------------------------------------------------------------------- #
# Near-duplicate detection (advisory; never auto-deletes)
# --------------------------------------------------------------------------- #
_DUP_MEMBER_FIELDS = (
    "source_id", "title", "organization", "journal", "journal_tier",
    "year", "region", "topic", "evidence_class", "tier", "include", "doi", "url",
)


def _dup_member(source: Dict[str, Any]) -> Dict[str, Any]:
    return {k: source.get(k) for k in _DUP_MEMBER_FIELDS}


@router.get("/duplicates")
def scan_duplicates() -> Dict[str, Any]:
    """Scan the active catalogue for near-duplicate clusters (manual review).

    Match confidence: ``doi``/``pmid`` reasons are strong; ``title+year`` is a
    weak signal (distinct sources can share a generic title) — the caller must
    let a human confirm before trashing anything.
    """

    sources = _manager().list_sources()
    clusters = dedup.find_duplicate_clusters(sources)
    out = [
        {
            "reasons": c["reasons"],
            "strong": any(r in ("doi", "pmid") for r in c["reasons"]),
            "size": c["size"],
            "members": [_dup_member(m) for m in c["members"]],
        }
        for c in clusters
    ]
    return {"cluster_count": len(out), "clusters": out}


@router.post("/duplicates/check")
def check_duplicates(payload: DuplicateCheckRequest) -> Dict[str, Any]:
    """For each draft, list catalogued sources it looks like (import warning)."""

    existing = _manager().list_sources()
    existing_ids = dedup.build_identities(existing)  # normalise the catalogue once
    results = []
    for idx, item in enumerate(payload.items):
        matches = dedup.find_duplicates(item.model_dump(), existing, existing_ids=existing_ids)
        results.append({"index": idx, "matches": matches})
    return {"results": results}


# --------------------------------------------------------------------------- #
# Governed full-text management
# --------------------------------------------------------------------------- #
@router.get("/fulltext")
def fulltext_status() -> Dict[str, Any]:
    """Per-source full-text status (has_pdf / indexed / chunks / access_mode)."""

    return fulltext_admin.fulltext_status()


@router.get("/sources/{source_id}/fulltext")
def source_fulltext(source_id: str) -> Dict[str, Any]:
    try:
        return fulltext_admin.source_fulltext_status(source_id)
    except fulltext_admin.FulltextAdminError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/sources/{source_id}/fulltext")
async def attach_fulltext(
    source_id: str,
    request: Request,
    access_mode: str = Query(..., description="declared license/access mode, e.g. public_pdf"),
    allowed_uses: Optional[str] = Query(None, description="comma-separated; defaults to the source's own uses"),
    institution_required: bool = False,
    attestation: Optional[str] = Query(None, description="fixed local-governance authorization assertion"),
    rebuild: bool = True,
) -> Dict[str, Any]:
    """Attach a full-text PDF (raw request body) to a source and index it.

    The raw PDF is stored only in the git-ignored governance library; the committed
    registry keeps metadata only.
    """

    body = await request.body()
    if len(body) > fulltext_admin.MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF 超过 50 MB 限制")
    secure_mode = not admin_auth_disabled()
    if secure_mode and attestation != fulltext_admin.LICENSE_ATTESTATION_CODE:
        raise HTTPException(
            status_code=422,
            detail=f"必须使用固定授权确认码 {fulltext_admin.LICENSE_ATTESTATION_CODE}",
        )
    uses = [u.strip() for u in allowed_uses.split(",")] if allowed_uses else None
    try:
        # In authenticated deployments the request only validates and stores
        # the governed PDF. Parsing/indexing is always delegated to the worker.
        result = await asyncio.wait_for(
            run_in_threadpool(
                fulltext_admin.attach_pdf,
                source_id,
                body,
                access_mode=access_mode,
                allowed_uses=uses,
                institution_required=institution_required,
                license_attestation=fulltext_admin.LICENSE_ATTESTATION_CODE if attestation else None,
                rebuild=rebuild and not secure_mode,
            ),
            timeout=30.0 if secure_mode else 180.0,
        )
        if secure_mode and rebuild:
            job = _enqueue(request, "build_fulltext", {"source_ids": [source_id]})
            return JSONResponse(status_code=202, content={**result, "job": job})
        return result
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="PDF 治理处理超时") from exc
    except fulltext_admin.FulltextAdminError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/sources/{source_id}/fulltext")
def detach_fulltext(source_id: str, request: Request, rebuild: bool = True) -> Any:
    secure_mode = not admin_auth_disabled()
    try:
        result = fulltext_admin.remove_fulltext(source_id, rebuild=rebuild and not secure_mode)
        if secure_mode and rebuild:
            job = _enqueue(request, "build_fulltext", {"source_ids": [source_id]})
            return JSONResponse(status_code=202, content={**result, "job": job})
        return result
    except fulltext_admin.FulltextAdminError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/fulltext/rebuild")
def rebuild_fulltext(request: Request, source_id: Optional[List[str]] = Query(None)) -> Any:
    if not admin_auth_disabled():
        return JSONResponse(
            status_code=202,
            content={"job": _enqueue(request, "build_fulltext", {"source_ids": source_id or []})},
        )
    return fulltext_admin.build_fulltext(source_ids=source_id)


@router.post("/ingest")
def ingest(request: Request, build_vector: bool = False) -> Any:
    """Rebuild the retrieval chunks (``chunks.jsonl``) from the knowledge base.

    Admin-triggered: run this after adding/removing sources so the new content
    reaches retrieval. ``build_vector=true`` also rebuilds the optional Chroma
    vector index (heavier; needs optional deps).
    """

    if not admin_auth_disabled():
        job_type = "build_chroma" if build_vector else "ingest_chunks"
        return JSONResponse(status_code=202, content={"job": _enqueue(request, job_type)})
    try:
        return ingest_knowledge_base(build_vector=build_vector)
    except Exception as exc:  # pragma: no cover - surfaced to the admin UI
        raise HTTPException(status_code=500, detail=f"ingest failed: {exc}")
