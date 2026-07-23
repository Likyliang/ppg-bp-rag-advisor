from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session
import portalocker

from app.admin.audit import redact_sensitive_text
from app.admin.db import session_scope
from app.admin.models import AdminJob, JobEvent, utcnow
from app.services.config_loader import resolve_project_path


JOB_RESOURCES = {
    "rescreen": "catalog_write",
    "ingest_chunks": "kb_write",
    "build_chroma": "kb_write",
    "build_fulltext": "fulltext_index",
    "build_openai_processed": "openai_processed",
    "build_openai_fulltext": "openai_fulltext",
    "kb_audit": "kb_read",
    "quality_gate": "quality_gate",
    "retrieval_evaluation": "quality_gate",
    "report_evaluation": "quality_gate",
    "api_experiment": "quality_gate",
    "validate_config_draft": "config_validation",
    "rollback_config_revision": "config_write",
}
_UUID_RE = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}"


def _validate_job_request(job_type: str, parameters: Dict[str, Any]) -> None:
    if job_type not in JOB_RESOURCES:
        raise ValueError("unsupported job type")
    if job_type == "build_fulltext":
        source_ids = parameters.get("source_ids") or []
        if set(parameters) - {"source_ids"} or not isinstance(source_ids, list) or len(source_ids) > 100:
            raise ValueError("source_ids must be a list with at most 100 items")
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", str(source_id)) for source_id in source_ids):
            raise ValueError("invalid source_id")
        return
    if job_type == "validate_config_draft":
        if set(parameters) != {"draft_id"} or not re.fullmatch(_UUID_RE, str(parameters.get("draft_id") or "")):
            raise ValueError("invalid config draft id")
        return
    if job_type == "rollback_config_revision":
        reason = parameters.get("reason")
        if (
            set(parameters) != {"revision_id", "reason", "expected_revision"}
            or not re.fullmatch(_UUID_RE, str(parameters.get("revision_id") or ""))
            or not re.fullmatch(r"[0-9a-f]{64}", str(parameters.get("expected_revision") or ""))
            or not isinstance(reason, str)
            or not 3 <= len(reason.strip()) <= 1000
        ):
            raise ValueError("invalid config rollback request")
        return
    if parameters:
        raise ValueError("this job type accepts no parameters")


def _command_for(job_type: str, parameters: Dict[str, Any], *, job_id: Optional[str] = None) -> List[str]:
    _validate_job_request(job_type, parameters)
    python = sys.executable
    commands = {
        "rescreen": [python, "scripts/screen_sources.py"],
        "ingest_chunks": [python, "scripts/ingest_kb.py"],
        "build_chroma": [python, "scripts/ingest_kb.py", "--vector"],
        "build_fulltext": [python, "scripts/ingest_fulltext_pdfs.py"],
        "build_openai_processed": [python, "scripts/ingest_openai_embeddings.py", "--scope", "processed_chunks"],
        "build_openai_fulltext": [python, "scripts/ingest_openai_embeddings.py", "--scope", "fulltext_chunks"],
        "kb_audit": [python, "scripts/audit_kb.py"],
        "quality_gate": [python, "scripts/run_quality_gate.py", "--strict-stop"],
        "retrieval_evaluation": [python, "scripts/evaluate_retrieval.py"],
        "report_evaluation": [python, "scripts/evaluate_reports.py"],
        "api_experiment": [python, "scripts/run_api_experiments.py"],
    }
    if job_type in {"validate_config_draft", "rollback_config_revision"}:
        if not job_id or not re.fullmatch(_UUID_RE, job_id):
            raise ValueError("internal admin action requires a job id")
        return [python, "-m", "app.admin.job_actions", job_id]
    command = list(commands[job_type])
    if job_type == "build_fulltext":
        for source_id in parameters.get("source_ids") or []:
            command.extend(["--source-id", str(source_id)])
    return command


