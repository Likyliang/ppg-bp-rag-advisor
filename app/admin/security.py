from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Deque, Dict, Iterable, Optional, Set

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.db import get_db
from app.admin.models import AdminSession, AdminUser, ApiClient, utcnow


ADMIN_SESSION_COOKIE = "ppg_admin_session"
ADMIN_CSRF_COOKIE = "ppg_admin_csrf"
VALID_ROLES = {"admin", "curator", "reviewer", "viewer"}
ROLE_PERMISSIONS = {
    "admin": {"*"},
    "curator": {"library:read", "library:draft", "library:edit", "fulltext:write", "jobs:read"},
    "reviewer": {"library:read", "library:publish", "quality:read", "quality:run", "jobs:read"},
    "viewer": {"library:read", "quality:read", "jobs:read", "config:read", "audit:read"},
}

_PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_LOGIN_LOCK = threading.Lock()
_LOGIN_ATTEMPTS: Dict[str, Deque[float]] = defaultdict(deque)
_CLIENT_RATE_LOCK = threading.Lock()
_CLIENT_REQUESTS: Dict[str, Deque[float]] = defaultdict(deque)


@dataclass(frozen=True)
class AdminPrincipal:
    user_id: str
    username: str
    role: str
    session_id: Optional[str] = None
    auth_disabled: bool = False

    def has_permission(self, permission: str) -> bool:
        permissions = ROLE_PERMISSIONS.get(self.role, set())
        return "*" in permissions or permission in permissions


@dataclass(frozen=True)
class ApiClientPrincipal:
    client_id: str
    name: str
    scopes: Set[str]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def admin_auth_disabled() -> bool:
    return _env_bool("ADMIN_AUTH_DISABLED", False)


def validate_security_startup() -> None:
    environment = os.getenv("APP_ENV", "development").strip().lower()
    if environment in {"internal", "production"} and admin_auth_disabled():
        raise RuntimeError("ADMIN_AUTH_DISABLED cannot be enabled in internal or production environments")


def api_client_required() -> bool:
    explicit = os.getenv("REQUIRE_API_CLIENT")
    if explicit is not None:
        return explicit.strip().lower() in {"1", "true", "yes", "on"}
    return os.getenv("APP_ENV", "development").lower() in {"internal", "production"}


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_context(value: Optional[str]) -> Optional[str]:
    return hash_token(value) if value else None


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    return _PASSWORDS.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bool(_PASSWORDS.verify(password_hash, password))
    except (VerifyMismatchError, InvalidHashError):
        return False


