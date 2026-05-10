from __future__ import annotations

from typing import List, Tuple

from app.schemas.measurement import MeasurementPayload, Symptoms
from app.schemas.rule_result import QualityResult, RuleResult
from app.services.config_loader import load_yaml_config


def _symptom_labels() -> dict:
    return load_yaml_config("config/safety_terms.yaml").get("symptom_labels", {})


def _active_symptoms(symptoms: Symptoms, symptom_names: List[str]) -> List[str]:
    labels = _symptom_labels()
    active = []
    for name in symptom_names:
        if bool(getattr(symptoms, name, False)):
            active.append(labels.get(name, name))
    return active


def _run_quality_rules(payload: MeasurementPayload) -> QualityResult:
    config = load_yaml_config("config/bp_thresholds.yaml").get("quality", {})
    measurement = payload.measurement
    warnings: List[str] = []

    poor_score = config.get("poor_signal_score_lt", 0.60)
    fair_score = config.get("fair_signal_score_lt", 0.75)
    low_confidence = config.get("low_confidence_lt", 0.50)
    short_duration = config.get("short_capture_duration_lt_sec", 20)

    is_usable = True
    quality_level = "acceptable"

    if measurement.signal_quality_label == "poor":
        is_usable = False
        quality_level = "low_quality"
        warnings.append("信号质量标记为 poor，本次结果只适合提示重新采集。")

    if measurement.signal_quality_score is not None:
        if measurement.signal_quality_score < poor_score:
            is_usable = False
            quality_level = "low_quality"
            warnings.append("信号质量分低于阈值，本次估算不适合做风险解释。")
        elif measurement.signal_quality_score < fair_score and quality_level != "low_quality":
            quality_level = "fair"
            warnings.append("信号质量一般，建议复测确认趋势。")

    confidence_level = "unknown"
    if measurement.confidence is not None:
        confidence_level = "low" if measurement.confidence < low_confidence else "acceptable"
        if confidence_level == "low":
            warnings.append("上游估算置信度偏低，应优先复测。")

    if (
        measurement.capture_duration_sec is not None
        and measurement.capture_duration_sec < short_duration
    ):
        warnings.append("采集时长偏短，建议重新采集不少于 20 秒。")
        if quality_level == "acceptable":
            quality_level = "fair"

    if is_usable and quality_level == "acceptable":
        explanation = "本次信号质量可用于生成保守的趋势解释。"
    elif is_usable:
        explanation = "本次信号质量存在不确定性，报告会优先建议复测。"
    else:
        explanation = "本次信号质量不足，不生成强风险结论。"

    return QualityResult(
        is_usable=is_usable,
        quality_level=quality_level,
        confidence_level=confidence_level,
        explanation=explanation,
        warnings=warnings,
    )


def _bp_values(payload: MeasurementPayload) -> Tuple[float, float]:
    return payload.measurement.estimated_sbp, payload.measurement.estimated_dbp


def _bp_category(payload: MeasurementPayload, quality: QualityResult) -> Tuple[str, str]:
    sbp, dbp = _bp_values(payload)
    if sbp is None or dbp is None:
        return "unavailable", "missing_estimated_bp"
    if not quality.is_usable:
        return "not_interpretable_low_quality", "quality_rule"

    region = "AHA" if payload.guideline_region == "AHA" else "CN"
    thresholds = load_yaml_config("config/bp_thresholds.yaml")

    severe = thresholds.get("emergency", {})
    if sbp >= severe.get("sbp_gte", 180) or dbp >= severe.get("dbp_gte", 120):
        return "severe_range", f"{region}_severe_reference_range"

    if sbp >= 140 or dbp >= 90:
        return "stage_2_reference_range", f"{region}_stage_2_reference_range"
    if 130 <= sbp <= 139 or 80 <= dbp <= 89:
        return "stage_1_reference_range", f"{region}_stage_1_reference_range"
    if 120 <= sbp <= 129 and dbp < 80:
        return "elevated_reference_range", f"{region}_elevated_reference_range"
    if sbp < 120 and dbp < 80:
        return "normal_reference_range", f"{region}_normal_reference_range"
    return "borderline_reference_range", f"{region}_borderline_reference_range"


def _emergency_result(payload: MeasurementPayload) -> Tuple[bool, List[str]]:
    sbp, dbp = _bp_values(payload)
    if sbp is None or dbp is None:
        return False, []
    config = load_yaml_config("config/bp_thresholds.yaml").get("emergency", {})
    severe_bp = sbp >= config.get("sbp_gte", 180) or dbp >= config.get("dbp_gte", 120)
    active = _active_symptoms(payload.symptoms, config.get("symptoms", []))
    if severe_bp and active:
        return True, [f"估算血压达到严重偏高范围，并伴随{label}" for label in active]
    return False, []


def _special_population(payload: MeasurementPayload) -> Tuple[bool, List[str]]:
    profile = payload.user_profile
    symptoms = payload.symptoms
    reasons: List[str] = []

    if profile.age is not None and profile.age >= 65:
        reasons.append("年龄达到 65 岁及以上")
    if profile.pregnancy:
        reasons.append("妊娠或可能妊娠")
    if profile.diabetes:
        reasons.append("合并糖尿病")
    if profile.kidney_disease:
        reasons.append("合并慢性肾脏病")
    if profile.cvd_history:
        reasons.append("既往心血管病史")
    if profile.antihypertensive_medication:
        reasons.append("正在使用降压药")
    if symptoms.chest_pain or symptoms.shortness_of_breath or symptoms.severe_headache:
        reasons.append("存在需要重视的症状")

    return bool(reasons), reasons


