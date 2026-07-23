"""Worker-only entry points for long-running admin database actions.

The public job API stores validated identifiers and governance reasons in
SQLite.  The worker passes only the opaque job UUID on the process command
line, so no free-form operator text or secret can become shell/process-list
data.
"""

from __future__ import annotations

import json
import sys
from typing import Optional

from app.admin.audit import write_audit
from app.admin.config_service import rollback_config_revision, validate_config_draft
from app.admin.db import session_scope
from app.admin.models import AdminJob, AdminUser, ConfigDraft, ConfigRevision
from app.admin.security import AdminPrincipal


def _principal(db, job: AdminJob) -> Optional[AdminPrincipal]:
    user = db.get(AdminUser, job.requested_by) if job.requested_by else None
    if user is None:
        return None
    return AdminPrincipal(user.id, user.username, user.role)


def execute(job_id: str) -> dict:
    with session_scope() as db:
        job = db.get(AdminJob, job_id)
        if job is None:
            raise RuntimeError("admin job not found")
        params = json.loads(job.params_json or "{}")
        principal = _principal(db, job)
        if job.job_type == "validate_config_draft":
            draft = db.get(ConfigDraft, params.get("draft_id"))
            if draft is None:
                raise RuntimeError("config draft not found")
            result = validate_config_draft(db, draft, run_regression=True)
            write_audit(
                db,
                principal=principal,
                action="config_draft.validation_complete",
                resource_type="config_draft",
                resource_id=draft.id,
                status="success" if result.get("passed") else "failed",
                details={"passed": bool(result.get("passed")), "error_count": len(result.get("errors") or [])},
            )
            return {"draft_id": draft.id, "status": draft.status, "passed": bool(result.get("passed"))}
        if job.job_type == "rollback_config_revision":
            revision = db.get(ConfigRevision, params.get("revision_id"))
            if revision is None:
                raise RuntimeError("config revision not found")
            result = rollback_config_revision(
                db,
                revision,
                user_id=job.requested_by or "system",
                reason=str(params.get("reason") or ""),
                expected_current_revision=str(params.get("expected_revision") or ""),
            )
            write_audit(
                db,
                principal=principal,
                action="config.rollback_complete",
                resource_type="config",
                resource_id=revision.config_key,
                reason=str(params.get("reason") or ""),
                after=result,
            )
            return result
        raise RuntimeError("unsupported internal admin job")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m app.admin.job_actions <job-id>")
    print(json.dumps(execute(sys.argv[1]), ensure_ascii=False))


if __name__ == "__main__":
    main()
