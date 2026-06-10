"""E1: pooled-qrels retrieval ablation for the application layer (Chapter 6).

Two stages so the human-review step sits in the middle:

  pool      — run every variant over the 100 golden queries, pool their top-5
              into a deduped query–chunk set, LLM-pre-grade each pair's relevance
              (independent of the retriever), and write an annotation sheet
              (judge grade + blank human_grade) for review.
  evaluate  — read the qrels (human_grade if filled, else judge grade), run the
              8 main variants + the keyword-weight sweep, compute graded
              nDCG@5 / Recall@5 / MRR per variant with paired bootstrap CIs and
              Holm-corrected pre-registered contrasts, and quantify how much the
              old self-evaluation (allowed_uses metadata) overstates precision.

Variants are driven entirely by env switches added to retriever.py, so no
production code path changes. The default behaviour and the quality gate are
untouched.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple

from app.services.config_loader import resolve_project_path
from app.services.retriever import retrieve_knowledge
from scripts.evaluate_retrieval import GOLDEN_QUERIES, _evidence_matches
from scripts.stat_utils import holm_bonferroni, paired_bootstrap_diff_ci

POOL_PATH = "knowledge_base/processed/e1_qrels_pool.jsonl"
RESULT_PATH = "knowledge_base/processed/e1_retrieval_ablation.json"


# ---------------------------------------------------------------------------
# Variant definitions (env-driven)
# ---------------------------------------------------------------------------

# Each variant is a dict of env overrides applied around retrieve_knowledge.
# kw = keyword_weight (vector_weight auto = 1 - kw unless set).
VARIANTS: Dict[str, Dict[str, str]] = {
    # single-channel baselines (fulltext OFF must be EXPLICIT — otherwise
    # settings.include_fulltext=auto turns it ON and the on/off contrast is moot)
    "keyword_only": {"RETRIEVAL_EMBEDDING_BACKEND": "off", "RETRIEVAL_INCLUDE_FULLTEXT": "off"},
    "vector_only_openai": {"RETRIEVAL_EMBEDDING_BACKEND": "openai", "RETRIEVAL_KEYWORD_WEIGHT": "0.0", "RETRIEVAL_INCLUDE_FULLTEXT": "off"},
    # hybrid, no fulltext
    "hybrid_hashing": {"RETRIEVAL_EMBEDDING_BACKEND": "hashing", "RETRIEVAL_KEYWORD_WEIGHT": "0.6", "RETRIEVAL_INCLUDE_FULLTEXT": "off"},
    "hybrid_openai": {"RETRIEVAL_EMBEDDING_BACKEND": "openai", "RETRIEVAL_KEYWORD_WEIGHT": "0.6", "RETRIEVAL_INCLUDE_FULLTEXT": "off"},
    # hybrid + fulltext
    "hybrid_hashing_ft": {
        "RETRIEVAL_EMBEDDING_BACKEND": "hashing",
        "RETRIEVAL_KEYWORD_WEIGHT": "0.6",
        "RETRIEVAL_INCLUDE_FULLTEXT": "on",
    },
    "hybrid_openai_ft": {
        "RETRIEVAL_EMBEDDING_BACKEND": "openai",
        "RETRIEVAL_KEYWORD_WEIGHT": "0.6",
        "RETRIEVAL_INCLUDE_FULLTEXT": "on",
    },
    # dedup ablation (per_source_cap=0)
    "hybrid_openai_nodedup": {
        "RETRIEVAL_EMBEDDING_BACKEND": "openai",
        "RETRIEVAL_KEYWORD_WEIGHT": "0.6",
        "RETRIEVAL_INCLUDE_FULLTEXT": "off",
        "RETRIEVAL_PER_SOURCE_CAP": "0",
    },
    "hybrid_openai_ft_nodedup": {
        "RETRIEVAL_EMBEDDING_BACKEND": "openai",
        "RETRIEVAL_KEYWORD_WEIGHT": "0.6",
        "RETRIEVAL_INCLUDE_FULLTEXT": "on",
        "RETRIEVAL_PER_SOURCE_CAP": "0",
    },
}

# Pre-registered paired contrasts (Holm-corrected family).
CONTRASTS = [
    ("hybrid_vs_keyword", "keyword_only", "hybrid_openai"),
    ("hybrid_vs_vector", "vector_only_openai", "hybrid_openai"),
    ("openai_vs_hashing", "hybrid_hashing", "hybrid_openai"),
    ("fulltext_on_vs_off", "hybrid_openai", "hybrid_openai_ft"),
    ("dedup_on_vs_off", "hybrid_openai_nodedup", "hybrid_openai"),
]

WEIGHT_SWEEP = [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]


@contextmanager
def _variant_env(overrides: Dict[str, str]):
    keys = set(overrides) | {
        "RETRIEVAL_EMBEDDING_BACKEND",
        "RETRIEVAL_KEYWORD_WEIGHT",
        "RETRIEVAL_VECTOR_WEIGHT",
        "RETRIEVAL_INCLUDE_FULLTEXT",
        "RETRIEVAL_PER_SOURCE_CAP",
    }
    saved = {k: os.environ.get(k) for k in keys}
    try:
        # Clear all variant knobs first so a previous variant never leaks in.
        for k in keys:
            os.environ.pop(k, None)
        # NOTE: the query cache is intentionally LEFT ENABLED. A query's OpenAI
        # embedding is identical regardless of variant, so sharing the cached
        # vector across variants is correct for quality metrics (nDCG/recall) and
        # avoids re-hitting the API mid-run (which under load timed out → tripped
        # the 5-min backoff → silently degraded the OpenAI backend to keyword).
        # The cache is pre-warmed once before the variant loop.
        for k, v in overrides.items():
            os.environ[k] = v
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


def _prewarm_openai_cache(concurrency: int = 6) -> Dict:
    """Embed all golden queries into the retriever's OpenAI query cache once.

    Run BEFORE the variant loop so every openai-backend retrieval is a cache hit
    (zero mid-run API calls → no timeout → no backoff → the OpenAI backend
    reliably contributes real vectors instead of silently falling back to
    keyword). Returns coverage diagnostics so a failed prewarm is visible.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.services import retriever as R

    R._OPENAI_QUERY_CACHE.clear()
    R._OPENAI_BACKOFF_UNTIL = 0.0
    index = R._load_vector_index(*R._file_signature(R.VECTOR_STORE_PATHS["processed"][0]))
    if index is None:
        return {"prewarmed": 0, "dims": None, "note": "no OpenAI processed index; openai variants unavailable"}
    dims = int(index[1].shape[1])
    queries = [c["query"] for c in GOLDEN_QUERIES]
    os.environ.pop("RETRIEVAL_DISABLE_QUERY_CACHE", None)  # ensure cache writes

    def _warm(q):
        return R._openai_query_vector(q, dims) is not None

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        hits = list(executor.map(_warm, queries))
    return {"prewarmed": sum(hits), "queries": len(queries), "dims": dims, "cache_size": len(R._OPENAI_QUERY_CACHE)}


