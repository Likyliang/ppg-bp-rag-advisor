"""Tests for the unified admin backend (shell + read-only aggregators)."""

import json

from fastapi.testclient import TestClient

from app.api import admin as admin_module
from app.main import app

client = TestClient(app)


def test_admin_shell_served():
    r = client.get("/api/v1/admin")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert 'id="app"' in body
    assert "高血压健康解释后台" in body


def test_legacy_library_admin_redirects_to_shell():
    r = client.get("/api/v1/library/admin", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/admin/"


def test_overview_aggregates_all_blocks():
    r = client.get("/api/v1/admin/overview")
    assert r.status_code == 200
    data = r.json()
    for key in ("library", "fulltext", "audit", "quality_gate"):
        assert key in data
    # library stats surface totals
    assert isinstance(data["library"].get("total"), int)
    # audit exposes counts as plain integers, not the raw lists
    assert isinstance(data["audit"].get("orphan_source_ids"), int)
    assert isinstance(data["audit"].get("unsafe_source_leakage"), int)
    # quality gate is either 已运行 or 未运行, never crashes
    assert data["quality_gate"]["status"] in ("已运行", "未运行")


def test_manifests_reports_index_status():
    r = client.get("/api/v1/admin/manifests")
    assert r.status_code == 200
    data = r.json()
    assert "fulltext_vector" in data
    assert "chunks_jsonl_count" in data
    assert isinstance(data["chunks_jsonl_count"], int)


def test_read_json_ignores_non_object(tmp_path):
    # Non-object JSON (array / scalar) collapses to None so callers can .get() safely.
    arr = tmp_path / "arr.json"
    arr.write_text("[1, 2, 3]", encoding="utf-8")
    assert admin_module._read_json(str(arr)) is None

    scalar = tmp_path / "scalar.json"
    scalar.write_text("42", encoding="utf-8")
    assert admin_module._read_json(str(scalar)) is None

    obj = tmp_path / "obj.json"
    obj.write_text('{"a": 1}', encoding="utf-8")
    assert admin_module._read_json(str(obj)) == {"a": 1}


def test_overview_degrades_when_a_block_fails(monkeypatch):
    # A failing block must not 500 the endpoint, and must surface a generic
    # marker (never a raw str(exc) that can embed absolute filesystem paths).
    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("/abs/secret/path/catalog.yaml exploded")

    monkeypatch.setattr("app.services.library_manager.LibraryManager", Boom)
    r = client.get("/api/v1/admin/overview")
    assert r.status_code == 200
    data = r.json()
    assert data["library"] == {"error": "加载失败"}
    assert "/abs/secret/path" not in json.dumps(data, ensure_ascii=False)
    # The other blocks still populate.
    assert data["quality_gate"]["status"] in ("已运行", "未运行")


def test_config_returns_six_yaml_without_secrets():
    r = client.get("/api/v1/admin/config")
    assert r.status_code == 200
    data = r.json()
    files = data["files"]
    assert set(files) == {
        "settings",
        "screening_rules",
        "safety_terms",
        "bp_thresholds",
        "advisor_questions",
        "field_mapping",
    }
    for meta in files.values():
        assert "path" in meta and "read_by" in meta and "content" in meta
    # No credential material leaks through the config viewer.
    blob = json.dumps(data, ensure_ascii=False).lower()
    for needle in ("api_key", "secret", "password", "sk-", "bearer"):
        assert needle not in blob
