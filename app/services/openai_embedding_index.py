from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import numpy as np
import requests

from app.services.config_loader import OpenAIEmbeddingConfig, load_openai_embedding_config, resolve_project_path


VECTOR_ROOT = "knowledge_base/vector_store"
PROCESSED_CHUNKS_PATH = "knowledge_base/processed/chunks.jsonl"
FULLTEXT_CHUNKS_PATH = "knowledge_base/vector_store/fulltext_chunks.jsonl"
MANIFEST_TEMPLATE = "knowledge_base/processed/openai_embedding_manifest_{scope}.json"


class OpenAIEmbeddingError(RuntimeError):
    pass


@dataclass
class EmbeddingChunk:
    chunk_id: str
    content: str
    metadata: Dict[str, Any]


def _scope_paths(scope: str) -> tuple[Path, Path, Path]:
    if scope == "processed_chunks":
        chunks_path = resolve_project_path(PROCESSED_CHUNKS_PATH)
        vector_path = resolve_project_path(f"{VECTOR_ROOT}/openai_embeddings_processed_chunks.npz")
    elif scope == "fulltext_chunks":
        chunks_path = resolve_project_path(FULLTEXT_CHUNKS_PATH)
        vector_path = resolve_project_path(f"{VECTOR_ROOT}/openai_embeddings_fulltext_chunks.npz")
    else:
        raise ValueError("scope must be one of: processed_chunks, fulltext_chunks")
    manifest_path = resolve_project_path(MANIFEST_TEMPLATE.format(scope=scope))
    return chunks_path, vector_path, manifest_path


def _upstream_build_fingerprint(scope: str) -> str:
    manifest_name = (
        "knowledge_base/processed/chunks_manifest.json"
        if scope == "processed_chunks"
        else "knowledge_base/processed/fulltext_vector_manifest.json"
    )
    path = resolve_project_path(manifest_name)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        manifest = {}
    if scope == "processed_chunks":
        return str(manifest.get("build_fingerprint") or "")
    return str(manifest.get("input_fingerprint") or "")


def _jsonable_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    excluded = {"content", "text"}
    metadata = {key: value for key, value in item.items() if key not in excluded}
    return {str(key): value for key, value in metadata.items()}


def _embedding_text(chunk: EmbeddingChunk) -> str:
    # Shared composition (title/section/topic/uses prefix) keeps the remote
    # embedding space aligned with the offline hashing index and keyword scorer.
    from app.services.chunking import build_embedding_text

    return build_embedding_text(chunk.metadata, chunk.content).strip()


def load_embedding_chunks(
    scope: str = "processed_chunks",
    limit: Optional[int] = None,
    offset: int = 0,
    source_ids: Optional[Iterable[str]] = None,
) -> List[EmbeddingChunk]:
    chunks_path, _, _ = _scope_paths(scope)
    if not chunks_path.exists():
        raise FileNotFoundError(chunks_path)
    source_filter = set(source_ids or [])
    chunks: List[EmbeddingChunk] = []
    matched_index = 0
    with chunks_path.open("r", encoding="utf-8") as handle:
        for line_index, line in enumerate(handle):
            if not line.strip():
                continue
            item = json.loads(line)
            if source_filter and str(item.get("source_id") or "") not in source_filter:
                continue
            if matched_index < offset:
                matched_index += 1
                continue
            if limit is not None and len(chunks) >= limit:
                break
            content = str(item.get("content") or item.get("text") or "").strip()
            if not content:
                continue
            chunk_id = str(item.get("chunk_id") or item.get("source_id") or f"{scope}_{line_index}")
            chunks.append(EmbeddingChunk(chunk_id=chunk_id, content=content, metadata=_jsonable_metadata(item)))
            matched_index += 1
    return chunks


