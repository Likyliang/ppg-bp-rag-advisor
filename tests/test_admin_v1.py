from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.admin import config_service, freshness
from app.admin.config_service import ConfigConflictError
from app.admin.db import get_engine, init_admin_db, reset_admin_engine_for_tests, session_scope
from app.admin.draft_service import (
    LiteratureDraftConflictError,
    create_literature_draft,
    publish_literature_draft,
    reject_literature_draft,
    validate_literature_draft,
)
from app.admin.integration_service import runtime_integration
from app.admin.job_service import (
    _progress_marker_value,
    _sanitize,
    cancel_job,
    create_job,
    recover_interrupted_jobs,
    retry_job,
)
from app.admin.models import AdminUser, ApiClient, ApiMetric, AuditEvent, ConfigRevision, IntegrationProfile
from app.admin.metrics import record_metric
from app.admin import security
from app.admin.security import ADMIN_CSRF_COOKIE, hash_password
from app.main import app
from app.services.config_loader import development_override, load_openai_embedding_config
from app.services import retriever as retriever_service
from app.services.library_manager import LibraryManager


@pytest.fixture()
def secure_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_DATABASE_URL", f"sqlite:///{tmp_path / 'admin.db'}")
    monkeypatch.setenv("ADMIN_AUTH_DISABLED", "0")
    monkeypatch.setenv("REQUIRE_API_CLIENT", "0")
    monkeypatch.setenv("ADMIN_SECRET_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    reset_admin_engine_for_tests()
    security._LOGIN_ATTEMPTS.clear()
    security._CLIENT_REQUESTS.clear()
    init_admin_db()
    with session_scope() as db:
        db.add(AdminUser(username="rootadmin", password_hash=hash_password("very-secure-pass-123"), role="admin"))
        db.add(AdminUser(username="curator1", password_hash=hash_password("very-secure-pass-456"), role="curator"))
        db.add(AdminUser(username="reviewer1", password_hash=hash_password("very-secure-pass-789"), role="reviewer"))
    with TestClient(app) as client:
        yield client
    reset_admin_engine_for_tests()
    security._LOGIN_ATTEMPTS.clear()
    security._CLIENT_REQUESTS.clear()


def _login(client: TestClient, username="rootadmin", password="very-secure-pass-123") -> dict:
    response = client.post("/api/v1/admin/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    csrf = client.cookies.get(ADMIN_CSRF_COOKIE)
    assert csrf
    return {"x-csrf-token": csrf}


def test_admin_auth_csrf_and_rbac(secure_client):
    assert secure_client.get("/api/v1/admin/overview").status_code == 401
    headers = _login(secure_client)
    assert secure_client.get("/api/v1/admin/auth/me").json()["role"] == "admin"

    body = {"username": "viewer1", "password": "another-secure-pass-123", "role": "viewer"}
    assert secure_client.post("/api/v1/admin/users", json=body).status_code == 403
    created = secure_client.post("/api/v1/admin/users", json=body, headers=headers)
    assert created.status_code == 201 and created.json()["role"] == "viewer"
    me = secure_client.get("/api/v1/admin/auth/me").json()
    assert secure_client.patch(
        f"/api/v1/admin/users/{me['id']}", json={"role": "viewer"}, headers=headers
    ).status_code == 422

    secure_client.post("/api/v1/admin/auth/logout", headers=headers)
    curator_headers = _login(secure_client, "curator1", "very-secure-pass-456")
    assert secure_client.get("/api/v1/admin/users").status_code == 403
    assert secure_client.post(
        "/api/v1/admin/configs/settings/drafts",
        json={"content": {"unsafe": True}},
        headers=curator_headers,
    ).status_code == 403


def test_auth_bypass_is_forbidden_in_internal_and_production(monkeypatch):
    monkeypatch.setenv("ADMIN_AUTH_DISABLED", "1")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError):
        security.validate_security_startup()
    monkeypatch.setenv("APP_ENV", "internal")
    with pytest.raises(RuntimeError):
        security.validate_security_startup()


def test_governed_deployment_ignores_algorithm_env_overrides(monkeypatch):
    monkeypatch.setenv("APP_ENV", "internal")
    monkeypatch.setenv("REPORT_MODE", "llm_only")
    monkeypatch.setenv("RETRIEVAL_EMBEDDING_BACKEND", "openai")
    assert development_override("REPORT_MODE") == ""
    assert development_override("RETRIEVAL_EMBEDDING_BACKEND") == ""


def test_request_id_cannot_persist_free_form_health_text(secure_client):
    response = secure_client.get(
        "/api/v1/health", headers={"x-request-id": "patient-bp-185-122-secret"}
    )
    request_id = response.headers["x-request-id"]
    assert request_id != "patient-bp-185-122-secret"
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    headers = _login(secure_client)
    secure_client.get("/api/v1/admin/overview", headers=headers)
    with session_scope() as db:
        rows = db.scalars(select(ApiMetric)).all()
        assert rows and all(not hasattr(row, "request_id") and not hasattr(row, "client_id") for row in rows)


def test_early_metric_schema_is_privacy_migrated(tmp_path, monkeypatch):
    path = tmp_path / "legacy-admin.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE api_metrics (
            id VARCHAR(36) PRIMARY KEY, created_at DATETIME NOT NULL,
            route_name VARCHAR(120) NOT NULL, method VARCHAR(12) NOT NULL,
            status_code INTEGER NOT NULL, latency_ms FLOAT NOT NULL,
            request_id VARCHAR(64) NOT NULL, client_id VARCHAR(36),
            generation_mode VARCHAR(120), retrieval_backend VARCHAR(60),
            safety_fallback BOOLEAN NOT NULL
        );
        INSERT INTO api_metrics VALUES
            ('legacy', '2026-07-10', 'report', 'POST', 200, 1.0,
             'private-request-id', 'private-client-id', NULL, NULL, 0);
        """
    )
    connection.commit()
    connection.close()
    monkeypatch.setenv("ADMIN_DATABASE_URL", f"sqlite:///{path}")
    reset_admin_engine_for_tests()
    init_admin_db()
    columns = {item["name"] for item in inspect(get_engine()).get_columns("api_metrics")}
    assert "request_id" not in columns and "client_id" not in columns
    with session_scope() as db:
        record_metric(db, route_name="report", method="POST", status_code=200, latency_ms=2.0)
        assert len(db.scalars(select(ApiMetric)).all()) == 2
    reset_admin_engine_for_tests()


def test_api_client_key_is_one_time_and_enforced(secure_client, monkeypatch):
    headers = _login(secure_client)
    created = secure_client.post(
        "/api/v1/admin/api-clients",
        json={"name": "miniapp-test", "scopes": ["reports:write"], "rate_limit_per_minute": 10},
        headers=headers,
    )
    assert created.status_code == 201
    raw_key = created.json()["api_key"]
    listing = secure_client.get("/api/v1/admin/api-clients").json()["api_clients"]
    assert "api_key" not in listing[0]
    with session_scope() as db:
        row = db.scalar(select(ApiClient).where(ApiClient.name == "miniapp-test"))
        assert row and raw_key not in row.key_hash

    monkeypatch.setenv("REQUIRE_API_CLIENT", "1")
    payload = {"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86}
    assert secure_client.post("/api/v1/reports/generate", json=payload).status_code == 401
    assert secure_client.post(
        "/api/v1/reports/generate", json=payload, headers={"x-api-key": raw_key}
    ).status_code == 200
    assert secure_client.post(
        "/api/v1/advisor/sessions", json=payload, headers={"x-api-key": raw_key}
    ).status_code == 403


def test_expired_api_client_and_login_rate_limit(secure_client, monkeypatch):
    headers = _login(secure_client)
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    created = secure_client.post(
        "/api/v1/admin/api-clients",
        json={"name": "expired-client", "scopes": ["reports:write"], "expires_at": expired},
        headers=headers,
    )
    key = created.json()["api_key"]
    monkeypatch.setenv("REQUIRE_API_CLIENT", "1")
    payload = {"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86}
    assert secure_client.post("/api/v1/reports/generate", json=payload, headers={"x-api-key": key}).status_code == 401

    secure_client.post("/api/v1/admin/auth/logout", headers=headers)
    for _ in range(5):
        assert secure_client.post(
            "/api/v1/admin/auth/login", json={"username": "rootadmin", "password": "wrong-password"}
        ).status_code == 401
    assert secure_client.post(
        "/api/v1/admin/auth/login", json={"username": "rootadmin", "password": "wrong-password"}
    ).status_code == 429
    security._LOGIN_ATTEMPTS.clear()


def test_api_client_rate_limit_and_revocation(secure_client, monkeypatch):
    headers = _login(secure_client)
    created = secure_client.post(
        "/api/v1/admin/api-clients",
        json={"name": "limited-client", "scopes": ["kb:search"], "rate_limit_per_minute": 1},
        headers=headers,
    )
    client_id, raw_key = created.json()["id"], created.json()["api_key"]
    monkeypatch.setenv("REQUIRE_API_CLIENT", "1")
    request = {"queries": ["家庭血压复核"], "top_k": 1}
    assert secure_client.post(
        "/api/v1/kb/search", json=request, headers={"x-api-key": raw_key}
    ).status_code == 200
    assert secure_client.post(
        "/api/v1/kb/search", json=request, headers={"x-api-key": raw_key}
    ).status_code == 429
    assert secure_client.post(
        f"/api/v1/admin/api-clients/{client_id}/revoke", headers=headers
    ).status_code == 200
    assert secure_client.post(
        "/api/v1/kb/search", json=request, headers={"x-api-key": raw_key}
    ).status_code == 401


def test_provider_secret_encrypted_never_returned_or_audited(secure_client):
    headers = _login(secure_client)
    profile = {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "text-embedding-3-small",
        "timeout_sec": 30,
        "max_concurrency": 2,
        "enabled": True,
        "settings": {"dimensions": 1536, "batch_size": 32},
    }
    assert secure_client.put("/api/v1/admin/integrations/embedding", json=profile, headers=headers).status_code == 200
    secret = "sk-test-never-return-this-value"
    response = secure_client.put(
        "/api/v1/admin/integrations/embedding/secret", json={"secret": secret}, headers=headers
    )
    assert response.status_code == 200
    assert secret not in response.text and "secret_ciphertext" not in response.text
    assert response.json()["secret_configured"] is True
    runtime_config = load_openai_embedding_config()
    assert runtime_config.timeout_sec == 30
    assert runtime_config.max_concurrency == 2
    with session_scope() as db:
        row = db.get(IntegrationProfile, "embedding")
        assert row and row.secret_ciphertext and secret not in row.secret_ciphertext
        audit_blob = "\n".join(item.details_json for item in db.scalars(select(AuditEvent)).all())
        assert secret not in audit_blob
    assert runtime_integration("embedding")["secret"] == secret
    plaintext_attempt = {**profile, "settings": {"api_key": "must-not-be-stored"}}
    rejected = secure_client.put(
        "/api/v1/admin/integrations/embedding", json=plaintext_attempt, headers=headers
    )
    assert rejected.status_code == 422 and "must-not-be-stored" not in rejected.text
    report_profile = {
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "timeout_sec": 30,
        "max_concurrency": 1,
        "enabled": False,
        "settings": {"max_tokens": 2400, "temperature": 0.4, "min_interval_sec": 0},
    }
    accepted = secure_client.put(
        "/api/v1/admin/integrations/report_llm", json=report_profile, headers=headers
    )
    assert accepted.status_code == 200
    credential_setting = {
        **report_profile,
        "settings": {"access_token": "must-not-be-stored"},
    }
    rejected = secure_client.put(
        "/api/v1/admin/integrations/report_llm", json=credential_setting, headers=headers
    )
    assert rejected.status_code == 422 and "must-not-be-stored" not in rejected.text


def test_validation_errors_do_not_echo_credential_inputs(secure_client):
    headers = _login(secure_client)
    short_secret = "leakme7"
    response = secure_client.put(
        "/api/v1/admin/integrations/embedding/secret",
        json={"secret": short_secret},
        headers=headers,
    )
    assert response.status_code == 422
    assert short_secret not in response.text
    assert response.json()["detail"][0]["input"] == "[REDACTED]"


def test_missing_or_rotated_master_key_fails_closed(secure_client, monkeypatch):
    headers = _login(secure_client)
    profile = {
        "provider": "openai", "base_url": "https://api.openai.com/v1",
        "model": "text-embedding-3-small", "enabled": True,
        "timeout_sec": 10, "max_concurrency": 1, "settings": {"dimensions": 1536},
    }
    secure_client.put("/api/v1/admin/integrations/embedding", json=profile, headers=headers)
    secret = "sk-test-rotation-never-leak"
    assert secure_client.put(
        "/api/v1/admin/integrations/embedding/secret", json={"secret": secret}, headers=headers
    ).status_code == 200
    monkeypatch.setenv("ADMIN_SECRET_MASTER_KEY", "")
    response = secure_client.put(
        "/api/v1/admin/integrations/embedding/secret", json={"secret": "replacement-secret"}, headers=headers
    )
    assert response.status_code == 422 and secret not in response.text
    monkeypatch.setenv("ADMIN_SECRET_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    degraded = runtime_integration("embedding")
    assert degraded and degraded.get("secret_error") is True and degraded.get("secret") == ""
    monkeypatch.setenv("OPENAI_EMBEDDING_API_KEY", "old-env-secret-must-not-revive")
    assert load_openai_embedding_config().api_key == ""


def test_evaluation_channel_never_reuses_report_key(secure_client, monkeypatch):
    import scripts.relevance_judge as relevance_judge

    for name in ("EVAL_LLM_API_KEY", "EVAL_LLM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "report-key-must-not-become-judge-key")
    with pytest.raises(relevance_judge.RelevanceJudgeError):
        relevance_judge._resolve_provider()


def _valid_settings(top_k: int) -> dict:
    return {
        "generation": {"report_mode": "template_only"},
        "retrieval": {"top_k": top_k, "keyword_weight": 0.6, "vector_weight": 0.4, "per_source_cap": 2},
        "safety": {
            "require_ppg_limitation": True,
            "require_disclaimer": True,
            "block_diagnosis": True,
            "block_medication_changes": True,
        },
    }


def test_governance_reason_redacts_accidental_credentials(secure_client):
    headers = _login(secure_client)
    secret = "sk-accidental-secret-value"
    response = secure_client.post(
        "/api/v1/admin/configs/settings/drafts",
        json={"content": _valid_settings(5), "reason": f"api_key={secret}"},
        headers=headers,
    )
    assert response.status_code == 201
    assert secret not in response.text
    assert response.json()["reason"] == "[REDACTED]"
    unsafe_content = {**_valid_settings(5), "api_key": secret}
    rejected = secure_client.post(
        "/api/v1/admin/configs/settings/drafts",
        json={"content": unsafe_content, "reason": "must reject plaintext credentials"},
        headers=headers,
    )
    assert rejected.status_code == 422
    assert secret not in rejected.text


def test_config_draft_atomic_publish_conflict_and_rollback(secure_client, tmp_path, monkeypatch):
    path = tmp_path / "settings.yaml"
    path.write_text(config_service._dump(_valid_settings(5)), encoding="utf-8")
    monkeypatch.setitem(config_service.CONFIG_SPECS["settings"], "path", str(path))
    with session_scope() as db:
        draft = config_service.create_config_draft(db, "settings", _valid_settings(7), "admin", "test")
        validation = config_service.validate_config_draft(db, draft, run_regression=False)
        assert validation["passed"] is True and draft.status == "validated"
        result = config_service.publish_config_draft(
            db,
            draft,
            user_id="admin",
            reason="approved test",
            expected_revision=draft.base_revision,
            confirmation="settings",
        )
        assert result["revision"] != result["previous_revision"]
        assert "top_k: 7" in path.read_text(encoding="utf-8")

        second = config_service.create_config_draft(db, "settings", _valid_settings(9), "admin")
        config_service.validate_config_draft(db, second, run_regression=False)
        path.write_text(config_service._dump(_valid_settings(8)), encoding="utf-8")
        with pytest.raises(ConfigConflictError):
            config_service.publish_config_draft(
                db,
                second,
                user_id="admin",
                reason="stale",
                expected_revision=second.base_revision,
                confirmation="settings",
            )

        baseline = db.scalar(
            select(ConfigRevision).where(
                ConfigRevision.config_key == "settings",
                ConfigRevision.revision == result["previous_revision"],
            )
        )
        assert baseline is not None
        config_service.rollback_config_revision(db, baseline, user_id="admin", reason="restore")
        assert "top_k: 5" in path.read_text(encoding="utf-8")


def test_config_safety_invariants_and_if_match(secure_client, tmp_path, monkeypatch):
    invalid = _valid_settings(5)
    invalid["safety"]["block_diagnosis"] = False
    assert any("不能关闭" in item for item in config_service._structural_validation("settings", invalid))

    path = tmp_path / "settings-if-match.yaml"
    path.write_text(config_service._dump(_valid_settings(5)), encoding="utf-8")
    monkeypatch.setitem(config_service.CONFIG_SPECS["settings"], "path", str(path))
    with session_scope() as db:
        draft = config_service.create_config_draft(db, "settings", _valid_settings(6), "admin")
        config_service.validate_config_draft(db, draft, run_regression=False)
        draft_id, revision = draft.id, draft.base_revision
    headers = _login(secure_client)
    headers["If-Match"] = "0" * 64
    response = secure_client.post(
        f"/api/v1/admin/config-drafts/{draft_id}/publish",
        json={"reason": "stale request", "expected_revision": revision, "confirmation": "settings"},
        headers=headers,
    )
    assert response.status_code == 409


def test_config_validation_and_rollback_are_worker_jobs(secure_client, tmp_path, monkeypatch):
    path = tmp_path / "settings-worker.yaml"
    path.write_text(config_service._dump(_valid_settings(5)), encoding="utf-8")
    monkeypatch.setitem(config_service.CONFIG_SPECS["settings"], "path", str(path))
    headers = _login(secure_client)
    created = secure_client.post(
        "/api/v1/admin/configs/settings/drafts",
        json={"content": _valid_settings(6), "reason": "worker validation"},
        headers=headers,
    )
    assert created.status_code == 201
    queued = secure_client.post(
        f"/api/v1/admin/config-drafts/{created.json()['id']}/validate", headers=headers
    )
    assert queued.status_code == 202
    assert queued.json()["job"]["job_type"] == "validate_config_draft"
    assert queued.json()["draft"]["status"] == "validating"

    with session_scope() as db:
        revision = ConfigRevision(
            config_key="settings",
            revision=config_service.current_revision("settings"),
            content_text=path.read_text(encoding="utf-8"),
            published_by="admin",
            reason="baseline",
            validation_json="{}",
        )
        db.add(revision)
        db.commit()
        revision_id = revision.id
    rollback = secure_client.post(
        f"/api/v1/admin/config-revisions/{revision_id}/rollback",
        json={"reason": "restore governed baseline"},
        headers={**headers, "If-Match": config_service.current_revision("settings")},
    )
    assert rollback.status_code == 202
    assert rollback.json()["job"]["job_type"] == "rollback_config_revision"


def test_high_risk_config_rejects_regex_threshold_conflicts_and_runs_strict_gate(monkeypatch):
    safety = yaml.safe_load(Path("config/safety_terms.yaml").read_text(encoding="utf-8"))
    safety["diagnostic_patterns"] = ["("]
    assert any("正则无效" in item for item in config_service._structural_validation("safety_terms", safety))

    thresholds = yaml.safe_load(Path("config/bp_thresholds.yaml").read_text(encoding="utf-8"))
    thresholds["AHA"]["stage_2_reference_range"]["sbp_gte"] = 100
    assert any("顺序冲突" in item for item in config_service._structural_validation("bp_thresholds", thresholds))

    valid = yaml.safe_load(Path("config/safety_terms.yaml").read_text(encoding="utf-8"))
    called = []

    class Completed:
        returncode = 0
        stdout = "targeted regression passed"

    monkeypatch.setattr(config_service.subprocess, "run", lambda *args, **kwargs: Completed())
    monkeypatch.setattr(
        config_service,
        "_fixed_case_preview",
        lambda _env: {"passed": True, "cases": [{"case_id": "synthetic"}]},
    )
    monkeypatch.setattr(
        config_service,
        "_isolated_strict_quality_gate",
        lambda _env: called.append(True) or {"passed": True, "returncode": 0},
    )
    result = config_service._regression_gate("safety_terms", valid)
    assert result["passed"] is True and called == [True]


def test_high_risk_config_rollback_cannot_bypass_regression(secure_client, tmp_path, monkeypatch):
    path = tmp_path / "safety_terms.yaml"
    content = yaml.safe_load(Path("config/safety_terms.yaml").read_text(encoding="utf-8"))
    path.write_text(config_service._dump(content), encoding="utf-8")
    monkeypatch.setitem(config_service.CONFIG_SPECS["safety_terms"], "path", str(path))
    monkeypatch.setattr(config_service, "_regression_gate", lambda *_args: {"passed": False})
    with session_scope() as db:
        revision = ConfigRevision(
            config_key="safety_terms",
            revision=config_service._sha256(config_service._dump(content)),
            content_text=config_service._dump(content),
            published_by="admin",
            reason="old safe-looking revision",
            validation_json="{}",
        )
        db.add(revision)
        db.commit()
        with pytest.raises(config_service.ConfigValidationError):
            config_service.rollback_config_revision(db, revision, user_id="admin", reason="must revalidate")


def test_high_risk_config_publish_rejects_skipped_regression(secure_client, tmp_path, monkeypatch):
    path = tmp_path / "safety_terms-publish.yaml"
    content = yaml.safe_load(Path("config/safety_terms.yaml").read_text(encoding="utf-8"))
    path.write_text(config_service._dump(content), encoding="utf-8")
    monkeypatch.setitem(config_service.CONFIG_SPECS["safety_terms"], "path", str(path))
    with session_scope() as db:
        draft = config_service.create_config_draft(db, "safety_terms", content, "admin")
        assert config_service.validate_config_draft(db, draft, run_regression=False)["passed"] is True
        with pytest.raises(config_service.ConfigValidationError):
            config_service.publish_config_draft(
                db,
                draft,
                user_id="admin",
                reason="must not skip regression",
                expected_revision=draft.base_revision,
                confirmation="safety_terms",
            )


def _draft_source() -> dict:
    return {
        "source_id": "admin_draft_source",
        "title": "Governed blood pressure review",
        "organization": "Example University",
        "url": "https://example.org/paper",
        "year": 2026,
        "language": "en",
        "region": "global",
        "topic": "research_context",
        "evidence_class": "research_context",
        "source_type": "review",
        "include": True,
        "allowed_uses": ["research_background"],
        "screening": {"authority": 4, "recency": 4, "relevance": 4, "accessibility": 4, "safety_applicability": 4},
    }


def test_literature_draft_validate_publish(tmp_path, secure_client):
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text("catalog_version: 1\nsources: []\n", encoding="utf-8")
    manager = LibraryManager(
        catalog_files=[str(catalog)],
        writable_catalog=str(catalog),
        trash_catalog=str(tmp_path / "trash.yaml"),
        auto_rescreen=False,
        manage_fulltext=False,
    )
    with session_scope() as db:
        row = create_literature_draft(db, _draft_source(), "curator")
        result = validate_literature_draft(db, row, manager)
        assert result["passed"] is True and row.status == "validated"
        stale = create_literature_draft(db, {**_draft_source(), "source_id": "stale-source", "url": "https://example.org/stale"}, "curator")
        assert validate_literature_draft(db, stale, manager)["passed"] is True
        published = publish_literature_draft(db, row, manager, "reviewer")
        assert published["action"] == "added" and manager.exists("admin_draft_source")
        with pytest.raises(LiteratureDraftConflictError):
            publish_literature_draft(db, stale, manager, "reviewer")

        rejected = create_literature_draft(db, {**_draft_source(), "source_id": "rejected-source"}, "curator")
        reject_literature_draft(db, rejected, "reviewer", "evidence scope is unsuitable")
        assert rejected.status == "rejected" and rejected.review_note


def test_literature_draft_rejects_credential_metadata(secure_client):
    headers = _login(secure_client, "curator1", "very-secure-pass-456")
    source = {**_draft_source(), "notes": {"api_key": "must-never-enter-catalog"}}
    response = secure_client.post(
        "/api/v1/admin/library/drafts", json={"source": source}, headers=headers
    )
    assert response.status_code == 422
    assert "must-never-enter-catalog" not in response.text


def test_job_allowlist_cancel_retry_recovery_and_redaction(secure_client, monkeypatch):
    with session_scope() as db:
        with pytest.raises(ValueError):
            create_job(db, "quality_gate", {"argv": ["; rm -rf /"]}, "admin")
        with pytest.raises(ValueError):
            create_job(db, "validate_config_draft", {"draft_id": "; rm -rf /"}, "admin")
        row = create_job(db, "kb_audit", {}, "admin")
        cancel_job(db, row)
        clone = retry_job(db, row, "admin")
        assert clone.status == "queued" and clone.parent_id == row.id and clone.attempt == 2
        running = create_job(db, "kb_audit", {}, "admin")
        running.status = "running"
        running.process_pid = 43210
        db.commit()
        killed = []
        monkeypatch.setattr("app.admin.job_service.os.killpg", lambda pid, sig: killed.append((pid, sig)))
        cancel_job(db, running)
        assert running.status == "cancelling" and killed[0][0] == 43210
    assert recover_interrupted_jobs() == 1
    assert "super-secret" not in _sanitize("api_key=super-secret")


def test_worker_progress_marker_is_strict_and_reserves_terminal_progress():
    assert _progress_marker_value("__ADMIN_JOB_PROGRESS__=42") == 42
    assert _progress_marker_value("__ADMIN_JOB_PROGRESS__=100") == 95
    assert _progress_marker_value("__ADMIN_JOB_PROGRESS__=101") is None
    assert _progress_marker_value("prefix __ADMIN_JOB_PROGRESS__=42") is None
    assert _progress_marker_value("__ADMIN_JOB_PROGRESS__=42 extra") is None


def test_progress_markers_are_silent_outside_managed_worker(monkeypatch, capsys):
    from scripts.ingest_fulltext_pdfs import _emit_progress as emit_fulltext_progress
    from scripts.ingest_openai_embeddings import _emit_progress as emit_openai_progress

    monkeypatch.delenv("ADMIN_JOB_PROGRESS", raising=False)
    emit_fulltext_progress(1, 2)
    emit_openai_progress(1, 2)
    assert capsys.readouterr().out == ""

    monkeypatch.setenv("ADMIN_JOB_PROGRESS", "1")
    emit_fulltext_progress(1, 2)
    emit_openai_progress(1, 2)
    output = capsys.readouterr().out
    assert "__ADMIN_JOB_PROGRESS__=47" in output
    assert "__ADMIN_JOB_PROGRESS__=50" in output


def test_reviewer_cannot_retry_admin_only_job(secure_client):
    with session_scope() as db:
        admin_job = create_job(db, "rescreen", {}, "admin")
        cancel_job(db, admin_job)
        quality_job = create_job(db, "kb_audit", {}, "admin")
        cancel_job(db, quality_job)
        admin_job_id, quality_job_id = admin_job.id, quality_job.id
    reviewer_headers = _login(secure_client, "reviewer1", "very-secure-pass-789")
    assert secure_client.post(
        f"/api/v1/admin/jobs/{admin_job_id}/retry", headers=reviewer_headers
    ).status_code == 403
    assert secure_client.post(
        f"/api/v1/admin/jobs/{quality_job_id}/retry", headers=reviewer_headers
    ).status_code == 202


def test_secure_heavy_library_operation_returns_job(secure_client):
    headers = _login(secure_client)
    direct = secure_client.post("/api/v1/library/sources", json=_draft_source(), headers=headers)
    assert direct.status_code == 409 and "草稿" in direct.text
    source = secure_client.get("/api/v1/library/sources?limit=1").json()["sources"][0]
    assert secure_client.patch(
        f"/api/v1/library/sources/{source['source_id']}", json={"title": source["title"]}, headers=headers
    ).status_code == 428
    response = secure_client.post("/api/v1/library/rescreen", headers=headers)
    assert response.status_code == 202
    assert response.json()["job"]["job_type"] == "rescreen"


def test_freshness_detects_fingerprint_mismatch(monkeypatch):
    monkeypatch.setattr(freshness, "catalog_fingerprint", lambda: "catalog-new")
    monkeypatch.setattr(freshness, "config_fingerprint", lambda: "config-new")
    monkeypatch.setattr(freshness, "fingerprint_paths", lambda _paths: "raw-new")
    monkeypatch.setattr(freshness, "sha256_file", lambda path: "chunks-new" if path.endswith("chunks.jsonl") else "")
    monkeypatch.setattr(freshness, "current_fulltext_input_fingerprint", lambda: "fulltext-new")
    monkeypatch.setattr(
        freshness,
        "_mtime",
        lambda path: 1.0 if path.endswith("processed_hashing_vectors.npz") else 0.0,
    )
    old_chunks_build = freshness.combine_fingerprints(
        {"governed_notes": "raw-new", "catalog": "catalog-old"}
    )
    old_vector_build = freshness.combine_fingerprints(
        {"chunks_sha256": "chunks-new", "chunks_build_fingerprint": old_chunks_build}
    )

    def stale_manifest(path):
        if path.endswith("source_screening_report.json"):
            return {"input_fingerprint": "catalog-old"}
        if path.endswith("chunks_manifest.json"):
            return {"build_fingerprint": old_chunks_build, "chunk_count": 562}
        if path.endswith("hashing_vector_manifest.json"):
            return {"status": "current", "input_fingerprint": old_vector_build}
        return {}

    monkeypatch.setattr(freshness, "_json", stale_manifest)
    items = freshness.artifact_freshness()
    screening = next(item for item in items if item["artifact"] == "screening")
    assert screening["status"] == "stale"
    assert next(item for item in items if item["artifact"] == "chunks")["status"] == "stale"
    # A catalog change propagates through the stale chunks state even when the
    # chunks file hash/count itself has not changed.
    assert next(item for item in items if item["artifact"] == "hashing_processed")["status"] == "stale"


def test_disabled_catalog_source_is_filtered_before_stale_chunks_rebuild(monkeypatch):
    base = {
        "title": "Home blood pressure monitoring",
        "organization": "Example",
        "region": "global",
        "year": 2026,
        "url": "https://example.org",
        "evidence_class": "guideline",
        "allowed_uses": ["home_bp_monitoring"],
        "source_quality_score": 25,
        "review_status": "included",
    }
    chunks = [
        {**base, "source_id": "disabled", "chunk_id": "disabled_001", "content": "家庭血压复核记录"},
        {**base, "source_id": "active", "chunk_id": "active_001", "content": "家庭血压复核记录"},
    ]
    monkeypatch.setattr(retriever_service, "_load_chunks", lambda _path=None: chunks)
    monkeypatch.setattr(
        retriever_service,
        "_current_catalog_governance",
        lambda: {"active": {**base, "source_id": "active"}},
    )
    monkeypatch.setattr(retriever_service, "_prefetch_openai_query_vectors", lambda _queries: None)
    result = retriever_service.retrieve_knowledge(
        ["家庭血压复核"], top_k=5, allowed_uses=["home_bp_monitoring"], min_quality_score=18
    )
    assert result.evidence and all("disabled" not in item.source_id for item in result.evidence)


def test_advisor_session_uuid_and_explicit_delete(secure_client):
    payload = {"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86}
    created = secure_client.post("/api/v1/advisor/sessions", json=payload)
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    assert len(session_id) == 36 and session_id.count("-") == 4
    deleted = secure_client.delete(f"/api/v1/advisor/sessions/{session_id}")
    assert deleted.status_code == 200
    assert secure_client.get(f"/api/v1/advisor/sessions/{session_id}").status_code == 404
