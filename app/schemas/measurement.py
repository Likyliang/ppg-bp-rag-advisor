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
    # Poincaré-plot descriptors of the inter-beat-interval series. AF tends to be
    # "irregularly irregular": more clusters, larger beat-to-beat stepping, and
    # wider dispersion around the identity line (Sarkar/Lian-style features).
    poincare_cluster_count: Optional[int] = Field(default=None, ge=0, le=1000)
    poincare_dispersion: Optional[float] = Field(default=None, ge=0)
    ibi_stepping_increment_ms: Optional[float] = Field(default=None, ge=0, le=5000)
    poincare_sd1_ms: Optional[float] = Field(default=None, ge=0, le=5000)
    poincare_sd2_ms: Optional[float] = Field(default=None, ge=0, le=5000)

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
    # Beat-to-beat SCG amplitude variation (CV). Elevated in AF (mechanocardiography).
    beat_amplitude_cv: Optional[float] = Field(default=None, ge=0, le=5)

    @field_validator("signal_quality_label", mode="before")
    @classmethod
    def normalize_scg_quality_label(cls, value):
        if value is None or value == "":
            return "unknown"
        value = str(value).strip().lower()
        aliases = {"高": "good", "好": "good", "中": "fair", "一般": "fair", "低": "poor", "差": "poor"}
        return aliases.get(value, value)


class PPGMorphologyFeatures(BaseModel):
    """Single-pulse PPG waveform morphology (scaffold for later screening tiers).

    These describe pulse-wave shape and arterial-stiffness/reflection indices used
    in the vascular-aging literature. Carried structurally now; not yet consumed
    by a screening condition until thresholds are calibrated. Optional by design.
    """

    model_config = ConfigDict(extra="ignore")

    available: bool = False
    systolic_peak_amplitude: Optional[float] = Field(default=None, ge=0)
    diastolic_peak_amplitude: Optional[float] = Field(default=None, ge=0)
    dicrotic_notch_present: Optional[bool] = None
    pulse_width_ms: Optional[float] = Field(default=None, ge=0, le=5000)
    crest_time_ms: Optional[float] = Field(default=None, ge=0, le=2000)
    pulse_area: Optional[float] = Field(default=None, ge=0)
    # Arterial-stiffness / reflection indices (units per source convention).
    stiffness_index: Optional[float] = Field(default=None, ge=0)
    reflection_index: Optional[float] = Field(default=None, ge=0, le=100)
    augmentation_index: Optional[float] = Field(default=None, ge=-100, le=100)


class PPGDerivedFeatures(BaseModel):
    """Derivative-based and PPG-derived physiology (scaffold for later tiers).

    Includes SDPPG (second-derivative) aging-index family and oximetry/respiratory
    derivatives. Carried structurally now; conditions that consume them (vascular
    aging, sleep-apnea screening) are deferred until data + thresholds exist.
    """

    model_config = ConfigDict(extra="ignore")

    available: bool = False
    # SDPPG (acceleration plethysmogram) a–e wave ratios / aging index.
    sdppg_b_a_ratio: Optional[float] = Field(default=None, ge=-10, le=10)
    sdppg_d_a_ratio: Optional[float] = Field(default=None, ge=-10, le=10)
    sdppg_aging_index: Optional[float] = Field(default=None, ge=-10, le=10)
    # Oximetry / respiratory derivatives (need continuous / nightly data to be useful).
    spo2: Optional[float] = Field(default=None, ge=0, le=100)
    oxygen_desaturation_index: Optional[float] = Field(default=None, ge=0, le=200)
    respiratory_rate_bpm: Optional[float] = Field(default=None, ge=0, le=80)
    perfusion_index: Optional[float] = Field(default=None, ge=0, le=100)
    # Pulse-wave-amplitude drop index: PWA reductions per hour (autonomic arousals).
    pwa_drop_index: Optional[float] = Field(default=None, ge=0, le=200)


class MeasurementPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    measurement: PPGMeasurement
    rhythm: RhythmFeatures = Field(default_factory=RhythmFeatures)
    cardiac_vibration: CardiacVibrationFeatures = Field(default_factory=CardiacVibrationFeatures)
    ppg_morphology: PPGMorphologyFeatures = Field(default_factory=PPGMorphologyFeatures)
    ppg_derived: PPGDerivedFeatures = Field(default_factory=PPGDerivedFeatures)
    user_profile: UserProfile = Field(default_factory=UserProfile)
    symptoms: Symptoms = Field(default_factory=Symptoms)
    locale: Literal["zh-CN", "en-US", "bilingual"] = "zh-CN"
    guideline_region: Literal["CN", "AHA", "auto"] = "CN"
    user_question: Optional[str] = None
    # Opt-in per request: emit "建议进一步排查" screening suggestions (never a
    # diagnosis). Defaults to False so existing reports are byte-for-byte unchanged.
    enable_screening_suggestions: bool = False
