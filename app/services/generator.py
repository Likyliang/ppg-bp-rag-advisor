from __future__ import annotations

import os
import re
from typing import List
from uuid import uuid4

from app.schemas.measurement import MeasurementPayload
from app.schemas.report import (
    Evidence,
    CitationQuality,
    HealthReport,
    InputSummary,
    MeasurementStatus,
    Recommendations,
    RiskAssessment,
    SafetyAlert,
    UiSummary,
)
from app.schemas.rule_result import RuleResult
from app.services.citations import build_registry, extract_citation_numbers
from app.services.evidence_quality import bind_recommendation_evidence, evaluate_citation_quality
from app.services.medical_copy import clean_citation_fragments, sanitize_medical_copy
from app.services.config_loader import load_yaml_config
from app.services.llm_adapter import (
    LlmGenerationError,
    generate_anthropic_input_only_report,
    generate_anthropic_report_body,
    generate_deepseek_input_only_report,
    generate_deepseek_report_body,
    generate_openai_compatible_input_only_report,
    generate_openai_compatible_report_body,
)


# Provider aliases accepted from LLM_PROVIDER for the third-party
# OpenAI-compatible chat channel (base url / model / key via LLM_*).
OPENAI_COMPATIBLE_PROVIDERS = {"openai_compatible", "openai-compatible", "third_party", "thirdparty"}


DISCLAIMER = (
    "本报告仅供个人健康趋势参考，不能替代医生诊断、治疗决策，也不能替代规范血压测量。"
    "如有不适或多次复核仍异常，请咨询专业医务人员。"
)

NO_EMERGENCY_SYMPTOM_TEXT = (
    "目前没有填写胸痛、气短、肢体无力、视物改变、说话困难或严重头痛等需要立刻处理的症状；"
    "如果之后出现这些不适，请直接拨打 120 或前往急诊。"
)


def _category_text(category: str) -> str:
    mapping = {
        "normal_reference_range": "处于常见正常参考范围",
        "elevated_reference_range": "处于偏高趋势参考范围",
        "stage_1_reference_range": "处于偏高范围参考值",
        "stage_2_reference_range": "处于明显偏高范围参考值",
        "severe_range": "处于严重偏高范围参考值",
        "not_interpretable_low_quality": "因信号质量不足，本次不做范围解释",
        "unavailable": "缺少估算血压值，无法进行范围解释",
    }
    return mapping.get(category, "需要结合复测进一步观察")


def _risk_explanation(rule_result: RuleResult) -> str:
    if rule_result.emergency:
        reasons = "、".join(rule_result.emergency_reasons)
        return f"{reasons}。请优先寻求当地急救或紧急医疗帮助；在中国大陆可拨打 120 或前往急诊。"
    if not rule_result.quality.is_usable:
        return "本次信号质量不足，建议重新采集并使用经过验证的上臂式电子血压计复核。"
    if rule_result.estimated_bp_category == "severe_range":
        return "本次估算值处于严重偏高参考范围，即使没有急症症状，也建议尽快用规范设备复核并咨询医生。"
    if rule_result.estimated_bp_category in {"stage_1_reference_range", "stage_2_reference_range"}:
        return "本次估算值处于偏高参考范围，建议复测并结合连续记录判断趋势。"
    if rule_result.estimated_bp_category == "elevated_reference_range":
        return "本次估算值提示可能存在偏高趋势，可通过规范家庭监测和生活方式管理继续观察。"
    return "目前没有看到需要立刻处理的急症信息，仍建议关注长期趋势而非单次估算值。"


def _one_sentence_takeaway(rule_result: RuleResult) -> str:
    if rule_result.emergency:
        return "结论：现在先处理急症风险，立即拨打 120 或前往急诊；不要等待小程序复测结果。"
    if not rule_result.quality.is_usable:
        return "结论：这次信号质量不够，先别急着看血压高低；重新采集一次，再用上臂式血压计复核。"
    if rule_result.estimated_bp_category == "severe_range":
        return "结论：这次估算值已到严重偏高参考范围，请尽快用上臂式血压计复核；若复核仍很高或伴不适，立即就医。"
    if rule_result.estimated_bp_category == "stage_2_reference_range":
        return "结论：这次数值明显偏高，先别给自己下诊断；今天先用上臂式血压计复核，后续若多次仍偏高，再带记录去社区、乡镇卫生院或门诊咨询。"
    if rule_result.estimated_bp_category == "stage_1_reference_range":
        return "结论：这次有偏高迹象，先用上臂式血压计复核并连续记录；如果后续多次仍偏高，再带记录咨询医生。"
    if rule_result.estimated_bp_category == "elevated_reference_range":
        return "结论：这次更像偏高趋势，先做规范家庭复核和连续记录；暂时不要只凭一次估算下判断。"
    return "结论：这次未提示明显偏高，继续定期观察；如果后续趋势升高，再按报告建议复核。"


def _recommendations(rule_result: RuleResult) -> Recommendations:
    if rule_result.emergency:
        return Recommendations(
            remeasurement=["如条件允许，可在等待医疗帮助时使用规范血压计复核，但不要因此延误急救。"],
            device_advice=["PPG 估算值不能替代规范设备，严重症状需要优先处理。"],
            lifestyle=[],
            medical_consultation=["立即寻求当地急救或紧急医疗服务；在中国大陆可拨打 120 或前往急诊。"],
        )

    remeasurement: List[str] = []
    device: List[str] = ["使用经过验证的上臂式电子血压计进行复核。"]
    lifestyle: List[str] = []
    consultation: List[str] = []

    if "remeasurement" in rule_result.recommendation_intents:
        remeasurement.extend(["安静休息至少 5 分钟后重新测量。", "连续记录一段时间观察趋势，避免只看单次估算值。"])
    if "signal_quality_improvement" in rule_result.recommendation_intents:
        remeasurement.extend(["重新采集时保持手指覆盖摄像头、身体静止，避免强光干扰。"])
    if "home_bp_monitoring" in rule_result.recommendation_intents:
        remeasurement.append("按固定时间记录家庭血压，并保留记录供医生参考。")
    if "lifestyle" in rule_result.recommendation_intents or "healthy_lifestyle" in rule_result.recommendation_intents:
        lifestyle.extend(["减少钠盐摄入。", "保持规律运动和体重管理。", "戒烟限酒，保证睡眠。", "管理压力，避免过量咖啡因。"])
    if "medical_consultation" in rule_result.recommendation_intents:
        consultation.append("若多次规范复核仍偏高，建议带记录到社区卫生服务中心、乡镇卫生院、家庭医生团队或医院门诊咨询。")
    if rule_result.special_population:
        reasons = "、".join(rule_result.special_population_reasons)
        consultation.append(f"因存在{reasons}，建议采取更保守的复核和就医策略。")
        if "正在使用降压药" in rule_result.special_population_reasons:
            consultation.append("正在使用降压药时，请带连续复核记录咨询医生，药物相关问题由医生处理。")
    if rule_result.estimated_bp_category == "severe_range":
        consultation.append("若复核仍达到严重偏高范围，或出现胸痛、气短、肢体无力、视物改变、说话困难等症状，请立即寻求急救。")

    return Recommendations(
        remeasurement=list(dict.fromkeys(remeasurement)),
        device_advice=list(dict.fromkeys(device)),
        lifestyle=list(dict.fromkeys(lifestyle)),
        medical_consultation=list(dict.fromkeys(consultation)),
    )


def _safety_alert(rule_result: RuleResult) -> SafetyAlert:
    if rule_result.emergency:
        return SafetyAlert(
            emergency=True,
            message="可能存在紧急风险：估算值达到严重偏高范围且伴随急症相关症状，请立即寻求当地急救或紧急医疗帮助；在中国大陆可拨打 120 或前往急诊。",
        )
    return SafetyAlert(
        emergency=False,
        message=NO_EMERGENCY_SYMPTOM_TEXT,
    )


def _active_symptom_labels(payload: MeasurementPayload) -> List[str]:
    labels = load_yaml_config("config/safety_terms.yaml").get("symptom_labels", {})
    active: List[str] = []
    for field_name, label in labels.items():
        if bool(getattr(payload.symptoms, field_name, False)):
            active.append(label)
    return active


