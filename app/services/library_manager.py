"""Literature (source) management layer for the RAG knowledge base.

This module is the single management surface for *adding*, *removing*, and
*organising* the literature that feeds the retrieval pipeline. It sits on top of
the existing ``source_catalog`` validation/screening logic and never bypasses
it: every mutation is validated and, on success, the screening artefacts
(``included_sources.json`` / ``excluded_sources.json`` /
``source_screening_report.json``) are regenerated so the rest of the system
stays consistent.

Organisation model (分类 / 分级)
--------------------------------
* **分类 classification** — every source is filed under a ``topic`` (subject
  taxonomy), a ``region`` (issuing body / geography) and a ``source_type``
  (document kind). ``allowed_uses`` further scopes where a source may be cited.
* **分级 grading** — ``evidence_class`` maps onto a three-tier trust hierarchy
  (:data:`EVIDENCE_TIERS`). The 5-dimension ``screening`` score
  (:func:`app.services.source_catalog.screening_score`) grades individual
  quality and drives the include threshold.

The catalog is stored in two YAML files. ``source_catalog.yaml`` holds the core
guideline sources and is treated as protected; new sources are appended to
``source_catalog_extra.yaml``. Mutations to an existing source are written back
to whichever file owns it.
"""

from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.services.config_loader import resolve_project_path
from app.services.source_catalog import (
    ALLOWED_EVIDENCE_CLASSES,
    ALLOWED_USES,
    CATALOG_PATH,
    EXPECTED_TOPICS,
    EXTRA_CATALOG_PATH,
    SCREEN_THRESHOLD,
    CatalogIssue,
    screening_score,
    source_identity_hash,
    validate_source,
    write_screening_outputs,
)

# Catalog files, in priority order. The first is protected (core guideline
# sources); new sources are appended to the second.
PROTECTED_CATALOG = CATALOG_PATH
WRITABLE_CATALOG = EXTRA_CATALOG_PATH
CATALOG_FILES = (PROTECTED_CATALOG, WRITABLE_CATALOG)

# Recycle bin: trashed sources move here (committed metadata) and vanish from
# the active catalog / screening / retrieval until restored. Delete = soft.
TRASH_CATALOG = "knowledge_base/sources/source_catalog_trash.yaml"

# 分级：evidence_class -> trust tier. Tier A carries the highest citation trust
# (guidelines, standards, official statements); Tier C is background context.
EVIDENCE_TIERS: "OrderedDict[str, List[str]]" = OrderedDict(
    [
        (
            "A",
            [
                "guideline",
                "validation_standard",
                "scientific_statement",
                "official_health_education",
                "safety_rule",
            ],
        ),
        ("B", ["review", "patient_education"]),
        ("C", ["research_context"]),
    ]
)

TIER_LABELS = {
    "A": "A · 高信任（指南/标准/官方声明）",
    "B": "B · 中信任（综述/患教）",
    "C": "C · 背景（研究上下文）",
}

_EVIDENCE_TO_TIER = {
    evidence: tier for tier, classes in EVIDENCE_TIERS.items() for evidence in classes
}

# Canonical field order for YAML write-back so diffs stay stable and readable.
_FIELD_ORDER = [
    "source_id",
    "title",
    "organization",
    "url",
    "doi",
    "pmid",
    "year",
    "language",
    "region",
    "journal",
    "journal_tier",
    "topic",
    "evidence_class",
    "source_type",
    "include",
    "allowed_uses",
    "copyright_note",
    "access_note",
    "last_accessed",
    "screening",
    "notes",
]

# Fields rendered in flow (inline) style to match the existing catalog format.
_FLOW_FIELDS = {"allowed_uses", "screening"}

_SCREENING_DIMS = ("authority", "recency", "relevance", "accessibility", "safety_applicability")


def evidence_tier(evidence_class: Optional[str]) -> str:
    """Return the trust tier ('A'/'B'/'C') for an ``evidence_class``.

    Unknown/empty classes fall back to tier ``C`` (treated as background).
    """

    return _EVIDENCE_TO_TIER.get(str(evidence_class or ""), "C")


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class LibraryError(Exception):
    """Raised when a management operation cannot be completed."""


