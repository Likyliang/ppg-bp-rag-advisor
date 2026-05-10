from __future__ import annotations

import json
import sys

from app.services.source_catalog import write_screening_outputs, screen_sources


def main() -> None:
    result = screen_sources()
    files = write_screening_outputs()
    errors = [issue for issue in result["issues"] if issue["severity"] == "error"]
    print(json.dumps({k: v for k, v in result.items() if k not in {"included_sources", "excluded_sources"}}, ensure_ascii=False, indent=2))
    print(json.dumps({"files": files}, ensure_ascii=False, indent=2))
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
