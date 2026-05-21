import json

from scripts.benchmark_report import benchmark
from scripts.evaluate_reports import evaluate
from scripts.evaluation_runtime import MAX_ALLOWED_CONCURRENCY, resolve_max_concurrency


def _one_case_file(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(
        json.dumps(
            {
                "case_id": "concurrency_case",
                "estimated_sbp": 145,
                "estimated_dbp": 92,
                "heart_rate": 78,
                "signal_quality_score": 0.86,
                "confidence": 0.72,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return str(path)


def test_evaluation_concurrency_is_capped_at_five():
    assert resolve_max_concurrency(99) == MAX_ALLOWED_CONCURRENCY
    assert resolve_max_concurrency(0) == 1


def test_report_evaluation_records_capped_concurrency(tmp_path):
    result = evaluate(cases_path=_one_case_file(tmp_path), max_concurrency=99)
    assert result["max_concurrency"] == MAX_ALLOWED_CONCURRENCY


def test_report_benchmark_records_capped_concurrency(tmp_path):
    result = benchmark(cases_path=_one_case_file(tmp_path), max_concurrency=99)
    assert result["max_concurrency"] == MAX_ALLOWED_CONCURRENCY
