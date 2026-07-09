from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.library import router as library_router
from app.api.routes import router


app = FastAPI(
    title="PPG BP RAG-Agent",
    version="0.1.0",
    description="Conservative RAG-Agent for PPG-based blood pressure estimate explanations.",
)

app.include_router(router, prefix="/api/v1")
app.include_router(library_router, prefix="/api/v1/library")
app.include_router(admin_router, prefix="/api/v1")

# Vendored static assets (Bootstrap CSS, etc.) for the library admin UI.
_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.exists():
    app.mount("/api/v1/library/static", StaticFiles(directory=str(_STATIC_DIR)), name="library-static")
