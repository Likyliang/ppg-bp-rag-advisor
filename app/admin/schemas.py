from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.admin.audit import redact_sensitive_text


AdminRole = Literal["admin", "curator", "reviewer", "viewer"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,80}$")
    password: str = Field(min_length=12, max_length=256)
    role: AdminRole


class UserUpdate(BaseModel):
    role: Optional[AdminRole] = None
    active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=12, max_length=256)


class ApiClientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    scopes: List[str] = Field(default_factory=lambda: ["reports:write", "advisor:write"])
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)
    expires_at: Optional[datetime] = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: List[str]) -> List[str]:
        allowed = {"*", "reports:write", "advisor:write", "kb:search"}
        invalid = set(value) - allowed
        if invalid:
            raise ValueError(f"unsupported scopes: {sorted(invalid)}")
        return sorted(set(value))


class LiteratureDraftCreate(BaseModel):
    source: Dict[str, Any]


class LiteratureDraftPatch(BaseModel):
    source: Dict[str, Any]


class LiteratureRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def redact_credentials(cls, value):
        return redact_sensitive_text(str(value))


class ConfigDraftCreate(BaseModel):
    content: Dict[str, Any]
    reason: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def redact_credentials(cls, value):
        return redact_sensitive_text(str(value)) if value is not None else None


class ConfigPublishRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
    expected_revision: str = Field(min_length=64, max_length=64)
    confirmation: str = Field(min_length=1, max_length=120)

    @field_validator("reason", mode="before")
    @classmethod
    def redact_credentials(cls, value):
        return redact_sensitive_text(str(value))


class ConfigRollbackRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def redact_credentials(cls, value):
        return redact_sensitive_text(str(value))


IntegrationChannel = Literal["report_llm", "embedding", "evaluation", "crossref"]


class IntegrationUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=40)
    base_url: str = Field(default="", max_length=1000)
    model: str = Field(default="", max_length=160)
    timeout_sec: float = Field(default=30, ge=1, le=300)
    max_concurrency: int = Field(default=1, ge=1, le=32)
    enabled: bool = False
    settings: Dict[str, Any] = Field(default_factory=dict)


class IntegrationSecretUpdate(BaseModel):
    secret: str = Field(min_length=8, max_length=4096)


JobType = Literal[
    "rescreen",
    "ingest_chunks",
    "build_chroma",
    "build_fulltext",
    "build_openai_processed",
    "build_openai_fulltext",
    "kb_audit",
    "quality_gate",
    "retrieval_evaluation",
    "report_evaluation",
    "api_experiment",
]


class JobCreate(BaseModel):
    job_type: JobType
    parameters: Dict[str, Any] = Field(default_factory=dict)
