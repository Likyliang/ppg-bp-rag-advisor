# Roadmap

## Done

- Admin V1 implementation landed in commit `39d75cd`.
- Nineteen local commits were fast-forward pushed to the tracked GitHub branch.
- Development launcher binds to localhost and no longer disables authentication.
- Admin SQLite backup/migration, first administrator, master key, persistent Worker,
  scoped API Client, and three safe integration profiles are in place.
- Tests use disposable DB/lock state; legacy static admin pages are retired.
- All nine Vue modules are productized and authenticated browser QA is complete.
- Screening, summary chunks, hashing, Chroma/BGE, OpenAI summary, and local full-text
  artifacts are current; the live lock directory contains only the Worker lock.
- OpenAI full-text embedding is current for all 12,509 governed technical chunks, and
  stale/failed upstream artifacts are blocked before any external embedding request.
- Long-running full-text and OpenAI jobs report real source/batch progress, while the
  embedding profile's configured concurrency limit is enforced.
- Candidate downloads use an isolated staging path and cannot overwrite governed PDFs.
- Historical full-text governance is normalized; all 175 local PDFs in registry and
  candidate inventory expose an authorization-review backlog without being described
  as authorized.
- The final strict gate passed all 16 criteria with 536 tests.

## In Progress

- Complete the Claude Code narrative review after its local OAuth session is restored.
- Securely hand off bootstrap credentials.

## Next

- Move the evaluation endpoint to HTTPS before storing it in Admin integrations.
- Review and attest historical local PDF authorization one document at a time.
- Securely hand off and then delete the one-time bootstrap credential file.

## Deferred

- Public high availability, multi-tenancy, patient CRM, and hospital integrations.
