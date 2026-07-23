# Versioned Template Snapshots Release 1 - Task 2 Report

## Status

Complete. Task 2 persists a legacy-safe versioned template snapshot identity and
validates the `snapshot-text-v1` plugin capture contract.

## Files

- `backend/alembic/versions/0020_versioned_template_snapshots.py`
- `backend/app/domains/page_blueprints/models.py`
- `backend/app/domains/page_blueprints/schemas.py`
- `backend/app/domains/page_blueprints/service.py`
- `backend/tests/page_blueprints/test_models.py`
- `backend/tests/page_blueprints/test_service.py`
- `backend/tests/page_packages/test_model_registration.py`

## RED Evidence

Command:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_blueprints/test_models.py tests/page_blueprints/test_service.py
```

Result: failed during collection with the expected missing production symbols:

- `ImportError: cannot import name 'SnapshotTextSchema'`
- `ImportError: cannot import name 'snapshot_schema_from_capture'`

The initial PostgreSQL Alembic upgrade also failed before recording the revision:

```text
psycopg.errors.StringDataRightTruncation: value too long for type character varying(32)
```

Root cause: the proposed revision token exceeded the repository's existing
`alembic_version.version_num VARCHAR(32)` limit. The new migration keeps the
required `0020_versioned_template_snapshots.py` filename and uses the compatible
revision ID `0020_template_snapshots`.

## GREEN Verification

```bash
cd backend
.venv/bin/ruff check app tests alembic
```

Result: `All checks passed!`

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_blueprints/test_models.py tests/page_blueprints/test_service.py tests/page_packages/test_model_registration.py
```

Result: `38 passed in 0.91s`.

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/alembic current
.venv/bin/alembic downgrade 0019_outbound_wp_draft_jobs
.venv/bin/alembic current
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

Result: PostgreSQL upgraded to `0020_template_snapshots (head)`, downgraded to
`0019_outbound_wp_draft_jobs`, and upgraded back to `0020_template_snapshots
(head)`.

An in-memory SQLite Alembic operations probe also upgraded a legacy
`page_blueprints` row, verified every new column remained null for that row,
downgraded, and confirmed the legacy row remained. Result:

```text
SQLite upgrade/downgrade batch migration passed
```

## Self-Review

- `0020` is reversible and uses `batch_alter_table(recreate="auto")`, which
  performs native alteration on PostgreSQL and table recreation on SQLite.
- Every snapshot column is nullable for legacy records. The named check accepts
  either all seven snapshot fields as null or a complete native identity only.
- A native identity requires the exact `snapshot-text-v1` schema discriminator,
  `capture_state='ready'`, `migration_state='native'`, non-null adapter version,
  and a verification timestamp.
- Snapshot uniqueness is `(project_id, wordpress_snapshot_id)`, so a snapshot
  identifier can be reused only by a different project. The existing
  `wordpress_blueprint_id` remains unchanged for v1 compatibility.
- `SnapshotTextSchema.fields_by_id()` rejects duplicate IDs across document and
  block fields; the capture converter accepts only `content_schema` values that
  satisfy this typed contract and does not reinterpret legacy AI packages.
- `git diff --check` passed. The unrelated modified Task 1 report and untracked
  manual-handoff plan were not edited or staged.

## Commits

`dc505188339b9b3c715924a7b8e603bee53cd5ef` - `feat: persist versioned template
snapshot identity`

## Concerns

No open implementation concerns. An independent reviewer was not available in
this session; the requested self-review and database portability checks were
completed before commit.

## Review Fix

### Status

Complete. The snapshot identity constraint no longer accepts SQL `UNKNOWN` for
partially populated native snapshot rows.

### Files

- `backend/app/domains/page_blueprints/models.py`
- `backend/alembic/versions/0020_versioned_template_snapshots.py`
- `backend/tests/page_blueprints/test_models.py`
- `backend/tests/page_blueprints/test_snapshot_migration.py`

### RED Evidence

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_blueprints/test_models.py tests/page_blueprints/test_snapshot_migration.py
```

Result: `2 failed, 26 passed in 1.07s`.

- The model regression populated every native snapshot field after
  `schema_version` and set `schema_version=None`; it failed because no
  `IntegrityError` was raised.
- The PostgreSQL migration regression upgraded a fresh database from `0019`,
  inserted the same middle-null identity, and also failed because no
  `IntegrityError` was raised.

### GREEN Verification

```bash
cd backend
.venv/bin/ruff check app tests alembic
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_blueprints/test_models.py tests/page_blueprints/test_service.py tests/page_blueprints/test_snapshot_migration.py tests/page_packages/test_model_registration.py
.venv/bin/alembic downgrade 0019_outbound_wp_draft_jobs
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

Result: Ruff passed; `41 passed in 1.59s`; PostgreSQL downgraded from `0020`,
upgraded back to `0020_template_snapshots`, and reported
`0020_template_snapshots (head)`.

The committed migration regression starts at `0019`, preserves a legacy row
with all snapshot columns null during upgrade, rejects the middle-null native
identity, and verifies downgrade removes the new columns while preserving that
legacy row. The matching SQLite batch-migration round trip passed with:

```text
SQLite snapshot migration upgrade/downgrade and partial-identity rejection passed
```

### Commit

`383c8e4cf886d078306c66f9cb0a65e27f1f9dde` - `fix: harden template snapshot
identity constraint`

### Self-Review

- The populated branch now explicitly checks every identity field for
  non-nullness. `schema_version`, `capture_state`, and `migration_state` each
  have an `IS NOT NULL` guard immediately before their equality condition.
- The same expression is present in ORM metadata and Alembic `0020`, so fresh
  schema creation and migrated databases have identical semantics.
- Same-project snapshot-ID reuse remains rejected; the new model test proves
  a matching snapshot ID is accepted for a different project.
- The migration regression is committed and follows the repository's isolated
  PostgreSQL Alembic database pattern. The user-owned Task 1 report edit and
  untracked manual-handoff plan were not changed or staged.

### Concerns

No open implementation concerns. An independent reviewer was not available in
this session; the requested self-review and committed migration regression were
completed.
