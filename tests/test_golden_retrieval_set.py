import pytest

from app.services.retriever import retrieve_knowledge
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES
from scripts.evaluate_retrieval import GOLDEN_QUERIES, _evidence_matches


@pytest.mark.parametrize("case", GOLDEN_QUERIES[:35], ids=lambda case: case["query"][:28])
def test_golden_query_has_expected_evidence(case):
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

