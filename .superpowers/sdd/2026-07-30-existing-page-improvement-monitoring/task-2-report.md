# Task 2 Report: Outbound Existing-Page Snapshot Capture

## Status

Implemented, hardened after round-one review, and locally verified.

## Delivered

- Added idempotent snapshot capture-job creation, project/site-bound claiming,
  five-minute lease recovery, terminal token hashing, safe failure handling, and
  immutable completion replay.
- Added authenticated outbound claim, complete, and fail routes.
- Added optimization-source snapshot capture through the existing registered
  ACF, Elementor, WPBakery, Bricks, and Gutenberg adapters.
- Persisted snapshot kind and source identity on private snapshot posts.
- Preserved current Yoast, Rank Math, and AIOSEO metadata in optimization
  snapshots and exposed their real title, description, and focus-keyword values
  in the snapshot schema.
- Expanded the source fingerprint to title, slug, permalink, content, page
  template, featured image, SEO metadata, and every matching registered
  builder's structure and clone metadata.
- Froze source URL and content hash at first claim, rejects null legacy hashes
  for new work, and rejects claim retry or completion after source drift.
- Added durable job-to-private-snapshot replay metadata. Ambiguous callback
  failures retain and reuse the same snapshot; definitive 4xx completion
  rejection deletes it.
- Added a completion-only `snapshot_claim_invalid` conflict code so expired or
  invalid claim-token 409s retain the snapshot for lease reclaim, while source
  and result conflicts remain definitive cleanup signals.
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
- Round-one backend RED: null source hashes, lease-time identity drift, and
  completion after a legacy null hash were accepted (`3 failed, 15 passed`).
- Round-one PHP RED: optimization schema SEO fields were empty and supported SEO
  metadata was not cloned.
- Added regressions for every fingerprint component, builder-meta mutation,
  all three supported SEO families, ambiguous completion replay, and 409
  snapshot cleanup without source writes.
- Round-two RED: an expired-claim completion 409 deleted the retained private
  snapshot; GREEN reclaims with a new token and completes using the same
  snapshot ID without another capture.

## Verification

- Backend focused/concurrency command: `19 passed, 2 skipped`.
- The two PostgreSQL concurrency tests skipped only because
  `WP_FIXPILOT_POSTGRES_TEST_URL` is not configured.
- Repository backend Ruff (`app`, `tests`, and `alembic`): clean.
- PHP optimization snapshot, template snapshot, snapshot draft-job, and change
  controller suites passed under PHP 8.2 in Docker.
- Full plugin PHP syntax lint: clean.

## Review

Local review covered outbound authentication, site binding, page/job lock order,
terminal races, claim identity persistence, strict schema/result validation,
registered adapter fingerprinting, SEO metadata cloning, retry replay, 4xx clone
cleanup, completion conflict classification, cron priority, and absence of
live-page writes.

## Concern

PostgreSQL race behavior is covered by committed tests but was not exercised
locally because the optional test database URL is absent.
