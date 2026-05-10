from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Tuple

import yaml

from app.services.config_loader import resolve_project_path


FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_\-]+", "_", value.strip().lower())
    return slug.strip("_") or "chunk"


def _read_markdown(path: Path) -> Tuple[Dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    metadata = yaml.safe_load(match.group(1)) or {}
    content = text[match.end() :]
    return metadata, content


def _jsonable_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable_value(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _jsonable_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return {key: _jsonable_value(value) for key, value in metadata.items()}


def _split_markdown(content: str, max_chars: int = 900) -> List[str]:
    sections = re.split(r"\n(?=##\s+)", content.strip())
    chunks: List[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= max_chars:
            chunks.append(section)
            continue
        paragraphs = [para.strip() for para in re.split(r"\n\s*\n", section) if para.strip()]
        current = ""
        for paragraph in paragraphs:
            if len(current) + len(paragraph) + 2 > max_chars and current:
                chunks.append(current.strip())
                current = paragraph
            else:
                current = f"{current}\n\n{paragraph}".strip()
        if current:
            chunks.append(current.strip())
    return chunks


def build_chunks(raw_dir: str = None) -> List[Dict[str, Any]]:
    raw_path = resolve_project_path(raw_dir or "knowledge_base/raw")
    expanded_path = raw_path / "expanded"
    prefer_governed_notes = expanded_path.exists()
    chunks: List[Dict[str, Any]] = []
    for path in sorted(raw_path.rglob("*.md")):
        metadata, content = _read_markdown(path)
        metadata = _jsonable_metadata(metadata)
        if prefer_governed_notes and metadata.get("derived_from") != "knowledge_base/sources/source_catalog.yaml":
            continue
        source_id = metadata.get("source_id") or _slug(path.stem)
        for index, chunk_text in enumerate(_split_markdown(content), start=1):
            source_hash = metadata.get("source_hash")
            if not source_hash:
                hash_input = f"{metadata.get('title', '')}|{metadata.get('url', '')}|{metadata.get('doi', '')}|{metadata.get('pmid', '')}"
                source_hash = __import__("hashlib").sha256(hash_input.encode("utf-8")).hexdigest()[:16]
            chunk = {
                **metadata,
                "chunk_id": f"{source_id}_{index:03d}",
                "source_path": str(path.relative_to(resolve_project_path("."))),
                "source_hash": source_hash,
                "review_status": metadata.get("review_status", "legacy_reviewed"),
                "evidence_class": metadata.get("evidence_class", "legacy"),
                "source_quality_score": metadata.get("source_quality_score", ""),
                "allowed_uses": metadata.get("allowed_uses", []),
                "derived_from": metadata.get("derived_from", str(path.relative_to(resolve_project_path(".")))),
                "content": re.sub(r"\s+", " ", chunk_text).strip(),
            }
            chunks.append(chunk)
    return chunks


def _write_jsonl(chunks: Iterable[Dict[str, Any]], output_path: str = None) -> Path:
    out_path = resolve_project_path(output_path or "knowledge_base/processed/chunks.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    return out_path


def _try_vector_index(chunks: List[Dict[str, Any]]) -> str:
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        return f"vector index skipped: optional dependencies unavailable ({exc.__class__.__name__})"

    model_name = "BAAI/bge-small-zh-v1.5"
    persist_dir = resolve_project_path("knowledge_base/vector_store")
    persist_dir.mkdir(parents=True, exist_ok=True)
    model = SentenceTransformer(model_name)
    client = chromadb.PersistentClient(path=str(persist_dir))
    collection = client.get_or_create_collection("ppg_bp_knowledge")
    ids = [chunk["chunk_id"] for chunk in chunks]
    documents = [chunk["content"] for chunk in chunks]
    metadatas = [
        {key: str(value) for key, value in chunk.items() if key != "content"}
        for chunk in chunks
    ]
    embeddings = model.encode(documents, normalize_embeddings=True).tolist()
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    return f"vector index updated: {len(chunks)} chunks"


def ingest_knowledge_base(raw_dir: str = None, output_path: str = None, build_vector: bool = False) -> Dict[str, Any]:
    chunks = build_chunks(raw_dir=raw_dir)
    out_path = _write_jsonl(chunks, output_path=output_path)
    vector_status = "vector index skipped: set build_vector=true to enable optional Chroma indexing"
    if build_vector:
        vector_status = _try_vector_index(chunks)
    return {
        "chunk_count": len(chunks),
        "chunks_path": str(out_path),
        "vector_status": vector_status,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Markdown knowledge base into chunks.jsonl.")
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--output-path", default=None)
    parser.add_argument("--vector", action="store_true", help="Try optional Chroma + sentence-transformers index.")
    args = parser.parse_args()
    result = ingest_knowledge_base(args.raw_dir, args.output_path, build_vector=args.vector)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
