from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

from app.services.chunking import chunk_text, tokenize_for_match
from app.services.config_loader import resolve_project_path
from app.services.fulltext_candidates import validate_fulltext_catalog
from app.services.source_catalog import included_sources


DOWNLOADS_ROOT = "knowledge_base/sources/downloads"
VECTOR_ROOT = "knowledge_base/vector_store"
MANIFEST_PATH = "knowledge_base/processed/fulltext_vector_manifest.json"
# Pages whose extracted text is shorter than this are header/footer debris
# and would only produce degenerate chunks with no retrievable content.
MIN_PAGE_TEXT_CHARS = 40


@dataclass
class FulltextChunk:
    chunk_id: str
    text: str
    metadata: Dict[str, Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _load_pdf_pages(path: Path) -> Tuple[List[str], str]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - depends on optional local package.
        raise RuntimeError("pypdf is required for PDF full-text extraction; install the rag extra or pypdf.") from exc

    reader = PdfReader(str(path))
    pages: List[str] = []
    for page in reader.pages:
        try:
            pages.append(_normalize_text(page.extract_text() or ""))
        except Exception:
            pages.append("")
    return pages, "pypdf"


def split_text_for_fulltext_chunks(
    text: str,
    target_chars: int = 850,
    overlap_chars: int = 140,
    min_chars: int = 120,
) -> List[str]:
    """Split PDF-extracted text into sentence-safe chunks with local overlap.

    Delegates to the shared structure-aware chunker so summary notes and PDF
    full text use identical sentence-boundary and overlap semantics. Pages with
    almost no extracted text (running headers, page numbers) are dropped
    instead of becoming degenerate few-character chunks.
    """
    if len((text or "").strip()) < MIN_PAGE_TEXT_CHARS:
        return []
    chunks = chunk_text(
        text,
        target_chars=target_chars,
        min_chars=min_chars,
        overlap_chars=overlap_chars,
        hard_max_chars=max(target_chars, 900),
    )
    return [re.sub(r"\s+", " ", chunk).strip() for chunk in chunks if chunk.strip()]


def hashing_embedding(text: str, dims: int = 384) -> np.ndarray:
    """Create a deterministic normalized hashing vector without external model downloads."""
    vector = np.zeros(dims, dtype=np.float32)
    for token in tokenize_for_match(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "little")
        index = value % dims
        sign = 1.0 if (value >> 63) else -1.0
        vector[index] += sign
    norm = float(np.linalg.norm(vector))
    if norm > 0:
        vector /= norm
    return vector


def _candidate_by_source() -> Dict[str, Dict[str, Any]]:
    report = validate_fulltext_catalog()
    return {candidate["source_id"]: candidate for candidate in report.get("candidates", [])}


def _source_by_id() -> Dict[str, Dict[str, Any]]:
    return {source["source_id"]: source for source in included_sources()}


def _jsonable(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)


def _build_chunks_for_pdf(
    source: Dict[str, Any],
    candidate: Optional[Dict[str, Any]],
    pdf_path: Path,
    target_chars: int,
    overlap_chars: int,
) -> Tuple[List[FulltextChunk], Dict[str, Any]]:
    pages, extraction_method = _load_pdf_pages(pdf_path)
    pdf_sha256 = _sha256_file(pdf_path)
    chunks: List[FulltextChunk] = []
    source_id = source["source_id"]
    for page_index, page_text in enumerate(pages, start=1):
        for local_index, chunk_text in enumerate(
            split_text_for_fulltext_chunks(page_text, target_chars=target_chars, overlap_chars=overlap_chars),
            start=1,
        ):
            metadata = {
                "source_id": source_id,
                "candidate_id": (candidate or {}).get("candidate_id", ""),
                "title": source.get("title", ""),
                "organization": source.get("organization", ""),
                "region": source.get("region", ""),
                "topic": source.get("topic", ""),
                "language": source.get("language", ""),
                "url": source.get("url", ""),
                "doi": source.get("doi", ""),
                "pmid": source.get("pmid", ""),
                "year": source.get("year", ""),
                "evidence_class": source.get("evidence_class", ""),
                "allowed_uses": source.get("allowed_uses", []),
                "review_status": source.get("review_status", "included"),
                "source_quality_score": source.get("source_quality_score", ""),
                "local_pdf": str(pdf_path.relative_to(resolve_project_path("."))),
                "pdf_sha256": pdf_sha256,
                "page_start": page_index,
                "page_end": page_index,
                "extraction_method": extraction_method,
                "governance_note": "local_fulltext_vector_only_not_committed_raw_pdf_text",
            }
            chunk_id = f"fulltext::{source_id}::p{page_index:03d}::c{local_index:02d}"
            chunks.append(FulltextChunk(chunk_id=chunk_id, text=chunk_text, metadata=_jsonable(metadata)))
    source_manifest = {
        "source_id": source_id,
        "title": source.get("title", ""),
        "local_pdf": str(pdf_path.relative_to(resolve_project_path("."))),
        "pdf_sha256": pdf_sha256,
        "page_count": len(pages),
        "chunk_count": len(chunks),
        "extraction_method": extraction_method,
    }
    return chunks, source_manifest


def build_fulltext_chunks(
    source_ids: Optional[Iterable[str]] = None,
    target_chars: int = 850,
    overlap_chars: int = 140,
) -> Tuple[List[FulltextChunk], List[Dict[str, Any]], List[Dict[str, str]]]:
    downloads_root = resolve_project_path(DOWNLOADS_ROOT)
    source_filter = set(source_ids or [])
    candidates = _candidate_by_source()
    sources = _source_by_id()
    chunks: List[FulltextChunk] = []
    sources_manifest: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []

    for source_id, source in sorted(sources.items()):
        if source_filter and source_id not in source_filter:
            continue
        pdf_path = downloads_root / f"{source_id}.pdf"
        if not pdf_path.exists():
            skipped.append({"source_id": source_id, "reason": "local_pdf_missing"})
            continue
        try:
            source_chunks, source_manifest = _build_chunks_for_pdf(
                source=source,
                candidate=candidates.get(source_id),
                pdf_path=pdf_path,
                target_chars=target_chars,
                overlap_chars=overlap_chars,
            )
        except Exception as exc:
            skipped.append({"source_id": source_id, "reason": f"extract_failed:{exc.__class__.__name__}:{exc}"})
            continue
        chunks.extend(source_chunks)
        sources_manifest.append(source_manifest)
    return chunks, sources_manifest, skipped


def write_local_fulltext_chunks(chunks: List[FulltextChunk], path: Optional[str] = None) -> Path:
    out_path = resolve_project_path(path or f"{VECTOR_ROOT}/fulltext_chunks.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(
                json.dumps(
                    {"chunk_id": chunk.chunk_id, "content": chunk.text, **chunk.metadata},
                    ensure_ascii=False,
                )
                + "\n"
            )
    return out_path


def write_hashing_vector_index(chunks: List[FulltextChunk], dims: int = 384, path: Optional[str] = None) -> Path:
    out_path = resolve_project_path(path or f"{VECTOR_ROOT}/fulltext_hashing_vectors.npz")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    embeddings = np.vstack([hashing_embedding(chunk.text, dims=dims) for chunk in chunks]) if chunks else np.zeros((0, dims), dtype=np.float32)
    ids = np.array([chunk.chunk_id for chunk in chunks], dtype=object)
    metadata = np.array([json.dumps(chunk.metadata, ensure_ascii=False, sort_keys=True) for chunk in chunks], dtype=object)
    np.savez_compressed(out_path, ids=ids, embeddings=embeddings, metadata=metadata)
    return out_path


def rebuild_hashing_vectors_from_jsonl(
    chunks_path: Optional[str] = None,
    vector_path: Optional[str] = None,
    dims: int = 384,
) -> Dict[str, Any]:
    """Recompute hashing vectors for an existing chunks JSONL.

    Used when the chunk text is already on disk but the tokenizer changed (the
    query-time embedding must share the index-time token space) and the source
    PDFs are not present locally to re-chunk from scratch.
    """
    chunk_file = resolve_project_path(chunks_path or f"{VECTOR_ROOT}/fulltext_chunks.jsonl")
    if not chunk_file.exists():
        return {"status": "skipped", "reason": "chunks_jsonl_missing", "chunks_path": str(chunk_file)}
    chunks: List[FulltextChunk] = []
    with chunk_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            metadata = {key: value for key, value in item.items() if key not in {"chunk_id", "content"}}
            chunks.append(FulltextChunk(chunk_id=item["chunk_id"], text=item.get("content", ""), metadata=metadata))
    out_path = write_hashing_vector_index(chunks, dims=dims, path=vector_path)
    return {
        "status": "ok",
        "chunk_count": len(chunks),
        "vector_path": str(out_path),
        "embedding_dims": dims,
    }


def query_hashing_vector_index(query: str, top_k: int = 5, vector_path: Optional[str] = None, chunks_path: Optional[str] = None) -> List[Dict[str, Any]]:
    vector_file = resolve_project_path(vector_path or f"{VECTOR_ROOT}/fulltext_hashing_vectors.npz")
    chunk_file = resolve_project_path(chunks_path or f"{VECTOR_ROOT}/fulltext_chunks.jsonl")
    if not vector_file.exists() or not chunk_file.exists():
        return []
    data = np.load(vector_file, allow_pickle=True)
    ids = data["ids"]
    embeddings = data["embeddings"]
    if embeddings.shape[0] == 0:
        return []
    query_vector = hashing_embedding(query, dims=embeddings.shape[1])
    scores = np.einsum("ij,j->i", embeddings.astype(np.float64), query_vector.astype(np.float64))
    chunk_by_id: Dict[str, Dict[str, Any]] = {}
    with chunk_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                item = json.loads(line)
                chunk_by_id[item["chunk_id"]] = item
    order = np.argsort(-scores)[:top_k]
    results: List[Dict[str, Any]] = []
    for index in order:
        chunk_id = str(ids[index])
        item = chunk_by_id.get(chunk_id, {"chunk_id": chunk_id})
        results.append({**item, "score": round(float(scores[index]), 4)})
    return results


def build_fulltext_vector_index(
    source_ids: Optional[Iterable[str]] = None,
    target_chars: int = 850,
    overlap_chars: int = 140,
    dims: int = 384,
    chunks_path: Optional[str] = None,
    vector_path: Optional[str] = None,
    manifest_path: Optional[str] = None,
) -> Dict[str, Any]:
    started = time.time()
    chunks, sources_manifest, skipped = build_fulltext_chunks(
        source_ids=source_ids,
        target_chars=target_chars,
        overlap_chars=overlap_chars,
    )
    local_chunks_path = write_local_fulltext_chunks(chunks, path=chunks_path)
    local_vector_path = write_hashing_vector_index(chunks, dims=dims, path=vector_path)
    source_count = sum(1 for source in sources_manifest if source.get("chunk_count", 0) > 0)
    page_count = sum(int(source.get("page_count") or 0) for source in sources_manifest)
    manifest = {
        "timestamp": int(time.time()),
        "backend": "local_hashing_vectors",
        "purpose": "Local full-text PDF chunking and vector indexing. Raw PDF text stays in ignored vector_store files and is not committed.",
        "target_chars": target_chars,
        "overlap_chars": overlap_chars,
        "embedding_dims": dims,
        "source_count": source_count,
        "page_count": page_count,
        "chunk_count": len(chunks),
        "chunks_path": str(local_chunks_path),
        "vector_path": str(local_vector_path),
        "duration_sec": round(time.time() - started, 3),
        "sources": sources_manifest,
        "skipped": skipped,
    }
    out_path = resolve_project_path(manifest_path or MANIFEST_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def summarize_query_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summary: List[Dict[str, Any]] = []
    for item in results:
        content = re.sub(r"\s+", " ", item.get("content", "")).strip()
        summary.append(
            {
                "chunk_id": item.get("chunk_id"),
                "score": item.get("score"),
                "title": item.get("title"),
                "source_id": item.get("source_id"),
                "page_start": item.get("page_start"),
                "topic": item.get("topic"),
                "allowed_uses": item.get("allowed_uses"),
                "snippet": content[:260] + ("..." if len(content) > 260 else ""),
            }
        )
    return summary
