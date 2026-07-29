"""Tests for the screening evaluation / calibration harness."""

from scripts.evaluate_screening import (
    DEFAULT_CASES,
    _load_cases,
    evaluate_screening_cases,
    fired_conditions,
    sweep_threshold,
)


def test_fixture_cases_match_current_config():
    cases = _load_cases(DEFAULT_CASES)
    report = evaluate_screening_cases(cases)
    # The shipped synthetic fixture is consistent with the current rules.
    assert report["exact_match_rate"] == 1.0
    assert report["macro_sensitivity"] == 1.0
    assert report["macro_specificity"] == 1.0
    # Every labeled condition is represented with a perfect confusion row.
    for condition in ("arrhythmia_screening", "valvular_screening", "vascular_aging_screening",
                      "osa_screening", "tachycardia_eval", "bradycardia_eval", "hypertension_workup"):
        assert condition in report["per_condition"]
        assert report["per_condition"][condition]["fn"] == 0
        assert report["per_condition"][condition]["fp"] == 0


def test_emergency_and_low_quality_cases_fire_nothing():
    cases = {c["id"]: c for c in _load_cases(DEFAULT_CASES)}
    assert fired_conditions(cases["emergency_suppressed"]["payload"]) == []
    assert fired_conditions(cases["low_quality_suppressed"]["payload"]) == []
    assert fired_conditions(cases["spot_reading_no_osa"]["payload"]) == []


def test_sweep_threshold_finds_separating_cutoff():
    cases = [
        {"payload": {"rhythm": {"ibi_cv": 0.30}}, "expected_conditions": ["arrhythmia_screening"]},
        {"payload": {"rhythm": {"ibi_cv": 0.22}}, "expected_conditions": ["arrhythmia_screening"]},
        {"payload": {"rhythm": {"ibi_cv": 0.04}}, "expected_conditions": []},
        {"payload": {"rhythm": {"ibi_cv": 0.02}}, "expected_conditions": []},
    ]
    out = sweep_threshold(cases, "rhythm.ibi_cv", "arrhythmia_screening", [0.05, 0.10, 0.15, 0.20, 0.25])
    assert out["n_labeled"] == 4
    # A cutoff in (0.04, 0.22] perfectly separates → Youden J = 1.
    assert out["suggested_threshold"] in (0.05, 0.10, 0.15, 0.20)
    best = next(r for r in out["sweep"] if r["threshold"] == out["suggested_threshold"])
    assert best["youden_j"] == 1.0
