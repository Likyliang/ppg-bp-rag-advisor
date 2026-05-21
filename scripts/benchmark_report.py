from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from app.agents.workflow import generate_report
from app.services.config_loader import resolve_project_path

try:
    from scripts.evaluation_runtime import add_concurrency_arg, resolve_max_concurrency
except ModuleNotFoundError:  # pragma: no cover - direct script execution path.
    from evaluation_runtime import add_concurrency_arg, resolve_max_concurrency


def _load_cases(path: str) -> list:
    file_path = resolve_project_path(path)
    with file_path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _timed_generate(case: dict) -> float:
    started = time.perf_counter()
    generate_report(case)
    return time.perf_counter() - started


def benchmark(cases_path: str = "tests/fixtures/demo_cases.jsonl", max_concurrency: int = None) -> dict:
    cases = _load_cases(cases_path)
    concurrency = resolve_max_concurrency(max_concurrency)
    if concurrency == 1:
        durations = [_timed_generate(case) for case in cases]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            durations = list(executor.map(_timed_generate, cases))
    durations_sorted = sorted(durations)
    p95_index = max(0, int(len(durations_sorted) * 0.95) - 1)
    return {
        "case_count": len(cases),
        "max_concurrency": concurrency,
        "mean_sec": round(statistics.mean(durations), 4) if durations else 0,
        "p95_sec": round(durations_sorted[p95_index], 4) if durations else 0,
        "max_sec": round(max(durations), 4) if durations else 0,
        "target_p95_sec": 3.0,
        "passed": bool(durations) and durations_sorted[p95_index] < 3.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark report generation with capped experiment concurrency.")
    parser.add_argument("--cases-path", default="tests/fixtures/demo_cases.jsonl")
    add_concurrency_arg(parser)
    args = parser.parse_args()
    result = benchmark(cases_path=args.cases_path, max_concurrency=args.max_concurrency)
    out_path = resolve_project_path("knowledge_base/processed/report_benchmark.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
