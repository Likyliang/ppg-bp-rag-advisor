from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.schemas.measurement import MeasurementPayload
from app.schemas.rule_result import RuleResult
from app.schemas.screening import ScreeningResult, ScreeningSuggestion
from app.services.config_loader import load_yaml_config


CONFIG_PATH = "config/screening_rules.yaml"

# Confidence is hard-capped: a consumer PPG/SCG signal cannot support a
# high-confidence cardiac claim, so anything above "moderate" is clamped down.
_CONFIDENCE_RANK = {"low": 0, "moderate": 1}
# Recognized levels above the cap → clamped to moderate (vs. unknown → low).
_ABOVE_CAP = {"high", "very_high", "very high", "strong", "definite"}


def _load_config() -> Dict[str, Any]:
    return load_yaml_config(CONFIG_PATH)


def _clamp_confidence(value: Optional[str]) -> str:
    value = (value or "low").strip().lower()
    # Recognized over-cap levels clamp down to moderate; unknown tokens fall to
    # the conservative default of low.
    if value in _ABOVE_CAP:
        return "moderate"
    if value not in _CONFIDENCE_RANK:
        return "low"
    return "moderate" if _CONFIDENCE_RANK[value] >= _CONFIDENCE_RANK["moderate"] else "low"


def _scg_signal_good(payload: MeasurementPayload) -> bool:
    scg = payload.cardiac_vibration
    if scg.signal_quality_label == "good":
        return True
    return scg.signal_quality_score is not None and scg.signal_quality_score >= 0.75


def _requires_met(requires: Dict[str, Any], payload: MeasurementPayload, rule_result: RuleResult) -> bool:
    for key, expected in requires.items():
        # ``requires`` holds positive gates only: a falsy value means "no
        # constraint" (not "must be absent"), which avoids inverted-gate bugs.
        if not expected:
            continue
        if key == "rhythm_available":
            if bool(payload.rhythm.available) != bool(expected):
                return False
        elif key == "ppg_signal_usable":
            if rule_result.quality.is_usable != bool(expected):
                return False
        elif key == "scg_available":
            if bool(payload.cardiac_vibration.available) != bool(expected):
                return False
        elif key == "scg_signal_good":
            if _scg_signal_good(payload) != bool(expected):
                return False
        # Unknown requirement keys are ignored rather than silently failing.
    return True


def _evaluate_triggers(
    triggers: Dict[str, Any], payload: MeasurementPayload, rule_result: RuleResult
) -> List[str]:
    """Return human-readable evidence phrases for each satisfied trigger."""
    rhythm = payload.rhythm
    measurement = payload.measurement
    scg = payload.cardiac_vibration
    fired: List[str] = []

    for key, value in triggers.items():
        if key == "pulse_rhythm_irregular" and value and rhythm.pulse_rhythm == "irregular":
            fired.append("脉搏节律不规则")
        elif key == "ibi_cv_gte" and rhythm.ibi_cv is not None and rhythm.ibi_cv >= value:
            fired.append(f"脉搏间期变异偏大（CV≈{rhythm.ibi_cv:g}）")
        elif (
            key == "ectopic_beat_ratio_gte"
            and rhythm.ectopic_beat_ratio is not None
            and rhythm.ectopic_beat_ratio >= value
        ):
            fired.append(f"出现疑似早搏的比例偏高（约{rhythm.ectopic_beat_ratio:.0%}）")
        elif key == "pulse_pause_detected" and value and rhythm.pulse_pause_detected:
            fired.append("检测到脉搏间歇/停顿")
        elif key == "heart_rate_gte" and measurement.heart_rate is not None and measurement.heart_rate >= value:
            fired.append(f"心率约{measurement.heart_rate:g}次/分")
        elif key == "heart_rate_lte" and measurement.heart_rate is not None and measurement.heart_rate <= value:
            fired.append(f"心率约{measurement.heart_rate:g}次/分")
        elif key == "bp_category_in" and rule_result.estimated_bp_category in (value or []):
            fired.append("估算血压处于偏高参考范围")
        elif key == "pep_ms_gte" and scg.pep_ms is not None and scg.pep_ms >= value:
            fired.append(f"PEP≈{scg.pep_ms:g}ms")
        elif key == "ptt_ms_lte" and scg.ptt_ms is not None and scg.ptt_ms <= value:
            fired.append(f"PTT≈{scg.ptt_ms:g}ms")
    return fired


