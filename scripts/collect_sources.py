from __future__ import annotations

import argparse
import json
import urllib.request
from typing import Dict, List

from app.services.config_loader import resolve_project_path
from app.services.source_catalog import screen_sources


def _check_url(url: str, timeout: int = 10) -> Dict:
    if not url or url.startswith("https://example.com"):
        return {"url": url, "status": "skipped"}
    request = urllib.request.Request(url, headers={"User-Agent": "ppg-bp-rag-agent/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"url": url, "status": response.status, "content_type": response.headers.get("content-type", "")}
    except Exception as exc:
        return {"url": url, "status": "error", "error": f"{exc.__class__.__name__}: {exc}"}


def collect_sources(check_urls: bool = False) -> Dict:
    screened = screen_sources()
    candidates: List[Dict] = []
    for source in screened["included_sources"] + screened["excluded_sources"]:
        candidate = {
            "source_id": source["source_id"],
            "title": source["title"],
            "url": source.get("url"),
            "include": source.get("include"),
            "source_quality_score": source.get("source_quality_score"),
            "topic": source.get("topic"),
            "evidence_class": source.get("evidence_class"),
        }
        if check_urls:
            candidate["url_check"] = _check_url(source.get("url"))
        candidates.append(candidate)

    out_path = resolve_project_path("knowledge_base/processed/candidate_sources.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"candidate_count": len(candidates), "output_path": str(out_path), "checked_urls": check_urls}


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect source-catalog candidates and optional URL status.")
    parser.add_argument("--check-urls", action="store_true")
    args = parser.parse_args()
    print(json.dumps(collect_sources(check_urls=args.check_urls), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
