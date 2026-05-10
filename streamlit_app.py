from __future__ import annotations

import json

import streamlit as st

from app.agents.workflow import generate_report, preview_rules
from app.services.kb_audit import audit_knowledge_base
from app.services.source_catalog import screen_sources


st.set_page_config(page_title="PPG 血压估算解释 RAG-Agent", layout="wide")
st.title("PPG 血压估算解释 RAG-Agent")

with st.sidebar:
    st.header("PPG 估算输入")
    sbp = st.number_input("估算收缩压 SBP (mmHg)", min_value=40, max_value=260, value=145)
    dbp = st.number_input("估算舒张压 DBP (mmHg)", min_value=30, max_value=180, value=92)
    heart_rate = st.number_input("心率 bpm", min_value=20, max_value=240, value=82)
    quality_score = st.slider("信号质量分", min_value=0.0, max_value=1.0, value=0.86, step=0.01)
    confidence = st.slider("上游置信度", min_value=0.0, max_value=1.0, value=0.68, step=0.01)
    age = st.number_input("年龄", min_value=0, max_value=120, value=45)
    guideline_region = st.selectbox("指南地区", ["CN", "AHA", "auto"], index=0)

    st.header("基础情况")
    diabetes = st.checkbox("糖尿病")
    kidney_disease = st.checkbox("慢性肾脏病")
    cvd_history = st.checkbox("既往心血管病史")
    pregnancy = st.checkbox("妊娠或可能妊娠")
    antihypertensive_medication = st.checkbox("正在使用降压药")

    st.header("症状")
    chest_pain = st.checkbox("胸痛")
    shortness_of_breath = st.checkbox("气短或呼吸困难")
    back_pain = st.checkbox("背痛")
    numbness_or_weakness = st.checkbox("肢体麻木或无力")
    vision_change = st.checkbox("视物改变")
    speech_difficulty = st.checkbox("说话困难")
    severe_headache = st.checkbox("严重头痛")

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
