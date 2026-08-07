# Task 5 Report: Existing-Page Review And Page Timeline UI

## Status

Complete. Existing-page opportunities now open the established proposal review flow,
with page monitoring and manual checks added without any live-publishing action.

## Delivered

- Added project-scoped monitoring and idempotent manual-check endpoints.
- Returned ordered versions, scores, recommendations, monitoring events, latest sync,
  next weekly check, current status, and proposal-scoped projected score factors.
- Added a complete ordered timeline derived from monitoring, proposal, approval,
  draft-job, and observed publication state.
- Added existing-page opportunity creation with the exact action label
  `Verbeteringsvoorstel maken` and safe handling while WordPress captures a snapshot.
- Kept the full-width preview above current/proposed comparisons and editable fields.
- Reused regeneration, comparison, approval, and draft controls. Draft creation remains
  disabled until approval; no publishing control was added.
- Added accessible score tables, timeline semantics, manual-check state, errors, and a
  polite live-region completion message.

## TDD Evidence

- Initial focused backend tests failed because the monitoring/check routes did not
  exist; initial focused frontend tests failed because the monitoring components and
  existing-page review behavior did not exist.
- Review regressions then failed for snapshot-wait responses, proposal-scoped
  projections, lifecycle events, current-version status, monitoring refresh, and
  accessible completion feedback before their production fixes were applied.
- Final focused result: 9 backend route tests and 36 frontend component tests passed.

## Verification

- `backend/.venv/bin/python -m pytest tests/wordpress/test_routes.py tests/page_packages -q`:
  141 passed, 2 skipped.
- The two skips require the optional `WP_FIXPILOT_POSTGRES_TEST_URL` concurrency test
  database.
- Scoped Ruff check: passed.
- `frontend npm test -- --run`: 29 files, 115 tests passed.
- `frontend npm run lint`: passed.
- `frontend npm run build`: passed.
- `git diff --check`: passed.

## Independent Review

An independent read-only Codex review found six issues: snapshot-wait handling,
proposal projection scope, stale projected scores after edits, missing lifecycle
events, historic recommendations affecting current status, and missing asynchronous
status announcement. All six were reproduced or verified against the current models
and fixed with regressions before commit.

## Concerns

- PostgreSQL-only concurrency tests were not run because
  `WP_FIXPILOT_POSTGRES_TEST_URL` is not configured. Their absence is reported by the
  suite as two explicit skips, not failures.
- Vitest emits the repository's existing `--localstorage-file` path warning; all tests
  pass.
