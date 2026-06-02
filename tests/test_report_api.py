import re

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


def test_anthropic_llm_mode_uses_adapter(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    def fake_anthropic_report_body(**kwargs):
        return (
            "## 先看结论\n这是 Claude 个性化改写，引用了证据[1]，"
            "仍说明 PPG 不能替代规范血压测量。"
        )

    monkeypatch.setattr(generator_service, "generate_anthropic_report_body", fake_anthropic_report_body)
    payload = parse_payload({"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86})
    rules = run_rule_engine(payload)
    evidence = retrieve_knowledge(
        rules.retrieval_intents,
        allowed_uses=rules.retrieval_allowed_uses,
        min_quality_score=18,
    ).evidence
    report = generate_report_draft(payload, rules, evidence, mode="llm_rag")
    assert report.generation_mode == "llm_rag_anthropic:claude-sonnet-4-5"
    assert "Claude 个性化改写" in report.markdown_report
    assert "证据[1]" in report.markdown_report
    assert "## 参考文献" in report.markdown_report


def test_anthropic_llm_only_mode_uses_input_adapter(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    def fake_anthropic_input_only(**kwargs):
        return "## 先看结论\n这是 Claude 仅凭结构化输入的对照报告，PPG 不能替代规范血压测量。"

    monkeypatch.setattr(generator_service, "generate_anthropic_input_only_report", fake_anthropic_input_only)
    report = generate_report(
        {"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86},
        report_mode="llm_only",
    )
    assert report.generation_mode == "llm_only_input_anthropic:claude-sonnet-4-5"
    assert report.retrieved_evidence == []
    assert "## 参考文献" not in report.markdown_report


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


def test_deepseek_rag_body_without_citations_gets_them_injected(monkeypatch):
    # DeepSeek often drops [n]; the generator must inject valid markers so the
    # body never contradicts the "正文中的 [n]" tail, and mode stays llm_rag_deepseek.
    monkeypatch.setenv("REPORT_MODE", "llm_rag")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    def no_citation_body(**kwargs):
        return (
            "## 先看结论\n这次估算值明显偏高，不是诊断结果，建议先规范复核。\n\n"
            "## 接下来怎么做\n### 复测与记录\n- 安静休息后用上臂式血压计复核。\n"
            "### 生活方式\n- 减少钠盐摄入。\n\n"
            "## 几个容易误解的点\n- PPG 只能看趋势，不能替代规范血压测量。"
        )

    monkeypatch.setattr(generator_service, "generate_deepseek_report_body", no_citation_body)
    report = generate_report({"estimated_sbp": 146, "estimated_dbp": 92, "signal_quality_score": 0.86})
    assert report.generation_mode.startswith("llm_rag_deepseek")
    assert report.warnings == []
    body_only = report.markdown_report.split("## 参考文献", 1)[0]
    nums = re.findall(r"\[\d+(?:,\d+)*\]", body_only)
    assert nums, "expected injected inline citations in the body"
    # every inline number must be within evidence range
    n_ev = len(report.retrieved_evidence)
    for grp in nums:
        for part in grp.strip("[]").split(","):
            assert 1 <= int(part) <= n_ev


def test_deepseek_rag_strips_hallucinated_citation_numbers(monkeypatch):
    monkeypatch.setenv("REPORT_MODE", "llm_rag")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    def hallucinated_body(**kwargs):
        return (
            "## 先看结论\n这次估算值明显偏高[1]，但也参考了不存在的来源[99]。\n\n"
            "## 接下来怎么做\n### 复测与记录\n- 用上臂式血压计复核[1]。\n"
            "## 几个容易误解的点\n- PPG 只能看趋势[2]。"
        )

    monkeypatch.setattr(generator_service, "generate_deepseek_report_body", hallucinated_body)
    report = generate_report({"estimated_sbp": 146, "estimated_dbp": 92, "signal_quality_score": 0.86})
    assert report.generation_mode.startswith("llm_rag_deepseek")
    body_only = report.markdown_report.split("## 参考文献", 1)[0]
    assert "[99]" not in body_only
    n_ev = len(report.retrieved_evidence)
    for grp in re.findall(r"\[\d+(?:,\d+)*\]", body_only):
        for part in grp.strip("[]").split(","):
            assert int(part) <= n_ev


def test_deepseek_rag_glued_heading_is_repaired(monkeypatch):
    monkeypatch.setenv("REPORT_MODE", "llm_rag")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    def glued_body(**kwargs):
        # The exact real-world form: the no-emergency clause (which the sanitizer
        # rewrites and whose trailing whitespace it collapses) glued to a heading.
        return (
            "## 现在最该做什么\n这次数值明显偏高，建议复核[1]。\n"
            "目前没有填写胸痛、气短、肢体无力、视物改变、说话困难或严重头痛等需要立刻处理的症状；"
            "如果之后出现这些不适，请直接拨打 120 或前往急诊。## 为什么这样提醒你\n"
            "- 估算值进入偏高范围[1]。"
        )

    monkeypatch.setattr(generator_service, "generate_deepseek_report_body", glued_body)
    report = generate_report({"estimated_sbp": 146, "estimated_dbp": 92, "signal_quality_score": 0.86})
    assert "急诊。## 为什么" not in report.markdown_report
    assert "\n## 为什么这样提醒你" in report.markdown_report
    # the heading must be a real standalone line
    assert any(ln.strip() == "## 为什么这样提醒你" for ln in report.markdown_report.splitlines())


def test_deepseek_rag_medical_copy_cleans_wrong_words_and_colloquial(monkeypatch):
    # Editorial pass through the full RAG path: wrong words, over-reassurance,
    # colloquialisms and lifestyle detail must all be cleaned in the final report.
    monkeypatch.setenv("REPORT_MODE", "llm_rag")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    def messy_body(**kwargs):
        return (
            "## 先看结论\n这个数字本身只是估算，不说明任何问题[1]。算法置信度并非 100%，信号质量算中上等。\n\n"
            "## 现在最该做什么\n先别着急给自己下结论，建议休息后用药师（上臂式血压计）复核[1]。\n\n"
            "## 接下来怎么做\n### 生活方式\n- 保持规律运动（如快走、慢跑），少吃咸菜和加工食品[2,3]。\n\n"
            "## 几个容易误解的点\n- PPG 只能看趋势[6]。"
        )

    monkeypatch.setattr(generator_service, "generate_deepseek_report_body", messy_body)
    report = generate_report({"estimated_sbp": 146, "estimated_dbp": 92, "signal_quality_score": 0.86})
    md = report.markdown_report
    for bad in [
        "药师（上臂式血压计）", "用药师", "不说明任何问题", "并非 100%",
        "算中上等", "先别着急给自己下结论", "快走", "慢跑", "少吃咸菜",
        "这个数字本身只是估算",
    ]:
        assert bad not in md, f"medical copy leaked: {bad}"
    assert "用上臂式血压计复核" in md
    assert "适合自身情况的规律身体活动" in md or "减少高盐食物摄入" in md
    assert report.generation_mode.startswith("llm_rag_deepseek")


def test_deepseek_rag_emergency_strips_new_operational_advice(monkeypatch):
    # Emergency report must keep only 拨打120/急诊 + 不要等待复测; no driving/escort.
    monkeypatch.setenv("REPORT_MODE", "llm_rag")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    def emergency_body(**kwargs):
        return (
            "## 可能存在紧急风险\n这次估算值很高且伴随胸痛，请立即拨打 120 或前往急诊[1]。\n"
            "- 也不要自己开车去医院。\n"
            "- 最好有家人陪同前往，路上保持平躺。\n\n"
            "## 先看结论\n这次属于严重偏高参考范围[1]，先处理急症。"
        )

    monkeypatch.setattr(generator_service, "generate_deepseek_report_body", emergency_body)
    report = generate_report(
        {"estimated_sbp": 192, "estimated_dbp": 124, "signal_quality_score": 0.84,
         "symptoms": {"chest_pain": True}}
    )
    md = report.markdown_report
    assert report.safety_alert.emergency is True
    assert md.lstrip().startswith("## 可能存在紧急风险")
    assert "120" in md
    for bad in ["开车", "陪同", "平躺"]:
        assert bad not in md, f"emergency ops advice leaked: {bad}"
    assert "不要等待" in md


def test_deepseek_rag_isolated_hash_and_group_level_normalized(monkeypatch):
    # DeepSeek emits "#\n\n## 复测与记录" separators; the report must have no
    # standalone '#' lines and group headings must render as ### (under 接下来怎么做).
    monkeypatch.setenv("REPORT_MODE", "llm_rag")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    def grouped_body(**kwargs):
        return (
            "## 先看结论\n这次估算值明显偏高，不是诊断结果[1]。\n\n"
            "## 接下来怎么做\n#\n\n## 复测与记录 [1,2,3]\n- 用上臂式血压计复核。\n#\n\n"
            "## 设备复核 [1,4,5]\n- 使用经过验证的上臂式电子血压计。\n#\n\n"
            "## 生活方式 [2,3]\n- 减少钠盐摄入。\n#\n\n"
            "## 几个容易误解的点\n- PPG 只能看趋势[6]。"
        )

    monkeypatch.setattr(generator_service, "generate_deepseek_report_body", grouped_body)
    report = generate_report({"estimated_sbp": 146, "estimated_dbp": 92, "signal_quality_score": 0.86})
    body = report.markdown_report.split("## 参考文献", 1)[0]
    # No isolated '#' lines anywhere in the body.
    assert not any(ln.strip() in ("#", "# ") for ln in body.splitlines())
    # No empty heading lines.
    assert not any(re.fullmatch(r"#{1,6}\s*", ln.strip()) for ln in body.splitlines())
    # Recommendation groups demoted to ###.
    assert "### 复测与记录" in body
    assert "### 设备复核" in body
    assert "### 生活方式" in body
    assert "\n## 复测与记录" not in body


def test_deepseek_rag_strips_introduced_specific_details(monkeypatch):
    # DeepSeek adds forbidden specifics (fixed timepoints, sleep hours, week
    # durations, prep micro-steps); the report must scrub them to generic phrasing.
    monkeypatch.setenv("REPORT_MODE", "llm_rag")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    def detailed_body(**kwargs):
        return (
            "## 先看结论\n这次估算值明显偏高[1]。\n\n"
            "## 接下来怎么做\n### 复测与记录\n"
            "- 连续多天在同一时间（例如早晨起床排尿后、晚饭前）测量并记录[1,2,3]。\n"
            "- 测量前半小时不吸烟、不喝咖啡，排空膀胱，坐靠背椅，双脚平放。\n"
            "### 生活方式\n- 减少钠盐摄入，增加蔬菜水果，保证每晚 7-8 小时睡眠[2,3]。\n"
            "- 后续稳定后连续记录一周。\n"
            "## 几个容易误解的点\n- PPG 只能看趋势[6]。"
        )

    monkeypatch.setattr(generator_service, "generate_deepseek_report_body", detailed_body)
    report = generate_report({"estimated_sbp": 146, "estimated_dbp": 92, "signal_quality_score": 0.86})
    md = report.markdown_report
    for forbidden in [
        "晚饭前", "起床排尿后", "排空膀胱", "双脚平放", "测量前半小时",
        "7-8 小时", "7-8小时", "连续一周", "连续记录一周", "增加蔬菜水果",
    ]:
        assert forbidden not in md, f"forbidden detail leaked: {forbidden}"
    # safe replacements present
    assert ("在相对固定、方便的时间" in md) or ("连续记录一段时间" in md)


def test_deepseek_rag_empty_content_retries_then_succeeds(monkeypatch):
    # First DeepSeek call returns empty; the adapter retries once (still DeepSeek)
    # and the report stays llm_rag_deepseek instead of falling back.
    monkeypatch.setenv("REPORT_MODE", "llm_rag")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    from app.services import llm_adapter

    calls = {"n": 0}

    class FakeResp:
        status_code = 200

        def __init__(self, content):
            self._content = content

        def json(self):
            return {"choices": [{"message": {"content": self._content}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp("   ")  # empty -> triggers retry
        return FakeResp(
            "## 先看结论\n本次信号质量不足，先重新采集，再用上臂式电子血压计复核[1]。\n"
            "## 现在最该做什么\n先别看血压高低，重新规范采集[1]。\n"
            "## 接下来怎么做\n### 复测与记录\n- 重新采集后规范复核[1,2]。\n"
            "## 几个容易误解的点\n- PPG 只能看趋势，不能替代规范血压测量[3]。"
        )

    monkeypatch.setattr(llm_adapter.requests, "post", fake_post)
    report = generate_report(
        {"estimated_sbp": 150, "estimated_dbp": 95, "signal_quality_score": 0.42,
         "confidence": 0.38, "capture_duration_sec": 11, "signal_quality_label": "poor"}
    )
    assert calls["n"] == 2  # empty then retry
    assert report.generation_mode.startswith("llm_rag_deepseek")
    assert not any("回退" in w for w in report.warnings)


def test_deepseek_rag_double_empty_falls_back(monkeypatch):
    # If both the initial call and the retry return empty, degrade to template.
    monkeypatch.setenv("REPORT_MODE", "llm_rag")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    from app.services import llm_adapter

    calls = {"n": 0}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": ""}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(llm_adapter.requests, "post", fake_post)
    report = generate_report(
        {"estimated_sbp": 150, "estimated_dbp": 95, "signal_quality_score": 0.42,
         "signal_quality_label": "poor"}
    )
    assert calls["n"] == 2  # one retry, then give up
    assert report.generation_mode == "llm_rag_fallback_template"
    assert any("回退" in w or "empty content" in w for w in report.warnings)


def test_deepseek_rag_recovers_even_from_unmapped_headings(monkeypatch):
    # Even if DeepSeek returns only unmapped headings, the pipeline appends the
    # standard citable sections (在国内可以怎么做 / 几个容易误解的点) and injects
    # markers, so it stays a real RAG report instead of silently shipping an
    # inconsistent body.
    monkeypatch.setenv("REPORT_MODE", "llm_rag")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")

    def odd_body(**kwargs):
        return "## 随便写的标题\n一些内容，不是诊断结果。\n\n## 另一个标题\n继续写，建议规范复核。"

    monkeypatch.setattr(generator_service, "generate_deepseek_report_body", odd_body)
    report = generate_report({"estimated_sbp": 146, "estimated_dbp": 92, "signal_quality_score": 0.86})
    assert report.generation_mode.startswith("llm_rag_deepseek")
    body_only = report.markdown_report.split("## 参考文献", 1)[0]
    assert re.search(r"\[\d+(?:,\d+)*\]", body_only)  # body is citation-consistent


def test_workflow_citation_guard_detects_inconsistency_directly():
    # Unit-test the guard: a hand-built RAG report whose tail promises [n] but
    # whose body has none must be flagged so the workflow can degrade it.
    from app.agents.workflow import _citation_consistency_issue

    report = generate_report({"estimated_sbp": 146, "estimated_dbp": 92, "signal_quality_score": 0.86})
    assert report.retrieved_evidence  # has evidence
    # Sanity: a normal report is consistent.
    assert _citation_consistency_issue(report) is None

    # Corrupt the body: keep the tail claim, strip body markers.
    body, _, tail = report.markdown_report.partition("## 参考文献")
    stripped_body = re.sub(r"\s*\[\d+(?:,\d+)*\]", "", body)
    report.markdown_report = stripped_body + "## 参考文献" + tail
    assert _citation_consistency_issue(report) is not None

    # Out-of-range marker is also flagged.
    report2 = generate_report({"estimated_sbp": 146, "estimated_dbp": 92, "signal_quality_score": 0.86})
    report2.markdown_report = report2.markdown_report.replace("## 先看结论", "## 先看结论\n越界引用[999]。", 1)
    assert _citation_consistency_issue(report2) is not None


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
