# WP FixPilot Agent Instructions

## Product Goal

WP FixPilot is a multi-project SEO SaaS that audits WordPress sites, combines live
search and analytics data, proposes evidence-based improvements, and creates safe
WordPress drafts for human review. It must never publish automatically.

## Repository Layout

- `backend/`: FastAPI, SQLAlchemy, Alembic, Supabase/PostgreSQL integration.
- `frontend/`: React/Vite dashboard deployed through Vercel.
- `plugin/wp-fixpilot-bridge/`: WordPress bridge plugin and PHP test harnesses.
- `docs/superpowers/specs/`: approved product and architecture designs.
- `docs/superpowers/plans/`: executable implementation plans.
- `.superpowers/sdd/`: task briefs, reports, review packages, and progress ledger.

## Current Development Workflow

- Work on `feature/platform-build` in the `platform-build` worktree.
- Read `.superpowers/sdd/progress.md` before resuming. Never repeat a completed task.
- Follow `docs/superpowers/plans/2026-06-28-managed-page-blueprints.md` in order.
- Use strict TDD: write and run a failing regression before production changes.
- Every task requires an independent review before it is marked complete.
- Do not move to the next task while important review findings remain open.
- Keep edits scoped. Do not revert unrelated or user-authored changes.
- Use `apply_patch` for manual file edits.

## Global Safety Rules

- A managed blueprint is always a normal WordPress `page` with `draft` status.
- Source pages and managed blueprint pages are immutable during generation.
- Generated pages are always WordPress drafts. Publishing requires human action.
- Preserve builder structure, ACF rows/repeaters, media IDs, styles, widgets, PHP page
  templates, featured images, and allowlisted non-text metadata.
- AI may change only schema-listed text fields and approved internal-link/CTA URLs.
- Every draft request must match blueprint ID, version, and live structure hash.
- Draft creation is idempotent per approved proposal and immutable snapshot.
- Delete incomplete clones after any post, metadata, builder, or SEO write failure.
- Keep existing page-package routes working until managed-blueprint migration is done.
- Never write API keys, passwords, OAuth secrets, tokens, or database URLs to git.

## Blueprint Responsibilities

- Task 1 owns backend persistence, lifecycle states, lineage, and database constraints.
- Task 2 owns generic WordPress cloning, REST lifecycle, authentication, snapshot
  validation, drift detection, idempotency, and cleanup.
- Task 3 owns concrete ACF, Elementor, WPBakery, Bricks, and Gutenberg adapters and
  production adapter registration.
- Task 4 owns the backend blueprint API and proposal-dependency checks before deletion.
- Later tasks own UI, schema-bound AI generation, approved draft creation, migration,
  end-to-end validation, release, and deployment.

## Required Verification

### Backend

```bash
cd backend
.venv/bin/ruff check app tests alembic
.venv/bin/python -m pytest --import-mode=importlib -q
.venv/bin/alembic upgrade head
```

### Frontend

Use the package manager declared by the repository and run its test, lint, and build
commands. Do not claim success from only one of these checks.

### WordPress Plugin

Run these under PHP 8.2:

```bash
php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php
php -d zend.assertions=1 -d assert.exception=1 tests/auth-test.php
php -d zend.assertions=1 -d assert.exception=1 tests/change-controller-test.php
php -d zend.assertions=1 -d assert.exception=1 tests/page-package-test.php
find . -name '*.php' -print0 | xargs -0 -n1 php -l
```

Docker may be used when local PHP is unavailable.

## Product Roadmap That Must Be Preserved

After the managed-blueprint publication flow is stable and live, continue with:

1. DataForSEO keyword opportunities with strict topical/category relevance.
2. Per-project AI providers, models, company profile, and project prompt.
3. Google Search Console OAuth, property selection, sync, trends, and opportunities.
4. GA4 OAuth, property selection, traffic, engagement, conversion, and revenue data.
5. Sitemap import and recurring URL discovery.
6. Internal-link analysis, approved link updates, orphan-page detection, and suggestions.
7. External-link analysis, validation, quality checks, and recommendations.
8. PageSpeed/CrUX checks and safe performance recommendations or changes.
9. Yoast, Rank Math, and All in One SEO metadata support.
10. Combined SEO priority scoring using WordPress, crawl, GSC, GA4, and DataForSEO data.

Do not collapse these into mockups. Each integration needs persisted state, real API
calls, user-visible sync status, error handling, tests, and deployment verification.

