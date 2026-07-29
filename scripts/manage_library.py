"""Command-line literature management for the RAG knowledge base.

A single entry point to *add*, *remove*, *organise* and *inspect* the sources
that feed retrieval, built on :class:`app.services.library_manager.LibraryManager`.
Every mutation is validated and rescreens the knowledge base so downstream
artefacts stay consistent.

Examples
--------
    # List everything, or filter by classification / grade
    python scripts/manage_library.py list --tier A --topic lifestyle

    # Inspect one source
    python scripts/manage_library.py show aha_2025_bp_guideline_top_things

    # Add a source from a JSON/YAML file, or inline flags
    python scripts/manage_library.py add --file new_source.json
    python scripts/manage_library.py add \
        --id smith_2026_ppg_review --title "PPG BP review" \
        --organization "IEEE" --url https://doi.org/xx --year 2026 \
        --region global --topic cuffless_ppg_limitations \
        --evidence-class review --allowed-uses cuffless_ppg_limitations,signal_quality \
        --screening 4,5,5,4,4

    # Disable (soft) or delete (hard) a source
    python scripts/manage_library.py disable smith_2026_ppg_review
    python scripts/manage_library.py remove smith_2026_ppg_review

    # Taxonomy, stats, and manual rescreen
    python scripts/manage_library.py taxonomy
    python scripts/manage_library.py stats
    python scripts/manage_library.py rescreen
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

from app.services.library_manager import (
    EVIDENCE_TIERS,
    LibraryError,
    LibraryManager,
    evidence_tier,
)

_SCREENING_DIMS = ("authority", "recency", "relevance", "accessibility", "safety_applicability")


def _print_json(obj: Any) -> None:
    def _default(value: Any) -> Any:
        return str(value)

    print(json.dumps(obj, ensure_ascii=False, indent=2, default=_default))


def _load_payload(path: str) -> Dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    if path.endswith((".yaml", ".yml")):
        return yaml.safe_load(text) or {}
    return json.loads(text)


def _source_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    if args.file:
        return _load_payload(args.file)

    source: Dict[str, Any] = {}
    field_map = {
        "id": "source_id",
        "title": "title",
        "organization": "organization",
        "url": "url",
        "doi": "doi",
        "pmid": "pmid",
        "year": "year",
        "language": "language",
        "region": "region",
        "topic": "topic",
        "evidence_class": "evidence_class",
        "source_type": "source_type",
        "copyright_note": "copyright_note",
        "access_note": "access_note",
    }
    for arg_name, field in field_map.items():
        value = getattr(args, arg_name, None)
        if value is not None:
            source[field] = value
    if args.allowed_uses:
        source["allowed_uses"] = [u.strip() for u in args.allowed_uses.split(",") if u.strip()]
    if args.screening:
        parts = [p.strip() for p in args.screening.split(",")]
        if len(parts) != 5:
            raise SystemExit("--screening expects 5 comma-separated ints: authority,recency,relevance,accessibility,safety_applicability")
        source["screening"] = {dim: int(p) for dim, p in zip(_SCREENING_DIMS, parts)}
    if args.summary:
        source.setdefault("notes", {})["summary"] = args.summary
    return source


def _fmt_row(source: Dict[str, Any]) -> str:
    flag = "on " if source.get("include") else "off"
    return (
        f"[{source.get('tier', evidence_tier(source.get('evidence_class')))}] {flag} "
        f"{source.get('source_id', ''):<48} "
        f"{str(source.get('topic', '')):<26} "
        f"{str(source.get('evidence_class', '')):<24} "
        f"q={source.get('source_quality_score', 0):>2} "
        f"{str(source.get('title', ''))[:60]}"
    )


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_list(manager: LibraryManager, args: argparse.Namespace) -> int:
    include = None if args.all else (False if args.disabled else (True if args.enabled else None))
    sources = manager.list_sources(
        topic=args.topic,
        tier=args.tier,
        evidence_class=args.evidence_class,
        region=args.region,
        include=include,
        query=args.query,
        journal=args.journal,
        journal_tier=args.journal_tier,
    )
    if args.json:
        _print_json(sources)
        return 0
    print(f"# {len(sources)} sources (tier | include | id | topic | evidence_class | quality | title)")
    for tier in EVIDENCE_TIERS:
        rows = [s for s in sources if s.get("tier") == tier]
        if not rows:
            continue
        print(f"\n=== Tier {tier} ({len(rows)}) ===")
        for source in rows:
            print(_fmt_row(source))
    return 0


def cmd_show(manager: LibraryManager, args: argparse.Namespace) -> int:
    _print_json(manager.get_source(args.source_id))
    return 0


def cmd_add(manager: LibraryManager, args: argparse.Namespace) -> int:
    source = _source_from_args(args)
    result = manager.add_source(source, overwrite=args.overwrite)
    if result.warnings:
        print("warnings: " + "; ".join(result.warnings), file=sys.stderr)
    print(f"✓ {result.action}: {result.source_id} (tier {result.source['tier']}, quality {result.source['source_quality_score']})")
    if result.screening_files:
        print("rescreened -> " + ", ".join(Path(p).name for p in result.screening_files.values()))
    return 0


def cmd_update(manager: LibraryManager, args: argparse.Namespace) -> int:
    patch = _load_payload(args.file) if args.file else _source_from_args(args)
    patch.pop("source_id", None)
    result = manager.update_source(args.source_id, patch, replace=args.replace)
    print(f"✓ {result.action}: {result.source_id}")
    return 0


def cmd_remove(manager: LibraryManager, args: argparse.Namespace) -> int:
    if args.hard:
        result = manager.remove_source(args.source_id)
    else:
        result = manager.trash_source(args.source_id, reason=args.reason)
    print(f"✓ {result.action}: {result.source_id}")
    if result.action == "trashed":
        print("  （已移入废纸篓，可用 restore 恢复）")
    return 0


def cmd_restore(manager: LibraryManager, args: argparse.Namespace) -> int:
    result = manager.restore_source(args.source_id)
    print(f"✓ {result.action}: {result.source_id}")
    return 0


def cmd_trash_list(manager: LibraryManager, args: argparse.Namespace) -> int:
    items = manager.list_trash()
    if args.json:
        _print_json(items)
        return 0
    print(f"# 废纸篓 {len(items)} 条")
    for s in items:
        print(f"[{s.get('tier')}] {s.get('source_id'):<48} trashed@{s.get('_trashed_at','')} {str(s.get('title',''))[:50]}")
    return 0


def cmd_purge(manager: LibraryManager, args: argparse.Namespace) -> int:
    if args.all:
        result = manager.empty_trash()
        print(f"✓ 已清空废纸篓：{result['purged']} 条")
    else:
        if not args.source_id:
            raise SystemExit("purge 需要 source_id，或用 --all 清空废纸篓")
        result = manager.purge_source(args.source_id)
        print(f"✓ {result.action}: {result.source_id}（不可恢复）")
    return 0


def cmd_disable(manager: LibraryManager, args: argparse.Namespace) -> int:
    result = manager.set_include(args.source_id, False)
    print(f"✓ {result.action}: {result.source_id}")
    return 0


def cmd_enable(manager: LibraryManager, args: argparse.Namespace) -> int:
    result = manager.set_include(args.source_id, True)
    print(f"✓ {result.action}: {result.source_id}")
    return 0


def cmd_stats(manager: LibraryManager, args: argparse.Namespace) -> int:
    _print_json(manager.stats())
    return 0


def cmd_taxonomy(manager: LibraryManager, args: argparse.Namespace) -> int:
    _print_json(manager.taxonomy())
    return 0


def cmd_rescreen(manager: LibraryManager, args: argparse.Namespace) -> int:
    files = manager.rescreen()
    print("rescreened:")
    _print_json(files)
    return 0


def cmd_export(manager: LibraryManager, args: argparse.Namespace) -> int:
    sources = manager.list_sources(topic=args.topic, tier=args.tier, region=args.region)
    payload = json.dumps(sources, ensure_ascii=False, indent=2, default=str)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"exported {len(sources)} sources -> {args.out}")
    else:
        print(payload)
    return 0


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage_library",
        description="Add, remove and organise RAG knowledge-base literature.",
    )
    parser.add_argument("--no-rescreen", action="store_true", help="skip regenerating screening artefacts after a mutation")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list sources (filterable)")
    p_list.add_argument("--topic")
    p_list.add_argument("--tier", choices=list(EVIDENCE_TIERS))
    p_list.add_argument("--evidence-class", dest="evidence_class")
    p_list.add_argument("--region")
    p_list.add_argument("--journal", help="substring match on journal name")
    p_list.add_argument("--journal-tier", dest="journal_tier", type=int, choices=[1, 2, 3], help="filter by journal quality tier")
    p_list.add_argument("--query", help="substring match on id/title/organization/journal")
    p_list.add_argument("--enabled", action="store_true", help="only included sources")
    p_list.add_argument("--disabled", action="store_true", help="only excluded sources")
    p_list.add_argument("--all", action="store_true", help="include disabled (default shows all)")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show one source as JSON")
    p_show.add_argument("source_id")
    p_show.set_defaults(func=cmd_show)

    def _add_source_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--file", help="JSON/YAML file describing the source")
        p.add_argument("--id", help="source_id")
        p.add_argument("--title")
        p.add_argument("--organization")
        p.add_argument("--url")
        p.add_argument("--doi")
        p.add_argument("--pmid")
        p.add_argument("--year", type=int)
        p.add_argument("--language")
        p.add_argument("--region")
        p.add_argument("--topic")
        p.add_argument("--evidence-class", dest="evidence_class")
        p.add_argument("--source-type", dest="source_type")
        p.add_argument("--allowed-uses", dest="allowed_uses", help="comma-separated allowed_uses")
        p.add_argument("--screening", help="comma-separated 5 ints: authority,recency,relevance,accessibility,safety_applicability")
        p.add_argument("--summary", help="notes.summary text")
        p.add_argument("--copyright-note", dest="copyright_note")
        p.add_argument("--access-note", dest="access_note")

    p_add = sub.add_parser("add", help="add a new source")
    _add_source_flags(p_add)
    p_add.add_argument("--overwrite", action="store_true", help="replace if source_id already exists")
    p_add.set_defaults(func=cmd_add)

    p_update = sub.add_parser("update", help="update an existing source")
    p_update.add_argument("source_id")
    _add_source_flags(p_update)
    p_update.add_argument("--replace", action="store_true", help="full replace instead of merge")
    p_update.set_defaults(func=cmd_update)

    p_remove = sub.add_parser("remove", help="移入废纸篓（软删除，可恢复）；--hard 永久删除")
    p_remove.add_argument("source_id")
    p_remove.add_argument("--reason", help="废纸篓记录的删除原因")
    p_remove.add_argument("--hard", action="store_true", help="permanently delete instead of trashing")
    p_remove.set_defaults(func=cmd_remove)

    p_restore = sub.add_parser("restore", help="从废纸篓恢复一条文献")
    p_restore.add_argument("source_id")
    p_restore.set_defaults(func=cmd_restore)

    p_trash = sub.add_parser("trash-list", help="列出废纸篓内容")
    p_trash.add_argument("--json", action="store_true")
    p_trash.set_defaults(func=cmd_trash_list)

    p_purge = sub.add_parser("purge", help="从废纸篓永久删除（--all 清空）")
    p_purge.add_argument("source_id", nargs="?")
    p_purge.add_argument("--all", action="store_true", help="empty the whole recycle bin")
    p_purge.set_defaults(func=cmd_purge)

    p_disable = sub.add_parser("disable", help="soft-disable a source (include:false)")
    p_disable.add_argument("source_id")
    p_disable.set_defaults(func=cmd_disable)

    p_enable = sub.add_parser("enable", help="re-enable a disabled source")
    p_enable.add_argument("source_id")
    p_enable.set_defaults(func=cmd_enable)

    p_stats = sub.add_parser("stats", help="counts by tier/topic/region")
    p_stats.set_defaults(func=cmd_stats)

    p_tax = sub.add_parser("taxonomy", help="show controlled vocabularies (分类/分级)")
    p_tax.set_defaults(func=cmd_taxonomy)

    p_re = sub.add_parser("rescreen", help="regenerate screening artefacts")
    p_re.set_defaults(func=cmd_rescreen)

    p_exp = sub.add_parser("export", help="export filtered sources as JSON")
    p_exp.add_argument("--topic")
    p_exp.add_argument("--tier", choices=list(EVIDENCE_TIERS))
    p_exp.add_argument("--region")
    p_exp.add_argument("--out", help="output file (default stdout)")
    p_exp.set_defaults(func=cmd_export)

    return parser


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    manager = LibraryManager(auto_rescreen=not args.no_rescreen)
    try:
        return args.func(manager, args)
    except LibraryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
