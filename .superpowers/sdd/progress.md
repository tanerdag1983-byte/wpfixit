# Managed Page Blueprints SDD Progress

Plan: docs/superpowers/plans/2026-06-28-managed-page-blueprints.md
Start: 721dd07

Baseline: backend 143 passed; frontend 60 passed, lint/build clean; plugin 3 suites passed.
Task 1: complete (commits 721dd07..87fd133, final review approved; backend 170 passed, Alembic PostgreSQL upgrade clean).
Task 2: complete (commits 87fd133..d5e8279, final review approved; plugin 4 suites passed, lint clean, all atomicity/validation/idempotency/cleanup verified).
Task 3: complete (commits 0b7f113..6984919, final review approved; plugin 6 suites passed, lint clean, builder structure preservation regressions covered).
Task 4: complete (commits 3e1dde6..bd5daa7, final review approved; backend 198 passed, blueprint API 49 passed, Alembic PostgreSQL upgrade clean, plugin 6 suites and PHP lint clean).
Task 5: complete (commits fc868a1..1aaf931, final review approved; frontend 26 files/77 tests passed, lint and production build clean).
Task 6: complete (commit 97036d3, final review approved; backend 210 passed, focused schema/provider 23 passed, Ruff clean).
Task 7: complete (commits 5040aa7..1c9cceb, final review approved; backend 214 passed, frontend 26 files/78 tests passed, lint/build clean, PHP blueprint lifecycle passed).
Task 8: complete (commit 57368ee, final review approved; backend 214 passed, frontend 26 files/80 tests passed, lint/build clean).
Task 9: in progress (release commit d9eb2c0 is on GitHub main; GitHub CI, Render API and Vercel production are green; WordPress staging plugin install and source-to-draft acceptance remain).

# Manual WordPress Handoff And Proposal Versions SDD Progress

Plan: docs/superpowers/plans/2026-07-07-manual-wordpress-handoff-and-proposal-versions.md
Start: e92d290

Task 1: complete (commits e92d290..ffb2608, final review approved; backend 222 passed, 1 skipped for missing `WP_FIXPILOT_POSTGRES_TEST_URL`, focused page-package persistence 4 passed, Alembic PostgreSQL upgrade clean).
Task 2: complete (commits ffb2608..ee41f77 plus follow-up hardening, local review approved; focused proposal-version and handoff regressions 10 passed, backend ruff passed).
Task 3: complete (full-width preview, compare flow, regeneration controls, and generated opportunity state shipped; frontend lint passed, focused frontend tests 12 passed, frontend build passed, backend payload regressions 15 passed, backend ruff passed).
Task 4: complete (commit 16b1e44, local review approved; plugin manual import screen, redeem flow, focused manual-handoff test passed, PHP lint clean).
Task 5: complete (commit 95b197d, local review approved; confirm-import flow now creates one draft, reports completion idempotently, focused backend handoff tests 8 passed, plugin targeted suites passed, PHP lint clean).
Task 6: in progress (local verification green: backend 232 passed, 1 skipped for missing `WP_FIXPILOT_POSTGRES_TEST_URL`; frontend 26 files/84 tests passed, lint/build clean; plugin auth/change-controller/page-package/manual-handoff suites passed and PHP lint clean; live WordPress acceptance remains).

# Outbound WordPress Draft Jobs SDD Progress

Plan: docs/superpowers/plans/2026-07-11-outbound-wordpress-draft-jobs.md
Start: c3e9b8a

