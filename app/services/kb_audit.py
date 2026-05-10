from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

from app.services.config_loader import resolve_project_path
from app.services.source_catalog import EXPECTED_TOPICS, HIGH_TRUST_EVIDENCE_CLASSES, screen_sources


def load_chunks(chunks_path: str = "knowledge_base/processed/chunks.jsonl") -> List[Dict[str, Any]]:
    path = resolve_project_path(chunks_path)
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def audit_knowledge_base(chunks_path: str = "knowledge_base/processed/chunks.jsonl") -> Dict[str, Any]:
    chunks = load_chunks(chunks_path)
    catalog = screen_sources()
    included_ids = {source["source_id"] for source in catalog["included_sources"]}

    topics = Counter(chunk.get("topic") for chunk in chunks)
    evidence_classes = Counter(chunk.get("evidence_class") for chunk in chunks)
    source_ids = Counter(chunk.get("source_id") for chunk in chunks)
    hash_sources = defaultdict(set)
    for chunk in chunks:
        if chunk.get("source_hash"):
            hash_sources[chunk.get("source_hash")].add(chunk.get("source_id"))

    missing_topics = sorted(EXPECTED_TOPICS - set(topic for topic in topics if topic))
    duplicate_hashes = sorted(hash_value for hash_value, source_ids in hash_sources.items() if len(source_ids) > 1)
    orphan_chunks = sorted(
        set(chunk.get("source_id") for chunk in chunks if chunk.get("source_id"))
        - included_ids
    )

    unsafe_source_leakage = []
    for chunk in chunks:
        allowed_uses = chunk.get("allowed_uses") or []
        if isinstance(allowed_uses, str):
            allowed_uses = [part.strip() for part in allowed_uses.split(",") if part.strip()]
        sensitive = {"emergency_alert", "medication_safety"} & set(allowed_uses)
        if sensitive and chunk.get("evidence_class") not in HIGH_TRUST_EVIDENCE_CLASSES:
            unsafe_source_leakage.append(chunk.get("chunk_id"))

    topic_sources = defaultdict(set)
    for chunk in chunks:
        topic_sources[chunk.get("topic")].add(chunk.get("source_id"))

    return {
        "chunk_count": len(chunks),
        "source_count": len(source_ids),
        "catalog_included_count": catalog["included_count"],
        "topic_counts": dict(topics),
        "topic_source_counts": {topic: len(ids) for topic, ids in topic_sources.items() if topic},
        "evidence_class_counts": dict(evidence_classes),
        "missing_topics": missing_topics,
        "duplicate_source_hashes": duplicate_hashes,
        "orphan_source_ids": orphan_chunks,
        "unsafe_source_leakage": unsafe_source_leakage,
        "quality": {
            "has_all_expected_topics": not missing_topics,
            "has_no_unsafe_source_leakage": not unsafe_source_leakage,
            "has_catalog_alignment": not orphan_chunks,
        },
    }
