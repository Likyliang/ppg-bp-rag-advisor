from __future__ import annotations

import json
from pathlib import Path

from app.services.config_loader import resolve_project_path


DEMO_CASES = [
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
