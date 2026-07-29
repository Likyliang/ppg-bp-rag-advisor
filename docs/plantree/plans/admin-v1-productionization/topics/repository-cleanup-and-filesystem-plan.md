# Repository Cleanup And Filesystem Plan

Date: 2026-07-29
Role: topic-capsule
Status: active

## Purpose

Retire superseded administration assets and stop tests from polluting the shared
runtime lock directory while preserving rollback evidence.

## Current Inventory

- Canonical frontend: `admin_ui/` and `app/static/admin_dist/`.
- Legacy assets: `app/static/admin.html` and `app/static/library_admin.html`.
- Runtime locks: `var/locks/`, including hundreds of test-generated catalog locks.

## Rules

- Confirm no imports, mounts, docs, or tests depend on legacy pages before deletion.
- Keep the built SPA and vendored assets required by active routes.
- Back up the active SQLite database before migration.
- Runtime state stays ignored; tests must use a temporary runtime directory.
- Clean only disposable lock files after verifying no Worker/API process is running.

## Safety checks

- Repository search for legacy paths.
- Focused admin/library/full-text tests.
- Frontend build and `/admin/` smoke test.
- Git status and ignore verification.
