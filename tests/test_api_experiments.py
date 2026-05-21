import json

from scripts.run_api_experiments import run_experiment


def test_api_experiment_caps_concurrency_and_writes_outputs(tmp_path):
    cases_path = tmp_path / "cases.jsonl"
    cases = [
        {"case_id": "api_normal", "estimated_sbp": 118, "estimated_dbp": 76, "signal_quality_score": 0.88},
        {
            "case_id": "api_signal_context",
            "estimated_sbp": 145,
            "estimated_dbp": 92,
            "heart_rate": 82,
            "signal_quality_score": 0.86,
            "confidence": 0.68,
            "capture_duration_sec": 30,
            "ppg_source": "camera_finger",
            "algorithm_version": "miniapp-bp-v1.0",
        },
        {
            "case_id": "api_emergency",
            "estimated_sbp": 185,
            "estimated_dbp": 122,
            "signal_quality_score": 0.9,
            "symptoms": {"chest_pain": True},
        },
    ]
    cases_path.write_text("\n".join(json.dumps(case, ensure_ascii=False) for case in cases), encoding="utf-8")

    output_prefix = tmp_path / "api_experiment"
    result = run_experiment(
        cases_path=str(cases_path),
        max_concurrency=99,
        output_prefix=str(output_prefix),
    )

    assert result["summary"]["max_concurrency"] == 5
    assert result["summary"]["success_rate"] == 1.0
    assert result["summary"]["safety_pass_rate"] == 1.0
    assert result["summary"]["evidence_coverage_rate"] == 1.0
    assert result["summary"]["emergency_consistency_rate"] == 1.0
    assert result["search_summary"]["expected_use_hit_rate"] == 1.0
    assert output_prefix.with_suffix(".json").exists()
    assert output_prefix.with_suffix(".csv").exists()
    assert output_prefix.with_suffix(".md").exists()
