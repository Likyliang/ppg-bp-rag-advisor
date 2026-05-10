from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from app.agents.workflow import generate_report
from app.services.config_loader import resolve_project_path
from app.services.safety import review_safety


def _load_cases(path: str) -> List[Dict]:
    file_path = resolve_project_path(path)
    with file_path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _metrics_for_report(report: Dict) -> Dict[str, int]:
    text = json.dumps(report, ensure_ascii=False)
    safety = review_safety(report)
    evidence = report.get("retrieved_evidence") or []
    high_quality_evidence = [
        item for item in evidence
        if item.get("evidence_class") in {"guideline", "official_health_education", "scientific_statement", "validation_standard", "safety_rule"}
        and float(item.get("source_quality_score") or 0) >= 18
    ]
    return {
        "has_summary": int("input_summary" in report),
        "has_evidence": int(bool(report.get("retrieved_evidence"))),
        "has_high_quality_evidence": int(bool(high_quality_evidence)),
        "has_ppg_limitation": int("PPG" in text and "不能替代" in text),
        "safety_pass": int(safety.passed),
        "emergency_detected": int(report.get("safety_alert", {}).get("emergency", False)),
    }


def evaluate(cases_path: str = "tests/fixtures/demo_cases.jsonl") -> Dict:
    cases = _load_cases(cases_path)
    systems = ["llm_only_mock", "rag_only_mock", "rule_rag_safety"]
    rows = []
    for case in cases:
        report = generate_report(case).model_dump(by_alias=True)
        for system in systems:
            if system == "llm_only_mock":
                candidate = {
                    "text": "这是通用健康建议。请注意休息并咨询医生。",
                    "retrieved_evidence": [],
                    "safety_alert": {"emergency": False},
                }
            elif system == "rag_only_mock":
                candidate = {
                    **report,
                    "safety_review": None,
                    "risk_assessment": {"estimated_bp_category": "retrieved_context_only"},
                }
            else:
                candidate = report
            metrics = _metrics_for_report(candidate)
            rows.append({"case_id": case.get("case_id", "case"), "system": system, **metrics})

    summary = {}
    for system in systems:
        system_rows = [row for row in rows if row["system"] == system]
        summary[system] = {
            key: round(sum(row[key] for row in system_rows) / len(system_rows), 3)
            for key in ["has_summary", "has_evidence", "has_high_quality_evidence", "has_ppg_limitation", "safety_pass", "emergency_detected"]
        }
    return {"case_count": len(cases), "rows": rows, "summary": summary}


def main() -> None:
    result = evaluate()
    out_path = resolve_project_path("knowledge_base/processed/evaluation_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
