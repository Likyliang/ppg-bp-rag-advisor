from app.services.source_catalog import ALLOWED_USES, screen_sources, validate_source


def test_source_catalog_screens_without_errors():
    result = screen_sources()
    assert result["included_count"] >= 35
    assert result["excluded_count"] >= 4
    assert not [issue for issue in result["issues"] if issue["severity"] == "error"]
    assert "emergency" in result["topic_counts"]
    assert "cuffless_ppg_limitations" in result["topic_counts"]


def test_source_catalog_rejects_missing_url_for_non_safety_source():
    issues = validate_source(
        {
            "source_id": "bad_source",
            "title": "Bad source",
            "organization": "unknown",
            "year": 2026,
            "language": "zh",
            "region": "global",
            "topic": "lifestyle",
            "evidence_class": "official_health_education",
            "allowed_uses": ["lifestyle"],
            "include": True,
            "screening": {"authority": 5, "recency": 5, "relevance": 5, "accessibility": 5, "safety_applicability": 5},
        }
    )
    assert any("url, doi, pmid" in issue.message for issue in issues)


def test_source_catalog_rejects_invalid_allowed_use():
    issues = validate_source(
        {
            "source_id": "bad_use",
            "title": "Bad use",
            "organization": "project",
            "year": 2026,
            "language": "zh",
            "region": "global",
            "topic": "lifestyle",
            "evidence_class": "safety_rule",
            "allowed_uses": ["diagnosis"],
            "include": True,
            "screening": {"authority": 5, "recency": 5, "relevance": 5, "accessibility": 5, "safety_applicability": 5},
        }
    )
    assert "diagnosis" not in ALLOWED_USES
    assert any("invalid allowed_uses" in issue.message for issue in issues)
