from __future__ import annotations

from typing import Iterable, List, Set

from app.schemas.report import CitationQuality, Evidence
from app.schemas.rule_result import RuleResult
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES


SENSITIVE_USES = {"emergency_alert", "medication_safety", "special_population"}


def evaluate_citation_quality(rule_result: RuleResult, evidence: Iterable[Evidence]) -> CitationQuality:
    evidence_list = list(evidence)
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

    return CitationQuality(
        passed=not issues,
        coverage_rate=coverage_rate,
        checked_uses=sorted(expected_uses),
        missing_uses=missing_uses,
        high_trust_sensitive_uses=high_trust_sensitive,
        issues=issues,
    )
