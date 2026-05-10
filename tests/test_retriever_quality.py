from app.services.retriever import retrieve_knowledge
from app.services.source_catalog import HIGH_TRUST_EVIDENCE_CLASSES


def test_lifestyle_query_returns_official_lifestyle_evidence():
    result = retrieve_knowledge(["减少钠盐 规律运动 体重管理 血压 生活方式"], top_k=5)
    assert result.evidence
    assert any("lifestyle" in item.allowed_uses for item in result.evidence)
    assert any(item.organization in {"American Heart Association", "Centers for Disease Control and Prevention"} for item in result.evidence)


def test_emergency_query_uses_high_trust_sources_only():
    result = retrieve_knowledge(["185/122 胸痛 气短 需要急救吗"], top_k=5)
    assert result.evidence
    assert all("emergency_alert" in item.allowed_uses for item in result.evidence)
    assert all(item.evidence_class in HIGH_TRUST_EVIDENCE_CLASSES for item in result.evidence)


def test_medication_query_does_not_return_lifestyle_only_sources():
    result = retrieve_knowledge(["正在使用降压药 PPG 血压偏高 要停药吗"], top_k=5)
    assert result.evidence
    assert all("medication_safety" in item.allowed_uses for item in result.evidence)
    assert all("lifestyle" not in item.allowed_uses or "medication_safety" in item.allowed_uses for item in result.evidence)
