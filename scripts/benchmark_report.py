from __future__ import annotations

import json
import statistics
import time

from app.agents.workflow import generate_report
from app.services.config_loader import resolve_project_path


def _load_cases(path: str) -> list:
    file_path = resolve_project_path(path)
    with file_path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def benchmark(cases_path: str = "tests/fixtures/demo_cases.jsonl") -> dict:
    cases = _load_cases(cases_path)
    durations = []
    for case in cases:
        started = time.perf_counter()
        generate_report(case)
        durations.append(time.perf_counter() - started)
    durations_sorted = sorted(durations)
    p95_index = max(0, int(len(durations_sorted) * 0.95) - 1)
    return {
        "case_count": len(cases),
        "mean_sec": round(statistics.mean(durations), 4) if durations else 0,
        "p95_sec": round(durations_sorted[p95_index], 4) if durations else 0,
        "max_sec": round(max(durations), 4) if durations else 0,
        "target_p95_sec": 3.0,
        "passed": bool(durations) and durations_sorted[p95_index] < 3.0,
    }


def main() -> None:
    result = benchmark()
    out_path = resolve_project_path("knowledge_base/processed/report_benchmark.json")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
