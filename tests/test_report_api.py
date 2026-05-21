from fastapi.testclient import TestClient

from app.main import app
from app.services.generator import generate_report_draft
from app.services.retriever import retrieve_knowledge
from app.services.rule_engine import run_rule_engine
from app.services.validator import parse_payload


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_preview_rules_endpoint():
    response = client.post(
        "/api/v1/reports/preview-rules",
        json={"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86},
    )
    assert response.status_code == 200
    assert response.json()["estimated_bp_category"] == "stage_2_reference_range"


def test_generate_report_endpoint():
    response = client.post(
        "/api/v1/reports/generate",
        json={
            "estimated_sbp": 145,
            "estimated_dbp": 92,
            "heart_rate": 82,
            "signal_quality_score": 0.86,
            "confidence": 0.68,
            "capture_duration_sec": 30,
            "ppg_source": "camera_finger",
            "algorithm_version": "miniapp-bp-v1.0",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["input_summary"]["heart_rate"] == 82
    assert body["input_summary"]["signal_quality_score"] == 0.86
    assert body["input_summary"]["confidence"] == 0.68
    assert body["input_summary"]["capture_duration_sec"] == 30
    assert body["input_summary"]["ppg_source"] == "camera_finger"
    assert body["input_summary"]["algorithm_version"] == "miniapp-bp-v1.0"
    assert body["risk_assessment"]["estimated_bp_category"] == "stage_2_reference_range"
    assert body["safety_review"]["pass"] is True
    assert "diagnosis" not in body["risk_assessment"]
    assert body["retrieved_evidence"][0]["evidence_class"]
    assert body["recommendation_evidence"]
    assert body["citation_quality"]["recommendation_grounding_rate"] == 1.0


def test_kb_sources_endpoint():
    response = client.get("/api/v1/kb/sources")
    assert response.status_code == 200
    body = response.json()
    assert body["included_count"] >= 35
    assert body["excluded_count"] >= 4


def test_kb_audit_endpoint():
    response = client.get("/api/v1/kb/audit")
    assert response.status_code == 200
    assert response.json()["quality"]["has_no_unsafe_source_leakage"] is True


def test_kb_search_endpoint():
    response = client.post("/api/v1/kb/search", json={"queries": ["185/122 胸痛 急救"], "top_k": 3})
    assert response.status_code == 200
    evidence = response.json()["evidence"]
    assert evidence
    assert all("emergency_alert" in item["allowed_uses"] for item in evidence)


def test_invalid_payload_returns_422():
    response = client.post("/api/v1/reports/generate", json={"estimated_sbp": 500, "estimated_dbp": 92})
    assert response.status_code == 422


def test_empty_knowledge_base_fallback(tmp_path):
    missing_path = tmp_path / "missing_chunks.jsonl"
    result = retrieve_knowledge(["home blood pressure monitoring"], chunks_path=str(missing_path))
    assert result.evidence == []
    assert result.warnings


def test_llm_mode_falls_back_to_template(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    payload = parse_payload({"estimated_sbp": 130, "estimated_dbp": 82, "signal_quality_score": 0.86})
    rules = run_rule_engine(payload)
    report = generate_report_draft(payload, rules, [], mode="llm_rag")
    assert report.generation_mode == "llm_rag_fallback_template"
    assert report.markdown_report
