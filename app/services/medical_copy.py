"""Medical copy sanitizer: a final editorial pass over LLM-written report bodies.

This is deliberately separate from ``generator._sanitize_llm_body`` (which
enforces the hard safety boundary: no diagnosis / no medication changes / no
device over-claims). This layer is the *editorial* pass that makes the prose
read like "health science communication + safety statement" rather than a chat:

1. Wrong words   — OCR/LLM garbles like "用药师（上臂式血压计）" -> "上臂式血压计".
2. Over-reassurance — "不说明任何问题 / 没有问题 / 不用担心 / 没事" -> conservative
   "不适合解释血压范围 / 不适合单独判断" phrasing (esp. low-quality captures).
3. Emergency ops advice — in emergency reports, strip newly-introduced concrete
   actions (driving, escort, posture, diet) the evidence/template never licensed;
   keep only "拨打 120 / 前往急诊 / 不要等待小程序或家庭复测".
4. Colloquial -> precise — chatty comfort phrasing -> neutral科普 wording.
5. Lifestyle detail — over-specific lifestyle tips -> generic, non-prescriptive.

Every rule rewrites the offending span into safe text instead of deleting the
sentence, so structure and inline citations are preserved.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.schemas.rule_result import RuleResult


# ---------------------------------------------------------------------------
# 1. Wrong-word blacklist (highest priority — these are outright errors).
# ---------------------------------------------------------------------------
_WRONG_WORD_RULES: List[Tuple[re.Pattern, str]] = [
    # "用药师（上臂式血压计）复核" -> "用上臂式血压计复核" (keep the 用 verb).
    (re.compile(r"用药师\s*[（(]\s*(上臂式)?血压计\s*[）)]"), "用上臂式血压计"),
    # bare "药师（…血压计…）" (no leading 用) -> 上臂式血压计
    (re.compile(r"药师\s*[（(]\s*(上臂式)?血压计\s*[）)]"), "上臂式血压计"),
    (re.compile(r"药师\s*[（(][^）)]*血压计[^）)]*[）)]"), "上臂式血压计"),
    (re.compile(r"用药师复核"), "用上臂式血压计复核"),
    (re.compile(r"用药师"), "用上臂式血压计"),
]


# ---------------------------------------------------------------------------
# 2. Over-reassurance phrasing.
# ---------------------------------------------------------------------------
_REASSURANCE_RULES: List[Tuple[re.Pattern, str]] = [
    # "…只是估算，不说明任何问题。" -> conservative low-quality framing.
    (re.compile(r"[^，。；\n]*不说明任何问题[^。\n]*。?"),
     "该数值来自 PPG 估算，不适合单独解释血压高低；更稳妥的做法是重新采集并用上臂式血压计复核。"),
    (re.compile(r"[^，。；\n]*没有(任何)?问题[^。\n]*。?"),
     "该数值不适合单独判断血压高低，仍需重新采集并规范复核。"),
    (re.compile(r"[^，。；\n]*(完全)?不用担心[^。\n]*。?"),
     "该数值不适合单独判断血压高低，仍建议规范复核。"),
    (re.compile(r"[^，。；\n]*(完全)?没事[^。\n]*。?"),
     "该数值不适合单独判断血压高低，仍建议规范复核。"),
    (re.compile(r"风险不大|问题不大|无需担心|不必担心"),
     "不适合单独判断，需要规范复核"),
]


# ---------------------------------------------------------------------------
# 4. Colloquial -> precise (applies to all reports).
# ---------------------------------------------------------------------------
_COLLOQUIAL_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"算法置信度并非\s*100%?"), "算法置信度有限"),
    (re.compile(r"置信度并非\s*100%?"), "置信度有限"),
    (re.compile(r"并非\s*100%\s*准确"), "准确性有限"),
    (re.compile(r"(信号质量)?算中上等"), "信号质量较好，可用于保守趋势解释"),
    (re.compile(r"质量算中上"), "信号质量较好"),
    (re.compile(r"中上等"), "较好"),
    (re.compile(r"(请)?(先)?别(着急|急着)给自己下结论"), "不要将本次结果作为诊断结论"),
    (re.compile(r"(请)?(先)?别(着急|急着)下结论"), "不要将本次结果作为诊断结论"),
    (re.compile(r"(先)?不要(着急|急着)给自己下结论"), "不要将本次结果作为诊断结论"),
    # "先别急着把它当成/当作/当做诊断结果" and kin -> neutral.
    (re.compile(r"(请)?(先)?(别|不要)(着急|急着)?把(它|这|本次结果|这个数字)?(当成|当作|当做|当)诊断(结果|结论)"),
     "不要将本次结果作为诊断结论"),
    # generic leftover "先别急着…" opener at sentence start.
    (re.compile(r"(请)?先别(着急|急着)"), "请注意，"),
    (re.compile(r"先别(着急|担心)"), "请注意"),
    (re.compile(r"这个数字本身只是估算[^。\n]*。?"),
     "该数值来自 PPG 估算，需结合规范测量复核。"),
    (re.compile(r"这个数字只是(一个)?估算[^。\n]*。?"),
     "该数值来自 PPG 估算，需结合规范测量复核。"),
    (re.compile(r"别紧张|不要紧张|放轻松"), "请理性看待"),
]


# ---------------------------------------------------------------------------
# 5. Lifestyle detail -> generic, non-prescriptive.
# ---------------------------------------------------------------------------
_LIFESTYLE_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"保持规律运动\s*（[^）]*）"), "保持适合自身情况的规律身体活动"),
    (re.compile(r"规律运动\s*（[^）]*）"), "适合自身情况的规律身体活动"),
    (re.compile(r"保持规律运动(（如[^）]*）)?"), "保持适合自身情况的规律身体活动"),
    (re.compile(r"(如|例如|比如)?快走、?慢跑(、?游泳)?"), "适度活动"),
    (re.compile(r"少吃咸菜和加工食品"), "减少高盐食物摄入"),
    (re.compile(r"少吃咸菜"), "减少高盐食物摄入"),
    (re.compile(r"不吃咸菜、?腌制食品"), "减少高盐食物摄入"),
    (re.compile(r"少吃腌制食品"), "减少高盐食物摄入"),
]


# ---------------------------------------------------------------------------
# 3. Emergency-only: strip newly-introduced concrete operational advice.
# ---------------------------------------------------------------------------
# Lines mentioning these actions (in an emergency report) are replaced with the
# single licensed instruction. Matches the *idea*, not one exact phrasing.
_EMERGENCY_OPS_PATTERN = re.compile(
    r"开车|驾车|自驾|骑车|坐车|打车|交通工具|"
    r"陪同|有人陪|找人陪|让家人|让家属|喊人|叫人|"
    r"平躺|躺下|平卧|坐下休息|保持(某种)?姿势|半坐位|"
    r"喝水|吃点|进食|含服|舌下|嚼服"
)
_EMERGENCY_SAFE_LINE = "不要等待小程序再次测量或家庭复测结果。"
# Don't rewrite a line that is purely the licensed 120/ER instruction.
_EMERGENCY_KEEP_PATTERN = re.compile(r"120|急诊|急救|紧急医疗")


def _apply_rules(text: str, rules: List[Tuple[re.Pattern, str]]) -> str:
    for pattern, replacement in rules:
        text = pattern.sub(replacement, text)
    return text


def _sanitize_emergency_ops(body: str) -> str:
    """In emergency reports, replace lines that add non-licensed actions.

    A line that mentions a forbidden action AND is not the core 120/ER line is
    rewritten to the single safe instruction. Bullet/numbered prefixes preserved.
    """
    out: List[str] = []
    for line in body.splitlines():
        if line.lstrip().startswith("#"):
            out.append(line)
            continue
        if _EMERGENCY_OPS_PATTERN.search(line) and not _EMERGENCY_KEEP_PATTERN.search(line):
            prefix_match = re.match(r"^(\s*(?:[-*]\s+|\d+[.、)]\s*)?)", line)
            prefix = prefix_match.group(1) if prefix_match else ""
            safe_line = f"{prefix}{_EMERGENCY_SAFE_LINE}"
            if out and out[-1].strip() == safe_line.strip():
                continue
            out.append(safe_line)
            continue
        # Mixed line: forbidden action + 120 mention -> drop only the action clause.
        if _EMERGENCY_OPS_PATTERN.search(line):
            clauses = re.split(r"([，。；])", line)
            kept = []
            for part in clauses:
                if _EMERGENCY_OPS_PATTERN.search(part) and not _EMERGENCY_KEEP_PATTERN.search(part):
                    continue
                kept.append(part)
            rebuilt = "".join(kept)
            rebuilt = re.sub(r"[，；]{2,}", "，", rebuilt).replace("，。", "。")
            out.append(rebuilt if rebuilt.strip() else line)
            continue
        out.append(line)
    return "\n".join(out)


def _tidy(body: str) -> str:
    body = re.sub(r"[，、；]{2,}", "，", body)
    body = body.replace("。。", "。").replace("；。", "。").replace("，。", "。")
    body = re.sub(r"[ \t]{2,}", " ", body)
    return body


def sanitize_medical_copy(body: str, rule_result: Optional[RuleResult] = None) -> str:
    """Final editorial pass. Safe to run on any LLM-written report body."""
    body = _apply_rules(body, _WRONG_WORD_RULES)
    body = _apply_rules(body, _REASSURANCE_RULES)
    body = _apply_rules(body, _COLLOQUIAL_RULES)
    body = _apply_rules(body, _LIFESTYLE_RULES)
    if rule_result is not None and getattr(rule_result, "emergency", False):
        body = _sanitize_emergency_ops(body)
    return _tidy(body)
