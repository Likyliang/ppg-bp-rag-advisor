from __future__ import annotations

from fastapi import FastAPI

from app.api.library import router as library_router
from app.api.routes import router


app = FastAPI(
    title="PPG BP RAG-Agent",
    version="0.1.0",
    description="Conservative RAG-Agent for PPG-based blood pressure estimate explanations.",
)

app.include_router(router, prefix="/api/v1")
app.include_router(library_router, prefix="/api/v1/library")
