"""Post-report advisor: evidence-cited Q&A plus gentle, staged intake.

After the structured measurement report, the advisor:

1. answers the user's free-text questions with knowledge-base evidence and
   inline ``[n]`` citations (LLM-written when a provider is configured, a
   curated template otherwise — both pass the same safety net);
2. proactively gathers context through the staged question bank
   (``config/advisor_questions.yaml``): low-sensitivity measurement context
   first, history/medication last, every question explained and skippable;
3. turns each newly volunteered fact into further evidence-backed advice.

Safety: replies run through the same forbidden-pattern review as reports
(diagnosis / medication changes / device overclaims / emergency
false-reassurance) and fall back to the curated template reply on violation.
Emergency sessions suppress intake questions entirely and lead with the
emergency banner.
"""

from __future__ import annotations

import json
import re
import threading
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from app.schemas.conversation import (
    AdvisorAnswer,
    AdvisorOption,
    AdvisorQuestion,
    AdvisorSafety,
    AdvisorSession,
    AdvisorTurn,
    AdvisorTurnResponse,
    AdvisorUserMessage,
    ConversationProfile,
)
from app.schemas.report import Evidence, HealthReport
from app.schemas.rule_result import RuleResult
from app.services.citations import build_registry
from app.services.config_loader import load_yaml_config, resolve_project_path
from app.services.medical_copy import clean_citation_fragments, sanitize_medical_copy
from app.services.retriever import retrieve_knowledge

ADVISOR_FOOTNOTE = "以上内容为健康教育信息，不能替代医生诊断或规范血压测量；用药问题请咨询医生。"

EMERGENCY_BANNER = (
    "**当前最重要的事**：之前的评估提示可能存在紧急风险，请立即拨打 120 或前往急诊，"
    "不要等待复测或本对话的其他建议。"
)

SESSION_DIR = "outputs/advisor_sessions"


# ---------------------------------------------------------------------------
# Question bank
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _question_bank() -> Tuple[AdvisorQuestion, ...]:
    data = load_yaml_config("config/advisor_questions.yaml")
    questions: List[AdvisorQuestion] = []
    for raw in data.get("questions", []):
        questions.append(
            AdvisorQuestion(
                id=raw["id"],
                stage=int(raw.get("stage", 0)),
                topic=raw.get("topic", "general"),
                sensitivity=raw.get("sensitivity", "low"),
                preface=raw.get("preface"),
                text=raw["text"],
                why=raw["why"],
                options=[
                    AdvisorOption(id=opt["id"], label=opt["label"], profile=opt.get("profile", {}))
                    for opt in raw.get("options", [])
                ],
            )
        )
    return tuple(questions)


@lru_cache(maxsize=1)
def _question_meta() -> Dict[str, Dict]:
    data = load_yaml_config("config/advisor_questions.yaml")
    return {raw["id"]: raw for raw in data.get("questions", [])}


def _condition_met(condition: Dict, rule_result: RuleResult) -> bool:
    if not condition:
        return False
    if "quality_usable" in condition and rule_result.quality.is_usable != bool(condition["quality_usable"]):
        return False
    if "bp_category_in" in condition and rule_result.estimated_bp_category not in set(condition["bp_category_in"]):
        return False
    if "emergency" in condition and rule_result.emergency != bool(condition["emergency"]):
        return False
    return True


def _question_profile_fields(question: AdvisorQuestion) -> List[str]:
    fields: List[str] = []
    for option in question.options:
        for key in option.profile:
            if key not in fields:
                fields.append(key)
    return fields


