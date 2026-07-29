import json

import numpy as np
import pytest

from app.services.config_loader import OpenAIEmbeddingConfig
from app.services.openai_embedding_index import (
    OpenAIEmbeddingError,
    _normalize_embeddings,
    _validate_upstream_current,
    build_openai_embedding_index,
    embed_texts,
    load_embedding_chunks,
)


def test_normalize_embeddings_handles_zero_rows():
    vectors = np.array([[3.0, 4.0], [0.0, 0.0]], dtype=np.float32)
    normalized = _normalize_embeddings(vectors)
    assert np.allclose(normalized[0], [0.6, 0.8])
    assert np.allclose(normalized[1], [0.0, 0.0])


def test_embed_texts_reports_completed_batches(monkeypatch):
    config = OpenAIEmbeddingConfig(
        provider="openai",
        api_key="test",
        base_url="https://api.openai.com/v1",
        model="text-embedding-3-small",
        dimensions=2,
        batch_size=2,
        input_scope="processed_chunks",
        max_concurrency=2,
    )

    def fake_post(texts, config, session, timeout_sec):
        return {
            "model": config.model,
            "data": [{"index": index, "embedding": [1.0, 0.0]} for index in range(len(texts))],
            "usage": {},
        }

    monkeypatch.setattr("app.services.openai_embedding_index._post_embeddings", fake_post)
    progress = []
    embeddings, _, _ = embed_texts(
        ["a", "b", "c"],
        config,
        progress_callback=lambda completed, total: progress.append((completed, total)),
    )

    assert embeddings.shape == (3, 2)
    assert progress == [(0, 2), (1, 2), (2, 2)]


def test_embed_texts_handles_empty_input_without_provider_call(monkeypatch):
    config = OpenAIEmbeddingConfig(
        provider="openai",
        api_key="test",
        base_url="https://api.openai.com/v1",
        model="text-embedding-3-small",
        dimensions=8,
        batch_size=2,
        input_scope="processed_chunks",
    )
    monkeypatch.setattr(
        "app.services.openai_embedding_index._post_embeddings",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("provider must not be called")),
    )

    embeddings, usage, returned_model = embed_texts([], config)

    assert embeddings.shape == (0, 8)
    assert usage == {"prompt_tokens": 0, "total_tokens": 0}
    assert returned_model == config.model


def test_load_embedding_chunks_reads_processed_chunk_shape(tmp_path, monkeypatch):
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(
        json.dumps(
            {
                "chunk_id": "chunk-1",
                "source_id": "source-1",
                "title": "家庭血压监测",
                "topic": "home_bp_monitoring",
                "content": "安静休息后用上臂式血压计复测。",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_scope_paths(scope):
        return chunks_path, tmp_path / "vectors.npz", tmp_path / "manifest.json"

    monkeypatch.setattr("app.services.openai_embedding_index._scope_paths", fake_scope_paths)
    chunks = load_embedding_chunks("processed_chunks")
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "chunk-1"
    assert chunks[0].content == "安静休息后用上臂式血压计复测。"
    assert chunks[0].metadata["source_id"] == "source-1"
    assert "content" not in chunks[0].metadata


def test_load_embedding_chunks_filters_source_ids_before_limit(tmp_path, monkeypatch):
    chunks_path = tmp_path / "chunks.jsonl"
    rows = [
        {"chunk_id": "a-1", "source_id": "a", "content": "A"},
        {"chunk_id": "b-1", "source_id": "b", "content": "B"},
        {"chunk_id": "b-2", "source_id": "b", "content": "B2"},
    ]
    chunks_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

    def fake_scope_paths(scope):
        return chunks_path, tmp_path / "vectors.npz", tmp_path / "manifest.json"

    monkeypatch.setattr("app.services.openai_embedding_index._scope_paths", fake_scope_paths)
    chunks = load_embedding_chunks("processed_chunks", limit=1, source_ids=["b"])
    assert [chunk.chunk_id for chunk in chunks] == ["b-1"]


def test_build_openai_embedding_index_manifest_tracks_requested_and_indexed_sources(tmp_path, monkeypatch):
    chunks_path = tmp_path / "chunks.jsonl"
    rows = [
        {"chunk_id": "a-1", "source_id": "a", "content": "A"},
        {"chunk_id": "b-1", "source_id": "b", "content": "B"},
        {"chunk_id": "b-2", "source_id": "b", "content": "B2"},
    ]
    chunks_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    vector_path = tmp_path / "vectors.npz"
    manifest_path = tmp_path / "manifest.json"

    def fake_scope_paths(scope):
        return chunks_path, vector_path, manifest_path

    def fake_config():
        return OpenAIEmbeddingConfig(
            provider="openai",
            api_key="test",
            base_url="https://api.openai.com/v1",
            model="text-embedding-3-small",
            dimensions=2,
            batch_size=2,
            input_scope="processed_chunks",
        )

    def fake_embed_texts(texts, config, timeout_sec):
        embeddings = np.ones((len(texts), 2), dtype=np.float32)
        return embeddings, {"prompt_tokens": len(texts), "total_tokens": len(texts)}, config.model

    monkeypatch.setattr("app.services.openai_embedding_index._scope_paths", fake_scope_paths)
    monkeypatch.setattr("app.services.openai_embedding_index._validate_upstream_current", lambda scope: None)
    monkeypatch.setattr("app.services.openai_embedding_index.load_openai_embedding_config", fake_config)
    monkeypatch.setattr("app.services.openai_embedding_index.embed_texts", fake_embed_texts)

    manifest = build_openai_embedding_index("fulltext_chunks", source_ids=["b"], limit=1)

    assert manifest["input_scope"] == "fulltext_chunks"
    assert manifest["configured_input_scope"] == "processed_chunks"
    assert manifest["source_ids_filter"] == ["b"]
    assert manifest["source_ids_indexed"] == ["b"]
    assert manifest["chunk_count"] == 1
    assert manifest["timeout_sec"] == 60.0
    assert manifest["max_concurrency"] == 1


def test_openai_fulltext_build_rejects_failed_upstream(tmp_path, monkeypatch):
    manifest_path = tmp_path / "fulltext-manifest.json"
    manifest_path.write_text(
        json.dumps({"status": "failed", "input_fingerprint": "old"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.services.openai_embedding_index.resolve_project_path",
        lambda path: manifest_path,
    )

    with pytest.raises(OpenAIEmbeddingError, match="missing, stale, or failed"):
        _validate_upstream_current("fulltext_chunks")
