# Versioned Template Snapshots Release 1 - Task 6

## Scope

Create normal WordPress drafts from the exact private template snapshot through
the strict `wordpress-snapshot-draft-job-v1` outbound contract. Keep legacy
`wordpress-draft-job-v1` dispatch unchanged.

## RED

- Backend snapshot payload tests failed because the legacy
  `GeneratedBlueprintPackage` parser rejected `text_replacements`.
- The plugin snapshot test failed with `wp_fixpilot_unsupported_contract`.

## GREEN

- Native snapshots with a ready validation stage now emit only the eight
  contract-v2 fields from stored normalized validation output.
- Validation freezes approved URLs alongside normalized field replacements.
- Legacy blueprints continue to emit and process `wordpress-draft-job-v1`.
- The plugin requires the exact v2 key set and strict scalar types, asserts the
  private snapshot, verifies snapshot and schema versions, then delegates to the
  existing verified clone/write/cleanup/idempotency path.
- Document title, slug, and SEO values are derived from their field IDs; only
  remaining block fields reach the builder adapter.
- Migration `0022_snapshot_draft_jobs` allows exactly the legacy and snapshot
  contract versions.

## Verification

- Ruff: clean.
- Focused backend contract and route suite: 37 passed.
- Full backend: 379 passed, 6 optional PostgreSQL concurrency tests skipped.
- All plugin tests and PHP lint passed under PHP 8.2.
- PostgreSQL `0021 -> 0022 -> 0021 -> 0022` passed.
- Isolated SQLite `0021 -> 0022 -> 0021 -> 0022` passed.
- Snapshot plugin regression proves private snapshot to normal `page`/`draft`,
  exact-key rejection, strict ID typing, and idempotent replay.

## Invariants

- Draft-job payload and hash remain immutable after insertion.
- Native proposal identity must match the stored snapshot ID, version, schema
  version, and structure hash.
- Source pages and private snapshots are never modified or published.
- Failed writes use the existing cleanup path; successful writes are verified as
  persisted WordPress drafts.

## Independent Review Fix

- A compatible migrated proposal now runs through the same snapshot normalizer
  during approval, persists a ready validation stage and approved URLs, and can
  immediately create a v2 draft job.
- Draft creation uses an atomic MySQL/MariaDB named lock per idempotency key. A
  concurrent worker leaves the backend claim retryable instead of reporting a
  terminal failure; an interrupted request releases its connection-scoped lock.
- Persisted document title and slug are reloaded and compared after
  `wp_update_post`. Hook mutations or slug suffixing trigger cleanup and a
  failed draft result.
- Review-fix verification: 57 focused backend tests passed; full backend
  remained 379 passed with 6 optional PostgreSQL skips; all plugin tests and PHP
  lint passed.
- Re-review replaced the initial option-based stale-lock recovery with a
  connection-scoped database named lock, removing its delete/add takeover race.
