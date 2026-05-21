from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional local metadata helper.
    PdfReader = None  # type: ignore[assignment]


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = Path("/Users/lianghao/Documents/Codex/2026-05-12/obsiden-zetro/KnowledgeVault")
LIBRARY_REL = Path("10 Literature") / "High Blood Pressure RAG"
DOWNLOADS_DIR = PROJECT_ROOT / "knowledge_base" / "sources" / "downloads"
SUMMARY_DIR = PROJECT_ROOT / "knowledge_base" / "sources" / "fulltext_summaries"
TRACKER_DIR = PROJECT_ROOT / "outputs" / "literature_download_tracker"
SOURCE_CATALOGS = [
    PROJECT_ROOT / "knowledge_base" / "sources" / "source_catalog.yaml",
    PROJECT_ROOT / "knowledge_base" / "sources" / "source_catalog_extra.yaml",
]
FULLTEXT_CANDIDATES = PROJECT_ROOT / "knowledge_base" / "sources" / "fulltext_candidates.yaml"

TOPIC_LABELS = {
    "bp_categories": "BP Categories",
    "cuffless_ppg_limitations": "Cuffless PPG Limitations",
    "home_bp_monitoring": "Home BP Monitoring",
    "lifestyle": "Lifestyle",
    "measurement_quality": "Measurement Quality",
    "medication_safety": "Medication Safety",
    "research_background": "Research Background",
    "special_population": "Special Population",
    "supplemental": "Supplemental",
    "validated_devices": "Validated Devices",
    "uncategorized": "Uncategorized",
}

