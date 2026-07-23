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
