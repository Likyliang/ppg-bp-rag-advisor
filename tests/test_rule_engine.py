from app.services.rule_engine import run_rule_engine
from app.services.validator import parse_payload


def _rules(payload):
    return run_rule_engine(parse_payload(payload))


def test_stage_2_high_quality_rule():
    result = _rules({"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86})
    assert result.estimated_bp_category == "stage_2_reference_range"
    assert result.risk_level == "elevated_attention"
    assert "lifestyle" in result.recommendation_intents
    assert any("国家卫健委" in query for query in result.retrieval_intents)


def test_aha_region_keeps_aha_retrieval_intents():
    result = _rules(
        {
            "estimated_sbp": 145,
            "estimated_dbp": 92,
            "signal_quality_score": 0.86,
            "guideline_region": "AHA",
        }
    )
    assert result.guideline_region_used == "AHA"
    assert any("blood pressure reference range" in query for query in result.retrieval_intents)
    assert not any("国家卫健委" in query for query in result.retrieval_intents)


def test_low_quality_blocks_strong_range_explanation():
    result = _rules({"estimated_sbp": 150, "estimated_dbp": 95, "signal_quality_score": 0.42})
    assert result.quality.is_usable is False
    assert result.estimated_bp_category == "not_interpretable_low_quality"
    assert result.risk_level == "remeasurement_required"


def test_severe_with_chest_pain_triggers_emergency():
    result = _rules(
        {
            "estimated_sbp": 185,
            "estimated_dbp": 122,
            "signal_quality_score": 0.9,
            "symptoms": {"chest_pain": True},
        }
    )
    assert result.emergency is True
    assert result.urgency_level == "emergency"
    assert "emergency_care" in result.recommendation_intents


def test_severe_without_symptoms_is_urgent_recheck_not_emergency():
    result = _rules({"estimated_sbp": 185, "estimated_dbp": 122, "signal_quality_score": 0.9})
    assert result.emergency is False
    assert result.estimated_bp_category == "severe_range"
    assert result.urgency_level == "urgent_recheck"


def test_special_population_flags_medication_user():
    result = _rules(
        {
            "estimated_sbp": 136,
            "estimated_dbp": 86,
            "signal_quality_score": 0.82,
            "antihypertensive_medication": True,
        }
    )
    assert result.special_population is True
    assert "正在使用降压药" in result.special_population_reasons


def test_ppg_feature_motion_artifact_blocks_strong_range_explanation():
    result = _rules(
        {
            "estimated_sbp": 145,
            "estimated_dbp": 92,
            "signal_quality_score": 0.86,
            "motion_artifact_score": 0.82,
        }
    )
    assert result.quality.is_usable is False
    assert result.estimated_bp_category == "not_interpretable_low_quality"
    assert "signal_quality_improvement" in result.recommendation_intents
    assert any("运动伪影" in warning for warning in result.quality.warnings)


def test_ppg_feature_contact_pressure_adds_signal_quality_retrieval():
    result = _rules(
        {
            "estimated_sbp": 130,
            "estimated_dbp": 82,
            "signal_quality_score": 0.86,
            "contact_pressure_level": "high",
        }
    )
    assert result.quality.quality_level == "fair"
    assert "signal_quality_improvement" in result.recommendation_intents
    assert "signal_quality" in result.retrieval_allowed_uses
    assert any("接触压力" in query for query in result.retrieval_intents)
