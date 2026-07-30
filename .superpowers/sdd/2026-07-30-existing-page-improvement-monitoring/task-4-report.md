# Task 4 Report

## Status

Complete after Round 1 review fixes.

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
- Optimization-source snapshot wrappers use the persisted
  `optimization-source-v1` provenance and are excluded from ordinary blueprint
  registry, detail, mutation, default, and version paths.
- Frozen capture identity drift retires stale queued/claimed work under the shared
  source-page lock and creates or reuses one fresh capture. Completion conflicts
  preserve replay-safe terminal state and an open successor.

## TDD Evidence

- Initial focused regression run: `3 failed, 19 passed` on the previous
  new-page-only route behavior.
- Approved-proposal retry regression failed by creating a second proposal before the
  source-bound idempotency fix.
- Final review regressions failed before the manual-handoff guard and shared
  source-page lock, then passed after the minimal fixes.
- Round 1 registry/default regressions failed while optimization snapshots remained
  visible and selectable.
- Round 1 drift regressions failed while stale claimed jobs were reused, expired
  claims rolled back repeatedly, and null-hash completion left no open successor.
- The PHP source post/content/meta byte comparison was added as a characterization
  regression and was green before and after the backend fixes.

## Verification

- Focused backend: `27 passed`.
- Snapshot job service/routes: `22 passed`.
- Blueprint route/service regressions: `53 passed`.
- Full page-package suite: `131 passed, 2 skipped` (optional PostgreSQL tests require
  `WP_FIXPILOT_POSTGRES_TEST_URL`).
- Ruff: `All checks passed!`
- Plugin `tests/snapshot-draft-job-test.php`: lifecycle and snapshot draft-job tests
  passed under PHP 8.2 Docker.
- The PostgreSQL source-drift completion/retry race regression was added but skipped
  because `WP_FIXPILOT_POSTGRES_TEST_URL` is not configured.

## Review

Independent review found an alternate manual handoff draft path and a concurrent
snapshot-wrapper race. Both were resolved by rejecting source-bound proposals from
handoff issue/redeem/complete and locking the shared synchronized WordPress page
before snapshot lookup/wrapping. Round 1 review then found blueprint registry leakage,
expired-claim drift rollback, and missing null-hash recovery. These were resolved with
provenance filtering, page-first claim locking, replayable stale terminal state, and
one recoverable fresh capture. Route and service regressions cover unchanged
`new_page` default resolution and internal existing-page resolution.

## Concerns

No blocking concerns. The PostgreSQL race regression is present but was not executed
because the optional PostgreSQL test URL is unavailable in this environment.
