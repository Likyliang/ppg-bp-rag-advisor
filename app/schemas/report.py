from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InputSummary(BaseModel):
    estimated_sbp: Optional[float] = None
    estimated_dbp: Optional[float] = None
    heart_rate: Optional[float] = None
    signal_quality_label: str = "unknown"
    confidence: Optional[float] = None


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


class SafetyReview(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    passed: bool = Field(alias="pass")
    issues: List[str] = Field(default_factory=list)
    required_edits: List[str] = Field(default_factory=list)
    severity: str = "none"


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
    disclaimer: str
    markdown_report: str
    safety_review: Optional[SafetyReview] = None
    warnings: List[str] = Field(default_factory=list)
