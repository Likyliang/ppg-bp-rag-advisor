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
            "age": 45,
        }
    )
    assert payload.measurement.estimated_sbp == 145
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
