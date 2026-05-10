from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class QualityResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    is_usable: bool
    quality_level: str
    confidence_level: str
    explanation: str
    warnings: List[str] = Field(default_factory=list)


class RuleResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    quality: QualityResult
    estimated_bp_category: str
    bp_category_reference: str
    risk_level: str
    urgency_level: str
    emergency: bool
    emergency_reasons: List[str] = Field(default_factory=list)
    special_population: bool = False
    special_population_reasons: List[str] = Field(default_factory=list)
    recommendation_intents: List[str] = Field(default_factory=list)
    retrieval_intents: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    guideline_region_used: Optional[str] = None