def select_next_questions(session: AdvisorSession, max_questions: int = 2) -> List[AdvisorQuestion]:
    """Pick the next gentle questions: lowest open stage first, relevance-boosted.

    Never asks: in an emergency session, anything already asked/answered/
    declined, or anything whose profile facts the user already provided.
    """
    if session.rule_result.emergency or session.closed:
        return []
    known = set(session.profile.known_fields())
    seen = set(session.asked_question_ids) | set(session.answered_question_ids) | set(session.declined_question_ids)
    meta = _question_meta()
    candidates: List[Tuple[int, int, AdvisorQuestion]] = []
    for question in _question_bank():
        if question.id in seen:
            continue
        fields = _question_profile_fields(question)
        if fields and all(field in known for field in fields):
            continue
        ask_if = meta.get(question.id, {}).get("ask_if")
        if ask_if and not _condition_met(ask_if, session.rule_result):
            continue
        boost = 0
        boost_if = meta.get(question.id, {}).get("priority_boost_if")
        if boost_if and _condition_met(boost_if, session.rule_result):
            boost = 1
        candidates.append((question.stage, -boost, question))
    if not candidates:
        return []
    candidates.sort(key=lambda item: (item[0], item[1]))
    lowest_stage = candidates[0][0]
    session.stage = lowest_stage
    same_stage = [question for stage, _, question in candidates if stage == lowest_stage]
    # Sensitive stages go one question at a time so the conversation never
    # feels like a form; early stages may pair two light questions.
    limit = 1 if lowest_stage >= 2 else max_questions
    return same_stage[:limit]


def match_free_text_answer(question: AdvisorQuestion, text: str) -> Optional[str]:
    """Map a free-text reply onto one of the question's options (best effort)."""
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    letters = "ABCDEFGH"
    upper = cleaned.upper()
    for index, option in enumerate(question.options):
        if index < len(letters) and upper == letters[index]:
            return option.id
    for option in question.options:
        if option.label and (option.label in cleaned or cleaned in option.label):
            return option.id
    return None


# ---------------------------------------------------------------------------
# Free-text fact extraction (conservative keyword rules)
# ---------------------------------------------------------------------------

_NEGATION = r"(?:不|没|没有|未|无)"

_FACT_RULES: List[Tuple[re.Pattern, str, object]] = [
    (re.compile(rf"{_NEGATION}[^。；，]{{0,4}}(血压计)"), "has_home_cuff_device", False),
    (re.compile(r"(有|买了|备了)[^。；，]{0,6}血压计"), "has_home_cuff_device", True),
    (re.compile(r"(口味|吃得|饮食)[^。；，]{0,6}(咸|重)"), "salt_preference", "heavy"),
    (re.compile(r"(口味|饮食|吃得)[^。；，]{0,6}清淡"), "salt_preference", "light"),
    (re.compile(rf"{_NEGATION}[^。；，]{{0,6}}(运动|锻炼)|久坐"), "exercise_frequency", "rare"),
    (re.compile(r"(经常|每天|规律)[^。；，]{0,6}(运动|锻炼|快走|跑步)"), "exercise_frequency", "regular"),
    (re.compile(r"(失眠|睡不好|熬夜|睡得很晚)"), "sleep_quality", "poor"),
    (re.compile(rf"{_NEGATION}[^。；，]{{0,4}}(抽烟|吸烟)"), "smoking", "none"),
    (re.compile(r"(抽烟|吸烟)"), "smoking", "regular"),
    (re.compile(rf"{_NEGATION}[^。；，]{{0,4}}(喝酒|饮酒)"), "alcohol", "none"),
    (re.compile(r"(喝酒|饮酒)"), "alcohol", "regular"),
    (re.compile(rf"{_NEGATION}[^。；，]{{0,8}}(降压药|吃药|用药)"), "on_bp_medication", "no"),
    (re.compile(r"(在吃|在用|服用)[^。；，]{0,8}(降压药|药)"), "on_bp_medication", "yes"),
    (re.compile(r"(医生|体检)[^。；，]{0,10}(偏高|高血压)"), "known_bp_history", "yes"),
    (re.compile(r"(爸|妈|父|母|家里人|兄弟|姐妹)[^。；，]{0,10}(高血压|血压高|血压偏高)"), "family_history", "yes"),
]


def extract_profile_facts(text: str) -> Dict[str, object]:
    """Very conservative keyword extraction from free text; order matters
    (negated forms are listed before their positive counterparts)."""
    facts: Dict[str, object] = {}
    for pattern, field_name, value in _FACT_RULES:
        if field_name in facts:
            continue
        if pattern.search(text or ""):
            facts[field_name] = value
    return facts


# ---------------------------------------------------------------------------
# Profile -> further advice (deterministic, evidence-cited)
# ---------------------------------------------------------------------------