def _beats_sufficient(payload: MeasurementPayload, min_valid_beats: int) -> bool:
    """Rhythm-based suggestions need enough analysable beats; missing count is allowed."""
    count = payload.rhythm.valid_beat_count
    if count is None:
        return True
    return count >= min_valid_beats


def _build_rationale(template: str, evidence: List[str], payload: MeasurementPayload) -> str:
    evidence_text = "、".join(evidence) if evidence else "信号特征提示"
    heart_rate = payload.measurement.heart_rate
    heart_rate_text = f"{heart_rate:g}" if heart_rate is not None else "—"
    try:
        return template.format(evidence=evidence_text, heart_rate=heart_rate_text)
    except (KeyError, IndexError):
        return template


def run_screening(payload: MeasurementPayload, rule_result: RuleResult) -> ScreeningResult:
    """Produce hedged "建议进一步排查" suggestions from PPG/SCG features.

    Gated by both the global config switch and the per-request opt-in. In an
    emergency the screening section is suppressed so the emergency block and
    120/急诊 guidance stay front-and-centre.
    """
    config = _load_config()
    enabled = bool(config.get("enabled", False))
    requested = bool(payload.enable_screening_suggestions)
    result = ScreeningResult(enabled=enabled, requested=requested, produced=False)

    if not enabled:
        result.notes.append("排查建议功能未在配置中启用。")
        return result
    if not requested:
        result.notes.append("本次请求未开启排查建议（enable_screening_suggestions=False）。")
        return result
    if rule_result.emergency:
        result.notes.append("急症情境下抑制排查建议，优先急救与就医。")
        return result

    min_valid_beats = int(config.get("min_valid_beats", 0) or 0)
    suggestions: List[ScreeningSuggestion] = []
    for condition in config.get("conditions", []):
        requires = condition.get("requires", {}) or {}
        if not _requires_met(requires, payload, rule_result):
            continue
        if requires.get("rhythm_available") and not _beats_sufficient(payload, min_valid_beats):
            result.notes.append(
                f"{condition.get('id', '?')}：可分析心搏数不足（<{min_valid_beats}），不给排查建议。"
            )
            continue
        evidence = _evaluate_triggers(condition.get("triggers", {}) or {}, payload, rule_result)
        if not evidence:
            continue
        suggestions.append(
            ScreeningSuggestion(
                condition_id=str(condition.get("id", "")),
                label=str(condition.get("label", "")),
                confidence=_clamp_confidence(condition.get("confidence")),
                rationale=_build_rationale(
                    str(condition.get("rationale_template", "")), evidence, payload
                ),
                screening_action=str(condition.get("screening_action", "")),
                retrieval_intents=list(condition.get("retrieval_intents", []) or []),
                allowed_uses=list(condition.get("allowed_uses", []) or []),
            )
        )

    result.suggestions = suggestions
    result.produced = bool(suggestions)
    if not suggestions:
        result.notes.append("本次信号特征未触发任何排查建议。")
    return result


def aggregate_retrieval(result: ScreeningResult) -> Tuple[List[str], List[str]]:
    """Collect dedup'd retrieval intents and allowed_uses from all suggestions."""
    intents: List[str] = []
    uses: List[str] = []
    for suggestion in result.suggestions:
        intents.extend(suggestion.retrieval_intents)
        uses.extend(suggestion.allowed_uses)
    return list(dict.fromkeys(intents)), list(dict.fromkeys(uses))
