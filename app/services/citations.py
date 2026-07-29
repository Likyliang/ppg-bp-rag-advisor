"""Citation engine: turn governed retrieval evidence into numbered, inline
academic-style references for the user report body.

Design goals
------------
* Deterministic, evidence-grounded numbering ([1], [2], ...), deduplicated at
  the *source* level: two chunks of the same guideline share one number, so the
  reference list never repeats an entry.
* Inline markers in the report body, mapped from a section's *allowed use*
  to the evidence that actually carries that use — so a citation only appears
  where the underlying source is licensed for that claim.
* A professional "参考文献" block with organization / title / class / region /
  year / locator (DOI > PMID > URL, plus page locators for fulltext passages).
* ``finalize``: after the body is assembled, citations are renumbered by order
  of first appearance and uncited entries are pruned from the reference list —
  the standard numeric (Vancouver-style) convention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from app.schemas.report import Evidence, ReferenceEntry


# Matches inline academic markers like [1], [2,5], [1, 3] in report bodies.
INLINE_CITE_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


def extract_citation_numbers(text: str) -> List[int]:
    """Return every citation number referenced inline in ``text`` (deduped, sorted)."""
    numbers: set[int] = set()
    for group in INLINE_CITE_RE.findall(text or ""):
        for part in group.split(","):
            part = part.strip()
            if part.isdigit():
                numbers.add(int(part))
    return sorted(numbers)


EVIDENCE_CLASS_LABELS = {
    "guideline": "临床指南",
    "official_health_education": "官方健康教育",
    "scientific_statement": "科学声明",
    "validation_standard": "设备验证标准",
    "review": "系统综述/综述",
    "safety_rule": "安全规则",
    "patient_education": "患者教育材料",
    "research_context": "研究背景文献",
}

REGION_LABELS = {
    "CN": "中国",
    "AHA": "美国（AHA/ACC）",
    "US": "美国",
    "EU": "欧洲",
    "global": "国际",
    "intl": "国际",
}


FULLTEXT_CHUNK_ID_RE = re.compile(r"^fulltext::(?P<source>[^:]+)::p(?P<page>\d+)::c\d+$")
SUMMARY_CHUNK_ID_RE = re.compile(r"^(?P<source>.+)_\d{3}$")


def _insert_marker_before_terminal(line: str, marker: str) -> str:
    """Place an inline marker before a trailing 。/；/！/？ (academic style).

    Appending after the full stop would produce the forbidden dangling pattern
    ``。 [n]``; numeric citations conventionally sit inside the sentence.
    """
    match = re.search(r"([。；！？]+)\s*$", line)
    if match:
        return line[: match.start()].rstrip() + marker + match.group(1)
    return line + marker


def source_key_for(item: Evidence) -> str:
    """Collapse chunk-level ids to the parent source for reference dedup."""
    source_id = item.source_id or ""
    fulltext = FULLTEXT_CHUNK_ID_RE.match(source_id)
    if fulltext:
        return fulltext.group("source")
    summary = SUMMARY_CHUNK_ID_RE.match(source_id)
    if summary:
        return summary.group("source")
    if source_id:
        return source_id
    return f"{item.title}|{item.organization}"


@dataclass
class FinalizedCitations:
    """Result of renumbering a finished body by first appearance."""

    body: str
    references: List[str] = field(default_factory=list)
    entries: List[ReferenceEntry] = field(default_factory=list)

    @property
    def cited_count(self) -> int:
        return len(self.entries)


class CitationRegistry:
    """Holds the ordered evidence and a use -> [citation numbers] index."""

    def __init__(self, evidence: List[Evidence]) -> None:
        self.evidence: List[Evidence] = evidence
        self.by_use: Dict[str, List[int]] = {}
        self.items_by_number: Dict[int, List[Evidence]] = {}
        number_by_source: Dict[str, int] = {}
        next_number = 1
        for item in evidence:
            key = source_key_for(item)
            number = number_by_source.get(key)
            if number is None:
                number = next_number
                number_by_source[key] = number
                next_number += 1
            item.citation_number = number
            self.items_by_number.setdefault(number, []).append(item)
            for use in item.allowed_uses or []:
                numbers = self.by_use.setdefault(use, [])
                if number not in numbers:
                    numbers.append(number)

    @property
    def has_evidence(self) -> bool:
        return bool(self.evidence)

    def numbers_for(self, uses: Iterable[str]) -> List[int]:
        seen: List[int] = []
        for use in uses:
            for number in self.by_use.get(use, []):
                if number not in seen:
                    seen.append(number)
        return sorted(seen)

    def cite(self, *uses: str, limit: int = 3) -> str:
        """Return an inline marker like ` [1,3]` (with a leading space) or ''."""
        numbers = self.numbers_for(uses)[:limit]
        if not numbers:
            return ""
        return " [" + ",".join(str(n) for n in numbers) + "]"

    def numbers_for_sources(self, source_ids: Iterable[str]) -> List[int]:
        """Citation numbers for specific governed sources (by source_id), if present."""
        wanted = {sid for sid in source_ids if sid}
        seen: List[int] = []
        for item in self.evidence:
            if item.citation_number is None:
                continue
            if source_key_for(item) in wanted and item.citation_number not in seen:
                seen.append(item.citation_number)
        return sorted(seen)

    def cite_sources(self, *source_ids: str, limit: int = 3) -> str:
        """Inline marker citing specific sources by id (or '' if none retrieved).

        Unlike ``cite`` (which maps an allowed-use to whatever evidence carries
        it), this cites the *exact* governed sources that back a claim — so a
        screening suggestion can only ever cite the paper that actually supports
        its feature→condition association, never an unrelated source.
        """
        numbers = self.numbers_for_sources(source_ids)[:limit]
        if not numbers:
            return ""
        return " [" + ",".join(str(n) for n in numbers) + "]"

    def _locator(self, item: Evidence) -> str:
        if item.doi:
            return f"DOI: {item.doi}"
        if item.pmid:
            return f"PMID: {item.pmid}"
        if item.url:
            return item.url
        return "来源存档于本地治理知识库"

    def _pages_for_number(self, number: int) -> str:
        """Page locator like ``p.7`` / ``pp.7,12`` for fulltext passage chunks."""
        pages: List[int] = []
        for item in self.items_by_number.get(number, []):
            match = FULLTEXT_CHUNK_ID_RE.match(item.source_id or "")
            if match:
                page = int(match.group("page"))
                if page not in pages:
                    pages.append(page)
        if not pages:
            return ""
        pages.sort()
        if len(pages) == 1:
            return f"p.{pages[0]}"
        return "pp." + ",".join(str(page) for page in pages)

    def _format_entry(self, item: Evidence, number: Optional[int] = None, pages_key: Optional[int] = None) -> str:
        parts: List[str] = []
        if item.organization:
            parts.append(item.organization.rstrip("。."))
        title = item.title or "未命名来源"
        class_label = EVIDENCE_CLASS_LABELS.get(item.evidence_class or "", item.evidence_class or "")
        title_block = f"{title}[{class_label}]" if class_label else title
        parts.append(title_block)
        region_year = []
        region_label = REGION_LABELS.get(item.region or "", item.region or "")
        if region_label:
            region_year.append(region_label)
        if item.year:
            region_year.append(str(item.year))
        if region_year:
            parts.append("，".join(region_year))
        locator = self._locator(item)
        # ``pages_key`` indexes the (possibly still-old-numbered) items_by_number;
        # finalize passes the OLD number here so page locators stay attached to
        # the right source while ``number`` shows the renumbered citation.
        page_lookup = pages_key if pages_key is not None else (number if number is not None else (item.citation_number or 0))
        pages = self._pages_for_number(page_lookup)
        if pages:
            locator = f"{locator} ({pages})"
        parts.append(locator)
        display_number = number if number is not None else item.citation_number
        return f"[{display_number}] " + ". ".join(parts) + "."

    def _representative(self, number: int) -> Optional[Evidence]:
        items = self.items_by_number.get(number, [])
        return items[0] if items else None

    def references_markdown(self) -> List[str]:
        lines: List[str] = []
        for number in sorted(self.items_by_number):
            item = self._representative(number)
            if item is not None:
                lines.append(self._format_entry(item, number=number))
        return lines

    def references_markdown_entries(self) -> List[ReferenceEntry]:
        """Structured reference entries for ALL evidence in source-dedup order.

        Used by the citation-enforcement-OFF path (no first-appearance
        renumbering / pruning): the body keeps its raw [n], so the reference
        list must keep the registry's original numbering.
        """
        entries: List[ReferenceEntry] = []
        for number in sorted(self.items_by_number):
            item = self._representative(number)
            if item is None:
                continue
            entries.append(
                ReferenceEntry(
                    number=number,
                    source_id=source_key_for(item),
                    title=item.title,
                    organization=item.organization,
                    year=item.year,
                    evidence_class=item.evidence_class,
                    locator=self._locator(item),
                    url=item.url,
                    pages=self._pages_for_number(number) or None,
                    snippet=item.snippet,
                    formatted=self._format_entry(item, number=number),
                )
            )
        return entries

    # ------------------------------------------------------------------ repair

    @property
    def max_number(self) -> int:
        return len(self.items_by_number)

    def strip_invalid_markers(self, text: str) -> str:
        """Remove inline markers whose numbers exceed the evidence count.

        An LLM may hallucinate ``[9]`` when only 6 sources exist. We drop the
        whole bracket group if *any* member is out of range, leaving prose intact.
        """
        if not text:
            return text

        def _repl(match: "re.Match[str]") -> str:
            parts = [p.strip() for p in match.group(1).split(",")]
            if all(p.isdigit() and 1 <= int(p) <= self.max_number for p in parts):
                return match.group(0)
            return ""

        cleaned = INLINE_CITE_RE.sub(_repl, text)
        # Collapse whitespace left where a marker was removed mid-sentence.
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\s+([。，、；：！？])", r"\1", cleaned)
        return cleaned

    def enforce_section_citations(self, body: str) -> str:
        """Guarantee that key sections carry at least one valid inline ``[n]``.

        For each `## / ###` section heading we recognise, if the section's body
        has no inline marker we append the registry's use-mapped marker to the
        first substantive line. This is deterministic and only uses real
        evidence numbers, so the body can never claim a citation that the
        reference list does not back.
        """
        if not self.has_evidence:
            return body

        # heading keyword -> uses to cite for that section
        section_uses = {
            "先看结论": ("bp_category_reference", "cuffless_ppg_limitations"),
            "现在最该做什么": ("remeasurement", "home_bp_monitoring", "device_advice"),
            "为什么这样提醒你": ("bp_category_reference", "cuffless_ppg_limitations"),
            "怎么看这次测量": ("signal_quality", "cuffless_ppg_limitations"),
            "建议背后的原因": ("bp_category_reference", "lifestyle"),
            "复测与记录": ("remeasurement", "home_bp_monitoring", "signal_quality"),
            "设备复核": ("device_advice", "cuffless_ppg_limitations"),
            "生活方式": ("lifestyle",),
            "就医沟通": ("home_bp_monitoring", "special_population", "emergency_alert"),
            "几个容易误解的点": ("cuffless_ppg_limitations", "signal_quality"),
            "可能存在紧急风险": ("emergency_alert",),
        }

        lines = body.splitlines()
        # Identify section spans by heading lines.
        heading_idx = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("#")]
        spans = []
        for pos, start in enumerate(heading_idx):
            end = heading_idx[pos + 1] if pos + 1 < len(heading_idx) else len(lines)
            spans.append((start, end))

        for start, end in spans:
            heading = lines[start]
            uses = next((u for kw, u in section_uses.items() if kw in heading), None)
            if not uses:
                continue
            marker = self.cite(*uses)
            if not marker:
                continue
            block = "\n".join(lines[start:end])
            if extract_citation_numbers(block):
                continue  # section already cited
            # Find first substantive content line (bullet or paragraph) to tag.
            target = None
            for i in range(start + 1, end):
                stripped = lines[i].strip()
                if not stripped:
                    continue
                if stripped.startswith("#"):
                    break
                target = i
                break
            if target is None:
                continue
            lines[target] = _insert_marker_before_terminal(lines[target].rstrip(), marker)
        return "\n".join(lines)

    def body_is_consistent(self, body: str) -> bool:
        """True iff the body carries >=1 valid inline marker, none out of range."""
        numbers = extract_citation_numbers(body)
        if not numbers:
            return False
        return all(1 <= n <= self.max_number for n in numbers)

    # ---------------------------------------------------------------- finalize

    def _appearance_order(self, body: str) -> List[int]:
        order: List[int] = []
        for match in INLINE_CITE_RE.finditer(body or ""):
            for part in match.group(1).split(","):
                part = part.strip()
                if part.isdigit():
                    number = int(part)
                    if 1 <= number <= self.max_number and number not in order:
                        order.append(number)
        return order

    def finalize(self, body: str) -> FinalizedCitations:
        """Renumber inline markers by first appearance and prune uncited refs.

        This is the standard numeric-citation convention: [1] is the first
        source cited in the text, and the reference list contains exactly the
        cited sources in citation order. Evidence items keep their final
        number (or ``None`` when their source ended up uncited).
        """
        body = self.strip_invalid_markers(body or "")
        order = self._appearance_order(body)
        renumber = {old: new for new, old in enumerate(order, start=1)}

        def _rewrite(match: "re.Match[str]") -> str:
            numbers: List[int] = []
            for part in match.group(1).split(","):
                part = part.strip()
                if part.isdigit():
                    mapped = renumber.get(int(part))
                    if mapped is not None and mapped not in numbers:
                        numbers.append(mapped)
            if not numbers:
                return ""
            return "[" + ",".join(str(n) for n in sorted(numbers)) + "]"

        new_body = INLINE_CITE_RE.sub(_rewrite, body)

        references: List[str] = []
        entries: List[ReferenceEntry] = []
        for old_number in order:
            new_number = renumber[old_number]
            item = self._representative(old_number)
            if item is None:
                continue
            references.append(self._format_entry(item, number=new_number, pages_key=old_number))
            entries.append(
                ReferenceEntry(
                    number=new_number,
                    source_id=source_key_for(item),
                    title=item.title,
                    organization=item.organization,
                    year=item.year,
                    evidence_class=item.evidence_class,
                    locator=self._locator(item),
                    url=item.url,
                    pages=self._pages_for_number(old_number) or None,
                    snippet=item.snippet,
                    formatted=self._format_entry(item, number=new_number, pages_key=old_number),
                )
            )
        # Re-stamp evidence items with their final numbers.
        for item in self.evidence:
            old = item.citation_number
            item.citation_number = renumber.get(old) if old is not None else None
        # Keep the internal indexes coherent with the new numbering so later
        # cite()/references_markdown() calls (if any) stay valid.
        self.items_by_number = {}
        for item in self.evidence:
            if item.citation_number is not None:
                self.items_by_number.setdefault(item.citation_number, []).append(item)
        self.by_use = {}
        for item in self.evidence:
            if item.citation_number is None:
                continue
            for use in item.allowed_uses or []:
                numbers = self.by_use.setdefault(use, [])
                if item.citation_number not in numbers:
                    numbers.append(item.citation_number)
        return FinalizedCitations(body=new_body, references=references, entries=entries)


def build_registry(evidence: Optional[Iterable[Evidence]]) -> CitationRegistry:
    return CitationRegistry(list(evidence or []))