_PROFILE_LABELS = {
    "rest_before_measurement": "测量前状态",
    "caffeine_or_smoking_before": "测量前咖啡因/吸烟",
    "posture_ok": "测量姿势",
    "has_home_cuff_device": "家用血压计情况",
    "prior_reading_level": "既往测量水平",
    "salt_preference": "饮食口味",
    "exercise_frequency": "活动量",
    "sleep_quality": "睡眠情况",
    "smoking": "吸烟情况",
    "alcohol": "饮酒情况",
    "known_bp_history": "既往血压提示",
    "on_bp_medication": "降压药使用情况",
    "family_history": "家族血压情况",
    "goal": "关注重点",
}


def _advice_for_update(field_name: str, value: object, registry) -> Optional[str]:
    """One tailored, conservative advice line for a newly learned fact."""
    cite_signal = registry.cite("signal_quality", "remeasurement", limit=2)
    cite_device = registry.cite("device_advice", "home_bp_monitoring", limit=2)
    cite_life = registry.cite("lifestyle", limit=2)
    cite_monitor = registry.cite("home_bp_monitoring", "remeasurement", limit=2)
    cite_med = registry.cite("medication_safety", limit=2)

    if field_name == "rest_before_measurement" and value is False:
        return f"您提到测量前刚活动过：活动后的短时读数普遍偏高，这次数值的参考价值有限；下次先安静坐几分钟再测，并以上臂式血压计的结果为准{cite_signal}。"
    if field_name == "caffeine_or_smoking_before" and value is True:
        return f"咖啡、浓茶或吸烟后的一段时间内血压常会短时升高，这次估算值更适合当作提醒而不是结论；建议平静状态下复核{cite_signal}。"
    if field_name == "posture_ok" and value is False:
        return f"姿势不稳会明显影响 PPG 信号质量；下次坐稳、手放平、保持手指稳定覆盖摄像头再测{cite_signal}。"
    if field_name == "has_home_cuff_device":
        if value is True:
            return f"家里有上臂式血压计很好：安静休息后按说明书规范测量，并把日期、数值和当时状态记录下来，连续记录一段时间更能说明趋势{cite_monitor}。"
        return f"目前没有血压计也不用着急：可以就近在社区卫生服务中心、药店复核，或考虑选购经过验证的上臂式电子血压计{cite_device}。"
    if field_name == "prior_reading_level":
        if value == "high":
            return f"结合您提到以往测量也偏高，更建议把家庭记录整理起来，带给医生看趋势，而不是只看这一次{cite_monitor}。"
        if value == "normal":
            return f"以往规范测量基本正常的话，这次估算值先不必紧张；复核一两次、对比记录即可{cite_monitor}。"
        if value == "none":
            return f"很久没有规范测量过血压的话，这次正好是个开始：用上臂式血压计建立自己的基线记录{cite_device}。"
        return None
    if field_name == "salt_preference" and value == "heavy":
        return f"口味偏咸是很常见的情况，也是最值得先调整的一项：逐步减盐对血压管理有明确益处，可以从少放一勺盐、少喝汤底开始{cite_life}。"
    if field_name == "exercise_frequency" and value == "rare":
        return f"久坐为主的话，不必一上来就高强度运动：从每天多走一段路这类容易坚持的小目标开始就有意义{cite_life}。"
    if field_name == "sleep_quality" and value == "poor":
        return f"睡眠差和压力大都会让血压波动变大，也会影响单次测量的参考价值；保持规律作息本身就是血压管理的一部分{cite_life}。"
    if field_name == "smoking" and value in {"regular", "occasional"}:
        return f"吸烟与血压和心血管风险相关；如果考虑减量或戒烟，社区医生可以提供帮助，这一步什么时候开始都不晚{cite_life}。"
    if field_name == "alcohol" and value in {"regular", "occasional"}:
        return f"饮酒对血压有影响，限制饮酒是公认的生活方式建议之一；可以从减少频次和单次量开始{cite_life}。"
    if field_name == "known_bp_history" and value == "yes":
        return f"既往有过偏高提示的话，规律的家庭血压记录和定期随访比单次测量更重要；把记录带给熟悉您情况的医生最有价值{cite_monitor}。"
    if field_name == "on_bp_medication" and value == "yes":
        return f"已在使用降压药时，本应用不会给任何用药调整意见；最有帮助的做法是按固定习惯记录血压，复诊时带给医生参考{cite_med or cite_monitor}。"
    if field_name == "family_history" and value == "yes":
        return f"直系亲属有血压偏高时，更建议尽早建立家庭自测习惯并关注趋势；这是提醒，不是结论{cite_monitor}。"
    return None


