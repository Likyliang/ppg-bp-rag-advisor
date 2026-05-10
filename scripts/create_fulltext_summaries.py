from __future__ import annotations

import argparse
import json

from app.services.fulltext_candidates import create_summary_notes


def main() -> None:
    parser = argparse.ArgumentParser(description="Create tracked Chinese summary notes from approved full-text candidates.")
    parser.add_argument("--source-id", help="Limit to a source_id or candidate_id.")
    args = parser.parse_args()
    result = create_summary_notes(source_id=args.source_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
