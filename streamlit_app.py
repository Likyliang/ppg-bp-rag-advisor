from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from app.agents.workflow import generate_report, preview_rules
from app.services.kb_audit import audit_knowledge_base
from app.services.source_catalog import screen_sources


def _load_demo_cases():
    path = Path("tests/fixtures/demo_cases.jsonl")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


st.set_page_config(page_title="PPG 血压估算解释 RAG-Agent", layout="wide")
st.title("PPG 血压估算解释 RAG-Agent")

with st.sidebar:
    demo_cases = _load_demo_cases()
    selected_case = None
    if demo_cases:
        st.header("病例样例")
        case_ids = ["手动输入"] + [case["case_id"] for case in demo_cases]
        selected_id = st.selectbox("选择病例", case_ids)
        if selected_id != "手动输入":
            selected_case = next(case for case in demo_cases if case["case_id"] == selected_id)

    st.header("PPG 估算输入")
    sbp = st.number_input("估算收缩压 SBP (mmHg)", min_value=40, max_value=260, value=int(selected_case.get("estimated_sbp", 145)) if selected_case else 145)
    dbp = st.number_input("估算舒张压 DBP (mmHg)", min_value=30, max_value=180, value=int(selected_case.get("estimated_dbp", 92)) if selected_case else 92)
    heart_rate = st.number_input("心率 bpm", min_value=20, max_value=240, value=int(selected_case.get("heart_rate", 82)) if selected_case else 82)
    quality_score = st.slider("信号质量分", min_value=0.0, max_value=1.0, value=float(selected_case.get("signal_quality_score", 0.86)) if selected_case else 0.86, step=0.01)
    confidence = st.slider("上游置信度", min_value=0.0, max_value=1.0, value=float(selected_case.get("confidence", 0.68)) if selected_case else 0.68, step=0.01)
    age = st.number_input("年龄", min_value=0, max_value=120, value=int(selected_case.get("age", 45)) if selected_case else 45)
    guideline_region = st.selectbox("指南地区", ["CN", "AHA", "auto"], index=0)

    st.header("基础情况")
    diabetes = st.checkbox("糖尿病", value=bool(selected_case.get("diabetes", False)) if selected_case else False)
    kidney_disease = st.checkbox("慢性肾脏病", value=bool(selected_case.get("kidney_disease", False)) if selected_case else False)
    cvd_history = st.checkbox("既往心血管病史", value=bool(selected_case.get("cvd_history", False)) if selected_case else False)
    pregnancy = st.checkbox("妊娠或可能妊娠", value=bool(selected_case.get("pregnancy", False)) if selected_case else False)
    antihypertensive_medication = st.checkbox("正在使用降压药", value=bool(selected_case.get("antihypertensive_medication", False)) if selected_case else False)

    st.header("症状")
    selected_symptoms = selected_case.get("symptoms", {}) if selected_case else {}
    chest_pain = st.checkbox("胸痛", value=bool(selected_symptoms.get("chest_pain", False)))
    shortness_of_breath = st.checkbox("气短或呼吸困难", value=bool(selected_symptoms.get("shortness_of_breath", False)))
    back_pain = st.checkbox("背痛", value=bool(selected_symptoms.get("back_pain", False)))
    numbness_or_weakness = st.checkbox("肢体麻木或无力", value=bool(selected_symptoms.get("numbness_or_weakness", False)))
    vision_change = st.checkbox("视物改变", value=bool(selected_symptoms.get("vision_change", False)))
    speech_difficulty = st.checkbox("说话困难", value=bool(selected_symptoms.get("speech_difficulty", False)))
    severe_headache = st.checkbox("严重头痛", value=bool(selected_symptoms.get("severe_headache", False)))

payload = {
    "measurement": {
        "estimated_sbp": sbp,
        "estimated_dbp": dbp,
        "heart_rate": heart_rate,
        "signal_quality_score": quality_score,
        "confidence": confidence,
        "signal_quality_label": "good" if quality_score >= 0.75 else "fair" if quality_score >= 0.6 else "poor",
        "capture_duration_sec": 30,
        "ppg_source": "camera_finger",
    },
    "user_profile": {
        "age": age,
        "diabetes": diabetes,
        "kidney_disease": kidney_disease,
        "cvd_history": cvd_history,
        "pregnancy": pregnancy,
        "antihypertensive_medication": antihypertensive_medication,
    },
    "symptoms": {
        "chest_pain": chest_pain,
        "shortness_of_breath": shortness_of_breath,
        "back_pain": back_pain,
        "numbness_or_weakness": numbness_or_weakness,
        "vision_change": vision_change,
        "speech_difficulty": speech_difficulty,
        "severe_headache": severe_headache,
    },
    "locale": "zh-CN",
    "guideline_region": guideline_region,
    "user_question": "这个血压结果需要注意什么？",
}

rules = preview_rules(payload)
report = generate_report(payload)

report_tab, evidence_tab, audit_tab, json_tab = st.tabs(["报告", "证据", "知识库审计", "完整 JSON"])

with report_tab:
    left, right = st.columns([1, 1])
    with left:
        st.subheader("规则预览")
        st.json(rules.model_dump())
    with right:
        st.subheader("用户报告")
        st.markdown(report.markdown_report)
        st.subheader("安全审查")
        st.json(report.safety_review.model_dump(by_alias=True) if report.safety_review else {})
        st.download_button("下载 Markdown 报告", report.markdown_report, file_name=f"{report.report_id}.md")
        st.download_button(
            "下载 JSON 报告",
            json.dumps(report.model_dump(by_alias=True), ensure_ascii=False, indent=2),
            file_name=f"{report.report_id}.json",
            mime="application/json",
        )

with evidence_tab:
    st.subheader("检索证据")
    if report.retrieved_evidence:
        for item in report.retrieved_evidence:
            st.markdown(f"- **{item.title}** · {item.organization or 'source'} · `{item.evidence_class or 'unknown'}`")
            st.caption(f"topic={item.topic} · uses={', '.join(item.allowed_uses)} · score={item.source_quality_score}")
            if item.url:
                st.caption(item.url)
    else:
        st.info("知识库为空或未命中，当前使用规则和模板兜底。")

with audit_tab:
    st.subheader("来源筛选")
    screened = screen_sources()
    c1, c2, c3 = st.columns(3)
    c1.metric("候选来源", screened["total_sources"])
    c2.metric("纳入来源", screened["included_count"])
    c3.metric("排除来源", screened["excluded_count"])
    st.json({"topic_counts": screened["topic_counts"], "evidence_class_counts": screened["evidence_class_counts"]})

    st.subheader("知识库覆盖")
    st.json(audit_knowledge_base())

with json_tab:
    st.code(json.dumps(report.model_dump(by_alias=True), ensure_ascii=False, indent=2), language="json")
