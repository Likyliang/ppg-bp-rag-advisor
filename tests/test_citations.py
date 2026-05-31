from app.schemas.report import Evidence
from app.services.citations import build_registry


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
