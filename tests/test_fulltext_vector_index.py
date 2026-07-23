import json

import numpy as np

from app.services.fulltext_vector_index import (
    FulltextChunk,
    _chunk_source_id,
    _governance_metadata,
    drop_source_from_index,
    hashing_embedding,
    merge_hashing_vector_index,
    merge_local_fulltext_chunks,
    query_hashing_vector_index,
    split_text_for_fulltext_chunks,
    summarize_query_results,
    write_hashing_vector_index,
    write_local_fulltext_chunks,
)


def _chunks(source_id, n):
    return [
        FulltextChunk(
            chunk_id=f"fulltext::{source_id}::p001::c{i:02d}",
            text=f"{source_id} cuffless ppg blood pressure passage {i}",
            metadata={"source_id": source_id, "title": source_id},
        )
        for i in range(1, n + 1)
    ]


def _counts(jsonl, npz):
    from collections import Counter

    rows = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
    data = np.load(npz, allow_pickle=True)
    jc = Counter(r["source_id"] for r in rows)
    nc = Counter(_chunk_source_id(str(x)) for x in data["ids"])
    return dict(jc), dict(nc), data["embeddings"].shape[0]


def test_incremental_splice_preserves_other_sources(tmp_path):
    jsonl, npz = tmp_path / "c.jsonl", tmp_path / "v.npz"
    merge_local_fulltext_chunks(_chunks("A", 2) + _chunks("B", 3), ["A", "B"], path=str(jsonl))
    merge_hashing_vector_index(_chunks("A", 2) + _chunks("B", 3), ["A", "B"], path=str(npz))
    merge_local_fulltext_chunks(_chunks("C", 4), ["C"], path=str(jsonl))
    merge_hashing_vector_index(_chunks("C", 4), ["C"], path=str(npz))
    jc, nc, rows = _counts(jsonl, npz)
    assert jc == nc == {"A": 2, "B": 3, "C": 4}
    assert rows == 9


def test_reattach_replaces_not_duplicates(tmp_path):
    jsonl, npz = tmp_path / "c.jsonl", tmp_path / "v.npz"
    merge_local_fulltext_chunks(_chunks("B", 3), ["B"], path=str(jsonl))
    merge_hashing_vector_index(_chunks("B", 3), ["B"], path=str(npz))
    merge_local_fulltext_chunks(_chunks("B", 1), ["B"], path=str(jsonl))
    merge_hashing_vector_index(_chunks("B", 1), ["B"], path=str(npz))
    jc, nc, rows = _counts(jsonl, npz)
    assert jc == nc == {"B": 1}
    assert rows == 1


def test_drop_removes_only_target_source(tmp_path):
    jsonl, npz, manifest = tmp_path / "c.jsonl", tmp_path / "v.npz", tmp_path / "m.json"
    merge_local_fulltext_chunks(_chunks("A", 2) + _chunks("B", 3), ["A", "B"], path=str(jsonl))
    merge_hashing_vector_index(_chunks("A", 2) + _chunks("B", 3), ["A", "B"], path=str(npz))
    drop_source_from_index("A", chunks_path=str(jsonl), vector_path=str(npz), manifest_path=str(manifest))
    jc, nc, rows = _counts(jsonl, npz)
    assert jc == nc == {"B": 3}
    assert rows == 3


def test_split_text_for_fulltext_chunks_keeps_small_overlapping_chunks():
    text = "PPG signal quality depends on motion and contact pressure. " * 40
    chunks = split_text_for_fulltext_chunks(text, target_chars=180, overlap_chars=30, min_chars=50)

    assert len(chunks) > 3
    assert all(len(chunk) <= 240 for chunk in chunks)
    assert "contact pressure" in chunks[0]


def test_hashing_embedding_is_normalized_and_deterministic():
    first = hashing_embedding("home blood pressure monitoring validated cuff")
    second = hashing_embedding("home blood pressure monitoring validated cuff")

    assert first.shape == second.shape
    assert first.tolist() == second.tolist()
    assert round(float((first * first).sum()), 3) == 1.0


def test_fulltext_governance_can_only_narrow_allowed_uses():
    source = {
        "title": "Source",
        "allowed_uses": ["signal_quality", "research_background"],
    }
    governed = _governance_metadata(
        source,
        {"access_mode": "public_pdf", "allowed_uses": ["research_background", "lifestyle"]},
    )
    assert governed["allowed_uses"] == ["research_background"]
    assert governed["access_mode"] == "public_pdf"


def test_local_hashing_vector_query_returns_chunk_metadata(tmp_path):
    chunks = [
        FulltextChunk(
            chunk_id="fulltext::a::p001::c01",
            text="validated upper arm cuff home blood pressure monitoring repeated readings",
            metadata={"source_id": "a", "title": "Home BP", "allowed_uses": ["home_bp_monitoring"]},
        ),
        FulltextChunk(
            chunk_id="fulltext::b::p001::c01",
            text="camera PPG motion artifact and signal quality limitations",
            metadata={"source_id": "b", "title": "PPG Quality", "allowed_uses": ["signal_quality"]},
        ),
    ]
    chunks_path = tmp_path / "chunks.jsonl"
    vector_path = tmp_path / "vectors.npz"
    write_local_fulltext_chunks(chunks, path=str(chunks_path))
    write_hashing_vector_index(chunks, path=str(vector_path))

    results = query_hashing_vector_index(
        "validated cuff home blood pressure",
        top_k=1,
        vector_path=str(vector_path),
        chunks_path=str(chunks_path),
    )
    summary = summarize_query_results(results)

    assert results[0]["source_id"] == "a"
    assert json.dumps(summary, ensure_ascii=False)