_SUMMARY_CHUNK_SUFFIX = re.compile(r"_\d{3}$")


def _parent_source(source_id: str) -> str:
    """Collapse a chunk id to its parent source for source-diversity counting.

    fulltext::SRC::p001::c01 -> SRC ; summary  SRC_001 -> SRC ; else unchanged.
    Without this, summary chunks of one source (…_001, …_002) were counted as
    distinct sources, inflating the diversity metric the dedup contrast uses.
    """
    if "::" in source_id:
        parts = source_id.split("::")
        return parts[1] if len(parts) > 1 else source_id
    return _SUMMARY_CHUNK_SUFFIX.sub("", source_id)


def _retrieve_for_variant(query: str, overrides: Dict[str, str], top_k: int = 5):
    include_ft = overrides.get("RETRIEVAL_INCLUDE_FULLTEXT")
    kwargs = {"top_k": top_k, "min_quality_score": 18}
    if include_ft is not None:
        kwargs["include_fulltext"] = include_ft.lower() in {"on", "true", "1"}
    with _variant_env(overrides):
        return retrieve_knowledge([query], **kwargs).evidence


# ---------------------------------------------------------------------------
# Stage: pool
# ---------------------------------------------------------------------------


def _write_pool(rows: List[Dict]) -> str:
    out_path = resolve_project_path(POOL_PATH)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return str(out_path)


