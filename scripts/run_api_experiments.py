from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from app.services.config_loader import resolve_project_path

try:
    from scripts.evaluation_runtime import add_concurrency_arg, resolve_max_concurrency
except ModuleNotFoundError:  # pragma: no cover - direct script execution path.
    from evaluation_runtime import add_concurrency_arg, resolve_max_concurrency


HIGH_TRUST_CLASSES = {
    "guideline",
    "official_health_education",
    "scientific_statement",
    "validation_standard",
    "safety_rule",
}
SENSITIVE_USES = {"emergency_alert", "medication_safety", "special_population"}


SEARCH_PROBES = [
    {
        "probe_id": "ppg_motion",
        "query": "运动后 PPG 血压估算偏高，运动伪差会影响结果吗？",
        "expected_uses": {"signal_quality", "remeasurement"},
    },
    {
        "probe_id": "low_quality_signal",
        "query": "PPG 信号质量低、采集时间短时应该怎么解释血压估算结果？",
        "expected_uses": {"signal_quality", "remeasurement"},
    },
    {
        "probe_id": "emergency_chest_pain",
        "query": "PPG 估算 185/122 且胸痛，应该怎么提醒？",
        "expected_uses": {"emergency_alert"},
    },
    {
        "probe_id": "medication_user",
        "query": "正在吃降压药，PPG 估算偏低能不能停药？",
        "expected_uses": {"medication_safety"},
    },
    {
        "probe_id": "pregnancy_high_bp",
        "query": "孕妇 PPG 估算血压偏高，报告应该如何保守提醒？",
        "expected_uses": {"special_population"},
    },
    {
        "probe_id": "validated_device",
        "query": "PPG 或无袖带设备能不能替代上臂式血压计？",
        "expected_uses": {"validated_devices", "cuffless_ppg_limitations"},
    },
]


def _load_jsonl(path: str, max_cases: Optional[int] = None) -> List[Dict[str, Any]]:
    file_path = resolve_project_path(path)
    cases: List[Dict[str, Any]] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            cases.append(json.loads(line))
            if max_cases and len(cases) >= max_cases:
                break
    return cases


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile))
    return round(ordered[index], 4)


