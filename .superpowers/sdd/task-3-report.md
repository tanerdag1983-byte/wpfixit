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

## Second Review Fix

### Status

All Important and Minor findings from the second Task 3 re-review are fixed and
committed. The progress ledger remains unchanged pending another independent
review.

### Files

- `backend/app/api/routes/page_blueprints.py`
- `backend/app/domains/page_blueprints/service.py`
- `backend/app/domains/page_packages/schemas.py`
- `backend/tests/page_blueprints/test_migration.py`
- `.superpowers/sdd/task-3-report.md`

### Commits

- `ed819a5adfbb615d3b586b32bee8d51a9e2af560` - `fix: close snapshot
  migration rereview findings`

### RED Evidence

Real migrated-proposal approval:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_migration.py \
  -k versions_compatible_proposal
```

Result before the schema compatibility change: `1 failed, 7 deselected`.
The unmocked `_generation_context` raised a `PagePackageContext` validation
error because `snapshot-text-v1` and `document_fields` were rejected by the
legacy-only `BlueprintSchema` field.

Durable remote cleanup:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_migration.py \
  -k durable_remote_cleanup
```

Result before the recovery checkpoint change: `1 failed, 8 deselected`.
The first failed migration returned `action=recapture` instead of retaining the
trusted snapshot ID as `action=cleanup`.

Active-proposal and concurrent-successor handling:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_migration.py \
  -k 'generating_proposal or concurrent_successor'
```

Result before the locking/recheck change: `2 failed, 9 deselected`. Migration
captured and cloned a current `generating` proposal, while a successor created
after candidate discovery left the route in failed/recapture instead of
terminalizing the durable migration job.

### GREEN Evidence

- Real migrated-proposal approval: `1 passed, 7 deselected`.
- Durable cleanup retry: `1 passed, 8 deselected`.
- Active proposal and concurrent successor: `2 passed, 9 deselected`.
- Task 3 routes, migration, and WordPress client: `51 passed in 1.12s`.
- Real proposal approval/generation: `25 passed in 0.62s`.
- Ruff: `.venv/bin/ruff check app tests alembic` returned
  `All checks passed!`.
- Full backend: `318 passed, 3 skipped in 8.65s`.
- Alembic: `.venv/bin/alembic upgrade head` exited `0` at migration head.
- `git diff --check` and the staged diff check passed.
- Plugin suites were not rerun because no plugin file changed in this review
  fix.

### Invariants

- `PagePackageContext.blueprint_schema` accepts the typed union
  `BlueprintSchema | SnapshotTextSchema`; legacy parsing and validation remain
  unchanged, while both schemas use the same block-field replacement checks.
- A trusted snapshot ID is committed to
  `Job.checkpoint.cleanup_snapshot_id` before remote cleanup is attempted.
  Cleanup failure leaves `state=failed`, `action=cleanup`, and the exact ID
  durable. Retry cannot capture until deleting that ID succeeds. A crash after
  remote deletion is safe because retry treats remote `404` as success.
- Migration locks the legacy row and selects all current proposal rows with
  `FOR UPDATE` before remote capture. Current `generating` or
  `draft_in_progress` proposals produce durable `state=pending`,
  `action=wait`, and `blocked_proposal_ids`; they are not cloned or changed.
- Migration rechecks for a successor after entering `migrating`. If another
  migration created one after candidate discovery, the job commits terminal
  `migrated` with that successor ID and performs no capture.

### Self-Review

- The migrated proposal route test now uses real `_generation_context`, real
  replacement validation, and real WordPress identity validation. Only the
  transport client factory is replaced by the test bridge.
- Snapshot document fields do not weaken or bypass the existing block
  replacement contract; Task 4 can extend the generation output separately.
- Cleanup state survives request retries and is not reset by
  `prepare_snapshot_migration`.
- Cleanup success clears and commits the recovery ID before recapture.
- The pre-capture proposal locks are held in the same transaction as successor
  creation and immutable proposal versioning.
- The generation worker's current legacy proposal remains current and
  `generating` while migration waits.
- Concurrent successor discovery records a terminal migration state instead of
  leaving the job stuck at `migrating`.
- No source page writes/deletes, authorization changes, plugin changes, or
  legacy blueprint identity rewrites were introduced.
- The unrelated Task 1 report and untracked manual-handoff plan were neither
  edited nor staged.

### Concerns

- The full backend run skipped three PostgreSQL concurrency tests because
  `WP_FIXPILOT_POSTGRES_TEST_URL` is not configured. The proposal selection
  explicitly uses SQLAlchemy `with_for_update()` for PostgreSQL row locking.
- Independent re-review is still required before Task 3 is marked complete in
  the progress ledger.

## Third Review Fix

### Status

All five in-scope Task 3 findings from the third re-review are fixed and
committed. The requested snapshot draft-job contract remains explicitly
deferred to Task 6.

### Files

- `backend/app/api/routes/page_blueprints.py`
- `backend/app/api/routes/page_packages.py`
- `backend/app/domains/page_blueprints/service.py`
- `backend/app/domains/page_packages/service.py`
- `backend/tests/page_blueprints/test_migration.py`
- `backend/tests/page_blueprints/test_postgres_concurrency.py`
- `backend/tests/page_blueprints/test_routes.py`
- `backend/tests/page_blueprints/test_service.py`
- `backend/tests/page_packages/test_proposal_routes.py`
- `.superpowers/sdd/task-3-report.md`

### Commits

- `a0e4a02bf2177f2c1fe50735bb8a036620daaece` - `fix: close task
  three third review findings`

### RED Evidence

Successor lock ordering:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_migration.py -k concurrent_successor
```