def _load_existing_grades() -> Dict[str, Dict]:
    """Load already-judged pairs (key qid::chunk_id) so a resumed run skips them.

    This is the key protection for a small endpoint: a killed run never loses
    judged pairs and a restart re-issues ZERO requests for what's already done.
    """
    path = resolve_project_path(POOL_PATH)
    if not path.exists():
        return {}
    grades: Dict[str, Dict] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("judge_grade") is not None:
                grades[f"{row['qid']}::{row['chunk_id']}"] = {
                    "judge_grade": row["judge_grade"],
                    "judge_reason": row.get("judge_reason", ""),
                    "judge_model": row.get("judge_model", ""),
                    "human_grade": row.get("human_grade"),
                }
    return grades


def build_pool(
    top_k: int = 5,
    limit_queries: Optional[int] = None,
    judge: bool = True,
    concurrency: int = 2,
    resume: bool = True,
    checkpoint_every: int = 20,
) -> Dict:
    """Pool variant top-5 then (optionally) judge-grade each pair.

    Gentle by design: low default concurrency, a global rate limit in the judge
    (EVAL_LLM_MIN_INTERVAL_SEC), incremental checkpoints to disk, and resume of
    already-judged pairs so a small endpoint is never bursted or re-hit.
    """
    queries = GOLDEN_QUERIES[:limit_queries] if limit_queries else GOLDEN_QUERIES
    existing = _load_existing_grades() if (judge and resume) else {}

    pool: Dict[str, Dict] = {}  # key = f"{qid}::{chunk_id}"
    per_query_chunks: Dict[int, set] = {}
    for qid, case in enumerate(queries):
        per_query_chunks[qid] = set()
        for variant_name, overrides in VARIANTS.items():
            evidence = _retrieve_for_variant(case["query"], overrides, top_k=top_k)
            for ev in evidence:
                chunk_id = ev.source_id
                key = f"{qid}::{chunk_id}"
                per_query_chunks[qid].add(chunk_id)
                if key not in pool:
                    pool[key] = {
                        "qid": qid,
                        "query": case["query"],
                        "expected_uses": case["expected_uses"],
                        "sensitive": bool(case.get("sensitive")),
                        "chunk_id": chunk_id,
                        "title": ev.title,
                        "snippet": ev.snippet,
                        "allowed_uses": ev.allowed_uses,
                        "topic": ev.topic,
                        "evidence_class": ev.evidence_class,
                        "selfeval_relevant": int(_evidence_matches(ev, case["expected_uses"])),
                        "found_by": [],
                    }
                    # carry over any prior judge result for this pair (resume)
                    prior = existing.get(key)
                    if prior:
                        pool[key].update(prior)
                pool[key]["found_by"].append(variant_name)

    rows = list(pool.values())
    for row in rows:
        row.setdefault("human_grade", None)
    # Checkpoint the retrieval pool immediately so the structure survives even
    # before any judging completes.
    _write_pool(rows)

    judged = sum(1 for row in rows if row.get("judge_grade") is not None)
    if judge:
        from concurrent.futures import ThreadPoolExecutor

        from scripts.relevance_judge import grade_pair, RelevanceJudgeError

        pending = [row for row in rows if row.get("judge_grade") is None]

        def _judge_row(row: Dict) -> Dict:
            try:
                verdict = grade_pair(row["query"], row.get("snippet") or row.get("title", ""))
                row["judge_grade"] = verdict["grade"]
                row["judge_reason"] = verdict["reason"]
                row["judge_model"] = verdict["judge_model"]
            except RelevanceJudgeError as exc:
                row["judge_grade"] = None
                row["judge_error"] = str(exc)[:160]
            return row

        workers = max(1, min(concurrency, len(pending) or 1))
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for _ in executor.map(_judge_row, pending):
                done += 1
                if done % checkpoint_every == 0:
                    _write_pool(rows)  # incremental checkpoint
        _write_pool(rows)
        judged = sum(1 for row in rows if row.get("judge_grade") is not None)

    pool_depth = {qid: len(chunks) for qid, chunks in per_query_chunks.items()}
    return {
        "queries": len(queries),
        "variants": list(VARIANTS),
        "pairs": len(rows),
        "judged": judged,
        "resumed_from_existing": len(existing),
        "concurrency": (workers if judge else 0),
        "mean_pool_depth": round(sum(pool_depth.values()) / len(pool_depth), 2) if pool_depth else 0,
        "max_pool_depth": max(pool_depth.values()) if pool_depth else 0,
        "pool_path": str(resolve_project_path(POOL_PATH)),
    }


