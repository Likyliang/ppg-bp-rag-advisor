"""Citation engine: turn governed retrieval evidence into numbered, inline
academic-style references for the user report body.

Design goals
------------
* Deterministic, evidence-grounded numbering ([1], [2], ...).
* Inline markers in the report body, mapped from a section's *allowed use*
  to the evidence that actually carries that use — so a citation only appears
  where the underlying source is licensed for that claim.
* A professional "参考文献" block with organization / title / class / region /
  year / locator (DOI > PMID > URL), instead of a flat bullet dump.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

from app.schemas.report import Evidence


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


class CitationRegistry:
    """Holds the ordered evidence and a use -> [citation numbers] index."""

    def __init__(self, evidence: List[Evidence]) -> None:
        self.evidence: List[Evidence] = evidence
        self.by_use: Dict[str, List[int]] = {}
        for position, item in enumerate(evidence, start=1):
            item.citation_number = position
            for use in item.allowed_uses or []:
                self.by_use.setdefault(use, []).append(position)

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

    def _locator(self, item: Evidence) -> str:
        if item.doi:
            return f"DOI: {item.doi}"
        if item.pmid:
            return f"PMID: {item.pmid}"
        if item.url:
            return item.url
        return "来源存档于本地治理知识库"

    def _format_entry(self, item: Evidence) -> str:
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
        parts.append(self._locator(item))
        return f"[{item.citation_number}] " + ". ".join(parts) + "."

    def references_markdown(self) -> List[str]:
        return [self._format_entry(item) for item in self.evidence]

    # ------------------------------------------------------------------ repair

    @property
    def max_number(self) -> int:
        return len(self.evidence)

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
            lines[target] = lines[target].rstrip() + marker
        return "\n".join(lines)

    def body_is_consistent(self, body: str) -> bool:
        """True iff the body carries >=1 valid inline marker, none out of range."""
        numbers = extract_citation_numbers(body)
        if not numbers:
            return False
        return all(1 <= n <= self.max_number for n in numbers)


def build_registry(evidence: Optional[Iterable[Evidence]]) -> CitationRegistry:
    return CitationRegistry(list(evidence or []))
