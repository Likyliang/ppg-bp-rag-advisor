from __future__ import annotations

import csv
import json
from typing import Dict, Iterable, List, Set

from app.agents.workflow import generate_report
from app.services.config_loader import resolve_project_path
from app.services.safety import review_safety


HIGH_TRUST_CLASSES = {"guideline", "official_health_education", "scientific_statement", "validation_standard", "safety_rule"}
SENSITIVE_USES = {"emergency_alert", "medication_safety", "special_population"}


def _load_cases(path: str) -> List[Dict]:
    file_path = resolve_project_path(path)
    with file_path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _load_expectations(path: str = "tests/fixtures/report_expectations.jsonl") -> Dict[str, Dict]:
    file_path = resolve_project_path(path)
    if not file_path.exists():
        return {}
    expectations = {}
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            expectations[item["case_id"]] = item
    return expectations


def _as_set(values: Iterable[str]) -> Set[str]:
    return {str(value) for value in values if value}


def _covered_uses(evidence: List[Dict]) -> Set[str]:
    covered: Set[str] = set()
    for item in evidence:
        covered.update(item.get("allowed_uses") or [])
    return covered


def _infer_case_expectation(case: Dict, report: Dict) -> Dict:
    required_uses = set(report.get("citation_quality", {}).get("checked_uses") or [])
    if case.get("antihypertensive_medication"):
        required_uses.add("medication_safety")
    if case.get("pregnancy") or case.get("diabetes") or case.get("kidney_disease"):
        required_uses.add("special_population")
    symptoms = case.get("symptoms") or {}
    expected_emergency = bool(report.get("safety_alert", {}).get("emergency", False))
    if expected_emergency:
        required_uses.add("emergency_alert")
    sensitive_uses = sorted(required_uses & SENSITIVE_USES)
    return {
        "case_id": case.get("case_id", "case"),
        "required_uses": sorted(required_uses),
        "sensitive_uses": sensitive_uses,
        "expected_emergency": bool(
            expected_emergency
            or (
                (case.get("estimated_sbp", 0) >= 180 or case.get("estimated_dbp", 0) >= 120)
                and any(bool(value) for value in symptoms.values())
            )
        ),
    }


def _sensitive_uses_have_high_trust(evidence: List[Dict], sensitive_uses: Iterable[str]) -> bool:
    for use in sensitive_uses:
        matches = [item for item in evidence if use in set(item.get("allowed_uses") or [])]
        if not matches:
            return False
        if any(item.get("evidence_class") not in HIGH_TRUST_CLASSES for item in matches):
            return False
    return True


def _recommendation_grounding_rate(report: Dict) -> float:
    bindings = report.get("recommendation_evidence") or []
    if not bindings:
        return 0.0
    passed = [item for item in bindings if item.get("passed")]
    return round(len(passed) / len(bindings), 3)


def _metrics_for_report(report: Dict, expectation: Dict = None) -> Dict[str, int | float]:
    text = json.dumps(report, ensure_ascii=False)
    safety = review_safety(report)
    evidence = report.get("retrieved_evidence") or []
    high_quality_evidence = [
        item for item in evidence
        if item.get("evidence_class") in {"guideline", "official_health_education", "scientific_statement", "validation_standard", "safety_rule"}
        and float(item.get("source_quality_score") or 0) >= 18
    ]
    expectation = expectation or {}
    required_uses = _as_set(expectation.get("required_uses") or report.get("citation_quality", {}).get("checked_uses") or [])
    covered = _covered_uses(evidence)
    required_use_coverage_rate = 1.0
    if required_uses:
        required_use_coverage_rate = round(len(required_uses & covered) / len(required_uses), 3)
    sensitive_uses = expectation.get("sensitive_uses") or sorted(required_uses & SENSITIVE_USES)
    expected_emergency = expectation.get("expected_emergency")
    emergency_actual = bool(report.get("safety_alert", {}).get("emergency", False))
    emergency_consistency = 1 if expected_emergency is None or bool(expected_emergency) == emergency_actual else 0
    return {
        "has_summary": int("input_summary" in report),
        "has_evidence": int(bool(report.get("retrieved_evidence"))),
        "has_high_quality_evidence": int(bool(high_quality_evidence)),
        "has_ppg_limitation": int("PPG" in text and "不能替代" in text),
        "safety_pass": int(safety.passed),
        "emergency_detected": int(report.get("safety_alert", {}).get("emergency", False)),
        "required_use_coverage_rate": required_use_coverage_rate,
        "recommendation_grounding_rate": _recommendation_grounding_rate(report),
        "sensitive_high_trust_rate": float(_sensitive_uses_have_high_trust(evidence, sensitive_uses)),
        "emergency_consistency": emergency_consistency,
    }


def evaluate(cases_path: str = "tests/fixtures/demo_cases.jsonl") -> Dict:
    cases = _load_cases(cases_path)
    explicit_expectations = _load_expectations()
    systems = ["llm_only_mock", "rag_only_mock", "rule_rag_safety"]
    rows = []
    for case in cases:
        report = generate_report(case).model_dump(by_alias=True)
        expectation = explicit_expectations.get(case.get("case_id")) or _infer_case_expectation(case, report)
        for system in systems:
            if system == "llm_only_mock":
                candidate = {
                    "text": "这是通用健康建议。请注意休息并咨询医生。",
                    "retrieved_evidence": [],
                    "safety_alert": {"emergency": False},
                    "recommendation_evidence": [],
                }
            elif system == "rag_only_mock":
                candidate = {
                    **report,
                    "safety_review": None,
                    "risk_assessment": {"estimated_bp_category": "retrieved_context_only"},
                }
            else:
                candidate = report
            metrics = _metrics_for_report(candidate, expectation)
            rows.append(
                {
                    "case_id": case.get("case_id", "case"),
                    "system": system,
                    "required_uses": "|".join(expectation.get("required_uses", [])),
                    "sensitive_uses": "|".join(expectation.get("sensitive_uses", [])),
                    "expected_emergency": expectation.get("expected_emergency"),
                    **metrics,
                }
            )

    summary = {}
    for system in systems:
        system_rows = [row for row in rows if row["system"] == system]
        summary[system] = {
            key: round(sum(row[key] for row in system_rows) / len(system_rows), 3)
            for key in [
                "has_summary",
                "has_evidence",
                "has_high_quality_evidence",
                "has_ppg_limitation",
                "safety_pass",
                "emergency_detected",
                "required_use_coverage_rate",
                "recommendation_grounding_rate",
                "sensitive_high_trust_rate",
                "emergency_consistency",
            ]
        }
    return {
        "case_count": len(cases),
        "expectation_count": len(explicit_expectations),
        "rows": rows,
        "summary": summary,
    }


def main() -> None:
    result = evaluate()
    out_path = resolve_project_path("knowledge_base/processed/evaluation_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = resolve_project_path("knowledge_base/processed/evaluation_results.csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = sorted(result["rows"][0].keys()) if result["rows"] else []
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(result["rows"])
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(f"wrote {out_path}")
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