def _profile_lines(payload: MeasurementPayload, rule_result: RuleResult) -> List[str]:
    profile = payload.user_profile
    lines: List[str] = []
    if profile.age is not None:
        age_note = "，属于更保守解释人群" if profile.age >= 65 else ""
        lines.append(f"年龄：{profile.age} 岁{age_note}。")

    factors = []
    if profile.pregnancy:
        factors.append("妊娠或可能妊娠")
    if profile.diabetes:
        factors.append("糖尿病")
    if profile.kidney_disease:
        factors.append("慢性肾脏病")
    if profile.cvd_history:
        factors.append("既往心血管病史")
    if profile.antihypertensive_medication:
        factors.append("正在使用降压药")

    if factors:
        lines.append(f"已填报背景因素：{'、'.join(factors)}；因此报告采用更保守的复核和就医沟通口径。")
    elif not rule_result.special_population:
        lines.append("未填报妊娠、糖尿病、慢性肾脏病、既往心血管病史或正在使用降压药等需额外保守处理的因素。")
    location_parts = []
    if profile.province:
        location_parts.append(f"地区：{profile.province}")
    if profile.residence_area == "urban":
        location_parts.append("居住场景：城市/城镇")
    elif profile.residence_area == "rural":
        location_parts.append("居住场景：乡村/县域")
    if location_parts:
        lines.append("中国使用场景：" + "；".join(location_parts) + "。这些信息只用于本地化表达，不参与诊断。")
    return lines


def _join_warnings(warnings: List[str]) -> str:
    return "；".join(item.rstrip("。；; ") for item in warnings if item).strip()


def _reason_lines(payload: MeasurementPayload, report: HealthReport, rule_result: RuleResult) -> List[str]:
    summary = report.input_summary
    if rule_result.emergency:
        lines = [
            (
                f"这次估算值是 {summary.estimated_sbp}/{summary.estimated_dbp} mmHg，"
                f"属于“{_category_text(rule_result.estimated_bp_category)}”，并且你勾选了急症相关症状；"
                "现在最重要的是先拨打 120 或前往急诊，不要等待小程序复测。"
            ),
            rule_result.quality.explanation,
        ]
    else:
        lines = [
            (
                f"这次估算值是 {summary.estimated_sbp}/{summary.estimated_dbp} mmHg，"
                f"属于“{_category_text(rule_result.estimated_bp_category)}”，所以建议先用上臂式血压计复核。"
            ),
            rule_result.quality.explanation,
        ]
    if rule_result.quality.warnings:
        lines.append(f"测量质量提醒：{_join_warnings(rule_result.quality.warnings)}。")

    active_symptoms = _active_symptom_labels(payload)
    if rule_result.emergency:
        lines.append(f"你勾选了 {'、'.join(active_symptoms)}，且估算值很高，因此报告把急救提醒放在最前面。")
    elif active_symptoms:
        lines.append(f"你填写了 {'、'.join(active_symptoms)}；这些信息会让报告更保守。如果症状持续、加重，或出现胸痛、气短、肢体无力、视物改变、说话困难、严重头痛，请直接拨打 120 或前往急诊。")
    else:
        lines.append(NO_EMERGENCY_SYMPTOM_TEXT)

    lines.extend(_profile_lines(payload, rule_result))
    if rule_result.emergency:
        lines.append("结合你选择的中国大陆使用场景，今天的主要路径是 120 或急诊，后续稳定后再做连续记录和门诊随访。")
    elif payload.guideline_region == "AHA":
        lines.append("你选择了中外指南对照场景，日常面向中国用户使用时建议切回中国大陆场景。")
    else:
        lines.append("结合你选择的中国大陆使用场景，报告会把复测、连续记录和基层或门诊沟通作为主要下一步。")
    return lines


def _why_lines(payload: MeasurementPayload, rule_result: RuleResult) -> List[str]:
    lines: List[str] = []
    if rule_result.emergency:
        lines.append("因为估算值很高且伴随急症相关症状，报告优先提示拨打 120 或前往急诊，复测和记录都不能排在急救前面。")
    elif not rule_result.quality.is_usable:
        lines.append("本次质量不足，所以报告不展开血压范围解释，重点变为重新采集和规范设备复核。")
    elif rule_result.estimated_bp_category in {"stage_1_reference_range", "stage_2_reference_range", "severe_range"}:
        lines.append("因为估算值进入偏高或严重偏高参考范围，报告优先建议复测、连续记录和医生沟通。")
    elif rule_result.estimated_bp_category == "elevated_reference_range":
        lines.append("因为估算值只是偏高趋势，报告重点放在家庭监测和生活方式观察，而不是就医紧急化。")
    else:
        lines.append("因为未进入偏高参考范围，报告重点放在趋势观察和保持健康生活方式。")

    if "lifestyle" in rule_result.recommendation_intents or "healthy_lifestyle" in rule_result.recommendation_intents:
        lines.append("生活方式内容只作为通用健康教育，用于减盐、运动、体重和睡眠等长期管理，不承诺个体降压效果。")
    if payload.user_profile.antihypertensive_medication:
        lines.append("已填报正在使用降压药，因此报告只提示带记录咨询医生，不给药物处理方案。")
    if rule_result.special_population:
        lines.append("存在特殊背景因素时，单次 PPG 估算更不能单独解释，应更依赖规范血压计复核和专业评估。")
    return lines


def _append_recommendation_group(
    lines: List[str], title: str, items: List[str], cite: str = ""
) -> None:
    if not items:
        return
    lines.append(f"### {title}{cite}")
    for item in items:
        lines.append(f"- {item}")


def _primary_care_name(preference: str) -> str:
    mapping = {
        "community_health_center": "社区卫生服务中心或家庭医生团队",
        "township_health_center": "乡镇卫生院或村卫生室上级转诊渠道",
        "hospital_outpatient": "医院门诊",
    }
    return mapping.get(preference, "社区卫生服务中心、乡镇卫生院、家庭医生团队或医院门诊")


def _china_context_lines(payload: MeasurementPayload, rule_result: RuleResult, uses_rag: bool = True) -> List[str]:
    if payload.guideline_region == "AHA":
        return ["当前选择 AHA/ACC 科研对照语境，报告不会优先使用中国本地路径；面向中国用户正式展示时建议切回中国大陆（CN）。"]

    profile = payload.user_profile
    primary_care = _primary_care_name(profile.primary_care_preference)
    if uses_rag:
        lines = [
            "如果只是一次估算偏高，先不要给自己下结论；更重要的是用上臂式血压计复核，并把结果连续记录下来。",
            f"如果多次规范复核仍偏高，可带家庭血压记录到{primary_care}咨询；本报告只帮助整理趋势和问题，不替代医生判断。",
            "家庭记录建议写清日期、时间、收缩压/舒张压、心率、测量设备和当时状态，方便基层随访或门诊沟通。",
        ]
    else:
        lines = [
            "这是非 RAG 对照报告：没有读取本地文档库，也不展示参考来源，只用于和 RAG 版比较。",
            f"即使是对照报告，仍建议多次规范复核后再带记录到{primary_care}咨询；本报告不替代医生判断。",
            "正式演示或面向用户展示时，建议以 RAG 版为准，因为它能显示证据来源和引用质量。",
        ]
    if profile.residence_area == "rural":
        lines.append("乡村或县域场景下，可优先考虑乡镇卫生院、村医随访和县级医院门诊之间的转诊路径。")
    elif profile.residence_area == "urban":
        lines.append("城市或城镇场景下，可优先考虑社区卫生服务中心、家庭医生团队或医院门诊。")
    if rule_result.emergency:
        lines.append("若触发急症相关症状，优先拨打 120 或前往急诊，不要等待小程序或家庭复测结果。")
    return lines


