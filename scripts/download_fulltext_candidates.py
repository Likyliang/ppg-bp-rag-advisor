from __future__ import annotations

import argparse
import json

from app.services.fulltext_candidates import download_public_candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Download only public PDF full-text candidates; never uses institution credentials.")
    parser.add_argument("--force", action="store_true", help="Re-download files that already exist in downloads/.")
    parser.add_argument(
        "--all-public-pdf",
        action="store_true",
        help="Download every governed access_mode=public_pdf candidate with a PDF URL, not only auto_download=true rows.",
    )
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    result = download_public_candidates(force=args.force, timeout=args.timeout, include_all_public_pdf=args.all_public_pdf)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
