"""Vector-backend dispatch: OpenAI embedding index first, hashing fallback."""

import numpy as np
import pytest

from app.services import retriever


def _write_npz(path, ids, vectors):
    np.savez_compressed(
        path,
        ids=np.array(ids, dtype=object),
        embeddings=np.array(vectors, dtype=np.float32),
        metadata=np.array(["{}"] * len(ids), dtype=object),
    )


@pytest.fixture()
def fake_indexes(tmp_path, monkeypatch):
    # conftest pins RETRIEVAL_EMBEDDING_BACKEND=hashing for offline determinism;
    # these tests exercise the dispatch itself, so restore production "auto".
    monkeypatch.setenv("RETRIEVAL_EMBEDDING_BACKEND", "auto")
    openai_npz = tmp_path / "openai.npz"
    hashing_npz = tmp_path / "hashing.npz"
    # OpenAI index ranks chunk b first for query [0,1]; hashing index ranks a.
    _write_npz(openai_npz, ["a", "b"], [[1.0, 0.0], [0.0, 1.0]])
    _write_npz(hashing_npz, ["a", "b"], [[1.0, 0.0], [0.0, 0.0]])
    monkeypatch.setitem(
        retriever.VECTOR_STORE_PATHS, "processed", (str(openai_npz), str(hashing_npz))
    )
    return openai_npz, hashing_npz


def test_auto_prefers_openai_index_when_query_embedding_works(fake_indexes, monkeypatch):
    monkeypatch.setattr(
        retriever, "_openai_query_vector", lambda text, dims: np.array([0.0, 1.0], dtype=np.float32)
    )
    scores = retriever._store_vector_scores("查询", ["a", "b"], "processed")
    assert scores is not None
    assert scores["b"] > scores["a"]


def test_auto_falls_back_to_hashing_when_openai_unavailable(fake_indexes, monkeypatch):
    monkeypatch.setattr(retriever, "_openai_query_vector", lambda text, dims: None)
    monkeypatch.setattr(
        retriever, "_hashing_query_vector", lambda text, dims: np.array([1.0, 0.0], dtype=np.float32)
    )
    scores = retriever._store_vector_scores("查询", ["a", "b"], "processed")
    assert scores is not None
    assert scores["a"] > scores["b"]  # hashing index ranking, not openai's


def test_stale_openai_index_is_skipped_by_coverage_check(tmp_path, fake_indexes, monkeypatch):
    openai_npz, hashing_npz = fake_indexes
    # Rebuild the openai index with ids that no longer exist (stale after re-ingest).
    _write_npz(openai_npz, ["old_1", "old_2"], [[1.0, 0.0], [0.0, 1.0]])
    monkeypatch.setattr(
        retriever, "_openai_query_vector", lambda text, dims: np.array([0.0, 1.0], dtype=np.float32)
    )
    monkeypatch.setattr(
        retriever, "_hashing_query_vector", lambda text, dims: np.array([1.0, 0.0], dtype=np.float32)
    )
    retriever._load_vector_index.cache_clear()
    scores = retriever._store_vector_scores("查询", ["a", "b"], "processed")
    assert scores is not None
    assert scores["a"] > scores["b"]  # served by the hashing index


def test_backend_off_disables_vector_scoring(fake_indexes, monkeypatch):
    monkeypatch.setenv("RETRIEVAL_EMBEDDING_BACKEND", "off")
    assert retriever._store_vector_scores("查询", ["a", "b"], "processed") is None


def test_pinned_openai_backend_never_uses_hashing(fake_indexes, monkeypatch):
    monkeypatch.setenv("RETRIEVAL_EMBEDDING_BACKEND", "openai")
    monkeypatch.setattr(retriever, "_openai_query_vector", lambda text, dims: None)
    assert retriever._store_vector_scores("查询", ["a", "b"], "processed") is None


def test_openai_query_vector_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_EMBEDDING_API_KEY", raising=False)
    retriever._OPENAI_QUERY_CACHE.clear()
    assert retriever._openai_query_vector("查询", 1536) is None


def test_openai_query_vector_uses_cache_and_validates_dims(monkeypatch):
    monkeypatch.setenv("OPENAI_EMBEDDING_API_KEY", "test-key")
    calls = {"n": 0}

    def fake_embed_texts(texts, config, timeout_sec, max_retries):
        calls["n"] += 1
        return np.array([[0.6, 0.8]], dtype=np.float32), {}, "fake-model"

    import app.services.openai_embedding_index as oai

    monkeypatch.setattr(oai, "embed_texts", fake_embed_texts)
    retriever._OPENAI_QUERY_CACHE.clear()
    monkeypatch.setattr(retriever, "_OPENAI_BACKOFF_UNTIL", 0.0)

    first = retriever._openai_query_vector("同一查询", 2)
    second = retriever._openai_query_vector("同一查询", 2)
    assert first is not None and second is not None
    assert calls["n"] == 1  # second call served from cache
    # dimension mismatch with the index is rejected
    assert retriever._openai_query_vector("另一查询", 1536) is None


def test_openai_index_older_than_chunks_is_treated_as_stale(tmp_path, fake_indexes, monkeypatch):
    import os
    import time

    openai_npz, hashing_npz = fake_indexes
    # Make the openai index *older* than the chunks file -> content changed.
    past = time.time() - 86400
    os.utime(openai_npz, (past, past))
    monkeypatch.setattr(
        retriever, "_openai_query_vector", lambda text, dims: np.array([0.0, 1.0], dtype=np.float32)
    )
    monkeypatch.setattr(
        retriever, "_hashing_query_vector", lambda text, dims: np.array([1.0, 0.0], dtype=np.float32)
    )
    retriever._load_vector_index.cache_clear()
    scores = retriever._store_vector_scores("查询", ["a", "b"], "processed")
    assert scores is not None
    assert scores["a"] > scores["b"]  # hashing ranking proves openai was skipped


def test_retrieve_knowledge_end_to_end_with_mocked_openai_backend(tmp_path, monkeypatch):
    """Full plumbing check: a fresh fake OpenAI index drives report retrieval."""
    monkeypatch.setenv("RETRIEVAL_EMBEDDING_BACKEND", "auto")

    from app.services.chunking import build_embedding_text
    from app.services.fulltext_vector_index import hashing_embedding

    # Build a fake "openai" index over the real processed chunks (hashing
    # vectors standing in for the remote embeddings), so ranking is meaningful.
    chunks = retriever._load_chunks()
    ids = [str(chunk.get("chunk_id")) for chunk in chunks]
    vectors = [
        hashing_embedding(build_embedding_text(chunk, str(chunk.get("content", ""))), dims=384)
        for chunk in chunks
    ]
    fake_openai = tmp_path / "openai_processed.npz"
    _write_npz(fake_openai, ids, np.vstack(vectors))
    monkeypatch.setitem(
        retriever.VECTOR_STORE_PATHS,
        "processed",
        (str(fake_openai), "knowledge_base/vector_store/processed_hashing_vectors.npz"),
    )
    calls = {"n": 0}

    def fake_openai_query(text, dims):
        calls["n"] += 1
        return hashing_embedding(text, dims=dims)

    monkeypatch.setattr(retriever, "_openai_query_vector", fake_openai_query)
    retriever._load_vector_index.cache_clear()

    result = retriever.retrieve_knowledge(["家庭血压监测 上臂式 电子血压计"], top_k=5)
    assert result.evidence
    assert calls["n"] >= 1, "the openai query-embedding path must be exercised"
    assert any("home_bp_monitoring" in item.allowed_uses for item in result.evidence)
