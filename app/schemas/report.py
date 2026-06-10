from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InputSummary(BaseModel):
    module: str = "CHS-BloodPressure"
    estimated_sbp: Optional[float] = None
    estimated_dbp: Optional[float] = None
    heart_rate: Optional[float] = None
    signal_quality_score: Optional[float] = None
    signal_quality_label: str = "unknown"
    confidence: Optional[float] = None
    capture_duration_sec: Optional[float] = None
    motion_artifact_score: Optional[float] = None
    finger_coverage_score: Optional[float] = None
    contact_pressure_level: str = "unknown"
    ambient_light_level: str = "unknown"
    ppg_source: str = "unknown"
    algorithm_version: Optional[str] = None
    calculation_principle: Optional[str] = None
    timestamp: Optional[str] = None


class MeasurementStatus(BaseModel):
    is_usable: bool
    quality_level: str
    quality_explanation: str
    warnings: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    bp_category_reference: str
    estimated_bp_category: str
    risk_level: str
    urgency_level: str
    explanation: str


class Recommendations(BaseModel):
    remeasurement: List[str] = Field(default_factory=list)
    device_advice: List[str] = Field(default_factory=list)
    lifestyle: List[str] = Field(default_factory=list)
    medical_consultation: List[str] = Field(default_factory=list)


class SafetyAlert(BaseModel):
    emergency: bool
    message: str


class Evidence(BaseModel):
    source_id: str
    title: str
    url: Optional[str] = None
    used_for: str
    organization: Optional[str] = None
    region: Optional[str] = None
    topic: Optional[str] = None
    language: Optional[str] = None
    evidence_class: Optional[str] = None
    source_quality_score: Optional[float] = None
    allowed_uses: List[str] = Field(default_factory=list)
    review_status: Optional[str] = None
    score: Optional[float] = None
    snippet: Optional[str] = None
    year: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    citation_number: Optional[int] = None


class ReferenceEntry(BaseModel):
    """One finalized bibliography entry: number == order of first citation."""

    number: int
    source_id: str
    title: str
    organization: Optional[str] = None
    year: Optional[str] = None
    evidence_class: Optional[str] = None
    locator: Optional[str] = None
    url: Optional[str] = None
    pages: Optional[str] = None
    snippet: Optional[str] = None
    formatted: str


class RecommendationEvidence(BaseModel):
    group: str
    index: int
    text: str
    required_uses: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    high_trust_required: bool = False
    passed: bool = True
    issues: List[str] = Field(default_factory=list)


class SafetyReview(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    passed: bool = Field(alias="pass")
    issues: List[str] = Field(default_factory=list)
    required_edits: List[str] = Field(default_factory=list)
    severity: str = "none"


class CitationQuality(BaseModel):
    passed: bool = True
    coverage_rate: float = 1.0
    checked_uses: List[str] = Field(default_factory=list)
    missing_uses: List[str] = Field(default_factory=list)
    high_trust_sensitive_uses: bool = True
    recommendation_grounding_rate: float = 1.0
    ungrounded_recommendations: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)


class UiSummary(BaseModel):
    title: str
    status: str
    priority: str
    chips: List[str] = Field(default_factory=list)
    next_actions: List[str] = Field(default_factory=list)


class HealthReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    report_id: str
    mode: str = "user_health_report"
    generation_mode: str = "template_only"
    input_summary: InputSummary
    measurement_status: MeasurementStatus
    risk_assessment: RiskAssessment
    recommendations: Recommendations
    safety_alert: SafetyAlert
    retrieved_evidence: List[Evidence] = Field(default_factory=list)
    references: List[ReferenceEntry] = Field(default_factory=list)
    recommendation_evidence: List[RecommendationEvidence] = Field(default_factory=list)
    citation_quality: CitationQuality = Field(default_factory=CitationQuality)
    ui_summary: Optional[UiSummary] = None
    disclaimer: str
    markdown_report: str
    safety_review: Optional[SafetyReview] = None
    warnings: List[str] = Field(default_factory=list)
