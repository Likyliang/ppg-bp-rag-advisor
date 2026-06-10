"""Statistical primitives shared by the Chapter-6 application-layer experiments.

Ported from the thesis main line (`medrag_agent.evaluators.paired_comparison`)
to keep both chapters methodologically consistent, then extended with the
primitives the experiment plan (110_*) requires but the main line lacks:

* zero-event upper bounds (Wilson + rule-of-three) — so near-0 safety violation
  rates are reported as honest upper bounds, never as "the system is safe";
* multiple-comparison correction (Holm-Bonferroni, Benjamini-Hochberg FDR) —
  fixes the main line's uncorrected-comparison gap for pre-registered families;
* cluster bootstrap — sentences inside one report are not independent, so
  report-level resampling is needed for citation-faithfulness CIs;
* McNemar exact — paired binary system comparison (S2 vs S3, on vs off).

Pure stdlib (math/random); no numpy/scipy dependency so it runs in the gate env.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

Z_95 = 1.959963984540054


# ---------------------------------------------------------------------------
# Proportion confidence intervals and zero-event upper bounds
# ---------------------------------------------------------------------------


def wilson_ci(successes: int, total: int, z: float = Z_95) -> Tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Preferred over the normal approximation near 0/1, which is exactly the
    regime safety violation rates live in.
    """
    if total <= 0:
        return (0.0, 0.0)
    phat = successes / total
    denom = 1 + z**2 / total
    center = (phat + z**2 / (2 * total)) / denom
    margin = z * math.sqrt((phat * (1 - phat) + z**2 / (4 * total)) / total) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def rule_of_three_upper_bound(total: int, confidence: float = 0.95) -> float:
    """Upper bound on a true rate when 0 events were observed in ``total`` trials.

    The classic rule-of-three gives ~3/n at 95%. We return the exact
    1 - (1 - confidence)^(1/n) form so other confidence levels are correct too.
    Use this to write "violation rate <= X% (0/N observed)" instead of "0%".
    """
    if total <= 0:
        return 1.0
    alpha = 1.0 - confidence
    return 1.0 - alpha ** (1.0 / total)


def zero_event_report(successes: int, total: int, confidence: float = 0.95) -> Dict[str, float]:
    """Honest reporting bundle for a (possibly zero) event rate."""
    lower, upper = wilson_ci(successes, total, z=Z_95)
    out = {
        "events": successes,
        "total": total,
        "rate": (successes / total) if total else 0.0,
        "wilson_low": round(lower, 5),
        "wilson_high": round(upper, 5),
    }
    if successes == 0 and total > 0:
        out["rule_of_three_upper"] = round(rule_of_three_upper_bound(total, confidence), 5)
    return out


# ---------------------------------------------------------------------------
# Paired binary comparison
# ---------------------------------------------------------------------------