# ---------------------------------------------------------------------------
# Stage: evaluate
# ---------------------------------------------------------------------------


def _load_qrels(prefer_human: bool = True) -> Dict[Tuple[int, str], int]:
    """qrels[(qid, chunk_id)] = graded relevance (human_grade if present else judge)."""
    path = resolve_project_path(POOL_PATH)
    if not path.exists():
        raise FileNotFoundError(f"pool not built yet: {path} (run `pool` first)")
    qrels: Dict[Tuple[int, str], int] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            grade = None
            if prefer_human and row.get("human_grade") is not None:
                grade = row["human_grade"]
            elif row.get("judge_grade") is not None:
                grade = row["judge_grade"]
            if grade is not None:
                qrels[(row["qid"], row["chunk_id"])] = int(grade)
    return qrels


def _dcg(gains: List[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def _ndcg_at_k(ranked_ids: List[str], qid: int, qrels: Dict, k: int = 5) -> float:
    gains = [qrels.get((qid, cid), 0) for cid in ranked_ids[:k]]
    dcg = _dcg(gains)
    ideal = sorted((g for (qq, _), g in qrels.items() if qq == qid), reverse=True)[:k]
    idcg = _dcg(ideal)
    return dcg / idcg if idcg > 0 else 0.0


def _recall_at_k(ranked_ids: List[str], qid: int, qrels: Dict, k: int = 5) -> float:
    relevant = {cid for (qq, cid), g in qrels.items() if qq == qid and g >= 1}
    if not relevant:
        return 0.0
    retrieved_rel = sum(1 for cid in ranked_ids[:k] if cid in relevant)
    return retrieved_rel / len(relevant)


def _mrr(ranked_ids: List[str], qid: int, qrels: Dict) -> float:
    for i, cid in enumerate(ranked_ids):
        if qrels.get((qid, cid), 0) >= 1:
            return 1.0 / (i + 1)
    return 0.0


def _eval_variant(overrides: Dict[str, str], qrels: Dict, top_k: int = 5, concurrency: int = 1) -> Dict:
    """Score one variant over all golden queries.

    The variant env (incl. cache-disable for fairness) is set ONCE around the
    whole loop; query workers only READ it, so parallelism is safe. Concurrency
    accelerates the OpenAI-embedding-bound retrieval (OpenAI handles high
    concurrency fine); the GPT-5.5 judge is not touched in this phase.
    """
    from concurrent.futures import ThreadPoolExecutor

    include_ft = overrides.get("RETRIEVAL_INCLUDE_FULLTEXT")
    kwargs = {"top_k": top_k, "min_quality_score": 18}
    if include_ft is not None:
        kwargs["include_fulltext"] = include_ft.lower() in {"on", "true", "1"}

    def _score_query(item):
        qid, case = item
        evidence = retrieve_knowledge([case["query"]], **kwargs).evidence
        ranked_ids = [ev.source_id for ev in evidence]
        if evidence:
            selfeval = sum(1 for ev in evidence if _evidence_matches(ev, case["expected_uses"])) / len(evidence)
            indep = sum(1 for cid in ranked_ids[:top_k] if qrels.get((qid, cid), 0) >= 1) / len(ranked_ids[:top_k])
        else:
            selfeval = indep = 0.0
        uniq = len({_parent_source(ev.source_id) for ev in evidence})
        return {
            "qid": qid,
            "ndcg": _ndcg_at_k(ranked_ids, qid, qrels, top_k),
            "recall": _recall_at_k(ranked_ids, qid, qrels, top_k),
            "mrr": _mrr(ranked_ids, qid, qrels),
            "selfeval": selfeval,
            "indep": indep,
            "uniq": uniq,
        }

    items = list(enumerate(GOLDEN_QUERIES))
    with _variant_env(overrides):  # env set once; workers only read it
        if concurrency <= 1:
            results = [_score_query(it) for it in items]
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                results = list(executor.map(_score_query, items))

    results.sort(key=lambda r: r["qid"])  # stable order for per-query arrays
    per_query = {
        "ndcg": [r["ndcg"] for r in results],
        "recall": [r["recall"] for r in results],
        "mrr": [r["mrr"] for r in results],
        "selfeval_precision": [r["selfeval"] for r in results],
        "indep_precision": [r["indep"] for r in results],
    }
    diversity = [r["uniq"] for r in results]
    n = len(GOLDEN_QUERIES)
    return {
        "ndcg_at_5": round(sum(per_query["ndcg"]) / n, 4),
        "recall_at_5": round(sum(per_query["recall"]) / n, 4),
        "mrr": round(sum(per_query["mrr"]) / n, 4),
        "selfeval_precision_at_5": round(sum(per_query["selfeval_precision"]) / n, 4),
        "independent_precision_at_5": round(sum(per_query["indep_precision"]) / n, 4),
        "mean_unique_sources_at_5": round(sum(diversity) / n, 3),
        "_per_query": per_query,
    }


def evaluate_ablation(top_k: int = 5, concurrency: int = 1) -> Dict:
    qrels = _load_qrels(prefer_human=True)
    human_used = any(True for _ in qrels)  # qrels non-empty
    # Pre-warm the OpenAI query cache once so every openai-backend retrieval is a
    # cache hit (no mid-run API call → no timeout → no backoff → no silent
    # degradation to keyword). Critical: without this the openai variants
    # collapsed onto keyword_only.
    prewarm = _prewarm_openai_cache(concurrency=max(4, concurrency))
    variant_results = {}
    for name, overrides in VARIANTS.items():
        variant_results[name] = _eval_variant(overrides, qrels, top_k=top_k, concurrency=concurrency)

    # Sanity guard: if any openai variant's nDCG exactly equals keyword_only's,
    # the OpenAI vectors silently did not contribute — flag it loudly rather
    # than ship a meaningless openai-vs-keyword comparison.
    kw_ndcg = variant_results["keyword_only"]["ndcg_at_5"]
    collapsed = [
        name for name in ("vector_only_openai", "hybrid_openai", "hybrid_openai_ft")
        if abs(variant_results[name]["ndcg_at_5"] - kw_ndcg) < 1e-9
    ]

    # Pre-registered contrasts on nDCG@5 with paired bootstrap + Holm.
    contrast_rows = []
    pvalues = []
    for label, base, var in CONTRASTS:
        base_pq = variant_results[base]["_per_query"]["ndcg"]
        var_pq = variant_results[var]["_per_query"]["ndcg"]
        pairs = list(zip(base_pq, var_pq))
        lo, hi = paired_bootstrap_diff_ci(pairs, iters=10000, seed=13)
        diff = sum(v - b for b, v in pairs) / len(pairs)
        # bootstrap p: fraction of resampled diffs crossing 0 (two-sided approx)
        p = _bootstrap_p(pairs)
        pvalues.append(p)
        contrast_rows.append(
            {"contrast": label, "baseline": base, "variant": var,
             "ndcg_diff": round(diff, 4), "ci95": [round(lo, 4), round(hi, 4)], "p_raw": round(p, 5)}
        )
    holm = holm_bonferroni(pvalues, alpha=0.05)
    for row, adj in zip(contrast_rows, holm):
        row["p_holm"] = adj["p_adjusted"]
        row["significant"] = adj["reject"]

    # Weight sweep on openai and hashing hybrids.
    sweep = {}
    for backend in ("openai", "hashing"):
        sweep[backend] = []
        for kw in WEIGHT_SWEEP:
            ov = {"RETRIEVAL_EMBEDDING_BACKEND": backend, "RETRIEVAL_KEYWORD_WEIGHT": str(kw)}
            res = _eval_variant(ov, qrels, top_k=top_k, concurrency=concurrency)
            sweep[backend].append({"keyword_weight": kw, "ndcg_at_5": res["ndcg_at_5"], "recall_at_5": res["recall_at_5"]})

    # Self-eval inflation: how much the old metadata precision overstates the
    # independent qrels precision, on the production-default variant.
    prod = variant_results["hybrid_openai_ft"]
    inflation = round(prod["selfeval_precision_at_5"] - prod["independent_precision_at_5"], 4)

    clean = {k: {kk: vv for kk, vv in v.items() if kk != "_per_query"} for k, v in variant_results.items()}
    result = {
        "top_k": top_k,
        "qrels_pairs": len(qrels),
        "judge_note": "qrels use human_grade where present, else LLM judge grade (PRELIMINARY pending human review of e1_review_sheet)",
        "openai_prewarm": prewarm,
        "openai_backend_sanity": {
            "collapsed_to_keyword": collapsed,
            "ok": not collapsed,
            "note": "If non-empty, OpenAI vectors silently did not contribute (backoff/timeout); results invalid for openai contrasts.",
        },
        "variants": clean,
        "contrasts": contrast_rows,
        "weight_sweep": sweep,
        "self_eval_inflation": {
            "variant": "hybrid_openai_ft",
            "selfeval_precision_at_5": prod["selfeval_precision_at_5"],
            "independent_precision_at_5": prod["independent_precision_at_5"],
            "overstatement": inflation,
            "note": "Positive overstatement = the old allowed_uses self-evaluation reports higher precision than independent graded relevance.",
        },
    }
    out_path = resolve_project_path(RESULT_PATH)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["result_path"] = str(out_path)
    return result


def _bootstrap_p(pairs, iters: int = 10000, seed: int = 17) -> float:
    """Two-sided bootstrap p-value for mean paired diff != 0."""
    import random

    n = len(pairs)
    if n == 0:
        return 1.0
    observed = sum(v - b for b, v in pairs) / n
    if observed == 0:
        return 1.0
    rng = random.Random(seed)
    centered = [(v - b) - observed for b, v in pairs]
    extreme = 0
    for _ in range(iters):
        m = sum(centered[rng.randrange(n)] for _ in range(n)) / n
        if abs(m) >= abs(observed):
            extreme += 1
    return max(1.0 / iters, extreme / iters)


def main() -> None:
    parser = argparse.ArgumentParser(description="E1 pooled-qrels retrieval ablation.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_pool = sub.add_parser("pool", help="Build pooled query-chunk set + LLM pre-grade (gentle/resumable).")
    p_pool.add_argument("--top-k", type=int, default=5)
    p_pool.add_argument("--limit-queries", type=int, default=None, help="Subset of golden queries (smoke test / incremental).")
    p_pool.add_argument("--no-judge", action="store_true", help="Skip LLM grading (structure-only dry run).")
    p_pool.add_argument("--concurrency", type=int, default=2, help="Judge worker threads (keep low for small endpoints; default 2).")
    p_pool.add_argument("--no-resume", action="store_true", help="Re-judge every pair instead of skipping already-judged ones.")
    p_pool.add_argument("--checkpoint-every", type=int, default=20, help="Flush pool to disk every N judged pairs.")
    p_eval = sub.add_parser("evaluate", help="Score 8 variants + weight sweep against qrels.")
    p_eval.add_argument("--top-k", type=int, default=5)
    p_eval.add_argument("--concurrency", type=int, default=1,
                        help="Parallel query workers (OpenAI embeddings tolerate high concurrency; "
                        "the GPT-5.5 judge is NOT used in this phase).")
    args = parser.parse_args()

    if args.cmd == "pool":
        summary = build_pool(
            top_k=args.top_k,
            limit_queries=args.limit_queries,
            judge=not args.no_judge,
            concurrency=args.concurrency,
            resume=not args.no_resume,
            checkpoint_every=args.checkpoint_every,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        result = evaluate_ablation(top_k=args.top_k, concurrency=args.concurrency)
        print(json.dumps({k: v for k, v in result.items() if k != "variants"}, ensure_ascii=False, indent=2))
        print("--- variant nDCG@5 / Recall@5 / unique-sources ---")
        for name, m in result["variants"].items():
            print(f"  {name:28s} nDCG@5={m['ndcg_at_5']:.4f} R@5={m['recall_at_5']:.4f} uniq={m['mean_unique_sources_at_5']:.2f}")


if __name__ == "__main__":
    main()