def create_job(db: Session, job_type: str, parameters: Dict[str, Any], requested_by: str) -> AdminJob:
    parameters = dict(parameters)
    if job_type == "rollback_config_revision" and "reason" in parameters:
        parameters["reason"] = redact_sensitive_text(str(parameters["reason"]))
    _validate_job_request(job_type, parameters)
    row = AdminJob(
        job_type=job_type,
        resource_lock=JOB_RESOURCES[job_type],
        params_json=json.dumps(parameters, ensure_ascii=False, sort_keys=True),
        requested_by=requested_by,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    add_job_event(db, row.id, "info", "任务已进入队列")
    return row


def add_job_event(db: Session, job_id: str, level: str, message: str) -> JobEvent:
    last = db.scalar(
        select(JobEvent.sequence).where(JobEvent.job_id == job_id).order_by(JobEvent.sequence.desc()).limit(1)
    )
    row = JobEvent(job_id=job_id, sequence=int(last or 0) + 1, level=level, message=_sanitize(message)[:4000])
    db.add(row)
    db.commit()
    return row


def _sanitize(text: str) -> str:
    value = str(text).replace(str(resolve_project_path(".")), "<project>")
    value = re.sub(r"(?i)(api[_-]?key|authorization|bearer|secret|password)(\s*[:=]\s*)\S+", r"\1\2[REDACTED]", value)
    value = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "[REDACTED]", value)
    return value


def job_dict(row: AdminJob) -> Dict[str, Any]:
    return {
        "id": row.id,
        "job_type": row.job_type,
        "resource_lock": row.resource_lock,
        "parameters": json.loads(row.params_json or "{}"),
        "status": row.status,
        "progress": row.progress,
        "requested_by": row.requested_by,
        "created_at": row.created_at.isoformat(),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "result": json.loads(row.result_json or "{}"),
        "error_code": row.error_code,
        "log_tail": row.log_tail,
        "attempt": row.attempt,
        "parent_id": row.parent_id,
    }


def _release_internal_job_state(db: Session, row: AdminJob, error_code: str) -> None:
    if row.job_type != "validate_config_draft":
        return
    from app.admin.models import ConfigDraft

    params = json.loads(row.params_json or "{}")
    draft = db.get(ConfigDraft, params.get("draft_id"))
    if draft is not None and draft.status == "validating":
        draft.status = "invalid"
        draft.validation_json = json.dumps(
            {"passed": False, "errors": ["后台校验任务未完成"], "error_code": error_code},
            ensure_ascii=False,
        )


def claim_next_job(db: Session) -> Optional[AdminJob]:
    queued = db.scalars(select(AdminJob).where(AdminJob.status == "queued").order_by(AdminJob.created_at)).all()
    for row in queued:
        running = db.scalar(
            select(AdminJob.id).where(
                AdminJob.status.in_(["running", "cancelling"]),
                AdminJob.resource_lock == row.resource_lock,
                AdminJob.id != row.id,
            ).limit(1)
        )
        if running:
            continue
        row.status = "running"
        row.progress = 5
        row.started_at = utcnow()
        db.commit()
        add_job_event(db, row.id, "info", "任务开始执行")
        return row
    return None


def run_job(row_id: str) -> Dict[str, Any]:
    with session_scope() as db:
        row = db.get(AdminJob, row_id)
        if row is None:
            raise KeyError(row_id)
        command = _command_for(row.job_type, json.loads(row.params_json or "{}"), job_id=row.id)
        env = os.environ.copy()
        if row.job_type in {"quality_gate", "retrieval_evaluation", "report_evaluation", "api_experiment"}:
            env["REPORT_MODE"] = "template_only"
            env["LLM_PROVIDER"] = "mock"
            env["RETRIEVAL_EMBEDDING_BACKEND"] = "hashing"
        process = subprocess.Popen(
            command,
            cwd=resolve_project_path("."),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            start_new_session=True,
        )
        row.process_pid = process.pid
        db.commit()
        lines: List[str] = []
        assert process.stdout is not None
        for line in process.stdout:
            safe = _sanitize(line.rstrip())
            lines.append(safe)
            if len(lines) > 200:
                lines = lines[-200:]
            if len(lines) % 20 == 0:
                row.log_tail = "\n".join(lines)[-20000:]
                row.progress = min(90, row.progress + 5)
                db.commit()
        returncode = process.wait()
        db.refresh(row)
        row.log_tail = "\n".join(lines)[-20000:]
        row.finished_at = utcnow()
        row.process_pid = None
        if row.status == "cancelling":
            row.status = "cancelled"
            row.progress = min(row.progress, 99)
            row.error_code = "user_cancelled"
            row.result_json = json.dumps({"returncode": returncode, "cancelled": True}, ensure_ascii=False)
            _release_internal_job_state(db, row, "user_cancelled")
            add_job_event(db, row.id, "warning", "运行中的任务已取消")
        elif returncode == 0:
            row.status = "succeeded"
            row.progress = 100
            row.result_json = json.dumps({"returncode": 0}, ensure_ascii=False)
            add_job_event(db, row.id, "info", "任务执行成功")
        else:
            row.status = "failed"
            row.error_code = f"exit_{returncode}"
            row.result_json = json.dumps({"returncode": returncode}, ensure_ascii=False)
            _release_internal_job_state(db, row, row.error_code)
            add_job_event(db, row.id, "error", f"任务失败（退出码 {returncode}）")
        db.commit()
        return job_dict(row)


