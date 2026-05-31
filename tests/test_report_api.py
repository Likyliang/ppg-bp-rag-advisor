from fastapi.testclient import TestClient

from app.main import app
from app.agents.workflow import generate_report
from app.services import generator as generator_service
from app.services.generator import _sanitize_llm_body, generate_report_draft
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
            "motion_artifact_score": 0.12,
            "finger_coverage_score": 0.93,
            "contact_pressure_level": "normal",
            "ambient_light_level": "normal",
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
    assert body["input_summary"]["motion_artifact_score"] == 0.12
    assert body["input_summary"]["finger_coverage_score"] == 0.93
    assert body["input_summary"]["contact_pressure_level"] == "normal"
    assert body["input_summary"]["ambient_light_level"] == "normal"
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


def test_deepseek_llm_mode_uses_adapter(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    def fake_deepseek_report_body(**kwargs):
        return "## 本次结果摘要\n这是 DeepSeek 个性化改写，但仍说明 PPG 不能替代规范血压测量。"

    monkeypatch.setattr(generator_service, "generate_deepseek_report_body", fake_deepseek_report_body)
    payload = parse_payload({"estimated_sbp": 130, "estimated_dbp": 82, "signal_quality_score": 0.86})
    rules = run_rule_engine(payload)
    report = generate_report_draft(payload, rules, [], mode="llm_rag")
    assert report.generation_mode == "llm_rag_deepseek:deepseek-v4-flash"
    assert "DeepSeek 个性化改写" in report.markdown_report
    assert "## 在国内可以怎么做" in report.markdown_report
    assert "## 几个容易误解的点" in report.markdown_report
    assert "## 免责声明" in report.markdown_report


def test_deepseek_output_preface_is_removed(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    def fake_deepseek_report_body(**kwargs):
        return (
            "好的，以下是根据您的规则和输入信息改写的个性化健康解释报告。\n\n"
            "---\n\n"
            "## 先看结论\n这次估算值偏高，建议先规范复核。"
        )

    monkeypatch.setattr(generator_service, "generate_deepseek_report_body", fake_deepseek_report_body)
    payload = parse_payload({"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86})
    rules = run_rule_engine(payload)
    report = generate_report_draft(payload, rules, [], mode="llm_rag")
    assert report.markdown_report.startswith("## 先看结论")
    assert "给用户看的报告" not in report.markdown_report
    assert "以下是根据您的规则" not in report.markdown_report
    assert "个性化健康解释报告" not in report.markdown_report


def test_deepseek_llm_only_mode_uses_no_evidence_adapter(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    captured = {}

    def fake_deepseek_input_only_report(**kwargs):
        captured.update(kwargs)
        return "## 先看结论\n这是只根据结构化输入生成的结果，仍说明 PPG 不能替代规范血压测量。"

    monkeypatch.setattr(generator_service, "generate_deepseek_input_only_report", fake_deepseek_input_only_report)
    payload = parse_payload({"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86})
    rules = run_rule_engine(payload)
    report = generate_report_draft(payload, rules, [], mode="llm_only")
    assert report.generation_mode == "llm_only_input_deepseek:deepseek-v4-flash"
    assert captured["payload"] == payload
    assert "evidence" not in captured
    assert "rule_result" not in captured
    assert "template_body" not in captured
    assert report.retrieved_evidence == []
    assert "本对照报告未使用本地文档库资料" in report.markdown_report


def test_unsafe_llm_output_falls_back_to_template(monkeypatch):
    monkeypatch.setenv("REPORT_MODE", "llm_rag")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    def unsafe_deepseek_report_body(**kwargs):
        return "## 本次结果摘要\n你患有高血压。"

    monkeypatch.setattr(generator_service, "generate_deepseek_report_body", unsafe_deepseek_report_body)
    report = generate_report({"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86})
    assert report.generation_mode == "llm_rag_safety_fallback_template"
    assert report.safety_review.passed is True
    assert "你患有高血压" not in report.markdown_report


def test_unsafe_llm_only_fallback_keeps_no_evidence(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    def unsafe_deepseek_input_only_report(**kwargs):
        return "## 先看结论\n你已经确诊高血压，不需要复测。"

    monkeypatch.setattr(generator_service, "generate_deepseek_input_only_report", unsafe_deepseek_input_only_report)
    report = generate_report(
        {"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86},
        report_mode="llm_only",
    )
    assert report.generation_mode == "llm_only_safety_fallback_template"
    assert report.safety_review.passed is True
    assert report.retrieved_evidence == []
    assert all(not item.evidence_ids for item in report.recommendation_evidence)
    assert "## 参考来源" not in report.markdown_report
    assert "本对照报告未使用本地文档库资料" in report.markdown_report


def test_llm_body_sanitizes_emergency_reassurance_phrasing():
    body = _sanitize_llm_body(
        "当前无需紧急处理，本次不属于紧急情况，本次不视为紧急情况，"
        "规范测量是确认血压水平的金标准。\n"
        "- 不要自行停药或改变现有药物（如有用药）。\n"
        "- 暂不需要打120，因为你没有报告胸痛。\n"
        "- 暂时不需要去急诊，也不要自己调整任何药物。\n"
        "- 不要自己调整任何用药。\n"
        "- 没有问题，不用复测。"
    )
    assert "当前无需紧急处理" not in body
    assert "本次不属于紧急情况" not in body
    assert "本次不视为紧急情况" not in body
    assert "停药" not in body
    assert "暂不需要打120" not in body
    assert "暂时不需要去急诊" not in body
    assert "调整任何药物" not in body
    assert "调整任何用药" not in body
    assert "拨打 120" in body
    assert "不用复测" not in body
    assert "本报告不提供用药方案" in body
    assert "急症提醒规则" not in body
    assert "需要立刻处理的症状" in body
    assert "金标准" not in body


def test_llm_body_sanitizes_over_specific_rag_details():
    body = _sanitize_llm_body(
        "## 现在最该做什么\n"
        "如果连续记录几天仍偏高，比如早上起床排尿后、晚饭前测量，"
        "或收缩压≥140 mmHg 或舒张压≥90 mmHg，就要处理。"
        "比如早上起床后、晚上睡前记录，或如早晨起床后、晚上睡前测量。"
        "也可能写成比如早上起床后、晚上睡觉前，或比如早晚固定时间，不要马上吃药。"
        "还可能写成按固定时间（比如早上起床排尿后、晚上睡觉前）记录血压。"
        "模型有时会说没有被归为紧急情况，或者把可用信号写成但不算高质量信号，只能当作趋势参考。"
        "也会说这次不是紧急情况（未触发本系统急症提醒规则），一次估算偏高不代表什么。"
        "还会写系统没有触发紧急提醒。"
        "它也可能说不等于确诊高血压，连续记录 3~5 天，甚至在加粗句子里说不要自行加药或减药。"
        "还有比如早起后安静时、如空腹、服药后等、是否吃药、不要自己改药、坚持下来一定有用。"
        "也可能写比如早晨和睡前。"
        "还可能把句子粘成如果之后出现这些不适，请直接拨打 120 或前往急诊。- 年龄 45 岁，正在吃降压药。"
        "袖带下缘距肘窝 2~3 厘米，松紧以能插入 1~2 指为宜。"
    )
    assert "连续记录几天" not in body
    assert "早上起床排尿后" not in body
    assert "晚上睡前" not in body
    assert "晚上睡觉前" not in body
    assert "早晚固定时间" not in body
    assert "（按自己方便" not in body
    assert "早晨起床后" not in body
    assert "马上吃药" not in body
    assert "没有被归为紧急情况" not in body
    assert "不是紧急情况" not in body
    assert "急症提醒规则" not in body
    assert "系统没有触发紧急提醒" not in body
    assert "。。" not in body
    assert "不代表什么" not in body
    assert "确诊" not in body
    assert "3~5 天" not in body
    assert "加药" not in body
    assert "减药" not in body
    assert "改药" not in body
    assert "服药" not in body
    assert "是否吃药" not in body
    assert "早起后安静时" not in body
    assert "早晨和睡前" not in body
    assert "（按自己方便" not in body
    assert "。- 年龄" not in body
    assert "正在吃降压药" not in body
    assert "一定有用" not in body
    assert "*如涉及" not in body
    assert "不算高质量信号" not in body
    assert "≥140" not in body
    assert "2~3 厘米" not in body
    assert "1~2 指" not in body
    assert "连续记录一段时间" in body
    assert "按设备说明书佩戴袖带" in body