# ---------------------------------------------------------------------------
# Template answers to user questions (intent -> curated, cited copy)
# ---------------------------------------------------------------------------


def _intent_answer_lines(message: str, rule_result: RuleResult, registry) -> List[str]:
    from app.services.retriever import infer_allowed_uses

    uses = infer_allowed_uses([message])
    lines: List[str] = []
    cite_ppg = registry.cite("cuffless_ppg_limitations", "signal_quality", limit=2)
    cite_monitor = registry.cite("home_bp_monitoring", "remeasurement", limit=2)
    cite_device = registry.cite("device_advice", limit=2)
    cite_life = registry.cite("lifestyle", limit=2)
    cite_bp = registry.cite("bp_category_reference", limit=2)
    cite_emergency = registry.cite("emergency_alert", limit=2)
    cite_med = registry.cite("medication_safety", limit=2)

    if rule_result.emergency or "emergency_alert" in uses:
        lines.append(f"如果现在有胸痛、气短、肢体无力、视物改变、说话困难或严重头痛，请立即拨打 120 或前往急诊，不要先等待复测{cite_emergency}。")
    if "medication_safety" in uses:
        # Phrasing must avoid medication-operation words entirely (even in
        # negation) or the reply trips the same safety patterns it serves.
        lines.append(f"关于用药：请直接咨询医生，本应用不提供用药方案；最有帮助的做法是把连续的家庭血压记录带给医生，由医生结合记录做专业判断{cite_med or cite_monitor}。")
    if {"cuffless_ppg_limitations", "signal_quality"} & uses:
        lines.append(f"手机 PPG 估算利用摄像头光信号推算血压趋势，容易受手指按压力度、光线和身体活动影响，所以它适合做趋势提醒，不能替代规范的上臂式血压计测量{cite_ppg}。")
    if {"remeasurement", "home_bp_monitoring"} & uses:
        lines.append(f"复核的关键是：安静休息后按说明书规范测量，并把日期、数值和当时状态记下来；连续一段时间的记录比单次数字更能说明问题{cite_monitor}。")
    if "device_advice" in uses:
        lines.append(f"挑选血压计时优先选择经过独立验证的上臂式电子血压计，腕式和手指式设备的可靠性普遍更弱{cite_device}。")
    if "lifestyle" in uses:
        lines.append(f"生活方式上，减盐、规律活动、控制体重、限酒戒烟和规律作息是被指南反复确认的方向；先挑一件最容易开始的就好{cite_life}。")
    if "bp_category_reference" in uses and not lines:
        lines.append(f"血压参考范围用于解读规范测量的读数；估算值进入偏高范围时更应理解为「需要复核」，而不是诊断{cite_bp}。")
    if not lines:
        lines.append(f"这类问题通常可以从两步入手：先用上臂式血压计规范复核，再连续记录一段时间观察趋势；如果记录持续偏高，带着记录咨询医生{cite_monitor}。")
    return lines


# ---------------------------------------------------------------------------
# Safety review for advisor replies
# ---------------------------------------------------------------------------


def review_advisor_reply(text: str, rule_result: RuleResult) -> AdvisorSafety:
    terms = load_yaml_config("config/safety_terms.yaml")
    issues: List[str] = []
    for key, label in (
        ("diagnostic_patterns", "诊断性表述"),
        ("medication_change_patterns", "用药调整表述"),
        ("device_overclaim_patterns", "设备能力过度承诺"),
    ):
        for pattern in terms.get(key, []):
            if re.search(pattern, text):
                issues.append(f"{label}: {pattern}")
    if rule_result.emergency:
        for pattern in terms.get("emergency_false_reassurance_patterns", []):
            if re.search(pattern, text):
                issues.append(f"急症情境下的不当安抚: {pattern}")
    return AdvisorSafety(passed=not issues, issues=issues)


# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------


