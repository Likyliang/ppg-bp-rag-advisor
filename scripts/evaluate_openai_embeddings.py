from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.report import Evidence
from app.services.config_loader import load_openai_embedding_config, resolve_project_path
from app.services.openai_embedding_index import _scope_paths, embed_texts
from app.services.retriever import _chunk_allowed, _chunk_to_evidence, infer_allowed_uses, retrieve_knowledge
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES
from scripts.evaluate_retrieval import (
    GOLDEN_QUERIES,
    _class_matches,
    _evidence_matches,
    _topic_matches,
    _unsafe_sources,
)


def _load_chunks(path: Path) -> Dict[str, Dict[str, Any]]:
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


def _load_embedding_index(scope: str) -> tuple[np.ndarray, np.ndarray, Dict[str, Dict[str, Any]]]:
    chunks_path, vector_path, _ = _scope_paths(scope)
    if not vector_path.exists():
        raise FileNotFoundError(f"OpenAI embedding vector index not found: {vector_path}")
    data = np.load(vector_path, allow_pickle=True)
    return data["ids"], data["embeddings"].astype(np.float32), _load_chunks(chunks_path)


def _candidate_indices(
    ids: np.ndarray,
    chunks_by_id: Dict[str, Dict[str, Any]],
    required_uses: Set[str],
    min_quality_score: float = 18,
) -> List[int]:
    candidates = [
        index for index, chunk_id in enumerate(ids)
        if _chunk_allowed(chunks_by_id.get(str(chunk_id), {}), required_uses, None, min_quality_score)
    ]
    if candidates:
        return candidates
    return [
        index for index, chunk_id in enumerate(ids)
        if _chunk_allowed(chunks_by_id.get(str(chunk_id), {}), set(), None, min_quality_score)
    ]


def _select_embedding_evidence(
    *,
    query: str,
    query_vector: np.ndarray,
    ids: np.ndarray,
    embeddings: np.ndarray,
    chunks_by_id: Dict[str, Dict[str, Any]],
    mode: str,
    expected_uses: Iterable[str],
    top_k: int,
    cn_boost: float = 0.0,
    high_trust_boost: float = 0.0,
) -> List[Evidence]:
    if mode == "openai_embedding_metadata_augmented":
        required_uses: Set[str] = set()
    elif mode == "openai_embedding_inferred_uses":
        required_uses = infer_allowed_uses([query])
    elif mode == "openai_embedding_expected_uses":
        required_uses = set(expected_uses)
    elif mode == "openai_embedding_hybrid_cn_boost":
        required_uses = infer_allowed_uses([query])
    else:
        raise ValueError(f"unsupported embedding mode: {mode}")

    candidates = _candidate_indices(ids, chunks_by_id, required_uses=required_uses)
    if not candidates:
        return []
    candidate_embeddings = embeddings[candidates].astype(np.float64)
    scores = np.einsum("ij,j->i", candidate_embeddings, query_vector.astype(np.float64))
    boosted_scores: List[float] = []
    for local_index, score in enumerate(scores):
        chunk = chunks_by_id.get(str(ids[candidates[int(local_index)]]), {})
        adjusted = float(score)
        if mode == "openai_embedding_hybrid_cn_boost" and chunk.get("region") == "CN":
            adjusted += cn_boost
        if mode == "openai_embedding_hybrid_cn_boost" and chunk.get("evidence_class") in HIGH_TRUST_EVIDENCE_CLASSES:
            adjusted += high_trust_boost
        boosted_scores.append(adjusted)
    order = np.argsort(-np.array(boosted_scores))[:top_k]
    evidence: List[Evidence] = []
    for local_index in order:
        global_index = candidates[int(local_index)]
        chunk_id = str(ids[global_index])
        chunk = chunks_by_id.get(chunk_id, {"chunk_id": chunk_id})
        evidence.append(_chunk_to_evidence(chunk, query, float(boosted_scores[int(local_index)])))
    return evidence