def _plain_language_lines(report: HealthReport, rule_result: RuleResult, payload: MeasurementPayload, uses_rag: bool = True) -> List[str]:
    lines = [
        "PPG 可以理解为用手指摄像头的光信号来估算血压趋势；它容易受手指按压力度、光线、静止程度和算法置信度影响，所以不能当作最终血压值。",
        "规范复核指的是用经过验证的上臂式电子血压计，在安静休息后按说明测量；这样得到的连续记录更适合拿给医生判断。",
    ]
    if rule_result.emergency:
        lines.append("如果同时有胸痛、气短、肢体无力、说话困难、视物改变等症状，先处理症状并寻求急救，PPG 或家庭复测不能排在急救前面。")
    elif not rule_result.quality.is_usable:
        lines.append("这次最重要的不是血压数字，而是采集质量不足：先重新测，等信号质量可靠后再看趋势。")
    elif rule_result.estimated_bp_category in {"stage_1_reference_range", "stage_2_reference_range", "severe_range"}:
        lines.append("如果多次规范复核仍偏高，把日期、时间、血压值和当时状态记录下来，再和医生沟通会更有帮助。")
    else:
        lines.append("如果后续多次记录都稳定，可以继续保持监测；如果趋势变高，再按报告建议复核和咨询。")

    if payload.user_profile.antihypertensive_medication:
        lines.append("已经在用降压药时，不要根据本报告自行改变用药方案；更合适的做法是带复核记录咨询医生。")
    if report.recommendations.lifestyle:
        lines.append("生活方式建议是长期健康教育，比如少盐、规律运动、体重管理和睡眠管理，不是立刻降压的承诺。")
    if payload.guideline_region != "AHA" and uses_rag:
        lines.append("在中国大陆日常就医路径里，更实用的做法是先复核、再记录、再带记录去基层或门诊沟通。")
    return lines


def _markdown(report: HealthReport, rule_result: RuleResult, payload: MeasurementPayload, uses_rag: bool = True) -> str:
    summary = report.input_summary
    registry = build_registry(report.retrieved_evidence)
    cite_bp = registry.cite("bp_category_reference") if rule_result.quality.is_usable and not rule_result.emergency else ""
    cite_ppg = registry.cite("cuffless_ppg_limitations", "signal_quality")
    cite_emergency = registry.cite("emergency_alert")
    lines: List[str] = []
    quality_parts = []
    if summary.signal_quality_score is not None:
        quality_parts.append(f"信号质量分 {summary.signal_quality_score}")
    if summary.confidence is not None:
        quality_parts.append(f"算法置信度 {summary.confidence}")
    if summary.capture_duration_sec is not None:
        quality_parts.append(f"采集时长 {summary.capture_duration_sec} 秒")
    if summary.motion_artifact_score is not None and summary.motion_artifact_score >= 0.45:
        quality_parts.append("可能有手指移动影响")
    if summary.finger_coverage_score is not None and summary.finger_coverage_score < 0.75:
        quality_parts.append("手指覆盖可能不够稳定")
    if summary.contact_pressure_level not in {"", "normal", "unknown"}:
        quality_parts.append("手指按压力度可能影响波形")
    if summary.ambient_light_level not in {"", "normal", "unknown"}:
        quality_parts.append("环境光可能影响采集")
    if summary.ppg_source and summary.ppg_source != "unknown":
        source_text = "手指摄像头" if summary.ppg_source == "camera_finger" else summary.ppg_source
        quality_parts.append(f"采集方式 {source_text}")
    if report.safety_alert.emergency:
        lines.append("## 可能存在紧急风险")
        lines.append(report.safety_alert.message + cite_emergency)
        lines.append("")

    lines.extend(
        [
            "## 先看结论",
            (
                f"这次小程序给出的估算值是 "
                f"{summary.estimated_sbp}/{summary.estimated_dbp} mmHg，"
                f"提示{_category_text(rule_result.estimated_bp_category)}。{cite_bp}"
            ),
            f"这次采集的信息包括：{'；'.join(quality_parts)}。" if quality_parts else "这次测量信息还不完整。",
            "不要将本次结果作为诊断结论。它更像一次提醒：需要用规范血压计复核，再结合连续记录判断趋势。",
            "",
            "## 现在最该做什么",
            _one_sentence_takeaway(rule_result),
            "",
            "## 为什么这样提醒你",
        ]
    )
    lines.extend(f"- {item}" for item in _reason_lines(payload, report, rule_result))
    lines.extend(
        [
            "",
            "## 怎么看这次测量",
            report.measurement_status.quality_explanation,
            report.risk_assessment.explanation,
            "",
            "## 建议背后的原因",
        ]
    )
    lines.extend(f"- {item}" for item in _why_lines(payload, rule_result))
    lines.extend(
        [
            "",
            "## 接下来怎么做",
        ]
    )
    medical_cite = cite_emergency if rule_result.emergency else registry.cite(
        "home_bp_monitoring", "special_population"
    )
    _append_recommendation_group(
        lines, "复测与记录", report.recommendations.remeasurement,
        registry.cite("remeasurement", "home_bp_monitoring", "signal_quality"),
    )
    _append_recommendation_group(
        lines, "设备复核", report.recommendations.device_advice,
        registry.cite("device_advice", "cuffless_ppg_limitations"),
    )
    _append_recommendation_group(
        lines, "生活方式", report.recommendations.lifestyle, registry.cite("lifestyle"),
    )
    _append_recommendation_group(
        lines, "就医沟通", report.recommendations.medical_consultation, medical_cite,
    )
    lines.extend(["", "## 在国内可以怎么做"])
    lines.extend(f"- {item}" for item in _china_context_lines(payload, rule_result, uses_rag=uses_rag))
    lines.extend(["", "## 几个容易误解的点"])
    plain_lines = _plain_language_lines(report, rule_result, payload, uses_rag=uses_rag)
    if plain_lines and cite_ppg:
        plain_lines[0] = plain_lines[0] + cite_ppg
    lines.extend(f"- {item}" for item in plain_lines)

    body = "\n".join(lines)
    final = registry.finalize(body) if registry.has_evidence else None
    if final is not None:
        body = final.body
        report.references = final.entries
    tail = _reference_tail_lines(report, final, uses_rag=uses_rag)
    return body + "\n" + "\n".join(tail)


def _reference_tail_lines(report: HealthReport, final, uses_rag: bool = True, registry=None) -> List[str]:
    """Compose 参考文献 / 参考依据说明 / 免责声明 from finalized citations.

    The bibliography lists exactly the sources cited in the body, numbered by
    first appearance — the numeric-citation convention — instead of dumping the
    whole retrieval pool. When ``final`` is None but ``registry`` is given
    (citation-enforcement OFF / S3), the full ordered reference list is emitted
    with the registry's original source-dedup numbering.
    """
    lines: List[str] = []
    cited_count = final.cited_count if final is not None else 0
    reference_lines = []
    if final is not None and final.references:
        reference_lines = final.references
    elif registry is not None and registry.has_evidence:
        reference_lines = registry.references_markdown()
        cited_count = len(reference_lines)
    if reference_lines:
        lines.extend(
            [
                "",
                "## 参考文献",
                "正文中的 [n] 标注按首次出现顺序编号，对应下列经治理的权威来源；每条建议只引用其被授权用途范围内的资料。",
                "",
            ]
        )
        for index, reference_line in enumerate(reference_lines):
            if index:
                lines.append("")
            lines.append(reference_line)

    evidence_count = len(report.retrieved_evidence)
    grounding_text = "是" if report.citation_quality.recommendation_grounding_rate >= 1.0 else "部分建议需要继续补充资料"
    lines.extend(
        [
            "",
            "## 参考依据说明",
            (
                f"本报告基于 {evidence_count} 条本地治理知识库资料，正文实际引用其中 {cited_count} 篇来源，并在正文中以 [n] 形式标注引用。"
                if uses_rag
                else "本对照报告未使用本地文档库资料，因此正文不含文献引用。"
            ),
            f"主要建议是否能对应到资料来源：{grounding_text}。",
            f"涉及安全提醒时是否优先使用高可信来源：{'是' if report.citation_quality.high_trust_sensitive_uses else '否'}。",
        ]
    )

    lines.extend(["", "## 免责声明", report.disclaimer])
    return lines