class AdvisorSessionStore:
    """In-memory session store with best-effort JSON persistence."""

    def __init__(self, persist_dir: Optional[str] = SESSION_DIR) -> None:
        self._sessions: Dict[str, AdvisorSession] = {}
        self._lock = threading.RLock()
        self._persist_dir = persist_dir

    def put(self, session: AdvisorSession) -> None:
        with self._lock:
            self._sessions[session.session_id] = session
        self._persist(session)

    def get(self, session_id: str) -> Optional[AdvisorSession]:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is not None:
            return session
        return self._load(session_id)

    def _session_path(self, session_id: str):
        if not self._persist_dir:
            return None
        if not re.fullmatch(r"[0-9a-f]{12}", session_id or ""):
            return None
        return resolve_project_path(self._persist_dir) / f"{session_id}.json"

    def _persist(self, session: AdvisorSession) -> None:
        path = self._session_path(session.session_id)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(session.model_dump_json(), encoding="utf-8")
        except OSError:
            pass

    def _load(self, session_id: str) -> Optional[AdvisorSession]:
        path = self._session_path(session_id)
        if path is None or not path.exists():
            return None
        try:
            session = AdvisorSession.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None
        with self._lock:
            self._sessions[session_id] = session
        return session


_STORE = AdvisorSessionStore()


def get_session_store() -> AdvisorSessionStore:
    return _STORE


# ---------------------------------------------------------------------------
# Turn orchestration
# ---------------------------------------------------------------------------


# field -> (focused retrieval query, allowed_uses to guarantee coverage for)
_FIELD_RETRIEVAL_HINTS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "rest_before_measurement": ("测量前安静休息 复测 血压测量准备", ("remeasurement", "signal_quality")),
    "caffeine_or_smoking_before": ("咖啡因 吸烟 测量前 血压短时升高 复测", ("remeasurement", "signal_quality")),
    "posture_ok": ("测量姿势 手指覆盖 信号质量 PPG", ("signal_quality", "remeasurement")),
    "has_home_cuff_device": ("上臂式电子血压计 验证设备 家庭血压监测", ("device_advice", "home_bp_monitoring")),
    "prior_reading_level": ("家庭血压监测 连续记录 趋势 就医沟通", ("home_bp_monitoring",)),
    "salt_preference": ("减少钠盐摄入 饮食 生活方式 血压", ("lifestyle",)),
    "exercise_frequency": ("规律运动 身体活动 血压 生活方式", ("lifestyle",)),
    "sleep_quality": ("睡眠 作息 压力管理 血压 生活方式", ("lifestyle",)),
    "smoking": ("戒烟 血压 生活方式", ("lifestyle",)),
    "alcohol": ("限制饮酒 血压 生活方式", ("lifestyle",)),
    "known_bp_history": ("家庭血压监测 随访 连续记录", ("home_bp_monitoring",)),
    "on_bp_medication": ("降压药 用药安全 带记录咨询医生", ("medication_safety",)),
    "family_history": ("家族史 家庭血压监测 趋势", ("home_bp_monitoring",)),
}


def _advisor_retrieval(
    session: AdvisorSession,
    focus_texts: List[str],
    extra_uses: Optional[Iterable[str]] = None,
) -> List[Evidence]:
    from app.services.retriever import infer_allowed_uses

    intents = [text for text in focus_texts if text and text.strip()]
    if not intents:
        intents = list(session.rule_result.retrieval_intents)[:2]
    uses = infer_allowed_uses(intents) | set(extra_uses or [])
    result = retrieve_knowledge(
        intents,
        top_k=5,
        allowed_uses=sorted(uses) if uses else None,
        min_quality_score=18,
    )
    return result.evidence


def _format_questions_markdown(questions: List[AdvisorQuestion]) -> List[str]:
    lines: List[str] = []
    letters = "ABCDEFGH"
    for question in questions:
        lines.append("")
        if question.preface:
            lines.append(f"{question.preface}")
        lines.append(f"**{question.text}**")
        lines.append(f"_为什么问这个：{question.why}_")
        for index, option in enumerate(question.options):
            letter = letters[index] if index < len(letters) else str(index + 1)
            lines.append(f"- {letter}. {option.label}")
        lines.append("（直接回复选项字母或内容即可；回复「跳过」我们就不再问这一条。）")
    return lines


