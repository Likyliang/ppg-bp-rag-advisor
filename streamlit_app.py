from __future__ import annotations

import json
import re
from pathlib import Path

import streamlit as st

from app.agents.workflow import generate_report, preview_rules
from app.schemas.conversation import AdvisorAnswer, AdvisorUserMessage
from app.services.advisor import advisor_turn, create_session, get_session_store, match_free_text_answer
from app.services.kb_audit import audit_knowledge_base
from app.services.source_catalog import screen_sources


NO_EMERGENCY_SYMPTOM_TEXT = (
    "目前没有填写胸痛、气短、肢体无力、视物改变、说话困难或严重头痛等需要立刻处理的症状；"
    "如果之后出现这些不适，请直接拨打 120 或前往急诊。"
)


GUIDELINE_REGION_OPTIONS = {
    "中国大陆（默认）": "CN",
    "AHA/ACC（科研对照）": "AHA",
    "自动选择": "auto",
}

PROVINCES = [
    "不填写",
    "北京",
    "上海",
    "天津",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
    "台湾",
]

RESIDENCE_AREA_OPTIONS = {
    "不确定 / 不填写": "unknown",
    "城市 / 城镇": "urban",
    "乡村 / 县域": "rural",
}

PRIMARY_CARE_OPTIONS = {
    "不确定 / 让系统给通用路径": "unknown",
    "社区卫生服务中心 / 家庭医生": "community_health_center",
    "乡镇卫生院 / 村医转诊": "township_health_center",
    "医院门诊": "hospital_outpatient",
}

QUALITY_LABELS = {
    "acceptable": "可用于保守解释",
    "fair": "一般，建议复测",
    "low_quality": "质量不足，先重测",
    "unknown": "未知",
}

RISK_LABELS = {
    "possible_emergency": "可能紧急",
    "urgent_attention": "尽快复核",
    "elevated_attention": "偏高，需复核记录",
    "lifestyle_attention": "关注趋势",
    "remeasurement_required": "先重新采集",
    "routine_monitoring": "常规观察",
    "insufficient_input": "信息不足",
}

CONTACT_PRESSURE_OPTIONS = {
    "正常": "normal",
    "偏低/过松": "low",
    "偏高/过紧": "high",
    "不稳定": "unstable",
    "不填写": "unknown",
}

AMBIENT_LIGHT_OPTIONS = {
    "正常": "normal",
    "偏暗": "dim",
    "强光/过亮": "bright",
    "不稳定": "unstable",
    "不填写": "unknown",
}

PPG_SOURCE_OPTIONS = {
    "手机摄像头手指 PPG": "camera_finger",
    "外部波形输入": "waveform",
    "其他来源": "other",
    "不确定": "unknown",
}

MODE_LABELS = {
    "template_only": "本地模板",
    "llm_rag_fallback_template": "模型生成失败，已使用保守报告",
    "llm_rag_safety_fallback_template": "保守兜底报告",
    "llm_rag_citation_fallback_template": "引用一致性兜底报告",
    "llm_only_template": "非 RAG 模板对照",
    "llm_only_input_deepseek": "DeepSeek 非 RAG：仅结构化输入",
    "llm_only_input_anthropic": "Claude 非 RAG：仅结构化输入",
    "llm_only_fallback_template": "非 RAG 生成失败，已使用保守报告",
    "llm_only_safety_fallback_template": "非 RAG 保守兜底报告",
}


def _option_index(options: dict[str, str], selected_value: str, default: int = 0) -> int:
    labels = list(options.keys())
    return next(
        (idx for idx, label in enumerate(labels) if options[label] == selected_value),
        default,
    )


def _score_label(value, higher_is_better: bool = True) -> str:
    if value is None:
        return "未输入"
    if higher_is_better:
        if value >= 0.75:
            return "较好"
        if value >= 0.60:
            return "一般"
        return "偏低"
    if value >= 0.70:
        return "偏高"
    if value >= 0.45:
        return "中等"
    return "较低"


def build_ppg_parameter_rows(payload: dict, rules) -> list[dict[str, str]]:
    measurement = payload["measurement"]
    warnings_text = "；".join(rules.quality.warnings)
    rows = [
        {
            "参数": "信号质量分",
            "当前值": f"{measurement.get('signal_quality_score'):.2f}",
            "页面解读": _score_label(measurement.get("signal_quality_score"), higher_is_better=True),
            "对报告的影响": "低于阈值时会弱化或停止风险解释，优先提示重新采集。",
        },
        {
            "参数": "上游置信度",
            "当前值": f"{measurement.get('confidence'):.2f}",
            "页面解读": _score_label(measurement.get("confidence"), higher_is_better=True),
            "对报告的影响": "偏低时加入复测提醒，但不等同于血压准确或不准确。",
        },
        {
            "参数": "采集时长",
            "当前值": f"{measurement.get('capture_duration_sec')} 秒",
            "页面解读": "偏短" if measurement.get("capture_duration_sec", 0) < 20 else "可展示",
            "对报告的影响": "偏短时提示重新采集不少于20秒；这是采集质量提示，不是诊断。",
        },
        {
            "参数": "运动伪影",
            "当前值": f"{measurement.get('motion_artifact_score'):.2f}",
            "页面解读": _score_label(measurement.get("motion_artifact_score"), higher_is_better=False),
            "对报告的影响": "中高时触发 PPG 运动伪影检索意图；过高时本次结果只适合提示重测。",
        },
        {
            "参数": "手指覆盖完整度",
            "当前值": f"{measurement.get('finger_coverage_score'):.2f}",
            "页面解读": _score_label(measurement.get("finger_coverage_score"), higher_is_better=True),
            "对报告的影响": "覆盖不足时提示重新覆盖摄像头；不推断真实血压偏差方向。",
        },
        {
            "参数": "接触压力",
            "当前值": measurement.get("contact_pressure_level", "unknown"),
            "页面解读": "可能影响波形" if measurement.get("contact_pressure_level") in {"low", "high", "unstable"} else "未触发",
            "对报告的影响": "异常时触发接触压力/波形质量相关证据检索。",
        },
        {
            "参数": "环境光",
            "当前值": measurement.get("ambient_light_level", "unknown"),
            "页面解读": "可能干扰采集" if measurement.get("ambient_light_level") in {"dim", "bright", "unstable"} else "未触发",
            "对报告的影响": "异常时触发摄像头 PPG 环境光和光照干扰相关检索。",
        },
    ]
    if warnings_text:
        rows.append(
            {
                "参数": "规则层提示",
                "当前值": str(len(rules.quality.warnings)),
                "页面解读": "已触发",
                "对报告的影响": warnings_text,
            }
        )
    return rows


