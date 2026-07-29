from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import IntegrationProfile, utcnow


CHANNEL_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "report_llm": {
        "provider": "mock",
        "base_url": "",
        "model": "",
        "timeout_sec": 30.0,
        "max_concurrency": 1,
        "enabled": False,
        "settings": {
            "max_tokens": 2400,
            "temperature": 0.4,
            "min_interval_sec": 0.0,
            "anthropic_version": "2023-06-01",
        },
    },
    "embedding": {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "text-embedding-3-small",
        "timeout_sec": 60.0,
        "max_concurrency": 2,
        "enabled": False,
        "settings": {"dimensions": 1536, "batch_size": 64, "input_scope": "processed_chunks"},
    },
    "evaluation": {
        "provider": "openai_compatible",
        "base_url": "",
        "model": "gpt-5.5",
        "timeout_sec": 60.0,
        "max_concurrency": 2,
        "enabled": False,
        "settings": {
            "temperature": 0.0,
            "max_tokens": 1200,
            "min_interval_sec": 1.5,
            "send_fulltext": False,
        },
    },
    "crossref": {
        "provider": "crossref",
        "base_url": "https://api.crossref.org",
        "model": "",
        "timeout_sec": 15.0,
        "max_concurrency": 2,
        "enabled": True,
        "settings": {},
    },
}

CHANNEL_PROVIDERS = {
    "report_llm": {"mock", "deepseek", "anthropic", "claude", "openai_compatible"},
    "embedding": {"openai"},
    "evaluation": {"openai_compatible"},
    "crossref": {"crossref"},
}

_SENSITIVE_SETTING_KEY = re.compile(
    r"(?i)(?:^|_)(?:api_?key|secret|token|password|authorization|cookie|credential)(?:$|_)"
)


class SecretConfigurationError(RuntimeError):
    pass


def generate_master_key() -> str:
    return Fernet.generate_key().decode("ascii")


def _fernet() -> Fernet:
    key = os.getenv("ADMIN_SECRET_MASTER_KEY", "").strip()
    if not key:
        raise SecretConfigurationError("ADMIN_SECRET_MASTER_KEY 未配置，禁止保存或读取后台密钥")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise SecretConfigurationError("ADMIN_SECRET_MASTER_KEY 格式无效") from exc


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: Optional[str]) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretConfigurationError("密钥无法解密，请检查主密钥配置") from exc


def _validate_base_url(url: str, *, allow_empty: bool = False) -> str:
    value = (url or "").strip().rstrip("/")
    if not value and allow_empty:
        return ""
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("base_url 必须是无内嵌凭证的 HTTP(S) 地址")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("非本机外部 API 必须使用 HTTPS")
    return value


