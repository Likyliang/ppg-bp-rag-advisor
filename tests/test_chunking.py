from app.services.chunking import (
    build_embedding_text,
    chunk_markdown_note,
    chunk_text,
    parse_note_sections,
    split_sentences,
    tokenize_for_match,
)


def test_tokenizer_emits_cjk_bigrams_not_single_chars():
    tokens = tokenize_for_match("高血压指南 BP guideline 2024")
    assert "高血" in tokens and "血压" in tokens and "压指" in tokens
    assert "高" not in tokens  # no lone CJK chars for multi-char runs
    assert "guideline" in tokens and "2024" in tokens


def test_split_sentences_respects_zh_and_en_boundaries():
    text = "先休息5分钟。再测一次！数值仍高吗？Take a rest. Then measure again."
    units = split_sentences(text)
    assert "先休息5分钟。" in units
    assert "再测一次！" in units
    assert "Take a rest." in units
    # decimal points must not split: 1.5 stays intact
    assert any("1.5" in unit for unit in split_sentences("信号质量 1.5 分。"))


def test_chunk_text_overlaps_on_sentence_boundaries():
    sentence = "家庭血压监测有助于判断趋势，建议安静休息后规范测量并连续记录。"
    text = sentence * 20
    chunks = chunk_text(text, target_chars=120, min_chars=40, overlap_chars=40)
    assert len(chunks) > 2
    # every chunk starts at a sentence start (no mid-sentence cuts)
    assert all(chunk.startswith("家庭血压监测") for chunk in chunks)
    # no degenerate tail
    assert all(len(chunk) >= 40 for chunk in chunks)


def test_chunk_markdown_note_separates_governance_from_content():
    note = (
        "## 来源摘要\n\n这是一段实质摘要内容，解释来源的核心观点。\n\n"
        "## 可用于报告的要点\n\n- 要点一：规范测量。\n- 要点二：连续记录。\n\n"
        "## 安全边界\n\n- 该来源只用于健康教育，不用于诊断。\n\n"
        "## 实现使用说明\n\n- 仅用于 lifestyle 用途。\n"
    )
    chunks = chunk_markdown_note(note)
    roles = {chunk.section_role for chunk in chunks}
    assert roles == {"content", "governance"}
    content_chunks = [chunk for chunk in chunks if chunk.section_role == "content"]
    governance_chunks = [chunk for chunk in chunks if chunk.section_role == "governance"]
    # substantive sections merged into one coherent chunk, not per-heading shards
    assert len(content_chunks) == 1
    assert "实质摘要" in content_chunks[0].text and "要点二" in content_chunks[0].text
    assert all("安全边界" in chunk.section_title or "实现使用说明" in chunk.section_title for chunk in governance_chunks)


def test_parse_note_sections_reads_full_heading():
    sections = parse_note_sections("## 可用于报告的要点\n\n- 内容。\n")
    assert sections[0].title == "可用于报告的要点"


def test_build_embedding_text_prefixes_context():
    text = build_embedding_text(
        {"title": "Guide", "topic": "lifestyle", "section_title": "要点", "allowed_uses": ["lifestyle"]},
        "减少钠盐摄入。",
    )
    assert text.startswith("Guide 要点 lifestyle lifestyle")
    assert text.endswith("减少钠盐摄入。")
