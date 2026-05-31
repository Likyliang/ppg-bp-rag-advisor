from __future__ import annotations

import re
from typing import Any, Iterable, List

from app.schemas.report import HealthReport, SafetyReview
from app.schemas.rule_result import RuleResult
from app.services.config_loader import load_yaml_config


def _flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return "\n".join(
            _flatten_text(item)
            for key, item in value.items()
            if key not in {"retrieved_evidence", "safety_review"}
        )
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return "\n".join(_flatten_text(item) for item in value)
    if hasattr(value, "model_dump"):
        return _flatten_text(value.model_dump())
    return str(value)


def _match_patterns(text: str, patterns: List[str]) -> List[str]:
    matches = []
    for pattern in patterns:
        if re.search(pattern, text):
            matches.append(pattern)
    return matches


def review_safety(report: Any, rule_result: RuleResult = None) -> SafetyReview:
    terms = load_yaml_config("config/safety_terms.yaml")
    if isinstance(report, HealthReport):
        text = _flatten_text(
            {
                "markdown_report": report.markdown_report,
                "disclaimer": report.disclaimer,
                "recommendations": report.recommendations,
                "risk_assessment": report.risk_assessment,
                "safety_alert": report.safety_alert,
            }
        )
    else:
        text = _flatten_text(report)
    issues: List[str] = []
    required_edits: List[str] = []
    severity = "none"

    diagnostic_hits = _match_patterns(text, terms.get("diagnostic_patterns", []))
    if diagnostic_hits:
        issues.append(f"存在诊断性或过度确定表述：{', '.join(diagnostic_hits)}")
        required_edits.append("删除确诊、无需复测或无需就医等确定性表述。")
        severity = "high"

    medication_hits = _match_patterns(text, terms.get("medication_change_patterns", []))
    if medication_hits:
        issues.append(f"存在用药调整风险表述：{', '.join(medication_hits)}")
        required_edits.append("删除开药、停药、调药或自行服药建议。")
        severity = "high"

    overclaim_hits = _match_patterns(text, terms.get("device_overclaim_patterns", []))
    if overclaim_hits:
        issues.append(f"存在 PPG 或设备能力过度承诺：{', '.join(overclaim_hits)}")
        required_edits.append("补充 PPG 估算局限，避免替代规范血压测量的说法。")
        severity = "high"

    has_ppg_limitation = "PPG" in text and ("不能替代" in text or "仅供个人健康趋势参考" in text)
    if not has_ppg_limitation:
        issues.append("缺少 PPG 估算局限说明。")
        required_edits.append("加入 PPG 估算仅供趋势参考、不能替代规范血压测量的说明。")
        if severity == "none":
            severity = "medium"

    required_terms = terms.get("required_disclaimer_terms", [])
    missing_terms = [term for term in required_terms if term not in text]
    if missing_terms:
        issues.append(f"免责声明缺少必要内容：{', '.join(missing_terms)}")
        required_edits.append("补齐趋势参考、不能替代医生判断和规范测量的免责声明。")
        if severity == "none":
            severity = "medium"

    if rule_result and rule_result.emergency:
        reassurance_hits = _match_patterns(
            text, terms.get("emergency_false_reassurance_patterns", [])
        )
        if reassurance_hits:
            issues.append(
                f"急症情境下出现不当安抚表述（不需要 120 或急诊）：{', '.join(reassurance_hits)}"
            )
            required_edits.append("急症情境下必须保留急救提示，删除任何“不需要 120/急诊”的表述。")
            severity = "high"
        first_block = text[:180]
        emergency_cues = ("急救", "紧急医疗", "120", "急诊")
        if not any(cue in first_block for cue in emergency_cues):
            issues.append("急症规则已触发，但报告开头缺少急救提示。")
            required_edits.append("把急救、120、急诊或紧急医疗提示放在报告最前面。")
            severity = "high"

    passed = severity not in {"high", "critical"}
    return SafetyReview(
        passed=passed,
        issues=issues,
        required_edits=required_edits,
        severity=severity,
    )


def apply_safety_edits(report: HealthReport, safety_review: SafetyReview) -> HealthReport:
    if "PPG" not in report.markdown_report:
        report.markdown_report += "\n\nPPG 估算值仅供个人健康趋势参考，不能替代规范血压测量。"
    if "不能替代医生诊断" not in report.disclaimer:
        report.disclaimer = (
            report.disclaimer.rstrip("。")
            + "，不能替代医生诊断、治疗决策或规范血压测量。"
        )
    if "不能替代规范血压测量" not in report.disclaimer:
        report.disclaimer = report.disclaimer.rstrip("。") + "，也不能替代规范血压测量。"
    report.safety_review = safety_review
    return report
