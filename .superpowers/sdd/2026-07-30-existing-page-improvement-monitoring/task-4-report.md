# Task 4 Report

## Status

Complete.

## Delivered

- Existing-page opportunities now return `202` while one outbound snapshot capture
  job is pending, then reuse the completed immutable snapshot for generation.
- Existing-page proposals persist `source_wordpress_page_id`, snapshot identity, and
  a frozen generation context containing the target URL, prior score, evidence, and
  captured field values.
- Approval and regeneration validate against the stored snapshot context. The source
  WordPress page is never written.
- Existing-page drafts can use only `create_or_get_draft_job`; legacy direct draft and
  manual handoff paths reject them.
- `new_page` behavior remains on the existing default-blueprint path, and `review`
  remains a `409`.

## TDD Evidence

- Initial focused regression run: `3 failed, 19 passed` on the previous
  new-page-only route behavior.
- Approved-proposal retry regression failed by creating a second proposal before the
  source-bound idempotency fix.
- Final review regressions failed before the manual-handoff guard and shared
  source-page lock, then passed after the minimal fixes.

## Verification

- Focused backend: `24 passed`.
- Legacy proposal and handoff regressions: `42 passed`.
- Full page-package suite: `128 passed, 2 skipped` (optional PostgreSQL tests require
  `WP_FIXPILOT_POSTGRES_TEST_URL`).
- Ruff: `All checks passed!`
- Plugin `tests/snapshot-draft-job-test.php`: lifecycle and snapshot draft-job tests
  passed under PHP 8.2 Docker.

## Review

Independent review found an alternate manual handoff draft path and a concurrent
snapshot-wrapper race. Both were resolved by rejecting source-bound proposals from
handoff issue/redeem/complete and locking the shared synchronized WordPress page
before snapshot lookup/wrapping. Existing legacy route tests cover unchanged
`new_page` behavior.

## Concerns

No blocking concerns. The shared-row locking contract is covered by a focused query
regression; a live PostgreSQL concurrency test was not added to keep Task 4 scoped.