def _normalize_embeddings(embeddings: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return embeddings / norms


def _post_embeddings(
    texts: List[str],
    config: OpenAIEmbeddingConfig,
    session: requests.Session,
    timeout_sec: float,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"model": config.model, "input": texts}
    if config.dimensions and config.model.startswith("text-embedding-3"):
        payload["dimensions"] = config.dimensions
    response = session.post(
        f"{config.base_url}/embeddings",
        headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=timeout_sec,
        allow_redirects=False,
    )
    if response.status_code >= 400:
        # Never include a provider-controlled response body in logs/errors: a
        # misconfigured endpoint could echo Authorization or submitted text.
        raise OpenAIEmbeddingError(f"OpenAI embeddings HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise OpenAIEmbeddingError("OpenAI embeddings response was not valid JSON") from exc


def embed_texts(
    texts: List[str],
    config: OpenAIEmbeddingConfig,
    timeout_sec: float = 60.0,
    max_retries: int = 3,
) -> tuple[np.ndarray, Dict[str, int], str]:
    if not config.api_key:
        raise OpenAIEmbeddingError("OPENAI_EMBEDDING_API_KEY is not set")
    embeddings: List[List[float]] = []
    usage = {"prompt_tokens": 0, "total_tokens": 0}
    returned_model = config.model
    session = requests.Session()
    for start in range(0, len(texts), config.batch_size):
        batch = texts[start : start + config.batch_size]
        for attempt in range(max_retries + 1):
            try:
                data = _post_embeddings(batch, config, session=session, timeout_sec=timeout_sec)
                break
            except (requests.RequestException, OpenAIEmbeddingError):
                if attempt >= max_retries:
                    raise
                time.sleep(min(2**attempt, 8))
        returned_model = str(data.get("model") or returned_model)
        usage_payload = data.get("usage") or {}
        usage["prompt_tokens"] += int(usage_payload.get("prompt_tokens") or 0)
        usage["total_tokens"] += int(usage_payload.get("total_tokens") or 0)
        batch_embeddings = [item["embedding"] for item in sorted(data.get("data", []), key=lambda item: item["index"])]
        if len(batch_embeddings) != len(batch):
            raise OpenAIEmbeddingError("OpenAI embeddings response count did not match input count")
        embeddings.extend(batch_embeddings)
    array = np.array(embeddings, dtype=np.float32)
    return _normalize_embeddings(array), usage, returned_model


def build_openai_embedding_index(
    scope: str = "processed_chunks",
    limit: Optional[int] = None,
    offset: int = 0,
    timeout_sec: float = 60.0,
    source_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    started = time.time()
    config = load_openai_embedding_config()
    requested_source_ids = sorted({str(item) for item in source_ids or [] if str(item).strip()})
    chunks = load_embedding_chunks(
        scope=scope,
        limit=limit,
        offset=offset,
        source_ids=requested_source_ids or None,
    )
    texts = [_embedding_text(chunk) for chunk in chunks]
    embeddings, usage, returned_model = embed_texts(texts, config=config, timeout_sec=timeout_sec)
    _, vector_path, manifest_path = _scope_paths(scope)
    vector_path.parent.mkdir(parents=True, exist_ok=True)
    ids = np.array([chunk.chunk_id for chunk in chunks], dtype=object)
    metadata = np.array([json.dumps(chunk.metadata, ensure_ascii=False, sort_keys=True) for chunk in chunks], dtype=object)
    np.savez_compressed(vector_path, ids=ids, embeddings=embeddings, metadata=metadata)

    indexed_source_ids = sorted(
        {str(chunk.metadata.get("source_id") or "") for chunk in chunks if chunk.metadata.get("source_id")}
    )
    manifest = {
        "timestamp": int(time.time()),
        "backend": "openai_embeddings",
        "scope": scope,
        "purpose": (
            "External OpenAI embedding index for governed KB chunks. "
            "The API key is loaded from the active encrypted integration profile "
            "or the first-start environment fallback and is never persisted here."
        ),
        "model_requested": config.model,
        "model_returned": returned_model,
        "embedding_dimensions": int(embeddings.shape[1]) if embeddings.ndim == 2 else 0,
        "chunk_count": len(chunks),
        "source_count": len(indexed_source_ids),
        "offset": offset,
        "limit": limit,
        "source_ids_filter": requested_source_ids,
        "source_ids_indexed": indexed_source_ids,
        "batch_size": config.batch_size,
        "input_scope": scope,
        "configured_input_scope": config.input_scope,
        "usage": usage,
        "chunks_path": str(_scope_paths(scope)[0]),
        "vector_path": str(vector_path),
        "duration_sec": round(time.time() - started, 3),
    }
    from app.services.fingerprints import combine_fingerprints, sha256_file

    manifest["input_sha256"] = sha256_file(str(_scope_paths(scope)[0]))
    manifest["upstream_build_fingerprint"] = _upstream_build_fingerprint(scope)
    manifest["input_fingerprint"] = combine_fingerprints(
        {
            "chunks_sha256": manifest["input_sha256"],
            "upstream_build_fingerprint": manifest["upstream_build_fingerprint"],
        }
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _load_chunk_content(path: Path) -> Dict[str, Dict[str, Any]]:
    chunks: Dict[str, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            chunk_id = str(item.get("chunk_id") or item.get("source_id") or "")
            if chunk_id:
                chunks[chunk_id] = item
    return chunks


def query_openai_embedding_index(
    query: str,
    scope: str = "processed_chunks",
    top_k: int = 5,
    timeout_sec: float = 60.0,
    allowed_uses: Optional[Iterable[str]] = None,
    min_quality_score: Optional[float] = 18,
    cn_boost: float = 0.0,
    high_trust_boost: float = 0.0,
) -> List[Dict[str, Any]]:
    """Diagnostic query helper for a local embedding index.

    Production report generation should pass scenario-specific allowed_uses, keep
    min_quality_score enabled, and preserve the main safety agent checks.
    """
    from app.services.retriever import _chunk_allowed
    from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES

    config = load_openai_embedding_config()
    chunks_path, vector_path, _ = _scope_paths(scope)
    if not vector_path.exists():
        raise FileNotFoundError(vector_path)
    data = np.load(vector_path, allow_pickle=True)
    ids = data["ids"]
    embeddings = data["embeddings"].astype(np.float32)
    query_vector, _, _ = embed_texts([query], config=config, timeout_sec=timeout_sec)
    chunks_by_id = _load_chunk_content(chunks_path)
    required_uses: Set[str] = set(allowed_uses or [])
    candidate_indices = [
        index for index, chunk_id in enumerate(ids)
        if _chunk_allowed(chunks_by_id.get(str(chunk_id), {}), required_uses, None, min_quality_score)
    ]
    if not candidate_indices:
        candidate_indices = [
            index for index, chunk_id in enumerate(ids)
            if _chunk_allowed(chunks_by_id.get(str(chunk_id), {}), set(), None, min_quality_score)
        ]
    if not candidate_indices:
        return []

    candidate_embeddings = embeddings[candidate_indices].astype(np.float64)
    scores = np.einsum("ij,j->i", candidate_embeddings, query_vector[0].astype(np.float64))
    boosted_scores: List[float] = []
    for local_index, score in enumerate(scores):
        chunk = chunks_by_id.get(str(ids[candidate_indices[local_index]]), {})
        adjusted = float(score)
        if cn_boost and chunk.get("region") == "CN":
            adjusted += cn_boost
        if high_trust_boost and chunk.get("evidence_class") in HIGH_TRUST_EVIDENCE_CLASSES:
            adjusted += high_trust_boost
        boosted_scores.append(adjusted)
    order = np.argsort(-np.array(boosted_scores))[:top_k]
    results: List[Dict[str, Any]] = []
    for local_index in order:
        global_index = candidate_indices[int(local_index)]
        chunk_id = str(ids[global_index])
        item = chunks_by_id.get(chunk_id, {"chunk_id": chunk_id})
        content = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
        results.append(
            {
                "chunk_id": chunk_id,
                "score": round(float(boosted_scores[int(local_index)]), 4),
                "embedding_score": round(float(scores[int(local_index)]), 4),
                "source_id": item.get("source_id"),
                "title": item.get("title"),
                "topic": item.get("topic"),
                "evidence_class": item.get("evidence_class"),
                "allowed_uses": item.get("allowed_uses"),
                "snippet": content[:260] + ("..." if len(content) > 260 else ""),
            }
        )
    return results