def ppg_related_intents(rules) -> list[str]:
    keywords = ("PPG", "ppg", "signal", "信号", "伪影", "环境光", "接触压力", "手指", "摄像头")
    return [intent for intent in rules.retrieval_intents if any(keyword in intent for keyword in keywords)]


def clean_user_markdown(markdown: str) -> str:
    text = markdown.strip()
    first_heading = re.search(r"(?m)^#{1,3}\s+", text)
    if first_heading and first_heading.start() > 0:
        text = text[first_heading.start():]
    blocked_patterns = (
        "给用户看的报告",
        "根据您的规则和输入信息",
        "以下是根据",
        "个性化健康解释报告",
        "当前按中国大陆常见健康管理语境",
        "优先参考国家卫健委",
        "本报告参考了国家卫健委",
        "报告更强调有来源的官方",
    )
    replacements = {
        "## 一句话结论": "## 现在最该做什么",
        "这次估算值偏高，重点不是给自己下诊断，而是用上臂式血压计规范复核，并连续记录趋势。": (
            "结论：这次估算值明显偏高，今天先用上臂式血压计复核；"
            "如果连续多次仍偏高，带记录去社区、乡镇卫生院或门诊咨询。"
        ),
        "比如早上起床后、晚上睡觉前": "按自己方便且相对固定的时间",
        "早上起床后、晚上睡觉前": "自己方便且相对固定的时间",
        "比如早起后安静时": "按自己方便且相对固定的时间",
        "早起后安静时": "自己方便且相对固定的时间",
        "比如早晨和睡前": "按自己方便且相对固定的时间",
        "早晨和睡前": "自己方便且相对固定的时间",
        "比如早晨或睡前": "按自己方便且相对固定的时间",
        "早晨或睡前": "自己方便且相对固定的时间",
        "比如早晨或傍晚": "按自己方便且相对固定的时间",
        "早晨或傍晚": "自己方便且相对固定的时间",
        "比如早晚固定时间": "按固定时间",
        "连续多天、固定时间（按自己方便且相对固定的时间）": "连续记录一段时间",
        "连续记录 3~5 天": "连续记录一段时间",
        "正在吃降压药": "正在使用降压药",
        "不要自己改药": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自行改药": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自行加药或减药": "用药问题请咨询医生；本报告不提供用药方案",
        "不等于确诊高血压": "不等于诊断结果",
        "不能确诊高血压": "不能作为诊断结果",
        "这次不是紧急情况（未触发本系统急症提醒规则）": NO_EMERGENCY_SYMPTOM_TEXT,
        "本次不是紧急情况（未触发本系统急症提醒规则）": NO_EMERGENCY_SYMPTOM_TEXT,
        "不是紧急情况（未触发本系统急症提醒规则）": NO_EMERGENCY_SYMPTOM_TEXT,
        "不是紧急情况": NO_EMERGENCY_SYMPTOM_TEXT,
        "本次未触发本系统急症提醒规则": NO_EMERGENCY_SYMPTOM_TEXT,
        "当前未触发本系统急症提醒规则": NO_EMERGENCY_SYMPTOM_TEXT,
        "未触发本系统急症提醒规则": NO_EMERGENCY_SYMPTOM_TEXT,
        "本系统未触发急症提醒": NO_EMERGENCY_SYMPTOM_TEXT,
        "系统没有触发紧急提醒": NO_EMERGENCY_SYMPTOM_TEXT,
        "没有触发紧急提醒": NO_EMERGENCY_SYMPTOM_TEXT,
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace(f"{NO_EMERGENCY_SYMPTOM_TEXT}（{NO_EMERGENCY_SYMPTOM_TEXT}）", NO_EMERGENCY_SYMPTOM_TEXT)
    text = re.sub(rf"(?:{re.escape(NO_EMERGENCY_SYMPTOM_TEXT)}[。；;，,\s]*)+", NO_EMERGENCY_SYMPTOM_TEXT, text)
    text = text.replace("连续多天、固定时间（按自己方便且相对固定的时间）", "连续记录一段时间")
    text = text.replace("连续多天、固定时间（自己方便且相对固定的时间）", "连续记录一段时间")
    text = text.replace("连续记录一段时间测量", "连续记录一段时间")
    text = text.replace(f"{NO_EMERGENCY_SYMPTOM_TEXT}- ", f"{NO_EMERGENCY_SYMPTOM_TEXT}\n- ")
    text = re.sub(r"([。！？])-\s+", r"\1\n- ", text)
    text = text.replace("。。", "。").replace("；。", "。")
    lines = [line for line in text.splitlines() if not any(pattern in line for pattern in blocked_patterns)]
    return "\n".join(lines).strip()


def clean_control_markdown(markdown: str) -> str:
    text = clean_user_markdown(markdown)
    text = re.sub(r"\n## 参考文献\n.*?(?=\n## |\Z)", "", text, flags=re.S)
    text = re.sub(r"\n## 参考来源\n.*?(?=\n## |\Z)", "", text, flags=re.S)
    text = re.sub(
        r"\n## 参考依据说明\n.*?(?=\n## |\Z)",
        "\n\n## 对照组说明\n本栏只使用同一份结构化输入，不使用本地文档库，也不展示参考来源。",
        text,
        flags=re.S,
    )
    return text.strip()


def build_compare_rows(report, control_report) -> list[dict[str, str]]:
    rag_status = (
        "DeepSeek 输出未通过安全审查，当前展示保守兜底报告"
        if report.generation_mode.startswith("llm_rag_safety_fallback")
        else "DeepSeek + RAG 生成"
        if report.generation_mode.startswith("llm_rag_deepseek")
        else MODE_LABELS.get(report.generation_mode, report.generation_mode)
    )
    control_status = MODE_LABELS.get(
        control_report.generation_mode,
        "DeepSeek 非 RAG：仅结构化输入"
        if control_report.generation_mode.startswith("llm_only_input_deepseek")
        else control_report.generation_mode,
    )
    return [
        {
            "对比点": "模型输入",
            "RAG 版": "结构化输入 + 规则结果 + 本地证据片段 + 模板约束",
            "非 RAG 对照": "只有结构化输入",
        },
        {
            "对比点": "证据来源",
            "RAG 版": f"{len(report.retrieved_evidence)} 条证据片段，可查看参考来源",
            "非 RAG 对照": "0 条证据片段，不显示参考来源",
        },
        {
            "对比点": "输出特点",
            "RAG 版": "更保守、更稳定，建议能绑定到文档库证据",
            "非 RAG 对照": "表达更自由，但阈值、频次和路径可能缺少来源约束",
        },
        {
            "对比点": "当前生成状态",
            "RAG 版": rag_status,
            "非 RAG 对照": control_status,
        },
    ]


def scan_non_rag_risks(markdown: str, control_report) -> list[dict[str, str]]:
    risks = [
        {
            "暴露点": "没有本地证据",
            "页面表现": f"证据数量为 {len(control_report.retrieved_evidence)}",
            "为什么能说明 RAG 有用": "RAG 版能把建议绑定到可追溯来源；非 RAG 无法说明依据来自哪里。",
        }
    ]
    if control_report.citation_quality.recommendation_grounding_rate < 1.0:
        risks.append(
            {
                "暴露点": "建议无法证据绑定",
                "页面表现": "参考依据说明显示“部分建议需要继续补充资料”",
                "为什么能说明 RAG 有用": "RAG 版会检查建议是否能对应到文档库证据，降低凭空建议的风险。",
            }
        )

    pattern_groups = [
        (
            r"连续.*3\s*天|早晚各一次|每天早晚|每年体检",
            "出现具体频次建议",
            "具体监测频次如果没有来源约束，容易变成模型经验化表达。",
        ),
        (
            r"<\s*130/80|≥\s*140|≥\s*90|60-100|正常范围",
            "出现具体阈值或正常范围",
            "阈值和范围应尽量绑定指南或官方资料，否则老师会追问依据。",
        ),
        (
            r"风险相对较低|不要慌张|不用担心|暂不需要|不需要|无需",
            "出现安抚性语气",
            "健康场景里安抚性判断需要格外谨慎，RAG + Safety Agent 会更保守。",
        ),
        (
            r"买药|吃药|半片药|药物|用药",
            "触及用药相关表达",
            "用药话题应只提示咨询医生，不能给处理方案。",
        ),
    ]
    for pattern, title, reason in pattern_groups:
        if re.search(pattern, markdown):
            risks.append(
                {
                    "暴露点": title,
                    "页面表现": "非 RAG 文本中命中该类表述",
                    "为什么能说明 RAG 有用": reason,
                }
            )

    if not risks:
        risks.append(
            {
                "暴露点": "本次未发现明显问题",
                "页面表现": "非 RAG 文本较保守",
                "为什么能说明 RAG 有用": "仍然没有证据来源和建议绑定，适合作为可追溯性对照。",
            }
        )
    return risks


FEATURED_DEMO_CASES = [
    {
        "case_id": "cn_city_stage2_demo",
        "display_name": "城市中年：估算明显偏高，建议社区复核",
        "estimated_sbp": 145,
        "estimated_dbp": 92,
        "heart_rate": 82,
        "signal_quality_score": 0.86,
        "confidence": 0.68,
        "age": 45,
        "province": "上海",
        "residence_area": "urban",
        "primary_care_preference": "community_health_center",
    },
    {
        "case_id": "cn_rural_stage2_demo",
        "display_name": "乡村县域：多次偏高，建议乡镇卫生院复核",
        "estimated_sbp": 151,
        "estimated_dbp": 96,
        "heart_rate": 78,
        "signal_quality_score": 0.88,
        "confidence": 0.72,
        "age": 58,
        "province": "河南",
        "residence_area": "rural",
        "primary_care_preference": "township_health_center",
    },
    {
        "case_id": "cn_low_quality_demo",
        "display_name": "采集质量差：先重新测，不做风险判断",
        "estimated_sbp": 150,
        "estimated_dbp": 95,
        "heart_rate": 83,
        "signal_quality_score": 0.42,
        "confidence": 0.40,
        "capture_duration_sec": 12,
        "age": 42,
        "province": "广东",
        "residence_area": "urban",
        "primary_care_preference": "community_health_center",
    },
    {
        "case_id": "cn_ppg_feature_quality_demo",
        "display_name": "本周新增：PPG信号参数输入演示",
        "estimated_sbp": 142,
        "estimated_dbp": 90,
        "heart_rate": 81,
        "signal_quality_score": 0.79,
        "confidence": 0.62,
        "capture_duration_sec": 18,
        "motion_artifact_score": 0.58,
        "finger_coverage_score": 0.68,
        "contact_pressure_level": "high",
        "ambient_light_level": "bright",
        "age": 44,
        "province": "上海",
        "residence_area": "urban",
        "primary_care_preference": "community_health_center",
    },
    {
        "case_id": "cn_emergency_chest_pain_demo",
        "display_name": "高值伴胸痛：触发 120 / 急诊提示",
        "estimated_sbp": 185,
        "estimated_dbp": 122,
        "heart_rate": 96,
        "signal_quality_score": 0.90,
        "confidence": 0.75,
        "age": 61,
        "province": "北京",
        "residence_area": "urban",
        "primary_care_preference": "hospital_outpatient",
        "symptoms": {"chest_pain": True},
    },
    {
        "case_id": "cn_older_demo",
        "display_name": "老年用户：偏高趋势，采用更保守解释",
        "estimated_sbp": 138,
        "estimated_dbp": 86,
        "heart_rate": 74,
        "signal_quality_score": 0.86,
        "confidence": 0.72,
        "age": 70,
        "province": "四川",
        "residence_area": "urban",
        "primary_care_preference": "community_health_center",
    },
    {
        "case_id": "cn_diabetes_demo",
        "display_name": "合并糖尿病：建议带记录咨询医生",
        "estimated_sbp": 136,
        "estimated_dbp": 86,
        "heart_rate": 76,
        "signal_quality_score": 0.86,
        "confidence": 0.72,
        "age": 52,
        "diabetes": True,
        "province": "江苏",
        "residence_area": "urban",
        "primary_care_preference": "community_health_center",
    },
    {
        "case_id": "cn_medication_demo",
        "display_name": "正在使用降压药：只提示复核和医生沟通",
        "estimated_sbp": 141,
        "estimated_dbp": 88,
        "heart_rate": 73,
        "signal_quality_score": 0.86,
        "confidence": 0.72,
        "age": 56,
        "antihypertensive_medication": True,
        "province": "浙江",
        "residence_area": "urban",
        "primary_care_preference": "community_health_center",
    },
    {
        "case_id": "cn_pregnancy_demo",
        "display_name": "妊娠或可能妊娠：更保守处理",
        "estimated_sbp": 132,
        "estimated_dbp": 84,
        "heart_rate": 88,
        "signal_quality_score": 0.84,
        "confidence": 0.70,
        "age": 31,
        "sex": "female",
        "pregnancy": True,
        "province": "湖北",
        "residence_area": "urban",
        "primary_care_preference": "hospital_outpatient",
    },
    {
        "case_id": "cn_vision_demo",
        "display_name": "高值伴视物改变：急症规则演示",
        "estimated_sbp": 182,
        "estimated_dbp": 119,
        "heart_rate": 89,
        "signal_quality_score": 0.86,
        "confidence": 0.72,
        "age": 49,
        "province": "山东",
        "residence_area": "rural",
        "primary_care_preference": "township_health_center",
        "symptoms": {"vision_change": True},
    },
    {
        "case_id": "cn_normal_demo",
        "display_name": "正常范围：强调趋势观察和健康生活方式",
        "estimated_sbp": 116,
        "estimated_dbp": 74,
        "heart_rate": 72,
        "signal_quality_score": 0.90,
        "confidence": 0.80,
        "age": 36,
        "province": "福建",
        "residence_area": "urban",
        "primary_care_preference": "community_health_center",
    },
    {
        "case_id": "cn_aha_compare_demo",
        "display_name": "科研对照：AHA/ACC 指南语境",
        "estimated_sbp": 145,
        "estimated_dbp": 92,
        "heart_rate": 72,
        "signal_quality_score": 0.86,
        "confidence": 0.72,
        "age": 45,
        "guideline_region": "AHA",
    },
]

CASE_LABELS = {
    "normal_good_quality": "正常范围：信号良好",
    "high_good_quality": "偏高估算：信号良好",
    "high_low_quality": "偏高但质量差：先重测",
    "severe_no_symptoms": "严重偏高值：无急症症状",
    "severe_chest_pain": "严重偏高伴胸痛",
    "medication_user": "正在使用降压药",
    "diabetes_user": "合并糖尿病",
    "alias_input": "小程序别名字段输入",
    "fair_quality": "信号一般且采集偏短",
    "pregnancy": "妊娠或可能妊娠",
}


def _load_demo_cases():
    path = Path("tests/fixtures/demo_cases.jsonl")
    fixture_cases = []
    if not path.exists():
        return list(FEATURED_DEMO_CASES)
    fixture_cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    featured_ids = {case["case_id"] for case in FEATURED_DEMO_CASES}
    return list(FEATURED_DEMO_CASES) + [case for case in fixture_cases if case.get("case_id") not in featured_ids]


def _case_label(case):
    if case is None:
        return "手动输入"
    case_id = case.get("case_id", "")
    if case.get("display_name"):
        return case["display_name"]
    if case_id in CASE_LABELS:
        return CASE_LABELS[case_id]
    if case_id.startswith("normal_"):
        return f"正常范围样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("elevated_"):
        return f"偏高趋势样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("stage1_"):
        return f"轻度偏高样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("stage2_"):
        return f"明显偏高样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("severe_emergency_"):
        return f"严重偏高伴症状样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("severe_no_symptom_"):
        return f"严重偏高无症状样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("low_quality_"):
        return f"低质量采集样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("fair_short_"):
        return f"采集偏短样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("older_"):
        return f"老年用户样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("pregnancy_"):
        return f"妊娠背景样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("diabetes_"):
        return f"糖尿病背景样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("kidney_"):
        return f"慢性肾脏病背景样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("cvd_"):
        return f"既往心血管病史样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("medication_"):
        return f"正在用降压药样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("dizziness_"):
        return f"头晕症状样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("vision_"):
        return f"视物改变样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("speech_"):
        return f"说话困难样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("weakness_"):
        return f"肢体无力样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("aha_region_"):
        return f"AHA/ACC 对照样例 {case_id.rsplit('_', 1)[-1]}"
    if case_id.startswith("bilingual_"):
        return f"双语输出样例 {case_id.rsplit('_', 1)[-1]}"
    return case_id or "未命名病例"


st.set_page_config(page_title="PPG 血压估算解释 RAG-Agent", layout="wide")
st.title("PPG 血压估算解释 RAG-Agent")
st.caption("网页演示版：展示 PPG 信号参数如何进入规则层、检索意图和报告生成。该 demo 只做健康解释，不验证 PPG 血压估算准确性。")

with st.sidebar:
    demo_cases = _load_demo_cases()
    selected_case = None
    if demo_cases:
        st.header("病例样例")
        selected_case = st.selectbox("选择病例", [None] + demo_cases, format_func=_case_label)

    st.header("PPG 估算输入")
    sbp = st.number_input("估算收缩压 SBP (mmHg)", min_value=40, max_value=260, value=int(selected_case.get("estimated_sbp", 145)) if selected_case else 145)
    dbp = st.number_input("估算舒张压 DBP (mmHg)", min_value=30, max_value=180, value=int(selected_case.get("estimated_dbp", 92)) if selected_case else 92)
    heart_rate = st.number_input("心率 bpm", min_value=20, max_value=240, value=int(selected_case.get("heart_rate", 82)) if selected_case else 82)

    st.header("PPG 信号参数")
    st.caption("本周新增展示：这些参数只影响采集质量解释和复测建议，不用于诊断或证明估算准确。")
    quality_score = st.slider("信号质量分", min_value=0.0, max_value=1.0, value=float(selected_case.get("signal_quality_score", 0.86)) if selected_case else 0.86, step=0.01)
    confidence = st.slider("上游置信度", min_value=0.0, max_value=1.0, value=float(selected_case.get("confidence", 0.68)) if selected_case else 0.68, step=0.01)
    capture_duration_sec = st.number_input(
        "采集时长（秒）",
        min_value=5,
        max_value=120,
        value=int(selected_case.get("capture_duration_sec", 30)) if selected_case else 30,
        step=1,
    )
    motion_artifact_score = st.slider("手指移动/运动伪影", min_value=0.0, max_value=1.0, value=float(selected_case.get("motion_artifact_score", 0.10)) if selected_case else 0.10, step=0.01)
    finger_coverage_score = st.slider("手指覆盖完整度", min_value=0.0, max_value=1.0, value=float(selected_case.get("finger_coverage_score", 0.92)) if selected_case else 0.92, step=0.01)
    selected_contact_pressure = selected_case.get("contact_pressure_level", "normal") if selected_case else "normal"
    contact_pressure_labels = list(CONTACT_PRESSURE_OPTIONS.keys())
    contact_pressure_index = _option_index(CONTACT_PRESSURE_OPTIONS, selected_contact_pressure)
    contact_pressure_label = st.selectbox("手指按压力度", contact_pressure_labels, index=contact_pressure_index)
    selected_ambient_light = selected_case.get("ambient_light_level", "normal") if selected_case else "normal"
    ambient_light_labels = list(AMBIENT_LIGHT_OPTIONS.keys())
    ambient_light_index = _option_index(AMBIENT_LIGHT_OPTIONS, selected_ambient_light)
    ambient_light_label = st.selectbox("环境光", ambient_light_labels, index=ambient_light_index)
    selected_ppg_source = selected_case.get("ppg_source", "camera_finger") if selected_case else "camera_finger"
    ppg_source_labels = list(PPG_SOURCE_OPTIONS.keys())
    ppg_source_index = _option_index(PPG_SOURCE_OPTIONS, selected_ppg_source)
    ppg_source_label = st.selectbox("PPG 来源", ppg_source_labels, index=ppg_source_index)
    algorithm_version = st.text_input(
        "算法版本",
        value=str(selected_case.get("algorithm_version", "miniapp-bp-v1.1-signal-demo")) if selected_case else "miniapp-bp-v1.1-signal-demo",
    )
    age = st.number_input("年龄", min_value=0, max_value=120, value=int(selected_case.get("age", 45)) if selected_case else 45)
    selected_region = selected_case.get("guideline_region", "CN") if selected_case else "CN"
    region_labels = list(GUIDELINE_REGION_OPTIONS.keys())
    region_index = next(
        (idx for idx, label in enumerate(region_labels) if GUIDELINE_REGION_OPTIONS[label] == selected_region),
        0,
    )
    guideline_region_label = st.selectbox("指南语境", region_labels, index=region_index)
    guideline_region = GUIDELINE_REGION_OPTIONS[guideline_region_label]

    st.header("中国使用场景")
    selected_province = selected_case.get("province") if selected_case else None
    province_index = PROVINCES.index(selected_province) if selected_province in PROVINCES else 0
    province_label = st.selectbox("所在省份/地区", PROVINCES, index=province_index)
    selected_residence_area = selected_case.get("residence_area", "unknown") if selected_case else "unknown"
    residence_labels = list(RESIDENCE_AREA_OPTIONS.keys())
    residence_index = next(
        (idx for idx, label in enumerate(residence_labels) if RESIDENCE_AREA_OPTIONS[label] == selected_residence_area),
        0,
    )
    residence_area_label = st.selectbox("居住场景", residence_labels, index=residence_index)
    selected_primary_care = selected_case.get("primary_care_preference", "unknown") if selected_case else "unknown"
    primary_care_labels = list(PRIMARY_CARE_OPTIONS.keys())
    primary_care_index = next(
        (idx for idx, label in enumerate(primary_care_labels) if PRIMARY_CARE_OPTIONS[label] == selected_primary_care),
        0,
    )
    primary_care_label = st.selectbox("就近咨询路径", primary_care_labels, index=primary_care_index)

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

    st.header("心振 / 节律特征（实验）")
    enable_screening = st.checkbox(
        "启用排查建议（建议进一步排查）",
        value=False,
        help="基于 PPG 节律/变异与 SCG（心振）特征给出“建议就医排查”的提示——是带不确定性、带就医指引、置信度封顶的分诊建议，不是诊断。",
    )
    with st.expander("PPG 节律 / SCG 心振 输入", expanded=enable_screening):
        rhythm_available = st.checkbox("提供脉搏节律分析", value=enable_screening)
        pulse_rhythm_label = st.selectbox("脉搏节律", ["未知", "规则", "不规则"], index=0)
        ibi_cv_val = st.slider("脉搏间期变异系数 (IBI CV)", 0.0, 1.0, 0.05, step=0.01)
        ectopic_ratio_val = st.slider("疑似早搏比例", 0.0, 1.0, 0.0, step=0.01)
        valid_beat_count_val = st.number_input("可分析心搏数", min_value=0, max_value=2000, value=40)
        scg_available = st.checkbox("提供 SCG / 心振", value=False)
        scg_quality_label = st.selectbox("心振信号质量", ["未知", "好", "中", "差"], index=1)
        pep_ms_val = st.number_input("PEP 射血前期 (ms)", min_value=0, max_value=600, value=0)
        lvet_ms_val = st.number_input("LVET 左室射血时间 (ms)", min_value=0, max_value=900, value=0)
        s1_s2_ratio_val = st.number_input("心音 S1/S2 振幅比", min_value=0.0, max_value=20.0, value=0.0, step=0.1)
        beat_amplitude_cv_val = st.slider("心振逐拍幅值变异 (CV)", 0.0, 1.0, 0.0, step=0.01)

payload = {
    "measurement": {
        "estimated_sbp": sbp,
        "estimated_dbp": dbp,
        "heart_rate": heart_rate,
        "signal_quality_score": quality_score,
        "confidence": confidence,
        "signal_quality_label": "good" if quality_score >= 0.75 else "fair" if quality_score >= 0.6 else "poor",
        "capture_duration_sec": capture_duration_sec,
        "motion_artifact_score": motion_artifact_score,
        "finger_coverage_score": finger_coverage_score,
        "contact_pressure_level": CONTACT_PRESSURE_OPTIONS[contact_pressure_label],
        "ambient_light_level": AMBIENT_LIGHT_OPTIONS[ambient_light_label],
        "ppg_source": PPG_SOURCE_OPTIONS[ppg_source_label],
        "algorithm_version": algorithm_version,
        "calculation_principle": "camera-based finger PPG estimation",
    },
    "user_profile": {
        "age": age,
        "diabetes": diabetes,
        "kidney_disease": kidney_disease,
        "cvd_history": cvd_history,
        "pregnancy": pregnancy,
        "antihypertensive_medication": antihypertensive_medication,
        "province": None if province_label == "不填写" else province_label,
        "residence_area": RESIDENCE_AREA_OPTIONS[residence_area_label],
        "primary_care_preference": PRIMARY_CARE_OPTIONS[primary_care_label],
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

if enable_screening:
    payload["enable_screening_suggestions"] = True
    _rhythm_map = {"规则": "regular", "不规则": "irregular", "未知": "unknown"}
    rhythm_block = {
        "available": rhythm_available,
        "pulse_rhythm": _rhythm_map[pulse_rhythm_label],
        "valid_beat_count": int(valid_beat_count_val),
    }
    if ibi_cv_val:
        rhythm_block["ibi_cv"] = ibi_cv_val
    if ectopic_ratio_val:
        rhythm_block["ectopic_beat_ratio"] = ectopic_ratio_val
    payload["rhythm"] = rhythm_block

    _scg_quality_map = {"好": "good", "中": "fair", "差": "poor", "未知": "unknown"}
    scg_block = {"available": scg_available, "signal_quality_label": _scg_quality_map[scg_quality_label]}
    if pep_ms_val:
        scg_block["pep_ms"] = pep_ms_val
    if lvet_ms_val:
        scg_block["lvet_ms"] = lvet_ms_val
    if s1_s2_ratio_val:
        scg_block["s1_s2_amplitude_ratio"] = s1_s2_ratio_val
    if beat_amplitude_cv_val:
        scg_block["beat_amplitude_cv"] = beat_amplitude_cv_val
    payload["cardiac_vibration"] = scg_block

st.header("个性化解释报告")
action_cols = st.columns([1, 3])
with action_cols[0]:
    run_report = st.button("生成个性化报告", type="primary", use_container_width=True)

if "demo_payload" not in st.session_state or "demo_report" not in st.session_state:
    st.session_state.demo_payload = payload
    with st.spinner("正在生成个性化解释报告..."):
        st.session_state.demo_rules = preview_rules(payload)
        st.session_state.demo_report = generate_report(payload)
        st.session_state.demo_control_report = None
elif run_report:
    st.session_state.demo_payload = payload
    with st.spinner("正在生成 RAG 报告和非 RAG 对照组..."):
        st.session_state.demo_rules = preview_rules(payload)
        st.session_state.demo_report = generate_report(payload)
        st.session_state.demo_control_report = generate_report(payload, report_mode="llm_only")
elif payload != st.session_state.demo_payload:
    st.info("左侧输入已变化，点击“生成个性化报告”更新当前报告。")

rules = st.session_state.demo_rules
report = st.session_state.demo_report
control_report = st.session_state.get("demo_control_report")
display_report_markdown = clean_user_markdown(report.markdown_report)
display_control_markdown = clean_control_markdown(control_report.markdown_report) if control_report else None

signal_tab, report_tab, advisor_tab, compare_tab, evidence_tab, audit_tab, json_tab = st.tabs([
    "PPG 信号参数",
    "用户报告",
    "随访对话",
    "RAG 对照实验",
    "证据依据",
    "过程审计",
    "原始 JSON",
])

with signal_tab:
    st.subheader("PPG 信号参数输入与规则联动")
    st.markdown(
        "同一组血压估算值下，改变信号质量、运动伪影、手指覆盖、接触压力和环境光，"
        "系统会将报告从“可解释”逐步收敛到“先复测”。"
    )

    signal_cols = st.columns(5)
    signal_cols[0].metric("信号质量", f"{payload['measurement']['signal_quality_score']:.2f}", _score_label(payload["measurement"]["signal_quality_score"]))
    signal_cols[1].metric("置信度", f"{payload['measurement']['confidence']:.2f}", _score_label(payload["measurement"]["confidence"]))
    signal_cols[2].metric("运动伪影", f"{payload['measurement']['motion_artifact_score']:.2f}", _score_label(payload["measurement"]["motion_artifact_score"], higher_is_better=False))
    signal_cols[3].metric("手指覆盖", f"{payload['measurement']['finger_coverage_score']:.2f}", _score_label(payload["measurement"]["finger_coverage_score"]))
    signal_cols[4].metric("采集时长", f"{payload['measurement']['capture_duration_sec']} 秒")

    left, right = st.columns([1.35, 1])
    with left:
        st.markdown("### 参数如何影响报告")
        st.table(build_ppg_parameter_rows(payload, rules))
    with right:
        st.markdown("### 规则输出")
        st.write(
            {
                "quality_level": rules.quality.quality_level,
                "is_usable": rules.quality.is_usable,
                "confidence_level": rules.quality.confidence_level,
                "risk_level": rules.risk_level,
                "urgency_level": rules.urgency_level,
            }
        )
        related_intents = ppg_related_intents(rules)
        st.markdown("### PPG 相关检索意图")
        if related_intents:
            for intent in related_intents:
                st.caption(intent)
        else:
            st.caption("当前输入没有额外触发 PPG 特征检索。")

    if rules.quality.warnings:
        st.warning("；".join(rules.quality.warnings))
    else:
        st.success("当前信号参数没有触发明显质量问题；报告仍会保留 PPG/无袖带边界说明。")

    st.markdown("### 故意保留的演示瑕疵")
    st.info(
        "这个网页目前展示的是“参数级输入 + 规则联动 + 报告变化”，还没有接真实 PPG 波形图，"
        "也不会量化每个信号因素对真实血压误差的方向和大小。这个缺口可以作为下一步工作继续汇报。"
    )
    with st.expander("查看发送给后端的 measurement payload"):
        st.json(payload["measurement"])

with report_tab:
    metric_cols = st.columns(3)
    metric_cols[0].metric("本次估算血压", f"{report.input_summary.estimated_sbp}/{report.input_summary.estimated_dbp} mmHg")
    metric_cols[1].metric("信号质量", QUALITY_LABELS.get(report.measurement_status.quality_level, report.measurement_status.quality_level))
    metric_cols[2].metric("风险提示", RISK_LABELS.get(report.risk_assessment.risk_level, report.risk_assessment.risk_level))

    st.markdown(display_report_markdown)

    screening = getattr(report, "screening", None)
    if screening is not None and screening.produced:
        st.markdown("#### 排查建议（结构化）")
        st.caption("以下为“建议进一步排查”的结构化视图：带不确定性、带就医指引、置信度封顶，非诊断。")
        _conf = {"low": "较低", "moderate": "中等"}
        st.table([
            {
                "建议排查": s.label,
                "提示强度": _conf.get(s.confidence, s.confidence),
                "依据": s.rationale,
                "建议动作": s.screening_action,
            }
            for s in screening.suggestions
        ])
    elif screening is not None and screening.requested and not screening.produced:
        st.info("已开启排查建议，但本次信号特征未触发任何排查提示（或处于急症抑制/质量不足）。")

    with st.expander("演示信息：生成状态"):
        mode_label = MODE_LABELS.get(report.generation_mode, "DeepSeek + RAG" if report.generation_mode.startswith("llm_rag_deepseek") else report.generation_mode)
        st.write(mode_label)
    with st.expander("演示信息：规则预览"):
        st.json(rules.model_dump())
    with st.expander("演示信息：安全检查"):
        st.json(report.safety_review.model_dump(by_alias=True) if report.safety_review else {})

    st.download_button("下载 Markdown 报告", display_report_markdown, file_name=f"{report.report_id}.md")
    st.download_button(
        "下载 JSON 报告",
        json.dumps(report.model_dump(by_alias=True), ensure_ascii=False, indent=2),
        file_name=f"{report.report_id}.json",
        mime="application/json",
    )

def _advisor_send(message=None, answers=None, skips=None):
    """One advisor turn; refreshes the open questions kept in session state."""
    response = advisor_turn(
        st.session_state.advisor_session_id,
        AdvisorUserMessage(
            message=message,
            answers=[AdvisorAnswer(**item) for item in (answers or [])],
            skip_question_ids=list(skips or []),
        ),
    )
    st.session_state.advisor_questions = response.questions
    st.session_state.advisor_profile = response.profile.model_dump()


with advisor_tab:
    st.subheader("测量后的随访对话")
    st.markdown(
        "报告只是开始：这里会**循序渐进**地了解测量情境、复核条件、生活习惯与既往情况"
        "（每个问题都解释为什么问、都可以跳过），并把你补充的每条信息转成**有文献依据**的进一步建议。"
        "你也可以随时直接提问。"
    )

    payload_signature = json.dumps(st.session_state.demo_payload, ensure_ascii=False, sort_keys=True, default=str)
    if st.session_state.get("advisor_payload_signature") != payload_signature:
        # New measurement -> stale conversation; ask the user to restart it.
        st.session_state.pop("advisor_session_id", None)
        st.session_state.pop("advisor_questions", None)
        st.session_state.advisor_payload_signature = payload_signature

    if "advisor_session_id" not in st.session_state:
        if st.button("基于当前报告开始随访对话", type="primary"):
            session, opening = create_session(st.session_state.demo_payload, report=report)
            st.session_state.advisor_session_id = session.session_id
            st.session_state.advisor_questions = opening.questions
            st.session_state.advisor_profile = opening.profile.model_dump()
            st.rerun()
        st.info("点击上方按钮开启对话；对话与当前输入的测量结果绑定。")
    else:
        session = get_session_store().get(st.session_state.advisor_session_id)
        if session is None:
            st.session_state.pop("advisor_session_id", None)
            st.warning("会话已失效，请重新开始。")
            st.stop()

        for turn in session.history:
            with st.chat_message("assistant" if turn.role == "advisor" else "user"):
                st.markdown(turn.content)

        questions = st.session_state.get("advisor_questions") or []
        if questions:
            st.markdown("---")
            for question in questions:
                cols = st.columns(max(len(question.options) + 1, 2))
                for index, option in enumerate(question.options):
                    if cols[index].button(option.label, key=f"opt_{question.id}_{option.id}"):
                        _advisor_send(answers=[{"question_id": question.id, "option_id": option.id}])
                        st.rerun()
                if question.skippable and cols[len(question.options)].button(
                    "跳过", key=f"skip_{question.id}"
                ):
                    _advisor_send(skips=[question.id])
                    st.rerun()

        user_text = st.chat_input("输入你的问题或回答……")
        if user_text:
            # Free text that clearly picks an open option becomes a structured answer.
            matched = []
            for question in questions:
                option_id = match_free_text_answer(question, user_text)
                if option_id:
                    matched.append({"question_id": question.id, "option_id": option_id})
                    break
            if user_text.strip() in {"跳过", "跳过吧", "不方便说"} and questions:
                _advisor_send(skips=[question.id for question in questions])
            elif matched:
                _advisor_send(answers=matched)
            else:
                _advisor_send(message=user_text)
            st.rerun()

        with st.expander("已了解的情况（用户画像）"):
            profile = {
                key: value
                for key, value in (st.session_state.get("advisor_profile") or {}).items()
                if value not in (None, [], "")
            }
            st.json(profile or {"说明": "目前还没有补充信息"})


with compare_tab:
    st.subheader("同一份输入：RAG 版 vs 非 RAG 对照组")
    st.markdown(
        "- **RAG 版**：先检索本地文档库，再让模型在证据约束下生成，能展示参考来源和引用质量。\n"
        "- **非 RAG 对照组**：只给模型结构化输入，不给本地证据，也不使用 RAG 版模板骨架，用来展示没有证据约束时的差异。"
    )
    if control_report is None:
        st.info("点击上方“生成个性化报告”，系统会同步生成非 RAG 对照组。")
    else:
        rag_mode = MODE_LABELS.get(report.generation_mode, "DeepSeek + RAG" if report.generation_mode.startswith("llm_rag_deepseek") else report.generation_mode)
        control_mode = MODE_LABELS.get(
            control_report.generation_mode,
            "DeepSeek 非 RAG：仅结构化输入" if control_report.generation_mode.startswith("llm_only_input_deepseek") else control_report.generation_mode,
        )
        st.table(build_compare_rows(report, control_report))
        risk_rows = scan_non_rag_risks(display_control_markdown, control_report)
        st.markdown("### 对照组暴露的问题")
        st.table(risk_rows)
        st.info(
            "展示重点：非 RAG 不一定每句话都错，但它缺少证据锚点和建议绑定。"
            "RAG 策略的价值，是把健康建议拉回可追溯文档库，并交给 Safety Agent 做最终把关。"
        )
        if report.generation_mode.startswith("llm_rag_safety_fallback"):
            st.warning(
                "当前 RAG 版显示的是保守兜底报告：DeepSeek 的 RAG 改写曾触发安全审查，系统自动退回到更保守的报告。"
                "这可以作为 Safety Agent 介入效果展示；若要展示 DeepSeek+RAG 正常文本，可换一个病例或继续收紧提示词。"
            )
        left, right = st.columns(2)
        with left:
            st.markdown(f"### RAG 版\n生成方式：{rag_mode}\n\n证据数量：{len(report.retrieved_evidence)}")
            st.markdown(display_report_markdown)
        with right:
            st.markdown(f"### 非 RAG 对照组\n生成方式：{control_mode}\n\n证据数量：{len(control_report.retrieved_evidence)}")
            st.markdown(display_control_markdown)
        with st.expander("对照组安全审查"):
            st.json(control_report.safety_review.model_dump(by_alias=True) if control_report.safety_review else {})

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
