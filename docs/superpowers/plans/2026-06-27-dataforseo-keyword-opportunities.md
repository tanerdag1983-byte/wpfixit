# DataForSEO Keyword Opportunities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first working DataForSEO integration that stores credentials, syncs keyword opportunities, and shows them in the Kansen dashboard tab.

**Architecture:** Add a focused `dataforseo` backend domain with models, provider adapter, service functions, and FastAPI routes. The frontend gets a settings panel for credentials and a live Opportunities page that reads and syncs project keyword opportunities.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, requests, React, TypeScript, Vitest.

## Global Constraints

- Credentials are encrypted with the existing crypto helper.
- API responses never include plaintext credentials.
- Sync is idempotent by `project_id`, `keyword`, `location_code`, and `language_code`.
- Owners/admins manage credentials and start syncs; project members can read opportunities.
- DataForSEO failures must not delete existing opportunities.

---

### Task 1: Backend DataForSEO Models And Migration

**Files:**
- Create: `backend/app/domains/dataforseo/__init__.py`
- Create: `backend/app/domains/dataforseo/models.py`
- Create: `backend/alembic/versions/0013_dataforseo_keyword_opportunities.py`
- Test: `backend/tests/dataforseo/test_models.py`

**Interfaces:**
- Produces: `DataForSeoConnection`, `KeywordOpportunity`.

- [ ] **Step 1: Write failing model tests**

Create `backend/tests/dataforseo/test_models.py` with tests that insert a connection and keyword opportunity, enforce one connection per organization, and enforce unique keyword opportunities per project/location/language.

- [ ] **Step 2: Run model tests and confirm failure**

Run: `./.venv/bin/pytest tests/dataforseo/test_models.py -q`
Expected: import failure for `app.domains.dataforseo`.

- [ ] **Step 3: Implement models and migration**

Create the two SQLAlchemy models and Alembic table definitions.

- [ ] **Step 4: Run model tests**

Run: `./.venv/bin/pytest tests/dataforseo/test_models.py -q`
Expected: pass.

### Task 2: Backend Routes, Provider, And Sync Service

**Files:**
- Create: `backend/app/domains/dataforseo/provider.py`
- Create: `backend/app/domains/dataforseo/service.py`
- Create: `backend/app/api/routes/dataforseo.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/dataforseo/test_routes.py`

**Interfaces:**
- Produces: `DataForSeoProvider.test_connection()`, `DataForSeoProvider.keyword_ideas(seeds)`, `sync_keyword_opportunities(session, project, provider)`.

- [ ] **Step 1: Write failing route tests**

Tests cover credential-free responses, safe failed tests, successful sync with mocked provider rows, idempotent upsert, and cross-organization access rejection.

- [ ] **Step 2: Run route tests and confirm failure**

Run: `./.venv/bin/pytest tests/dataforseo/test_routes.py -q`
Expected: route import failure.

- [ ] **Step 3: Implement provider, service, and routes**

Provider uses DataForSEO Basic Auth and `requests.post`. Routes use existing membership patterns and encrypted storage.

- [ ] **Step 4: Run backend checks**

Run: `./.venv/bin/pytest tests/dataforseo -q && ./.venv/bin/ruff check app tests`
Expected: pass.

### Task 3: Frontend Settings And Live Opportunities

**Files:**
- Create: `frontend/src/features/settings/DataForSeoPanel.tsx`
- Create: `frontend/src/features/settings/DataForSeoPanel.test.tsx`
- Modify: `frontend/src/features/settings/AiSettingsPanel.tsx`
- Modify: `frontend/src/routes/dashboard/OpportunitiesPage.tsx`
- Modify: `frontend/src/routes/dashboard/OpportunitiesPage.test.tsx`
- Modify: `frontend/src/app/App.tsx`

**Interfaces:**
- Consumes: backend routes from Task 2.
- Produces: settings UI for DataForSEO and live Kansen data.

- [ ] **Step 1: Write failing frontend tests**

Tests cover saving/testing DataForSEO credentials, loading opportunities, syncing opportunities, and empty state.

- [ ] **Step 2: Run frontend tests and confirm failure**

Run: `npm test -- --run src/features/settings/DataForSeoPanel.test.tsx src/routes/dashboard/OpportunitiesPage.test.tsx`
Expected: missing component/behavior failures.

- [ ] **Step 3: Implement frontend components**

Add DataForSEO panel to settings, pass `projectId` into OpportunitiesPage, and replace static opportunities with API data.

- [ ] **Step 4: Run frontend checks**

Run: `npm test -- --run src/features/settings/DataForSeoPanel.test.tsx src/routes/dashboard/OpportunitiesPage.test.tsx && npm run build`
Expected: pass.

### Task 4: Final Verification And Commit

**Files:**
- All files changed in Tasks 1-3.

- [ ] **Step 1: Run backend verification**

Run: `cd backend && ./.venv/bin/pytest tests/dataforseo tests/recommendations tests/priorities -q && ./.venv/bin/ruff check app tests`
Expected: pass.

- [ ] **Step 2: Run frontend verification**

Run: `cd frontend && npm test -- --run src/features/settings/DataForSeoPanel.test.tsx src/routes/dashboard/OpportunitiesPage.test.tsx src/features/settings/AiSettingsPanel.test.tsx && npm run build`
Expected: pass.

- [ ] **Step 3: Commit and push**

Commit message: `feat: add dataforseo keyword opportunities`.
