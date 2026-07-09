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

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.services import fulltext_admin, literature_intake

from app.services.library_manager import (
    EVIDENCE_TIERS,
    DuplicateSourceError,
    LibraryError,
    LibraryManager,
    SourceNotFoundError,
)
from scripts.ingest_kb import ingest_knowledge_base

router = APIRouter(tags=["library"])


def _manager() -> LibraryManager:
    return LibraryManager()


@router.get("/admin", include_in_schema=False)
def admin_page() -> RedirectResponse:
    """Legacy entry: the literature admin is now a module in the unified shell."""

    return RedirectResponse(url="/api/v1/admin", status_code=302)


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
    try:
        # PDF parse + Crossref lookup are blocking; run off the event loop so
        # parallel batch identifies don't serialize / freeze the server.
        return await run_in_threadpool(literature_intake.draft_from_pdf, body)
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
    all_sources = _manager().list_sources(
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
    return {"total": len(all_sources), "limit": limit, "offset": offset, "count": len(page), "sources": page}


@router.get("/sources/{source_id}")
def get_source(source_id: str) -> Dict[str, Any]:
    try:
        return _manager().get_source(source_id)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# --------------------------------------------------------------------------- #
# Write endpoints
# --------------------------------------------------------------------------- #
@router.post("/sources", status_code=201)
def create_source(payload: SourceCreate, overwrite: bool = False) -> Dict[str, Any]:
    try:
        result = _manager().add_source(payload.to_source(), overwrite=overwrite)
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result.as_dict()


@router.post("/sources/batch", status_code=201)
def create_sources_batch(payload: SourcesBatchCreate) -> Dict[str, Any]:
    """Add many confirmed drafts in one pass (single rescreen), returning a
    per-item outcome (added / duplicate / error). Never aborts on one bad item."""

    items = [item.to_source() for item in payload.items]
    return _manager().add_sources(items, overwrite=payload.overwrite)


@router.patch("/sources/{source_id}")
def update_source(source_id: str, payload: SourceUpdate) -> Dict[str, Any]:
    try:
        result = _manager().update_source(source_id, payload.to_patch())
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DuplicateSourceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result.as_dict()


@router.put("/sources/{source_id}/include")
def set_include(source_id: str, payload: IncludeUpdate) -> Dict[str, Any]:
    try:
        result = _manager().set_include(source_id, payload.include)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result.as_dict()


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, reason: Optional[str] = None, hard: bool = False) -> Dict[str, Any]:
    """Delete a source. Default = soft delete into the recycle bin (recoverable).

    ``hard=true`` permanently removes it from the catalog (no recovery).
    """

    try:
        manager = _manager()
        result = manager.remove_source(source_id) if hard else manager.trash_source(source_id, reason=reason)
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
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
def restore_source(source_id: str) -> Dict[str, Any]:
    try:
        return _manager().restore_source(source_id).as_dict()
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/trash/{source_id}")
def purge_source(source_id: str) -> Dict[str, Any]:
    """Permanently delete one item from the recycle bin (irreversible)."""

    try:
        return _manager().purge_source(source_id).as_dict()
    except SourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/trash/empty")
def empty_trash() -> Dict[str, Any]:
    return _manager().empty_trash()


@router.post("/rescreen")
def rescreen() -> Dict[str, str]:
    return _manager().rescreen()


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
    attestation: Optional[str] = Query(None, description="admin license attestation note"),
    rebuild: bool = True,
) -> Dict[str, Any]:
    """Attach a full-text PDF (raw request body) to a source and index it.

    The raw PDF is stored only in the git-ignored downloads dir; the committed
    registry keeps metadata only.
    """

    body = await request.body()
    uses = [u.strip() for u in allowed_uses.split(",")] if allowed_uses else None
    try:
        # Run the blocking PDF extract + index splice off the event loop so the
        # upload never freezes the rest of the UI.
        return await run_in_threadpool(
            fulltext_admin.attach_pdf,
            source_id,
            body,
            access_mode=access_mode,
            allowed_uses=uses,
            institution_required=institution_required,
            license_attestation=attestation,
            rebuild=rebuild,
        )
    except fulltext_admin.FulltextAdminError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete("/sources/{source_id}/fulltext")
def detach_fulltext(source_id: str, rebuild: bool = True) -> Dict[str, Any]:
    try:
        return fulltext_admin.remove_fulltext(source_id, rebuild=rebuild)
    except fulltext_admin.FulltextAdminError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/fulltext/rebuild")
def rebuild_fulltext(source_id: Optional[List[str]] = Query(None)) -> Dict[str, Any]:
    return fulltext_admin.build_fulltext(source_ids=source_id)


@router.post("/ingest")
def ingest(build_vector: bool = False) -> Dict[str, Any]:
    """Rebuild the retrieval chunks (``chunks.jsonl``) from the knowledge base.

    Admin-triggered: run this after adding/removing sources so the new content
    reaches retrieval. ``build_vector=true`` also rebuilds the optional Chroma
    vector index (heavier; needs optional deps).
    """

    try:
        return ingest_knowledge_base(build_vector=build_vector)
    except Exception as exc:  # pragma: no cover - surfaced to the admin UI
        raise HTTPException(status_code=500, detail=f"ingest failed: {exc}")
