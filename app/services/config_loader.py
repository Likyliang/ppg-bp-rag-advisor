from __future__ import annotations

import os
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class OpenAIEmbeddingConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    dimensions: int
    batch_size: int
    input_scope: str


@dataclass(frozen=True)
class EvalLlmConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    timeout_sec: float
    max_concurrency: int
    temperature: float
    max_tokens: int
    min_interval_sec: float
    send_fulltext: bool


@dataclass(frozen=True)
class ReportLlmConfig:
    provider: str
    api_key: str
    base_url: str
    model: str
    timeout_sec: float
    max_concurrency: int
    max_tokens: int
    temperature: float
    min_interval_sec: float
    anthropic_version: str
    enabled: bool
    configured: bool = False


@dataclass(frozen=True)
class CrossrefConfig:
    base_url: str
    timeout_sec: float
    enabled: bool
    configured: bool = False


def resolve_project_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


@lru_cache(maxsize=32)
def load_yaml_config(relative_path: str) -> Dict[str, Any]:
    # Admin config drafts are regression-tested in a child process through a
    # JSON overlay. The candidate never needs to replace the active YAML file.
    raw_overrides = os.getenv("APP_CONFIG_OVERRIDES_JSON", "")
    if raw_overrides:
        try:
            override = json.loads(raw_overrides).get(relative_path)
        except (TypeError, ValueError):
            override = None
        if isinstance(override, dict):
            return override
    path = resolve_project_path(relative_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def development_override(name: str, default: str = "") -> str:
    """Return experiment/test overrides only outside governed deployments.

    Internal and production services take algorithm and safety behavior from
    the published YAML/configuration records. Environment switches remain
    available for local experiments and the offline quality harness, but they
    cannot silently override an administrator-published setting in deployment.
    """

    if os.getenv("APP_ENV", "development").strip().lower() in {"internal", "production"}:
        return default
    return os.getenv(name, default)


def advisor_session_ttl_hours() -> int:
    return max(1, min(168, _env_int("ADVISOR_SESSION_TTL_HOURS", 24)))


def load_openai_embedding_config() -> OpenAIEmbeddingConfig:
    try:
        from app.admin.integration_service import runtime_integration

        profile = runtime_integration("embedding")
    except Exception:
        profile = None
    if profile is not None:
        return OpenAIEmbeddingConfig(
            provider=profile.get("provider") or "openai",
            api_key=profile.get("secret", "") if profile.get("enabled") else "",
            base_url=str(profile.get("base_url") or "https://api.openai.com/v1").rstrip("/"),
            model=profile.get("model") or "text-embedding-3-small",
            dimensions=int(profile.get("settings", {}).get("dimensions", 1536)),
            batch_size=max(1, int(profile.get("settings", {}).get("batch_size", 64))),
            input_scope=str(profile.get("settings", {}).get("input_scope", "processed_chunks")),
        )
    return OpenAIEmbeddingConfig(
        provider=os.getenv("EMBEDDING_PROVIDER", "openai"),
        api_key=os.getenv("OPENAI_EMBEDDING_API_KEY", ""),
        base_url=os.getenv("OPENAI_EMBEDDING_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        dimensions=_env_int("OPENAI_EMBEDDING_DIMENSIONS", 1536),
        batch_size=max(1, _env_int("OPENAI_EMBEDDING_BATCH_SIZE", 64)),
        input_scope=os.getenv("OPENAI_EMBEDDING_INPUT_SCOPE", "processed_chunks"),
    )


def load_eval_llm_config() -> EvalLlmConfig:
    try:
        from app.admin.integration_service import runtime_integration

        profile = runtime_integration("evaluation")
    except Exception:
        profile = None
    if profile is not None:
        return EvalLlmConfig(
            provider=profile.get("provider") or "openai_compatible",
            api_key=profile.get("secret", "") if profile.get("enabled") else "",
            base_url=str(profile.get("base_url") or "").rstrip("/"),
            model=profile.get("model") or "gpt-5.5",
            timeout_sec=float(profile.get("timeout_sec") or 60.0),
            max_concurrency=max(1, int(profile.get("max_concurrency") or 2)),
            temperature=float(profile.get("settings", {}).get("temperature", 0.0)),
            max_tokens=max(1, int(profile.get("settings", {}).get("max_tokens", 1200))),
            min_interval_sec=max(0.0, float(profile.get("settings", {}).get("min_interval_sec", 1.5))),
            # V1 invariant: third-party evaluation never receives full text.
            send_fulltext=False,
        )
    return EvalLlmConfig(
        provider=os.getenv("EVAL_LLM_PROVIDER", "openai_compatible"),
        api_key=os.getenv("EVAL_LLM_API_KEY", ""),
        base_url=os.getenv("EVAL_LLM_BASE_URL", "").rstrip("/"),
        model=os.getenv("EVAL_LLM_MODEL", "gpt-5.5"),
        timeout_sec=_env_float("EVAL_LLM_TIMEOUT_SEC", 60.0),
        max_concurrency=max(1, _env_int("EVAL_LLM_MAX_CONCURRENCY", 2)),
        temperature=_env_float("EVAL_LLM_TEMPERATURE", 0.0),
        max_tokens=max(1, _env_int("EVAL_LLM_MAX_TOKENS", 1200)),
        min_interval_sec=max(0.0, _env_float("EVAL_LLM_MIN_INTERVAL_SEC", 1.5)),
        # V1 governance invariant: evaluation providers never receive PDF full
        # text. The environment flag remains documented for old experiments
        # but is intentionally ignored by the application runtime.
        send_fulltext=False,
    )


def load_report_llm_config() -> ReportLlmConfig:
    try:
        from app.admin.integration_service import runtime_integration

        profile = runtime_integration("report_llm")
    except Exception:
        profile = None
    if profile is not None:
        active = bool(profile.get("enabled") and profile.get("secret"))
        settings = profile.get("settings", {})
        return ReportLlmConfig(
            provider=str(profile.get("provider") or "mock") if active else "mock",
            api_key=str(profile.get("secret") or "") if active else "",
            base_url=str(profile.get("base_url") or "").rstrip("/"),
            model=str(profile.get("model") or ""),
            timeout_sec=float(profile.get("timeout_sec") or 30.0),
            max_concurrency=max(1, int(profile.get("max_concurrency") or 1)),
            max_tokens=max(1, int(settings.get("max_tokens", 2400))),
            temperature=float(settings.get("temperature", 0.4)),
            min_interval_sec=max(0.0, float(settings.get("min_interval_sec", 0.0))),
            anthropic_version=str(settings.get("anthropic_version", "2023-06-01")),
            enabled=active,
            configured=True,
        )
    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    if provider == "deepseek":
        key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY", "")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    elif provider in {"anthropic", "claude"}:
        key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY", "")
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    else:
        key = os.getenv("LLM_API_KEY", "")
        base_url = os.getenv("LLM_BASE_URL", "")
        model = os.getenv("LLM_MODEL", "gpt-5.5")
    return ReportLlmConfig(
        provider=provider,
        api_key=key,
        base_url=base_url.rstrip("/"),
        model=model,
        timeout_sec=_env_float("LLM_TIMEOUT_SEC", 30.0),
        max_concurrency=max(1, _env_int("LLM_MAX_CONCURRENCY", 1)),
        max_tokens=max(1, _env_int("ANTHROPIC_MAX_TOKENS", 2400)),
        temperature=_env_float("ANTHROPIC_TEMPERATURE", 0.4),
        min_interval_sec=max(0.0, _env_float("LLM_MIN_INTERVAL_SEC", 0.0)),
        anthropic_version=os.getenv("ANTHROPIC_VERSION", "2023-06-01"),
        enabled=bool(key and provider != "mock"),
        configured=False,
    )


def load_crossref_config() -> CrossrefConfig:
    try:
        from app.admin.integration_service import runtime_integration

        profile = runtime_integration("crossref")
    except Exception:
        profile = None
    if profile is not None:
        return CrossrefConfig(
            base_url=str(profile.get("base_url") or "https://api.crossref.org").rstrip("/"),
            timeout_sec=float(profile.get("timeout_sec") or 8.0),
            enabled=bool(profile.get("enabled")),
            configured=True,
        )
    return CrossrefConfig(
        base_url=os.getenv("CROSSREF_BASE_URL", "https://api.crossref.org").rstrip("/"),
        timeout_sec=_env_float("CROSSREF_TIMEOUT_SEC", 8.0),
        enabled=True,
        configured=False,
    )


def clear_config_caches() -> None:
    load_yaml_config.cache_clear()
    try:
        from app.services import advisor, retriever

        advisor._question_bank.cache_clear()
        advisor._question_meta.cache_clear()
        retriever._load_chunks_cached.cache_clear()
        retriever._load_vector_index.cache_clear()
        retriever._load_fulltext_chunks_cached.cache_clear()
    except Exception:
        # Cache clearing is best-effort during import/startup; active reads use
        # file signatures as an additional guard.
        pass
