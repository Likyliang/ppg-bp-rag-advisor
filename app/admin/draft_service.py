from __future__ import annotations

import json
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import LiteratureDraft, utcnow
from app.services import dedup
from app.services.library_manager import LibraryError, LibraryManager, _normalise_input
from app.services.source_catalog import validate_source


class LiteratureDraftConflictError(ValueError):
    pass


def draft_dict(row: LiteratureDraft) -> Dict[str, Any]:
    return {
        "id": row.id,
        "status": row.status,
        "source": json.loads(row.source_json),
        "validation": json.loads(row.validation_json or "{}"),
        "duplicates": json.loads(row.duplicates_json or "[]"),
        "base_catalog_revision": row.base_catalog_revision,
        "created_by": row.created_by,
        "reviewed_by": row.reviewed_by,
        "review_note": row.review_note,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "published_at": row.published_at.isoformat() if row.published_at else None,
    }


def create_literature_draft(db: Session, source: Dict[str, Any], user_id: str) -> LiteratureDraft:
    normalized = _normalise_input(source)
    row = LiteratureDraft(source_json=json.dumps(normalized, ensure_ascii=False, default=str), created_by=user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_literature_draft(db: Session, row: LiteratureDraft, source: Dict[str, Any]) -> LiteratureDraft:
    if row.status == "published":
        raise ValueError("已发布草稿不可修改")
    row.source_json = json.dumps(_normalise_input(source), ensure_ascii=False, default=str)
    row.status = "draft"
    row.validation_json = "{}"
    row.duplicates_json = "[]"
    row.base_catalog_revision = None
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def validate_literature_draft(db: Session, row: LiteratureDraft, manager: LibraryManager) -> Dict[str, Any]:
    source = _normalise_input(json.loads(row.source_json))
    issues = validate_source(source)
    errors = [item.message for item in issues if item.severity == "error"]
    warnings = [item.message for item in issues if item.severity == "warning"]
    existing = manager.list_sources()
    duplicates = dedup.find_duplicates(source, existing, ignore_id=source.get("source_id"))
    if manager.exists(str(source.get("source_id") or "")):
        errors.append(f"source_id 已存在: {source.get('source_id')}")
    result = {"passed": not errors and not duplicates, "errors": errors, "warnings": warnings}
    row.source_json = json.dumps(source, ensure_ascii=False, default=str)
    row.validation_json = json.dumps(result, ensure_ascii=False)
    row.duplicates_json = json.dumps(duplicates, ensure_ascii=False)
    row.base_catalog_revision = manager.writable_revision()
    row.status = "validated" if result["passed"] else "invalid"
    row.updated_at = utcnow()
    db.commit()
    return {**result, "duplicates": duplicates}


def publish_literature_draft(
    db: Session, row: LiteratureDraft, manager: LibraryManager, reviewer_id: str
) -> Dict[str, Any]:
    if row.status != "validated":
        raise ValueError("草稿尚未通过校验")
    if not row.base_catalog_revision or row.base_catalog_revision != manager.writable_revision():
        raise LiteratureDraftConflictError("文献目录已变化，请重新校验草稿后再发布")
    source = json.loads(row.source_json)
    try:
        result = manager.add_source(source)
    except LibraryError:
        raise
    row.status = "published"
    row.reviewed_by = reviewer_id
    row.review_note = None
    row.reviewed_at = utcnow()
    row.published_at = utcnow()
    row.updated_at = utcnow()
    db.commit()
    return result.as_dict()


def reject_literature_draft(
    db: Session, row: LiteratureDraft, reviewer_id: str, reason: str
) -> LiteratureDraft:
    if row.status == "published":
        raise ValueError("已发布草稿不可驳回")
    reason = reason.strip()
    if len(reason) < 3:
        raise ValueError("驳回原因至少 3 个字符")
    row.status = "rejected"
    row.reviewed_by = reviewer_id
    row.review_note = reason
    row.reviewed_at = utcnow()
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def list_literature_drafts(db: Session, status: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    statement = select(LiteratureDraft).order_by(LiteratureDraft.updated_at.desc()).limit(limit)
    if status:
        statement = statement.where(LiteratureDraft.status == status)
    return [draft_dict(row) for row in db.scalars(statement).all()]
