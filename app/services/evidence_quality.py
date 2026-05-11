from __future__ import annotations

from typing import Iterable, List, Sequence, Set

from app.schemas.report import CitationQuality, Evidence, RecommendationEvidence, Recommendations
from app.schemas.rule_result import RuleResult
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES


SENSITIVE_USES = {"emergency_alert", "medication_safety", "special_population"}


def _evidence_matches_any_use(item: Evidence, required_uses: Sequence[str]) -> bool:
    allowed = set(item.allowed_uses or [])
    required = set(required_uses)
    if not required:
        return True
    if "validated_devices" in required and item.topic == "validated_devices":
        return True
    return bool(allowed & required)


def _is_high_trust(item: Evidence) -> bool:
    return item.evidence_class in HIGH_TRUST_EVIDENCE_CLASSES


def _required_uses_for_recommendation(group: str, text: str, rule_result: RuleResult) -> List[str]:
    content = text.lower()
    if group == "remeasurement":
        if rule_result.emergency:
            return ["emergency_alert"]
        if any(term in text for term in ["手指", "摄像头", "强光", "信号", "重新采集"]):
            return ["signal_quality", "remeasurement"]
        if any(term in text for term in ["家庭血压", "固定时间", "记录", "连续多天", "趋势"]):
            return ["home_bp_monitoring", "remeasurement"]
        return ["remeasurement"]
    if group == "device_advice":
        if "PPG" in text or "规范设备" in text:
            return ["cuffless_ppg_limitations", "device_advice"]
        return ["device_advice"]
    if group == "lifestyle":
        return ["lifestyle"]
    if group == "medical_consultation":
        if rule_result.emergency or any(term in text for term in ["立即", "急救", "急诊"]):
            return ["emergency_alert"]
        if any(term in text for term in ["降压药", "用药", "停药", "调药", "服药"]):
            return ["special_population"]
        if rule_result.special_population and any(term in text for term in ["因存在", "保守", "就医"]):
            return ["special_population"]
        if any(term in text for term in ["胸痛", "气短", "肢体", "视物", "说话困难"]):
            return ["emergency_alert"]
        return ["home_bp_monitoring", "remeasurement"]
    if "ppg" in content or "PPG" in text:
        return ["cuffless_ppg_limitations"]
    return []


def bind_recommendation_evidence(
    recommendations: Recommendations,
    rule_result: RuleResult,
    evidence: Iterable[Evidence],
) -> List[RecommendationEvidence]:
    evidence_list = list(evidence)
    bindings: List[RecommendationEvidence] = []
    groups = [
        ("remeasurement", recommendations.remeasurement),
        ("device_advice", recommendations.device_advice),
        ("lifestyle", recommendations.lifestyle),
        ("medical_consultation", recommendations.medical_consultation),
    ]
    for group, items in groups:
        for index, text in enumerate(items):
            required_uses = _required_uses_for_recommendation(group, text, rule_result)
            high_trust_required = bool(set(required_uses) & SENSITIVE_USES)
            matches = [item for item in evidence_list if _evidence_matches_any_use(item, required_uses)]
            if high_trust_required:
                matches = [item for item in matches if _is_high_trust(item)]
            evidence_ids = [item.source_id for item in matches[:3]]
            issues: List[str] = []
            if not evidence_ids:
                issues.append(f"{group}[{index}] 缺少用途匹配证据：{', '.join(required_uses) or 'general'}")
            bindings.append(
                RecommendationEvidence(
                    group=group,
                    index=index,
                    text=text,
                    required_uses=required_uses,
                    evidence_ids=evidence_ids,
                    high_trust_required=high_trust_required,
                    passed=not issues,
                    issues=issues,
                )
            )
    return bindings


def evaluate_citation_quality(
    rule_result: RuleResult,
    evidence: Iterable[Evidence],
    recommendation_evidence: Iterable[RecommendationEvidence] = None,
) -> CitationQuality:
    evidence_list = list(evidence)
    recommendation_bindings = list(recommendation_evidence or [])
    expected_uses: Set[str] = set(rule_result.retrieval_allowed_uses)
    covered_uses: Set[str] = set()
    issues: List[str] = []

    for item in evidence_list:
        covered_uses.update(set(item.allowed_uses) & expected_uses)

    missing_uses = sorted(expected_uses - covered_uses)
    if missing_uses:
        issues.append(f"缺少用途匹配证据：{', '.join(missing_uses)}")

    high_trust_sensitive = True
    for use in sorted(expected_uses & SENSITIVE_USES):
        matching = [item for item in evidence_list if use in item.allowed_uses]
        if not matching:
            high_trust_sensitive = False
            issues.append(f"敏感用途 {use} 缺少证据。")
            continue
        if any(item.evidence_class not in HIGH_TRUST_EVIDENCE_CLASSES for item in matching):
            high_trust_sensitive = False
            issues.append(f"敏感用途 {use} 包含非高可信来源。")

    coverage_rate = 1.0
    if expected_uses:
        coverage_rate = round(len(covered_uses) / len(expected_uses), 3)

    failed_bindings = [item for item in recommendation_bindings if not item.passed]
    grounding_rate = 1.0
    if recommendation_bindings:
        grounding_rate = round(
            (len(recommendation_bindings) - len(failed_bindings)) / len(recommendation_bindings),
            3,
        )
    if failed_bindings:
        labels = [f"{item.group}[{item.index}]" for item in failed_bindings]
        issues.append(f"建议缺少证据绑定：{', '.join(labels)}")

    return CitationQuality(
        passed=not issues,
        coverage_rate=coverage_rate,
        checked_uses=sorted(expected_uses),
        missing_uses=missing_uses,
        high_trust_sensitive_uses=high_trust_sensitive,
        recommendation_grounding_rate=grounding_rate,
        ungrounded_recommendations=[f"{item.group}[{item.index}]" for item in failed_bindings],
        issues=issues,
    )