def _row_for_evidence(mode: str, case: Dict[str, Any], evidence: List[Evidence]) -> Dict[str, Any]:
    matches = [item for item in evidence if _evidence_matches(item, case["expected_uses"])]
    topic_matches = [item for item in evidence if _topic_matches(item, case["expected_topics"])]
    class_matches = [item for item in evidence if _class_matches(item, case["expected_evidence_classes"])]
    precision = len(matches) / len(evidence) if evidence else 0.0
    topic_precision = len(topic_matches) / len(evidence) if evidence else 0.0
    sensitive = bool(case.get("sensitive"))
    unsafe = _unsafe_sources(evidence, sensitive)
    high_trust_sensitive = True
    if sensitive:
        sensitive_matches = [
            item for item in evidence
            if set(item.allowed_uses or []) & {"emergency_alert", "medication_safety", "special_population"}
        ]
        high_trust_sensitive = bool(sensitive_matches) and all(
            item.evidence_class in HIGH_TRUST_EVIDENCE_CLASSES for item in sensitive_matches
        )
    top1 = evidence[0] if evidence else None
    return {
        "mode": mode,
        "query": case["query"],
        "scenario_type": case.get("scenario_type", "general"),
        "expected_uses": case["expected_uses"],
        "expected_topics": case["expected_topics"],
        "expected_evidence_classes": case["expected_evidence_classes"],
        "retrieved": [item.model_dump() for item in evidence],
        "precision_at_k": round(precision, 3),
        "topic_precision_at_k": round(topic_precision, 3),
        "has_match": bool(matches),
        "has_topic_match": bool(topic_matches),
        "has_expected_class": bool(class_matches),
        "high_trust_sensitive": high_trust_sensitive,
        "unsafe_source_leakage": unsafe,
        "top1_source_id": top1.source_id if top1 else "",
        "top1_title": top1.title if top1 else "",
        "top1_topic": top1.topic if top1 else "",
        "top1_region": top1.region if top1 else "",
        "top1_evidence_class": top1.evidence_class if top1 else "",
    }


def _summary(mode: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"evaluation_mode": mode, "query_count": 0}
    return {
        "evaluation_mode": mode,
        "query_count": len(rows),
        "match_rate": round(sum(1 for row in rows if row["has_match"]) / len(rows), 3),
        "mean_precision_at_5": round(sum(row["precision_at_k"] for row in rows) / len(rows), 3),
        "topic_hit_rate": round(sum(1 for row in rows if row["has_topic_match"]) / len(rows), 3),
        "mean_topic_precision_at_5": round(sum(row["topic_precision_at_k"] for row in rows) / len(rows), 3),
        "expected_class_hit_rate": round(sum(1 for row in rows if row["has_expected_class"]) / len(rows), 3),
        "high_trust_sensitive_rate": round(
            sum(1 for row in rows if row["scenario_type"] != "sensitive" or row["high_trust_sensitive"]) / len(rows),
            3,
        ),
        "unsafe_source_leakage_count": sum(len(row["unsafe_source_leakage"]) for row in rows),
        "top1_cn_rate": round(sum(1 for row in rows if row["top1_region"] == "CN") / len(rows), 3),
    }


def evaluate_openai_embeddings(
    scope: str = "processed_chunks",
    top_k: int = 5,
    timeout_sec: float = 60.0,
    cn_boost: float = 0.03,
    high_trust_boost: float = 0.02,
) -> Dict[str, Any]:
    started = time.time()
    ids, embeddings, chunks_by_id = _load_embedding_index(scope)
    config = load_openai_embedding_config()
    queries = [case["query"] for case in GOLDEN_QUERIES]
    query_vectors, usage, returned_model = embed_texts(queries, config=config, timeout_sec=timeout_sec)

    modes = {
        "current_keyword_retriever": [],
        "openai_embedding_metadata_augmented": [],
        "openai_embedding_inferred_uses": [],
        "openai_embedding_hybrid_cn_boost": [],
        "openai_embedding_expected_uses": [],
    }
    for index, case in enumerate(GOLDEN_QUERIES):
        baseline = retrieve_knowledge([case["query"]], top_k=top_k, min_quality_score=18).evidence
        modes["current_keyword_retriever"].append(_row_for_evidence("current_keyword_retriever", case, baseline))
        for mode in [
            "openai_embedding_metadata_augmented",
            "openai_embedding_inferred_uses",
            "openai_embedding_hybrid_cn_boost",
            "openai_embedding_expected_uses",
        ]:
            evidence = _select_embedding_evidence(
                query=case["query"],
                query_vector=query_vectors[index],
                ids=ids,
                embeddings=embeddings,
                chunks_by_id=chunks_by_id,
                mode=mode,
                expected_uses=case["expected_uses"],
                top_k=top_k,
                cn_boost=cn_boost,
                high_trust_boost=high_trust_boost,
            )
            modes[mode].append(_row_for_evidence(mode, case, evidence))

    summary = {mode: _summary(mode, rows) for mode, rows in modes.items()}
    return {
        "scope": scope,
        "top_k": top_k,
        "model_requested": config.model,
        "model_returned": returned_model,
        "query_embedding_usage": usage,
        "cn_boost": cn_boost,
        "high_trust_boost": high_trust_boost,
        "duration_sec": round(time.time() - started, 3),
        "summary": summary,
        "modes": {mode: {"summary": summary[mode], "rows": rows} for mode, rows in modes.items()},
    }


