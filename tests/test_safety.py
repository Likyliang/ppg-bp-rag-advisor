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
    "可以自行加药或减药。",
    "不要自己改药。",
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


def test_emergency_safety_accepts_120_or_er_in_opening():
    class EmergencyRule:
        emergency = True

    review = review_safety(
        "## 可能存在紧急风险\n请立即拨打120或前往最近医院急诊。不要等待小程序复测结果。"
        "\n\nPPG 估算值仅供个人健康趋势参考，不能替代医生诊断，不能替代规范血压测量。",
        EmergencyRule(),
    )
    assert review.passed is True


def test_generated_report_passes_safety_review():
    report = generate_report({"estimated_sbp": 145, "estimated_dbp": 92, "signal_quality_score": 0.86})
    assert report.safety_review is not None
    assert report.safety_review.passed is True
    assert "仅供个人健康趋势参考" in report.markdown_report
    assert "不能替代医生诊断" in report.disclaimer
    assert "## 为什么这样提醒你" in report.markdown_report
    assert "属于“处于明显偏高范围参考值”" in report.markdown_report
    assert "## 建议背后的原因" in report.markdown_report
    assert "## 现在最该做什么" in report.markdown_report
    assert "结论：这次数值明显偏高" in report.markdown_report
    assert "先别给自己下诊断" in report.markdown_report
    assert "社区、乡镇卫生院或门诊咨询" in report.markdown_report
    assert "## 在国内可以怎么做" in report.markdown_report
    assert "## 几个容易误解的点" in report.markdown_report
    assert "社区卫生服务中心" in report.markdown_report
    assert "PPG 可以理解为用手指摄像头的光信号来估算血压趋势" in report.markdown_report
    assert "当前按中国大陆常见健康管理语境" not in report.markdown_report
    assert "优先参考国家卫健委" not in report.markdown_report
    assert "本报告参考了国家卫健委" not in report.markdown_report
    assert "未触发本系统急症提醒规则" not in report.markdown_report
    assert "急症提醒规则" not in report.markdown_report
    assert "CN_stage" not in report.markdown_report
    assert "读数触发" not in report.markdown_report


def test_low_quality_report_explains_remeasurement_first():
    report = generate_report(
        {
            "estimated_sbp": 149,
            "estimated_dbp": 94,
            "signal_quality_score": 0.44,
            "confidence": 0.42,
            "capture_duration_sec": 12,
        }
    )
    assert report.safety_review.passed is True
    assert "因信号质量不足，本次不做范围解释" in report.markdown_report
    assert "本次质量不足，所以报告不展开血压范围解释" in report.markdown_report
    assert "### 生活方式" not in report.markdown_report


def test_special_population_report_mentions_user_factors_without_drug_changes():
    report = generate_report(
        {
            "estimated_sbp": 141,
            "estimated_dbp": 88,
            "signal_quality_score": 0.86,
            "age": 70,
            "diabetes": True,
            "kidney_disease": True,
            "antihypertensive_medication": True,
        }
    )
    assert report.safety_review.passed is True
    assert "年龄：70 岁，属于更保守解释人群" in report.markdown_report
    assert "糖尿病、慢性肾脏病、正在使用降压药" in report.markdown_report
    assert "不给药物处理方案" in report.markdown_report


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
    assert "120" in report.markdown_report
    assert report.safety_review.passed is True


def test_china_context_uses_local_primary_care_path():
    report = generate_report(
        {
            "estimated_sbp": 145,
            "estimated_dbp": 92,
            "signal_quality_score": 0.86,
            "province": "广东",
            "residence_area": "rural",
            "primary_care_preference": "township_health_center",
        }
    )
    assert report.safety_review.passed is True
    assert "地区：广东" in report.markdown_report
    assert "乡镇卫生院" in report.markdown_report
    assert "中国使用场景" in report.markdown_report
