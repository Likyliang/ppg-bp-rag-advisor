from __future__ import annotations

import os
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
    send_fulltext: bool


def resolve_project_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


@lru_cache(maxsize=32)
def load_yaml_config(relative_path: str) -> Dict[str, Any]:
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


def load_openai_embedding_config() -> OpenAIEmbeddingConfig:
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
    return EvalLlmConfig(
        provider=os.getenv("EVAL_LLM_PROVIDER", "openai_compatible"),
        api_key=os.getenv("EVAL_LLM_API_KEY", ""),
        base_url=os.getenv("EVAL_LLM_BASE_URL", "").rstrip("/"),
        model=os.getenv("EVAL_LLM_MODEL", "gpt-5.5"),
        timeout_sec=_env_float("EVAL_LLM_TIMEOUT_SEC", 60.0),
        max_concurrency=max(1, _env_int("EVAL_LLM_MAX_CONCURRENCY", 2)),
        temperature=_env_float("EVAL_LLM_TEMPERATURE", 0.0),
        max_tokens=max(1, _env_int("EVAL_LLM_MAX_TOKENS", 1200)),
        send_fulltext=_env_bool("EVAL_LLM_SEND_FULLTEXT", False),
    )
