from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    age: Optional[int] = Field(default=None, ge=0, le=120)
    sex: Optional[Literal["male", "female", "other", "unknown"]] = "unknown"
    height_cm: Optional[float] = Field(default=None, gt=0, le=260)
    weight_kg: Optional[float] = Field(default=None, gt=0, le=400)
    bmi: Optional[float] = Field(default=None, gt=0, le=100)
    smoker: bool = False
    diabetes: bool = False
    kidney_disease: bool = False
    cvd_history: bool = False
    pregnancy: bool = False
    antihypertensive_medication: bool = False
    medication_names: List[str] = Field(default_factory=list)

    @field_validator("medication_names", mode="before")
    @classmethod
    def normalize_medication_names(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


class Symptoms(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chest_pain: bool = False
    shortness_of_breath: bool = False
    back_pain: bool = False
    numbness_or_weakness: bool = False
    vision_change: bool = False
    speech_difficulty: bool = False
    severe_headache: bool = False
    dizziness: bool = False


class PPGMeasurement(BaseModel):
    model_config = ConfigDict(extra="ignore")

    module: str = "CHS-BloodPressure"
    estimated_sbp: Optional[float] = Field(default=None, ge=40, le=260)
    estimated_dbp: Optional[float] = Field(default=None, ge=30, le=180)
    heart_rate: Optional[float] = Field(default=None, ge=20, le=240)
    signal_quality_score: Optional[float] = Field(default=None, ge=0, le=1)
    signal_quality_label: Literal["good", "fair", "poor", "unknown"] = "unknown"
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    capture_duration_sec: Optional[float] = Field(default=None, gt=0)
    ppg_source: Literal["camera_finger", "waveform", "other", "unknown"] = "camera_finger"
    algorithm_version: Optional[str] = None
    calculation_principle: Optional[str] = "camera-based finger PPG estimation"
    timestamp: Optional[datetime] = None

    @field_validator("signal_quality_label", mode="before")
    @classmethod
    def normalize_quality_label(cls, value):
        if value is None or value == "":
            return "unknown"
        value = str(value).strip().lower()
        aliases = {
            "高": "good",
            "好": "good",
            "中": "fair",
            "一般": "fair",
            "低": "poor",
            "差": "poor",
        }
        return aliases.get(value, value)


class MeasurementPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    measurement: PPGMeasurement
    user_profile: UserProfile = Field(default_factory=UserProfile)
    symptoms: Symptoms = Field(default_factory=Symptoms)
    locale: Literal["zh-CN", "en-US", "bilingual"] = "zh-CN"
    guideline_region: Literal["CN", "AHA", "auto"] = "CN"
    user_question: Optional[str] = None
