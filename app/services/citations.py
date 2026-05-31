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

from typing import Dict, Iterable, List, Optional

from app.schemas.report import Evidence


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


def build_registry(evidence: Optional[Iterable[Evidence]]) -> CitationRegistry:
    return CitationRegistry(list(evidence or []))
