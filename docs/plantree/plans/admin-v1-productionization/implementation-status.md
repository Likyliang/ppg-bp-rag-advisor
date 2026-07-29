# Implementation Status

Date: 2026-07-29

## Current Phase

Release validation and operational handoff.

## Active TODO

1. Complete the external narrative review after Claude Code OAuth is restored.
2. Securely hand off, then delete, the one-time local credential file.

## Done This Phase

- Pushed local commit range `2ea914b..39d75cd` by fast-forward over authenticated SSH.
- Preserved port `8020`, bound the launcher to `127.0.0.1`, and removed auth bypass.
- Backed up the Admin DB and `.env`, upgraded Alembic to head, and verified integrity.
- Generated the master key, created the first Argon2 administrator, and wrote the
  one-time handoff material only to an ignored owner-only local file.
- Installed a persistent macOS Worker and created one scoped expiring API Client.
- Migrated report, embedding, and evaluation keys into encrypted Admin configuration,
  removed the evaluation key from the active environment, and configured Crossref.
  Because the evaluation endpoint is HTTP-only, that profile remains safely disabled
  with no runtime key until an HTTPS endpoint is supplied.
- Isolated pytest DB/locks and verified 26 focused tests without formal-state changes.
- Retired the legacy static administration pages and mount.
- Productized all nine Vue modules with structured forms, polling, progress, filters,
  pagination, actionable error feedback, and responsive authenticated browser QA.
- Rebuilt screening, summary chunks, hashing, Chroma/BGE, OpenAI summary, and local
  full-text artifacts; freshness now uses input/build fingerprints rather than counts.
- Rebuilt the OpenAI full-text artifact from the current local full-text input:
  133 sources, 12,509 chunks, 1,536 dimensions, with matching upstream fingerprint.
- Added source-level full-text progress, batch-level OpenAI progress, and enforced the
  configured OpenAI embedding concurrency limit without changing direct CLI JSON output.
- Refuse external embedding builds when summary/full-text inputs are stale or failed;
  failed full-text manifests are also excluded from report/advisor retrieval.
- Split public-download staging from the governed library and added a regression test
  proving a forced candidate download cannot overwrite an already governed PDF.
- Normalized 168 historical full-text governance records without treating migration
  notes as licence assertions. Across registry and candidate inventory, 175 local
  PDFs remain visibly pending human authorization review.
- Restored all governed local PDFs to the recorded byte count and SHA-256; the current
  local full-text artifact contains 133 sources and 12,509 chunks.
- Reduced `var/locks/` to the single live owner-only Worker lock and moved test locks
  into disposable session directories.
- Verified focused backend tests, the 536-test strict suite, frontend tests,
  TypeScript checks, production build, dependency audit, and all nine browser routes.

## Blockers

- The evaluation provider's current endpoint is plain HTTP and the same-host HTTPS
  probe fails TLS. Its key is encrypted in Admin, but the profile remains disabled
  and the runtime receives no evaluation key until a valid HTTPS endpoint is supplied.
- The 175 historical local PDFs require document-by-document authorization review.
  The system reports this backlog and does not describe it as authorized.
- Claude Code narrative review is temporarily blocked by an expired local OAuth
  session; this is an external review-channel issue, not a passing review result.
- Administrator password and one-time API client key require a secure handoff.

## Next Commit Target

Post-review follow-up only; the governed operations console release is verified.

## Last Verified Commands

- `.venv/bin/python scripts/run_quality_gate.py --strict-stop`: 536 tests collected,
  all commands and all 16 stop criteria passed
- Retrieval match `1.0`, Precision@5 `0.971`, metadata-filter safety `1.0`,
  unsafe source leakage `0`, report P95 `2.2411s`
- `npm --prefix admin_ui run test`: 4 passed
- `npm --prefix admin_ui run typecheck`: passed
- `npm --prefix admin_ui run build`: passed
- `npm --prefix admin_ui audit --audit-level=high`: 0 vulnerabilities