def _risk_and_urgency(category: str, quality: QualityResult, emergency: bool) -> Tuple[str, str]:
    if emergency:
        return "possible_emergency", "emergency"
    if not quality.is_usable:
        return "remeasurement_required", "remeasurement_first"
    if category == "severe_range":
        return "urgent_attention", "urgent_recheck"
    if category in {"stage_2_reference_range", "stage_1_reference_range"}:
        return "elevated_attention", "non_emergency"
    if category == "elevated_reference_range":
        return "lifestyle_attention", "non_emergency"
    if category == "unavailable":
        return "insufficient_input", "non_emergency"
    return "routine_monitoring", "non_emergency"


def _recommendation_intents(
    category: str,
    quality: QualityResult,
    emergency: bool,
    special_population: bool,
) -> List[str]:
    intents = ["ppg_limitation_explanation", "validated_upper_arm_cuff_recheck"]
    if emergency:
        return ["emergency_care", "ppg_limitation_explanation"]
    if not quality.is_usable:
        return ["remeasurement", "signal_quality_improvement", "validated_upper_arm_cuff_recheck"]
    if category in {"stage_1_reference_range", "stage_2_reference_range", "severe_range"}:
        intents.extend(["remeasurement", "home_bp_monitoring", "lifestyle", "medical_consultation"])
    elif category == "elevated_reference_range":
        intents.extend(["home_bp_monitoring", "lifestyle"])
    else:
        intents.extend(["routine_monitoring", "healthy_lifestyle"])
    if special_population and "medical_consultation" not in intents:
        intents.append("medical_consultation")
    return intents


def _retrieval_intents(recommendation_intents: List[str], category: str) -> List[str]:
    query_map = {
        "ppg_limitation_explanation": "PPG cuffless blood pressure estimation limitations",
        "validated_upper_arm_cuff_recheck": "home blood pressure monitoring validated upper arm cuff",
        "remeasurement": "blood pressure remeasurement rest five minutes home monitoring",
        "signal_quality_improvement": "finger camera PPG signal quality limitations",
        "home_bp_monitoring": "home blood pressure monitoring repeated readings record",
        "lifestyle": "hypertension lifestyle sodium exercise weight smoking sleep",
        "medical_consultation": "when to consult doctor for high blood pressure readings",
        "emergency_care": "hypertensive emergency symptoms 180 120 chest pain weakness vision",
        "routine_monitoring": "normal blood pressure routine monitoring healthy lifestyle",
        "healthy_lifestyle": "healthy lifestyle blood pressure prevention",
    }
    queries = [query_map[intent] for intent in recommendation_intents if intent in query_map]
    if category in {"stage_1_reference_range", "stage_2_reference_range", "severe_range"}:
        queries.append(f"{category} blood pressure reference range")
    return list(dict.fromkeys(queries))


def _retrieval_allowed_uses(
    recommendation_intents: List[str],
    category: str,
    emergency: bool,
    special_population: bool,
) -> List[str]:
    uses = {"cuffless_ppg_limitations", "device_advice"}
    intent_map = {
        "validated_upper_arm_cuff_recheck": {"home_bp_monitoring", "device_advice", "remeasurement"},
        "remeasurement": {"home_bp_monitoring", "remeasurement"},
        "signal_quality_improvement": {"signal_quality", "cuffless_ppg_limitations"},
        "home_bp_monitoring": {"home_bp_monitoring", "remeasurement"},
        "lifestyle": {"lifestyle"},
        "healthy_lifestyle": {"lifestyle"},
        "medical_consultation": {"special_population", "home_bp_monitoring"},
        "emergency_care": {"emergency_alert"},
        "routine_monitoring": {"home_bp_monitoring"},
        "ppg_limitation_explanation": {"cuffless_ppg_limitations"},
    }
    for intent in recommendation_intents:
        uses.update(intent_map.get(intent, set()))
    if category in {"stage_1_reference_range", "stage_2_reference_range", "severe_range", "elevated_reference_range", "normal_reference_range"}:
        uses.add("bp_category_reference")
    if emergency:
        return ["emergency_alert", "cuffless_ppg_limitations"]
    if special_population:
        uses.add("special_population")
    return sorted(uses)


def run_rule_engine(payload: MeasurementPayload) -> RuleResult:
    quality = _run_quality_rules(payload)
    category, reference = _bp_category(payload, quality)
    emergency, emergency_reasons = _emergency_result(payload)
    special, special_reasons = _special_population(payload)
    risk, urgency = _risk_and_urgency(category, quality, emergency)
    recommendation_intents = _recommendation_intents(category, quality, emergency, special)
    retrieval_intents = _retrieval_intents(recommendation_intents, category)
    retrieval_allowed_uses = _retrieval_allowed_uses(recommendation_intents, category, emergency, special)

    warnings = list(quality.warnings)
    if category == "unavailable":
        warnings.append("缺少估算收缩压或舒张压，无法进行范围参考解释。")

    return RuleResult(
        quality=quality,
        estimated_bp_category=category,
        bp_category_reference=reference,
        risk_level=risk,
        urgency_level=urgency,
        emergency=emergency,
        emergency_reasons=emergency_reasons,
        special_population=special,
        special_population_reasons=special_reasons,
        recommendation_intents=recommendation_intents,
        retrieval_intents=retrieval_intents,
        retrieval_allowed_uses=retrieval_allowed_uses,
        warnings=warnings,
        guideline_region_used="AHA" if payload.guideline_region == "AHA" else "CN",
    )
