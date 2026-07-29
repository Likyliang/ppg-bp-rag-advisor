from __future__ import annotations

import argparse
import json
import os

from app.services.openai_embedding_index import build_openai_embedding_index, query_openai_embedding_index
from app.services.retriever import infer_allowed_uses


def _emit_progress(completed: int, total: int) -> None:
    if os.getenv("ADMIN_JOB_PROGRESS") != "1":
        return
    ratio = 1.0 if total <= 0 else min(1.0, max(0.0, completed / total))
    print(f"__ADMIN_JOB_PROGRESS__={10 + int(ratio * 80)}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an external OpenAI embedding index for governed KB chunks."
    )
    parser.add_argument(
        "--scope",
        choices=["processed_chunks", "fulltext_chunks"],
        default="processed_chunks",
        help="processed_chunks sends curated KB notes; fulltext_chunks sends local PDF-extracted full text.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional max chunks for a pilot run.")
    parser.add_argument("--offset", type=int, default=0, help="Optional chunk offset for pilot runs.")
    parser.add_argument("--source-id", action="append", help="Optional source_id filter. Repeat for multiple sources.")
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=None,
        help="Override the active Embedding integration timeout for this run.",
    )
    parser.add_argument("--query", help="Optional smoke-test query after building the index.")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    manifest = build_openai_embedding_index(
        scope=args.scope,
        limit=args.limit,
        offset=args.offset,
        timeout_sec=args.timeout_sec,
        source_ids=args.source_id,
        progress_callback=_emit_progress,
    )
    if os.getenv("ADMIN_JOB_PROGRESS") == "1":
        print("__ADMIN_JOB_PROGRESS__=95", flush=True)
    output = {"manifest": manifest}
    if args.query:
        output["query_results"] = query_openai_embedding_index(
            args.query,
            scope=args.scope,
            top_k=args.top_k,
            timeout_sec=args.timeout_sec,
            allowed_uses=infer_allowed_uses([args.query]),
            min_quality_score=18,
            cn_boost=0.03,
            high_trust_boost=0.02,
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
