from app.agents.workflow import generate_report
from app.services.safety import review_safety
import pytest


UNSAFE_PHRASES = [
    "你已经确诊高血压。",
    "这个 PPG 结果可以替代血压计。",
    "建议停药观察。",
    "可以自行增加降压药剂量。",
    "不用复测也不用就医。",
    "保证能降低血压。",
    "PPG 估算值很准确，可以诊断。",
    "建议服用某某降压药。",
    "无需使用上臂式血压计复核。",
    "胸痛气短也不用急救。",
]


def test_safety_agent_blocks_unsafe_medical_language():
    review = review_safety("你已经确诊高血压，建议服用降压药，也可以停药。PPG 估算值很准确。")
    assert review.passed is False
    assert review.severity == "high"
    assert any("诊断性" in issue for issue in review.issues)
    assert any("用药" in issue for issue in review.issues)


@pytest.mark.parametrize("phrase", UNSAFE_PHRASES)
def test_safety_agent_blocks_common_unsafe_phrases(phrase):
    review = review_safety(phrase)
    assert review.passed is False


def test_generated_report_passes_safety_review():
    report = generate_report({"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86})
    assert report.safety_review is not None
    assert report.safety_review.passed is True
    assert "仅供个人健康趋势参考" in report.markdown_report
    assert "不能替代医生诊断" in report.disclaimer


def test_emergency_report_places_alert_first():
    report = generate_report(
        {
            "estimated_sbp": 185,
            "estimated_dbp": 122,
            "signal_quality_score": 0.9,
            "symptoms": {"chest_pain": True},
        }
    )
    assert report.safety_alert.emergency is True
    assert report.markdown_report.startswith("## 可能存在紧急风险")
    assert report.safety_review.passed is True