def _write_csv(path: Path, result: Dict[str, Any]) -> None:
    rows = [row for mode in result["modes"].values() for row in mode["rows"]]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "mode",
                "query",
                "scenario_type",
                "expected_uses",
                "expected_topics",
                "precision_at_k",
                "topic_precision_at_k",
                "has_match",
                "has_topic_match",
                "has_expected_class",
                "high_trust_sensitive",
                "unsafe_source_leakage",
                "top1_source_id",
                "top1_title",
                "top1_topic",
                "top1_region",
                "top1_evidence_class",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "mode": row["mode"],
                    "query": row["query"],
                    "scenario_type": row["scenario_type"],
                    "expected_uses": "|".join(row["expected_uses"]),
                    "expected_topics": "|".join(row["expected_topics"]),
                    "precision_at_k": row["precision_at_k"],
                    "topic_precision_at_k": row["topic_precision_at_k"],
                    "has_match": row["has_match"],
                    "has_topic_match": row["has_topic_match"],
                    "has_expected_class": row["has_expected_class"],
                    "high_trust_sensitive": row["high_trust_sensitive"],
                    "unsafe_source_leakage": "|".join(row["unsafe_source_leakage"]),
                    "top1_source_id": row["top1_source_id"],
                    "top1_title": row["top1_title"],
                    "top1_topic": row["top1_topic"],
                    "top1_region": row["top1_region"],
                    "top1_evidence_class": row["top1_evidence_class"],
                }
            )


def _write_markdown(path: Path, result: Dict[str, Any]) -> None:
    lines = [
        "# OpenAI Embedding 检索评估",
        "",
        f"- scope: `{result['scope']}`",
        f"- top_k: {result['top_k']}",
        f"- model: `{result['model_returned']}`",
        f"- query embedding tokens: {result['query_embedding_usage'].get('total_tokens', 0)}",
        f"- cn_boost: {result.get('cn_boost')}",
        f"- high_trust_boost: {result.get('high_trust_boost')}",
        f"- duration_sec: {result['duration_sec']}",
        "",
        "| mode | match_rate | precision@5 | topic_hit | topic_precision@5 | class_hit | high_trust_sensitive | unsafe_leakage | top1_CN |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for mode, summary in result["summary"].items():
        lines.append(
            "| {mode} | {match_rate} | {precision} | {topic_hit} | {topic_precision} | {class_hit} | {high_trust} | {unsafe} | {cn} |".format(
                mode=mode,
                match_rate=summary.get("match_rate"),
                precision=summary.get("mean_precision_at_5"),
                topic_hit=summary.get("topic_hit_rate"),
                topic_precision=summary.get("mean_topic_precision_at_5"),
                class_hit=summary.get("expected_class_hit_rate"),
                high_trust=summary.get("high_trust_sensitive_rate"),
                unsafe=summary.get("unsafe_source_leakage_count"),
                cn=summary.get("top1_cn_rate"),
            )
        )
    lines.extend(
        [
            "",
            "## 解读口径",
            "",
            "- `openai_embedding_metadata_augmented` 表示用标题、主题、allowed_uses 等治理元数据增强后的 embedding 检索，但不加 allowed_uses 过滤；它不是纯内容向量。",
            "- `openai_embedding_inferred_uses` 表示用现有规则从 query 推断 allowed_uses 后再做 embedding 检索，更接近真实系统接入方式。",
            "- `openai_embedding_hybrid_cn_boost` 在 inferred allowed_uses 基础上，给中国来源和高可信来源轻量加权，用来观察中文用户场景下的本土权威来源优先效果。",
            "- `openai_embedding_expected_uses` 是带答案标签的上限实验，用来观察如果 allowed_uses 完全正确，embedding 排序本身能达到什么效果。",
            "- `top1_CN` 只表示第一条结果是否为中国来源；它不是唯一指标，但能帮助观察中文用户场景是否优先命中本土权威资料。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate OpenAI embedding retrieval against golden queries.")
    parser.add_argument("--scope", choices=["processed_chunks", "fulltext_chunks"], default="processed_chunks")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout-sec", type=float, default=60.0)
    parser.add_argument("--cn-boost", type=float, default=0.03)
    parser.add_argument("--high-trust-boost", type=float, default=0.02)
    args = parser.parse_args()

    result = evaluate_openai_embeddings(
        scope=args.scope,
        top_k=args.top_k,
        timeout_sec=args.timeout_sec,
        cn_boost=args.cn_boost,
        high_trust_boost=args.high_trust_boost,
    )
    out_dir = resolve_project_path("outputs/embedding_eval")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"openai_embedding_eval_{args.scope}.json"
    csv_path = out_dir / f"openai_embedding_eval_{args.scope}.csv"
    md_path = out_dir / f"openai_embedding_eval_{args.scope}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(csv_path, result)
    _write_markdown(md_path, result)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print(json.dumps({"json": str(json_path), "csv": str(csv_path), "markdown": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
