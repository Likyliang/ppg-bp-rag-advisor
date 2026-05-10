import json
from pathlib import Path

import pytest

from app.agents.workflow import generate_report


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "demo_cases.jsonl"
CASES = [json.loads(line) for line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_report_fixture_count_meets_stop_criteria():
    assert len(CASES) >= 50


@pytest.mark.parametrize("case", CASES[:25], ids=lambda case: case["case_id"])
def test_report_fixture_generates_safe_evidence_backed_report(case):
    report = generate_report(case)
    assert report.markdown_report
    assert report.safety_review is not None
    assert report.safety_review.passed is True
    assert report.retrieved_evidence
    assert report.citation_quality.coverage_rate >= 0.5
    assert "仅供个人健康趋势参考" in report.disclaimer

