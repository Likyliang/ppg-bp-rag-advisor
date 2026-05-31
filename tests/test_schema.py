import pytest
from pydantic import ValidationError

from app.services.validator import parse_payload


def test_parse_flat_payload():
    payload = parse_payload(
        {
            "estimated_sbp": 145,
            "estimated_dbp": 92,
            "heart_rate": 82,
            "signal_quality_score": 0.86,
            "confidence": 0.68,
            "capture_duration_sec": 30,
            "motion_artifact_score": 0.12,
            "finger_coverage_score": 0.92,
            "contact_pressure_level": "normal",
            "ambient_light_level": "normal",
            "ppg_source": "camera_finger",
            "algorithm_version": "miniapp-bp-v1.0",
            "age": 45,
        }
    )
    assert payload.measurement.estimated_sbp == 145
    assert payload.measurement.heart_rate == 82
    assert payload.measurement.confidence == 0.68
    assert payload.measurement.capture_duration_sec == 30
    assert payload.measurement.motion_artifact_score == 0.12
    assert payload.measurement.finger_coverage_score == 0.92
    assert payload.measurement.contact_pressure_level == "normal"
    assert payload.measurement.ambient_light_level == "normal"
    assert payload.measurement.ppg_source == "camera_finger"
    assert payload.measurement.algorithm_version == "miniapp-bp-v1.0"
    assert payload.user_profile.age == 45
    assert payload.locale == "zh-CN"


def test_schema_rejects_out_of_range_bp():
    with pytest.raises(ValidationError):
        parse_payload({"estimated_sbp": 500, "estimated_dbp": 90})


def test_medication_names_string_is_split():
    payload = parse_payload(
        {
            "estimated_sbp": 130,
            "estimated_dbp": 82,
            "medication_names": "amlodipine, losartan",
        }
    )
    assert payload.user_profile.medication_names == ["amlodipine", "losartan"]


def test_ppg_feature_chinese_labels_are_normalized():
    payload = parse_payload(
        {
            "estimated_sbp": 130,
            "estimated_dbp": 82,
            "按压力度": "过紧",
            "环境光": "强光",
        }
    )
    assert payload.measurement.contact_pressure_level == "high"
    assert payload.measurement.ambient_light_level == "bright"