MANUAL_OVERRIDES: dict[str, dict[str, Any]] = {
    "aha_ama_2020_smbp_policy_statement": {
        "topic": "home_bp_monitoring",
        "evidence_class": "scientific_statement",
        "allowed_uses": ["home_bp_monitoring", "remeasurement", "device_advice"],
    },
    "aha_prevent_equations_circulation_2024": {
        "topic": "research_background",
        "evidence_class": "research_article",
        "allowed_uses": ["research_background"],
    },
    "chinese_2019_home_bp_monitoring_guideline": {
        "title": "2019中国家庭血压监测指南",
        "topic": "home_bp_monitoring",
        "evidence_class": "guideline",
        "allowed_uses": ["home_bp_monitoring", "remeasurement", "device_advice"],
    },
    "esc_2024_elevated_bp_hypertension_guideline": {
        "title": "2024 ESC Guidelines for the management of elevated blood pressure and hypertension",
        "topic": "bp_categories",
        "evidence_class": "guideline",
        "allowed_uses": ["bp_category_reference", "home_bp_monitoring", "remeasurement", "special_population"],
    },
    "esc_2024_elevated_bp_hypertension_doi_report": {
        "topic": "supplemental",
        "evidence_class": "supplemental_disclosure",
        "allowed_uses": ["research_background"],
    },
    "esc_2024_pharmacotherapy_what_is_new": {
        "topic": "supplemental",
        "evidence_class": "commentary",
        "allowed_uses": ["research_background"],
    },
}


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def read_source_catalogs() -> dict[str, dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for path in SOURCE_CATALOGS:
        catalog = load_yaml(path)
        for source in catalog.get("sources", []) or []:
            source_id = str(source.get("source_id") or "")
            if source_id:
                sources[source_id] = source
    return sources


def read_candidates() -> dict[str, dict[str, Any]]:
    catalog = load_yaml(FULLTEXT_CANDIDATES)
    candidates: dict[str, dict[str, Any]] = {}
    for candidate in catalog.get("candidates", []) or []:
        source_id = str(candidate.get("source_id") or "")
        if source_id:
            candidates[source_id] = candidate
    return candidates


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pdf_pages_and_title(path: Path) -> tuple[int | None, str]:
    if PdfReader is None:
        data = path.read_bytes()
        # Cheap fallback when pypdf is not installed in the project venv. It is
        # enough for an inventory count and avoids adding a runtime dependency.
        page_count = len(re.findall(rb"/Type\s*/Page\b", data))
        return page_count or None, ""
    try:
        reader = PdfReader(str(path))
        metadata = reader.metadata or {}
        return len(reader.pages), str(metadata.get("/Title") or "").strip()
    except Exception:
        return None, ""


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [part.strip() for part in str(value).split(",") if part.strip()]


def slug_note_name(source_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", source_id).strip("_") + ".md"


def topic_note_name(topic: str) -> str:
    label = TOPIC_LABELS.get(topic, topic.replace("_", " ").title())
    safe = re.sub(r"[^A-Za-z0-9_. -]+", "", label).strip().replace(" ", " ")
    return f"Topic - {safe}.md"


def yaml_scalar(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def markdown_link_path(path: Path) -> str:
    return path.as_posix().replace(" ", "%20")


def external_file_uri(path: Path) -> str:
    return path.resolve().as_uri()


def build_records() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sources = read_source_catalogs()
    candidates = read_candidates()
    records: list[dict[str, Any]] = []
    for pdf in sorted(DOWNLOADS_DIR.glob("*.pdf")):
        source_id = pdf.stem
        source = sources.get(source_id, {})
        candidate = candidates.get(source_id, {})
        override = MANUAL_OVERRIDES.get(source_id, {})
        pages, pdf_title = pdf_pages_and_title(pdf)
        summary_path = SUMMARY_DIR / f"{source_id}.summary.md"
        title = str(override.get("title") or source.get("title") or candidate.get("title") or pdf_title or source_id)
        summary_exists = summary_path.exists()
        summary_status = str(candidate.get("summary_status") or ("ready" if summary_exists else "pending_fulltext"))
        record = {
            "source_id": source_id,
            "title": title,
            "organization": source.get("organization") or candidate.get("organization") or "",
            "year": source.get("year") or candidate.get("year") or "",
            "topic": override.get("topic") or source.get("topic") or candidate.get("topic") or "uncategorized",
            "evidence_class": override.get("evidence_class") or source.get("evidence_class") or "",
            "allowed_uses": as_list(override.get("allowed_uses") or source.get("allowed_uses") or candidate.get("allowed_uses")),
            "doi": source.get("doi") or candidate.get("doi") or "",
            "pmid": source.get("pmid") or candidate.get("pmid") or "",
            "url": source.get("url") or candidate.get("landing_url") or candidate.get("pdf_url") or "",
            "pdf_file": pdf.name,
            "project_pdf_path": str(pdf),
            "pages": pages,
            "sha256": sha256_file(pdf),
            "summary_exists": summary_exists,
            "summary_status": summary_status,
            "summary_path": str(summary_path) if summary_exists else "",
            "candidate_status": candidate.get("status") or "",
            "include_in_summary": bool(candidate.get("include_in_summary", False)),
            "access_instruction": candidate.get("access_instruction") or "",
        }
        records.append(record)

    unresolved: list[dict[str, Any]] = []
    for web_batch in sorted(TRACKER_DIR.glob("web_batch*_results_*.json")):
        payload = json.loads(web_batch.read_text(encoding="utf-8"))
        for item in payload.get("items", []):
            if item.get("local_status") == "unresolved_not_archived":
                unresolved.append(
                    {
                        "source_id": item.get("item_id"),
                        "title": item.get("title"),
                        "status": item.get("web_access_type"),
                        "url": item.get("best_pdf_url"),
                        "reason": item.get("notes"),
                        "save_as": item.get("desired_save_as"),
                    }
                )

    for source_id, candidate in sorted(candidates.items()):
        if (DOWNLOADS_DIR / f"{source_id}.pdf").exists():
            continue
        if candidate.get("summary_status") == "ready":
            continue
        if candidate.get("status") in {"queued_manual", "queued_browser", "queued_institution", "access_blocked", "awaiting_human_verification"}:
            unresolved.append(
                {
                    "source_id": source_id,
                    "title": candidate.get("title"),
                    "status": candidate.get("status"),
                    "url": candidate.get("pdf_url") or candidate.get("landing_url"),
                    "reason": candidate.get("access_instruction"),
                    "save_as": f"knowledge_base/sources/downloads/{source_id}.pdf",
                }
            )

    seen: set[str] = set()
    deduped_unresolved: list[dict[str, Any]] = []
    for item in unresolved:
        key = str(item.get("source_id") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped_unresolved.append(item)
    return records, deduped_unresolved


def ensure_symlink(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        if link.is_symlink() and link.resolve() == target.resolve():
            return
        link.unlink()
    os.symlink(target.resolve(), link)


def note_text(record: dict[str, Any], library_rel: Path) -> str:
    allowed = ", ".join(record["allowed_uses"]) if record["allowed_uses"] else "not cataloged"
    project_pdf_uri = external_file_uri(Path(record["project_pdf_path"]))
    summary_link = markdown_link_path(Path(record["summary_path"])) if record["summary_path"] else ""
    frontmatter = [
        "---",
        "type: literature_note",
        "project: high_blood_pressure_rag",
        f"source_id: {yaml_scalar(record['source_id'])}",
        f"title: {yaml_scalar(record['title'])}",
        f"topic: {yaml_scalar(record['topic'])}",
        f"evidence_class: {yaml_scalar(record['evidence_class'])}",
        f"summary_status: {yaml_scalar(record['summary_status'])}",
        f"summary_exists: {str(record['summary_exists']).lower()}",
        f"pages: {record['pages'] if record['pages'] is not None else 'null'}",
        f"sha256: {yaml_scalar(record['sha256'])}",
        f"updated: {date.today().isoformat()}",
        "tags: []",
        "---",
        "",
    ]
    lines = [
        *frontmatter,
        f"# {record['title']}",
        "",
        "## Status",
        "",
        f"- source_id: `{record['source_id']}`",
        f"- topic: `{record['topic']}`",
        f"- evidence_class: `{record['evidence_class'] or 'not cataloged'}`",
        f"- allowed_uses: `{allowed}`",
        f"- summary_status: `{record['summary_status']}`",
        f"- summary_note: `{'available' if record['summary_exists'] else 'missing'}`",
        "",
        "## Links",
        "",
        f"- PDF: [Open local PDF]({project_pdf_uri})",
        f"- Obsidian symlink path: `{(library_rel / 'PDF Library' / record['pdf_file']).as_posix()}`",
    ]
    if summary_link:
        lines.append(f"- Project summary note: [{record['source_id']}.summary.md]({summary_link})")
    if record["url"]:
        lines.append(f"- Source URL: {record['url']}")
    if record["doi"]:
        lines.append(f"- DOI: `{record['doi']}`")
    if record["pmid"]:
        lines.append(f"- PMID: `{record['pmid']}`")
    lines.extend(
        [
            "",
            "## RAG Boundary",
            "",
            "- 这篇文献只能按 `allowed_uses` 支撑报告证据，不能扩展为诊断、治疗、开药、停药或替代规范袖带血压测量。",
            "- PDF 全文只在本地保管；进入知识库的应是中文摘要、citation、访问记录和安全边界。",
            "",
        ]
    )
    if record["access_instruction"]:
        lines.extend(["## Access Note", "", f"- {record['access_instruction']}", ""])
    return "\n".join(lines)


def topic_hub_text(topic: str, records: list[dict[str, Any]], library_rel: Path) -> str:
    label = TOPIC_LABELS.get(topic, topic.replace("_", " ").title())
    ready = sum(1 for record in records if record["summary_exists"])
    lines = [
        "---",
        "type: topic_hub",
        "project: high_blood_pressure_rag",
        f"topic: {yaml_scalar(topic)}",
        f"updated: {date.today().isoformat()}",
        "tags: []",
        "---",
        "",
        f"# Topic - {label}",
        "",
        f"- topic: `{topic}`",
        f"- sources: {len(records)}",
        f"- summary ready: {ready}",
        "",
        "## Graph Role",
        "",
        "- 这个 hub 是 Obsidian 图谱中的主题中心节点。",
        "- 文献 note 只通过这里聚合；PDF 用普通外部文件链接，不进入关系图谱。",
        "",
        "## Sources",
        "",
        "| source_id | title | pages | summary |",
        "| --- | --- | ---: | --- |",
    ]
    for record in sorted(records, key=lambda item: (str(item["title"]).lower(), item["source_id"])):
        note_link = f"[[{(library_rel / 'Notes' / slug_note_name(record['source_id'])).as_posix()}|{record['source_id']}]]"
        title = str(record["title"]).replace("|", "\\|")
        lines.append(f"| {note_link} | {title} | {record['pages'] or ''} | {'ready' if record['summary_exists'] else 'pending'} |")
    lines.append("")
    return "\n".join(lines)


def index_text(records: list[dict[str, Any]], unresolved: list[dict[str, Any]], library_rel: Path) -> str:
    summarized = sum(1 for item in records if item["summary_exists"])
    pending = len(records) - summarized
    topics: dict[str, int] = {}
    for record in records:
        topics[record["topic"]] = topics.get(record["topic"], 0) + 1

    lines = [
        "# High Blood Pressure RAG Literature Library",
        "",
        f"- Updated: {date.today().isoformat()}",
        f"- Archived PDFs: {len(records)}",
        f"- With summary notes: {summarized}",
        f"- PDF archived but summary pending: {pending}",
        f"- Unresolved download/access items: {len(unresolved)}",
        f"- Canonical project PDF store: `{DOWNLOADS_DIR}`",
        f"- Clean graph guide: [[{(library_rel / 'Graph - Clean View.md').as_posix()}|Graph - Clean View]]",
        "",
        "## Governance",
        "",
        "- Obsidian 中的 `PDF Library/` 是指向项目 canonical PDF 的符号链接，不是新的可提交全文副本。",
        "- 文献 note 不再用 wiki-link 连接 PDF，避免 PDF/附件节点污染关系图谱。",
        "- 图谱入口建议使用下面的 Topic Hubs，而不是让 MOC 直接连接所有文献。",
        "- Git 中只应提交 source metadata、中文摘要、索引和工作日志；PDF 全文保持本地忽略。",
        "- 医学边界不变：不诊断、不开药、不停药、不替代规范血压测量。",
        "",
        "## Clean Graph Entry",
        "",
        "| topic | pdf_count | hub |",
        "| --- | ---: | --- |",
    ]
    for topic, count in sorted(topics.items()):
        hub_link = f"[[{(library_rel / 'Hubs' / topic_note_name(topic)).as_posix()}|{TOPIC_LABELS.get(topic, topic)}]]"
        lines.append(f"| `{topic}` | {count} | {hub_link} |")

    lines.extend(
        [
            "",
            "## Downloaded PDF Index",
            "",
            "| source_id | title | topic | pages | summary |",
            "| --- | --- | --- | ---: | --- |",
        ]
    )
    for record in records:
        title = str(record["title"]).replace("|", "\\|")
        lines.append(
            f"| `{record['source_id']}` | {title} | `{record['topic']}` | {record['pages'] or ''} | "
            f"{'ready' if record['summary_exists'] else 'pending'} |"
        )

    lines.extend(
        [
            "",
            "## Unresolved / Needs Manual Download",
            "",
            "| source_id | status | URL | reason | save_as |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if unresolved:
        for item in unresolved:
            reason = str(item.get("reason") or "").replace("\n", " ").replace("|", "\\|")
            if len(reason) > 180:
                reason = reason[:177] + "..."
            url = item.get("url") or ""
            url_cell = f"[link]({url})" if url else ""
            lines.append(
                f"| `{item.get('source_id')}` | `{item.get('status')}` | {url_cell} | {reason} | `{item.get('save_as')}` |"
            )
    else:
        lines.append("| none |  |  |  |  |")
    lines.append("")
    return "\n".join(lines)


def unresolved_text(unresolved: list[dict[str, Any]]) -> str:
    lines = [
        "# High Blood Pressure RAG - Unresolved Full Text",
        "",
        f"- Updated: {date.today().isoformat()}",
        f"- Items: {len(unresolved)}",
        "",
        "| source_id | status | URL | reason | save_as |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in unresolved:
        reason = str(item.get("reason") or "").replace("\n", " ").replace("|", "\\|")
        if len(reason) > 220:
            reason = reason[:217] + "..."
        url = item.get("url") or ""
        url_cell = f"[link]({url})" if url else ""
        lines.append(f"| `{item.get('source_id')}` | `{item.get('status')}` | {url_cell} | {reason} | `{item.get('save_as')}` |")
    return "\n".join(lines) + "\n"


def graph_guide_text(library_rel: Path) -> str:
    return "\n".join(
        [
            "# Clean Graph Guide - High Blood Pressure RAG",
            "",
            f"- Updated: {date.today().isoformat()}",
            "",
            "## 推荐入口",
            "",
            f"- 总入口：[[{(library_rel / 'MOC - High Blood Pressure RAG Literature.md').as_posix()}|MOC]]",
            f"- 主题入口目录：`{(library_rel / 'Hubs').as_posix()}`",
            "",
            "## 为什么现在更干净",
            "",
            "- PDF 不再使用 wiki-link，因此不会作为大量附件节点挤进图谱。",
            "- 文献 note 不再写 topic tag，避免 tag 节点干扰。",
            "- 图谱结构改成 `MOC -> Topic Hub -> Literature Note`。",
            "",
            "## Obsidian 图谱建议",
            "",
            "- 优先在 `MOC` 或某个 `Topic - ...` hub 上打开 Local Graph，深度设为 2。",
            "- Global Graph 建议关闭 Tags 和 Attachments。",
            "- Global Graph 可用过滤条件：",
            "",
            "```text",
            "path:\"10 Literature/High Blood Pressure RAG/Hubs\" OR path:\"10 Literature/High Blood Pressure RAG/Notes\" OR path:\"10 Literature/High Blood Pressure RAG/MOC\"",
            "```",
            "",
        ]
    )


def sync(vault: Path) -> dict[str, Any]:
    records, unresolved = build_records()
    library_dir = vault / LIBRARY_REL
    pdf_dir = library_dir / "PDF Library"
    notes_dir = library_dir / "Notes"
    hubs_dir = library_dir / "Hubs"
    library_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)
    hubs_dir.mkdir(parents=True, exist_ok=True)

    for record in records:
        ensure_symlink(pdf_dir / record["pdf_file"], Path(record["project_pdf_path"]))
        note_path = notes_dir / slug_note_name(record["source_id"])
        note_path.write_text(note_text(record, LIBRARY_REL), encoding="utf-8")

    records_by_topic: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        records_by_topic.setdefault(record["topic"], []).append(record)
    for topic, topic_records in sorted(records_by_topic.items()):
        hub_path = hubs_dir / topic_note_name(topic)
        hub_path.write_text(topic_hub_text(topic, topic_records, LIBRARY_REL), encoding="utf-8")

    index_path = library_dir / "MOC - High Blood Pressure RAG Literature.md"
    unresolved_path = library_dir / "Unresolved Full Text.md"
    graph_guide_path = library_dir / "Graph - Clean View.md"
    index_path.write_text(index_text(records, unresolved, LIBRARY_REL), encoding="utf-8")
    unresolved_path.write_text(unresolved_text(unresolved), encoding="utf-8")
    graph_guide_path.write_text(graph_guide_text(LIBRARY_REL), encoding="utf-8")

    manifest = {
        "generated_at": date.today().isoformat(),
        "vault": str(vault),
        "library_dir": str(library_dir),
        "pdf_link_dir": str(pdf_dir),
        "notes_dir": str(notes_dir),
        "hubs_dir": str(hubs_dir),
        "pdf_count": len(records),
        "topic_hub_count": len(records_by_topic),
        "summary_ready_count": sum(1 for item in records if item["summary_exists"]),
        "summary_pending_count": sum(1 for item in records if not item["summary_exists"]),
        "unresolved_count": len(unresolved),
        "index_path": str(index_path),
        "unresolved_path": str(unresolved_path),
        "graph_guide_path": str(graph_guide_path),
        "records": records,
        "unresolved": unresolved,
    }
    TRACKER_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = TRACKER_DIR / f"obsidian_literature_sync_{date.today().isoformat()}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync downloaded RAG literature PDFs into an Obsidian-friendly library.")
    parser.add_argument("--vault", default=os.environ.get("OBSIDIAN_VAULT", str(DEFAULT_VAULT)), help="Obsidian vault root.")
    args = parser.parse_args()
    manifest = sync(Path(args.vault).expanduser())
    print(json.dumps({key: manifest[key] for key in [
        "library_dir",
        "pdf_link_dir",
        "notes_dir",
        "hubs_dir",
        "pdf_count",
        "topic_hub_count",
        "summary_ready_count",
        "summary_pending_count",
        "unresolved_count",
        "index_path",
        "unresolved_path",
    ]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
