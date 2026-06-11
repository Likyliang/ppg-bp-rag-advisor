"""Tests for the PPG/SCG screening-suggestion ("建议进一步排查") layer.

These verify the new capability *and* its guardrails: suggestions are opt-in,
hedged, referral-bearing, confidence-capped, emergency-suppressed, and that
definitive-diagnosis / care-avoidance language stays blocked.
"""

from app.agents.workflow import generate_report
from app.schemas.screening import ScreeningResult, ScreeningSuggestion
from app.services.rule_engine import run_rule_engine
from app.services.safety import review_safety, review_screening_suggestions
from app.services.screening import _clamp_confidence, run_screening
from app.services.validator import parse_payload


SECTION_TITLE = "建议进一步排查（需医生确认）"


def _run(payload):
    parsed = parse_payload(payload)
    rule_result = run_rule_engine(parsed)
    return parsed, rule_result, run_screening(parsed, rule_result)


# --------------------------------------------------------------------------- #
# Opt-in gating
# --------------------------------------------------------------------------- #
def test_screening_off_by_default_produces_nothing():
    payload = {
        "estimated_sbp": 142, "estimated_dbp": 91, "heart_rate": 116,
        "signal_quality_score": 0.86,
        "rhythm": {"available": True, "pulse_rhythm": "irregular", "ibi_cv": 0.22},
    }
    report = generate_report(payload)
    assert report.screening is not None
    assert report.screening.requested is False
    assert report.screening.produced is False
    assert SECTION_TITLE not in report.markdown_report


def test_screening_requires_global_and_request_optin():
    _, _, result = _run({"estimated_sbp": 118, "estimated_dbp": 76, "signal_quality_score": 0.9})
    assert result.enabled is True  # config switch on
    assert result.requested is False
    assert result.produced is False


# --------------------------------------------------------------------------- #
# Arrhythmia screening from rhythm features
# --------------------------------------------------------------------------- #
def test_irregular_rhythm_triggers_arrhythmia_suggestion():
    payload = {
        "estimated_sbp": 124, "estimated_dbp": 78, "heart_rate": 88,
        "signal_quality_score": 0.86, "confidence": 0.8, "capture_duration_sec": 30,
        "enable_screening_suggestions": True,
        "rhythm": {"available": True, "pulse_rhythm": "irregular", "ibi_cv": 0.22,
                   "ectopic_beat_ratio": 0.08, "valid_beat_count": 40},
    }
    report = generate_report(payload)
    ids = {s.condition_id for s in report.screening.suggestions}
    assert "arrhythmia_screening" in ids
    arr = next(s for s in report.screening.suggestions if s.condition_id == "arrhythmia_screening")
    assert arr.confidence == "moderate"
    text = arr.rationale + arr.screening_action
    assert "可能" in text                      # hedged
    assert any(cue in text for cue in ("心电图", "门诊", "就医", "心内科"))  # referral
    assert report.safety_review.passed is True
    assert SECTION_TITLE in report.markdown_report
    # The validated text is shown verbatim, before the reference/disclaimer tail.
    assert report.markdown_report.count(SECTION_TITLE) == 1
    assert 0 <= report.markdown_report.find(SECTION_TITLE) < report.markdown_report.find("## 参考文献")


def test_regular_rhythm_does_not_trigger_arrhythmia():
    payload = {
        "estimated_sbp": 118, "estimated_dbp": 76, "heart_rate": 72,
        "signal_quality_score": 0.9, "confidence": 0.85, "capture_duration_sec": 30,
        "enable_screening_suggestions": True,
        "rhythm": {"available": True, "pulse_rhythm": "regular", "ibi_cv": 0.03, "valid_beat_count": 50},
    }
    _, _, result = _run(payload)
    assert "arrhythmia_screening" not in {s.condition_id for s in result.suggestions}


def test_insufficient_beats_suppresses_rhythm_suggestion():
    payload = {
        "estimated_sbp": 124, "estimated_dbp": 78, "signal_quality_score": 0.86,
        "enable_screening_suggestions": True,
        "rhythm": {"available": True, "pulse_rhythm": "irregular", "ibi_cv": 0.3, "valid_beat_count": 5},
    }
    _, _, result = _run(payload)
    assert "arrhythmia_screening" not in {s.condition_id for s in result.suggestions}
    assert any("心搏数不足" in note for note in result.notes)


# --------------------------------------------------------------------------- #
# Heart-rate based suggestions
# --------------------------------------------------------------------------- #
def test_tachycardia_low_confidence_suggestion():
    payload = {
        "estimated_sbp": 124, "estimated_dbp": 78, "heart_rate": 122,
        "signal_quality_score": 0.86, "enable_screening_suggestions": True,
    }
    _, _, result = _run(payload)
    tachy = [s for s in result.suggestions if s.condition_id == "tachycardia_eval"]
    assert tachy and tachy[0].confidence == "low"