def _split_report_tail(markdown_report: str) -> tuple[str, str]:
    tail_markers = ["\n## 参考文献", "\n## 参考来源", "\n## 参考依据说明", "\n## 引用质量", "\n## 免责声明"]
    indexes = [markdown_report.find(marker) for marker in tail_markers if markdown_report.find(marker) >= 0]
    if not indexes:
        return markdown_report.strip(), ""
    split_at = min(indexes)
    return markdown_report[:split_at].strip(), markdown_report[split_at:].strip()


def _with_replaced_body(markdown_report: str, body: str) -> str:
    _, tail = _split_report_tail(markdown_report)
    body = body.strip()
    if tail:
        return f"{body}\n\n{tail}"
    return body


def _strip_llm_preface(body: str) -> str:
    body = body.strip()
    first_heading = re.search(r"(?m)^#{1,3}\s+", body)
    if first_heading and first_heading.start() > 0:
        body = body[first_heading.start():]
    return re.sub(r"\A[-*_]{3,}\s*", "", body).strip()


def _sanitize_llm_body(body: str) -> str:
    body = _strip_llm_preface(body)
    replacements = {
        "当前未达到紧急就医标准": NO_EMERGENCY_SYMPTOM_TEXT,
        "未达到紧急就医标准": NO_EMERGENCY_SYMPTOM_TEXT,
        "当前无需紧急处理": NO_EMERGENCY_SYMPTOM_TEXT,
        "无需紧急处理": NO_EMERGENCY_SYMPTOM_TEXT,
        "本次不属于紧急情况": NO_EMERGENCY_SYMPTOM_TEXT,
        "不属于紧急情况": NO_EMERGENCY_SYMPTOM_TEXT,
        "本次结果不视为紧急情况": NO_EMERGENCY_SYMPTOM_TEXT,
        "本次不视为紧急情况": NO_EMERGENCY_SYMPTOM_TEXT,
        "不视为紧急情况": NO_EMERGENCY_SYMPTOM_TEXT,
        "这次不是紧急情况（未触发本系统急症提醒规则）": NO_EMERGENCY_SYMPTOM_TEXT,
        "本次不是紧急情况（未触发本系统急症提醒规则）": NO_EMERGENCY_SYMPTOM_TEXT,
        "不是紧急情况（未触发本系统急症提醒规则）": NO_EMERGENCY_SYMPTOM_TEXT,
        "本次不是紧急情况": NO_EMERGENCY_SYMPTOM_TEXT,
        "不是紧急情况": NO_EMERGENCY_SYMPTOM_TEXT,
        "未触发本系统急症提醒规则（未触发本系统急症提醒规则）": NO_EMERGENCY_SYMPTOM_TEXT,
        "本次未触发本系统急症提醒规则": NO_EMERGENCY_SYMPTOM_TEXT,
        "当前未触发本系统急症提醒规则": NO_EMERGENCY_SYMPTOM_TEXT,
        "未触发本系统急症提醒规则": NO_EMERGENCY_SYMPTOM_TEXT,
        "本系统未触发急症提醒": NO_EMERGENCY_SYMPTOM_TEXT,
        "系统没有触发紧急提醒": NO_EMERGENCY_SYMPTOM_TEXT,
        "没有触发紧急提醒": NO_EMERGENCY_SYMPTOM_TEXT,
        "没有被归为紧急情况": NO_EMERGENCY_SYMPTOM_TEXT,
        "一次估算偏高不代表什么": "一次估算偏高不能说明最终血压情况",
        "不等于确诊高血压": "不等于诊断结果",
        "不能确诊高血压": "不能作为诊断结果",
        "是确认血压水平的金标准": "是复核血压水平的重要依据",
        "中国 2 级高血压参考范围": "中国血压分级中的明显偏高参考范围",
        "中国2级高血压参考范围": "中国血压分级中的明显偏高参考范围",
        "不要自行停药或改变现有药物（如有用药）": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自行停药或改变现有药物": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自行停药、加药或减药": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自行停药": "用药问题请咨询医生；本报告不提供用药方案",
        "暂不需要打120，因为你没有报告胸痛、气短、肢体无力、视物改变、说话困难或严重头痛这些紧急症状。": (
            "如果出现胸痛、气短、肢体无力、视物改变、说话困难或严重头痛，请立即拨打 120 或前往急诊。"
        ),
        "暂不需要打120": "如果出现急症相关症状，请立即拨打 120 或前往急诊",
        "不需要打120": "如果出现急症相关症状，请立即拨打 120 或前往急诊",
        "无需打120": "如果出现急症相关症状，请立即拨打 120 或前往急诊",
        "暂时不需要去急诊，也不要自己调整任何药物": "如果出现急症相关症状，请立即拨打 120 或前往急诊；用药问题请咨询医生",
        "暂时不需要去急诊，也不要自行调整任何药物": "如果出现急症相关症状，请立即拨打 120 或前往急诊；用药问题请咨询医生",
        "暂时不需要去急诊": "如果出现急症相关症状，请立即拨打 120 或前往急诊",
        "暂时不需要急诊": "如果出现急症相关症状，请立即拨打 120 或前往急诊",
        "不需要去急诊": "如果出现急症相关症状，请立即拨打 120 或前往急诊",
        "无需去急诊": "如果出现急症相关症状，请立即拨打 120 或前往急诊",
        "不要自己调整任何用药": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自行调整任何用药": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自己调整任何药物": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自行调整任何药物": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自己改药": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自行改药": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自行加药或减药": "用药问题请咨询医生；本报告不提供用药方案",
        "不要自己加药或减药": "用药问题请咨询医生；本报告不提供用药方案",
        "如涉及用药问题，请咨询医生、加药或减药": "用药问题请咨询医生；本报告不提供用药方案",
        "正在服用降压药": "正在使用降压药",
        "正在吃降压药": "正在使用降压药",
        "是高血压诊断和家庭管理的推荐工具": "是血压复核和家庭记录的重要工具",
        "每周至少 5 次中等强度运动": "保持规律运动",
        "每周至少5次中等强度运动": "保持规律运动",
        "## 一句话结论": "## 现在最该做什么",
        "这次估算值偏高，重点不是给自己下诊断，而是用上臂式血压计规范复核，并连续记录趋势。": (
            "结论：这次数值明显偏高，先别给自己下诊断；今天先用上臂式血压计复核，"
            "后续若多次仍偏高，再带记录去社区、乡镇卫生院或门诊咨询。"
        ),
        "连续几天、每天早晚都复测": "按说明书规范复测并连续记录",
        "连续测 3 天": "连续记录一段时间",
        "连续测3天": "连续记录一段时间",
        "连续记录几天": "连续记录一段时间",
        "连续多天、固定时间记录家庭血压（比如按固定时间记录）": "按固定时间连续记录家庭血压",
        "连续多天、固定时间（按自己方便且相对固定的时间）": "连续记录一段时间",
        "每天早晚各一次": "按固定时间记录",
        "早晚各一次": "按固定时间记录",
        "按固定时间（比如早上起床排尿后、晚上睡觉前）": "按自己方便且相对固定的时间",
        "按固定时间（比如早上起床排尿后、晚上睡前）": "按自己方便且相对固定的时间",
        "按固定时间（比如早上起床排尿后、晚饭前）": "按自己方便且相对固定的时间",
        "比如早上起床排尿后、晚饭前": "按自己方便且相对固定的时间",
        "早上起床排尿后、晚饭前": "自己方便且相对固定的时间",
        "比如早上起床排尿后、晚上睡觉前": "按自己方便且相对固定的时间",
        "早上起床排尿后、晚上睡觉前": "自己方便且相对固定的时间",
        "比如早上起床排尿后、晚上睡前": "按自己方便且相对固定的时间",
        "早上起床排尿后、晚上睡前": "自己方便且相对固定的时间",
        "比如早起后、晚饭前": "按自己方便且相对固定的时间",
        "早起后、晚饭前": "自己方便且相对固定的时间",
        "比如早起后安静时": "按自己方便且相对固定的时间",
        "早起后安静时": "自己方便且相对固定的时间",
        "比如早晨和睡前": "按自己方便且相对固定的时间",
        "早晨和睡前": "自己方便且相对固定的时间",
        "比如早晨或睡前": "按自己方便且相对固定的时间",
        "早晨或睡前": "自己方便且相对固定的时间",
        "比如早、晚固定时间测几天": "连续记录一段时间",
        "早、晚固定时间测几天": "连续记录一段时间",
        "比如早上起床后、晚上睡前": "按自己方便且相对固定的时间",
        "早上起床后、晚上睡前": "自己方便且相对固定的时间",
        "比如早上起床后、晚上睡觉前": "按自己方便且相对固定的时间",
        "早上起床后、晚上睡觉前": "自己方便且相对固定的时间",
        "如早晨起床后、晚上睡前": "按自己方便且相对固定的时间",
        "早晨起床后、晚上睡前": "自己方便且相对固定的时间",
        "比如早晚固定时间": "按固定时间",
        "连续记录 3~5 天": "连续记录一段时间",
        "连续记录3~5天": "连续记录一段时间",
        "连续记录三到五天": "连续记录一段时间",
        "每天固定时间测量": "按自己方便且相对固定的时间测量",
        "每天固定时间记录": "按自己方便且相对固定的时间记录",
        "每天固定时间": "按自己方便且相对固定的时间",
        "每天在固定时间（按自己方便且相对固定的时间）": "按自己方便且相对固定的时间",
        "每天在固定时间": "按自己方便且相对固定的时间",
        "、是否服药": "",
        "是否服药": "当时状态",
        "、是否吃药": "",
        "是否吃药": "当时状态",
        "如空腹、服药后等": "如刚活动后或安静休息后",
        "服药后": "按当时状态",
        "坚持下来一定有用": "长期坚持通常有帮助",
        "收缩压≥140 mmHg 或舒张压≥90 mmHg": "复核结果仍持续偏高",
        "收缩压 ≥140 mmHg 或舒张压 ≥90 mmHg": "复核结果仍持续偏高",
        "≥140/90 mmHg": "仍持续偏高",
        "<130/80 mmHg": "常见正常参考范围",
        "袖带下缘距肘窝 2~3 厘米，松紧以能插入 1~2 指为宜": "按设备说明书佩戴袖带",
        "袖带下缘距肘窝2~3厘米，松紧以能插入1~2指为宜": "按设备说明书佩戴袖带",
        "马上吃药或调整生活方式": "自己处理",
        "马上吃药": "自己处理",
        "但不算高质量信号，只能当作趋势参考": "但仍只能当作趋势参考",
        # Newly-introduced sleep-hour / duration / prep-step details that the
        # prompt forbids but DeepSeek still occasionally adds.
        "保证每晚 7-8 小时睡眠": "保持规律作息",
        "保证每晚7-8小时睡眠": "保持规律作息",
        "每晚 7-8 小时睡眠": "规律作息",
        "每晚7-8小时睡眠": "规律作息",
        "每晚 7~8 小时睡眠": "规律作息",
        "每晚7~8小时睡眠": "规律作息",
        "保证 7-8 小时睡眠": "保持规律作息",
        "保证7-8小时睡眠": "保持规律作息",
        "7-8 小时睡眠": "规律作息",
        "7-8小时睡眠": "规律作息",
        "7～8小时睡眠": "规律作息",
        "保证充足睡眠": "保持规律作息",
        "充足睡眠": "规律作息",
        "增加蔬菜水果": "均衡饮食",
        "多吃蔬菜水果": "均衡饮食",
        "增加蔬菜和水果": "均衡饮食",
        "连续记录一周": "连续记录一段时间",
        "连续测一周": "连续记录一段时间",
        "记录一周": "连续记录一段时间",
        "持续一周": "连续记录一段时间",
        "连续一周": "连续记录一段时间",
        "连续两周": "连续记录一段时间",
        "连续记录两周": "连续记录一段时间",
        "测量前半小时不吸烟、不喝咖啡，排空膀胱，坐靠背椅，双脚平放": "按设备说明书规范测量",
        "测量前半小时不吸烟、不喝咖啡": "按设备说明书规范测量",
        "测量前 30 分钟不吸烟、不喝咖啡": "按设备说明书规范测量",
        "测量前30分钟不吸烟、不喝咖啡": "按设备说明书规范测量",
        "排空膀胱，坐靠背椅，双脚平放": "按说明书规范姿势测量",
        "坐靠背椅，双脚平放": "按说明书规范姿势测量",
        "双脚平放": "按说明书规范姿势",
        "排空膀胱": "按说明书规范准备",
    }
    for old, new in replacements.items():
        body = body.replace(old, new)
    body = body.replace(f"{NO_EMERGENCY_SYMPTOM_TEXT}（{NO_EMERGENCY_SYMPTOM_TEXT}）", NO_EMERGENCY_SYMPTOM_TEXT)
    body = re.sub(rf"(?:{re.escape(NO_EMERGENCY_SYMPTOM_TEXT)}[。；;，,\s]*)+", NO_EMERGENCY_SYMPTOM_TEXT, body)
    body = body.replace("连续多天、固定时间（按自己方便且相对固定的时间）", "连续记录一段时间")
    body = body.replace("连续多天、固定时间（自己方便且相对固定的时间）", "连续记录一段时间")
    body = body.replace("连续记录一段时间测量", "连续记录一段时间")
    body = body.replace(f"{NO_EMERGENCY_SYMPTOM_TEXT}- ", f"{NO_EMERGENCY_SYMPTOM_TEXT}\n- ")
    body = re.sub(r"([。！？])-\s+", r"\1\n- ", body)
    body = body.replace("。。", "。").replace("；。", "。")
    unsafe_line_pattern = re.compile(
        r"停药|停用降压药|调整用药|调整.*用药|调整.*药物|调药|改药|加药|减药|增加剂量|减少剂量|自行增加.*药|自行.*剂量|自行服用|建议服用.*药|马上吃药"
        r"|没有问题，不用复测|不用复测|无需就医|不用就医|无需.*复核|不用急救"
        r"|不需要.*120|暂不需要.*120|无需.*120|不用.*120|不需要.*急诊|暂时不需要.*急诊|无需.*急诊|不用.*急诊"
        r"|可以替代血压计|可以替代规范血压测量|PPG\s*估算值很准确|保证准确|保证.*降低血压"
    )
    medication_line_pattern = re.compile(
        r"停药|停用降压药|调整用药|调整.*用药|调整.*药物|调药|改药|加药|减药|增加剂量|减少剂量|自行增加.*药|自行.*剂量|自行服用|建议服用.*药|马上吃药"
    )
    emergency_reassurance_line_pattern = re.compile(
        r"无需就医|不用就医|不用急救|不需要.*120|暂不需要.*120|无需.*120|不用.*120|不需要.*急诊|暂时不需要.*急诊|无需.*急诊|不用.*急诊"
    )
    diagnostic_line_pattern = re.compile(r"没有问题，不用复测|不用复测|无需.*复核")
    device_line_pattern = re.compile(r"可以替代血压计|可以替代规范血压测量|PPG\s*估算值很准确|保证准确|保证.*降低血压")
    audience_unfriendly_line_pattern = re.compile(
        r"(当前按中国大陆常见健康管理语境|优先参考国家卫健委|本报告参考了国家卫健委|"
        r"报告更强调有来源的官方|指南库|文档库证据|根据您的规则和输入信息|"
        r"以下是.*健康解释报告|个性化健康解释报告)"
    )
    safe_lines: List[str] = []
    for line in body.splitlines():
        if audience_unfriendly_line_pattern.search(line):
            continue
        if not unsafe_line_pattern.search(line):
            safe_lines.append(line)
            continue
        prefix_match = re.match(r"^(\s*(?:[-*]\s+|\d+[.、)]\s*|[0-9️⃣]+\s*))", line)
        prefix = prefix_match.group(1) if prefix_match else ""
        if medication_line_pattern.search(line):
            safe_text = "用药问题请咨询医生；本报告不提供用药方案。"
        elif emergency_reassurance_line_pattern.search(line):
            safe_text = "如果出现急症相关症状，请立即拨打 120 或前往急诊；没有症状时先按报告建议复核和记录。"
        elif device_line_pattern.search(line):
            safe_text = "PPG 估算只适合做趋势提醒，不能替代规范血压测量。"
        elif diagnostic_line_pattern.search(line):
            safe_text = "这不是诊断结果，下一步应先规范复核并连续记录。"
        else:
            safe_text = "这不是诊断结果，下一步应先规范复核并连续记录。"
        safe_line = f"{prefix}{safe_text}"
        if safe_lines and safe_lines[-1].strip() == safe_line.strip():
            continue
        safe_lines.append(safe_line)
    body = "\n".join(safe_lines)
    body = _scrub_introduced_details(body)
    return body


