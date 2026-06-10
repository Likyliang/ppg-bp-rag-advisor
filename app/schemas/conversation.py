"""Schemas for the post-report advisor conversation.

The advisor runs *after* a measurement report: it answers the user's questions
with evidence-cited replies, and proactively gathers context through gentle,
staged, always-skippable questions, turning new facts into further
evidence-backed suggestions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.measurement import MeasurementPayload
from app.schemas.report import ReferenceEntry
from app.schemas.rule_result import RuleResult


class AdvisorOption(BaseModel):
    """One quick-reply choice; selecting it patches the session profile."""

    id: str
    label: str
    profile: Dict[str, Any] = Field(default_factory=dict)


class AdvisorQuestion(BaseModel):
    """A gentle, staged intake question.

    ``why`` is always shown with the question — explaining why we ask is the
    core of the non-offensive design, together with skippability and the
    normalising ``preface``.
    """

    id: str
    stage: int = 0
    topic: str = "general"
    sensitivity: Literal["low", "medium", "high"] = "low"
    preface: Optional[str] = None
    text: str
    why: str
    options: List[AdvisorOption] = Field(default_factory=list)
    allow_free_text: bool = True
    skippable: bool = True


class ConversationProfile(BaseModel):
    """Facts the user has volunteered during the conversation.

    Everything is optional and starts unknown; ``declined`` topics are never
    asked again. ``str`` enums use plain values so the question bank YAML can
    patch them directly.
    """

    model_config = ConfigDict(extra="ignore")

    rest_before_measurement: Optional[bool] = None
    caffeine_or_smoking_before: Optional[bool] = None
    posture_ok: Optional[bool] = None
    has_home_cuff_device: Optional[bool] = None
    prior_reading_level: Optional[str] = None  # high / normal / none / unsure
    salt_preference: Optional[str] = None  # light / medium / heavy / unsure
    exercise_frequency: Optional[str] = None  # regular / occasional / rare
    sleep_quality: Optional[str] = None  # good / fair / poor
    smoking: Optional[str] = None  # none / occasional / regular / declined
    alcohol: Optional[str] = None  # none / occasional / regular / declined
    known_bp_history: Optional[str] = None  # yes / no / unsure / declined
    on_bp_medication: Optional[str] = None  # yes / no / declined
    family_history: Optional[str] = None  # yes / no / unknown / declined
    current_symptom_note: Optional[str] = None
    goal: Optional[str] = None
    notes: List[str] = Field(default_factory=list)
    declined_topics: List[str] = Field(default_factory=list)

    def known_fields(self) -> List[str]:
        known: List[str] = []
        for name in type(self).model_fields:
            if name in {"notes", "declined_topics"}:
                continue
            if getattr(self, name) is not None:
                known.append(name)
        return known


class AdvisorTurn(BaseModel):
    role: Literal["user", "advisor"]
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    question_ids: List[str] = Field(default_factory=list)


class AdvisorSession(BaseModel):
    session_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    payload: MeasurementPayload
    rule_result: RuleResult
    report_id: Optional[str] = None
    report_markdown: Optional[str] = None
    profile: ConversationProfile = Field(default_factory=ConversationProfile)
    asked_question_ids: List[str] = Field(default_factory=list)
    answered_question_ids: List[str] = Field(default_factory=list)
    declined_question_ids: List[str] = Field(default_factory=list)
    history: List[AdvisorTurn] = Field(default_factory=list)
    stage: int = 0
    closed: bool = False


class AdvisorAnswer(BaseModel):
    """One structured answer to a previously asked question."""

    question_id: str
    option_id: Optional[str] = None
    text: Optional[str] = None


class AdvisorUserMessage(BaseModel):
    message: Optional[str] = None
    answers: List[AdvisorAnswer] = Field(default_factory=list)
    skip_question_ids: List[str] = Field(default_factory=list)


class AdvisorSafety(BaseModel):
    passed: bool = True
    issues: List[str] = Field(default_factory=list)


class AdvisorTurnResponse(BaseModel):
    session_id: str
    reply_markdown: str
    references: List[ReferenceEntry] = Field(default_factory=list)
    questions: List[AdvisorQuestion] = Field(default_factory=list)
    profile: ConversationProfile = Field(default_factory=ConversationProfile)
    profile_updates: List[str] = Field(default_factory=list)
    stage: int = 0
    generation_mode: str = "template_advisor"
    safety: AdvisorSafety = Field(default_factory=AdvisorSafety)
    warnings: List[str] = Field(default_factory=list)
