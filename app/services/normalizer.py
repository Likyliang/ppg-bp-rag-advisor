from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict

from app.services.config_loader import load_yaml_config


USER_PROFILE_FIELDS = {
    "age",
    "sex",
    "height_cm",
    "weight_kg",
    "bmi",
    "smoker",
    "diabetes",
    "kidney_disease",
    "cvd_history",
    "pregnancy",
    "antihypertensive_medication",
    "medication_names",
}

SYMPTOM_FIELDS = {
    "chest_pain",
    "shortness_of_breath",
    "back_pain",
    "numbness_or_weakness",
    "vision_change",
    "speech_difficulty",
    "severe_headache",
    "dizziness",
}

ROOT_FIELDS = {"locale", "guideline_region", "user_question"}


def _clean_empty(value: Any) -> Any:
    if value == "":
        return None
    return value


def _canonical_aliases() -> Dict[str, str]:
    mapping = load_yaml_config("config/field_mapping.yaml")
    aliases: Dict[str, str] = {}
    for canonical, spec in mapping.items():
        aliases[canonical.lower()] = canonical
        for alias in spec.get("aliases", []):
            aliases[str(alias).lower()] = canonical
    return aliases


def _canonicalize_measurement(source: Mapping[str, Any]) -> Dict[str, Any]:
    alias_map = _canonical_aliases()
    output: Dict[str, Any] = {}
    for key, value in source.items():
        canonical = alias_map.get(str(key).lower())
        if canonical:
            output[canonical] = _clean_empty(value)
    return output


def _copy_known_fields(source: Mapping[str, Any], fields: set) -> Dict[str, Any]:
    return {key: _clean_empty(value) for key, value in source.items() if key in fields}


def normalize_payload(raw_payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize aliases and flat payloads into the canonical API shape."""
    if not isinstance(raw_payload, Mapping):
        raise TypeError("payload must be a mapping")

    normalized: Dict[str, Any] = {}

    measurement_source = raw_payload.get("measurement") or {}
    if isinstance(measurement_source, Mapping):
        measurement = _canonicalize_measurement(measurement_source)
    else:
        measurement = {}
    for key, value in _canonicalize_measurement(raw_payload).items():
        measurement.setdefault(key, value)
    if measurement:
        normalized["measurement"] = measurement
    elif "measurement" in raw_payload:
        normalized["measurement"] = measurement_source

    profile_source = raw_payload.get("user_profile") or {}
    user_profile: Dict[str, Any] = {}
    if isinstance(profile_source, Mapping):
        user_profile.update(_copy_known_fields(profile_source, USER_PROFILE_FIELDS))
    user_profile.update(
        {
            key: _clean_empty(value)
            for key, value in raw_payload.items()
            if key in USER_PROFILE_FIELDS and key not in user_profile
        }
    )
    if user_profile:
        normalized["user_profile"] = user_profile

    symptoms_source = raw_payload.get("symptoms") or {}
    symptoms: Dict[str, Any] = {}
    if isinstance(symptoms_source, Mapping):
        symptoms.update(_copy_known_fields(symptoms_source, SYMPTOM_FIELDS))
    symptoms.update(
        {
            key: _clean_empty(value)
            for key, value in raw_payload.items()
            if key in SYMPTOM_FIELDS and key not in symptoms
        }
    )
    if symptoms:
        normalized["symptoms"] = symptoms

    for field in ROOT_FIELDS:
        if field in raw_payload:
            normalized[field] = _clean_empty(raw_payload[field])

    return normalized