# Free-form variants of forbidden "newly introduced specifics" that the literal
# replacement dict cannot enumerate. Each (pattern, replacement) rewrites the
# offending span into safe, generic guidance instead of dropping the sentence.
_DETAIL_SCRUB_RULES: List[tuple] = [
    # Redundant "在同一/固定时间（例如…）" lead-ins before the timepoint detail.
    (re.compile(r"(在|于)?\s*(同一|固定)(的)?时间\s*(（|\()?\s*(例如|比如|如)"), "在相对固定、方便的时间（"),
    # Fixed measurement timepoints: "（例如/比如）早晨起床排尿后、晚饭前(测量/记录)"
    (re.compile(r"(（|\()?\s*(例如|比如|如)?\s*[早晚][上晨]?[^，。；、\n]{0,6}(起床|排尿|睡前|睡觉前|晚饭前|早饭前|饭前|饭后)[^，。；\n]{0,12}(）|\))?"),
     "在相对固定、方便的时间"),
    # Sleep hours: "(每晚/保证)(7-8/7~8/8)小时(的)?睡眠"
    (re.compile(r"(保证|每晚|确保|建议)?\s*\d+\s*[-~～到]\s*\d+\s*小时(的)?睡眠"), "保持规律作息"),
    (re.compile(r"(保证|每晚|确保)\s*\d+\s*小时(的)?睡眠"), "保持规律作息"),
    # Generic "保证/确保充足睡眠".
    (re.compile(r"(保证|确保|建议)?\s*充足(的)?睡眠"), "保持规律作息"),
    # Explicit day/week durations introduced for measuring/recording, incl.
    # ranges like "3~5天" / "3 ～ 5 天" / "三到五天".
    (re.compile(r"连续\s*(测量|记录|监测)?\s*[0-9一二两三四五六七八九十]+\s*[-~～到至]\s*[0-9一二两三四五六七八九十]+\s*(天|周|星期)"), "连续记录一段时间"),
    (re.compile(r"(持续|记录|监测)\s*[0-9一二两三四五六七八九十]+\s*[-~～到至]\s*[0-9一二两三四五六七八九十]+\s*(天|周|星期)"), "连续记录一段时间"),
    (re.compile(r"连续\s*(测量|记录|监测)?\s*(一|二|两|三|四|五|六|七|几|\d+)\s*(天|周|星期)"), "连续记录一段时间"),
    (re.compile(r"(持续|记录|监测)\s*(一|二|两|三|四|五|六|七|几|\d+)\s*(天|周|星期)"), "连续记录一段时间"),
    # "(连续)?测量几天" / "连续几天的记录" with the indefinite quantifier 几.
    (re.compile(r"连续\s*(测量|记录|监测)?\s*几\s*(天|周|星期)"), "连续记录一段时间"),
    (re.compile(r"(测量|记录|监测)\s*几\s*(天|周|星期)"), "连续记录一段时间"),
    (re.compile(r"连续\s*几\s*(天|周|星期)(的记录)?"), "连续一段时间的记录"),
    # "(连续)?记录/测量几次" indefinite count.
    (re.compile(r"连续\s*(测量|记录|监测)?\s*几\s*次"), "连续记录一段时间"),
    (re.compile(r"(测量|记录|监测)\s*几\s*次"), "连续记录"),
    # Indefinite multi-day phrasing: "之后/接下来几天" -> "后续"; "连续多天(记录)" ->
    # "连续记录一段时间". No fixed-day / 几天 / 多天 frequency hints may survive.
    (re.compile(r"(之后|后面|接下来|往后|这)\s*几\s*天"), "后续"),
    (re.compile(r"连续\s*多\s*天\s*(记录|测量|监测)(测量趋势|趋势)?"), "连续记录一段时间"),
    (re.compile(r"连续\s*多\s*天"), "连续记录一段时间"),
    (re.compile(r"多\s*天\s*(连续)?\s*(记录|测量|监测)"), "连续记录一段时间"),
    (re.compile(r"(记录|测量|监测)\s*多\s*天"), "连续记录一段时间"),
    # Fixed timepoint variants without the meal/wake anchors: "早上、晚上" /
    # "早晚" / "早晨和晚上" / "早上或晚上" / "上午、下午" (optionally parenthesised).
    (re.compile(r"[（(]\s*(早上|早晨|清晨|上午)[、和或／/]+(晚上|傍晚|睡前|下午)\s*[）)]"), ""),
    (re.compile(r"(早上|早晨|清晨|上午)\s*[、和或／/]\s*(晚上|傍晚|下午)(各[一二]次)?"), ""),
    (re.compile(r"[（(]\s*早晚\s*[）)]"), ""),
    (re.compile(r"早晚各[一二]次"), ""),
    (re.compile(r"(上午|下午|早上|晚上)\s*固定时间"), "相对固定、方便的时间"),
    # "每天早晚/早晨/晚上(各一次)?(测量/记录)" fixed-frequency phrasing.
    (re.compile(r"每天(早晚|早晨|晚上|早上|清晨)(各一次)?\s*(测量|记录)?"), "在相对固定、方便的时间"),
    (re.compile(r"每日(早晚|早晨|晚上|早上|清晨)(各一次)?\s*(测量|记录)?"), "在相对固定、方便的时间"),
    # Measurement prep micro-steps.
    (re.compile(r"测量前\s*(半小时|\d+\s*分钟)[^。；\n]*"), "按设备说明书规范测量"),
    (re.compile(r"排空膀胱[^。；\n]*"), "按说明书规范准备"),
    (re.compile(r"(坐靠背椅|靠背椅)[^。；\n]*双脚平放"), "按说明书规范姿势测量"),
    (re.compile(r"双脚平放[^。；\n]*"), "按说明书规范姿势测量"),
    (re.compile(r"增加蔬菜(和)?水果[的摄入]*"), "均衡饮食"),
]


