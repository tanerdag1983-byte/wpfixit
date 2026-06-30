# WP FixPilot Handoff

Updated: 2026-06-30

## Overview

Repository: `wp-fixpilot-new`

**Main branch** (this branch): Stable baseline. Contains the core platform, keyword opportunities, and page generation features.

**Active development branch**: `feature/platform-build` — work happens in the `.worktrees/platform-build` worktree. This is where the Managed Page Blueprints feature (Tasks 1–9) is being implemented.

## Current Development Status

For **live task status and progress** on the Managed Page Blueprints feature, see:
- `.worktrees/platform-build/HANDOFF.md` (detailed task status, latest commits)
- `.worktrees/platform-build/.superpowers/sdd/progress.md` (completion ledger)

### What Exists on Main

The baseline platform includes:

- **Backend**: FastAPI, SQLAlchemy, PostgreSQL via Supabase
- **Frontend**: React 19, TypeScript, Vite
- **WordPress Plugin**: PHP bridge with HMAC auth, page package system, builder/SEO adapters
- **Crawling**: Firecrawl v2 integration
- **Data**: DataForSEO keyword opportunities
- **AI**: Multi-provider recommendations (OpenAI, Anthropic, Gemini, OpenRouter)
- **Auth**: Supabase JWT + Google OAuth

Approved designs and plans are in:
- `docs/superpowers/specs/`
- `docs/superpowers/plans/`

### What's In Progress (Feature Branch)

**Managed Page Blueprints** — 9-task implementation in `feature/platform-build`:

| Task | Status (as of last sync) |
|---|---|
| Task 1: Backend blueprint persistence | Complete & approved |
| Task 2: WordPress cloning + REST lifecycle | Implementation done, final review pending |
| Tasks 3–9 | Not started |

See the worktree's `HANDOFF.md` for specifics.

## Known Issues on Main

Several bugs exist in the current `main` branch that should be addressed:

### High Priority

1. **Production `assert` guards** — Python `assert` is optimized away with `-O`. Replace with explicit checks:
   - `backend/app/api/routes/wordpress.py:447, 461, 518, 533, 580`
   - `backend/app/api/routes/priorities.py:56`
   - `backend/app/api/routes/ai_settings.py:557`
   - `backend/app/domains/priorities/service.py:132`

2. **DemoWordPressClient state leakage** — Class-level mutable dict at `backend/app/domains/wordpress/demo.py:6` causes test state to leak between runs.

3. **page_importance score always 0.5** — The audit engine never sets `importance` in `facts`, making the priority scoring's importance dimension constant.

### Medium Priority

4. **Frontend Priority page stub** — `frontend/src/routes/dashboard/PriorityPage.tsx` uses hardcoded data instead of calling the working API endpoint.
5. **Dashboard overview static data** — `AnalyticsConsole` and `HybridCommandCenter` use `dashboardData.ts` (static) instead of the live API.
6. **SQLAlchemy 2.x deprecation** — `session.get_bind()` pattern in background jobs should be replaced.
7. **Missing JWT secret in render.yaml** — `WP_FIXPILOT_SUPABASE_JWT_SECRET` is absent from deployment config.

### Low Priority

8. Non-functional UI elements (global search, sync button)
9. Unused dependencies (`@tanstack/react-query`, `react-hook-form`, `zod`)
10. Redis URL configured but never used

## Product Roadmap

After the managed-blueprint workflow is live (Task 9 complete), continue with:

1. DataForSEO keyword opportunities (largely complete)
2. Per-project AI providers/models and project prompts
3. Google Search Console OAuth, sync, trends
4. GA4 OAuth, traffic, engagement, conversions
5. Sitemap import and URL discovery
6. Internal-link analysis and approved updates
7. External-link validation and recommendations
8. PageSpeed/CrUX checks and recommendations
9. Yoast, Rank Math, All in One SEO metadata support
10. Combined SEO priority scoring (partial implementation exists)
11. Content Calendar with manual/auto publication
12. Project Brand DNA, rewrite versions, image styles, SEO score cards

These are required future phases, not optional ideas. Each needs persisted state, real API calls, sync status, error handling, tests, and deployment verification.

## Deployment Context

- **Frontend**: Vercel
- **Backend**: Render
- **Database/Auth**: Supabase
- **Source control**: GitHub `tanerdag1983-byte/wpfixit`
- **WordPress**: Staging site with bridge plugin installed

Do not commit credentials. Confirm environment variables in deployment platforms. Treat any exposed credentials as compromised and rotate before production launch.

## Important Decisions

- Human review is mandatory before creating WordPress drafts
- WordPress publishing remains manual
- Multiple blueprints per project/page type; one ready default per type
- Existing pages can be used as reference pages (not formal templates)
- Full builder structure is cloned; AI receives only editable text/link fields
- Builder-specific behavior belongs behind shared adapter contracts
- Official Google SEO changes may auto-apply with dashboard notice + optional email when user enables

## Required Verification

### Backend
```bash
cd backend
.venv/bin/ruff check app tests alembic
.venv/bin/python -m pytest --import-mode=importlib -q
.venv/bin/alembic upgrade head
```

### Frontend
```bash
cd frontend
npm install
npm run lint
npm test -- --run
npm run build
```

### WordPress Plugin
```bash
cd plugin/wp-fixpilot-bridge
php -d zend.assertions=1 -d assert.exception=1 tests/auth-test.php
php -d zend.assertions=1 -d assert.exception=1 tests/change-controller-test.php
php -d zend.assertions=1 -d assert.exception=1 tests/page-package-test.php
find . -name '*.php' -print0 | xargs -0 -n1 php -l
```
