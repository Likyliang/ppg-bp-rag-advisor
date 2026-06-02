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


def test_emergency_strips_recheck_while_waiting_variants():
    rr = _RR(emergency=True)
    out = sanitize_medical_copy(
        "- 在等待医疗帮助时，如果条件允许（且不影响急救），可以请家人帮忙用规范上臂式血压计复核一次。",
        rr,
    )
    assert "请家人帮忙" not in out
    assert "复核一次" not in out
    assert "条件允许" not in out
    assert "不要等待" in out

    for variant in ["- 可以先复核一次。", "- 家人帮忙测一下。", "- 等待医疗帮助时先复核。"]:
        out = sanitize_medical_copy(variant, rr)
        assert "复核" not in out or "不要等待" in out


def test_emergency_alert_line_with_citation_is_preserved():
    rr = _RR(emergency=True)
    line = "请立即拨打 120 或前往最近医院的急诊，不要等待小程序复测结果[2,4]。"
    out = sanitize_medical_copy(line, rr)
    assert "120" in out and "急诊" in out
    assert "[2,4]" in out  # citation intact


# 6a. Concept error: symptoms are not a special population --------------------

def test_concept_symptoms_not_special_population():
    out = sanitize_medical_copy("特殊人群（你勾选了需要重视的症状）更不应依赖单次 PPG 结果。")
    assert "特殊人群" not in out
    assert "出现急症相关症状时" in out
    assert "更不应依赖单次 PPG 结果" in out


# 6b. More colloquial tightening ---------------------------------------------

def test_more_colloquial_tightened():
    assert "先别盯着数字看" not in sanitize_medical_copy("先别盯着数字看，先复核。")
    assert "不要仅依据本次估算值判断" in sanitize_medical_copy("先别盯着数字看。")
    assert "先别慌" not in sanitize_medical_copy("先别慌，这只是估算。")
    assert "请先进行规范复核" in sanitize_medical_copy("先别慌。")
    # "先别把它当成结果" (without 诊断) is also softened.
    out = sanitize_medical_copy("但先别把它当成结果。因为信号质量不够。")
    assert "先别把它当成结果" not in out
    assert "不要将本次结果作为诊断结论" in out


# 5. Dangling bracket / citation fragments -----------------------------------

def test_clean_citation_fragments_preserves_valid_markers():
    from app.services.medical_copy import clean_citation_fragments

    assert clean_citation_fragments("结论[1]，建议[1,2]，再看[3]。") == "结论[1]，建议[1,2]，再看[3]。"
    assert clean_citation_fragments("复核[1, 2]后记录[5]。") == "复核[1, 2]后记录[5]。"


def test_clean_citation_fragments_removes_dangling():
    from app.services.medical_copy import clean_citation_fragments

    assert clean_citation_fragments("不要等待小程序或家庭复测结果。 [") == "不要等待小程序或家庭复测结果。"
    assert "[1," not in clean_citation_fragments("这次偏高[1,")
    assert clean_citation_fragments("残留[1, ]结尾").count("[") == 0
    assert clean_citation_fragments("空[ ]括号") == "空括号"
    # line-end fragment after punctuation
    assert clean_citation_fragments("第一行。 [\n第二行。").splitlines()[0] == "第一行。"
