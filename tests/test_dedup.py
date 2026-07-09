"""Tests for near-duplicate detection (service + API)."""

from fastapi.testclient import TestClient

from app.main import app
from app.services import dedup

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #
def test_normalize_doi_from_various_forms():
    doi = "10.1161/cir.0000000000001356"
    assert dedup.normalize_doi("10.1161/CIR.0000000000001356") == doi
    assert dedup.normalize_doi("https://doi.org/10.1161/CIR.0000000000001356") == doi
    assert dedup.normalize_doi("doi:10.1161/CIR.0000000000001356") == doi
    assert dedup.normalize_doi("https://www.ahajournals.org/doi/10.1161/CIR.0000000000001356") == doi
    assert dedup.normalize_doi("") == ""
    assert dedup.normalize_doi(None) == ""
    assert dedup.normalize_doi("no doi here") == ""


def test_normalize_doi_strips_url_query_and_trailing():
    assert dedup.normalize_doi("https://x.org/10.1000/abc?utm=1") == "10.1000/abc"
    assert dedup.normalize_doi("https://x.org/10.1000/abc#frag") == "10.1000/abc"
    assert dedup.normalize_doi("https://x.org/10.1000/abc/full") == "10.1000/abc"


def test_normalize_doi_strips_ampersand_and_stacked_segments():
    # Over-capturing a URL tail makes the same paper look like a different DOI.
    assert (
        dedup.normalize_doi("https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0012345&type=printable")
        == "10.1371/journal.pone.0012345"
    )
    assert dedup.normalize_doi("https://x.org/10.1161/circ.119.001/fulltext") == "10.1161/circ.119.001"
    assert dedup.normalize_doi("https://x.org/10.1002/clc.12345/full/meta") == "10.1002/clc.12345"


def test_clean_doi_and_printable_url_are_the_same_paper():
    a = {"doi": "10.1371/journal.pone.0012345", "title": "T", "year": 2020}
    b = {"url": "https://journals.plos.org/plosone/article/file?id=10.1371/journal.pone.0012345&type=printable",
         "title": "T", "year": 2020}
    assert _m(a, b) == "doi"


def test_normalize_pmid():
    assert dedup.normalize_pmid("41376592") == "41376592"
    assert dedup.normalize_pmid("PMID: 41376592") == "41376592"
    assert dedup.normalize_pmid("https://pubmed.ncbi.nlm.nih.gov/41376592/") == "41376592"
    assert dedup.normalize_pmid("") == ""


def test_normalize_title_collapses_case_punct_space():
    assert dedup.normalize_title("Cuffless Blood Pressure!") == "cuffless blood pressure"
    assert dedup.normalize_title("  cuffless   blood  pressure ") == "cuffless blood pressure"
    assert dedup.normalize_title("Cuffless: Blood-Pressure") == "cuffless blood pressure"


# --------------------------------------------------------------------------- #
# Matching rules
# --------------------------------------------------------------------------- #
def _m(a, b):
    return dedup._match(dedup._Identity(a), dedup._Identity(b))


def test_match_same_doi_even_with_different_titles():
    assert _m(
        {"doi": "10.1161/ABC", "title": "X - PubMed record", "year": 2020},
        {"doi": "10.1161/abc", "title": "X", "year": 2020},
    ) == "doi"


def test_match_different_dois_vetoes_title():
    # Same title+year but authoritative DOIs differ -> NOT a duplicate.
    assert _m(
        {"doi": "10.1161/aaa", "title": "Same Title", "year": 2020},
        {"doi": "10.1161/bbb", "title": "Same Title", "year": 2020},
    ) is None


def test_match_doi_vs_no_doi_falls_back_to_title_year():
    assert _m(
        {"doi": "10.1161/aaa", "title": "Same Title", "year": 2020},
        {"title": "same title", "year": 2020},
    ) == "title+year"


def test_match_pmid_and_pmid_veto():
    assert _m(
        {"pmid": "111", "title": "A", "year": 2020},
        {"url": "https://pubmed.ncbi.nlm.nih.gov/111/", "title": "B", "year": 2021},
    ) == "pmid"
    assert _m({"pmid": "111", "title": "A", "year": 2020}, {"pmid": "222", "title": "A", "year": 2020}) is None


def test_match_title_requires_equal_year():
    assert _m({"title": "A", "year": 2020}, {"title": "A", "year": 2021}) is None
    assert _m({"title": "A"}, {"title": "A"}) is None  # no year -> no match


def test_find_duplicates_ignores_self():
    existing = [{"source_id": "s1", "doi": "10.1000/abc", "title": "T", "year": 2020}]
    got = dedup.find_duplicates({"doi": "10.1000/abc", "title": "T", "year": 2020}, existing, ignore_id="s1")
    assert got == []
    got2 = dedup.find_duplicates({"doi": "10.1000/abc"}, existing)
    assert len(got2) == 1 and got2[0]["source_id"] == "s1" and got2[0]["reason"] == "doi"