def _references_block(final) -> List[str]:
    if final is None or not final.references:
        return []
    lines = ["", "**参考文献**（按正文出现顺序编号）", ""]
    for reference in final.references:
        lines.append(reference)
    return lines


def _compose_reply(
    session: AdvisorSession,
    ack_lines: List[str],
    answer_lines: List[str],
    advice_lines: List[str],
    questions: List[AdvisorQuestion],
    registry,
) -> Tuple[str, object]:
    lines: List[str] = []
    if session.rule_result.emergency:
        lines.append(EMERGENCY_BANNER)
        lines.append("")
    lines.extend(ack_lines)
    if answer_lines:
        if lines and lines[-1]:
            lines.append("")
        lines.extend(answer_lines)
    if advice_lines:
        if lines and lines[-1]:
            lines.append("")
        lines.append("**结合您刚补充的信息，再给几条贴合的建议：**")
        lines.extend(f"- {line}" for line in advice_lines)
    if questions:
        lines.extend(_format_questions_markdown(questions))
    body = "\n".join(lines).strip()

    final = registry.finalize(body) if registry.has_evidence else None
    if final is not None:
        body = final.body
    tail: List[str] = _references_block(final)
    tail.extend(["", f"> {ADVISOR_FOOTNOTE}"])
    return body + "\n" + "\n".join(tail), final


def _apply_answers(
    session: AdvisorSession, answers: List[AdvisorAnswer], skip_ids: List[str]
) -> Tuple[List[str], List[str]]:
    """Apply structured answers/skips; returns (updated field labels, ack lines)."""
    questions_by_id = {question.id: question for question in _question_bank()}
    updates: List[str] = []
    acks: List[str] = []
    profile_data = session.profile.model_dump()

    for skip_id in skip_ids:
        if skip_id in questions_by_id and skip_id not in session.declined_question_ids:
            session.declined_question_ids.append(skip_id)
            topic = questions_by_id[skip_id].topic
            if topic not in profile_data["declined_topics"]:
                profile_data["declined_topics"].append(topic)
    if skip_ids:
        acks.append("好的，这部分先跳过，完全没问题。")

    for answer in answers:
        question = questions_by_id.get(answer.question_id)
        if question is None:
            continue
        if answer.question_id not in session.answered_question_ids:
            session.answered_question_ids.append(answer.question_id)
        option = None
        if answer.option_id:
            option = next((opt for opt in question.options if opt.id == answer.option_id), None)
        if option is None and answer.text:
            matched_id = match_free_text_answer(question, answer.text)
            option = next((opt for opt in question.options if opt.id == matched_id), None)
        if option is not None:
            declined = any(str(value) == "declined" for value in option.profile.values())
            for key, value in option.profile.items():
                if key in profile_data:
                    profile_data[key] = value
                    if not declined:
                        updates.append(key)
            if declined and question.topic not in profile_data["declined_topics"]:
                profile_data["declined_topics"].append(question.topic)
        elif answer.text:
            profile_data["notes"].append(f"{question.id}: {answer.text.strip()}")

    session.profile = ConversationProfile.model_validate(profile_data)
    return list(dict.fromkeys(updates)), acks


