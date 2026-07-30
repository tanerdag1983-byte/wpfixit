# Task 2 Report: Outbound Existing-Page Snapshot Capture

## Status

Implemented and locally verified.

## Delivered

- Added idempotent snapshot capture-job creation, project/site-bound claiming,
  five-minute lease recovery, terminal token hashing, safe failure handling, and
  immutable completion replay.
- Added authenticated outbound claim, complete, and fail routes.
- Added optimization-source snapshot capture through the existing registered
  ACF, Elementor, WPBakery, Bricks, and Gutenberg adapters.
- Persisted snapshot kind and source identity on private snapshot posts.
- Kept live source pages read-only and deletes incomplete or concurrently stale
  snapshot clones.
- Polls one snapshot job at priority 5 before the existing draft-job callback.
- Kept the direct `WordPressClient` blueprint compatibility path unchanged; the
  new optimization path is outbound and does not require a SaaS-to-WordPress
  request.

## TDD Evidence

- Backend RED: collection failed because
  `app.domains.wordpress.snapshot_jobs` did not exist.
- PHP RED: `capture_optimization_snapshot()` was undefined.
- Strict-boundary RED: a numeric-string `snapshot_id` returned HTTP 200 before
  strict integer validation; GREEN returns HTTP 422.

## Verification

- Backend focused/concurrency command: `14 passed, 2 skipped`.
- The two PostgreSQL concurrency tests skipped only because
  `WP_FIXPILOT_POSTGRES_TEST_URL` is not configured.
- Focused backend Ruff: clean.
- PHP optimization snapshot, template snapshot, and snapshot draft-job suites:
  passed under PHP 8.2 in Docker.
- Additional draft-job and draft-job admin regressions: passed.
- Owned-file PHP lint: clean.

## Review

Local review covered outbound authentication, site binding, page/job lock order,
terminal races, strict schema/result validation, snapshot persistence checks,
registered adapter wiring, cron priority, clone cleanup, and absence of live-page
writes. A separate read-only Codex review was started but interrupted by the
explicit status checkpoint before it returned findings.

## Concern

PostgreSQL race behavior is covered by committed tests but was not exercised
locally because the optional test database URL is absent.