Result before the lock-ordering change: `1 failed, 10 deselected`. The route
checked for a successor before locking the legacy blueprint and attempted
another capture.

Proposal default transfer:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_packages/test_proposal_routes.py -k reselects_default
```

Result before locked selection: `1 failed, 12 deselected`. Proposal creation
remained bound to the former legacy default after default ownership moved.

Legacy default reactivation:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_service.py -k superseded_legacy
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_routes.py -k reactivating_superseded
```

Results before the guard: each selection failed (`1 failed`); both service and
route allowed a superseded legacy blueprint to become default.

Native approval trust:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_packages/test_proposal_routes.py -k native_approval_rejects
```

Initial result: `6 failed, 2 passed`. Snapshot ID, post type, adapter version,
schema version, builder, and SEO identity mismatches were accepted. The final
matrix also covers compatibility snapshot ID, version, snapshot version, and
structure hash.

Failed proposal migration:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_migration.py -k failed_unfinished
```

Result before the recovery guard: `1 failed, 11 deselected`. Migration cloned
an unfinished failed proposal into a proposed successor version.

### GREEN Evidence

- Successor lock-ordering regression: `1 passed, 10 deselected`.
- Proposal default-transfer regression: `1 passed, 12 deselected`.
- Superseded-default service compatibility selection:
  `2 passed, 11 deselected`.
- Superseded-default route compatibility selection:
  `2 passed, 37 deselected`.
- Native approval mismatch matrix: `10 passed, 13 deselected`.
- Legacy approval compatibility selection: `2 passed, 19 deselected`.
- Failed proposal migration regression: `1 passed, 11 deselected`.
- Task 3 routes, migration, service, and WordPress client:
  `66 passed in 1.74s`.
- Proposal selection, approval, and generation: `36 passed in 1.40s`.
- Optional PostgreSQL concurrency suite: `2 skipped` because
  `WP_FIXPILOT_POSTGRES_TEST_URL` is absent.
- Ruff: `.venv/bin/ruff check app tests alembic` returned
  `All checks passed!`.
- Full backend: `332 passed, 4 skipped in 9.47s`; all four skips are optional
  PostgreSQL concurrency tests requiring `WP_FIXPILOT_POSTGRES_TEST_URL`.
- Alembic: `.venv/bin/alembic upgrade head` exited `0` at migration head.
- `git diff --check` passed.
- Plugin tests were not rerun because this review fix changed no plugin file.

### Invariants

- Migration acquires the legacy `PageBlueprint` row lock before querying for a
  successor, within the same transaction. A waiting migration observes a
  concurrently committed successor, terminalizes its job as `migrated`, and
  does not capture.
- Proposal creation locks the selected default row and then revalidates ready
  state, default ownership, and absence of a successor. A transferred default
  is reselected once; an unresolved race returns bounded `409` retry guidance.
- A legacy blueprint with a successor can never be reactivated as default.
  Native active snapshots and pre-migration legacy defaults remain supported.
- Native proposal approval requires exact WordPress snapshot identity and trust
  fields. Legacy proposal approval retains its existing validation contract.
- Failed or package-less current proposals remain legacy-bound and receive the
  existing `snapshot_migration_requires_generation` recovery code; no proposed
  successor version is copied.

### Task 6 Boundary

`wordpress-snapshot-draft-job-v1` is intentionally not implemented in Task 3.
`_draft_job_payload` and plugin dispatch are unchanged, and legacy v1 jobs
remain available for legacy proposals. Task 6 owns the `SnapshotTextSchema`
outbound payload and plugin dispatch. The third-review draft-job item is
therefore recorded as cross-task `Cannot verify`, not as a Task 3 change.

### Self-Review