def create_session(raw_payload: Dict, report: Optional[HealthReport] = None) -> Tuple[AdvisorSession, AdvisorTurnResponse]:
    """Create a session from miniapp structured input and open the conversation."""
    from app.agents.workflow import generate_report
    from app.services.validator import parse_payload

    payload = parse_payload(raw_payload)
    if report is None:
        report = generate_report(raw_payload)
    from app.services.rule_engine import run_rule_engine

    rule_result = run_rule_engine(payload)
    session = AdvisorSession(
        session_id=uuid4().hex[:12],
        payload=payload,
        rule_result=rule_result,
        report_id=report.report_id,
        report_markdown=report.markdown_report,
    )

    evidence = list(report.retrieved_evidence) or _advisor_retrieval(session, list(rule_result.retrieval_intents)[:2])
    registry = build_registry(evidence)

    ack_lines: List[str] = []
    if rule_result.emergency:
        ack_lines.append("检测报告已经生成。在症状处理好之前，我们不会再追问其他问题；之后随时可以回来继续。")
        questions: List[AdvisorQuestion] = []
    else:
        summary = session.payload.measurement
        bp_text = (
            f"{summary.estimated_sbp:.0f}/{summary.estimated_dbp:.0f} mmHg"
            if summary.estimated_sbp and summary.estimated_dbp
            else "本次估算值"
        )
        cite_bp = registry.cite("bp_category_reference", "cuffless_ppg_limitations", limit=2)
        ack_lines.append(
            f"报告已经生成。简单来说：这次估算值 {bp_text} 是一次趋势提醒，不是诊断结论，"
            f"下一步的重点是规范复核与记录{cite_bp}。"
        )
        ack_lines.append(
            "接下来如果方便，我想多了解一点当时的情况，让建议更贴合您；"
            "所有问题都可以跳过，您也可以随时直接提问。"
        )
        questions = select_next_questions(session)
        session.asked_question_ids.extend(question.id for question in questions)

    reply_markdown, final = _compose_reply(session, ack_lines, [], [], questions, registry)
    safety = review_advisor_reply(reply_markdown, rule_result)

    session.history.append(
        AdvisorTurn(role="advisor", content=reply_markdown, question_ids=[question.id for question in questions])
    )
    get_session_store().put(session)

    response = AdvisorTurnResponse(
        session_id=session.session_id,
        reply_markdown=reply_markdown,
        references=(final.entries if final is not None else []),
        questions=questions,
        profile=session.profile,
        profile_updates=[],
        stage=session.stage,
        generation_mode="template_advisor_opening",
        safety=safety,
    )
    return session, response


def _llm_reply(
    session: AdvisorSession,
    user_message: str,
    answer_summary: List[str],
    advice_lines: List[str],
    questions: List[AdvisorQuestion],
    evidence: List[Evidence],
) -> Optional[Tuple[str, str]]:
    """Try the configured LLM provider; returns (body, mode) or None."""
    import os

    from app.services.llm_adapter import LlmGenerationError, generate_llm_advisor_reply

    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    if provider in {"openai-compatible", "third_party", "thirdparty"}:
        provider = "openai_compatible"
    if provider not in {"deepseek", "anthropic", "claude", "openai_compatible"}:
        return None
    try:
        body = generate_llm_advisor_reply(
            provider=provider,
            rule_result=session.rule_result,
            profile=session.profile,
            history=session.history[-6:],
            user_message=user_message,
            answer_summary=answer_summary,
            advice_hints=advice_lines,
            questions=questions,
            evidence=evidence,
        )
    except LlmGenerationError:
        return None
    if provider == "deepseek":
        label, model = "deepseek", os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    elif provider == "openai_compatible":
        label, model = "openai_compatible", os.getenv("LLM_MODEL", "gpt-5.5")
    else:
        label, model = "anthropic", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    return body, f"llm_advisor_{label}:{model}"


