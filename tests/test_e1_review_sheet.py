"""Tests for the E1 review-sheet sampling protocol (sensitive=all, non-sensitive=30%)."""

import json

import scripts.exp_e1_make_review_sheet as mod


def _make_pool(tmp_path, monkeypatch):
    # 2 queries: q0 sensitive (4 pairs), q1 non-sensitive (10 pairs)
    rows = []
    for i in range(4):
        rows.append(
            {"qid": 0, "query": "急症", "sensitive": True, "expected_uses": ["emergency_alert"],
             "chunk_id": f"s{i}", "title": f"S{i}", "snippet": "x", "judge_grade": i % 3}
        )
    for i in range(10):
        rows.append(
            {"qid": 1, "query": "生活方式", "sensitive": False, "expected_uses": ["lifestyle"],
             "chunk_id": f"n{i}", "title": f"N{i}", "snippet": "y", "judge_grade": i % 3}
        )
    pool = tmp_path / "pool.jsonl"
    pool.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    review_jsonl = tmp_path / "review.jsonl"
    review_md = tmp_path / "review.md"
    monkeypatch.setattr(mod, "resolve_project_path", lambda p: {
        mod.POOL_PATH: pool,
        mod.REVIEW_JSONL: review_jsonl,
        mod.REVIEW_MD: review_md,
    }[p])
    return pool, review_jsonl, review_md


def test_sensitive_all_selected_nonsensitive_sampled(tmp_path, monkeypatch):
    pool, review_jsonl, review_md = _make_pool(tmp_path, monkeypatch)
    summary = mod.build_review_sheet(nonsensitive_fraction=0.30, seed=13)
    assert summary["pool_pairs"] == 14
    assert summary["sensitive_pairs"] == 4
    # 4 sensitive (all) + round(10*0.3)=3 non-sensitive = 7
    assert summary["selected_for_review"] == 7
    assert review_md.exists()
    # round-trip JSONL has the full pool with flags
    review_rows = [json.loads(l) for l in review_jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(review_rows) == 14
    sensitive_selected = [r for r in review_rows if r["qid"] == 0]
    assert all(r["selected_for_review"] for r in sensitive_selected)
    assert all("human_grade" in r for r in review_rows)


def test_sampling_is_deterministic(tmp_path, monkeypatch):
    _make_pool(tmp_path, monkeypatch)
    s1 = mod.build_review_sheet(seed=7)
    _make_pool(tmp_path, monkeypatch)
    s2 = mod.build_review_sheet(seed=7)
    assert s1["selected_for_review"] == s2["selected_for_review"]


def test_apply_review_writes_human_grade_back(tmp_path, monkeypatch):
    pool, review_jsonl, review_md = _make_pool(tmp_path, monkeypatch)
    mod.build_review_sheet(seed=13)
    # simulate a human filling one human_grade
    rows = [json.loads(l) for l in review_jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows[0]["human_grade"] = 2
    review_jsonl.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    result = mod.apply_review_into_pool()
    assert result["human_filled"] == 1
    pool_rows = [json.loads(l) for l in pool.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert pool_rows[0]["human_grade"] == 2


def test_judge_throttle_enforces_min_interval(monkeypatch):
    import time
    import scripts.relevance_judge as rj
    monkeypatch.setenv("EVAL_LLM_MIN_INTERVAL_SEC", "0.3")
    rj._LAST_REQUEST_AT[0] = 0.0
    t0 = time.monotonic()
    for _ in range(4):
        rj._throttle()
    # 4 calls at 0.3s spacing -> >= ~0.9s after the first
    assert time.monotonic() - t0 >= 0.85


def test_judge_throttle_disabled_when_zero(monkeypatch):
    import time
    import scripts.relevance_judge as rj
    monkeypatch.setenv("EVAL_LLM_MIN_INTERVAL_SEC", "0")
    rj._LAST_REQUEST_AT[0] = 0.0
    t0 = time.monotonic()
    for _ in range(5):
        rj._throttle()
    assert time.monotonic() - t0 < 0.2