- The deterministic route test proves no successor lookup occurs before the
  legacy lock; the optional real PostgreSQL test proves a waiter observes a
  successor committed by the lock holder.
- Proposal locking remains held through proposal insertion, preserving the
  migration/proposal serialization boundary.
- Default rejection happens before any default flags are mutated.
- Native trust mismatch coverage shares one fixture and spans every bounded
  identity class without weakening the legacy branch.
- No draft-job payload, plugin, source WordPress page, authorization, or legacy
  blueprint identity behavior was changed.
- The unrelated Task 1 report and untracked manual-handoff plan were neither
  edited nor staged.

### Concerns

- The real PostgreSQL concurrency tests could not execute locally because
  `WP_FIXPILOT_POSTGRES_TEST_URL` is not configured; their optional suite was
  collected and skipped as designed.
- Independent re-review is still required before Task 3 is marked complete in
  the progress ledger.

## Fourth Review Fix

### Status

The fourth, strictly scoped Task 3 review finding is fixed and committed.
Migration can no longer bypass a durable cleanup checkpoint committed while
another request waits for the legacy blueprint row lock.

### Files

- `backend/app/api/routes/page_blueprints.py`
- `backend/app/domains/page_blueprints/service.py`
- `backend/tests/page_blueprints/test_migration.py`
- `.superpowers/sdd/task-3-report.md`

### Commits

- `0423fd2ec4327a1f86c42cd1edbfc2129ecc55fc` - `fix: reload
  snapshot cleanup after migration lock`

### RED Evidence

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_blueprints/test_migration.py \
  -k cleanup_committed_while_waiting
```

Result before production changes: `1 failed, 12 deselected`. The deterministic
race wrote `cleanup_snapshot_id=812` directly to the database after the legacy
row lock was acquired while retaining the stale ORM job instance. The route
captured immediately, producing event order `["capture"]` instead of the
required `["delete:812", "capture"]`.

### GREEN Evidence

- Race regression: `1 passed, 12 deselected`.
- Race plus existing durable cleanup/retry regression:
  `2 passed, 11 deselected`.
- Task 3 routes, service, migration, and WordPress client:
  `67 passed in 1.76s`.
- Optional PostgreSQL concurrency suite: `2 skipped` because
  `WP_FIXPILOT_POSTGRES_TEST_URL` is absent.
- Ruff: `.venv/bin/ruff check app tests alembic` returned
  `All checks passed!`.
- Full backend: `333 passed, 4 skipped in 9.63s`; all four skips are optional
  PostgreSQL concurrency tests requiring `WP_FIXPILOT_POSTGRES_TEST_URL`.
- Alembic: `.venv/bin/alembic upgrade head` exited `0` at migration head.
- `git diff --check` passed.

### Invariant

The migration transaction now acquires the legacy `PageBlueprint` row lock
first, then locks and reloads the migration `Job` with
`populate_existing=True`, and only then checks for a successor or captures.
This explicitly defeats the `expire_on_commit=False` identity-map cache.

If the refreshed checkpoint contains `cleanup_snapshot_id`, the same recovery
function used at request entry runs before successor/capture logic. A delete
failure commits the existing durable `failed/cleanup` state. A successful
delete clears the checkpoint before capture in the same transaction. A crash
before commit leaves the cleanup ID durable, so retry repeats the idempotent
delete; remote `404` remains treated as already deleted.

### PostgreSQL Coverage

No additional optional PostgreSQL test was added. The existing optional suite
already covers waiting for and acquiring the legacy row lock with real
PostgreSQL transactions. The new deterministic route regression specifically
covers the previously missing stale SQLAlchemy identity-map reload after that
wait. The optional suite was still run and skipped only because the configured
test URL is absent.

### Task 6 Boundary

Task 6 draft-job behavior remains untouched. No
`wordpress-snapshot-draft-job-v1`, `_draft_job_payload`, plugin dispatch, or
legacy v1 job behavior changed in this review fix.

### Self-Review

- Lock order is legacy blueprint, migration job, successor, then proposals.
- The job query uses both `FOR UPDATE` and `populate_existing=True`.
- The durable cleanup path is shared rather than reimplemented.
- No capture occurs after a concurrent cleanup failure.
- Existing cleanup retry and remote-delete idempotence tests remain green.
- No authorization, source-page, plugin, proposal, or draft-job behavior was
  changed.
- The unrelated Task 1 report and untracked manual-handoff plan were neither
  edited nor staged.

### Concerns

- Real PostgreSQL concurrency execution remains unverified locally because
  `WP_FIXPILOT_POSTGRES_TEST_URL` is not configured.
- Independent re-review is still required before Task 3 is marked complete in
  the progress ledger.
