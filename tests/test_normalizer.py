from app.services.normalizer import normalize_payload


def test_field_aliases_are_normalized():
    normalized = normalize_payload(
        {
            "SBP": 142,
            "DBP": 91,
            "HR": 78,
            "quality": "good",
            "conf": 0.7,
            "duration": 30,
            "sensor_source": "camera_finger",
            "model_version": "miniapp-bp-v1.0",
        }
    )
    assert normalized["measurement"]["estimated_sbp"] == 142
    assert normalized["measurement"]["estimated_dbp"] == 91
    assert normalized["measurement"]["heart_rate"] == 78
    assert normalized["measurement"]["signal_quality_label"] == "good"
    assert normalized["measurement"]["confidence"] == 0.7
    assert normalized["measurement"]["capture_duration_sec"] == 30
    assert normalized["measurement"]["ppg_source"] == "camera_finger"
    assert normalized["measurement"]["algorithm_version"] == "miniapp-bp-v1.0"


def test_nested_measurement_aliases_are_normalized():
    normalized = normalize_payload(
        {
            "measurement": {"systolic_bp": 136, "diastolic_bp": 86, "quality_score": 0.8},
            "user_profile": {"age": 66},
            "symptoms": {"dizziness": True},
        }
    )
    assert normalized["measurement"]["estimated_sbp"] == 136
    assert normalized["measurement"]["estimated_dbp"] == 86
    assert normalized["measurement"]["signal_quality_score"] == 0.8
    assert normalized["user_profile"]["age"] == 66
    assert normalized["symptoms"]["dizziness"] is True