Task 1: complete (commits 831407c..0d570e8, independent review approved after persistence hardening; focused model tests 12 passed, backend 254 passed with 1 optional PostgreSQL concurrency skip, Ruff clean, PostgreSQL Alembic downgrade/upgrade clean).
Task 2: complete (commit 66189d9, independent review approved after atomic terminal-write and trusted URL hardening; backend 265 passed with 3 optional PostgreSQL concurrency skips, Ruff clean).
Task 3: complete (commit 7ab28b1, iterative independent review findings resolved; final extra reviewer was unavailable due usage limit, followed by local lock-order audit; backend 274 passed with 3 optional PostgreSQL skips, Ruff clean, Alembic at 0019 head).
Task 4: complete (commit 64952fa, local review because subagent usage was exhausted; all plugin contract suites and PHP lint passed).
Task 5: complete (commit 0accc1a, local review because subagent usage was exhausted; all plugin suites and PHP lint passed).
Task 6: complete (local review because subagent usage was exhausted; frontend 26 files/87 tests passed, lint/build clean; focused backend proposal and draft-job routes 18 passed, Ruff clean).
Task 7: complete (commits d77cd8f..76066dd, independent review approved after persistent recovery status, scoped per-template retries, sibling-state preservation, and misleading migration CTA removal; 15 focused backend migration tests passed, 381 backend tests passed with 6 optional PostgreSQL skips, 17 focused frontend tests and 92 full frontend tests passed, Ruff/lint/build clean).
Task 8: in progress.

# Versioned Template Snapshots Release 1 SDD Progress

Plan: docs/superpowers/plans/2026-07-23-versioned-template-snapshots-release-1.md
Start: 980b8c5

Baseline: backend 281 passed, 3 optional PostgreSQL skips, Ruff clean; frontend 26 files/88 tests passed, lint/build clean; all plugin suites and PHP lint passed under PHP 8.2.
Preflight: fixed the stale AI settings API-module mock that omitted `apiBaseUrl`.
Task 1: complete (commits 59176b9..9047785, independent review approved after legacy v1 compatibility and document-field validation fixes; all 10 plugin suites and PHP lint passed under PHP 8.2).
Task 2: complete (commits f4f0f05..cec676d, independent review approved after nullable-safe identity constraints and committed migration round-trip coverage; 41 focused tests passed, Ruff clean, PostgreSQL and SQLite migration checks passed).
Task 3: complete (commits 3330697..5d86f81, independent review approved after four hardening rounds covering migration locking, durable cleanup, stale-default selection, native trust validation, and failed-proposal recovery; 333 backend tests passed with 4 optional PostgreSQL concurrency skips, Ruff clean, Alembic at head).
Task 4: complete (commits 7ee2e25..ca84d9b, independent review approved after snapshot-prompt isolation, legacy prompt-version preservation, and self-closing rich-text hardening; 60 focused tests and 351 backend tests passed with 4 optional PostgreSQL concurrency skips, Ruff clean, Alembic at head).
Task 5: complete (commits 1202b2f..a8aff34, independent review approved after resumable-stage recovery, lease fencing, and identity-map refresh hardening; 52 focused tests passed with 2 optional PostgreSQL skips, 376 backend tests passed with 6 optional PostgreSQL skips, Ruff clean, PostgreSQL and SQLite migration round-trips passed).
Task 6: complete (commits cba9ac1..8650b06, independent review approved after migrated-proposal validation, atomic database locking, persisted document verification, and race-free clone serialization; 57 focused tests and 379 backend tests passed with 6 optional PostgreSQL skips, Ruff clean, all plugin tests and PHP lint passed, PostgreSQL and SQLite migration round-trips passed).
Task 7: complete (commits d77cd8f..76066dd, independent review approved after persistent migration recovery, scoped retries, and immutable snapshot settings; 381 backend tests passed with 6 optional PostgreSQL skips, 92 frontend tests passed, Ruff/lint/build clean).
Task 8: complete (commits 4b27c82..8818e8b, independent review approved after resumable-stage recovery, snapshot candidate comparison, current validation retry, optional-field editing, allowlist preservation, and draft-contract verification; 384 backend tests passed with 6 optional PostgreSQL skips, 106 frontend tests passed, Ruff/lint/build clean).
Task 9: in progress.
