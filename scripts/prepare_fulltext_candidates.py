from __future__ import annotations

import json
import sys

from app.services.fulltext_candidates import validate_fulltext_catalog, write_fulltext_candidate_outputs


def main() -> None:
    report = validate_fulltext_catalog()
    files = write_fulltext_candidate_outputs()
    payload = {key: value for key, value in report.items() if key != "candidates"}
    payload["files"] = files
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if [issue for issue in report["issues"] if issue["severity"] == "error"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