# --------------------------------------------------------------------------- #
# Clustering
# --------------------------------------------------------------------------- #
def test_clusters_group_transitively():
    # a~b by doi, b~c by pmid -> a,b,c one cluster of 3.
    sources = [
        {"source_id": "a", "doi": "10.1000/x", "title": "A", "year": 2020, "pmid": "999"},
        {"source_id": "b", "doi": "10.1000/x", "title": "B", "year": 2021, "pmid": "999"},
        {"source_id": "c", "pmid": "999", "title": "C", "year": 2022},
        {"source_id": "d", "doi": "10.1000/z", "title": "Z", "year": 2020},
    ]
    clusters = dedup.find_duplicate_clusters(sources)
    assert len(clusters) == 1
    members = {m["source_id"] for m in clusters[0]["members"]}
    assert members == {"a", "b", "c"}
    assert set(clusters[0]["reasons"]) <= {"doi", "pmid", "title+year"}


def test_clusters_respect_doi_veto():
    # Same title+year, different DOIs -> two distinct papers, no cluster.
    sources = [
        {"source_id": "a", "doi": "10.1161/aaa", "title": "High Blood Pressure", "year": 2026},
        {"source_id": "b", "doi": "10.1161/bbb", "title": "High Blood Pressure", "year": 2026},
    ]
    assert dedup.find_duplicate_clusters(sources) == []


def test_clusters_weak_edge_does_not_bridge_id_bearing_sources():
    # A(doi aaa) ~ B(no id, same title+year) ~ C(doi zzz): B must NOT bridge the
    # DOI-conflicting A and C into one cluster (transitivity would bypass the veto).
    sources = [
        {"source_id": "a", "doi": "10.1000/aaa", "title": "Series Part One", "year": 2021},
        {"source_id": "b", "title": "Series Part One", "year": 2021},
        {"source_id": "c", "doi": "10.1000/zzz", "title": "Series Part One", "year": 2021},
    ]
    assert dedup.find_duplicate_clusters(sources) == []


def test_clusters_weak_member_not_absorbed_into_strong_cluster():
    # A,B are a real DOI duplicate; C shares only title+year and has no id.
    # C must not inherit the strong (doi) cluster; only {A,B} clusters.
    sources = [
        {"source_id": "a", "doi": "10.1000/aaa", "title": "Some Specific Paper", "year": 2021},
        {"source_id": "b", "doi": "10.1000/aaa", "title": "Some Specific Paper", "year": 2021},
        {"source_id": "c", "title": "Some Specific Paper", "year": 2021},
    ]
    clusters = dedup.find_duplicate_clusters(sources)
    assert len(clusters) == 1
    assert {m["source_id"] for m in clusters[0]["members"]} == {"a", "b"}
    assert clusters[0]["reasons"] == ["doi"]


def test_generic_titles_are_not_sole_evidence():
    assert _m({"title": "Editorial", "year": 2020}, {"title": "editorial", "year": 2020}) is None
    assert _m({"title": "Erratum", "year": 2021}, {"title": "Erratum", "year": 2021}) is None
    # A specific title still matches on title+year.
    assert _m({"title": "Cuffless BP Validation Study", "year": 2020},
              {"title": "cuffless bp validation study", "year": 2020}) == "title+year"


def test_build_identities_batch_matches_per_call():
    existing = [
        {"source_id": "s1", "doi": "10.1161/HYP.0000000000000254", "title": "T", "year": 2025},
        {"source_id": "s2", "title": "Other", "year": 2020},
    ]
    ids = dedup.build_identities(existing)
    got = dedup.find_duplicates({"doi": "10.1161/hyp.0000000000000254"}, existing, existing_ids=ids)
    assert [m["source_id"] for m in got] == ["s1"]


def test_clusters_empty_when_all_unique():
    sources = [
        {"source_id": "a", "doi": "10.1000/a", "title": "A", "year": 2020},
        {"source_id": "b", "doi": "10.1000/b", "title": "B", "year": 2021},
    ]
    assert dedup.find_duplicate_clusters(sources) == []


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_api_scan_duplicates_flags_strength():
    r = client.get("/api/v1/library/duplicates")
    assert r.status_code == 200
    data = r.json()
    assert data["cluster_count"] == len(data["clusters"])
    for cl in data["clusters"]:
        assert cl["size"] >= 2
        assert "strong" in cl and isinstance(cl["strong"], bool)
        # strong iff a doi/pmid reason is present
        assert cl["strong"] == any(x in ("doi", "pmid") for x in cl["reasons"])
        # members carry enough to distinguish (org/url) plus id/title
        assert {"source_id", "title", "organization", "url"} <= set(cl["members"][0])


def test_api_check_duplicates_matches_existing_doi():
    r = client.post(
        "/api/v1/library/duplicates/check",
        json={"items": [
            {"doi": "https://doi.org/10.1161/HYP.0000000000000254", "title": "x", "year": 2025},
            {"title": "A Totally Novel Unrelated Paper About Nothing", "year": 2031},
        ]},
    )
    assert r.status_code == 200
    results = r.json()["results"]
    assert results[0]["matches"], "first item should match an existing source by DOI"
    assert results[0]["matches"][0]["reason"] == "doi"
    assert results[1]["matches"] == []