def _normalize_dt(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _session_ttl() -> timedelta:
    try:
        hours = max(1, min(72, int(os.getenv("ADMIN_SESSION_HOURS", "8"))))
    except ValueError:
        hours = 8
    return timedelta(hours=hours)


def _secure_cookie(request: Request) -> bool:
    return _env_bool("ADMIN_COOKIE_SECURE", request.url.scheme == "https")


def _prune_attempts(bucket: Deque[float], window_sec: float) -> None:
    cutoff = time.monotonic() - window_sec
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def check_login_rate_limit(remote_addr: str) -> None:
    key = hash_token(remote_addr or "unknown")
    with _LOGIN_LOCK:
        bucket = _LOGIN_ATTEMPTS[key]
        _prune_attempts(bucket, 300)
        if len(bucket) >= 5:
            raise HTTPException(status_code=429, detail="登录尝试过多，请稍后再试")


def record_login_failure(remote_addr: str) -> None:
    key = hash_token(remote_addr or "unknown")
    with _LOGIN_LOCK:
        bucket = _LOGIN_ATTEMPTS[key]
        _prune_attempts(bucket, 300)
        bucket.append(time.monotonic())


def clear_login_failures(remote_addr: str) -> None:
    key = hash_token(remote_addr or "unknown")
    with _LOGIN_LOCK:
        _LOGIN_ATTEMPTS.pop(key, None)


def create_login_session(db: Session, user: AdminUser, request: Request, response: Response) -> None:
    raw_token = secrets.token_urlsafe(32)
    raw_csrf = secrets.token_urlsafe(24)
    ttl = _session_ttl()
    session = AdminSession(
        token_hash=hash_token(raw_token),
        csrf_hash=hash_token(raw_csrf),
        user_id=user.id,
        expires_at=utcnow() + ttl,
        remote_addr_hash=hash_context(request.client.host if request.client else None),
        user_agent_hash=hash_context(request.headers.get("user-agent")),
    )
    db.add(session)
    user.last_login_at = utcnow()
    db.commit()
    max_age = int(ttl.total_seconds())
    secure = _secure_cookie(request)
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        raw_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    response.set_cookie(
        ADMIN_CSRF_COOKIE,
        raw_csrf,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )


def clear_login_session(db: Session, request: Request, response: Response) -> None:
    raw = request.cookies.get(ADMIN_SESSION_COOKIE)
    if raw:
        session = db.scalar(select(AdminSession).where(AdminSession.token_hash == hash_token(raw)))
        if session is not None:
            session.revoked_at = utcnow()
            db.commit()
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")
    response.delete_cookie(ADMIN_CSRF_COOKIE, path="/")


def get_current_principal(request: Request, db: Session = Depends(get_db)) -> AdminPrincipal:
    if admin_auth_disabled():
        principal = AdminPrincipal("development-admin", "development-admin", "admin", auth_disabled=True)
        request.state.admin_principal = principal
        return principal
    raw = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    session = db.scalar(select(AdminSession).where(AdminSession.token_hash == hash_token(raw)))
    now = utcnow()
    if session is None or session.revoked_at is not None or _normalize_dt(session.expires_at) <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录会话已失效")
    user = db.get(AdminUser, session.user_id)
    if user is None or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号已停用")
    session.last_seen_at = now
    db.commit()
    principal = AdminPrincipal(user.id, user.username, user.role, session.id)
    request.state.admin_principal = principal
    return principal


def require_roles(*roles: str) -> Callable:
    allowed = set(roles)

    def dependency(principal: AdminPrincipal = Depends(get_current_principal)) -> AdminPrincipal:
        if principal.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return principal

    return dependency


def require_permission(permission: str) -> Callable:
    def dependency(principal: AdminPrincipal = Depends(get_current_principal)) -> AdminPrincipal:
        if not principal.has_permission(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return principal

    return dependency


def csrf_protect(
    request: Request,
    principal: AdminPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AdminPrincipal:
    return validate_csrf_request(request, principal, db)


def validate_csrf_request(request: Request, principal: AdminPrincipal, db: Session) -> AdminPrincipal:
    if principal.auth_disabled:
        return principal
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(ADMIN_CSRF_COOKIE, "")
    if not header or not cookie or not hmac.compare_digest(header, cookie):
        raise HTTPException(status_code=403, detail="CSRF 校验失败")
    session = db.get(AdminSession, principal.session_id)
    if session is None or not hmac.compare_digest(session.csrf_hash, hash_token(header)):
        raise HTTPException(status_code=403, detail="CSRF 校验失败")
    return principal


def management_request_guard(
    request: Request,
    principal: AdminPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AdminPrincipal:
    method = request.method.upper()
    if method not in {"GET", "HEAD", "OPTIONS"}:
        path = request.url.path
        if principal.role in {"viewer", "reviewer"}:
            raise HTTPException(status_code=403, detail="权限不足")
        if principal.role == "curator":
            admin_only = (
                path.endswith("/trash/empty")
                or "/trash/" in path and method == "DELETE"
                or path.endswith("/rescreen")
                or path.endswith("/ingest")
                or path.endswith("/fulltext/rebuild")
                or request.query_params.get("hard", "false").lower() == "true"
            )
            if admin_only:
                raise HTTPException(status_code=403, detail="该操作仅管理员可执行")
        validate_csrf_request(request, principal, db)
    return principal


def _client_rate_limit(client: ApiClient) -> None:
    now = time.monotonic()
    with _CLIENT_RATE_LOCK:
        bucket = _CLIENT_REQUESTS[client.id]
        _prune_attempts(bucket, 60)
        if len(bucket) >= max(1, client.rate_limit_per_minute):
            raise HTTPException(status_code=429, detail="API Client 调用频率超限")
        bucket.append(now)


def require_api_client(*required_scopes: str) -> Callable:
    required = set(required_scopes)

    def dependency(request: Request, db: Session = Depends(get_db)) -> Optional[ApiClientPrincipal]:
        if not api_client_required():
            return None
        raw = request.headers.get("x-api-key", "")
        if not raw:
            raise HTTPException(status_code=401, detail="缺少 API Key")
        client = db.scalar(select(ApiClient).where(ApiClient.key_hash == hash_token(raw)))
        now = utcnow()
        if (
            client is None
            or not client.active
            or client.revoked_at is not None
            or (client.expires_at is not None and _normalize_dt(client.expires_at) <= now)
        ):
            raise HTTPException(status_code=401, detail="API Key 无效或已过期")
        scopes = set(json.loads(client.scopes_json or "[]"))
        if not required.issubset(scopes) and "*" not in scopes:
            raise HTTPException(status_code=403, detail="API Key 作用域不足")
        _client_rate_limit(client)
        client.last_used_at = now
        db.commit()
        request.state.api_client_id = client.id
        return ApiClientPrincipal(client.id, client.name, scopes)

    return dependency


def generate_api_client_key() -> str:
    return "ppg_" + secrets.token_urlsafe(32)


def scopes_json(scopes: Iterable[str]) -> str:
    return json.dumps(sorted(set(scopes)), ensure_ascii=False)
