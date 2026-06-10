from __future__ import annotations

import argparse
import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Dict, Iterable, List, Optional, Set

from app.agents.workflow import generate_report
from app.services.config_loader import resolve_project_path
from app.services.safety import review_safety

try:
    from scripts.evaluation_runtime import add_concurrency_arg, resolve_max_concurrency
except ModuleNotFoundError:  # pragma: no cover - direct script execution path.
    from evaluation_runtime import add_concurrency_arg, resolve_max_concurrency


HIGH_TRUST_CLASSES = {"guideline", "official_health_education", "scientific_statement", "validation_standard", "safety_rule"}
SENSITIVE_USES = {"emergency_alert", "medication_safety", "special_population"}


# E2 generation-ablation system variants. Each maps to a real generate_report
# run driven by report_mode + env overrides — NO hardcoded strawman. The mock
# trio below stays the offline-gate default so run_quality_gate keeps passing
# without API keys.
#   S1 template_only      : rule+RAG+safety, no LLM
#   S2 llm_rag_enforced   : LLM RAG, citation enforcement ON (production)
#   S3 llm_rag_unenforced : LLM RAG, citation enforcement OFF (ablation)
#   S4 llm_only           : LLM with NO retrieved evidence injected
REAL_SYSTEM_SPECS: Dict[str, Dict[str, object]] = {
    "S1_template_only": {"report_mode": "template_only", "env": {}},
    "S2_llm_rag_enforced": {
        "report_mode": "llm_rag",
        "env": {"REPORT_ENFORCE_CITATIONS": "1"},
        "needs_provider": True,
    },
    "S3_llm_rag_unenforced": {
        "report_mode": "llm_rag",
        "env": {"REPORT_ENFORCE_CITATIONS": "0"},
        "needs_provider": True,
    },
    "S4_llm_only": {"report_mode": "llm_only", "env": {}, "needs_provider": True},
}
MOCK_SYSTEMS = ["llm_only_mock", "rag_only_mock", "rule_rag_safety"]


@contextmanager
def _temp_env(overrides: Dict[str, str]):
    """Apply env overrides for one system pass, then restore (process-level)."""
    saved = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


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


