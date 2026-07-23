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

## Review Fix

### Status

All Critical, Important, and Minor review findings are fixed and committed.
Task 3 remains pending independent re-review; the progress ledger was not
changed.

### Files

- `backend/app/api/routes/page_blueprints.py`
- `backend/app/domains/page_blueprints/service.py`
- `backend/tests/page_blueprints/conftest.py`
- `backend/tests/page_blueprints/test_routes.py`
- `backend/tests/page_blueprints/test_migration.py`
- `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- `plugin/wp-fixpilot-bridge/tests/blueprint-test.php`
- `plugin/wp-fixpilot-bridge/tests/template-snapshot-test.php`
- `.superpowers/sdd/task-3-report.md`

### Commits

- `60649bd0389f21cfd1d9450995cae5b9a48c75c7` - `fix: harden snapshot
  migration review findings`

### RED Evidence

Failure-ordering regressions:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_routes.py \
  -k 'commit_failure or refresh_failure or delete_db_failure or remote_delete_failure or non_ready_commit'
```

Result before production changes: `5 failed, 1 passed`. The failures proved
that post-commit refresh errors deleted committed snapshots and that deletion
could remove WordPress before a durable non-ready backend state existed.

Migration state, proposal schema/approval, and SEO identity regressions:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_migration.py
```

Result before production changes: `5 failed, 2 passed`. The failures covered
missing durable migration states, stale proposal `config_snapshot`, downstream
approval rejection, and successor SEO identity drift.

Mandatory snapshot trust fields:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_routes.py -k trust_field
```

Result before production changes: `4 failed, 1 passed`. Missing `post_type` and
`adapter_version` were accepted during capture and verify.

Both PHP 8.2 focused suites failed before the plugin change with undefined
`post_type` assertions:

```bash
docker run --rm -v "$PWD:/app" -w /app php:8.2-cli \
  php -d zend.assertions=1 -d assert.exception=1 \
  tests/template-snapshot-test.php
docker run --rm -v "$PWD:/app" -w /app php:8.2-cli \
  php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php
```

SQLite composite foreign-key regression:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_migration.py \
  -k composite_blueprint_foreign_key
```

Result before enabling SQLite foreign keys: `1 failed`; the invalid composite
blueprint identity committed instead of raising `IntegrityError`.

### GREEN Evidence

- Failure-ordering selection: `6 passed, 27 deselected`.
- Migration suite before the FK coverage addition: `7 passed`.
- Mandatory backend trust fields: `5 passed, 33 deselected`.
- Focused plugin snapshot and blueprint suites: both passed under PHP 8.2.
- Composite-FK selection: `1 passed, 7 deselected`.
- Task 3 routes, migration, and WordPress client: `48 passed in 1.24s`.
- Adjacent proposal generation/approval: `25 passed in 0.60s`.
- Ruff: `.venv/bin/ruff check app tests alembic` returned
  `All checks passed!`.
- Full backend: `315 passed, 3 skipped in 8.96s`.
- Full plugin: all `10` PHP 8.2 suites passed; all `36` PHP files passed lint.
- Alembic: `.venv/bin/alembic upgrade head` exited `0` at migration head.
- `git diff --check` and the staged diff check passed.

### Invariant

New snapshot cleanup is allowed only for a newly returned trusted snapshot ID
before its backend transaction commits. A refresh or response-building failure
after commit never deletes the remote snapshot.

Explicit deletion first commits `state=invalid` and clears default status, then
deletes WordPress, then deletes the backend row. Therefore a remote failure or
final database failure leaves a durable non-ready row. Retrying is safe because
remote `404` is treated as already deleted; no ready backend row can point at a
deleted remote snapshot.

Each legacy blueprint's successor, proposal version changes, default transfer,
and terminal migration state commit atomically. Durable orchestration records
make `pending -> migrating -> migrated|incompatible|failed` observable without
rewriting the legacy blueprint identity.

### Self-Review

- Capture and verify now require exact `post_type=wpfixpilot_snapshot` and a
  non-empty explicit `adapter_version`; plugin capture/read responses provide
  both.
- Capture cleanup remains limited to trusted, newly created snapshot IDs and
  ends at commit.
- Compatible unapproved proposals receive a new immutable current version whose
  config contains the successor schema and complete snapshot identity/config.
  Route-level approval validation accepts that version.
- Approved proposals remain current and legacy-bound.
- Captured `seo_plugin` is validated, persisted on successors and new versions,
  and used by immediate verification.
- Migration job state and transition history persist all five mandated states;
  response items expose the terminal per-blueprint result and retry action.
- SQLite route fixtures enable foreign keys before schema creation and create
  parent records in explicit dependency order.
- No source WordPress page is written or deleted.
- Authorization and existing transaction/locking patterns remain in place.
- The unrelated Task 1 report and untracked manual-handoff plan were neither
  edited nor staged.

### Concerns

- The full backend run skipped three PostgreSQL concurrency tests because
  `WP_FIXPILOT_POSTGRES_TEST_URL` is not configured.
- Independent re-review is still required before Task 3 is marked complete in
  the progress ledger.