def test_heart_rate_condition_fires_even_when_rhythm_present():
    # Regression: ``requires`` is positive-only — a present rhythm block must not
    # suppress an unrelated heart-rate suggestion.
    payload = {
        "estimated_sbp": 124, "estimated_dbp": 78, "heart_rate": 122,
        "signal_quality_score": 0.86, "enable_screening_suggestions": True,
        "rhythm": {"available": True, "pulse_rhythm": "regular", "ibi_cv": 0.04, "valid_beat_count": 50},
    }
    _, _, result = _run(payload)
    assert "tachycardia_eval" in {s.condition_id for s in result.suggestions}


# --------------------------------------------------------------------------- #
# Signal-quality and emergency suppression
# --------------------------------------------------------------------------- #
def test_low_ppg_quality_suppresses_quality_gated_suggestions():
    payload = {
        "estimated_sbp": 150, "estimated_dbp": 96, "signal_quality_score": 0.4,
        "confidence": 0.4, "capture_duration_sec": 10, "enable_screening_suggestions": True,
        "rhythm": {"available": True, "pulse_rhythm": "irregular", "ibi_cv": 0.3, "valid_beat_count": 40},
    }
    _, _, result = _run(payload)
    ids = {s.condition_id for s in result.suggestions}
    # Both require ppg_signal_usable, which a poor-quality reading fails.
    assert "arrhythmia_screening" not in ids
    assert "hypertension_workup" not in ids


def test_emergency_suppresses_screening_section():
    payload = {
        "estimated_sbp": 188, "estimated_dbp": 124, "heart_rate": 120,
        "signal_quality_score": 0.9, "enable_screening_suggestions": True,
        "symptoms": {"chest_pain": True},
        "rhythm": {"available": True, "pulse_rhythm": "irregular", "ibi_cv": 0.3, "valid_beat_count": 40},
    }
    report = generate_report(payload)
    assert report.safety_alert.emergency is True
    assert report.markdown_report.startswith("## 可能存在紧急风险")
    assert report.screening.produced is False
    assert SECTION_TITLE not in report.markdown_report
    assert any("急症" in note for note in report.screening.notes)


# --------------------------------------------------------------------------- #
# Confidence cap and safety validation
# --------------------------------------------------------------------------- #
def test_confidence_is_capped_at_moderate():
    assert _clamp_confidence("high") == "moderate"
    assert _clamp_confidence("certain") == "low"
    assert _clamp_confidence("moderate") == "moderate"
    assert _clamp_confidence(None) == "low"


def test_validator_drops_unhedged_or_overreaching_suggestion():
    bad = ScreeningResult(
        enabled=True, requested=True, produced=True,
        suggestions=[
            ScreeningSuggestion(  # missing hedge + missing referral
                condition_id="bad1", label="x", confidence="moderate",
                rationale="心律不齐。", screening_action="自己观察即可。",
            ),
            ScreeningSuggestion(  # overreach: definitive diagnosis
                condition_id="bad2", label="y", confidence="moderate",
                rationale="你得了房颤。", screening_action="建议就医检查。",
            ),
            ScreeningSuggestion(  # well-formed
                condition_id="ok", label="z", confidence="moderate",
                rationale="信号可能与心律不齐有关，不能确定。",
                screening_action="建议到心内科门诊做心电图检查。",
            ),
        ],
    )
    reviewed = review_screening_suggestions(bad)
    kept = {s.condition_id for s in reviewed.suggestions}
    assert kept == {"ok"}
    assert reviewed.produced is True
    assert sum("拦截" in note for note in reviewed.notes) == 2


def test_review_safety_blocks_screening_overreach_language():
    review = review_safety(
        "你得了房颤，不用看医生。\nPPG 估算值仅供个人健康趋势参考，不能替代医生诊断，不能替代规范血压测量。"
    )
    assert review.passed is False
    assert review.severity == "high"
    assert any("越界" in issue for issue in review.issues)


# --------------------------------------------------------------------------- #
# Normalizer plumbing for the new nested feature blocks
# --------------------------------------------------------------------------- #
def test_normalizer_maps_nested_and_flat_feature_fields():
    parsed = parse_payload({
        "estimated_sbp": 130, "estimated_dbp": 84,
        "enable_screening_suggestions": True,
        "rhythm": {"available": True, "pulse_rhythm": "不齐", "ibi_cv": 0.2},
        "scg": {"available": True, "signal_quality_label": "好"},
        "pep_ms": 150,  # flat SCG key promoted into cardiac_vibration
    })
    assert parsed.enable_screening_suggestions is True
    assert parsed.rhythm.available is True
    assert parsed.rhythm.pulse_rhythm == "irregular"   # alias normalized
    assert parsed.cardiac_vibration.available is True
    assert parsed.cardiac_vibration.signal_quality_label == "good"  # alias normalized
    assert parsed.cardiac_vibration.pep_ms == 150