def _scrub_introduced_details(body: str) -> str:
    """Rewrite forbidden newly-introduced specifics into safe generic phrasing.

    The prompt already forbids fixed timepoints, sleep-hour counts, day/week
    durations and measurement micro-steps, but DeepSeek still emits free-form
    variants. This deterministic pass guarantees they never reach the user.
    """
    for pattern, replacement in _DETAIL_SCRUB_RULES:
        body = pattern.sub(replacement, body)
    # Tidy artifacts left by span removal.
    body = re.sub(r"在相对固定、方便的时间(（）|\(\))?", "在相对固定、方便的时间", body)
    body = body.replace("（）", "").replace("()", "")
    # Collapse redundant lead-ins like "连续多天在同一时间在相对固定、方便的时间".
    body = re.sub(r"(连续多天|连续)?\s*(在)?(同一|固定)(的)?时间(在相对固定、方便的时间)", r"\5", body)
    body = re.sub(r"(在相对固定、方便的时间)+", r"\1", body)
    body = re.sub(r"连续多天(在相对固定、方便的时间)", r"\1", body)
    # Remove stray modal verbs left dangling before the safe replacement.
    body = re.sub(r"(保证|确保|建议|尽量)(保持规律作息|均衡饮食|连续记录一段时间)", r"\2", body)
    body = re.sub(r"[，、]{2,}", "，", body)
    body = re.sub(r"，(）|\))", r"\1", body)
    body = re.sub(r"(在相对固定、方便的时间)(测量并记录|测量|记录|监测)", r"\1连续记录", body)
    body = re.sub(r"(连续记录一段时间)(测量并记录|测量|记录|监测)", r"\1", body)
    body = body.replace("连续记录一段时间的记录", "连续一段时间的记录")
    body = re.sub(r"(按设备说明书规范测量|按说明书规范姿势测量|按说明书规范准备)([，、])+", r"\1。", body)
    body = body.replace("。。", "。").replace("；。", "。").replace("，。", "。")
    return body


