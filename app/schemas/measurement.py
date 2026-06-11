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
    province: Optional[str] = None
    residence_area: Literal["urban", "rural", "unknown"] = "unknown"
    primary_care_preference: Literal[
        "community_health_center",
        "township_health_center",
        "hospital_outpatient",
        "unknown",
    ] = "unknown"

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
    motion_artifact_score: Optional[float] = Field(default=None, ge=0, le=1)
    finger_coverage_score: Optional[float] = Field(default=None, ge=0, le=1)
    contact_pressure_level: Literal["low", "normal", "high", "unstable", "unknown"] = "unknown"
    ambient_light_level: Literal["dim", "normal", "bright", "unstable", "unknown"] = "unknown"
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

    @field_validator("contact_pressure_level", mode="before")
    @classmethod
    def normalize_contact_pressure_level(cls, value):
        if value is None or value == "":
            return "unknown"
        value = str(value).strip().lower()
        aliases = {
            "偏低": "low",
            "低": "low",
            "过松": "low",
            "loose": "low",
            "偏高": "high",
            "高": "high",
            "过紧": "high",
            "tight": "high",
            "正常": "normal",
            "合适": "normal",
            "适中": "normal",
            "不稳定": "unstable",
            "波动": "unstable",
        }
        return aliases.get(value, value)

    @field_validator("ambient_light_level", mode="before")
    @classmethod
    def normalize_ambient_light_level(cls, value):
        if value is None or value == "":
            return "unknown"
        value = str(value).strip().lower()
        aliases = {
            "暗": "dim",
            "偏暗": "dim",
            "过暗": "dim",
            "弱光": "dim",
            "亮": "bright",
            "偏亮": "bright",
            "过亮": "bright",
            "强光": "bright",
            "正常": "normal",
            "稳定": "normal",
            "不稳定": "unstable",
            "闪烁": "unstable",
            "变化": "unstable",
        }
        return aliases.get(value, value)


class RhythmFeatures(BaseModel):
    """Beat-to-beat rhythm / variability features derived from the PPG pulse train.

    These describe *rhythm regularity*, not blood pressure. They are the inputs
    that let the screening layer suggest (never diagnose) an arrhythmia work-up.
    Everything is optional and defaults to unknown so older payloads stay valid.
    """

    model_config = ConfigDict(extra="ignore")

    available: bool = False
    pulse_rhythm: Literal["regular", "irregular", "unknown"] = "unknown"
    # Coefficient of variation of inter-beat intervals (SD/mean). Higher = less regular.
    ibi_cv: Optional[float] = Field(default=None, ge=0, le=5)
    # Fraction of beats flagged as ectopic / premature (suspected PAC/PVC).
    ectopic_beat_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    pulse_pause_detected: Optional[bool] = None
    # Heart-rate-variability time-domain metrics (ms), if the upstream computes them.
    hrv_sdnn_ms: Optional[float] = Field(default=None, ge=0, le=2000)
    hrv_rmssd_ms: Optional[float] = Field(default=None, ge=0, le=2000)
    valid_beat_count: Optional[int] = Field(default=None, ge=0, le=100000)

    @field_validator("pulse_rhythm", mode="before")
    @classmethod
    def normalize_pulse_rhythm(cls, value):
        if value is None or value == "":
            return "unknown"
        value = str(value).strip().lower()
        aliases = {
            "规则": "regular",
            "规整": "regular",
            "齐": "regular",
            "整齐": "regular",
            "normal": "regular",
            "不规则": "irregular",
            "不齐": "irregular",
            "紊乱": "irregular",
            "irregularly_irregular": "irregular",
        }
        return aliases.get(value, value)


class CardiacVibrationFeatures(BaseModel):
    """Seismocardiography / 心振 (chest-wall cardiac-vibration) features.

    SCG captures the mechanical activity of the heart from chest accelerometer
    signals. These features describe cardiac timing/quality, **not** a diagnosis.
    The screening layer uses them only to suggest a professional work-up, with
    research-grade timing intervals capped at low confidence. Optional by design.
    """

    model_config = ConfigDict(extra="ignore")

    available: bool = False
    signal_quality_score: Optional[float] = Field(default=None, ge=0, le=1)
    signal_quality_label: Literal["good", "fair", "poor", "unknown"] = "unknown"
    motion_artifact_score: Optional[float] = Field(default=None, ge=0, le=1)
    sensor_site: Literal["sternum", "chest", "wrist", "other", "unknown"] = "unknown"
    beat_count: Optional[int] = Field(default=None, ge=0, le=100000)
    # Cardiac timing intervals (ms). Research-grade; never used for diagnosis.
    pep_ms: Optional[float] = Field(default=None, ge=0, le=600)  # pre-ejection period
    lvet_ms: Optional[float] = Field(default=None, ge=0, le=900)  # LV ejection time
    ao_ac_interval_ms: Optional[float] = Field(default=None, ge=0, le=1200)
    # Ratio of first to second heart-sound vibration amplitude.
    s1_s2_amplitude_ratio: Optional[float] = Field(default=None, ge=0, le=20)
    # Pulse-transit / pulse-arrival time derived from SCG↔PPG fusion (ms).
    ptt_ms: Optional[float] = Field(default=None, ge=0, le=1000)

    @field_validator("signal_quality_label", mode="before")
    @classmethod
    def normalize_scg_quality_label(cls, value):
        if value is None or value == "":
            return "unknown"
        value = str(value).strip().lower()
        aliases = {"高": "good", "好": "good", "中": "fair", "一般": "fair", "低": "poor", "差": "poor"}
        return aliases.get(value, value)


class MeasurementPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    measurement: PPGMeasurement
    rhythm: RhythmFeatures = Field(default_factory=RhythmFeatures)
    cardiac_vibration: CardiacVibrationFeatures = Field(default_factory=CardiacVibrationFeatures)
    user_profile: UserProfile = Field(default_factory=UserProfile)
    symptoms: Symptoms = Field(default_factory=Symptoms)
    locale: Literal["zh-CN", "en-US", "bilingual"] = "zh-CN"
    guideline_region: Literal["CN", "AHA", "auto"] = "CN"
    user_question: Optional[str] = None
    # Opt-in per request: emit "建议进一步排查" screening suggestions (never a
    # diagnosis). Defaults to False so existing reports are byte-for-byte unchanged.
    enable_screening_suggestions: bool = False