def advisor_turn(session_id: str, user_input: AdvisorUserMessage) -> AdvisorTurnResponse:
    session = get_session_store().get(session_id)
    if session is None:
        raise KeyError(f"advisor session not found: {session_id}")

    user_message = (user_input.message or "").strip()

    # 1) absorb structured answers / skips, then conservative free-text facts.
    updates, acks = _apply_answers(session, user_input.answers, user_input.skip_question_ids)
    if user_message:
        facts = extract_profile_facts(user_message)
        if facts:
            profile_data = session.profile.model_dump()
            for key, value in facts.items():
                if profile_data.get(key) is None:
                    profile_data[key] = value
                    updates.append(key)
            session.profile = ConversationProfile.model_validate(profile_data)
        session.history.append(AdvisorTurn(role="user", content=user_message))
    elif user_input.answers or user_input.skip_question_ids:
        summary = "；".join(
            f"{answer.question_id}={answer.option_id or answer.text}" for answer in user_input.answers
        ) or "跳过提问"
        session.history.append(AdvisorTurn(role="user", content=f"[结构化回答] {summary}"))
    updates = list(dict.fromkeys(updates))

    # 2) retrieve evidence for this turn (user question + newly touched topics).
    focus = [user_message] if user_message else []
    extra_uses: List[str] = []
    for field_name in updates:
        hint = _FIELD_RETRIEVAL_HINTS.get(field_name)
        if hint is None:
            continue
        focus.append(hint[0])
        extra_uses.extend(hint[1])
    evidence = _advisor_retrieval(session, focus, extra_uses)
    registry = build_registry(evidence)

    # 3) deterministic building blocks (always computed: they are the fallback
    #    and the source of advice hints for the LLM).
    if updates and not acks:
        acks.append("谢谢补充，这些信息只用于让建议更贴合您。")
    answer_lines = _intent_answer_lines(user_message, session.rule_result, registry) if user_message else []
    advice_lines: List[str] = []
    for field_name in updates:
        line = _advice_for_update(field_name, getattr(session.profile, field_name, None), registry)
        if line:
            advice_lines.append(line)

    questions = select_next_questions(session)
    generation_mode = "template_advisor"
    warnings: List[str] = []

    # 4) optional LLM rewrite under the same evidence numbering + safety net.
    llm_result = _llm_reply(session, user_message, updates, advice_lines, questions, evidence)
    if llm_result is not None:
        llm_body, llm_mode = llm_result
        llm_body = sanitize_medical_copy(llm_body, session.rule_result)
        llm_body = clean_citation_fragments(llm_body)
        llm_body = registry.strip_invalid_markers(llm_body)
        llm_safety = review_advisor_reply(llm_body, session.rule_result)
        if llm_safety.passed and (not registry.has_evidence or registry.body_is_consistent(llm_body)):
            llm_registry = build_registry(evidence)
            reply_markdown, final = _compose_reply(
                session, [], [llm_body], [], questions, llm_registry
            )
            generation_mode = llm_mode
            safety = review_advisor_reply(reply_markdown, session.rule_result)
            session.asked_question_ids.extend(
                question.id for question in questions if question.id not in session.asked_question_ids
            )
            session.history.append(
                AdvisorTurn(role="advisor", content=reply_markdown, question_ids=[q.id for q in questions])
            )
            get_session_store().put(session)
            return AdvisorTurnResponse(
                session_id=session.session_id,
                reply_markdown=reply_markdown,
                references=(final.entries if final is not None else []),
                questions=questions,
                profile=session.profile,
                profile_updates=[_PROFILE_LABELS.get(field, field) for field in updates],
                stage=session.stage,
                generation_mode=generation_mode,
                safety=safety,
                warnings=warnings,
            )
        warnings.append("LLM 回复未通过安全或引用校验，已回退到模板回复。")
        generation_mode = "llm_advisor_safety_fallback_template"

    if not user_message and not updates and not user_input.skip_question_ids and not questions:
        acks.append("这一轮没有新的信息也没关系；您可以随时提问，或回复「结束」结束本次随访。")

    if not questions and not session.closed and not session.rule_result.emergency:
        session.closed = True
        acks.append("该了解的我们都聊到了；之后任何时候想确认复测结果或新的疑问，直接发消息就可以。")

    reply_markdown, final = _compose_reply(session, acks, answer_lines, advice_lines, questions, registry)
    safety = review_advisor_reply(reply_markdown, session.rule_result)
    if not safety.passed:
        # Curated copy should never trip the review; degrade hard if it does.
        reply_markdown = (
            (EMERGENCY_BANNER + "\n\n") if session.rule_result.emergency else ""
        ) + "建议先用经过验证的上臂式血压计规范复核并连续记录；如有不适请及时就医。\n\n> " + ADVISOR_FOOTNOTE
        final = None
        generation_mode = "advisor_safety_minimal"
        safety = review_advisor_reply(reply_markdown, session.rule_result)

    session.asked_question_ids.extend(
        question.id for question in questions if question.id not in session.asked_question_ids
    )
    session.history.append(
        AdvisorTurn(role="advisor", content=reply_markdown, question_ids=[q.id for q in questions])
    )
    get_session_store().put(session)

    return AdvisorTurnResponse(
        session_id=session.session_id,
        reply_markdown=reply_markdown,
        references=(final.entries if final is not None else []),
        questions=questions,
        profile=session.profile,
        profile_updates=[_PROFILE_LABELS.get(field, field) for field in updates],
        stage=session.stage,
        generation_mode=generation_mode,
        safety=safety,
        warnings=warnings,
    )
