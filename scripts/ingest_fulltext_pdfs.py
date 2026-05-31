from __future__ import annotations

import argparse
import json

from app.services.fulltext_vector_index import (
    build_fulltext_vector_index,
    query_hashing_vector_index,
    summarize_query_results,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract local governed PDF full text, split into fine chunks, and build an ignored local vector index. "
            "Raw PDF text is not committed."
        )
    )
    parser.add_argument("--source-id", action="append", help="Limit to one source_id. Repeat for multiple sources.")
    parser.add_argument("--target-chars", type=int, default=850, help="Approximate chunk size in characters.")
    parser.add_argument("--overlap-chars", type=int, default=140, help="Character overlap between adjacent chunks.")
    parser.add_argument("--dims", type=int, default=384, help="Hashing-vector dimensionality.")
    parser.add_argument("--query", help="Optional smoke-test query after building the vector index.")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    manifest = build_fulltext_vector_index(
        source_ids=args.source_id,
        target_chars=args.target_chars,
        overlap_chars=args.overlap_chars,
        dims=args.dims,
    )
    output = {"manifest": {key: value for key, value in manifest.items() if key != "sources"}}
    if args.query:
        output["query_results"] = summarize_query_results(query_hashing_vector_index(args.query, top_k=args.top_k))
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