def _ensure_plain_language_section(
    body: str,
    report: HealthReport,
    rule_result: RuleResult,
    payload: MeasurementPayload,
    uses_rag: bool = True,
) -> str:
    if "## 几个容易误解的点" in body or "## 给用户的易懂解释" in body:
        return body
    lines = [body.rstrip(), "", "## 几个容易误解的点"]
    lines.extend(f"- {item}" for item in _plain_language_lines(report, rule_result, payload, uses_rag=uses_rag))
    return "\n".join(lines)


def _ensure_china_context_section(body: str, rule_result: RuleResult, payload: MeasurementPayload, uses_rag: bool = True) -> str:
    if "## 在国内可以怎么做" in body or "## 中国用户提示" in body:
        return body
    lines = [body.rstrip(), "", "## 在国内可以怎么做"]
    lines.extend(f"- {item}" for item in _china_context_lines(payload, rule_result, uses_rag=uses_rag))
    return "\n".join(lines)


def _ui_summary(report: HealthReport, rule_result: RuleResult) -> UiSummary:
    if rule_result.emergency:
        return UiSummary(
            title="可能存在紧急风险",
            status="emergency",
            priority="highest",
            chips=["急症症状", "立即就医", "PPG需复核"],
            next_actions=report.recommendations.medical_consultation[:2],
        )
    if not rule_result.quality.is_usable:
        return UiSummary(
            title="本次信号质量不足",
            status="remeasurement_required",
            priority="high",
            chips=["重新采集", "规范血压计复核"],
            next_actions=report.recommendations.remeasurement[:2] + report.recommendations.device_advice[:1],
        )
    return UiSummary(
        title="血压估算趋势解释",
        status=rule_result.risk_level,
        priority="medium" if rule_result.risk_level != "routine_monitoring" else "routine",
        chips=[rule_result.estimated_bp_category, rule_result.quality.quality_level, rule_result.urgency_level],
        next_actions=(report.recommendations.remeasurement + report.recommendations.medical_consultation)[:3],
    )


def generate_template_report(
    payload: MeasurementPayload,
    rule_result: RuleResult,
    evidence: List[Evidence],
    warnings: List[str] = None,
    citation_quality: CitationQuality = None,
    uses_rag: bool = True,
) -> HealthReport:
    measurement = payload.measurement
    recommendations = _recommendations(rule_result)
    recommendation_evidence = bind_recommendation_evidence(recommendations, rule_result, evidence)
    citation_quality = evaluate_citation_quality(rule_result, evidence, recommendation_evidence)
    report = HealthReport(
        report_id=str(uuid4()),
        generation_mode="template_only",
        input_summary=InputSummary(
            module=measurement.module,
            estimated_sbp=measurement.estimated_sbp,
            estimated_dbp=measurement.estimated_dbp,
            heart_rate=measurement.heart_rate,
            signal_quality_score=measurement.signal_quality_score,
            signal_quality_label=measurement.signal_quality_label,
            confidence=measurement.confidence,
            capture_duration_sec=measurement.capture_duration_sec,
            motion_artifact_score=measurement.motion_artifact_score,
            finger_coverage_score=measurement.finger_coverage_score,
            contact_pressure_level=measurement.contact_pressure_level,
            ambient_light_level=measurement.ambient_light_level,
            ppg_source=measurement.ppg_source,
            algorithm_version=measurement.algorithm_version,
            calculation_principle=measurement.calculation_principle,
            timestamp=measurement.timestamp.isoformat() if measurement.timestamp else None,
        ),
        measurement_status=MeasurementStatus(
            is_usable=rule_result.quality.is_usable,
            quality_level=rule_result.quality.quality_level,
            quality_explanation=rule_result.quality.explanation,
            warnings=rule_result.quality.warnings,
        ),
        risk_assessment=RiskAssessment(
            bp_category_reference=rule_result.bp_category_reference,
            estimated_bp_category=rule_result.estimated_bp_category,
            risk_level=rule_result.risk_level,
            urgency_level=rule_result.urgency_level,
            explanation=_risk_explanation(rule_result),
        ),
        recommendations=recommendations,
        safety_alert=_safety_alert(rule_result),
        retrieved_evidence=evidence,
        recommendation_evidence=recommendation_evidence,
        citation_quality=citation_quality or CitationQuality(),
        disclaimer=DISCLAIMER,
        markdown_report="",
        warnings=list(dict.fromkeys(list(warnings or []) + citation_quality.issues + rule_result.warnings)),
    )
    report.ui_summary = _ui_summary(report, rule_result)
    report.markdown_report = _markdown(report, rule_result, payload, uses_rag=uses_rag)
    return report


def _repair_glued_headings(body: str) -> str:
    """Fix cases where an LLM glues the next heading onto a sentence.

    e.g. ``…请直接拨打 120 或前往急诊。## 为什么这样提醒你`` becomes two lines.
    """
    # Insert a newline before any inline '## '/'### ' heading that follows text.
    # The lookbehind also requires a non-newline char before, so a heading at the
    # very start of the body (position 0) is left untouched (no leading blanks).
    return re.sub(r"(?<=[^\n])(#{2,3}\s)", r"\n\n\1", body)


# Recommendation sub-groups that must render as ### under "## 接下来怎么做".
_RECOMMENDATION_GROUP_TITLES = ("复测与记录", "设备复核", "生活方式", "就医沟通")


