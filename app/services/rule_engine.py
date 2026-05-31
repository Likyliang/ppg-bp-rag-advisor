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
    high_motion_artifact = config.get("high_motion_artifact_gte", 0.70)
    moderate_motion_artifact = config.get("moderate_motion_artifact_gte", 0.45)
    poor_finger_coverage = config.get("poor_finger_coverage_lt", 0.60)
    fair_finger_coverage = config.get("fair_finger_coverage_lt", 0.75)

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

    if measurement.motion_artifact_score is not None:
        if measurement.motion_artifact_score >= high_motion_artifact:
            is_usable = False
            quality_level = "low_quality"
            warnings.append("手指移动或运动伪影偏高，本次估算只适合提示重新采集。")
        elif measurement.motion_artifact_score >= moderate_motion_artifact and quality_level != "low_quality":
            quality_level = "fair"
            warnings.append("采集过程中可能存在手指移动影响，建议保持静止后复测。")

    if measurement.finger_coverage_score is not None:
        if measurement.finger_coverage_score < poor_finger_coverage:
            is_usable = False
            quality_level = "low_quality"
            warnings.append("手指覆盖摄像头不完整，本次估算只适合提示重新采集。")
        elif measurement.finger_coverage_score < fair_finger_coverage and quality_level != "low_quality":
            quality_level = "fair"
            warnings.append("手指覆盖可能不够稳定，建议重新覆盖摄像头后复测。")

    if measurement.contact_pressure_level in {"low", "high", "unstable"} and quality_level != "low_quality":
        quality_level = "fair"
        warnings.append("手指按压力度可能影响 PPG 波形，建议放松手指、保持稳定后复测。")

    if measurement.ambient_light_level in {"dim", "bright", "unstable"} and quality_level != "low_quality":
        quality_level = "fair"
        warnings.append("环境光可能影响摄像头 PPG 采集，建议在稳定光线下重新测量。")

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
    if quality.quality_level == "fair":
        intents.extend(["remeasurement", "signal_quality_improvement"])
    if special_population and "medical_consultation" not in intents:
        intents.append("medical_consultation")
    return list(dict.fromkeys(intents))


def _retrieval_intents(
    recommendation_intents: List[str],
    category: str,
    guideline_region: str = "CN",
) -> List[str]:
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
    cn_query_map = {
        "ppg_limitation_explanation": "PPG 无袖带 血压估算 局限 不能替代规范血压测量",
        "validated_upper_arm_cuff_recheck": "中国 高血压 规范测量 上臂式 血压计 复核",
        "remeasurement": "中国 高血压 复测 安静休息 家庭血压 记录",
        "signal_quality_improvement": "手指 摄像头 PPG 信号质量 重新采集 复测",
        "home_bp_monitoring": "国家卫健委 基层高血压 家庭血压 监测 随访 记录",
        "lifestyle": "国家卫健委 高血压 食养 减盐 运动 体重管理 生活方式",
        "medical_consultation": "中国 基层高血压 多次复核 偏高 医生 咨询",
        "emergency_care": "高血压 急症 180 120 胸痛 气短 肢体无力 视物改变",
        "routine_monitoring": "中国 血压 正常范围 定期监测 健康生活方式",
        "healthy_lifestyle": "健康中国 高血压 预防 减盐 运动 健康生活方式",
    }

    queries: List[str] = []
    if guideline_region != "AHA":
        queries.extend(cn_query_map[intent] for intent in recommendation_intents if intent in cn_query_map)
    queries.extend(query_map[intent] for intent in recommendation_intents if intent in query_map)
    if category in {"stage_1_reference_range", "stage_2_reference_range", "severe_range"}:
        if guideline_region != "AHA":
            queries.append(f"中国 高血压 指南 {category} 血压分类 参考范围 140 90")
        queries.append(f"{category} blood pressure reference range")
    if category == "severe_range":
        if guideline_region != "AHA":
            queries.append("中国 高血压 严重偏高 180 120 急症症状 胸痛 肢体无力 视物改变")
        queries.append("severe blood pressure 180 120 emergency symptoms chest pain weakness vision")
    return list(dict.fromkeys(queries))


