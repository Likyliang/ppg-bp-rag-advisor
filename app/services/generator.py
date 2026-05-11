from __future__ import annotations

import os
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
from app.services.evidence_quality import bind_recommendation_evidence, evaluate_citation_quality


DISCLAIMER = (
    "本报告仅供个人健康趋势参考，不能替代医生诊断、治疗决策或规范血压测量。"
    "如有不适或多次复核仍异常，请咨询专业医务人员。"
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
        return f"{reasons}。请优先寻求当地急救或紧急医疗帮助。"
    if not rule_result.quality.is_usable:
        return "本次信号质量不足，建议重新采集并使用经过验证的上臂式电子血压计复核。"
    if rule_result.estimated_bp_category == "severe_range":
        return "本次估算值处于严重偏高参考范围，即使没有急症症状，也建议尽快用规范设备复核并咨询医生。"
    if rule_result.estimated_bp_category in {"stage_1_reference_range", "stage_2_reference_range"}:
        return "本次估算值处于偏高参考范围，建议复测并结合连续记录判断趋势。"
    if rule_result.estimated_bp_category == "elevated_reference_range":
        return "本次估算值提示可能存在偏高趋势，可通过规范家庭监测和生活方式管理继续观察。"
    return "当前未触发急症规则，仍建议关注长期趋势而非单次估算值。"


def _recommendations(rule_result: RuleResult) -> Recommendations:
    if rule_result.emergency:
        return Recommendations(
            remeasurement=["如条件允许，可在等待医疗帮助时使用规范血压计复核，但不要因此延误急救。"],
            device_advice=["PPG 估算值不能替代规范设备，严重症状需要优先处理。"],
            lifestyle=[],
            medical_consultation=["立即寻求当地急救或紧急医疗服务。"],
        )

    remeasurement: List[str] = []
    device: List[str] = ["使用经过验证的上臂式电子血压计进行复核。"]
    lifestyle: List[str] = []
    consultation: List[str] = []

    if "remeasurement" in rule_result.recommendation_intents:
        remeasurement.extend(["安静休息至少 5 分钟后重新测量。", "连续多天记录测量趋势，避免只看单次估算值。"])
    if "signal_quality_improvement" in rule_result.recommendation_intents:
        remeasurement.extend(["重新采集时保持手指覆盖摄像头、身体静止，避免强光干扰。"])
    if "home_bp_monitoring" in rule_result.recommendation_intents:
        remeasurement.append("按固定时间记录家庭血压，并保留记录供医生参考。")
    if "lifestyle" in rule_result.recommendation_intents or "healthy_lifestyle" in rule_result.recommendation_intents:
        lifestyle.extend(["减少钠盐摄入。", "保持规律运动和体重管理。", "戒烟限酒，保证睡眠。", "管理压力，避免过量咖啡因。"])
    if "medical_consultation" in rule_result.recommendation_intents:
        consultation.append("若多次规范复核仍偏高，建议咨询医生。")
    if rule_result.special_population:
        reasons = "、".join(rule_result.special_population_reasons)
        consultation.append(f"因存在{reasons}，建议采取更保守的复核和就医策略。")
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
            message="可能存在紧急风险：估算值达到严重偏高范围且伴随急症相关症状，请立即寻求当地急救或紧急医疗帮助。",
        )
    return SafetyAlert(
        emergency=False,
        message="当前未触发急症规则。若出现胸痛、气短、肢体无力、视物改变或说话困难，请及时寻求急救。",
    )


def _markdown(report: HealthReport, rule_result: RuleResult) -> str:
    summary = report.input_summary
    lines: List[str] = []
    if report.safety_alert.emergency:
        lines.append("## 可能存在紧急风险")
        lines.append(report.safety_alert.message)
        lines.append("")

    lines.extend(
        [
            "## 本次结果摘要",
            (
                f"本次手指摄像头 PPG 算法估算血压为 "
                f"{summary.estimated_sbp}/{summary.estimated_dbp} mmHg，"
                f"{_category_text(rule_result.estimated_bp_category)}。"
            ),
            "该结果来自 PPG 估算，仅供个人健康趋势参考，不能替代规范血压测量。",
            "",
            "## 质量与风险解释",
            report.measurement_status.quality_explanation,
            report.risk_assessment.explanation,
            "",
            "## 建议",
        ]
    )
    for group in (
        report.recommendations.remeasurement,
        report.recommendations.device_advice,
        report.recommendations.lifestyle,
        report.recommendations.medical_consultation,
    ):
        for item in group:
            lines.append(f"- {item}")

    if report.retrieved_evidence:
        lines.extend(["", "## 参考来源"])
        for evidence in report.retrieved_evidence:
            source = f"[{evidence.source_id}] {evidence.title}"
            if evidence.organization:
                source += f"（{evidence.organization}）"
            if evidence.evidence_class:
                source += f" · {evidence.evidence_class}"
            if evidence.url:
                source += f": {evidence.url}"
            lines.append(f"- {source}")

    lines.extend(
        [
            "",
            "## 引用质量",
            f"证据覆盖率：{report.citation_quality.coverage_rate}",
            f"建议证据绑定率：{report.citation_quality.recommendation_grounding_rate}",
            f"敏感用途高可信来源：{'是' if report.citation_quality.high_trust_sensitive_uses else '否'}",
        ]
    )

    lines.extend(["", "## 免责声明", report.disclaimer])
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
) -> HealthReport:
    measurement = payload.measurement
    recommendations = _recommendations(rule_result)
    recommendation_evidence = bind_recommendation_evidence(recommendations, rule_result, evidence)
    citation_quality = evaluate_citation_quality(rule_result, evidence, recommendation_evidence)
    report = HealthReport(
        report_id=str(uuid4()),
        generation_mode="template_only",
        input_summary=InputSummary(
            estimated_sbp=measurement.estimated_sbp,
            estimated_dbp=measurement.estimated_dbp,
            heart_rate=measurement.heart_rate,
            signal_quality_label=measurement.signal_quality_label,
            confidence=measurement.confidence,
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
    report.markdown_report = _markdown(report, rule_result)
    return report


def generate_report_draft(
    payload: MeasurementPayload,
    rule_result: RuleResult,
    evidence: List[Evidence],
    mode: str = None,
    warnings: List[str] = None,
    citation_quality: CitationQuality = None,
) -> HealthReport:
    requested_mode = mode or os.getenv("REPORT_MODE", "template_only")
    if requested_mode == "llm_rag" and os.getenv("LLM_PROVIDER", "mock") != "mock":
        report = generate_template_report(payload, rule_result, evidence, warnings=warnings, citation_quality=citation_quality)
        report.generation_mode = "llm_rag_fallback_template"
        report.warnings.append("LLM adapter 尚未配置为可用实现，已回退到 template_only。")
        return report
    return generate_template_report(payload, rule_result, evidence, warnings=warnings, citation_quality=citation_quality)
