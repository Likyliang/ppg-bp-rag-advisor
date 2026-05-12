# High Blood Pressure RAG Demo Instructions

This repository is the application demo for the thesis project:

`/Users/lianghao/Work/基于公开医学问答基准的安全约束 RAG-Agent 研究与高血压健康解释应用`

It demonstrates conservative, evidence-traceable health explanation for PPG blood-pressure estimates. It is not the thesis core and must not be described as validating PPG blood-pressure estimation accuracy.

Use Hermes skill `thesis-rag-agent` for cross-project orchestration.

## Working Rules

- Preserve the medical safety boundary: no diagnosis, prescription, medication adjustment, emergency reassurance, or replacement of validated cuff BP measurement.
- Preserve knowledge-base governance: no committed raw PDF full text, no credentials, no cookies, no institution session data.
- Keep citation/source metadata auditable.
- For substantial changes, run:

```bash
python scripts/run_quality_gate.py --strict-stop
```

- Keep calibrated query-only retrieval quality separate from metadata-filter safety checks.
- If a code change affects thesis claims, metrics, safety boundaries, or evaluation design, request both Claude Code narrative review and Codex engineering review before treating it as settled.