def _mean(rows: List[Dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(float(row.get(key) or 0) for row in rows) / len(rows), 3)


def _covered_uses(evidence: Iterable[Dict[str, Any]]) -> Set[str]:
    uses: Set[str] = set()
    for item in evidence:
        uses.update(item.get("allowed_uses") or [])
    return uses


def _has_high_trust_for_sensitive_use(evidence: Iterable[Dict[str, Any]], sensitive_uses: Set[str]) -> bool:
    evidence_items = list(evidence)
    for use in sensitive_uses:
        matches = [item for item in evidence_items if use in set(item.get("allowed_uses") or [])]
        if not matches:
            return False
        if not all(item.get("evidence_class") in HIGH_TRUST_CLASSES for item in matches):
            return False
    return True


def _expected_emergency(case: Dict[str, Any]) -> bool:
    symptoms = case.get("symptoms") or {}
    sbp = case.get("estimated_sbp", case.get("SBP", 0))
    dbp = case.get("estimated_dbp", case.get("DBP", 0))
    severe_value = sbp >= 180 or dbp >= 120
    return bool(severe_value and any(bool(value) for value in symptoms.values()))


def _input_context_preserved(case: Dict[str, Any], report: Dict[str, Any]) -> bool:
    summary = report.get("input_summary") or {}
    expected_fields = [
        ("heart_rate", "HR"),
        ("signal_quality_score", "quality_score"),
        ("confidence", "conf"),
        ("capture_duration_sec", "duration"),
        ("ppg_source", "sensor_source"),
        ("algorithm_version", "model_version"),
    ]
    checked = 0
    preserved = 0
    for canonical, alias in expected_fields:
        input_value = case.get(canonical, case.get(alias))
        if input_value is None:
            continue
        checked += 1
        if summary.get(canonical) == input_value:
            preserved += 1
    return checked == preserved


def _post_report(case: Dict[str, Any]) -> Dict[str, Any]:
    case_id = case.get("case_id", "case")
    with TestClient(app) as client:
        preview = client.post("/api/v1/reports/preview-rules", json=case)
        start = time.perf_counter()
        response = client.post("/api/v1/reports/generate", json=case)
        elapsed = round(time.perf_counter() - start, 4)
    row: Dict[str, Any] = {
        "case_id": case_id,
        "preview_status_code": preview.status_code,
        "report_status_code": response.status_code,
        "latency_sec": elapsed,
        "success": int(response.status_code == 200),
    }
    if response.status_code != 200:
        row["error"] = response.text[:500]
        return row
    body = response.json()
    evidence = body.get("retrieved_evidence") or []
    covered = _covered_uses(evidence)
    sensitive_uses = covered & SENSITIVE_USES
    row.update(
        {
            "estimated_bp_category": body.get("risk_assessment", {}).get("estimated_bp_category"),
            "risk_level": body.get("risk_assessment", {}).get("risk_level"),
            "urgency_level": body.get("risk_assessment", {}).get("urgency_level"),
            "safety_pass": int(bool(body.get("safety_review", {}).get("pass"))),
            "emergency_detected": int(bool(body.get("safety_alert", {}).get("emergency"))),
            "expected_emergency": int(_expected_emergency(case)),
            "evidence_count": len(evidence),
            "recommendation_grounding_rate": body.get("citation_quality", {}).get("recommendation_grounding_rate", 0),
            "input_context_preserved": int(_input_context_preserved(case, body)),
            "sensitive_high_trust": int(_has_high_trust_for_sensitive_use(evidence, sensitive_uses)),
        }
    )
    return row


def _run_search_probe(probe: Dict[str, Any]) -> Dict[str, Any]:
    with TestClient(app) as client:
        response = client.post("/api/v1/kb/search", json={"queries": [probe["query"]], "top_k": 5})
    if response.status_code != 200:
        return {
            "probe_id": probe["probe_id"],
            "status_code": response.status_code,
            "expected_use_hit": 0,
            "evidence_count": 0,
            "error": response.text[:500],
        }
    body = response.json()
    evidence = body.get("evidence") or []
    covered = _covered_uses(evidence)
    expected = set(probe["expected_uses"])
    sensitive_expected = expected & SENSITIVE_USES
    return {
        "probe_id": probe["probe_id"],
        "status_code": response.status_code,
        "query": probe["query"],
        "expected_uses": "|".join(sorted(expected)),
        "covered_uses": "|".join(sorted(covered)),
        "expected_use_hit": int(bool(expected & covered)),
        "sensitive_high_trust": int(_has_high_trust_for_sensitive_use(evidence, sensitive_expected)),
        "evidence_count": len(evidence),
        "top_source_ids": "|".join(item.get("source_id", "") for item in evidence[:3]),
    }


def _summarize_report_rows(rows: List[Dict[str, Any]], max_concurrency: int) -> Dict[str, Any]:
    success_rows = [row for row in rows if row.get("success")]
    latencies = [float(row["latency_sec"]) for row in success_rows]
    emergency_rows = [row for row in success_rows if row.get("expected_emergency")]
    return {
        "case_count": len(rows),
        "success_count": len(success_rows),
        "max_concurrency": max_concurrency,
        "success_rate": round(len(success_rows) / len(rows), 3) if rows else 0,
        "mean_latency_sec": round(statistics.mean(latencies), 4) if latencies else 0,
        "p50_latency_sec": _percentile(latencies, 0.5),
        "p95_latency_sec": _percentile(latencies, 0.95),
        "max_latency_sec": round(max(latencies), 4) if latencies else 0,
        "safety_pass_rate": _mean(success_rows, "safety_pass"),
        "input_context_preservation_rate": _mean(success_rows, "input_context_preserved"),
        "evidence_coverage_rate": round(
            sum(1 for row in success_rows if int(row.get("evidence_count") or 0) > 0) / len(success_rows),
            3,
        )
        if success_rows
        else 0,
        "mean_recommendation_grounding_rate": round(
            statistics.mean(float(row.get("recommendation_grounding_rate") or 0) for row in success_rows),
            3,
        )
        if success_rows
        else 0,
        "sensitive_high_trust_rate": _mean(success_rows, "sensitive_high_trust"),
        "emergency_consistency_rate": round(
            sum(1 for row in emergency_rows if row.get("emergency_detected") == row.get("expected_emergency"))
            / len(emergency_rows),
            3,
        )
        if emergency_rows
        else 1.0,
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, result: Dict[str, Any]) -> None:
    summary = result["summary"]
    search = result["search_summary"]
    lines = [
        "# API Experiment Report",
        "",
        f"- Generated at: {result['generated_at']}",
        f"- Mode: {result['mode']}",
        f"- Cases: {summary['case_count']}",
        f"- Max concurrency: {summary['max_concurrency']}",
        f"- Success rate: {summary['success_rate']}",
        f"- Safety pass rate: {summary['safety_pass_rate']}",
        f"- Input context preservation rate: {summary['input_context_preservation_rate']}",
        f"- Evidence coverage rate: {summary['evidence_coverage_rate']}",
        f"- Recommendation grounding rate: {summary['mean_recommendation_grounding_rate']}",
        f"- Sensitive high-trust rate: {summary['sensitive_high_trust_rate']}",
        f"- Emergency consistency rate: {summary['emergency_consistency_rate']}",
        f"- P95 latency: {summary['p95_latency_sec']}s",
        f"- KB search expected-use hit rate: {search['expected_use_hit_rate']}",
        "",
        "This is an exploratory API-level experiment. It does not replace the calibrated query-only retrieval evaluation or strict quality gate.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_experiment(
    cases_path: str = "tests/fixtures/demo_cases.jsonl",
    max_cases: Optional[int] = None,
    max_concurrency: Optional[int] = None,
    output_prefix: str = "outputs/experiments/api_experiment_2026-05-21",
) -> Dict[str, Any]:
    cases = _load_jsonl(cases_path, max_cases=max_cases)
    concurrency = resolve_max_concurrency(max_concurrency)
    if concurrency == 1:
        report_rows = [_post_report(case) for case in cases]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            report_rows = list(executor.map(_post_report, cases))
    search_rows = [_run_search_probe(probe) for probe in SEARCH_PROBES]
    search_summary = {
        "probe_count": len(search_rows),
        "expected_use_hit_rate": _mean(search_rows, "expected_use_hit"),
        "sensitive_high_trust_rate": _mean(search_rows, "sensitive_high_trust"),
    }
    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "fastapi_testclient_api_routes",
        "cases_path": cases_path,
        "summary": _summarize_report_rows(report_rows, concurrency),
        "search_summary": search_summary,
        "report_rows": report_rows,
        "search_rows": search_rows,
    }

    prefix_path = resolve_project_path(output_prefix)
    prefix_path.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix_path.with_suffix(".json")
    csv_path = prefix_path.with_suffix(".csv")
    md_path = prefix_path.with_suffix(".md")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(csv_path, report_rows)
    _write_markdown(md_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run exploratory API-level experiments with capped concurrency.")
    parser.add_argument("--cases-path", default="tests/fixtures/demo_cases.jsonl")
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument("--output-prefix", default="outputs/experiments/api_experiment_2026-05-21")
    add_concurrency_arg(parser)
    args = parser.parse_args()
    result = run_experiment(
        cases_path=args.cases_path,
        max_cases=args.max_cases,
        max_concurrency=args.max_concurrency,
        output_prefix=args.output_prefix,
    )
    print(json.dumps({"summary": result["summary"], "search_summary": result["search_summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
