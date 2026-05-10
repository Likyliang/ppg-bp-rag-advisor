from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

from app.services.config_loader import resolve_project_path


COMMANDS = [
    ("prepare_fulltext_candidates", [sys.executable, "scripts/prepare_fulltext_candidates.py"]),
    ("create_fulltext_summaries", [sys.executable, "scripts/create_fulltext_summaries.py"]),
    ("screen_sources", [sys.executable, "scripts/screen_sources.py"]),
    ("extract_source_notes", [sys.executable, "scripts/extract_source_notes.py", "--clean"]),
    ("ingest_kb", [sys.executable, "scripts/ingest_kb.py"]),
    ("audit_kb", [sys.executable, "scripts/audit_kb.py"]),
    ("evaluate_retrieval", [sys.executable, "scripts/evaluate_retrieval.py"]),
    ("evaluate_reports", [sys.executable, "scripts/evaluate_reports.py"]),
    ("benchmark_report", [sys.executable, "scripts/benchmark_report.py"]),
    ("pytest", [sys.executable, "-m", "pytest"]),
]


STOP_CRITERIA = {
    "min_tests": 60,
    "min_included_sources": 60,
    "min_chunks": 250,
    "min_golden_queries": 100,
    "min_report_fixtures": 50,
    "min_match_rate": 0.95,
    "min_precision_at_5": 0.85,
}


def _run_command(name: str, command: List[str]) -> Dict:
    started = time.time()
    result = subprocess.run(
        command,
        cwd=resolve_project_path("."),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return {
        "name": name,
        "command": " ".join(command),
        "returncode": result.returncode,
        "duration_sec": round(time.time() - started, 3),
        "output_tail": result.stdout[-4000:],
    }


def _load_json(path: str) -> Dict:
    file_path = resolve_project_path(path)
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8"))


def _count_pytest_tests() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=resolve_project_path("."),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    total = 0
    for line in result.stdout.splitlines():
        if line.startswith("tests/") and ":" in line:
            try:
                total += int(line.rsplit(":", 1)[1].strip())
            except ValueError:
                pass
    if total:
        return total
    for line in reversed(result.stdout.splitlines()):
        if " tests collected" in line:
            return int(line.split()[0])
    return 0


def _count_report_fixtures() -> int:
    path = resolve_project_path("tests/fixtures/demo_cases.jsonl")
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def summarize_quality(commands: List[Dict]) -> Dict:
    audit = _load_json("knowledge_base/processed/kb_audit_report.json")
    retrieval = _load_json("knowledge_base/processed/retrieval_evaluation.json").get("summary", {})
    reports = _load_json("knowledge_base/processed/evaluation_results.json").get("summary", {})
    benchmark = _load_json("knowledge_base/processed/report_benchmark.json")
    screen = _load_json("knowledge_base/processed/source_screening_report.json")
    test_count = _count_pytest_tests()
    report_fixture_count = _count_report_fixtures()

    metrics = {
        "commands_ok": all(item["returncode"] == 0 for item in commands),
        "test_count": test_count,
        "included_sources": screen.get("included_count", 0),
        "chunk_count": audit.get("chunk_count", 0),
        "golden_query_count": retrieval.get("query_count", 0),
        "report_fixture_count": report_fixture_count,
        "retrieval_match_rate": retrieval.get("match_rate", 0),
        "retrieval_precision_at_5": retrieval.get("mean_precision_at_5", 0),
        "unsafe_source_leakage_count": retrieval.get("unsafe_source_leakage_count", 999),
        "audit_quality": audit.get("quality", {}),
        "report_summary": reports,
        "report_p95_sec": benchmark.get("p95_sec", 999),
    }
    criteria = {
        "tests": metrics["test_count"] >= STOP_CRITERIA["min_tests"],
        "sources": metrics["included_sources"] >= STOP_CRITERIA["min_included_sources"],
        "chunks": metrics["chunk_count"] >= STOP_CRITERIA["min_chunks"],
        "golden_queries": metrics["golden_query_count"] >= STOP_CRITERIA["min_golden_queries"],
        "report_fixtures": metrics["report_fixture_count"] >= STOP_CRITERIA["min_report_fixtures"],
        "retrieval_match_rate": metrics["retrieval_match_rate"] >= STOP_CRITERIA["min_match_rate"],
        "retrieval_precision_at_5": metrics["retrieval_precision_at_5"] >= STOP_CRITERIA["min_precision_at_5"],
        "unsafe_source_leakage": metrics["unsafe_source_leakage_count"] == 0,
        "audit": all(metrics["audit_quality"].values()) if metrics["audit_quality"] else False,
        "commands": metrics["commands_ok"],
        "performance": metrics["report_p95_sec"] < 3.0,
    }
    return {
        "timestamp": int(time.time()),
        "stop_criteria": STOP_CRITERIA,
        "metrics": metrics,
        "criteria": criteria,
        "passed": all(criteria.values()),
        "commands": commands,
    }


def run_quality_gate(fail_on_stop_criteria: bool = False) -> Dict:
    command_results = [_run_command(name, command) for name, command in COMMANDS]
    summary = summarize_quality(command_results)
    out_path = resolve_project_path("knowledge_base/processed/quality_gate_report.json")
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if fail_on_stop_criteria and not summary["passed"]:
        raise SystemExit(1)
    if not summary["metrics"]["commands_ok"]:
        raise SystemExit(1)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full quality gate and write quality_gate_report.json.")
    parser.add_argument("--strict-stop", action="store_true", help="Exit non-zero if long-run stop criteria are not yet met.")
    args = parser.parse_args()
    summary = run_quality_gate(fail_on_stop_criteria=args.strict_stop)
    print(json.dumps({"passed": summary["passed"], "metrics": summary["metrics"], "criteria": summary["criteria"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
