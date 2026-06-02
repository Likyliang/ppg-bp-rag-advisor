"""Unit tests for the medical copy editorial sanitizer."""

from app.services.medical_copy import sanitize_medical_copy


class _RR:
    def __init__(self, emergency=False):
        self.emergency = emergency


# 1. Wrong words ------------------------------------------------------------

def test_wrong_word_pharmacist_garble_is_fixed():
    assert sanitize_medical_copy("建议休息后用药师（上臂式血压计）复核") == "建议休息后用上臂式血压计复核"
    assert sanitize_medical_copy("用药师（血压计）复核") == "用上臂式血压计复核"
    assert sanitize_medical_copy("用药师复核") == "用上臂式血压计复核"
    assert "药师" not in sanitize_medical_copy("带记录找药师（血压计）咨询")


# 2. Over-reassurance -------------------------------------------------------

def test_over_reassurance_is_replaced():
    out = sanitize_medical_copy("138/86 这个数字本身只是估算，不说明任何问题。")
    assert "不说明任何问题" not in out
    assert "没有问题" not in out
    assert ("不适合" in out) or ("需结合规范测量复核" in out)

    for phrase in ["完全没有问题", "不用担心", "没事的", "风险不大"]:
        out = sanitize_medical_copy(f"本次结果{phrase}。")
        assert phrase.rstrip("的") not in out or "不适合" in out
        assert "不适合" in out or "规范复核" in out


# 4. Colloquial -> precise --------------------------------------------------

def test_colloquial_becomes_precise():
    assert "并非 100%" not in sanitize_medical_copy("算法置信度并非 100%")
    assert "置信度有限" in sanitize_medical_copy("算法置信度并非 100%")
    assert "中上等" not in sanitize_medical_copy("信号质量算中上等")
    assert "先别着急给自己下结论" not in sanitize_medical_copy("先别着急给自己下结论")
    assert "不要将本次结果作为诊断结论" in sanitize_medical_copy("先别着急给自己下结论")
    out = sanitize_medical_copy("这个数字本身只是估算，仅供参考。")
    assert "该数值来自 PPG 估算" in out
    # variant: "先别急着把它当作诊断结果"
    out = sanitize_medical_copy("先别急着把它当作诊断结果——它更像一次提醒。")
    assert "先别急着" not in out
    assert "不要将本次结果作为诊断结论" in out


# 5. Lifestyle detail -------------------------------------------------------

def test_lifestyle_detail_is_generalized():
    out = sanitize_medical_copy("保持规律运动（如快走、慢跑），控制体重。")
    assert "快走" not in out and "慢跑" not in out
    assert "适合自身情况的规律身体活动" in out
    assert "减少高盐食物摄入" in sanitize_medical_copy("平时少吃咸菜和加工食品。")


# 3. Emergency-only ops advice ---------------------------------------------

def test_emergency_strips_new_operational_advice():
    rr = _RR(emergency=True)
    out = sanitize_medical_copy("- 也不要自己开车去医院。", rr)
    assert "开车" not in out
    assert "不要等待" in out

    out = sanitize_medical_copy("- 最好有家人陪同前往。", rr)
    assert "陪同" not in out

    # The licensed 120/ER line is preserved.
    keep = "- 请立即拨打 120 或前往急诊，不要等待复测。"
    assert sanitize_medical_copy(keep, rr).strip() == keep.strip()


def test_emergency_mixed_line_drops_only_the_action_clause():
    rr = _RR(emergency=True)
    out = sanitize_medical_copy("请立即拨打 120 或前往急诊，也不要自己开车去医院。", rr)
    assert "120" in out
    assert "开车" not in out


def test_non_emergency_keeps_ops_words_untouched_by_emergency_rule():
    # Outside emergencies the emergency-ops stripper must not run.
    rr = _RR(emergency=False)
    text = "家人可以陪同你去社区卫生服务中心咨询。"
    out = sanitize_medical_copy(text, rr)
    assert "陪同" in out  # unchanged by emergency rule
