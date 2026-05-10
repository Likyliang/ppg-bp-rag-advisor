from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml

from app.services.config_loader import resolve_project_path
from app.services.source_catalog import included_sources


GENERATED_ROOT = "knowledge_base/raw/expanded"
DOWNLOADS_ROOT = "knowledge_base/sources/downloads"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", value.strip().lower()).strip("_")


def _front_matter(source: Dict[str, Any]) -> str:
    fields = {
        "source_id": source.get("source_id"),
        "title": source.get("title"),
        "source_type": source.get("source_type"),
        "organization": source.get("organization"),
        "region": source.get("region"),
        "topic": source.get("topic"),
        "language": source.get("language"),
        "url": source.get("url") or "",
        "doi": source.get("doi") or "",
        "pmid": str(source.get("pmid") or ""),
        "year": str(source.get("year") or ""),
        "last_accessed": str(source.get("last_accessed") or ""),
        "evidence_class": source.get("evidence_class"),
        "source_quality_score": str(source.get("source_quality_score")),
        "allowed_uses": source.get("allowed_uses") or [],
        "review_status": source.get("review_status"),
        "derived_from": "knowledge_base/sources/source_catalog.yaml",
        "source_hash": source.get("source_hash"),
        "safety_level": "high" if "emergency_alert" in source.get("allowed_uses", []) or "medication_safety" in source.get("allowed_uses", []) else "standard",
    }
    return "---\n" + yaml.safe_dump(fields, allow_unicode=True, sort_keys=False).strip() + "\n---\n\n"


def _section(title: str, lines: Iterable[str]) -> str:
    content = "\n".join(f"- {line}" for line in lines if line)
    if not content:
        content = "- 暂无额外要点。"
    return f"## {title}\n\n{content}\n\n"


def source_to_markdown(source: Dict[str, Any]) -> str:
    notes = source.get("notes") or {}
    summary = notes.get("summary") or ""
    key_points = notes.get("key_points") or []
    implementation_notes = notes.get("implementation_notes") or []
    boundaries = [
        "该来源只用于 PPG 估算结果解释、复测建议、生活方式建议、就医提醒或安全边界。",
        "不得把该来源改写成本系统可以诊断、治疗、开药、停药或替代规范血压测量的依据。",
    ]
    if source.get("evidence_class") in {"review", "research_context"}:
        boundaries.append("研究或综述来源只用于背景和局限说明，不用于患者级临床建议。")
    download_note = _download_note_section(source["source_id"])
    return (
        _front_matter(source)
        + "## 来源摘要\n\n"
        + f"{summary}\n\n"
        + _section("可用于报告的要点", key_points)
        + _section("实现使用说明", implementation_notes)
        + download_note
        + _section("安全边界", boundaries)
    )


def _download_note_section(source_id: str) -> str:
    downloads = resolve_project_path(DOWNLOADS_ROOT)
    sections: List[str] = []
    for suffix in (".summary.md", ".summary.txt", ".notes.md", ".notes.txt"):
        path = downloads / f"{source_id}{suffix}"
        if path.exists():
            sections.append(path.read_text(encoding="utf-8").strip())
    pdf_path = downloads / f"{source_id}.pdf"
    if pdf_path.exists():
        sections.append(
            f"已检测到本地 PDF：{pdf_path.name}。请只把人工摘要写入同名 .summary.md 后再进入知识库，避免复制受版权保护全文。"
        )
    if not sections:
        return ""
    return "## 人工下载材料摘要\n\n" + "\n\n".join(sections) + "\n\n"


def extract_source_notes(clean: bool = False) -> Dict[str, Any]:
    root = resolve_project_path(GENERATED_ROOT)
    if clean and root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    written: List[str] = []
    for source in included_sources():
        topic = _slug(source.get("topic", "misc"))
        source_id = _slug(source["source_id"])
        path = root / topic / f"{source_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source_to_markdown(source), encoding="utf-8")
        written.append(str(path))
    return {"written_count": len(written), "root": str(root), "files": written}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate curated Markdown source notes from source_catalog.yaml.")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    result = extract_source_notes(clean=args.clean)
    print(yaml.safe_dump({k: v for k, v in result.items() if k != "files"}, allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    main()
