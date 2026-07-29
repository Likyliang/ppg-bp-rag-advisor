# Runtime Flows

## Administration

Browser → FastAPI `/api/v1/admin/*` → RBAC/CSRF → SQLite or governed YAML.
Long-running operations are enqueued in SQLite and executed by the single-host
admin Worker.

## Report and advisor

Scoped API client → normalized request → conservative rules/retrieval →
generation or safe fallback → safety review. Raw health payloads are not stored
in administration metrics or audit events.

## Knowledge governance

Catalog → screening → chunks → local/OpenAI indexes → quality gate. Input
fingerprints determine `current`, `stale`, `missing`, `building`, or `failed`.
