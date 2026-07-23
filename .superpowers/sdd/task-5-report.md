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