class SourceNotFoundError(LibraryError):
    """Raised when a ``source_id`` does not exist in any catalog."""


class DuplicateSourceError(LibraryError):
    """Raised when adding a source whose id or identity already exists."""


@dataclass
class MutationResult:
    """Outcome of an add/update/remove operation."""

    source_id: str
    action: str
    source: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    screening_files: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "action": self.action,
            "source": self.source,
            "warnings": self.warnings,
            "screening_files": self.screening_files,
        }


# --------------------------------------------------------------------------- #
# YAML load / dump helpers (per-file, format-preserving-ish)
# --------------------------------------------------------------------------- #
def _load_catalog_file(path: str) -> Dict[str, Any]:
    catalog_path = resolve_project_path(path)
    if not catalog_path.exists():
        return {"catalog_version": 1, "sources": []}
    with catalog_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    data.setdefault("sources", [])
    return data


class _CatalogDumper(yaml.SafeDumper):
    """SafeDumper matching the hand-written catalog style: block sequences are
    indented under their key, and empty values render blank (not ``null``)."""

    def increase_indent(self, flow=False, indentless=False):  # noqa: D401
        return super().increase_indent(flow, False)


def _represent_blank_none(dumper: yaml.Dumper, _value: Any):
    return dumper.represent_scalar("tag:yaml.org,2002:null", "")


_CatalogDumper.add_representer(type(None), _represent_blank_none)


def _ordered_source(source: Dict[str, Any]) -> "OrderedDict[str, Any]":
    ordered: "OrderedDict[str, Any]" = OrderedDict()
    for key in _FIELD_ORDER:
        if key in source:
            ordered[key] = source[key]
    # Preserve any extra keys not in the canonical order.
    for key, value in source.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def _apply_flow_style(node: yaml.nodes.Node) -> None:
    """Match the hand-written catalog style: inline every scalar list, plus the
    ``screening`` mapping; keep ``notes``/source mappings in block style."""

    if isinstance(node, yaml.nodes.SequenceNode):
        if all(isinstance(child, yaml.nodes.ScalarNode) for child in node.value):
            node.flow_style = True
        for child in node.value:
            _apply_flow_style(child)
    elif isinstance(node, yaml.nodes.MappingNode):
        for key_node, value_node in node.value:
            if key_node.value == "screening":
                value_node.flow_style = True
            _apply_flow_style(value_node)


def _represent_source(dumper: yaml.Dumper, data: "OrderedDict[str, Any]"):
    node = dumper.represent_dict(data.items())
    _apply_flow_style(node)
    return node


_CatalogDumper.add_representer(OrderedDict, _represent_source)


def _serialize_entry(source: Dict[str, Any]) -> str:
    """Serialize a single source as an indented ``  - ...`` YAML list block."""

    doc = yaml.dump(
        {"sources": [_ordered_source(dict(source))]},
        Dumper=_CatalogDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=4096,
    )
    # Drop the wrapping ``sources:`` line, keep the indented entry block.
    lines = doc.splitlines()
    body = [ln for ln in lines[1:]] if lines and lines[0].startswith("sources:") else lines
    return "\n".join(body).rstrip() + "\n"


def _append_entry(path: str, source: Dict[str, Any]) -> None:
    """Append one entry to a catalog file without rewriting existing entries.

    Keeps day-to-day ``add`` operations to a minimal git diff. Falls back to a
    full rewrite if the file is missing or has no ``sources:`` anchor.
    """

    catalog_path = resolve_project_path(path)
    if not catalog_path.exists():
        _write_catalog_file(path, {"catalog_version": 1, "sources": [source]})
        return

    text = catalog_path.read_text(encoding="utf-8")
    if "\nsources:" not in text and not text.startswith("sources:"):
        catalog = _load_catalog_file(path)
        catalog.setdefault("sources", []).append(source)
        _write_catalog_file(path, catalog)
        return

    import re

    text = re.sub(r"(?m)^updated:.*$", f"updated: {date.today().isoformat()}", text, count=1)
    if not text.endswith("\n"):
        text += "\n"
    text += _serialize_entry(source)
    catalog_path.write_text(text, encoding="utf-8")


