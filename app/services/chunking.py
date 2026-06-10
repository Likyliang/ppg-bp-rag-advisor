"""Structure-aware chunking for the governed knowledge base.

Replaces the old paragraph-budget splitter, which emitted one fragment per
markdown section and produced a long tail of sub-100-char chunks: per-source
governance boilerplate (安全边界 / 实现使用说明) outnumbered substantive content
nearly 2:1 and polluted report retrieval.

Shared by the summary-note ingest (``scripts/ingest_kb.py``) and the fulltext
PDF ingest (``app/services/fulltext_vector_index.py``).

Key behaviours
--------------
* Markdown ``##`` sections are parsed with their headings and classified into a
  role: ``content`` (substantive, retrievable) or ``governance`` (per-source
  usage boilerplate that must stay auditable but must NOT compete in report
  retrieval).
* Substantive sections of one note are merged into coherent chunks around a
  target size instead of one fragment per heading.
* Long text splits on zh/en sentence boundaries with sentence-level overlap, so
  no chunk starts or ends mid-sentence.
* ``tokenize_for_match`` provides the shared zh-bigram / en-word tokenizer used
  by both keyword scoring and the offline hashing embedding, so query-time and
  index-time token spaces always agree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Tokenization (shared by retriever keyword scoring and hashing embeddings)
# ---------------------------------------------------------------------------

WORD_RE = re.compile(r"[A-Za-z0-9_]+")
CJK_RUN_RE = re.compile(r"[一-鿿]+")


def tokenize_for_match(text: str) -> List[str]:
    """Tokenize into lowercase EN words/numbers plus CJK character bigrams.

    Bigrams keep zh terms like 高血压 -> [高血, 血压] coherent instead of three
    independent single characters, which was the main source of false keyword
    matches in the old retriever. Single-character CJK runs are kept as-is.
    """
    tokens: List[str] = [word.lower() for word in WORD_RE.findall(text or "")]
    for run in CJK_RUN_RE.findall(text or ""):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


# ---------------------------------------------------------------------------
# Sentence-safe splitting
# ---------------------------------------------------------------------------

# Split after zh terminal punctuation, or after en terminal punctuation that is
# followed by whitespace (so "1.5" or "e.g." survive), keeping bullets intact.
_ZH_SENTENCE_END = re.compile(r"(?<=[。！？；])")
_EN_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+")


def split_sentences(text: str) -> List[str]:
    """Split text into sentence-ish units without breaking inside a sentence.

    Lines are treated as hard boundaries first (so markdown bullets stay whole
    units), then each line is split on zh/en sentence-ending punctuation.
    """
    units: List[str] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        for part in _EN_SENTENCE_END.split(line):
            for sentence in _ZH_SENTENCE_END.split(part):
                sentence = sentence.strip()
                if sentence:
                    units.append(sentence)
    return units


def _split_oversize_sentence(sentence: str, hard_max: int) -> List[str]:
    """Break a pathological sentence on clause punctuation, then hard-cut."""
    if len(sentence) <= hard_max:
        return [sentence]
    clauses = re.split(r"(?<=[，、,;；:：])", sentence)
    pieces: List[str] = []
    current = ""
    for clause in clauses:
        if len(current) + len(clause) > hard_max and current:
            pieces.append(current)
            current = clause
        else:
            current += clause
    if current:
        pieces.append(current)
    # Any clause still over hard_max gets a raw cut as the last resort.
    final: List[str] = []
    for piece in pieces:
        while len(piece) > hard_max:
            final.append(piece[:hard_max])
            piece = piece[hard_max:]
        if piece:
            final.append(piece)
    return final


def chunk_text(
    text: str,
    target_chars: int = 600,
    min_chars: int = 150,
    overlap_chars: int = 80,
    hard_max_chars: int = 900,
) -> List[str]:
    """Accumulate whole sentences into chunks of roughly ``target_chars``.

    * Overlap is sentence-level: the next chunk re-opens with the trailing
      sentences of the previous one (up to ``overlap_chars``), never a raw
      character slice that starts mid-word.
    * A trailing fragment shorter than ``min_chars`` is merged back into the
      previous chunk instead of being emitted as a degenerate chunk.
    """
    sentences: List[str] = []
    for unit in split_sentences(text):
        sentences.extend(_split_oversize_sentence(unit, hard_max_chars))
    if not sentences:
        return []

    chunks: List[List[str]] = []
    current: List[str] = []
    current_len = 0
    for sentence in sentences:
        sep = 1 if current else 0
        if current and current_len + sep + len(sentence) > target_chars and current_len >= min_chars:
            chunks.append(current)
            overlap: List[str] = []
            if overlap_chars > 0:
                used = 0
                for prev in reversed(current):
                    if used + len(prev) > overlap_chars:
                        break
                    overlap.insert(0, prev)
                    used += len(prev)
            current = list(overlap)
            current_len = sum(len(s) for s in current) + max(len(current) - 1, 0)
        current.append(sentence)
        current_len += len(sentence) + (1 if current_len else 0)
    if current:
        chunks.append(current)

    rendered = [" ".join(chunk).strip() for chunk in chunks]
    rendered = [chunk for chunk in rendered if chunk]
    if len(rendered) >= 2 and len(rendered[-1]) < min_chars:
        tail = rendered.pop()
        # Avoid re-appending pure overlap echo of the previous chunk.
        if tail not in rendered[-1]:
            rendered[-1] = f"{rendered[-1]} {tail}".strip()
    return rendered


# ---------------------------------------------------------------------------
# Markdown note parsing (governed source notes)
# ---------------------------------------------------------------------------

GOVERNANCE_HEADING_MARKERS: Tuple[str, ...] = (
    "安全边界",
    "实现使用说明",
    "全文候选与下载材料摘要",
    "治理说明",
    "使用限制",
)

SECTION_ROLE_CONTENT = "content"
SECTION_ROLE_GOVERNANCE = "governance"


@dataclass
class NoteSection:
    title: str
    role: str
    text: str


@dataclass
class NoteChunk:
    text: str
    section_title: str
    section_role: str


def _classify_heading(title: str) -> str:
    cleaned = title.strip()
    for marker in GOVERNANCE_HEADING_MARKERS:
        if marker in cleaned:
            return SECTION_ROLE_GOVERNANCE
    return SECTION_ROLE_CONTENT


def parse_note_sections(content: str) -> List[NoteSection]:
    """Split a governed markdown note into titled, role-classified sections."""
    sections: List[NoteSection] = []
    blocks = re.split(r"\n(?=#{1,3}\s+)", (content or "").strip())
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        heading_match = re.match(r"^(#{1,3})\s+([^\n]+)", block)
        if heading_match:
            title = heading_match.group(2).strip()
            body = block[heading_match.end() :].strip()
        else:
            title = ""
            body = block
        if not body:
            # A bare heading with no body carries no retrievable text.
            continue
        sections.append(NoteSection(title=title, role=_classify_heading(title), text=body))
    return sections


def _emit_section_group(
    group: List[NoteSection],
    role: str,
    target_chars: int,
    min_chars: int,
    overlap_chars: int,
) -> List[NoteChunk]:
    if not group:
        return []
    titles: List[str] = []
    for section in group:
        if section.title and section.title not in titles:
            titles.append(section.title)
    joined_title = " / ".join(titles[:3])
    if len(joined_title) > 60:
        joined_title = joined_title[:57] + "..."
    merged_text = "\n".join(f"{section.title}：{section.text}" if section.title else section.text for section in group)
    pieces = chunk_text(
        merged_text,
        target_chars=target_chars,
        min_chars=min_chars,
        overlap_chars=overlap_chars,
    )
    return [NoteChunk(text=piece, section_title=joined_title, section_role=role) for piece in pieces]


def chunk_markdown_note(
    content: str,
    target_chars: int = 700,
    min_chars: int = 120,
    overlap_chars: int = 80,
) -> List[NoteChunk]:
    """Chunk one governed source note with section-role awareness.

    Substantive sections (来源摘要 / 可用于报告的要点 / anything else) are merged
    into coherent ``content`` chunks; governance boilerplate sections are merged
    into separate ``governance`` chunks that stay in the JSONL for audit but are
    excluded from default report retrieval.
    """
    chunks: List[NoteChunk] = []
    content_group: List[NoteSection] = []
    governance_group: List[NoteSection] = []
    for section in parse_note_sections(content):
        if section.role == SECTION_ROLE_GOVERNANCE:
            governance_group.append(section)
        else:
            content_group.append(section)
    chunks.extend(
        _emit_section_group(content_group, SECTION_ROLE_CONTENT, target_chars, min_chars, overlap_chars)
    )
    chunks.extend(
        _emit_section_group(governance_group, SECTION_ROLE_GOVERNANCE, target_chars, min_chars, overlap_chars)
    )
    return chunks


def build_embedding_text(metadata: Dict[str, object], content: str) -> str:
    """Compose the text actually embedded/scored for a chunk.

    Prefixing title/topic/uses gives short summary chunks enough lexical
    context to match topical queries, which matters for both the hashing
    embedding and remote embedding providers.
    """
    title = str(metadata.get("title") or "").strip()
    topic = str(metadata.get("topic") or "").strip()
    section = str(metadata.get("section_title") or "").strip()
    uses = metadata.get("allowed_uses") or []
    if isinstance(uses, str):
        uses_text = uses
    else:
        uses_text = " ".join(str(use) for use in uses)
    prefix = " ".join(part for part in (title, section, topic, uses_text) if part)
    return f"{prefix}\n{content}" if prefix else content