def _validate_settings(channel: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    settings = dict(raw or {})
    for key in settings:
        normalized = str(key).lower().replace("-", "_")
        if _SENSITIVE_SETTING_KEY.search(normalized):
            raise ValueError(f"settings.{key} 可能包含凭证；请使用独立密钥接口")
    allowed = {
        "report_llm": {"max_tokens", "temperature", "min_interval_sec", "anthropic_version"},
        "embedding": {"dimensions", "batch_size", "input_scope"},
        "evaluation": {"temperature", "max_tokens", "min_interval_sec", "send_fulltext"},
        "crossref": set(),
    }[channel]
    unknown = set(settings) - allowed
    if unknown:
        raise ValueError(f"{channel} 不支持 settings 字段: {sorted(unknown)}")
    if channel == "report_llm":
        max_tokens = int(settings.get("max_tokens", 2400))
        temperature = float(settings.get("temperature", 0.4))
        min_interval = float(settings.get("min_interval_sec", 0.0))
        version = str(settings.get("anthropic_version", "2023-06-01"))
        if not 1 <= max_tokens <= 10000:
            raise ValueError("report_llm max_tokens 必须位于 1..10000")
        if not 0 <= temperature <= 2:
            raise ValueError("report_llm temperature 必须位于 0..2")
        if not 0 <= min_interval <= 60:
            raise ValueError("report_llm min_interval_sec 必须位于 0..60")
        if not version or len(version) > 40:
            raise ValueError("report_llm anthropic_version 非法")
        return {
            "max_tokens": max_tokens,
            "temperature": temperature,
            "min_interval_sec": min_interval,
            "anthropic_version": version,
        }
    if channel == "embedding":
        dimensions = int(settings.get("dimensions", 1536))
        batch_size = int(settings.get("batch_size", 64))
        input_scope = str(settings.get("input_scope", "processed_chunks"))
        if not 64 <= dimensions <= 3072:
            raise ValueError("embedding dimensions 必须位于 64..3072")
        if not 1 <= batch_size <= 512:
            raise ValueError("embedding batch_size 必须位于 1..512")
        if input_scope not in {"processed_chunks", "fulltext_chunks"}:
            raise ValueError("embedding input_scope 非法")
        return {"dimensions": dimensions, "batch_size": batch_size, "input_scope": input_scope}
    if channel == "evaluation":
        temperature = float(settings.get("temperature", 0.0))
        max_tokens = int(settings.get("max_tokens", 1200))
        min_interval = float(settings.get("min_interval_sec", 1.5))
        if not 0 <= temperature <= 2:
            raise ValueError("evaluation temperature 必须位于 0..2")
        if not 1 <= max_tokens <= 10000:
            raise ValueError("evaluation max_tokens 必须位于 1..10000")
        if not 0 <= min_interval <= 60:
            raise ValueError("evaluation min_interval_sec 必须位于 0..60")
        if settings.get("send_fulltext") not in {None, False}:
            raise ValueError("evaluation.send_fulltext 在 V1 固定为 false")
        return {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "min_interval_sec": min_interval,
            "send_fulltext": False,
        }
    return {}


def _profile_dict(row: Optional[IntegrationProfile], channel: str, *, include_secret: bool = False) -> Dict[str, Any]:
    default = deepcopy(CHANNEL_DEFAULTS[channel])
    if row is not None:
        default.update(
            {
                "provider": row.provider,
                "base_url": row.base_url,
                "model": row.model,
                "timeout_sec": row.timeout_sec,
                "max_concurrency": row.max_concurrency,
                "enabled": row.enabled,
                "settings": json.loads(row.settings_json or "{}"),
            }
        )
    # The full-text evaluation switch is deliberately not configurable in V1.
    if channel == "evaluation":
        default.setdefault("settings", {})["send_fulltext"] = False
    default.update(
        {
            "channel": channel,
            "secret_configured": bool(row and row.secret_ciphertext),
            "secret_updated_at": row.secret_updated_at.isoformat() if row and row.secret_updated_at else None,
            "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        }
    )
    if include_secret and row and row.secret_ciphertext:
        default["secret"] = decrypt_secret(row.secret_ciphertext)
    return default


def list_integrations(db: Session) -> List[Dict[str, Any]]:
    rows = {row.channel: row for row in db.scalars(select(IntegrationProfile)).all()}
    return [_profile_dict(rows.get(channel), channel) for channel in CHANNEL_DEFAULTS]


def update_integration(db: Session, channel: str, payload: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    if channel not in CHANNEL_DEFAULTS:
        raise KeyError(channel)
    provider = str(payload.get("provider") or "")
    if provider not in CHANNEL_PROVIDERS[channel]:
        raise ValueError(f"{channel} 不支持 provider={provider}")
    allow_empty = channel == "report_llm" and provider == "mock"
    base_url = _validate_base_url(str(payload.get("base_url") or ""), allow_empty=allow_empty)
    try:
        settings = _validate_settings(channel, dict(payload.get("settings") or {}))
    except (TypeError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    row = db.get(IntegrationProfile, channel)
    if row is None:
        row = IntegrationProfile(channel=channel, provider=provider)
        db.add(row)
    row.provider = provider
    row.base_url = base_url
    row.model = str(payload.get("model") or "")
    row.timeout_sec = float(payload.get("timeout_sec") or CHANNEL_DEFAULTS[channel]["timeout_sec"])
    row.max_concurrency = int(payload.get("max_concurrency") or CHANNEL_DEFAULTS[channel]["max_concurrency"])
    row.enabled = bool(payload.get("enabled"))
    row.settings_json = json.dumps(settings, ensure_ascii=False, sort_keys=True)
    row.updated_by = user_id
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return _profile_dict(row, channel)


def set_integration_secret(db: Session, channel: str, secret: str, user_id: str) -> Dict[str, Any]:
    if channel not in CHANNEL_DEFAULTS or channel == "crossref":
        raise ValueError("该集成不接受 API Key")
    row = db.get(IntegrationProfile, channel)
    if row is None:
        default = CHANNEL_DEFAULTS[channel]
        row = IntegrationProfile(
            channel=channel,
            provider=default["provider"],
            base_url=default["base_url"],
            model=default["model"],
            timeout_sec=default["timeout_sec"],
            max_concurrency=default["max_concurrency"],
            enabled=default["enabled"],
            settings_json=json.dumps(default["settings"], ensure_ascii=False),
        )
        db.add(row)
    row.secret_ciphertext = encrypt_secret(secret)
    row.secret_updated_at = utcnow()
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return _profile_dict(row, channel)


def clear_integration_secret(db: Session, channel: str, user_id: str) -> Dict[str, Any]:
    row = db.get(IntegrationProfile, channel)
    if row is None:
        raise KeyError(channel)
    row.secret_ciphertext = None
    row.secret_updated_at = None
    row.updated_by = user_id
    db.commit()
    return _profile_dict(row, channel)


def runtime_integration(channel: str) -> Optional[Dict[str, Any]]:
    """Return a DB-backed profile, or None only when no profile exists.

    Once an operator has created a profile, disabled/mis-keyed state must fail
    closed instead of silently reviving an old environment-variable secret.
    """

    if channel not in CHANNEL_DEFAULTS:
        return None
    from app.admin.db import session_scope

    try:
        with session_scope() as db:
            row = db.get(IntegrationProfile, channel)
            if row is None:
                return None
            profile = _profile_dict(row, channel)
            profile["secret"] = ""
            if row.enabled and row.secret_ciphertext:
                try:
                    profile["secret"] = decrypt_secret(row.secret_ciphertext)
                except SecretConfigurationError:
                    profile["secret_error"] = True
            return profile
    except Exception:
        # Report/retrieval paths must retain their conservative environment or
        # offline fallback when the admin database is unavailable.
        return None


def _safe_http_error(response: requests.Response) -> Dict[str, Any]:
    return {"ok": False, "error_code": f"http_{response.status_code}", "message": "外部服务返回错误"}


def test_integration(db: Session, channel: str) -> Dict[str, Any]:
    if channel not in CHANNEL_DEFAULTS:
        raise KeyError(channel)
    row = db.get(IntegrationProfile, channel)
    profile = _profile_dict(row, channel, include_secret=True)
    if not profile.get("enabled"):
        return {"ok": False, "error_code": "disabled", "message": "集成通道未启用"}
    if channel == "report_llm" and profile.get("provider") == "mock":
        return {"ok": True, "latency_ms": 0.0, "tested_with": "local_mock"}
    if channel not in {"crossref"} and not profile.get("secret"):
        return {"ok": False, "error_code": "secret_missing", "message": "尚未配置 API Key"}
    started = utcnow()
    timeout = min(float(profile.get("timeout_sec") or 30), 30.0)
    try:
        if channel == "crossref":
            response = requests.get(
                f"{profile['base_url']}/works",
                params={"query.title": "blood pressure health education", "rows": 0},
                timeout=timeout,
                allow_redirects=False,
            )
        elif channel == "embedding":
            response = requests.post(
                f"{profile['base_url']}/embeddings",
                headers={"Authorization": f"Bearer {profile.get('secret', '')}"},
                json={"model": profile["model"], "input": ["synthetic connectivity test"]},
                timeout=timeout,
                allow_redirects=False,
            )
        elif profile["provider"] in {"anthropic", "claude"}:
            response = requests.post(
                f"{profile['base_url']}/v1/messages",
                headers={
                    "x-api-key": profile.get("secret", ""),
                    "anthropic-version": profile.get("settings", {}).get("anthropic_version", "2023-06-01"),
                    "content-type": "application/json",
                },
                json={"model": profile["model"], "max_tokens": 8, "messages": [{"role": "user", "content": "Reply OK"}]},
                timeout=timeout,
                allow_redirects=False,
            )
        else:
            response = requests.post(
                f"{profile['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {profile.get('secret', '')}", "content-type": "application/json"},
                json={"model": profile["model"], "max_tokens": 8, "messages": [{"role": "user", "content": "Reply OK"}]},
                timeout=timeout,
                allow_redirects=False,
            )
        latency_ms = round((utcnow() - started).total_seconds() * 1000, 1)
        if not response.ok:
            result = _safe_http_error(response)
            result["latency_ms"] = latency_ms
            return result
        return {"ok": True, "latency_ms": latency_ms, "tested_with": "synthetic_payload"}
    except requests.Timeout:
        return {"ok": False, "error_code": "timeout", "message": "连接超时"}
    except requests.RequestException:
        return {"ok": False, "error_code": "connection_error", "message": "无法连接外部服务"}