def _normalize_markdown_headings(body: str) -> str:
    """Clean up LLM heading artifacts.

    * Drop standalone ``#`` / ``# `` lines (DeepSeek sometimes emits an empty
      ``#`` separator line, leaving an empty heading in the report).
    * Demote recommendation group headings (复测与记录 / 设备复核 / 生活方式 /
      就医沟通) to ``###`` so they nest under ``## 接下来怎么做`` instead of
      becoming top-level sections.
    * Remove any heading line whose text is empty after the marker.
    """
    out: List[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        # Empty heading: only '#' characters (and optional spaces), no text.
        if re.fullmatch(r"#{1,6}\s*", stripped):
            continue
        heading = re.match(r"^(#{1,6})\s+(.*\S)\s*$", stripped)
        if heading:
            text = heading.group(2)
            # Strip trailing inline citation when matching the group title.
            title_core = re.sub(r"\s*\[\d+(?:\s*,\s*\d+)*\]\s*$", "", text).strip()
            if any(title_core.startswith(t) for t in _RECOMMENDATION_GROUP_TITLES):
                out.append(f"### {text}")
                continue
        out.append(line)
    # Collapse any 3+ blank lines left behind into a single blank line.
    normalized = "\n".join(out)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized


def _citation_enforcement_enabled(enforce_citations: Optional[bool]) -> bool:
    """Whether to force inline citations (strip out-of-range + inject + renumber).

    Default ON. The E2 ablation harness sets ``REPORT_ENFORCE_CITATIONS=0`` (or
    passes ``enforce_citations=False``) to build the S3 variant: the LLM's raw
    citation behaviour is preserved so the judge can measure the true unsupported
    claim rate WITHOUT the deterministic citation engine repairing it.
    """
    if enforce_citations is not None:
        return enforce_citations
    return os.getenv("REPORT_ENFORCE_CITATIONS", "1").strip().lower() not in {"0", "false", "off", "no"}


def _finalize_rag_llm_body(
    llm_body: str,
    report: HealthReport,
    rule_result: RuleResult,
    payload: MeasurementPayload,
    evidence: List[Evidence],
    enforce_citations: Optional[bool] = None,
) -> tuple[str, bool]:
    """Sanitize + (optionally) citation-enforce an LLM RAG body.

    Returns ``(markdown, consistent)`` where ``markdown`` is the complete
    report (body + rebuilt 参考文献/参考依据说明/免责声明 tail) and
    ``consistent`` means: if evidence exists, the body carries at least one
    valid inline ``[n]`` and no marker exceeds the evidence count. With
    enforcement ON (default) the body is deterministically repaired (strip
    out-of-range markers, inject missing section citations, renumber by first
    appearance, prune uncited references). With enforcement OFF (S3 ablation)
    those repairs are skipped and the LLM's raw citations pass through.
    """
    enforce = _citation_enforcement_enabled(enforce_citations)
    registry = build_registry(evidence)
    # Sanitize first (it collapses the no-emergency clause and may swallow
    # newlines), THEN split any heading the LLM glued onto a sentence — otherwise
    # the sanitizer's whitespace-collapsing regexes re-glue the heading.
    body = _sanitize_llm_body(llm_body)
    body = _repair_glued_headings(body)
    body = _normalize_markdown_headings(body)
    # Editorial pass: wrong words, over-reassurance, emergency ops advice,
    # colloquialisms, lifestyle detail. Runs before citation enforcement so any
    # rewritten section still gets its inline [n] re-covered below.
    body = sanitize_medical_copy(body, rule_result)
    # Remove any dangling/incomplete citation brackets the LLM produced (e.g.
    # "…复测结果。 [" or "[1,") before the enforcement step re-adds valid ones.
    body = clean_citation_fragments(body)
    body = _ensure_china_context_section(body, rule_result, payload, uses_rag=True)
    body = _ensure_plain_language_section(body, report, rule_result, payload, uses_rag=True)

    final = None
    if registry.has_evidence and enforce:
        # Drop any hallucinated/out-of-range markers, then guarantee coverage.
        body = registry.strip_invalid_markers(body)
        body = registry.enforce_section_citations(body)
        # A final fragment sweep in case marker-stripping left a stray bracket.
        body = clean_citation_fragments(body)
        final = registry.finalize(body)
        body = final.body
        report.references = final.entries
        consistent = final.cited_count >= 1
    elif registry.has_evidence:
        # S3 (enforcement OFF): keep the LLM's raw inline markers untouched —
        # no stripping, no injection, no renumbering. Attach the full ordered
        # reference list so the report still renders; the judge sees raw [n].
        report.references = registry.references_markdown_entries()
        final = None
        # Not gated on citation consistency: letting the raw body through is the
        # whole point of this ablation arm.
        consistent = True
    else:
        report.references = []
        consistent = True
    tail = _reference_tail_lines(report, final, uses_rag=True, registry=registry if not enforce else None)
    return body + "\n" + "\n".join(tail), consistent


def generate_report_draft(
    payload: MeasurementPayload,
    rule_result: RuleResult,
    evidence: List[Evidence],
    mode: str = None,
    warnings: List[str] = None,
    citation_quality: CitationQuality = None,
) -> HealthReport:
    requested_mode = mode or os.getenv("REPORT_MODE", "template_only")
    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    report = generate_template_report(payload, rule_result, evidence, warnings=warnings, citation_quality=citation_quality)
    if requested_mode == "llm_only":
        no_rag_quality = CitationQuality(
            passed=False,
            coverage_rate=0.0,
            recommendation_grounding_rate=0.0,
            high_trust_sensitive_uses=False,
            issues=["非 RAG 对照组未使用文档库证据。"],
        )
        report = generate_template_report(
            payload,
            rule_result,
            [],
            warnings=list(warnings or []) + ["非 RAG 对照组：未使用文档库检索证据。"],
            citation_quality=no_rag_quality,
            uses_rag=False,
        )
        if provider == "deepseek":
            try:
                llm_body = generate_deepseek_input_only_report(payload=payload)
            except LlmGenerationError as exc:
                report.generation_mode = "llm_only_fallback_template"
                report.warnings.append(f"DeepSeek 对照组生成失败，已回退到 no_rag_template：{exc}")
                return report
            llm_body = _sanitize_llm_body(llm_body)
            report.markdown_report = _with_replaced_body(report.markdown_report, llm_body)
            report.generation_mode = f"llm_only_input_deepseek:{os.getenv('DEEPSEEK_MODEL', 'deepseek-v4-flash')}"
            return report
        if provider in {"anthropic", "claude"}:
            try:
                llm_body = generate_anthropic_input_only_report(payload=payload)
            except LlmGenerationError as exc:
                report.generation_mode = "llm_only_fallback_template"
                report.warnings.append(f"Claude 对照组生成失败，已回退到 no_rag_template：{exc}")
                return report
            llm_body = _sanitize_llm_body(llm_body)
            report.markdown_report = _with_replaced_body(report.markdown_report, llm_body)
            report.generation_mode = f"llm_only_input_anthropic:{os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-5')}"
            return report
        if provider in OPENAI_COMPATIBLE_PROVIDERS:
            try:
                llm_body = generate_openai_compatible_input_only_report(payload=payload)
            except LlmGenerationError as exc:
                report.generation_mode = "llm_only_fallback_template"
                report.warnings.append(f"第三方对照组生成失败，已回退到 no_rag_template：{exc}")
                return report
            llm_body = _sanitize_llm_body(llm_body)
            report.markdown_report = _with_replaced_body(report.markdown_report, llm_body)
            report.generation_mode = f"llm_only_input_openai_compatible:{os.getenv('LLM_MODEL', 'gpt-5.5')}"
            return report
        report.generation_mode = "llm_only_template"
        return report
    if requested_mode == "llm_rag" and provider == "deepseek":
        template_body, _ = _split_report_tail(report.markdown_report)
        try:
            llm_body = generate_deepseek_report_body(
                template_body=template_body,
                rule_result=rule_result,
                evidence=evidence,
            )
        except LlmGenerationError as exc:
            report.generation_mode = "llm_rag_fallback_template"
            report.warnings.append(f"DeepSeek 生成失败，已回退到 template_only：{exc}")
            return report
        full_markdown, consistent = _finalize_rag_llm_body(llm_body, report, rule_result, payload, evidence)
        if not consistent:
            report.warnings.append("DeepSeek RAG 正文缺少可用内联引用且自动补全失败，已回退到 template_only。")
            report.generation_mode = "llm_rag_fallback_template"
            return report
        report.markdown_report = full_markdown
        report.generation_mode = f"llm_rag_deepseek:{os.getenv('DEEPSEEK_MODEL', 'deepseek-v4-flash')}"
        return report
    if requested_mode == "llm_rag" and provider in {"anthropic", "claude"}:
        template_body, _ = _split_report_tail(report.markdown_report)
        try:
            llm_body = generate_anthropic_report_body(
                template_body=template_body,
                rule_result=rule_result,
                evidence=evidence,
            )
        except LlmGenerationError as exc:
            report.generation_mode = "llm_rag_fallback_template"
            report.warnings.append(f"Claude 生成失败，已回退到 template_only：{exc}")
            return report
        full_markdown, consistent = _finalize_rag_llm_body(llm_body, report, rule_result, payload, evidence)
        if not consistent:
            report.warnings.append("Claude RAG 正文缺少可用内联引用且自动补全失败，已回退到 template_only。")
            report.generation_mode = "llm_rag_fallback_template"
            return report
        report.markdown_report = full_markdown
        report.generation_mode = f"llm_rag_anthropic:{os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-5')}"
        return report
    if requested_mode == "llm_rag" and provider in OPENAI_COMPATIBLE_PROVIDERS:
        template_body, _ = _split_report_tail(report.markdown_report)
        try:
            llm_body = generate_openai_compatible_report_body(
                template_body=template_body,
                rule_result=rule_result,
                evidence=evidence,
            )
        except LlmGenerationError as exc:
            report.generation_mode = "llm_rag_fallback_template"
            report.warnings.append(f"第三方 LLM 生成失败，已回退到 template_only：{exc}")
            return report
        full_markdown, consistent = _finalize_rag_llm_body(llm_body, report, rule_result, payload, evidence)
        if not consistent:
            report.warnings.append("第三方 LLM RAG 正文缺少可用内联引用且自动补全失败，已回退到 template_only。")
            report.generation_mode = "llm_rag_fallback_template"
            return report
        report.markdown_report = full_markdown
        report.generation_mode = f"llm_rag_openai_compatible:{os.getenv('LLM_MODEL', 'gpt-5.5')}"
        return report
    if requested_mode == "llm_rag" and provider != "mock":
        report.generation_mode = "llm_rag_fallback_template"
        report.warnings.append(f"LLM provider `{provider}` 尚未配置为可用实现，已回退到 template_only。")
        return report
    return report
