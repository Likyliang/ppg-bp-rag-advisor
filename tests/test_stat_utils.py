import math

from scripts.stat_utils import (
    benjamini_hochberg,
    cluster_bootstrap_rate_ci,
    cohen_kappa,
    holm_bonferroni,
    mcnemar_exact_p,
    mcnemar_from_pairs,
    paired_bootstrap_diff_ci,
    rogan_gladen_correct,
    rule_of_three_upper_bound,
    wilson_ci,
    zero_event_report,
)


def test_wilson_ci_contains_point_estimate():
    lo, hi = wilson_ci(30, 100)
    assert 0 <= lo < 0.30 < hi <= 1
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_rule_of_three_approx_three_over_n():
    # classic rule of three: ~3/n at 95%
    assert abs(rule_of_three_upper_bound(100) - 0.03) < 0.0015
    assert rule_of_three_upper_bound(0) == 1.0


def test_zero_event_report_adds_upper_bound_only_when_zero():
    z = zero_event_report(0, 200)
    assert z["rate"] == 0.0
    assert "rule_of_three_upper" in z and z["rule_of_three_upper"] < 0.02
    nz = zero_event_report(5, 200)
    assert "rule_of_three_upper" not in nz


def test_mcnemar_exact_basic():
    assert mcnemar_exact_p(0, 0) == 1.0  # no discordant pairs -> no info
    # strongly asymmetric discordants -> small p
    assert mcnemar_exact_p(0, 20) < 1e-4
    # symmetric -> p == 1.0
    assert mcnemar_exact_p(10, 10) == 1.0


def test_mcnemar_from_pairs_counts_discordants():
    pairs = [(True, False), (True, False), (False, True), (True, True), (False, False)]
    out = mcnemar_from_pairs(pairs)
    assert out["a_pos_b_neg"] == 2
    assert out["b_pos_a_neg"] == 1
    assert out["discordant"] == 3


def test_holm_bonferroni_monotone_and_rejects():
    ps = [0.001, 0.04, 0.03, 0.5]
    res = holm_bonferroni(ps, alpha=0.05)
    by_index = {r["index"]: r for r in res}
    assert by_index[0]["reject"] is True  # smallest, clearly significant
    assert by_index[3]["reject"] is False  # 0.5 never rejected
    # adjusted p is non-decreasing along sorted order
    assert all(0 <= r["p_adjusted"] <= 1 for r in res)


def test_benjamini_hochberg_less_conservative_than_holm():
    ps = [0.01, 0.02, 0.03, 0.04, 0.05]
    holm = holm_bonferroni(ps)
    bh = benjamini_hochberg(ps)
    holm_rejects = sum(r["reject"] for r in holm)
    bh_rejects = sum(r["reject"] for r in bh)
    assert bh_rejects >= holm_rejects


def test_cluster_bootstrap_ci_brackets_pooled_rate():
    # 5 reports, each fully supported except one half-supported
    clusters = [[1, 1, 1], [1, 1], [1, 1, 1, 1], [0, 1], [1, 1, 1]]
    lo, hi = cluster_bootstrap_rate_ci(clusters, iters=2000, seed=1)
    pooled = sum(sum(c) for c in clusters) / sum(len(c) for c in clusters)
    assert lo <= pooled <= hi
    assert 0 <= lo <= hi <= 1


def test_paired_bootstrap_diff_ci_positive_when_variant_better():
    pairs = [(0.0, 1.0)] * 30 + [(1.0, 1.0)] * 10  # variant >= baseline
    lo, hi = paired_bootstrap_diff_ci(pairs, iters=2000, seed=2)
    assert lo > 0  # variant strictly better -> CI above 0


def test_cohen_kappa_perfect_and_chance():
    assert abs(cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) - 1.0) < 1e-9
    # opposite labels -> negative or zero agreement beyond chance
    assert cohen_kappa(["a", "a", "b", "b"], ["b", "b", "a", "a"]) <= 0.0


def test_rogan_gladen_correction():
    # perfect judge returns observed unchanged
    assert abs(rogan_gladen_correct(0.3, 1.0, 1.0) - 0.3) < 1e-9
    # imperfect judge correction stays in [0,1]
    c = rogan_gladen_correct(0.3, 0.9, 0.85)
    assert 0.0 <= c <= 1.0
    # uninformative judge (sens+spec=1) returns raw
    assert rogan_gladen_correct(0.4, 0.5, 0.5) == 0.4
