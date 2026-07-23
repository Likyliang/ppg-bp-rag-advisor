from __future__ import annotations

from contextlib import asynccontextmanager
import os
import re
import time
from uuid import uuid4
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.library import router as library_router
from app.api.routes import router
from app.admin import init_admin_db
from app.admin.db import session_scope
from app.admin.metrics import record_metric
from app.admin.audit import write_audit
from app.admin.security import validate_security_startup


_APP_ENV = os.getenv("APP_ENV", "development").lower()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    validate_security_startup()
    init_admin_db()
    yield


app = FastAPI(
    title="PPG BP RAG-Agent",
    version="0.1.0",
    description="Conservative RAG-Agent for PPG-based blood pressure estimate explanations.",
    docs_url="/docs" if _APP_ENV == "development" else None,
    redoc_url="/redoc" if _APP_ENV == "development" else None,
    openapi_url="/openapi.json" if _APP_ENV == "development" else None,
    lifespan=_lifespan,
)

_origins = [item.strip() for item in os.getenv("APP_CORS_ORIGINS", "").split(",") if item.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-API-Key", "X-Request-ID", "If-Match"],
    )

app.include_router(router, prefix="/api/v1")
app.include_router(library_router, prefix="/api/v1/library")
app.include_router(admin_router, prefix="/api/v1")


@app.middleware("http")
async def request_context_and_anonymous_metrics(request, call_next):
    supplied_request_id = (request.headers.get("x-request-id") or "").strip()
    # Request IDs are persisted with anonymous metrics/audit events.  Accept
    # UUID-shaped correlation IDs only so callers cannot place health text or
    # credentials into this metadata field.
    request_id = (
        supplied_request_id.lower()
        if re.fullmatch(
            r"(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})",
            supplied_request_id,
        )
        else uuid4().hex
    )
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path.startswith("/admin"):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
        )
    sensitive_api = request.url.path.startswith(
        ("/api/v1/admin", "/api/v1/reports", "/api/v1/advisor")
    )
    response.headers.setdefault("Cache-Control", "no-store" if sensitive_api else "no-cache")
    matched_route = request.scope.get("route")
    if matched_route is not None and request.url.path.startswith("/api/") and request.url.path != "/api/v1/health":
        try:
            route_name = getattr(matched_route, "name", None) or request.url.path
            with session_scope() as db:
                record_metric(
                    db,
                    route_name=route_name,
                    method=request.method,
                    status_code=response.status_code,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    generation_mode=str(getattr(request.state, "generation_mode", "")),
                    retrieval_backend=str(getattr(request.state, "retrieval_backend", "")),
                    safety_fallback=bool(getattr(request.state, "safety_fallback", False)),
                )
                if (
                    request.url.path.startswith("/api/v1/library")
                    and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
                ):
                    write_audit(
                        db,
                        principal=getattr(request.state, "admin_principal", None),
                        action=f"library.{route_name}",
                        resource_type="library_api",
                        resource_id=request.path_params.get("source_id") if request.path_params else None,
                        request_id=request_id,
                        status="success" if response.status_code < 400 else "failed",
                        details={"method": request.method, "status_code": response.status_code},
                    )
                elif (
                    request.url.path.startswith("/api/v1/admin")
                    and request.method.upper() not in {"GET", "HEAD", "OPTIONS"}
                    and response.status_code >= 400
                ):
                    # Successful admin mutations write domain-specific audit
                    # events in their handlers. Record rejected/failed attempts
                    # generically here without retaining the request body.
                    write_audit(
                        db,
                        principal=getattr(request.state, "admin_principal", None),
                        action=f"admin.failed.{route_name}",
                        resource_type="admin_api",
                        request_id=request_id,
                        status="failed",
                        details={"method": request.method, "status_code": response.status_code},
                    )
        except Exception:
            # Metrics are deliberately non-blocking and contain no request body.
            pass
    return response

# Vendored static assets (Bootstrap CSS, etc.) for the library admin UI.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.exists():
    app.mount("/api/v1/library/static", StaticFiles(directory=str(_STATIC_DIR)), name="library-static")

_ADMIN_DIST = _STATIC_DIR / "admin_dist"
if _ADMIN_DIST.exists():
    app.mount("/admin", StaticFiles(directory=str(_ADMIN_DIST), html=True), name="admin-spa")
