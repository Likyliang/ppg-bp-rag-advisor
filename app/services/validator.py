from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from app.schemas.measurement import MeasurementPayload
from app.services.normalizer import normalize_payload


def parse_payload(raw_payload: Mapping) -> MeasurementPayload:
    normalized = normalize_payload(raw_payload)
    return MeasurementPayload.model_validate(normalized)


def validate_payload(raw_payload: Mapping) -> MeasurementPayload:
    try:
        return parse_payload(raw_payload)
    except ValidationError:
        raise
