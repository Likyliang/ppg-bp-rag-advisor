# Storage And State

- Governed medical configuration remains in `config/*.yaml`.
- Governed literature metadata remains in knowledge-base catalogs.
- Admin accounts, sessions, jobs, revisions, encrypted integration secrets,
  anonymous metrics, and audit events live in `var/admin.db`.
- Runtime databases, locks, raw PDFs, full-text chunks, vector stores, and
  credentials are Git-ignored local state.
- Provider secrets require `ADMIN_SECRET_MASTER_KEY`; API client keys are stored
  only as hashes and are returned once on creation.