def _retrieval_allowed_uses(
    recommendation_intents: List[str],
    category: str,
    emergency: bool,
    special_population: bool,
    medication_safety: bool = False,
) -> List[str]:
    uses = {"cuffless_ppg_limitations", "device_advice"}
    intent_map = {
        "validated_upper_arm_cuff_recheck": {"home_bp_monitoring", "device_advice", "remeasurement"},
        "remeasurement": {"home_bp_monitoring", "remeasurement"},
        "signal_quality_improvement": {"signal_quality", "cuffless_ppg_limitations"},
        "home_bp_monitoring": {"home_bp_monitoring", "remeasurement"},
        "lifestyle": {"lifestyle"},
        "healthy_lifestyle": {"lifestyle"},
        "medical_consultation": {"home_bp_monitoring"},
        "emergency_care": {"emergency_alert"},
        "routine_monitoring": {"home_bp_monitoring"},
        "ppg_limitation_explanation": {"cuffless_ppg_limitations"},
    }
    for intent in recommendation_intents:
        uses.update(intent_map.get(intent, set()))
    if category in {"stage_1_reference_range", "stage_2_reference_range", "severe_range", "elevated_reference_range", "normal_reference_range"}:
        uses.add("bp_category_reference")
    if category == "severe_range":
        uses.add("emergency_alert")
    if emergency:
        return ["emergency_alert", "cuffless_ppg_limitations"]
    if special_population:
        uses.add("special_population")
    if medication_safety:
        uses.add("medication_safety")
    return sorted(uses)


def _ppg_feature_quality_queries(payload: MeasurementPayload) -> List[str]:
    measurement = payload.measurement
    config = load_yaml_config("config/bp_thresholds.yaml").get("quality", {})
    queries: List[str] = []

    if (
        measurement.motion_artifact_score is not None
        and measurement.motion_artifact_score >= config.get("moderate_motion_artifact_gte", 0.45)
    ):
        queries.append("PPG motion artifact 手指移动 运动伪影 信号质量 重新采集")
    if (
        measurement.finger_coverage_score is not None
        and measurement.finger_coverage_score < config.get("fair_finger_coverage_lt", 0.75)
    ):
        queries.append("手指覆盖不完整 摄像头 PPG signal quality finger coverage")
    if measurement.contact_pressure_level in {"low", "high", "unstable"}:
        queries.append("PPG contact pressure 手指按压力度 接触压力 波形质量")
    if measurement.ambient_light_level in {"dim", "bright", "unstable"}:
        queries.append("camera PPG ambient light 环境光 光照干扰 signal quality")
    return queries


def run_rule_engine(payload: MeasurementPayload) -> RuleResult:
    quality = _run_quality_rules(payload)
    category, reference = _bp_category(payload, quality)
    emergency, emergency_reasons = _emergency_result(payload)
    special, special_reasons = _special_population(payload)
    risk, urgency = _risk_and_urgency(category, quality, emergency)
    recommendation_intents = _recommendation_intents(category, quality, emergency, special)
    retrieval_intents = _retrieval_intents(recommendation_intents, category, payload.guideline_region)
    retrieval_intents.extend(_ppg_feature_quality_queries(payload))
    retrieval_intents = list(dict.fromkeys(retrieval_intents))
    if payload.user_profile.antihypertensive_medication:
        retrieval_intents.append("blood pressure medication safety do not stop or adjust dose")
    retrieval_allowed_uses = _retrieval_allowed_uses(
        recommendation_intents,
        category,
        emergency,
        special,
        medication_safety=payload.user_profile.antihypertensive_medication,
    )

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
