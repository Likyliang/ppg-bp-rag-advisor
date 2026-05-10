# v1.0.0-rc1 Release Notes

## Status

This release candidate meets the current usability stop criteria for the PPG blood pressure estimate RAG-Agent.

## Quality Gate

- Tests: 101 collected and passing.
- Knowledge base: 63 included governed sources and 252 chunks.
- Knowledge audit: all expected topics covered; no orphan sources; no duplicate source hashes; no unsafe-source leakage.
- Retrieval evaluation: 100 golden queries, match rate 1.0, mean precision@5 1.0, unsafe-source leakage 0.
- Report evaluation: 50 fixtures; Rule + RAG + Safety reports include summary, evidence, high-quality evidence, PPG limitation, and safety pass.
- Performance: template report P95 below 3 seconds on local fixtures.

## Safety Boundary

The system remains limited to conservative explanation of upstream PPG-based blood pressure estimates. It does not diagnose hypertension, provide treatment decisions, prescribe medication, stop medication, or replace validated blood pressure measurement.

## Release Commands

```bash
python scripts/run_quality_gate.py --strict-stop
uvicorn app.main:app --reload
streamlit run streamlit_app.py
```

