"""Tests for the literature management layer (LibraryManager + REST API).

All mutations run against a temporary copy of the real catalog so the
committed knowledge base is never touched.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

import app.api.library as library_api
from app.services.library_manager import (
    DuplicateSourceError,
    EVIDENCE_TIERS,
    LibraryError,
    LibraryManager,
    SourceNotFoundError,
    evidence_tier,
)

REAL_EXTRA = Path("knowledge_base/sources/source_catalog_extra.yaml")


def _valid_source(**overrides):
    source = {
        "source_id": "unit_test_paper_2026",
        "title": "Unit Test Paper on PPG BP",
        "organization": "Test Society",
        "url": "https://example.org/unit-test-paper",
        "year": 2026,
        "language": "en",
        "region": "global",
        "topic": "cuffless_ppg_limitations",
        "evidence_class": "review",
        "source_type": "review",
        "allowed_uses": ["cuffless_ppg_limitations", "signal_quality"],
        "screening": {
            "authority": 4,
            "recency": 5,
            "relevance": 5,
            "accessibility": 4,
            "safety_applicability": 4,
        },
    }
    source.update(overrides)
    return source


@pytest.fixture()
def manager(tmp_path):
    """LibraryManager backed by a temp copy of the real extra catalog."""

    catalog = tmp_path / "catalog.yaml"
    shutil.copy(REAL_EXTRA, catalog)
    return LibraryManager(
        catalog_files=[str(catalog)],
        writable_catalog=str(catalog),
        trash_catalog=str(tmp_path / "trash.yaml"),
        auto_rescreen=False,
        manage_fulltext=False,
    )


# --------------------------------------------------------------------------- #
# Grading (分级)
# --------------------------------------------------------------------------- #
def test_evidence_tier_mapping():
    assert evidence_tier("guideline") == "A"
    assert evidence_tier("review") == "B"
    assert evidence_tier("research_context") == "C"
    assert evidence_tier("unknown-or-empty") == "C"


def test_every_allowed_evidence_class_has_a_tier():
    from app.services.source_catalog import ALLOWED_EVIDENCE_CLASSES

    mapped = {c for classes in EVIDENCE_TIERS.values() for c in classes}
    assert ALLOWED_EVIDENCE_CLASSES <= mapped


# --------------------------------------------------------------------------- #
# Read / organise
# --------------------------------------------------------------------------- #
def test_list_and_stats_span_catalog(manager):
    sources = manager.list_sources()
    assert len(sources) >= 100
    assert all("tier" in s and "source_quality_score" in s for s in sources)

    stats = manager.stats()
    assert stats["total"] == len(sources)
    assert stats["included"] + stats["excluded"] == stats["total"]
    assert set(stats["by_tier"]) == set(EVIDENCE_TIERS)


def test_journal_tier_filter_and_stats(manager):
    manager.add_source(_valid_source(source_id="jt_t1", journal="Nature", journal_tier=1))
    manager.add_source(_valid_source(source_id="jt_t3", title="Weak paper", url="https://ex.org/weak",
                                     journal="Obscure J", journal_tier=3))
    t3 = manager.list_sources(journal_tier=3)
    assert "jt_t3" in [s["source_id"] for s in t3]
    assert "jt_t1" not in [s["source_id"] for s in t3]
    assert all(s.get("journal_tier") == 3 for s in t3)

    by_journal = manager.list_sources(journal="nature")
    assert "jt_t1" in [s["source_id"] for s in by_journal]

    stats = manager.stats()
    assert stats["by_journal_tier"]["1"] >= 1
    assert stats["by_journal_tier"]["3"] >= 1


def test_list_filters(manager):
    a_tier = manager.list_sources(tier="A")
    assert a_tier and all(s["tier"] == "A" for s in a_tier)

    lifestyle = manager.list_sources(topic="lifestyle")
    assert lifestyle and all(s["topic"] == "lifestyle" for s in lifestyle)

    disabled_only = manager.list_sources(include=False)
    assert all(s.get("include") is False for s in disabled_only)


# --------------------------------------------------------------------------- #
# Add
# --------------------------------------------------------------------------- #
def test_add_source_roundtrip(manager):
    result = manager.add_source(_valid_source())
    assert result.action == "added"
    assert result.source["tier"] == "B"
    assert result.source["source_quality_score"] == 22

    fetched = manager.get_source("unit_test_paper_2026")
    assert fetched["title"] == "Unit Test Paper on PPG BP"

    # Persisted and re-parseable.
    reloaded = LibraryManager(
        catalog_files=manager.catalog_files,
        writable_catalog=manager.writable_catalog,
        auto_rescreen=False,
    )
    assert reloaded.exists("unit_test_paper_2026")


def test_add_rejects_duplicate_id(manager):
    manager.add_source(_valid_source())
    with pytest.raises(DuplicateSourceError):
        manager.add_source(_valid_source(url="https://example.org/other"))


def test_add_rejects_duplicate_identity(manager):
    manager.add_source(_valid_source())
    with pytest.raises(DuplicateSourceError):
        # Same url -> same identity hash, different id.
        manager.add_source(_valid_source(source_id="another_id"))


def test_add_below_threshold_registers_excluded_not_error(manager):
    # A source whose screening sums below the include threshold must register as
    # excluded (include=false), not raise — this is what autofill-add relies on.
    low = _valid_source(
        source_id="low_score_paper",
        screening={"authority": 2, "recency": 2, "relevance": 2, "accessibility": 2, "safety_applicability": 2},
    )
    result = manager.add_source(low)
    assert result.action == "added"
    assert result.source["include"] is False
    assert result.source["source_quality_score"] == 10


def test_add_rejects_invalid_evidence_class(manager):
    with pytest.raises(LibraryError):
        manager.add_source(_valid_source(evidence_class="not_a_class"))


def test_add_rejects_invalid_allowed_use(manager):
    with pytest.raises(LibraryError):
        manager.add_source(_valid_source(allowed_uses=["totally_made_up_use"]))


def test_add_string_allowed_uses_is_split(manager):
    result = manager.add_source(_valid_source(allowed_uses="cuffless_ppg_limitations, signal_quality"))
    assert result.source["allowed_uses"] == ["cuffless_ppg_limitations", "signal_quality"]


# --------------------------------------------------------------------------- #
# Update / enable / remove
# --------------------------------------------------------------------------- #
def test_update_merges_fields(manager):
    manager.add_source(_valid_source())
    result = manager.update_source("unit_test_paper_2026", {"topic": "measurement_quality"})
    assert result.action == "updated"
    assert manager.get_source("unit_test_paper_2026")["topic"] == "measurement_quality"
    # Untouched fields survive a merge.
    assert manager.get_source("unit_test_paper_2026")["title"] == "Unit Test Paper on PPG BP"


def test_disable_and_enable(manager):
    manager.add_source(_valid_source())
    manager.set_include("unit_test_paper_2026", False)
    assert manager.get_source("unit_test_paper_2026")["include"] is False
    manager.set_include("unit_test_paper_2026", True)
    assert manager.get_source("unit_test_paper_2026")["include"] is True


def test_soft_remove_keeps_entry(manager):
    manager.add_source(_valid_source())
    result = manager.remove_source("unit_test_paper_2026", soft=True)
    assert result.action == "disabled"
    assert manager.exists("unit_test_paper_2026")
    assert manager.get_source("unit_test_paper_2026")["include"] is False


def test_hard_remove_deletes_entry(manager):
    manager.add_source(_valid_source())
    result = manager.remove_source("unit_test_paper_2026")
    assert result.action == "removed"
    assert not manager.exists("unit_test_paper_2026")


def test_operations_on_missing_source_raise(manager):
    with pytest.raises(SourceNotFoundError):
        manager.get_source("does_not_exist")
    with pytest.raises(SourceNotFoundError):
        manager.update_source("does_not_exist", {"topic": "lifestyle"})
    with pytest.raises(SourceNotFoundError):
        manager.remove_source("does_not_exist")


# --------------------------------------------------------------------------- #
# Recycle bin (soft delete)
# --------------------------------------------------------------------------- #
def test_trash_moves_out_of_active_and_is_recoverable(manager):
    manager.add_source(_valid_source())
    result = manager.trash_source("unit_test_paper_2026", reason="dup")
    assert result.action == "trashed"
    assert not manager.exists("unit_test_paper_2026")  # gone from active catalog

    trash = manager.list_trash()
    assert [t["source_id"] for t in trash] == ["unit_test_paper_2026"]
    assert trash[0]["_trash_reason"] == "dup"


def test_restore_brings_source_back(manager):
    manager.add_source(_valid_source())
    manager.trash_source("unit_test_paper_2026")
    result = manager.restore_source("unit_test_paper_2026")
    assert result.action == "restored"
    assert manager.exists("unit_test_paper_2026")
    assert manager.list_trash() == []


def test_restore_conflict_when_active_exists(manager):
    manager.add_source(_valid_source())
    manager.trash_source("unit_test_paper_2026")
    # Re-add a source with the same id, then a restore must not clobber it.
    manager.add_source(_valid_source())
    with pytest.raises(DuplicateSourceError):
        manager.restore_source("unit_test_paper_2026")


def test_purge_is_permanent(manager):
    manager.add_source(_valid_source())
    manager.trash_source("unit_test_paper_2026")
    manager.purge_source("unit_test_paper_2026")
    assert manager.list_trash() == []
    with pytest.raises(SourceNotFoundError):
        manager.restore_source("unit_test_paper_2026")


def test_empty_trash(manager):
    manager.add_source(_valid_source())
    manager.trash_source("unit_test_paper_2026")
    result = manager.empty_trash()
    assert result["purged"] == 1
    assert manager.list_trash() == []


def test_trashed_source_absent_from_screening(manager):
    manager.add_source(_valid_source())
    manager.trash_source("unit_test_paper_2026")
    assert not manager.exists("unit_test_paper_2026")
    assert all(s["source_id"] != "unit_test_paper_2026" for s in manager.list_sources())


def test_add_produces_minimal_diff(manager):
    """A single add appends one block and touches only the date line."""

    catalog_path = Path(manager.writable_catalog)
    before = catalog_path.read_text(encoding="utf-8").splitlines()
    manager.add_source(_valid_source())
    after = catalog_path.read_text(encoding="utf-8").splitlines()

    # Existing lines are preserved except the single `updated:` line.
    changed_existing = [
        b for b in before if b not in after and not b.startswith("updated:")
    ]
    assert changed_existing == []
    # New content parses and contains the new id.
    assert any("unit_test_paper_2026" in line for line in after)
    yaml.safe_load(catalog_path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# REST API
# --------------------------------------------------------------------------- #
@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    catalog = tmp_path / "api_catalog.yaml"
    shutil.copy(REAL_EXTRA, catalog)
    trash = tmp_path / "api_trash.yaml"
    monkeypatch.setattr(
        library_api,
        "_manager",
        lambda: LibraryManager(
            catalog_files=[str(catalog)],
            writable_catalog=str(catalog),
            trash_catalog=str(trash),
            auto_rescreen=False,
            manage_fulltext=False,
        ),
    )
    return TestClient(app)


def test_api_taxonomy_and_stats(api_client):
    assert api_client.get("/api/v1/library/taxonomy").status_code == 200
    stats = api_client.get("/api/v1/library/stats")
    assert stats.status_code == 200
    assert stats.json()["included"] >= 1


def test_api_crud_lifecycle(api_client):
    body = _valid_source()

    created = api_client.post("/api/v1/library/sources", json=body)
    assert created.status_code == 201
    assert created.json()["source"]["tier"] == "B"

    assert api_client.post("/api/v1/library/sources", json=body).status_code == 409

    got = api_client.get("/api/v1/library/sources/unit_test_paper_2026")
    assert got.status_code == 200

    patched = api_client.patch(
        "/api/v1/library/sources/unit_test_paper_2026", json={"topic": "measurement_quality"}
    )
    assert patched.status_code == 200
    assert patched.json()["source"]["topic"] == "measurement_quality"

    disabled = api_client.put(
        "/api/v1/library/sources/unit_test_paper_2026/include", json={"include": False}
    )
    assert disabled.status_code == 200
    assert disabled.json()["action"] == "disabled"

    # Default delete is a soft delete into the recycle bin.
    deleted = api_client.delete("/api/v1/library/sources/unit_test_paper_2026")
    assert deleted.status_code == 200
    assert deleted.json()["action"] == "trashed"
    assert api_client.get("/api/v1/library/sources/unit_test_paper_2026").status_code == 404


def test_api_recycle_bin_lifecycle(api_client):
    api_client.post("/api/v1/library/sources", json=_valid_source())
    api_client.delete("/api/v1/library/sources/unit_test_paper_2026")

    trash = api_client.get("/api/v1/library/trash")
    assert trash.status_code == 200 and trash.json()["count"] == 1

    restored = api_client.post("/api/v1/library/sources/unit_test_paper_2026/restore")
    assert restored.status_code == 200 and restored.json()["action"] == "restored"
    assert api_client.get("/api/v1/library/sources/unit_test_paper_2026").status_code == 200

    # Trash again then purge permanently.
    api_client.delete("/api/v1/library/sources/unit_test_paper_2026")
    purged = api_client.delete("/api/v1/library/trash/unit_test_paper_2026")
    assert purged.status_code == 200 and purged.json()["action"] == "purged"
    assert api_client.get("/api/v1/library/trash").json()["count"] == 0


def test_api_hard_delete_skips_trash(api_client):
    api_client.post("/api/v1/library/sources", json=_valid_source())
    deleted = api_client.delete("/api/v1/library/sources/unit_test_paper_2026?hard=true")
    assert deleted.json()["action"] == "removed"
    assert api_client.get("/api/v1/library/trash").json()["count"] == 0


def test_api_rejects_invalid_source(api_client):
    resp = api_client.post("/api/v1/library/sources", json=_valid_source(evidence_class="bogus"))
    assert resp.status_code == 422


def test_api_list_filter_and_bad_tier(api_client):
    resp = api_client.get("/api/v1/library/sources", params={"tier": "A"})
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1
    assert api_client.get("/api/v1/library/sources", params={"tier": "Z"}).status_code == 422


def test_api_journal_tier_filter(api_client):
    api_client.post("/api/v1/library/sources", json=_valid_source(source_id="api_jt1", journal="Nature", journal_tier=1))
    r = api_client.get("/api/v1/library/sources", params={"journal_tier": 1})
    assert r.status_code == 200
    assert "api_jt1" in [s["source_id"] for s in r.json()["sources"]]
    assert api_client.get("/api/v1/library/sources", params={"journal_tier": 9}).status_code == 422


def test_api_ingest_triggers_rebuild(api_client, monkeypatch):
    calls = {}

    def fake_ingest(build_vector=False):
        calls["build_vector"] = build_vector
        return {"chunk_count": 42, "content_chunk_count": 40, "hashing_vector_status": "ok"}

    monkeypatch.setattr(library_api, "ingest_knowledge_base", fake_ingest)
    resp = api_client.post("/api/v1/library/ingest", params={"build_vector": True})
    assert resp.status_code == 200
    assert resp.json()["chunk_count"] == 42
    assert calls["build_vector"] is True


def test_api_admin_page_served(api_client):
    resp = api_client.get("/api/v1/library/admin")
    assert resp.status_code == 200
    assert "文献管理后台" in resp.text
