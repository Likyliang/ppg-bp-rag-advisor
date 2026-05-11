import json
from pathlib import Path

import pytest

from app.agents.workflow import generate_report
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "demo_cases.jsonl"
CASES = [json.loads(line) for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_report_fixture_count_meets_stop_criteria():
    assert len(CASES) >= 50


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["case_id"])
def test_report_fixture_generates_safe_evidence_backed_report(case):
    report = generate_report(case)
    assert report.markdown_report
    assert report.safety_review is not None
    assert report.safety_review.passed is True
    assert report.retrieved_evidence
    assert report.citation_quality.coverage_rate >= 0.5
    assert report.recommendation_evidence
    assert report.citation_quality.recommendation_grounding_rate == 1.0
    assert all(item.passed for item in report.recommendation_evidence)
    assert "仅供个人健康趋势参考" in report.disclaimer


@pytest.mark.parametrize(
    "case",
    [
        item for item in CASES
        if item.get("pregnancy")
        or item.get("diabetes")
        or item.get("kidney_disease")
        or item.get("antihypertensive_medication")
        or bool((item.get("symptoms") or {}))
    ],
    ids=lambda case: case["case_id"],
)
def test_sensitive_report_fixtures_use_high_trust_evidence(case):
    report = generate_report(case)
    sensitive_uses = {"emergency_alert", "medication_safety", "special_population"}
    sensitive_evidence = [
        item for item in report.retrieved_evidence
        if sensitive_uses & set(item.allowed_uses)
    ]
    requires_sensitive_evidence = bool(
        report.safety_alert.emergency
        or case.get("pregnancy")
        or case.get("diabetes")
        or case.get("kidney_disease")
        or case.get("antihypertensive_medication")
    )
    if requires_sensitive_evidence:
        assert sensitive_evidence
    if sensitive_evidence:
        assert all(item.evidence_class in HIGH_TRUST_EVIDENCE_CLASSES for item in sensitive_evidence)