def _write_catalog_file(path: str, catalog: Dict[str, Any]) -> None:
    catalog = dict(catalog)
    catalog["updated"] = date.today().isoformat()
    catalog["sources"] = [_ordered_source(dict(s)) for s in catalog.get("sources", [])]
    # Emit top-level keys in a stable order: metadata first, then sources.
    ordered_top: "OrderedDict[str, Any]" = OrderedDict()
    for key in ("catalog_version", "updated", "screen_threshold"):
        if key in catalog:
            ordered_top[key] = catalog[key]
    ordered_top["sources"] = catalog["sources"]
    for key, value in catalog.items():
        if key not in ordered_top:
            ordered_top[key] = value

    catalog_path = resolve_project_path(path)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.dump(
        ordered_top,
        Dumper=_CatalogDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=4096,
    )
    catalog_path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- #
# LibraryManager
# --------------------------------------------------------------------------- #
class LibraryManager:
    """Add, remove and organise knowledge-base literature.

    All read operations span both catalog files. Writes go to the file that
    owns the source (new sources default to :data:`WRITABLE_CATALOG`).
    """

    def __init__(
        self,
        catalog_files: Optional[List[str]] = None,
        writable_catalog: str = WRITABLE_CATALOG,
        auto_rescreen: bool = True,
        trash_catalog: str = TRASH_CATALOG,
        manage_fulltext: bool = True,
    ) -> None:
        self.catalog_files = list(catalog_files or CATALOG_FILES)
        if writable_catalog not in self.catalog_files:
            self.catalog_files.append(writable_catalog)
        self.writable_catalog = writable_catalog
        self.auto_rescreen = auto_rescreen
        self.trash_catalog = trash_catalog
        # When True, trashing/restoring a source also moves its full-text PDF
        # into / out of the recycle bin. Disabled in unit tests to stay offline.
        self.manage_fulltext = manage_fulltext

    # ---- loading ---------------------------------------------------------- #
    def _load_all(self) -> "OrderedDict[str, Dict[str, Any]]":
        """Return ``{catalog_path: catalog_data}`` for every file."""

        return OrderedDict((path, _load_catalog_file(path)) for path in self.catalog_files)

    def _locate(self, source_id: str) -> Optional[tuple]:
        """Return ``(catalog_path, index, source)`` for ``source_id`` or None."""

        for path in self.catalog_files:
            catalog = _load_catalog_file(path)
            for index, source in enumerate(catalog.get("sources", [])):
                if str(source.get("source_id")) == source_id:
                    return path, index, source
        return None

    # ---- read ------------------------------------------------------------- #
    def list_sources(
        self,
        topic: Optional[str] = None,
        tier: Optional[str] = None,
        evidence_class: Optional[str] = None,
        region: Optional[str] = None,
        include: Optional[bool] = None,
        query: Optional[str] = None,
        journal: Optional[str] = None,
        journal_tier: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Return sources across all catalogs, filtered and annotated.

        Each returned source gains derived fields ``tier`` and
        ``source_quality_score`` for convenience. ``journal`` is a substring
        match; ``journal_tier`` filters on the 1/2/3 journal quality tier (used
        to screen out weaker papers).
        """

        results: List[Dict[str, Any]] = []
        query_lc = query.lower() if query else None
        journal_lc = journal.lower() if journal else None
        for path, catalog in self._load_all().items():
            for source in catalog.get("sources", []):
                item = dict(source)
                item["tier"] = evidence_tier(item.get("evidence_class"))
                item["source_quality_score"] = screening_score(item)
                item["_catalog"] = path
                if topic and item.get("topic") != topic:
                    continue
                if tier and item["tier"] != tier:
                    continue
                if evidence_class and item.get("evidence_class") != evidence_class:
                    continue
                if region and item.get("region") != region:
                    continue
                if journal_tier is not None and item.get("journal_tier") != journal_tier:
                    continue
                if journal_lc and journal_lc not in str(item.get("journal", "")).lower():
                    continue
                if include is not None and bool(item.get("include")) != include:
                    continue
                if query_lc:
                    haystack = " ".join(
                        str(item.get(f, "")) for f in ("source_id", "title", "organization", "journal")
                    ).lower()
                    if query_lc not in haystack:
                        continue
                results.append(item)
        results.sort(key=lambda s: (s["tier"], -s["source_quality_score"], s.get("source_id", "")))
        return results

    def get_source(self, source_id: str) -> Dict[str, Any]:
        located = self._locate(source_id)
        if not located:
            raise SourceNotFoundError(f"source not found: {source_id}")
        _, _, source = located
        item = dict(source)
        item["tier"] = evidence_tier(item.get("evidence_class"))
        item["source_quality_score"] = screening_score(item)
        return item

    def exists(self, source_id: str) -> bool:
        return self._locate(source_id) is not None

    # ---- validation ------------------------------------------------------- #
    def _validate_or_raise(self, source: Dict[str, Any]) -> List[str]:
        issues: List[CatalogIssue] = validate_source(source)
        errors = [i.message for i in issues if i.severity == "error"]
        if errors:
            raise LibraryError(
                f"validation failed for '{source.get('source_id')}': " + "; ".join(errors)
            )
        return [i.message for i in issues if i.severity == "warning"]

    def _duplicate_identity(self, source: Dict[str, Any], ignore_id: Optional[str] = None) -> Optional[str]:
        target_hash = source_identity_hash(source)
        for existing in self.list_sources():
            if ignore_id and existing.get("source_id") == ignore_id:
                continue
            if source_identity_hash(existing) == target_hash:
                return str(existing.get("source_id"))
        return None

    # ---- write ------------------------------------------------------------ #
    def add_source(
        self, source: Dict[str, Any], *, overwrite: bool = False, skip_duplicate_check: bool = False
    ) -> MutationResult:
        """Add a new literature source to the writable catalog.

        Validates the entry, guards against duplicate ``source_id`` and
        duplicate identity (title/url/doi/pmid), appends it and rescreens.
        """

        source = _normalise_input(source)
        source_id = source.get("source_id")
        if not source_id:
            raise LibraryError("source_id is required")

        if self.exists(source_id) and not overwrite:
            raise DuplicateSourceError(f"source_id already exists: {source_id}")

        warnings = self._validate_or_raise(source)

        if not skip_duplicate_check:
            dup = self._duplicate_identity(source, ignore_id=source_id)
            if dup:
                raise DuplicateSourceError(
                    f"identical source already catalogued as '{dup}' (same title/url/doi/pmid)"
                )

        if self.exists(source_id) and overwrite:
            return self.update_source(source_id, source, replace=True)

        _append_entry(self.writable_catalog, source)
        files = self._rescreen()
        return MutationResult(source_id, "added", self.get_source(source_id), warnings, files)

    def update_source(
        self, source_id: str, patch: Dict[str, Any], *, replace: bool = False
    ) -> MutationResult:
        """Update an existing source (merge patch, or full replace)."""

        located = self._locate(source_id)
        if not located:
            raise SourceNotFoundError(f"source not found: {source_id}")
        path, index, current = located

        if replace:
            updated = _normalise_input(dict(patch))
            updated["source_id"] = source_id
        else:
            updated = dict(current)
            updated.update(_normalise_input(dict(patch), partial=True))
            updated["source_id"] = source_id

        warnings = self._validate_or_raise(updated)
        dup = self._duplicate_identity(updated, ignore_id=source_id)
        if dup:
            raise DuplicateSourceError(
                f"update would duplicate existing source '{dup}' (same title/url/doi/pmid)"
            )

        catalog = _load_catalog_file(path)
        catalog["sources"][index] = updated
        _write_catalog_file(path, catalog)
        files = self._rescreen()
        return MutationResult(source_id, "updated", self.get_source(source_id), warnings, files)

    def set_include(self, source_id: str, include: bool) -> MutationResult:
        """Soft enable/disable a source without deleting it (audit-friendly)."""

        result = self.update_source(source_id, {"include": bool(include)})
        result.action = "enabled" if include else "disabled"
        return result

    def remove_source(self, source_id: str, *, soft: bool = False) -> MutationResult:
        """Remove a source.

        ``soft=True`` sets ``include: false`` (kept for audit trail);
        ``soft=False`` deletes the entry from its catalog file.
        """

        if soft:
            return self.set_include(source_id, False)

        located = self._locate(source_id)
        if not located:
            raise SourceNotFoundError(f"source not found: {source_id}")
        path, index, removed = located
        catalog = _load_catalog_file(path)
        catalog["sources"].pop(index)
        _write_catalog_file(path, catalog)
        files = self._rescreen()
        return MutationResult(source_id, "removed", removed, [], files)

    # ---- recycle bin (soft delete) --------------------------------------- #
    def _load_trash(self) -> Dict[str, Any]:
        return _load_catalog_file(self.trash_catalog)

    def _locate_in_trash(self, source_id: str):
        trash = self._load_trash()
        for index, source in enumerate(trash.get("sources", [])):
            if str(source.get("source_id")) == source_id:
                return index, source
        return None

    def _fulltext(self):
        """Lazily import the full-text admin layer (optional integration)."""

        if not self.manage_fulltext:
            return None
        from app.services import fulltext_admin

        return fulltext_admin

    def trash_source(self, source_id: str, reason: Optional[str] = None) -> MutationResult:
        """Move a source into the recycle bin (soft delete, recoverable).

        The entry leaves the active catalog (so it drops out of screening and
        retrieval) and is appended to the trash catalog with restore metadata.
        Any attached full text is moved to the recycle bin too.
        """

        located = self._locate(source_id)
        if not located:
            raise SourceNotFoundError(f"source not found: {source_id}")
        path, index, source = located

        catalog = _load_catalog_file(path)
        catalog["sources"].pop(index)
        _write_catalog_file(path, catalog)

        entry = dict(source)
        entry["_trashed_at"] = date.today().isoformat()
        entry["_trashed_from"] = path
        if reason:
            entry["_trash_reason"] = reason
        trash = self._load_trash()
        trash.setdefault("sources", []).append(entry)
        _write_catalog_file(self.trash_catalog, trash)

        warnings: List[str] = []
        ft = self._fulltext()
        if ft is not None:
            try:
                ft.trash_fulltext(source_id)
            except Exception as exc:  # keep the catalog trash even if FT fails
                warnings.append(f"full-text trash skipped: {exc}")

        files = self._rescreen()
        return MutationResult(source_id, "trashed", entry, warnings, files)

    def list_trash(self) -> List[Dict[str, Any]]:
        """Return trashed sources (recoverable), annotated with tier/quality."""

        results: List[Dict[str, Any]] = []
        for source in self._load_trash().get("sources", []):
            item = dict(source)
            item["tier"] = evidence_tier(item.get("evidence_class"))
            item["source_quality_score"] = screening_score(item)
            results.append(item)
        results.sort(key=lambda s: s.get("_trashed_at", ""), reverse=True)
        return results

    def restore_source(self, source_id: str) -> MutationResult:
        """Restore a trashed source back into its original catalog file."""

        located = self._locate_in_trash(source_id)
        if not located:
            raise SourceNotFoundError(f"source not in recycle bin: {source_id}")
        if self.exists(source_id):
            raise DuplicateSourceError(f"active source already exists: {source_id}")
        index, entry = located

        origin = entry.get("_trashed_from")
        if origin not in self.catalog_files:
            origin = self.writable_catalog
        restored = {k: v for k, v in entry.items() if not k.startswith("_trash")}

        trash = self._load_trash()
        trash["sources"].pop(index)
        _write_catalog_file(self.trash_catalog, trash)

        catalog = _load_catalog_file(origin)
        catalog.setdefault("sources", []).append(restored)
        _write_catalog_file(origin, catalog)

        warnings: List[str] = []
        ft = self._fulltext()
        if ft is not None:
            try:
                ft.restore_fulltext(source_id)
            except Exception as exc:
                warnings.append(f"full-text restore skipped: {exc}")

        files = self._rescreen()
        return MutationResult(source_id, "restored", self.get_source(source_id), warnings, files)

    def purge_source(self, source_id: str) -> MutationResult:
        """Permanently delete a source from the recycle bin (irreversible)."""

        located = self._locate_in_trash(source_id)
        if not located:
            raise SourceNotFoundError(f"source not in recycle bin: {source_id}")
        index, entry = located
        trash = self._load_trash()
        trash["sources"].pop(index)
        _write_catalog_file(self.trash_catalog, trash)

        ft = self._fulltext()
        if ft is not None:
            try:
                ft.purge_fulltext(source_id)
            except Exception:
                pass
        return MutationResult(source_id, "purged", entry, [], {})

    def empty_trash(self) -> Dict[str, Any]:
        """Permanently delete every source in the recycle bin."""

        ids = [s.get("source_id") for s in self._load_trash().get("sources", [])]
        for source_id in ids:
            self.purge_source(source_id)
        return {"purged": len(ids), "source_ids": ids}

    # ---- rescreen / stats ------------------------------------------------- #
    def _rescreen(self) -> Dict[str, str]:
        if not self.auto_rescreen:
            return {}
        return write_screening_outputs()

    def rescreen(self) -> Dict[str, str]:
        """Force regeneration of the screening artefacts."""

        return write_screening_outputs()

    def stats(self) -> Dict[str, Any]:
        """Aggregate counts by tier / topic / region / include state."""

        sources = self.list_sources()
        included = [s for s in sources if s.get("include")]
        tier_counts = Counter(s["tier"] for s in included)
        return {
            "total": len(sources),
            "included": len(included),
            "excluded": len(sources) - len(included),
            "threshold": SCREEN_THRESHOLD,
            "by_tier": {
                tier: {
                    "label": TIER_LABELS[tier],
                    "count": tier_counts.get(tier, 0),
                    "evidence_classes": EVIDENCE_TIERS[tier],
                }
                for tier in EVIDENCE_TIERS
            },
            "by_topic": dict(Counter(s.get("topic") for s in included)),
            "by_evidence_class": dict(Counter(s.get("evidence_class") for s in included)),
            "by_region": dict(Counter(s.get("region") for s in included)),
            # Journal quality tier across ALL sources (incl. excluded) — the
            # signal for culling weaker papers. None = no journal (guidelines/web).
            "by_journal_tier": {
                str(t): sum(1 for s in sources if s.get("journal_tier") == t) for t in (1, 2, 3)
            },
            "no_journal_tier": sum(1 for s in sources if not s.get("journal_tier")),
        }

    def taxonomy(self) -> Dict[str, Any]:
        """Return the controlled vocabularies used to organise the library."""

        return {
            "tiers": {tier: {"label": TIER_LABELS[tier], "evidence_classes": classes} for tier, classes in EVIDENCE_TIERS.items()},
            "topics": sorted(EXPECTED_TOPICS | {"research_context", "disclaimer"}),
            "evidence_classes": sorted(ALLOWED_EVIDENCE_CLASSES),
            "allowed_uses": sorted(ALLOWED_USES),
            "screening_dimensions": list(_SCREENING_DIMS),
            "screen_threshold": SCREEN_THRESHOLD,
            "journal_tiers": {"1": "T1 · 顶刊", "2": "T2 · 主流", "3": "T3 · 较弱"},
        }


# --------------------------------------------------------------------------- #
# Input normalisation
# --------------------------------------------------------------------------- #
def _normalise_input(source: Dict[str, Any], *, partial: bool = False) -> Dict[str, Any]:
    """Coerce user-supplied source dicts into catalog shape.

    Fills sensible defaults for a full add; for ``partial`` patches only the
    provided keys are normalised.
    """

    source = dict(source)

    if "allowed_uses" in source and isinstance(source["allowed_uses"], str):
        source["allowed_uses"] = [u.strip() for u in source["allowed_uses"].split(",") if u.strip()]

    if "screening" in source and isinstance(source["screening"], dict):
        source["screening"] = {d: int(source["screening"].get(d, 0)) for d in _SCREENING_DIMS}

    if partial:
        return source

    source.setdefault("include", True)
    source.setdefault("language", "en")
    source.setdefault("doi", None)
    source.setdefault("pmid", None)
    source.setdefault("last_accessed", date.today())
    source.setdefault("access_note", "public")
    source.setdefault("screening", {d: 0 for d in _SCREENING_DIMS})
    return source