def mcnemar_exact_p(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the two discordant counts.

    ``b`` = #(A correct/positive, B wrong/negative), ``c`` = the reverse.
    Returns 1.0 when there are no discordant pairs (no power) — callers must
    not read that as "no difference", only "test has no information here".
    """
    total = b + c
    if total == 0:
        return 1.0
    tail = sum(math.comb(total, k) for k in range(0, min(b, c) + 1)) / (2**total)
    return min(1.0, 2 * tail)


def mcnemar_from_pairs(pairs: Sequence[Tuple[bool, bool]]) -> Dict[str, float]:
    """McNemar summary from (system_a_positive, system_b_positive) pairs."""
    b = sum(1 for a, bb in pairs if a and not bb)
    c = sum(1 for a, bb in pairs if (not a) and bb)
    return {
        "a_pos_b_neg": b,
        "b_pos_a_neg": c,
        "discordant": b + c,
        "mcnemar_exact_p": mcnemar_exact_p(b, c),
    }


# ---------------------------------------------------------------------------
# Multiple-comparison correction
# ---------------------------------------------------------------------------


def holm_bonferroni(pvalues: Sequence[float], alpha: float = 0.05) -> List[Dict[str, object]]:
    """Holm-Bonferroni step-down correction (controls FWER).

    Returns, in the original input order, each p-value with its adjusted value
    and a reject flag. Use for small pre-registered families (e.g. the 4 E1
    main contrasts).
    """
    indexed = sorted(range(len(pvalues)), key=lambda i: pvalues[i])
    m = len(pvalues)
    adjusted = [0.0] * m
    running_max = 0.0
    for rank, idx in enumerate(indexed):
        adj = min(1.0, (m - rank) * pvalues[idx])
        running_max = max(running_max, adj)  # enforce monotonicity
        adjusted[idx] = running_max
    return [
        {"index": i, "p": pvalues[i], "p_adjusted": round(adjusted[i], 6), "reject": adjusted[i] <= alpha}
        for i in range(m)
    ]


def benjamini_hochberg(pvalues: Sequence[float], alpha: float = 0.05) -> List[Dict[str, object]]:
    """Benjamini-Hochberg FDR correction.

    Returns adjusted p-values (q-values) in original input order, less
    conservative than Holm — appropriate for larger exploratory families.
    """
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    prev = 1.0
    for rank in range(m - 1, -1, -1):
        idx = order[rank]
        q = min(prev, pvalues[idx] * m / (rank + 1))
        adjusted[idx] = q
        prev = q
    return [
        {"index": i, "p": pvalues[i], "q_value": round(adjusted[i], 6), "reject": adjusted[i] <= alpha}
        for i in range(m)
    ]


# ---------------------------------------------------------------------------
# Bootstrap (i.i.d. and clustered)
# ---------------------------------------------------------------------------


def bootstrap_mean_ci(
    values: Sequence[float],
    iters: int = 10000,
    seed: int = 13,
    ci: float = 0.95,
) -> Tuple[float, float]:
    """Percentile bootstrap CI for a mean over independent observations."""
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = int((1 - ci) / 2 * (iters - 1))
    hi = int((1 + ci) / 2 * (iters - 1))
    return (means[lo], means[hi])


def cluster_bootstrap_rate_ci(
    clusters: Sequence[Sequence[float]],
    iters: int = 10000,
    seed: int = 13,
    ci: float = 0.95,
) -> Tuple[float, float]:
    """Cluster (report-level) bootstrap CI for a pooled binary/continuous rate.

    Each cluster is a report; its elements are that report's sentence-level
    scores (e.g. 1=supported, 0=unsupported). Resampling whole reports, not
    individual sentences, respects within-report correlation — required for
    honest citation-faithfulness intervals.
    """
    clusters = [list(c) for c in clusters if len(c) > 0]
    k = len(clusters)
    if k == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    rates = []
    for _ in range(iters):
        picked = [clusters[rng.randrange(k)] for _ in range(k)]
        numer = sum(sum(c) for c in picked)
        denom = sum(len(c) for c in picked)
        rates.append(numer / denom if denom else 0.0)
    rates.sort()
    lo = int((1 - ci) / 2 * (iters - 1))
    hi = int((1 + ci) / 2 * (iters - 1))
    return (rates[lo], rates[hi])


def paired_bootstrap_diff_ci(
    paired_values: Sequence[Tuple[float, float]],
    iters: int = 10000,
    seed: int = 13,
    ci: float = 0.95,
) -> Tuple[float, float]:
    """Percentile CI for the mean paired difference (variant - baseline)."""
    n = len(paired_values)
    if n == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    diffs = []
    for _ in range(iters):
        idxs = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(paired_values[i][1] - paired_values[i][0] for i in idxs) / n)
    diffs.sort()
    lo = int((1 - ci) / 2 * (iters - 1))
    hi = int((1 + ci) / 2 * (iters - 1))
    return (diffs[lo], diffs[hi])


# ---------------------------------------------------------------------------
# Inter/intra-rater agreement
# ---------------------------------------------------------------------------


def cohen_kappa(labels_a: Sequence[object], labels_b: Sequence[object]) -> float:
    """Cohen's kappa for two label sequences (judge vs human, or test-retest).

    Reported as intra-annotator (test-retest) or judge-vs-human agreement; with
    a single annotator it CANNOT stand in for inter-annotator reliability —
    that limitation is disclosed in the chapter, not papered over here.
    """
    if len(labels_a) != len(labels_b) or not labels_a:
        return 0.0
    n = len(labels_a)
    categories = sorted(set(labels_a) | set(labels_b), key=str)
    observed = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    count_a = {cat: 0 for cat in categories}
    count_b = {cat: 0 for cat in categories}
    for a, b in zip(labels_a, labels_b):
        count_a[a] += 1
        count_b[b] += 1
    expected = sum((count_a[cat] / n) * (count_b[cat] / n) for cat in categories)
    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1 - expected)


def rogan_gladen_correct(
    observed_rate: float,
    sensitivity: float,
    specificity: float,
) -> float:
    """Rogan-Gladen misclassification correction for a measured prevalence.

    Corrects a judge-measured positive rate using the judge's per-class
    sensitivity/specificity (estimated from the human-calibration subset), so
    full-corpus judge numbers are bias-adjusted rather than taken at face value.
    Clamped to [0, 1].
    """
    denom = sensitivity + specificity - 1.0
    if abs(denom) < 1e-9:
        return observed_rate  # judge uninformative; return raw with caveat
    corrected = (observed_rate + specificity - 1.0) / denom
    return max(0.0, min(1.0, corrected))


__all__ = [
    "wilson_ci",
    "rule_of_three_upper_bound",
    "zero_event_report",
    "mcnemar_exact_p",
    "mcnemar_from_pairs",
    "holm_bonferroni",
    "benjamini_hochberg",
    "bootstrap_mean_ci",
    "cluster_bootstrap_rate_ci",
    "paired_bootstrap_diff_ci",
    "cohen_kappa",
    "rogan_gladen_correct",
]
