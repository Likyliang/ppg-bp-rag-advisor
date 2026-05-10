from scripts.ingest_kb import build_chunks
from app.services.kb_audit import audit_knowledge_base


def test_ingested_chunks_have_governance_metadata():
    chunks = build_chunks()
    assert len(chunks) >= 100
    sample = chunks[0]
    for field in ["evidence_class", "source_quality_score", "allowed_uses", "review_status", "derived_from", "source_hash"]:
        assert field in sample
    assert all(chunk["review_status"] == "included" for chunk in chunks)


def test_kb_audit_quality_gates_pass():
    audit = audit_knowledge_base()
    assert audit["chunk_count"] >= 250
    assert audit["catalog_included_count"] >= 60
    assert audit["quality"]["has_all_expected_topics"] is True
    assert audit["quality"]["has_no_unsafe_source_leakage"] is True
    assert audit["quality"]["has_catalog_alignment"] is True
    assert all(count >= 3 for count in audit["topic_source_counts"].values())
