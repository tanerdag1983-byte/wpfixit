# Task 5 Report: Existing-Page Review And Page Timeline UI

## Status

Complete after Round 2 review fixes. Monitoring and review data remain bound to the
proposal's captured source version, and no live-publishing action was added.

## Round 2 Fixes

- Split manual-check POST handling from the subsequent monitoring refresh. A failed
  POST reports that the check failed; a committed check followed by a failed refresh
  reports the successful check truthfully and offers `Resultaten opnieuw laden`.
- Kept monitoring cleared and loading stopped after a refresh failure. The retry only
  reloads monitoring and never repeats the already committed manual check.
- Made persisted page-scoped open recommendations take precedence over an improved
  score trend. Only pages without open recommendations can report `improved` or
  `monitoring`.

## Round 1 Fixes

- Bound captured content, current score factors, and projected score factors to
  `proposal.config_snapshot.source_content_hash`. A newer live observation is shown
  as a distinct warning and is never substituted as the proposal baseline.
- Approval now saves unsaved edits first and approves the exact returned proposal
  version. A failed save stops approval and leaves draft creation disabled.
- Replaced inferred lifecycle entries with durable proposal, candidate, draft-job,
  recommendation, check, and publication records. Publication is added only when a
  normal inventory sync proves that a managed draft/version is published.
- Added a durable `page_checked` event for every successful idempotent check and a
  durable recommendation event only when a recommendation is actually created.
- Cleared stale monitoring while proposals, saved packages, and checks refresh, with
  accessible loading and error states.
- Made status and open suggestions page-scoped across deduplicated recommendations.
- Added captured/live version context, score history, open suggestions, and both
  current and projected factor explanations while preserving the full-width preview.
- Derived latest and next check timestamps only from successful check events or an
  observed score timestamp. Inventory sync timestamps and failed fetches cannot
  advance the schedule.

## TDD Evidence

- Added failing backend regressions for captured-version projection, missing capture,
  durable lifecycle evidence, published managed-draft linkage, page-scoped status,
  successful-check timestamps, failed fetches, recommendation/check events, and
  edit-then-approve persistence.
- Added failing frontend regressions for save-before-approve, save failure, stale
  monitoring removal, captured score selection, live-change labeling, score history,
  open suggestions, and both sides of factor explanations.
- Focused backend result after implementation: 25 passed.
- Focused frontend result after implementation: 27 passed.

## Verification

- `backend/.venv/bin/python -m pytest --import-mode=importlib -q tests/wordpress tests/page_packages`:
  239 passed, 8 skipped.
- `backend/.venv/bin/ruff check app tests alembic`: passed.
- `frontend npm test -- --run`: 29 files, 118 tests passed.
- `frontend npm run lint`: passed.
- `frontend npm run build`: passed.
- `git diff --check`: passed.

### Round 2 Verification

- Focused backend route tests: 12 passed.
- Focused frontend review tests: 27 passed.
- `backend/.venv/bin/ruff check app tests alembic`: passed.
- `frontend npm test -- --run`: 29 files, 120 tests passed.
- `frontend npm run lint`: passed.
- `frontend npm run build`: passed.
- `git diff --check`: passed.

## Self-Review

- Tenant/project filters remain on page, proposal, candidate, draft-job, and timeline
  queries.
- Existing regeneration, compare, approval, and draft controls remain in place.
- WordPress creation remains draft-only and unavailable before approval.
- Manual checks remain idempotent for observed versions, scores, and recommendations;
  each successful check has its own durable check event.
- No publishing endpoint, control, or automatic publication behavior was introduced.

## Concerns

- Eight PostgreSQL concurrency tests were skipped because
  `WP_FIXPILOT_POSTGRES_TEST_URL` is not configured. These are explicit environment
  skips, not test failures.
- Vitest emits the repository's existing `--localstorage-file` warning; all frontend
  tests pass.
