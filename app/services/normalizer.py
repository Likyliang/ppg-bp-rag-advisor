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
    "province",
    "residence_area",
    "primary_care_preference",
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

RHYTHM_FIELDS = {
    "available",
    "pulse_rhythm",
    "ibi_cv",
    "ectopic_beat_ratio",
    "pulse_pause_detected",
    "hrv_sdnn_ms",
    "hrv_rmssd_ms",
    "valid_beat_count",
}

CARDIAC_VIBRATION_FIELDS = {
    "available",
    "signal_quality_score",
    "signal_quality_label",
    "motion_artifact_score",
    "sensor_site",
    "beat_count",
    "pep_ms",
    "lvet_ms",
    "ao_ac_interval_ms",
    "s1_s2_amplitude_ratio",
    "ptt_ms",
}

ROOT_FIELDS = {
    "locale",
    "guideline_region",
    "user_question",
    "enable_screening_suggestions",
}


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


def _collect_nested(
    raw_payload: Mapping[str, Any],
    nested_keys: tuple,
    known_fields: set,
    flat_allowlist: set,
) -> Dict[str, Any]:
    """Merge a nested feature object with unambiguous flat top-level keys.

    Nested values win; flat keys only fill gaps and are restricted to
    ``flat_allowlist`` so they cannot be confused with PPG measurement fields.
    """
    collected: Dict[str, Any] = {}
    for nested_key in nested_keys:
        source = raw_payload.get(nested_key)
        if isinstance(source, Mapping):
            collected.update(_copy_known_fields(source, known_fields))
    for key, value in raw_payload.items():
        if key in flat_allowlist and key not in collected:
            collected[key] = _clean_empty(value)
    return collected


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

    # Rhythm features: nested ``rhythm`` object plus unambiguous flat keys.
    rhythm = _collect_nested(
        raw_payload,
        nested_keys=("rhythm",),
        known_fields=RHYTHM_FIELDS,
        flat_allowlist=RHYTHM_FIELDS - {"available"},
    )
    if rhythm:
        normalized["rhythm"] = rhythm

    # Cardiac-vibration / SCG features: nested ``cardiac_vibration``/``scg``
    # object plus flat keys that do not collide with PPG measurement fields.
    cardiac_vibration = _collect_nested(
        raw_payload,
        nested_keys=("cardiac_vibration", "scg"),
        known_fields=CARDIAC_VIBRATION_FIELDS,
        flat_allowlist={
            "pep_ms",
            "lvet_ms",
            "ao_ac_interval_ms",
            "s1_s2_amplitude_ratio",
            "ptt_ms",
            "sensor_site",
            "beat_count",
        },
    )
    if cardiac_vibration:
        normalized["cardiac_vibration"] = cardiac_vibration

    for field in ROOT_FIELDS:
        if field in raw_payload:
            normalized[field] = _clean_empty(raw_payload[field])

    return normalized
