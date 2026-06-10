"""Tests for the Chapter-6 experiment switches (dedup / citation-enforcement /
query-cache disable / real-LLM eval routing). These guard that the ablation
knobs work AND that default (production / gate) behaviour is unchanged."""

import os

from app.services import retriever
from app.services import generator
from app.services.config_loader import load_yaml_config


# --------------------------------------------------------------- dedup switch


def _settings():
    return load_yaml_config("config/settings.yaml").get("retrieval", {})


def test_per_source_cap_default_is_two():
    assert retriever._resolve_per_source_cap(None, _settings()) == 2


def test_per_source_cap_env_override(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_PER_SOURCE_CAP", "0")
    assert retriever._resolve_per_source_cap(None, _settings()) == 0
    monkeypatch.setenv("RETRIEVAL_PER_SOURCE_CAP", "1")
    assert retriever._resolve_per_source_cap(None, _settings()) == 1


def test_diversify_cap_zero_disables_dedup():
    # 4 chunks, 2 from source A, 2 from source B; cap=0 keeps top-k by order
    ranked = [
        ({"chunk_id": "a1", "source_id": "A"}, 0.9, "q"),
        ({"chunk_id": "a2", "source_id": "A"}, 0.8, "q"),
        ({"chunk_id": "b1", "source_id": "B"}, 0.7, "q"),
        ({"chunk_id": "b2", "source_id": "B"}, 0.6, "q"),
    ]
    capped = retriever._diversify(ranked, limit=3, per_source_cap=2)
    uncapped = retriever._diversify(ranked, limit=3, per_source_cap=0)
    # cap=2 lets at most 2 of A through (here all 3 fit: a1,a2,b1)
    assert [c["chunk_id"] for c, _, _ in capped] == ["a1", "a2", "b1"]
    # cap=0 = pure top-3 (a1,a2,b1 too, since order matches) — but cap=1 differs
    capped1 = retriever._diversify(ranked, limit=3, per_source_cap=1)
    assert [c["chunk_id"] for c, _, _ in capped1] == ["a1", "b1"]
    assert len(uncapped) == 3


# --------------------------------------------- citation-enforcement bypass


def test_citation_enforcement_default_on():
    assert generator._citation_enforcement_enabled(None) is True


def test_citation_enforcement_env_off(monkeypatch):
    monkeypatch.setenv("REPORT_ENFORCE_CITATIONS", "0")
    assert generator._citation_enforcement_enabled(None) is False
    monkeypatch.setenv("REPORT_ENFORCE_CITATIONS", "1")
    assert generator._citation_enforcement_enabled(None) is True


def test_citation_enforcement_explicit_arg_wins(monkeypatch):
    monkeypatch.setenv("REPORT_ENFORCE_CITATIONS", "0")
    assert generator._citation_enforcement_enabled(True) is True


# --------------------------------------------- query-cache disable switch


def test_query_cache_enabled_by_default(monkeypatch):
    monkeypatch.delenv("RETRIEVAL_DISABLE_QUERY_CACHE", raising=False)
    assert retriever._query_cache_enabled() is True


def test_query_cache_disable_switch(monkeypatch):
    monkeypatch.setenv("RETRIEVAL_DISABLE_QUERY_CACHE", "1")
    assert retriever._query_cache_enabled() is False
    monkeypatch.setenv("RETRIEVAL_DISABLE_QUERY_CACHE", "0")
    assert retriever._query_cache_enabled() is True


# --------------------------------------------- evaluate_reports real routing


def test_evaluate_reports_real_specs_exist():
    from scripts.evaluate_reports import REAL_SYSTEM_SPECS, MOCK_SYSTEMS

    assert set(REAL_SYSTEM_SPECS) == {
        "S1_template_only",
        "S2_llm_rag_enforced",
        "S3_llm_rag_unenforced",
        "S4_llm_only",
    }
    # S2/S3/S4 need a provider; S1 does not
    assert REAL_SYSTEM_SPECS["S1_template_only"].get("needs_provider") is None
    assert REAL_SYSTEM_SPECS["S2_llm_rag_enforced"]["needs_provider"] is True
    # S3 carries the citation-enforcement-off env
    assert REAL_SYSTEM_SPECS["S3_llm_rag_unenforced"]["env"]["REPORT_ENFORCE_CITATIONS"] == "0"
    assert MOCK_SYSTEMS == ["llm_only_mock", "rag_only_mock", "rule_rag_safety"]


def test_temp_env_restores(monkeypatch):
    from scripts.evaluate_reports import _temp_env

    monkeypatch.delenv("REPORT_ENFORCE_CITATIONS", raising=False)
    with _temp_env({"REPORT_ENFORCE_CITATIONS": "0"}):
        assert os.environ["REPORT_ENFORCE_CITATIONS"] == "0"
    assert "REPORT_ENFORCE_CITATIONS" not in os.environ
