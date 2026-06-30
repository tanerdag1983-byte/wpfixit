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
- `.superpowers/sdd/`: task briefs, reports, review packages, and progress ledger (in worktrees).

## Current Development Workflow

**Active development:** Work on `feature/platform-build` in the `.worktrees/platform-build` worktree.

**Integration branch:** `main` (this branch) is the stable baseline. New features merge here after completion.

When resuming work on the Managed Page Blueprints feature:
- Read `.worktrees/platform-build/.superpowers/sdd/progress.md` to see completed tasks.
- Follow `docs/superpowers/plans/2026-06-28-managed-page-blueprints.md` in order.
- Use strict TDD: write and run a failing regression before production changes.
- Every task requires an independent review before it is marked complete.
- Do not move to the next task while important review findings remain open.
- Keep edits scoped. Do not revert unrelated or user-authored changes.

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
cd plugin/wp-fixpilot-bridge
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
11. Drag-and-drop Content Calendar with per-item manual or pre-approved automatic
    publication.
12. Project-specific Brand DNA, block/page rewrite versions, image-style proposals, and
    explainable SEO score cards for every existing and new page.

Do not collapse these into mockups. Each integration needs persisted state, real API
calls, user-visible sync status, error handling, tests, and deployment verification.

## Known Issues on Main Branch

Several bugs have been identified in the current `main` codebase:

1. **Production `assert` statements** — Multiple handlers use `assert x is not None` which is removed when Python runs with `-O`. Replace with explicit `if ... is None: raise` checks in:
   - `backend/app/api/routes/wordpress.py:447, 461, 518, 533, 580`
   - `backend/app/api/routes/priorities.py:56`
   - `backend/app/api/routes/ai_settings.py:557`
   - `backend/app/domains/priorities/service.py:132`

2. **DemoWordPressClient shared state** — `backend/app/domains/wordpress/demo.py:6` uses a class-level mutable dict causing test state leakage. Move to instance-level in `__init__`.

3. **Frontend stubs not wired** — `frontend/src/routes/dashboard/PriorityPage.tsx` uses hardcoded mock data instead of calling the working backend API `GET /projects/{id}/seo-priority-score`.

4. **SQLAlchemy 2.x deprecation** — `session.get_bind()` pattern in background jobs should pass `Engine` directly.

5. **page_importance always defaults to 0.5** — The audit engine never sets the `importance` key in `facts`, making priority scoring incomplete.
