import json

from app.services.fulltext_vector_index import (
    FulltextChunk,
    hashing_embedding,
    query_hashing_vector_index,
    split_text_for_fulltext_chunks,
    summarize_query_results,
    write_hashing_vector_index,
    write_local_fulltext_chunks,
)


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
