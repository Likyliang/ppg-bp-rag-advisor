from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.admin.models import AuditEvent
from app.admin.security import AdminPrincipal


_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "secret",
    "api_key",
    "key",
    "token",
    "secret_ciphertext",
    "authorization",
    "cookie",
}
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(?:^|_)(?:api_?key|key|token|secret|password|authorization|cookie|credential)(?:$|_)"
)
_SENSITIVE_TEXT = re.compile(
    r"(?i)(?:\bBearer\s+\S+|\bsk-[A-Za-z0-9_-]{8,}|"
    r"\b(?:api[_ -]?key|token|secret|password|authorization|cookie)\s*[:=]\s*\S+)"
)


def is_sensitive_key(value: Any) -> bool:
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return bool(_SENSITIVE_KEY_PATTERN.search(normalized))


def redact_sensitive_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return _SENSITIVE_TEXT.sub("[REDACTED]", str(value))


def stable_hash(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if str(key).lower() in _SENSITIVE_KEYS or is_sensitive_key(key)
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def write_audit(
    db: Session,
    *,
    principal: Optional[AdminPrincipal],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    request_id: Optional[str] = None,
    reason: Optional[str] = None,
    before: Any = None,
    after: Any = None,
    status: str = "success",
    details: Optional[Dict[str, Any]] = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_type="user" if principal else "system",
        actor_id=principal.user_id if principal else None,
        actor_name=principal.username if principal else "system",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        reason=redact_sensitive_text(reason),
        before_hash=stable_hash(before),
        after_hash=stable_hash(after),
        status=status,
        details_json=json.dumps(redact(details or {}), ensure_ascii=False, sort_keys=True, default=str),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
