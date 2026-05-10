# Release Checklist

- `pytest` passes.
- `scripts/screen_sources.py` passes with no catalog errors.
- `scripts/ingest_kb.py` regenerates governed chunks.
- `scripts/audit_kb.py` reports no missing topics, no orphan sources, no duplicate source hashes, and no unsafe-source leakage.
- `scripts/evaluate_retrieval.py` meets retrieval thresholds.
- `scripts/evaluate_reports.py` meets report thresholds.
- FastAPI imports and exposes `/api/v1/health`.
- Streamlit app starts and responds to health checks.

