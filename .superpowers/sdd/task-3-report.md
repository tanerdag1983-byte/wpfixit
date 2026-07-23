# Versioned Template Snapshots Release 1 - Task 3 Report

## Status

Implemented and committed. Native capture, verification, immutable versioning,
and per-blueprint legacy migration are complete. The SDD progress ledger remains
unchanged pending independent review.

## Files

- `backend/app/api/routes/page_blueprints.py`
- `backend/app/domains/page_blueprints/service.py`
- `backend/app/domains/wordpress/client.py`
- `backend/tests/page_blueprints/conftest.py`
- `backend/tests/page_blueprints/test_routes.py`
- `backend/tests/page_blueprints/test_migration.py`
- `backend/tests/wordpress/test_client.py`

## Commits

- `acce947eadfd657419ec4eed7482133c8c519a9f` - `feat: migrate managed
  blueprints to snapshots`

## RED Evidence

Initial focused command:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_routes.py \
  tests/page_blueprints/test_migration.py \
  tests/wordpress/test_client.py
```

Result: `3 failed, 27 passed`.

- Native `snapshot-text-v1` capture failed with `502` because the route still
  required `blueprint-v1`.
- `POST /page-blueprints/migrate` returned `405 Method Not Allowed`.
- `WordPressClient.capture_snapshot()` did not exist.

After converting the existing route fixtures to the native contract and adding
proposal migration coverage, the same command produced `26 failed, 9 passed`.
Failures covered the missing native capture path, exact snapshot identity,
verification route, migration transactions, proposal rebinding, trusted
cleanup, and snapshot client methods.

The first GREEN attempt exposed a proposal pointer invariant during migration:

```text
CHECK constraint failed:
ck_page_package_proposals_current_pointer_matches_flag
```

Tracing showed SQLAlchemy autoflush persisted `is_current=false` before the
row's `current_version_id` advanced. Setting both values before the group update
kept the constraint valid throughout the transaction.

## GREEN Evidence

Required focused tests:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_routes.py \
  tests/page_blueprints/test_migration.py \
  tests/wordpress/test_client.py
```

Result: `35 passed in 0.80s`.

Required Ruff check:

```bash
cd backend
.venv/bin/ruff check app tests
```

Result: `All checks passed!`

Adjacent blueprint coverage:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints tests/wordpress/test_client.py
```

Result: `75 passed, 1 skipped in 2.05s`. The skip requires
`WP_FIXPILOT_POSTGRES_TEST_URL`.

Full backend regression:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q
```

Result: `302 passed, 3 skipped in 8.17s`. All skips are optional PostgreSQL
concurrency tests requiring `WP_FIXPILOT_POSTGRES_TEST_URL`.

`git diff --check` and the staged diff check both passed.

## Self-Review

- Capture persists a snapshot only after `created is True`, both compatibility
  IDs match, the ID is positive, an optional returned post type is
  `wpfixpilot_snapshot`, and the project has no registered duplicate.
- Validation compares the trusted snapshot ID, version, schema version, source
  lineage ID, page type, builder, SEO plugin, structure hash, and typed schema.
- Verification reads the stored snapshot ID and never reads, writes, changes
  status on, or deletes the source WordPress page.
- Native create and new-version failures delete only the newly trusted snapshot.
  Untrusted or duplicate identities are never deleted.
- Migration locks and commits one legacy blueprint per transaction. A later
  capture failure does not roll back an earlier successful successor.
- Migration creates a successor row and never rewrites the legacy
  `PageBlueprint` identity referenced by historical proposal foreign keys.
- Compatible unapproved proposals receive a new immutable current version bound
  to the successor. The old proposal row and blueprint identity remain intact.
- Incompatible unapproved proposals become `failed` with bounded job error code
  `snapshot_migration_requires_generation`.
- Approved, in-progress, and created-draft proposals stay current and remain
  bound to the legacy identity for the compatibility draft path.
- Authorization still uses `_manager_project`; list, validate, create,
  new-version, and delete compatibility routes remain available.
- The unrelated modified Task 1 report and untracked manual-handoff plan were
  not edited or staged.

## Concerns

- The current plugin response contract provides trusted snapshot IDs, version,
  and schema version but does not expose `post_type` or `adapter_version`.
  Backend validation rejects an incorrect post type when supplied and derives
  a stable builder snapshot adapter version when absent. A future plugin
  contract can make both values explicit without changing stored identities.
- Independent review was not available in this session. Per the SDD workflow,
  Task 3 should not be marked complete in `.superpowers/sdd/progress.md` until
  that review is approved.
