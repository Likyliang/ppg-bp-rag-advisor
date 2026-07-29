from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class ScreeningSuggestion(BaseModel):
    """One "go get this professionally screened" suggestion — never a diagnosis.

    Each suggestion is hedged, names a concrete screening pathway, and carries a
    confidence capped at ``moderate``. The safety layer validates these bounds
    before the suggestion can reach a user-facing report.
    """

    model_config = ConfigDict(extra="ignore")

    condition_id: str
    label: str
    confidence: Literal["low", "moderate"] = "low"
    rationale: str
    screening_action: str
    retrieval_intents: List[str] = Field(default_factory=list)
    allowed_uses: List[str] = Field(default_factory=list)
    # Specific governed source_ids that back this suggestion's feature→condition
    # association; cited inline only when actually retrieved (never a wrong source).
    evidence_source_ids: List[str] = Field(default_factory=list)
    # True when this suggestion is tied to an already-flagged emergency; in that
    # case the report keeps the emergency block on top and suppresses the rest.
    emergency_linked: bool = False


class ScreeningResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # ``enabled``: the global config switch is on.
    # ``requested``: the request opted in (enable_screening_suggestions=True).
    # ``produced``: at least one suggestion was emitted.
    enabled: bool = False
    requested: bool = False
    produced: bool = False
    suggestions: List[ScreeningSuggestion] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