def run_next_job() -> Optional[Dict[str, Any]]:
    with session_scope() as db:
        row = claim_next_job(db)
        row_id = row.id if row else None
    return run_job(row_id) if row_id else None


def retry_job(db: Session, row: AdminJob, requested_by: str) -> AdminJob:
    if row.status not in {"failed", "cancelled", "interrupted"}:
        raise ValueError("只有失败、取消或中断的任务可以重试")
    clone = create_job(db, row.job_type, json.loads(row.params_json or "{}"), requested_by)
    clone.attempt = row.attempt + 1
    clone.parent_id = row.id
    if clone.job_type == "validate_config_draft":
        from app.admin.models import ConfigDraft

        draft = db.get(ConfigDraft, json.loads(clone.params_json or "{}").get("draft_id"))
        if draft is not None:
            draft.status = "validating"
    db.commit()
    return clone


def cancel_job(db: Session, row: AdminJob) -> AdminJob:
    if row.status == "queued":
        row.status = "cancelled"
        row.finished_at = utcnow()
        _release_internal_job_state(db, row, "user_cancelled")
        db.commit()
        add_job_event(db, row.id, "warning", "排队任务已取消")
        return row
    if row.status == "running" and row.process_pid:
        row.status = "cancelling"
        row.error_code = "user_cancelled"
        db.commit()
        try:
            os.killpg(row.process_pid, signal.SIGTERM)
        except ProcessLookupError:
            row.status = "interrupted"
            row.finished_at = utcnow()
            row.process_pid = None
            row.error_code = "process_not_found"
            db.commit()
        add_job_event(db, row.id, "warning", "已请求取消运行中的任务")
        return row
    if row.status == "cancelling":
        return row
    raise ValueError("只有排队或运行中的任务可以取消")


def recover_interrupted_jobs() -> int:
    with session_scope() as db:
        rows = db.scalars(select(AdminJob).where(AdminJob.status.in_(["running", "cancelling"]))).all()
        for row in rows:
            if row.process_pid:
                try:
                    # Every managed child starts a new session, therefore its
                    # process-group id must equal the recorded leader pid.
                    # Terminate a surviving orphan before releasing its DB lock.
                    if os.getpgid(row.process_pid) == row.process_pid:
                        os.killpg(row.process_pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
            row.status = "interrupted"
            row.finished_at = utcnow()
            row.process_pid = None
            row.error_code = "worker_restarted"
            _release_internal_job_state(db, row, "worker_restarted")
        db.commit()
        return len(rows)


def worker_loop(poll_interval: float = 1.0) -> None:
    lock_path = resolve_project_path("var/locks/admin-worker.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # A host must run exactly one worker. This process lock prevents two local
    # workers from racing between the DB resource check and job claim.
    with portalocker.Lock(str(lock_path), timeout=0):
        recover_interrupted_jobs()
        while True:
            result = run_next_job()
            if result is None:
                time.sleep(max(0.2, poll_interval))
