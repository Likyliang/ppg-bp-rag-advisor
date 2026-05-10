from app.services import fulltext_candidates as ft


def test_fulltext_candidate_catalog_validates_without_errors():
    report = ft.validate_fulltext_catalog()
    assert report["candidate_count"] >= 8
    assert report["public_download_count"] >= 1
    assert report["institution_queue_count"] >= 2
    assert report["summary_ready_count"] >= 3
    assert not [issue for issue in report["issues"] if issue["severity"] == "error"]


def test_fulltext_catalog_rejects_credential_like_fields():
    catalog = {
        "candidates": [
            {
                "candidate_id": "bad_credentials",
                "source_id": "aha_cuffless_bp_scientific_statement",
                "title": "Bad credential storage",
                "priority": 1,
                "access_mode": "institution_or_browser",
                "status": "queued_institution",
                "summary_status": "pending_fulltext",
                "institution_required": True,
                "auto_download": False,
                "include_in_summary": False,
                "allowed_uses": ["cuffless_ppg_limitations"],
                "landing_url": "https://example.org",
                "login_password": "never-store-this",
            }
        ]
    }
    report = ft.validate_fulltext_catalog(catalog)
    assert any("protected credential-like field" in issue["message"] for issue in report["issues"])


def test_fulltext_public_download_never_downloads_institution_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(ft, "DOWNLOADS_ROOT", str(tmp_path / "downloads"))
    monkeypatch.setattr(ft, "PROCESSED_ROOT", str(tmp_path / "processed"))
    requested_urls = []

    def fake_download(url, timeout):
        requested_urls.append(url)
        return b"%PDF-1.4\n%%EOF", {"content-type": "application/pdf"}

    monkeypatch.setattr(ft, "_download_pdf", fake_download)
    result = ft.download_public_candidates(force=True)

    assert result["download_count"] >= 1
    assert requested_urls
    assert not any("ahajournals.org" in url or "sciopen.com" in url for url in requested_urls)


def test_fulltext_summary_notes_are_tracked_summaries(tmp_path, monkeypatch):
    monkeypatch.setattr(ft, "DOWNLOADS_ROOT", str(tmp_path / "downloads"))
    monkeypatch.setattr(ft, "SUMMARY_ROOT", str(tmp_path / "summaries"))
    monkeypatch.setattr(ft, "PROCESSED_ROOT", str(tmp_path / "processed"))

    result = ft.create_summary_notes()

    assert result["written_count"] >= 3
    summary_text = "\n".join(path for path in result["written"])
    assert "downloads" not in summary_text
    first_note = (tmp_path / "summaries").glob("*.summary.md")
    contents = "\n".join(path.read_text(encoding="utf-8") for path in first_note)
    assert "不生成诊断" in contents
    assert "password" not in contents.lower()
