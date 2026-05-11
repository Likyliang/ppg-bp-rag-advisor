import pytest

import scripts.evaluate_retrieval as retrieval_eval

from app.services.retriever import retrieve_knowledge
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES
from scripts.evaluate_retrieval import GOLDEN_QUERIES, _evidence_matches


def test_golden_queries_cover_full_calibration_set():
    assert len(GOLDEN_QUERIES) == 100
    assert all(case.get("expected_topics") for case in GOLDEN_QUERIES)
    assert all(case.get("expected_evidence_classes") for case in GOLDEN_QUERIES)


def test_calibrated_evaluation_does_not_pass_gold_allowed_uses(monkeypatch):
    calls = []

    def fake_retrieve_knowledge(*args, **kwargs):
        calls.append(kwargs.get("allowed_uses"))

        class FakeResult:
            evidence = []
            warnings = []

        return FakeResult()

    monkeypatch.setattr(retrieval_eval, "retrieve_knowledge", fake_retrieve_knowledge)
    result = retrieval_eval.evaluate_retrieval(top_k=5)

    query_only_calls = calls[: len(GOLDEN_QUERIES)]
    metadata_filter_calls = calls[len(GOLDEN_QUERIES) :]
    assert result["summary"]["evaluation_mode"] == "calibrated_query_only"
    assert all(value is None for value in query_only_calls)
    assert all(value for value in metadata_filter_calls)


def test_calibrated_query_only_meets_quality_floor():
    result = retrieval_eval.evaluate_retrieval(top_k=5)
    summary = result["summary"]
    assert summary["query_count"] == 100
    assert summary["evaluation_mode"] == "calibrated_query_only"
    assert summary["match_rate"] >= 0.95
    assert summary["mean_precision_at_5"] >= 0.85
    assert summary["unsafe_source_leakage_count"] == 0


@pytest.mark.parametrize("case", GOLDEN_QUERIES, ids=lambda case: case["query"][:28])
def test_metadata_filter_safety_query_has_expected_evidence(case):
    result = retrieve_knowledge(
        [case["query"]],
        top_k=5,
        allowed_uses=case.get("allowed_uses") or case["expected_uses"],
        min_quality_score=18,
    )
    assert result.evidence
    assert any(_evidence_matches(item, case["expected_uses"]) for item in result.evidence)
    if case.get("sensitive"):
        assert all(item.evidence_class in HIGH_TRUST_EVIDENCE_CLASSES for item in result.evidence)
