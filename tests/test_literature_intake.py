"""Tests for auto-fill literature intake (offline: Crossref is mocked)."""

from __future__ import annotations

import pytest

import app.api.library as library_api
from app.services import literature_intake as li

_CROSSREF_MESSAGE = {
    "title": ["Photoplethysmography for the Assessment of Arterial Stiffness"],
    "DOI": "10.3390/s23249882",
    "URL": "https://doi.org/10.3390/s23249882",
    "type": "journal-article",
    "container-title": ["Sensors"],
    "publisher": "MDPI AG",
    "issued": {"date-parts": [[2023, 12, 1]]},
    "author": [
        {"family": "Karimpour", "affiliation": [{"name": "City, University of London"}]},
    ],
    "language": "en",
    "abstract": "A review of photoplethysmography (PPG) and cuffless pulse wave analysis.",
}


# --------------------------------------------------------------------------- #
# Pure helpers (no network)
# --------------------------------------------------------------------------- #
def test_extract_doi():
    assert li.extract_doi("see https://doi.org/10.3390/s23249882.") == "10.3390/s23249882"
    assert li.extract_doi("no identifier here") is None


def test_suggest_source_id():
    sid = li.suggest_source_id("A Novel Study of Cuffless Blood Pressure", 2024, "Smith")
    assert sid.startswith("smith_2024_")
    assert "novel" not in sid  # stopword dropped
    assert li.suggest_source_id("", None) == "untitled_source"


def test_suggest_topic_and_evidence():
    assert li.suggest_topic("cuffless PPG pulse transit time") == "cuffless_ppg_limitations"
    assert li.suggest_topic("DASH diet and sodium reduction") == "lifestyle"
    assert li.suggest_topic("something unrelated") == "research_context"
    assert li.suggest_evidence_class("2025 AHA Guideline for High Blood Pressure") == "guideline"
    assert li.suggest_evidence_class("A systematic review of PPG") == "review"
    assert li.suggest_evidence_class("An experimental sensor paper") == "research_context"


def test_suggest_screening_recency():
    assert li.suggest_screening(2025)["recency"] == 5
    assert li.suggest_screening(2021)["recency"] == 4
    assert li.suggest_screening(2010)["recency"] == 2
    assert li.suggest_screening(None)["recency"] == 2


def test_suggest_screening_recent_clears_include_threshold():
    # A recent (2020+) paper's suggested screening must sum to >= 18 so an
    # autofill-add registers as included, not below-threshold.
    from app.services.source_catalog import SCREEN_THRESHOLD

    assert sum(li.suggest_screening(2022).values()) >= SCREEN_THRESHOLD
    assert sum(li.suggest_screening(2025).values()) >= SCREEN_THRESHOLD


def test_message_to_draft_fills_and_suggests():
    draft = li.message_to_draft(_CROSSREF_MESSAGE)
    assert draft["title"].startswith("Photoplethysmography")
    assert draft["year"] == 2023
    assert draft["doi"] == "10.3390/s23249882"
    assert draft["organization"] == "City, University of London"
    assert draft["source_id"].startswith("karimpour_2023_")
    # Curation fields are suggestions, flagged for confirmation.
    assert draft["topic"] == "cuffless_ppg_limitations"
    assert draft["evidence_class"] == "review"
    assert set(draft["_suggested_fields"]) == {"topic", "evidence_class", "allowed_uses", "screening"}
    # allowed_uses are within the controlled vocabulary.
    from app.services.source_catalog import ALLOWED_USES

    assert set(draft["allowed_uses"]) <= ALLOWED_USES


# --------------------------------------------------------------------------- #
# Entry points with Crossref mocked
# --------------------------------------------------------------------------- #
def test_draft_from_query_by_doi(monkeypatch):
    monkeypatch.setattr(li, "crossref_by_doi", lambda doi: _CROSSREF_MESSAGE)
    draft = li.draft_from_query("10.3390/s23249882")
    assert draft["_resolved"] is True
    assert draft["year"] == 2023


def test_draft_from_query_offline_returns_placeholder(monkeypatch):
    monkeypatch.setattr(li, "crossref_by_doi", lambda doi: None)
    monkeypatch.setattr(li, "crossref_search", lambda title: None)
    draft = li.draft_from_query("Some paper title with no match")
    assert draft["_resolved"] is False
    assert draft["title"] == "Some paper title with no match"
    assert "topic" in draft  # still suggests, so the form is usable


def test_draft_from_query_empty_raises():
    with pytest.raises(ValueError):
        li.draft_from_query("   ")


# --------------------------------------------------------------------------- #
# API endpoints
# --------------------------------------------------------------------------- #
@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_api_autofill(client, monkeypatch):
    monkeypatch.setattr(
        library_api.literature_intake, "draft_from_query", lambda q: {"source_id": "x", "_resolved": True}
    )
    resp = client.post("/api/v1/library/autofill", json={"query": "10.3390/s23249882"})
    assert resp.status_code == 200
    assert resp.json()["source_id"] == "x"


def test_api_autofill_empty_query(client):
    resp = client.post("/api/v1/library/autofill", json={"query": ""})
    assert resp.status_code == 422


def test_api_autofill_pdf_empty(client):
    resp = client.post("/api/v1/library/autofill/pdf", content=b"")
    assert resp.status_code == 422
