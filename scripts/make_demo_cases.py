from __future__ import annotations

import json
from pathlib import Path

from app.services.config_loader import resolve_project_path


BASE_DEMO_CASES = [
    {"case_id": "normal_good_quality", "estimated_sbp": 116, "estimated_dbp": 74, "signal_quality_score": 0.9, "confidence": 0.8},
    {"case_id": "high_good_quality", "estimated_sbp": 145, "estimated_dbp": 92, "heart_rate": 82, "signal_quality_score": 0.86, "confidence": 0.68, "age": 45},
    {"case_id": "high_low_quality", "estimated_sbp": 150, "estimated_dbp": 95, "signal_quality_score": 0.42, "confidence": 0.4},
    {"case_id": "severe_no_symptoms", "estimated_sbp": 184, "estimated_dbp": 121, "signal_quality_score": 0.88, "symptoms": {}},
    {"case_id": "severe_chest_pain", "estimated_sbp": 185, "estimated_dbp": 122, "signal_quality_score": 0.9, "symptoms": {"chest_pain": True}},
    {"case_id": "medication_user", "estimated_sbp": 136, "estimated_dbp": 86, "signal_quality_score": 0.82, "antihypertensive_medication": True},
    {"case_id": "diabetes_user", "estimated_sbp": 132, "estimated_dbp": 84, "signal_quality_score": 0.83, "diabetes": True},
    {"case_id": "alias_input", "SBP": 142, "DBP": 91, "HR": 78, "quality": "good", "conf": 0.7},
    {"case_id": "fair_quality", "estimated_sbp": 128, "estimated_dbp": 78, "signal_quality_score": 0.7, "capture_duration_sec": 15},
    {"case_id": "pregnancy", "estimated_sbp": 130, "estimated_dbp": 82, "signal_quality_score": 0.84, "pregnancy": True},
]


def _generated_cases():
    cases = list(BASE_DEMO_CASES)
    scenarios = [
        ("normal", 112, 72, {}),
        ("elevated", 126, 78, {}),
        ("stage1", 134, 84, {}),
        ("stage2", 146, 94, {}),
        ("severe_no_symptom", 184, 118, {}),
        ("severe_emergency", 186, 122, {"symptoms": {"chest_pain": True}}),
        ("low_quality", 148, 93, {"signal_quality_score": 0.45, "confidence": 0.42}),
        ("fair_short", 128, 79, {"signal_quality_score": 0.7, "capture_duration_sec": 12}),
        ("older", 138, 86, {"age": 70}),
        ("pregnancy", 132, 84, {"pregnancy": True}),
        ("diabetes", 136, 86, {"diabetes": True}),
        ("kidney", 136, 86, {"kidney_disease": True}),
        ("cvd", 142, 90, {"cvd_history": True}),
        ("medication", 140, 88, {"antihypertensive_medication": True}),
        ("dizziness", 130, 82, {"symptoms": {"dizziness": True}}),
        ("vision", 181, 119, {"symptoms": {"vision_change": True}}),
        ("speech", 182, 121, {"symptoms": {"speech_difficulty": True}}),
        ("weakness", 183, 121, {"symptoms": {"numbness_or_weakness": True}}),
        ("bilingual", 145, 92, {"locale": "bilingual"}),
        ("aha_region", 145, 92, {"guideline_region": "AHA"}),
    ]
    for round_index in range(2):
        for name, sbp, dbp, extra in scenarios:
            case = {
                "case_id": f"{name}_{round_index + 1}",
                "estimated_sbp": sbp + round_index,
                "estimated_dbp": dbp,
                "heart_rate": 72 + round_index,
                "signal_quality_score": extra.get("signal_quality_score", 0.86),
                "confidence": extra.get("confidence", 0.72),
                "age": extra.get("age", 45 + round_index),
                "capture_duration_sec": extra.get("capture_duration_sec", 30),
                "guideline_region": extra.get("guideline_region", "CN"),
                "locale": extra.get("locale", "zh-CN"),
            }
            for field in ("pregnancy", "diabetes", "kidney_disease", "cvd_history", "antihypertensive_medication"):
                if field in extra:
                    case[field] = extra[field]
            if "symptoms" in extra:
                case["symptoms"] = extra["symptoms"]
            cases.append(case)
    return cases[:50]


DEMO_CASES = _generated_cases()


def write_demo_cases(path: str = "tests/fixtures/demo_cases.jsonl") -> Path:
    out_path = resolve_project_path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for case in DEMO_CASES:
            handle.write(json.dumps(case, ensure_ascii=False) + "\n")
    return out_path


if __name__ == "__main__":
    output = write_demo_cases()
    print(f"wrote {output}")
