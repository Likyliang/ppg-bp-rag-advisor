# Test And Release Gates

Substantial changes must pass:

1. Vue TypeScript check and production build.
2. Relevant focused pytest suites.
3. `python scripts/run_quality_gate.py --strict-stop`.
4. Claude narrative review and Codex engineering review when claims, metrics,
   safety boundaries, or evaluation design change.

`calibrated_query_only` retrieval quality and `metadata_filter_safety` checks
must remain separate.