SUMMARY_KEYS = [
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


def _mock_candidate(system: str, report: Dict) -> Dict:
    """Legacy offline strawman systems (kept so the gate runs without API keys)."""
    if system == "llm_only_mock":
        return {
            "text": "这是通用健康建议。请注意休息并咨询医生。",
            "retrieved_evidence": [],
            "safety_alert": {"emergency": False},
            "recommendation_evidence": [],
        }
    if system == "rag_only_mock":
        return {
            **report,
            "safety_review": None,
            "risk_assessment": {"estimated_bp_category": "retrieved_context_only"},
        }
    return report


def _evaluate_case_mock(case: Dict, explicit_expectations: Dict[str, Dict], systems: List[str]) -> List[Dict]:
    report = generate_report(case).model_dump(by_alias=True)
    expectation = explicit_expectations.get(case.get("case_id")) or _infer_case_expectation(case, report)
    rows = []
    for system in systems:
        candidate = _mock_candidate(system, report)
        metrics = _metrics_for_report(candidate, expectation)
        rows.append(_row(case, system, expectation, metrics, generation_mode="mock"))
    return rows


def _evaluate_case_real(case: Dict, explicit_expectations: Dict[str, Dict], system: str, report_mode: str) -> Dict:
    report_obj = generate_report(case, report_mode=report_mode)
    report = report_obj.model_dump(by_alias=True)
    expectation = explicit_expectations.get(case.get("case_id")) or _infer_case_expectation(case, report)
    metrics = _metrics_for_report(report, expectation)
    row = _row(case, system, expectation, metrics, generation_mode=report_obj.generation_mode)
    # Carry the full report body + references so E3 (citation faithfulness) can
    # judge sentences without re-generating.
    row["_report"] = {
        "case_id": case.get("case_id", "case"),
        "system": system,
        "generation_mode": report_obj.generation_mode,
        "markdown": report.get("markdown_report", ""),
        "references": report.get("references", []),
    }
    return row


def _row(case: Dict, system: str, expectation: Dict, metrics: Dict, generation_mode: str) -> Dict:
    return {
        "case_id": case.get("case_id", "case"),
        "system": system,
        "generation_mode": generation_mode,
        "required_uses": "|".join(expectation.get("required_uses", [])),
        "sensitive_uses": "|".join(expectation.get("sensitive_uses", [])),
        "expected_emergency": expectation.get("expected_emergency"),
        **metrics,
    }


def _summarize(rows: List[Dict], systems: List[str]) -> Dict:
    summary = {}
    for system in systems:
        system_rows = [row for row in rows if row["system"] == system]
        if not system_rows:
            continue
        summary[system] = {
            key: round(sum(row[key] for row in system_rows) / len(system_rows), 3) for key in SUMMARY_KEYS
        }
    return summary


def evaluate(
    cases_path: str = "tests/fixtures/demo_cases.jsonl",
    max_concurrency: int = None,
    systems: Optional[List[str]] = None,
    real: bool = False,
    provider: Optional[str] = None,
) -> Dict:
    """Evaluate report fixtures.

    Default (real=False): the offline mock trio — keeps the quality gate green
    without API keys. real=True: the E2 ablation variants S1–S4, each a true
    generate_report run with the variant's report_mode + env, run one system at
    a time (env applied per pass) to avoid cross-thread env races.
    """
    cases = _load_cases(cases_path)
    explicit_expectations = _load_expectations()
    concurrency = resolve_max_concurrency(max_concurrency)
    rows: List[Dict] = []

    if not real:
        systems = systems or MOCK_SYSTEMS
        if concurrency == 1:
            case_rows = [_evaluate_case_mock(case, explicit_expectations, systems) for case in cases]
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                case_rows = list(
                    executor.map(lambda case: _evaluate_case_mock(case, explicit_expectations, systems), cases)
                )
        for item in case_rows:
            rows.extend(item)
        return {
            "case_count": len(cases),
            "expectation_count": len(explicit_expectations),
            "max_concurrency": concurrency,
            "mode": "mock",
            "systems": systems,
            "rows": rows,
            "summary": _summarize(rows, systems),
        }

    systems = systems or list(REAL_SYSTEM_SPECS)
    provider_env = {"LLM_PROVIDER": provider} if provider else {}
    for system in systems:
        spec = REAL_SYSTEM_SPECS[system]
        env = dict(spec.get("env", {}))
        if spec.get("needs_provider"):
            env.update(provider_env)
        report_mode = str(spec["report_mode"])
        with _temp_env(env):
            if concurrency == 1:
                system_rows = [
                    _evaluate_case_real(case, explicit_expectations, system, report_mode) for case in cases
                ]
            else:
                with ThreadPoolExecutor(max_workers=concurrency) as executor:
                    system_rows = list(
                        executor.map(
                            lambda case: _evaluate_case_real(case, explicit_expectations, system, report_mode),
                            cases,
                        )
                    )
        rows.extend(system_rows)
    # Split the report bodies (for E3) out of the metric rows.
    reports = [row.pop("_report") for row in rows if "_report" in row]
    reports_path = resolve_project_path("knowledge_base/processed/e2_reports.jsonl")
    reports_path.parent.mkdir(parents=True, exist_ok=True)
    with reports_path.open("w", encoding="utf-8") as handle:
        for rep in reports:
            handle.write(json.dumps(rep, ensure_ascii=False) + "\n")
    return {
        "case_count": len(cases),
        "expectation_count": len(explicit_expectations),
        "max_concurrency": concurrency,
        "mode": "real",
        "provider": provider or os.getenv("LLM_PROVIDER", "mock"),
        "systems": systems,
        "reports_path": str(reports_path),
        "rows": rows,
        "summary": _summarize(rows, systems),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate report fixtures with a capped experiment concurrency.")
    parser.add_argument("--cases-path", default="tests/fixtures/demo_cases.jsonl")
    parser.add_argument(
        "--real",
        action="store_true",
        help="E2 ablation: run real generate_report variants S1-S4 (needs LLM key for S2-S4). "
        "Default off = offline mock trio used by the quality gate.",
    )
    parser.add_argument(
        "--systems",
        nargs="*",
        default=None,
        help="Subset of system names to run (real: S1_template_only/S2_llm_rag_enforced/"
        "S3_llm_rag_unenforced/S4_llm_only; mock: llm_only_mock/rag_only_mock/rule_rag_safety).",
    )
    parser.add_argument("--provider", default=None, help="Override LLM_PROVIDER for real S2-S4 (e.g. deepseek).")
    parser.add_argument(
        "--out-prefix",
        default=None,
        help="Output filename prefix (default: evaluation_results for mock, "
        "evaluation_results_real for --real, so the gate's mock artifacts are not overwritten).",
    )
    add_concurrency_arg(parser)
    args = parser.parse_args()
    result = evaluate(
        cases_path=args.cases_path,
        max_concurrency=args.max_concurrency,
        systems=args.systems,
        real=args.real,
        provider=args.provider,
    )
    prefix = args.out_prefix or ("evaluation_results_real" if args.real else "evaluation_results")
    out_path = resolve_project_path(f"knowledge_base/processed/{prefix}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = resolve_project_path(f"knowledge_base/processed/{prefix}.csv")
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
