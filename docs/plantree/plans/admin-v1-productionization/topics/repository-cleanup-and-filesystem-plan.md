# Repository Cleanup And Filesystem Plan

Date: 2026-07-29
Role: topic-capsule
Status: complete

## Purpose

Retire superseded administration assets and stop tests from polluting the shared
runtime lock directory while preserving rollback evidence.

## Current Inventory

- Canonical frontend: `admin_ui/` and `app/static/admin_dist/`.
- Retired legacy assets: `app/static/admin.html`, `app/static/library_admin.html`,
  their vendored Bootstrap/Vue files, and the old `/api/v1/library/static` mount.
- Runtime locks: `var/locks/`, including hundreds of test-generated catalog locks.

## Rules

- Keep the built SPA required by the active `/admin/` route.
- Back up the active SQLite database before migration.
- Runtime state stays ignored; tests must use a temporary runtime directory.
- Clean only disposable lock files after the current Worker queue is idle.

## Safety checks

- Repository search for legacy paths.
- Focused admin/library/full-text tests.
- Frontend build and `/admin/` smoke test.
- Git status and ignore verification.

## Completed

- Repository search confirmed that only the retired HTML referenced the vendored files.
- Removed both legacy pages, their unused assets, and the legacy static mount.
- Pytest now sets a session-scoped temporary Admin DB and `ADMIN_LOCK_DIR`.
- Focused Admin V1 suite passed without changing formal DB or lock counts.
- Historical disposable lock files were removed. The live directory now contains
  only the owner-only `admin-worker.lock` held by the persistent Worker.
- The production SPA build and authenticated nine-route browser smoke test passed.
- Runtime database, credentials, logs, locks, backups, and governed raw PDFs remain
  ignored by Git.
