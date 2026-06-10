import re

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.conversation import AdvisorAnswer, AdvisorUserMessage
from app.services.advisor import (
    advisor_turn,
    create_session,
    extract_profile_facts,
    review_advisor_reply,
    select_next_questions,
)


client = TestClient(app)

HIGH_BP_PAYLOAD = {
    "estimated_sbp": 146,
    "estimated_dbp": 93,
    "heart_rate": 80,
    "signal_quality_score": 0.88,
    "confidence": 0.7,
    "capture_duration_sec": 30,
    "ppg_source": "camera_finger",
    "age": 45,
}


def test_create_session_opens_with_gentle_low_sensitivity_questions():
    session, opening = create_session(dict(HIGH_BP_PAYLOAD))
    assert opening.questions, "opening should proactively ask questions"
    # progressive disclosure: the conversation must NOT start with sensitive topics
    assert all(question.stage == 0 for question in opening.questions)
    assert all(question.sensitivity == "low" for question in opening.questions)
    assert all(question.skippable for question in opening.questions)
    assert all(question.why for question in opening.questions)
    # opening recap is cited and carries the education footnote
    assert re.search(r"\[\d+(?:,\d+)*\]", opening.reply_markdown)
    assert "健康教育" in opening.reply_markdown
    assert opening.references, "opening should expose structured references"


def test_sensitive_questions_come_later_and_are_skippable():
    session, _ = create_session(dict(HIGH_BP_PAYLOAD))
    seen_stages = []
    for _ in range(12):
        questions = select_next_questions(session)
        if not questions:
            break
        seen_stages.extend(question.stage for question in questions)
        for question in questions:
            session.asked_question_ids.append(question.id)
            session.declined_question_ids.append(question.id)
    assert seen_stages == sorted(seen_stages), "stages must be non-decreasing (循序渐进)"
    bank_high = [q for q in seen_stages if q >= 3]
    assert bank_high, "history/medication stage should eventually be reachable"


def test_answer_updates_profile_and_yields_cited_followup_advice():
    session, _ = create_session(dict(HIGH_BP_PAYLOAD))
    response = advisor_turn(
        session.session_id,
        AdvisorUserMessage(answers=[AdvisorAnswer(question_id="q_rest_state", option_id="active")]),
    )
    assert session.profile.rest_before_measurement is False
    assert "测量前状态" in response.profile_updates
    # the tailored advice must be evidence-cited and renumbered from [1]
    assert re.search(r"\[1[,\]]", response.reply_markdown)
    assert response.references and response.references[0].number == 1
    assert "参考文献" in response.reply_markdown


def test_free_text_facts_are_extracted_conservatively():
    facts = extract_profile_facts("我平时吃得比较咸，几乎不运动，最近老是熬夜，没有血压计")
    assert facts["salt_preference"] == "heavy"
    assert facts["exercise_frequency"] == "rare"
    assert facts["sleep_quality"] == "poor"
    assert facts["has_home_cuff_device"] is False
    negated = extract_profile_facts("我不抽烟，也没有在吃降压药")
    assert negated["smoking"] == "none"
    assert negated["on_bp_medication"] == "no"


def test_medication_question_reply_stays_safe():
    session, _ = create_session(dict(HIGH_BP_PAYLOAD))
    response = advisor_turn(
        session.session_id,
        AdvisorUserMessage(message="我在吃降压药，能不能停药？"),
    )
    assert response.safety.passed is True
    assert "咨询医生" in response.reply_markdown
    # must never instruct stopping/adjusting medication
    assert not re.search(r"可以停药|建议停药|减少剂量|加大剂量", response.reply_markdown)


def test_skip_marks_topic_declined_and_never_asks_again():
    session, opening = create_session(dict(HIGH_BP_PAYLOAD))
    first_ids = [question.id for question in opening.questions]
    response = advisor_turn(
        session.session_id,
        AdvisorUserMessage(skip_question_ids=first_ids),
    )
    later_ids = [question.id for question in response.questions]
    assert not set(first_ids) & set(later_ids)
    assert set(first_ids) <= set(session.declined_question_ids)


def test_emergency_session_suppresses_questions_and_leads_with_120():
    payload = {
        "estimated_sbp": 185,
        "estimated_dbp": 122,
        "signal_quality_score": 0.9,
        "symptoms": {"chest_pain": True},
    }
    session, opening = create_session(payload)
    assert opening.questions == []
    assert "120" in opening.reply_markdown.splitlines()[0]
    followup = advisor_turn(session.session_id, AdvisorUserMessage(message="我现在该怎么办"))
    assert followup.questions == []
    assert "120" in followup.reply_markdown.splitlines()[0]
    assert followup.safety.passed is True


def test_review_advisor_reply_blocks_medication_instructions():
    session, _ = create_session(dict(HIGH_BP_PAYLOAD))
    bad = review_advisor_reply("你可以自行停药观察几天。", session.rule_result)
    assert bad.passed is False


def test_advisor_api_roundtrip():
    created = client.post("/api/v1/advisor/sessions", json=dict(HIGH_BP_PAYLOAD))
    assert created.status_code == 200
    data = created.json()
    assert data["report"]["markdown_report"]
    assert data["opening"]["questions"]
    session_id = data["session_id"]

    answered = client.post(
        f"/api/v1/advisor/sessions/{session_id}/messages",
        json={"message": "口味比较咸", "answers": [], "skip_question_ids": []},
    )
    assert answered.status_code == 200
    body = answered.json()
    assert body["safety"]["passed"] is True
    assert "盐" in body["reply_markdown"] or "减盐" in body["reply_markdown"]

    state = client.get(f"/api/v1/advisor/sessions/{session_id}")
    assert state.status_code == 200
    assert state.json()["profile"]["salt_preference"] == "heavy"

    missing = client.post("/api/v1/advisor/sessions/nope/messages", json={"message": "hi"})
    assert missing.status_code == 404
