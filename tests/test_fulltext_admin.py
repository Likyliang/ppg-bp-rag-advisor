"""Tests for governed full-text management.

The heavy PDF->vector rebuild is stubbed; storage paths are redirected to tmp so
no committed file, real download, or real index is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import app.api.library as library_api
from app.services import fulltext_admin as fa
from app.services.source_catalog import ALLOWED_USES, included_sources

_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _included_id() -> str:
    return included_sources()[0]["source_id"]


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """Redirect the topic-classified library / registry / manifest to tmp and
    stub the vector rebuild so tests stay offline and touch no real files."""

    library = tmp_path / "library"
    monkeypatch.setattr(fa, "UPLOADS_REGISTRY", str(tmp_path / "uploads.yaml"))
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(fa, "MANIFEST_PATH", str(manifest_path))

    def target(source_id, topic):
        return library / (str(topic) if topic else "uncategorized") / f"{source_id}.pdf"

    def existing(source_id, topic=None):
        if not library.exists():
            return None
        for pdf in library.rglob(f"{source_id}.pdf"):
            if ".trash" not in pdf.parts:
                return pdf
        return None

    def trash_path(source_id):
        return library / ".trash" / f"{source_id}.pdf"

    monkeypatch.setattr(fa, "library_pdf_target", target)
    monkeypatch.setattr(fa, "_existing_pdf", existing)
    monkeypatch.setattr(fa, "_trash_pdf_path", trash_path)

    state = {"built": 0}

    def fake_index(*args, **kwargs):
        # One stub for full rebuild / incremental update / drop: the manifest
        # always reflects whichever PDFs currently sit in the tmp library.
        state["built"] += 1
        sources = []
        if library.exists():
            for pdf in library.rglob("*.pdf"):
                if ".trash" not in pdf.parts:
                    sources.append({"source_id": pdf.stem, "chunk_count": 3})
        manifest_path.write_text(json.dumps({"sources": sources, "chunk_count": 3 * len(sources)}), encoding="utf-8")
        return {"source_count": len(sources), "chunk_count": 3 * len(sources), "page_count": 1, "skipped": []}

    monkeypatch.setattr(fa, "build_fulltext_vector_index", fake_index)
    monkeypatch.setattr(fa, "update_fulltext_vector_index", fake_index)
    monkeypatch.setattr(fa, "drop_source_from_index", fake_index)
    return state


# --------------------------------------------------------------------------- #
# Governance rejections
# --------------------------------------------------------------------------- #
def test_reject_non_included_source(sandbox):
    with pytest.raises(fa.FulltextAdminError):
        fa.attach_pdf("definitely_not_a_source", _PDF, access_mode="public_pdf")


def test_reject_bad_access_mode(sandbox):
    with pytest.raises(fa.FulltextAdminError):
        fa.attach_pdf(_included_id(), _PDF, access_mode="made_up")


def test_reject_non_pdf_bytes(sandbox):
    with pytest.raises(fa.FulltextAdminError):
        fa.attach_pdf(_included_id(), b"this is not a pdf", access_mode="public_pdf")


def test_reject_invalid_allowed_use(sandbox):
    with pytest.raises(fa.FulltextAdminError):
        fa.attach_pdf(_included_id(), _PDF, access_mode="public_pdf", allowed_uses=["totally_made_up"])


def test_fulltext_allowed_uses_cannot_expand_catalog_scope(sandbox):
    source = next(item for item in included_sources() if set(ALLOWED_USES) - set(item.get("allowed_uses") or []))
    extra = next(iter(set(ALLOWED_USES) - set(source.get("allowed_uses") or [])))
    with pytest.raises(fa.FulltextAdminError, match="不能扩大"):
        fa.attach_pdf(source["source_id"], _PDF, access_mode="public_pdf", allowed_uses=[extra])


# --------------------------------------------------------------------------- #
# Attach / remove lifecycle
# --------------------------------------------------------------------------- #
def test_attach_no_rebuild_writes_pdf_and_metadata(sandbox):
    sid = _included_id()
    result = fa.attach_pdf(sid, _PDF, access_mode="public_pdf", rebuild=False)
    assert result["action"] == "attached"
    assert result["record"]["status"] == "attached"
    assert result["record"]["pdf_bytes"] == len(_PDF)
    assert result["record"]["allowed_uses"]  # inherited from the source
    assert "license_attestation" not in result["record"]
    assert result["record"]["license_attested"] is False

    status = fa.source_fulltext_status(sid)
    assert status["has_pdf"] is True
    assert status["indexed"] is False
    assert status["managed_by"] == "upload"
    assert sandbox["built"] == 0  # rebuild skipped


def test_registry_normalisation_does_not_treat_legacy_review_note_as_attestation(sandbox, monkeypatch):
    sid = _included_id()
    title = "Governed bibliographic title"
    monkeypatch.setattr(
        fa,
        "load_source_catalog",
        lambda: {"sources": [{"source_id": sid, "title": title}]},
    )
    path, text = fa._normalise_uploads(
        {
            "uploads": [
                {
                    "source_id": sid,
                    "title": "private-upload-name.pdf",
                    "access_mode": "public_pdf",
                    "allowed_uses": ["research_background"],
                    "license_attestation": "imported; admin to verify license",
                }
            ]
        }
    )
    record = yaml.safe_load(text)["uploads"][0]
    assert path.name == "uploads.yaml"
    assert record["title"] == title
    assert record["license_attested"] is False
    assert "license_attestation" not in record
    assert "private-upload-name.pdf" not in text


def test_fixed_attestation_code_is_recognised():
    assert fa.is_license_attested({"license_attestation": fa.LICENSE_ATTESTATION_CODE}) is True
    assert fa.is_license_attested({"license_attested": False, "license_attestation": fa.LICENSE_ATTESTATION_CODE}) is False


def test_attach_only_accepts_fixed_attestation_assertion(sandbox):
    sid = _included_id()
    arbitrary = fa.attach_pdf(
        sid,
        _PDF,
        access_mode="public_pdf",
        license_attestation="operator said yes",
        rebuild=False,
    )
    assert arbitrary["record"]["license_attested"] is False
    fixed = fa.attach_pdf(
        sid,
        _PDF,
        access_mode="public_pdf",
        license_attestation=fa.LICENSE_ATTESTATION_CODE,
        rebuild=False,
    )
    assert fixed["record"]["license_attested"] is True


def test_attach_with_rebuild_indexes(sandbox):
    sid = _included_id()
    result = fa.attach_pdf(sid, _PDF, access_mode="public_pdf", rebuild=True)
    assert sandbox["built"] == 1
    assert result["record"]["status"] == "indexed"
    assert result["indexed_chunk_count"] == 3
    assert fa.source_fulltext_status(sid)["indexed"] is True


def test_remove_deletes_pdf_and_record(sandbox):
    sid = _included_id()
    fa.attach_pdf(sid, _PDF, access_mode="public_pdf", rebuild=False)
    result = fa.remove_fulltext(sid, rebuild=False)
    assert result["action"] == "removed"
    assert result["removed_pdf"] is True
    assert fa.source_fulltext_status(sid)["has_pdf"] is False
    # Registry no longer lists it.
    assert sid not in fa._uploads_by_source()


def test_remove_without_fulltext_raises(sandbox):
    with pytest.raises(fa.FulltextAdminError):
        fa.remove_fulltext(_included_id(), rebuild=False)


def test_trash_and_restore_fulltext(sandbox):
    sid = _included_id()
    fa.attach_pdf(sid, _PDF, access_mode="public_pdf", rebuild=False)
    assert fa.source_fulltext_status(sid)["has_pdf"] is True

    trashed = fa.trash_fulltext(sid, rebuild=False)
    assert trashed["action"] == "trashed"
    assert fa.source_fulltext_status(sid)["has_pdf"] is False  # moved to .trash

    restored = fa.restore_fulltext(sid, rebuild=False)
    assert restored["action"] == "restored"
    assert fa.source_fulltext_status(sid)["has_pdf"] is True


def test_purge_fulltext_is_permanent(sandbox):
    sid = _included_id()
    fa.attach_pdf(sid, _PDF, access_mode="public_pdf", rebuild=False)
    fa.trash_fulltext(sid, rebuild=False)
    result = fa.purge_fulltext(sid)
    assert result["purged"] is True
    assert fa.restore_fulltext(sid, rebuild=False)["action"] == "noop"
    assert sid not in fa._uploads_by_source()


def test_status_totals_and_governance(sandbox):
    st = fa.fulltext_status()
    assert st["total_sources"] == len(included_sources())
    assert "governance_note" in st and "诊断" in st["governance_note"]
    assert "public_pdf" in st["access_modes"]


def test_status_explains_pdf_excluded_by_allowed_use_intersection(sandbox, monkeypatch):
    source = {"source_id": "source-a", "title": "A", "topic": "research_context", "allowed_uses": ["signal_quality"]}
    monkeypatch.setattr(fa, "_included_by_id", lambda: {"source-a": source})
    monkeypatch.setattr(
        fa,
        "_uploads_by_source",
        lambda: {"source-a": {"access_mode": "public_pdf", "allowed_uses": ["research_background"]}},
    )
    monkeypatch.setattr(fa, "_candidate_by_source", lambda: {})
    monkeypatch.setattr(fa, "_indexed_chunk_counts", lambda: {})
    monkeypatch.setattr(fa, "_existing_pdf", lambda source_id, topic=None: Path("/tmp/source-a.pdf"))

    row = fa.source_fulltext_status("source-a")
    assert row["has_pdf"] is True
    assert row["index_eligible"] is False
    assert row["ineligible_reason"] == "fulltext_allowed_uses_empty"
    assert row["allowed_uses"] == []
    assert row["license_attested"] is False


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.fixture()
def client(sandbox):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_api_fulltext_status(client):
    resp = client.get("/api/v1/library/fulltext")
    assert resp.status_code == 200
    assert resp.json()["total_sources"] >= 1


def test_api_attach_and_detach(client):
    sid = _included_id()
    r = client.post(
        f"/api/v1/library/sources/{sid}/fulltext?access_mode=public_pdf&rebuild=false", content=_PDF
    )
    assert r.status_code == 200
    assert r.json()["action"] == "attached"

    r = client.get(f"/api/v1/library/sources/{sid}/fulltext")
    assert r.status_code == 200 and r.json()["has_pdf"] is True

    r = client.delete(f"/api/v1/library/sources/{sid}/fulltext?rebuild=false")
    assert r.status_code == 200 and r.json()["action"] == "removed"


def test_api_attach_bad_access_mode(client):
    sid = _included_id()
    r = client.post(
        f"/api/v1/library/sources/{sid}/fulltext?access_mode=bogus&rebuild=false", content=_PDF
    )
    assert r.status_code == 422
