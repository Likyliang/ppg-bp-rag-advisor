from app.schemas.report import Evidence
from app.services.citations import build_registry, extract_citation_numbers


def _ev(**kw):
    base = dict(source_id="s", title="T", used_for="x", allowed_uses=[])
    base.update(kw)
    return Evidence(**base)


def test_registry_numbers_and_inline_cite():
    ev = [
        _ev(source_id="a", title="指南A", organization="机构A",
            evidence_class="guideline", region="CN", year="2024", url="http://a",
            allowed_uses=["bp_category_reference", "lifestyle"]),
        _ev(source_id="b", title="综述B", organization="机构B",
            evidence_class="review", region="global", year="2020", doi="10.1/x",
            allowed_uses=["cuffless_ppg_limitations"]),
    ]
    reg = build_registry(ev)
    assert ev[0].citation_number == 1
    assert ev[1].citation_number == 2
    assert reg.cite("bp_category_reference") == " [1]"
    assert reg.cite("cuffless_ppg_limitations") == " [2]"
    assert reg.cite("bp_category_reference", "cuffless_ppg_limitations") == " [1,2]"
    assert reg.cite("nonexistent_use") == ""
    refs = reg.references_markdown()
    assert refs[0] == "[1] 机构A. 指南A[临床指南]. 中国，2024. http://a."
    assert "DOI: 10.1/x" in refs[1]


def test_cite_limit_caps_number_of_markers():
    ev = [_ev(source_id=str(i), allowed_uses=["lifestyle"]) for i in range(5)]
    reg = build_registry(ev)
    assert reg.cite("lifestyle") == " [1,2,3]"


def test_empty_registry_is_safe():
    reg = build_registry([])
    assert reg.has_evidence is False
    assert reg.cite("bp_category_reference") == ""
    assert reg.references_markdown() == []


def test_extract_citation_numbers():
    assert extract_citation_numbers("结论[1]，建议[2,3]，再看[3]") == [1, 2, 3]
    assert extract_citation_numbers("没有引用") == []
    assert extract_citation_numbers("混合 [1, 5] 与 [2]") == [1, 2, 5]


def test_strip_invalid_markers_drops_out_of_range_only():
    ev = [_ev(source_id=str(i), allowed_uses=["lifestyle"]) for i in range(3)]
    reg = build_registry(ev)  # valid numbers: 1..3
    text = "正常[2]，越界[9]，组合越界[1,9]，组合合法[1,3]。"
    out = reg.strip_invalid_markers(text)
    assert "[2]" in out
    assert "[1,3]" in out
    assert "[9]" not in out
    assert "[1,9]" not in out


def test_enforce_section_citations_injects_when_missing():
    ev = [
        _ev(source_id="a", allowed_uses=["bp_category_reference"]),
        _ev(source_id="b", allowed_uses=["lifestyle"]),
        _ev(source_id="c", allowed_uses=["cuffless_ppg_limitations"]),
    ]
    reg = build_registry(ev)
    body = (
        "## 先看结论\n这次估算值偏高。\n\n"
        "## 生活方式\n- 减少钠盐摄入。\n"
    )
    out = reg.enforce_section_citations(body)
    # 先看结论 cites both its mapped uses: bp_category_reference(1)+cuffless(3) => [1,3]
    assert "这次估算值偏高。 [1,3]" in out
    # 生活方式 -> lifestyle => [2]
    assert "减少钠盐摄入。 [2]" in out


def test_enforce_section_citations_leaves_existing_cite():
    ev = [_ev(source_id="a", allowed_uses=["bp_category_reference"])]
    reg = build_registry(ev)
    body = "## 先看结论\n这次估算值偏高[1]。\n"
    out = reg.enforce_section_citations(body)
    assert out.count("[1]") == 1  # not doubled


def test_body_is_consistent():
    ev = [_ev(source_id=str(i), allowed_uses=["lifestyle"]) for i in range(3)]
    reg = build_registry(ev)
    assert reg.body_is_consistent("结论[1]，建议[2,3]") is True
    assert reg.body_is_consistent("没有引用") is False
    assert reg.body_is_consistent("越界[9]") is False
