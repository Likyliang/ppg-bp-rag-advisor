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


def test_poincare_features_trigger_arrhythmia():
    # Poincaré descriptors alone (no explicit irregular flag) should trip the
    # arrhythmia screening path.
    payload = {
        "estimated_sbp": 124, "estimated_dbp": 78, "heart_rate": 84,
        "signal_quality_score": 0.86, "confidence": 0.8, "capture_duration_sec": 30,
        "enable_screening_suggestions": True,
        "rhythm": {"available": True, "ibi_cv": 0.05, "valid_beat_count": 60,
                   "poincare_cluster_count": 4, "poincare_dispersion": 0.35,
                   "ibi_stepping_increment_ms": 120},
    }
    _, _, result = _run(payload)
    arr = [s for s in result.suggestions if s.condition_id == "arrhythmia_screening"]
    assert arr
    assert "Poincaré" in arr[0].rationale


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


def test_scg_beat_amplitude_corroborates_arrhythmia():
    # SCG beat-to-beat amplitude variation alone (regular pulse flag, low ibi_cv)
    # should still trip arrhythmia screening as a mechanical corroboration signal.
    payload = {
        "estimated_sbp": 124, "estimated_dbp": 78, "heart_rate": 84,
        "signal_quality_score": 0.86, "enable_screening_suggestions": True,
        "rhythm": {"available": True, "pulse_rhythm": "regular", "ibi_cv": 0.04, "valid_beat_count": 40},
        "cardiac_vibration": {"available": True, "signal_quality_label": "good", "beat_amplitude_cv": 0.35},
    }
    _, _, result = _run(payload)
    arr = [s for s in result.suggestions if s.condition_id == "arrhythmia_screening"]
    assert arr and "心振逐拍幅值" in arr[0].rationale


def test_valvular_screening_fires_from_scg_morphology():
    payload = {
        "estimated_sbp": 124, "estimated_dbp": 78, "signal_quality_score": 0.86,
        "enable_screening_suggestions": True,
        "cardiac_vibration": {"available": True, "signal_quality_label": "good",
                               "lvet_ms": 350, "s1_s2_amplitude_ratio": 3.4},
    }
    _, _, result = _run(payload)
    valv = [s for s in result.suggestions if s.condition_id == "valvular_screening"]
    assert valv
    assert valv[0].confidence == "low"            # research-grade, capped low
    assert "yang_2021_scg_aortic_stenosis_detection" in valv[0].evidence_source_ids
    text = valv[0].rationale + valv[0].screening_action
    assert "可能" in text and any(c in text for c in ("超声心动图", "心内科", "就医"))


def test_screening_cites_the_specific_scg_source():
    # End-to-end: the SCG screening suggestions cite their exact backing papers.
    report = generate_report({
        "estimated_sbp": 124, "estimated_dbp": 78, "heart_rate": 84,
        "signal_quality_score": 0.86, "confidence": 0.8, "capture_duration_sec": 30,
        "enable_screening_suggestions": True,
        "rhythm": {"available": True, "pulse_rhythm": "irregular", "ibi_cv": 0.22, "valid_beat_count": 40},
        "cardiac_vibration": {"available": True, "signal_quality_label": "good",
                               "lvet_ms": 350, "s1_s2_amplitude_ratio": 3.4},
    })
    cited_sources = {
        e.source_id.rsplit("_", 1)[0]
        for e in report.retrieved_evidence
        if e.citation_number is not None
    }
    assert "mehrang_2018_smartphone_mechanocardiography" in {s.rsplit("_", 1)[0] for s in cited_sources} or \
           any("mehrang" in e.source_id for e in report.retrieved_evidence if e.citation_number)
    assert any("yang_2021_scg_aortic_stenosis" in e.source_id for e in report.retrieved_evidence if e.citation_number)
    # screening section carries inline [n] markers
    md = report.markdown_report
    sec = md[md.find("## 建议进一步排查"): md.find("## 在国内可以怎么做")]
    import re
    assert re.search(r"\[\d", sec)


def test_vascular_aging_fires_from_sdppg_and_morphology():
    payload = {
        "estimated_sbp": 124, "estimated_dbp": 78, "signal_quality_score": 0.86,
        "enable_screening_suggestions": True,
        "ppg_morphology": {"available": True, "stiffness_index": 13.5, "reflection_index": 78},
        "ppg_derived": {"available": True, "sdppg_aging_index": 0.7},
    }
    _, _, result = _run(payload)
    va = [s for s in result.suggestions if s.condition_id == "vascular_aging_screening"]
    assert va and va[0].confidence == "low"
    assert "charlton_2022_vascageNet_ppg_vascular_age_review" in va[0].evidence_source_ids


def test_vascular_aging_gated_by_feature_availability():
    # Values present but available=False must NOT fire (avoids stray-value triggers).
    payload = {
        "estimated_sbp": 124, "estimated_dbp": 78, "signal_quality_score": 0.86,
        "enable_screening_suggestions": True,
        "ppg_morphology": {"available": False, "stiffness_index": 99},
        "ppg_derived": {"available": False, "sdppg_aging_index": 9},
    }
    _, _, result = _run(payload)
    assert "vascular_aging_screening" not in {s.condition_id for s in result.suggestions}


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


def test_normalizer_maps_poincare_and_scaffold_models():
    parsed = parse_payload({
        "estimated_sbp": 128, "estimated_dbp": 82,
        "rhythm": {"available": True, "poincare_cluster_count": 3,
                   "poincare_dispersion": 0.4, "ibi_stepping_increment_ms": 110},
        "ppg_morphology": {"available": True, "crest_time_ms": 180,
                           "stiffness_index": 7.2, "reflection_index": 55,
                           "dicrotic_notch_present": False},
        "ppg_derived": {"available": True, "sdppg_b_a_ratio": -0.6,
                        "sdppg_aging_index": 0.3, "spo2": 96,
                        "oxygen_desaturation_index": 12},
    })
    assert parsed.rhythm.poincare_cluster_count == 3
    assert parsed.rhythm.ibi_stepping_increment_ms == 110
    assert parsed.ppg_morphology.available is True
    assert parsed.ppg_morphology.crest_time_ms == 180
    assert parsed.ppg_morphology.dicrotic_notch_present is False
    assert parsed.ppg_derived.available is True
    assert parsed.ppg_derived.sdppg_b_a_ratio == -0.6
    assert parsed.ppg_derived.oxygen_desaturation_index == 12
