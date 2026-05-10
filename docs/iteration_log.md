# Iteration Log

## Baseline: v0.2.0-kb-governance-baseline

- Date: 2026-05-10
- Branch: main
- Tests: `30 passed`
- Knowledge base: 35 included sources, 140 chunks
- Retrieval evaluation: match_rate 1.0, mean_precision_at_5 0.887, unsafe_source_leakage_count 0
- Audit: all expected topics covered; no orphan sources; no duplicate source hashes; no unsafe-source leakage
- Risk: no Git history existed before this baseline; long-run quality gate and stop-criteria enforcement still need to be added

## Iteration 02: Quality Gate

- Goal: add one-command verification for tests, source screening, note generation, ingest, audit, retrieval evaluation, and report evaluation.
- Expected artifact: `knowledge_base/processed/quality_gate_report.json`.
- Stop criteria are intentionally stricter than the current baseline so the report can show remaining gaps during the 20-round run.

