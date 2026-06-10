"""Unit tests for E1 retrieval-ablation ranking metrics (graded nDCG/Recall/MRR)
and the variant/contrast wiring."""

from scripts.exp_e1_retrieval_ablation import (
    CONTRASTS,
    VARIANTS,
    WEIGHT_SWEEP,
    _bootstrap_p,
    _dcg,
    _mrr,
    _ndcg_at_k,
    _recall_at_k,
)


QRELS = {(0, "a"): 2, (0, "b"): 1, (0, "c"): 0, (0, "d"): 2}


def test_ndcg_perfect_is_one():
    assert round(_ndcg_at_k(["a", "d", "b", "c"], 0, QRELS, 5), 4) == 1.0


def test_ndcg_penalizes_bad_ranking():
    bad = _ndcg_at_k(["c", "e", "a", "d", "b"], 0, QRELS, 5)
    assert 0 < bad < 1.0


def test_recall_counts_relevant_at_k():
    # relevant (grade>=1): a, b, d -> 3
    assert _recall_at_k(["a", "d", "b", "c", "e"], 0, QRELS, 5) == 1.0
    assert round(_recall_at_k(["a", "x", "y", "z", "w"], 0, QRELS, 5), 4) == round(1 / 3, 4)
    assert _recall_at_k(["x", "y"], 0, QRELS, 5) == 0.0


def test_mrr_reciprocal_rank():
    assert _mrr(["a", "c"], 0, QRELS) == 1.0
    assert round(_mrr(["c", "e", "a"], 0, QRELS), 4) == round(1 / 3, 4)
    assert _mrr(["c", "e"], 0, QRELS) == 0.0  # no relevant retrieved


def test_dcg_is_order_sensitive():
    assert _dcg([2, 1, 0]) > _dcg([0, 1, 2])


def test_ndcg_zero_when_no_relevant_in_qrels():
    empty = {(0, "x"): 0}
    assert _ndcg_at_k(["x", "y"], 0, empty, 5) == 0.0


def test_variant_and_contrast_wiring_is_consistent():
    # every contrast references variants that exist
    for _, base, var in CONTRASTS:
        assert base in VARIANTS, base
        assert var in VARIANTS, var
    # the four pre-registered ablation dimensions are all covered
    labels = {c[0] for c in CONTRASTS}
    assert {"hybrid_vs_keyword", "openai_vs_hashing", "fulltext_on_vs_off", "dedup_on_vs_off"} <= labels
    # weight sweep spans pure-vector (0) to pure-keyword (1)
    assert WEIGHT_SWEEP[0] == 0.0 and WEIGHT_SWEEP[-1] == 1.0


def test_bootstrap_p_significant_when_consistent_diff():
    pairs = [(0.2, 0.8)] * 40  # variant consistently +0.6
    assert _bootstrap_p(pairs, iters=2000, seed=1) < 0.05
    # no difference -> p == 1.0
    assert _bootstrap_p([(0.5, 0.5)] * 20, iters=1000) == 1.0
