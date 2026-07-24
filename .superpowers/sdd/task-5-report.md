# Versioned Template Snapshots Release 1 - Task 5

## Scope

Persist resumable snapshot-proposal stages and field errors while preserving the
legacy page-package flow. Snapshot proposals execute `template`, `text`, and
`validation` independently; only validated proposals become `proposed`.

## RED

- In a detached worktree at base `1202b2f8d4ee539a761785ff9c73e683797a295f`,
  a minimal `PageProposalStage` contract test failed during collection with
  `ImportError: cannot import name 'PageProposalStage'`.
- The new manual-correction regression initially failed with `422`: the write
  schema accepted only legacy `GeneratedBlueprintPackage` payloads, so an
  editable snapshot in `needs_attention` could not be corrected or revalidated.

## GREEN

- Added `PageProposalStage`, migration `0021_proposal_stages`, bounded JSON
  constraints, timestamps, retry counts, unique stage identity, cascading
  deletion, and row-locked transition helpers.
- Snapshot creation persists ordered `template`, `text`, and `validation`
  results. Validation attention exposes sorted field errors; legacy proposals
  retain `stages: []` and `field_errors: {}`.
- Validation retry reuses stored text and does not invoke the provider. Text
  retry creates a new current proposal version and preserves the original
  version and its stages.
- A snapshot needing attention accepts a field-ID correction, reruns only
  validation, and leaves the stored provider text result unchanged.
- Verification:
  - `ruff check app tests alembic`: passed.
  - Focused stages/routes/versions suite: `43 passed, 1 skipped`.
  - `alembic upgrade head`: reached `0021_proposal_stages (head)`.
  - Full backend suite: `367 passed, 5 skipped`.

## Invariants

- Stage names and states are database constrained; one stage name exists at
  most once per proposal version.
- Result and error JSON are bounded both by helpers and database constraints.
- State transitions use `SELECT ... FOR UPDATE`; terminal transitions have one
  winner under the optional PostgreSQL concurrency regression.
- Snapshot identity is recorded before provider execution. Provider output is
  stored in `text`; validation output is separate and field errors are ordered.
- Validation never reruns the provider. A provider text retry creates a new
  immutable proposal version instead of overwriting the old stage result.
- Legacy generation and proposal payloads remain compatible.

## Concerns

- The PostgreSQL terminal-transition race test is present but skipped locally
  because `WP_FIXPILOT_POSTGRES_TEST_URL` is not configured. The migration was
  nevertheless applied successfully to the configured Alembic PostgreSQL
  database.
- A separate Codex CLI review was started twice in read-only mode, but the CLI
  session terminated without returning a final findings message. The scoped
  code received a local lock-order and diff audit; obtain a completed external
  review before changing the SDD ledger to `complete`.

## Independent Review Fix

- RED: focused review regressions exposed the missing stale-stage lease API;
  historical snapshot update/approve, current-only proposal lookup, and stage
  error filtering were then exercised in the same focused suite.
- Historical snapshot versions now reject update and approval under the
  proposal row lock unless `is_current` is true. The regressions create a text
  retry first, then prove the archived version returns `409` without changing
  its proposal payload, state, or stages.
- A running stage has a fixed five-minute lease. A fresh lease returns
  `stage_in_progress`; a row-locked, demonstrably stale lease is reclaimed by
  a retrying worker with a new start time, retry count, and cleared incomplete
  data. The worker resumes only the reclaimed stage. PostgreSQL coverage proves
  that two concurrent reclaims have one winner when the optional database URL
  is configured.
- Existing-proposal lookup now selects only `is_current=true`, so a failed text
  retry cannot make a later create request return an archived
  `needs_attention` version.
- Proposal `field_errors` now include only field IDs present in the persisted
  snapshot schema. Technical `message`, provider, validation, and unknown-field
  errors remain in the stage payload and never appear as user field errors.
- Verification after the fixes: Ruff passed; focused Task 5 suites passed
  `48` tests with `2` optional PostgreSQL skips; Alembic remained at
  `0021_proposal_stages`; full backend passed `372` tests with `6` optional
  PostgreSQL skips.

## Lease Fencing Review Fix

- RED: two stage regressions failed because `PageProposalStage` had no
  `attempt_token`; the SQLite migration check also failed because revision
  `0021` did not create that column.
- Every begin, retry, and stale reclaim now issues a new opaque attempt token.
  Ready, attention, and failed transitions lock the stage row and require the
  exact token before changing state, result, or errors.
- Snapshot generation carries the token through template, text, and validation
  writes. Validation applies proposal and job changes only after the fenced
  stage transition succeeds.
- A late exception from a reclaimed worker rolls back and returns without
  changing the current stage, proposal, or job. Route coverage verifies both
  late success and late failure behavior after reclaim.
- Revision `0021` and the ORM model enforce a non-empty token of at most 64
  characters. The unreleased migration was verified with a PostgreSQL
  `0021 -> 0020 -> 0021` round trip and a SQLite upgrade/downgrade test.
- Verification: focused Task 5 suites passed `51` tests with `2` optional
  PostgreSQL skips; Ruff passed; the full backend passed `375` tests with `6`
  optional PostgreSQL concurrency skips; `git diff --check` passed.
- Independent review found one remaining terminal race: a stale failure could
  bypass `fail_stage` after the replacement attempt had already become ready.
  `_fail_snapshot_generation` now compares the locked stage token before
  inspecting its state, so late workers cannot change a completed proposal or
  job. The route regression covers both a running replacement and a completed
  replacement.
- Final rereview identified SQLAlchemy identity-map staleness with
  `expire_on_commit=False`: `SELECT FOR UPDATE` alone could return the old
  worker's cached token. `locked_stage` now uses `populate_existing=True`, and
  a separate-session regression proves the late worker observes the committed
  replacement token and terminal state. Final verification passed `52`
  focused tests with `2` optional skips and `376` backend tests with `6`
  optional PostgreSQL concurrency skips; Ruff remained clean.
