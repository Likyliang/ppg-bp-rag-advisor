from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request
from datetime import date, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from app.services.config_loader import resolve_project_path
from app.services.source_catalog import ALLOWED_USES, included_sources


CATALOG_PATH = "knowledge_base/sources/fulltext_candidates.yaml"
DOWNLOADS_ROOT = "knowledge_base/sources/downloads"
SUMMARY_ROOT = "knowledge_base/sources/fulltext_summaries"
PROCESSED_ROOT = "knowledge_base/processed"

ALLOWED_ACCESS_MODES = {
    "public_html",
    "public_pdf",
    "public_landing",
    "institution_or_browser",
    "browser_required",
    "metadata_only_paid_standard",
}

ALLOWED_STATUSES = {
    "downloadable",
    "queued_browser",
    "queued_institution",
    "queued_manual",
    "metadata_only",
    "summarized",
}

ALLOWED_SUMMARY_STATUSES = {
    "ready",
    "pending_fulltext",
    "metadata_only",
}

PROTECTED_KEY_PATTERN = re.compile(r"(password|credential|secret|token|cookie|username|account)", re.I)


@dataclass
class FulltextIssue:
    candidate_id: str
    severity: str
    message: str


def load_fulltext_catalog(path: str = CATALOG_PATH) -> Dict[str, Any]:
    catalog_path = resolve_project_path(path)
    if not catalog_path.exists():
        return {"candidates": []}
    with catalog_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {"candidates": []}


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _jsonable(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _walk_keys(value: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            joined = f"{prefix}.{key}" if prefix else str(key)
            yield joined
            yield from _walk_keys(item, joined)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_keys(item, f"{prefix}[{index}]")


def _source_lookup() -> Dict[str, Dict[str, Any]]:
    return {source["source_id"]: source for source in included_sources()}


def _jsonable_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    result = _jsonable(dict(candidate))
    result["allowed_uses"] = _as_list(result.get("allowed_uses"))
    result["priority"] = int(result.get("priority", 99))
    result["institution_required"] = bool(result.get("institution_required", False))
    result["auto_download"] = bool(result.get("auto_download", False))
    result["include_in_summary"] = bool(result.get("include_in_summary", False))
    return result


def validate_fulltext_catalog(catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    catalog = catalog or load_fulltext_catalog()
    candidates = [_jsonable_candidate(item) for item in catalog.get("candidates", [])]
    source_by_id = _source_lookup()
    issues: List[FulltextIssue] = []
    seen_ids = set()

    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "<missing>")
        for field in ["candidate_id", "source_id", "title", "priority", "access_mode", "status", "summary_status"]:
            if candidate.get(field) in (None, "", []):
                issues.append(FulltextIssue(candidate_id, "error", f"missing required field: {field}"))

        for key_path in _walk_keys(candidate):
            if PROTECTED_KEY_PATTERN.search(key_path):
                issues.append(FulltextIssue(candidate_id, "error", f"protected credential-like field is not allowed: {key_path}"))

        if candidate_id in seen_ids:
            issues.append(FulltextIssue(candidate_id, "error", "duplicate candidate_id"))
        seen_ids.add(candidate_id)

        source_id = str(candidate.get("source_id") or "")
        if source_id and source_id not in source_by_id:
            issues.append(FulltextIssue(candidate_id, "error", f"source_id is not an included source: {source_id}"))

        access_mode = candidate.get("access_mode")
        if access_mode and access_mode not in ALLOWED_ACCESS_MODES:
            issues.append(FulltextIssue(candidate_id, "error", f"invalid access_mode: {access_mode}"))

        status = candidate.get("status")
        if status and status not in ALLOWED_STATUSES:
            issues.append(FulltextIssue(candidate_id, "error", f"invalid status: {status}"))

        summary_status = candidate.get("summary_status")
        if summary_status and summary_status not in ALLOWED_SUMMARY_STATUSES:
            issues.append(FulltextIssue(candidate_id, "error", f"invalid summary_status: {summary_status}"))

        invalid_uses = sorted(set(candidate.get("allowed_uses", [])) - ALLOWED_USES)
        if invalid_uses:
            issues.append(FulltextIssue(candidate_id, "error", f"invalid allowed_uses: {', '.join(invalid_uses)}"))

        if candidate.get("auto_download"):
            if candidate.get("institution_required"):
                issues.append(FulltextIssue(candidate_id, "error", "institution_required candidates cannot auto_download"))
            if candidate.get("access_mode") != "public_pdf":
                issues.append(FulltextIssue(candidate_id, "error", "auto_download requires access_mode=public_pdf"))
            if not candidate.get("pdf_url"):
                issues.append(FulltextIssue(candidate_id, "error", "auto_download requires pdf_url"))

        if candidate.get("include_in_summary") and not candidate.get("summary_notes"):
            issues.append(FulltextIssue(candidate_id, "error", "include_in_summary requires summary_notes"))

    public_downloads = [item for item in candidates if item.get("auto_download")]
    institution_queue = [item for item in candidates if item.get("institution_required") or item.get("status") == "queued_institution"]
    browser_queue = [
        item
        for item in candidates
        if item.get("access_mode") in {"browser_required", "institution_or_browser"} or item.get("status") in {"queued_browser", "queued_manual"}
    ]
    action_queue_count = len({item.get("candidate_id") for item in institution_queue + browser_queue})
    summary_ready = [item for item in candidates if item.get("include_in_summary")]

    return {
        "catalog_version": catalog.get("catalog_version"),
        "updated": str(catalog.get("updated") or ""),
        "candidate_count": len(candidates),
        "public_download_count": len(public_downloads),
        "institution_queue_count": len(institution_queue),
        "browser_queue_count": len(browser_queue),
        "action_queue_count": action_queue_count,
        "summary_ready_count": len(summary_ready),
        "issues": [issue.__dict__ for issue in issues],
        "candidates": sorted(candidates, key=lambda item: (item.get("priority", 99), item.get("candidate_id", ""))),
    }


def candidate_download_path(candidate: Dict[str, Any]) -> Path:
    source_id = str(candidate["source_id"])
    return resolve_project_path(f"{DOWNLOADS_ROOT}/{source_id}.pdf")


def candidate_summary_path(candidate: Dict[str, Any]) -> Path:
    source_id = str(candidate["source_id"])
    return resolve_project_path(f"{SUMMARY_ROOT}/{source_id}.summary.md")


def _candidate_hash(candidate: Dict[str, Any]) -> str:
    identity = {
        "candidate_id": candidate.get("candidate_id"),
        "source_id": candidate.get("source_id"),
        "landing_url": candidate.get("landing_url"),
        "pdf_url": candidate.get("pdf_url"),
        "doi": candidate.get("doi"),
        "pmid": candidate.get("pmid"),
    }
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_fulltext_candidate_outputs(output_dir: str = PROCESSED_ROOT) -> Dict[str, str]:
    report = validate_fulltext_catalog()
    out_dir = resolve_project_path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "fulltext_candidate_report.json"
    queue_path = out_dir / "fulltext_download_queue.md"
    _write_json(report_path, {key: value for key, value in report.items() if key != "candidates"} | {"candidates": report["candidates"]})
    queue_path.write_text(render_download_queue(report), encoding="utf-8")
    return {"candidate_report": str(report_path), "download_queue": str(queue_path)}


def render_download_queue(report: Optional[Dict[str, Any]] = None) -> str:
    report = report or validate_fulltext_catalog()
    candidates = report.get("candidates", [])
    queued_ids = {
        item.get("candidate_id")
        for item in candidates
        if item.get("institution_required") or item.get("access_mode") in {"browser_required", "institution_or_browser"} or item.get("status") in {"queued_browser", "queued_institution", "queued_manual"}
    }
    lines = [
        "# Full-text Candidate Download Queue",
        "",
        f"- Updated: {report.get('updated')}",
        f"- Candidates: {report.get('candidate_count')}",
        f"- Public auto-download: {report.get('public_download_count')}",
        f"- Institution/browser queue: {report.get('action_queue_count', len(queued_ids))}",
        "",
        "## Safe Access Rules",
        "",
        "- 不记录、不保存、不复用机构账号、密码、cookie 或 token。",
        "- 需要机构身份时，只使用用户当前浏览器会话完成下载。",
        "- 下载的 PDF 放入 `knowledge_base/sources/downloads/`；该目录被 Git 忽略。",
        "- 只有中文摘要和 citation 进入可提交知识库，不复制受版权保护全文。",
        "",
    ]

    for title, predicate in [
        ("Public Auto-download", lambda item: item.get("auto_download")),
        ("Needs Browser Or Institution", lambda item: item.get("institution_required") or item.get("status") in {"queued_browser", "queued_institution", "queued_manual"}),
        ("Metadata Only", lambda item: item.get("status") == "metadata_only"),
    ]:
        bucket = [item for item in candidates if predicate(item)]
        lines.append(f"## {title}")
        lines.append("")
        if not bucket:
            lines.append("- None.")
            lines.append("")
            continue
        for item in bucket:
            pdf_name = f"knowledge_base/sources/downloads/{item['source_id']}.pdf"
            lines.extend(
                [
                    f"### P{item.get('priority')} {item.get('title')}",
                    "",
                    f"- candidate_id: `{item.get('candidate_id')}`",
                    f"- source_id: `{item.get('source_id')}`",
                    f"- access_mode: `{item.get('access_mode')}`",
                    f"- status: `{item.get('status')}`",
                    f"- landing_url: {item.get('landing_url') or 'n/a'}",
                    f"- pdf_url: {item.get('pdf_url') or 'n/a'}",
                    f"- save_as: `{pdf_name}`",
                    f"- purpose: {'; '.join(_as_list(item.get('allowed_uses')))}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _download_pdf(url: str, timeout: int) -> Tuple[bytes, Dict[str, str]]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; PPG-BP-RAG-Agent/1.0; +local research workflow)",
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec - curated URLs only
        headers = {key.lower(): value for key, value in response.headers.items()}
        data = response.read()
    return data, headers


def download_public_candidates(force: bool = False, timeout: int = 60) -> Dict[str, Any]:
    report = validate_fulltext_catalog()
    errors = [issue for issue in report["issues"] if issue["severity"] == "error"]
    if errors:
        raise ValueError(f"fulltext candidate catalog has validation errors: {errors}")

    results: List[Dict[str, Any]] = []
    downloads_root = resolve_project_path(DOWNLOADS_ROOT)
    downloads_root.mkdir(parents=True, exist_ok=True)

    for candidate in report["candidates"]:
        if not candidate.get("auto_download"):
            continue
        path = candidate_download_path(candidate)
        item = {
            "candidate_id": candidate["candidate_id"],
            "source_id": candidate["source_id"],
            "url": candidate.get("pdf_url"),
            "path": str(path),
            "status": "pending",
        }
        if path.exists() and not force:
            item.update({"status": "existing", "bytes": path.stat().st_size})
            results.append(item)
            continue
        try:
            data, headers = _download_pdf(str(candidate["pdf_url"]), timeout=timeout)
            content_type = headers.get("content-type", "")
            if not data.startswith(b"%PDF"):
                raise ValueError(f"downloaded content is not a PDF; content_type={content_type}")
            path.write_bytes(data)
            item.update(
                {
                    "status": "downloaded",
                    "bytes": len(data),
                    "content_type": content_type,
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
        except Exception as exc:  # pragma: no cover - network-specific failure detail is recorded.
            item.update({"status": "failed", "error": str(exc)})
        results.append(item)

    manifest = {
        "timestamp": int(time.time()),
        "download_count": sum(1 for item in results if item["status"] in {"downloaded", "existing"}),
        "failed_count": sum(1 for item in results if item["status"] == "failed"),
        "results": results,
    }
    _write_json(resolve_project_path(f"{PROCESSED_ROOT}/fulltext_download_manifest.json"), manifest)
    return manifest


def create_summary_notes(source_id: Optional[str] = None) -> Dict[str, Any]:
    report = validate_fulltext_catalog()
    errors = [issue for issue in report["issues"] if issue["severity"] == "error"]
    if errors:
        raise ValueError(f"fulltext candidate catalog has validation errors: {errors}")

    summary_root = resolve_project_path(SUMMARY_ROOT)
    summary_root.mkdir(parents=True, exist_ok=True)
    written: List[str] = []
    skipped: List[Dict[str, str]] = []

    for candidate in report["candidates"]:
        if source_id and candidate.get("source_id") != source_id and candidate.get("candidate_id") != source_id:
            continue
        if not candidate.get("include_in_summary"):
            skipped.append({"candidate_id": candidate["candidate_id"], "reason": "include_in_summary=false"})
            continue
        if candidate.get("summary_status") != "ready":
            skipped.append({"candidate_id": candidate["candidate_id"], "reason": f"summary_status={candidate.get('summary_status')}"})
            continue

        pdf_path = candidate_download_path(candidate)
        has_pdf = pdf_path.exists()
        lines = [
            f"### {candidate.get('title')}",
            "",
            f"- candidate_id: `{candidate.get('candidate_id')}`",
            f"- access_mode: `{candidate.get('access_mode')}`",
            f"- fulltext_status: {'local_pdf_available' if has_pdf else candidate.get('status')}",
            f"- source_url: {candidate.get('landing_url') or candidate.get('pdf_url') or 'n/a'}",
            f"- doi: {candidate.get('doi') or 'n/a'}",
            f"- pmid: {candidate.get('pmid') or 'n/a'}",
            f"- access_recorded: {candidate.get('last_accessed') or 'n/a'}",
            f"- local_pdf: `{pdf_path.name}`" if has_pdf else "- local_pdf: not saved",
            "",
            "#### 摘要入库要点",
            "",
        ]
        lines.extend(f"- {note}" for note in _as_list(candidate.get("summary_notes")))
        lines.extend(
            [
                "",
                "#### 使用边界",
                "",
                "- 只把上述摘要用于 PPG 估算解释、复测建议、设备局限、生活方式教育或安全提醒。",
                "- 不复制全文、不引用未审校段落、不生成诊断、治疗、开药、停药或替代规范血压测量的结论。",
                f"- candidate_hash: `{_candidate_hash(candidate)}`",
                "",
            ]
        )
        path = candidate_summary_path(candidate)
        path.write_text("\n".join(lines), encoding="utf-8")
        written.append(str(path))

    result = {"written_count": len(written), "written": written, "skipped": skipped}
    _write_json(resolve_project_path(f"{PROCESSED_ROOT}/fulltext_summary_manifest.json"), result)
    return result
