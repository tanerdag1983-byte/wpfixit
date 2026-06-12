# WP FixPilot Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-oriented WP FixPilot SaaS that combines WordPress, Google Search Console, GA4, Firecrawl, deterministic audits, AI recommendations, prioritized actions, and manually approved WordPress publishing.

**Architecture:** Use a TypeScript React frontend and a domain-organized FastAPI modular monolith backed by PostgreSQL. Celery workers handle provider syncs, crawls, audits, AI jobs, and WordPress writes; provider adapters isolate Google, Firecrawl, OpenAI, and SEO-plugin specifics.

**Tech Stack:** React 19, Vite, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, React Router, Recharts, FastAPI, Python 3.12, SQLAlchemy 2, Alembic, PostgreSQL, Redis, Celery, Supabase Auth, pytest, Vitest, Playwright, and PHPUnit.

---

## File Structure

```text
wp-fixpilot-new/
  .github/workflows/ci.yml
  backend/
    alembic/
    app/
      api/routes/
      core/
      domains/
        audits/
        crawls/
        dashboards/
        ga4/
        google/
        jobs/
        priorities/
        projects/
        recommendations/
        wordpress/
      main.py
    tests/
    alembic.ini
    pyproject.toml
  frontend/
    src/
      app/
      components/
      features/
      lib/
      routes/
    tests/
    package.json
  plugin/wp-fixpilot-bridge/
    includes/
    tests/
    wp-fixpilot-bridge.php
  infrastructure/
    render.yaml
    supabase/
    docker-compose.yml
  docs/
```

### Task 1: Repository And Local Infrastructure

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/tests/test_health.py`
- Create: `frontend/package.json`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/App.test.tsx`
- Create: `infrastructure/docker-compose.yml`
- Create: `.github/workflows/ci.yml`
- Create: `.env.example`

- [ ] **Step 1: Write failing backend health test**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_service_status() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "wp-fixpilot-api"}
```

- [ ] **Step 2: Run backend test and verify RED**

Run: `cd backend && uv run pytest tests/test_health.py -q`

Expected: FAIL because `app.main` does not exist.

- [ ] **Step 3: Implement minimal FastAPI application**

```python
from fastapi import FastAPI

app = FastAPI(title="WP FixPilot API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "wp-fixpilot-api"}
```

- [ ] **Step 4: Write and run failing frontend smoke test**

```tsx
import { render, screen } from "@testing-library/react";
import { App } from "./App";

it("renders the product name", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "WP FixPilot" })).toBeVisible();
});
```

Run: `cd frontend && npm test -- --run`

Expected: FAIL because the app is not implemented.

- [ ] **Step 5: Implement frontend shell and local services**

Create the minimal app heading, Vite/Vitest configuration, PostgreSQL and Redis
services, strict environment validation, and CI jobs for backend and frontend.

- [ ] **Step 6: Verify and commit**

Run:

```bash
cd backend && uv run pytest -q
cd ../frontend && npm test -- --run && npm run build
```

Expected: all commands PASS.

Commit: `git commit -am "build: scaffold WP FixPilot platform"`

### Task 2: Database, Auth, Tenancy, And Projects

**Files:**
- Create: `backend/app/core/database.py`
- Create: `backend/app/core/security.py`
- Create: `backend/app/domains/projects/models.py`
- Create: `backend/app/domains/projects/schemas.py`
- Create: `backend/app/domains/projects/service.py`
- Create: `backend/app/api/routes/projects.py`
- Create: `backend/alembic/versions/0001_identity_projects.py`
- Create: `backend/tests/projects/test_project_routes.py`
- Create: `frontend/src/features/auth/`
- Create: `frontend/src/features/projects/`

- [ ] **Step 1: Write tenant isolation route tests**

```python
def test_member_can_list_only_organization_projects(client, auth_as, projects):
    auth_as(projects.member)
    response = client.get("/projects")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [
        str(projects.member_project.id)
    ]


def test_non_member_cannot_read_project(client, auth_as, projects):
    auth_as(projects.outsider)
    response = client.get(f"/projects/{projects.member_project.id}")

    assert response.status_code == 404
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && uv run pytest tests/projects/test_project_routes.py -q`

Expected: FAIL because tenancy models and routes are absent.

- [ ] **Step 3: Implement identity and project persistence**

Create `profiles`, `organizations`, `organization_members`, and `projects`.
Validate Supabase JWTs, resolve the current profile, and require membership in
every project service query.

- [ ] **Step 4: Implement project CRUD API**

Support:

```text
POST /projects
GET /projects
GET /projects/{id}
DELETE /projects/{id}
```

Deletion is soft-delete and available only to organization owners/admins.

- [ ] **Step 5: Implement auth and project UI**

Build login, registration, protected routes, organization/project switchers,
project list, creation dialog, and delete confirmation with TanStack Query.

- [ ] **Step 6: Verify and commit**

Run backend project tests, frontend auth/project tests, migration upgrade and
downgrade, then commit `feat: add tenant-safe project management`.

### Task 3: WordPress Bridge, Inventory, And Audit Foundation

**Files:**
- Create: `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`
- Create: `plugin/wp-fixpilot-bridge/includes/class-auth.php`
- Create: `plugin/wp-fixpilot-bridge/includes/class-rest-controller.php`
- Create: `plugin/wp-fixpilot-bridge/tests/test-rest-controller.php`
- Create: `backend/app/domains/wordpress/`
- Create: `backend/app/domains/audits/`
- Create: `backend/alembic/versions/0002_wordpress_audits.py`
- Create: `backend/tests/wordpress/`
- Create: `backend/tests/audits/`

- [ ] **Step 1: Write failing signature and replay tests**

```php
public function test_rejects_replayed_signed_request(): void {
    $request = $this->signed_request('GET', '/inventory', 'fixed-nonce');

    $this->assertTrue($this->auth->verify($request));
    $this->assertWPError($this->auth->verify($request));
}
```

- [ ] **Step 2: Write failing backend audit tests**

```python
def test_audit_flags_missing_title_and_long_slug(audit_page):
    result = audit_page(title="", slug="x" * 76)

    assert result.score < 80
    assert {issue.type for issue in result.issues} == {
        "missing_title",
        "slug_too_long",
    }
```

- [ ] **Step 3: Verify RED in PHPUnit and pytest**

Expected: both suites fail because bridge and audit engine are absent.

- [ ] **Step 4: Implement secure bridge and inventory**

Add health and inventory routes for posts/pages. Authenticate timestamped HMAC
requests, reject nonce replay, check capabilities, and return normalized fields.

- [ ] **Step 5: Implement WordPress connection and idempotent sync**

Support:

```text
POST /projects/{id}/wordpress-connect
POST /projects/{id}/sync-pages
GET /projects/{id}/wordpress-pages
```

Use unique `(project_id, wordpress_object_id, post_type)` constraints and
upserts rather than delete/reinsert.

- [ ] **Step 6: Implement deterministic audit, issues, and recommendations**

Create page scores, typed issues, rule-based recommendations, audit history, and
the requested project audit endpoint.

- [ ] **Step 7: Verify and commit**

Run PHPUnit, WordPress route contract tests, backend audit tests, and migrations.
Commit `feat: add WordPress sync and deterministic SEO audits`.

### Task 4: Dashboard Foundation, Filters, Search, And SaaS Usage

**Files:**
- Create: `backend/app/domains/dashboards/`
- Create: `backend/app/domains/jobs/`
- Create: `backend/app/domains/subscriptions/`
- Create: `frontend/src/routes/dashboard/`
- Create: `frontend/src/components/charts/`
- Create: `frontend/src/features/issues/`
- Create: `frontend/src/features/recommendations/`
- Create: `frontend/tests/dashboard.spec.ts`

- [ ] **Step 1: Write failing combined filter API test**

```python
def test_dashboard_combines_search_and_all_filters(client, project):
    response = client.get(
        f"/projects/{project.id}/dashboard-overview",
        params={
            "q": "revisie",
            "priority": "high",
            "page_type": "service",
            "status": "publish",
            "max_score": 70,
        },
    )

    assert response.status_code == 200
    assert all(item["priority"] == "high" for item in response.json()["pages"])
```

- [ ] **Step 2: Verify RED**

Run focused backend and frontend dashboard tests.

- [ ] **Step 3: Implement dashboard query service and jobs**

Return summary, issues, recommendations, priority actions, job status, audit
history, pagination, sorting, search, and combined filters.

- [ ] **Step 4: Implement frontend dashboard foundation**

Build the shell, responsive navigation, KPI components, accessible chart
wrappers, data tables, filters, realtime search, loading skeletons, empty states,
and errors.

- [ ] **Step 5: Add subscription and usage records**

Implement plan limits and usage counters without coupling provider billing into
domain services. Use a fake billing adapter in tests.

- [ ] **Step 6: Verify and commit**

Run pytest, Vitest, Playwright dashboard smoke tests, and production build.
Commit `feat: add dashboard workflows and SaaS usage controls`.

### Task 5: Google OAuth And Search Console

**Files:**
- Create: `backend/app/domains/google/oauth.py`
- Create: `backend/app/domains/google/token_store.py`
- Create: `backend/app/domains/gsc/`
- Create: `backend/alembic/versions/0003_google_gsc.py`
- Create: `backend/tests/gsc/`
- Create: `frontend/src/features/google-connections/`
- Create: `frontend/src/routes/dashboard/SearchConsolePage.tsx`

- [ ] **Step 1: Write failing OAuth state and token encryption tests**

```python
def test_oauth_callback_rejects_state_for_another_user(oauth_service, users):
    state = oauth_service.create_state(users.alice.id, "project-1")

    with pytest.raises(InvalidOAuthState):
        oauth_service.consume_state(state, users.bob.id)
```

- [ ] **Step 2: Write failing idempotent GSC import test**

```python
def test_gsc_sync_upserts_same_daily_query(session, gsc_sync, gsc_fixture):
    gsc_sync.import_rows(gsc_fixture)
    gsc_sync.import_rows(gsc_fixture)

    assert session.scalar(select(func.count(GscQuery.id))) == 1
```

- [ ] **Step 3: Verify RED**

Run: `cd backend && uv run pytest tests/gsc -q`

- [ ] **Step 4: Implement OAuth2 Authorization Code plus PKCE**

Use encrypted refresh tokens, state expiry, incremental read-only scopes,
offline access, token refresh locking, disconnect, and revocation states.

- [ ] **Step 5: Implement property selection and GSC sync**

Support the requested endpoints plus property listing and binding. Import daily
page and query/page data with overlapping sync windows and composite upserts.

- [ ] **Step 6: Implement Search Console dashboard**

Add clicks, impressions, CTR, position, top queries, best pages, declining
pages, date comparison, filters, and export.

- [ ] **Step 7: Verify and commit**

Run OAuth security tests, provider contract tests, migrations, frontend tests,
and build. Commit `feat: integrate Google Search Console`.

### Task 6: Google Analytics 4

**Files:**
- Create: `backend/app/domains/ga4/`
- Create: `backend/alembic/versions/0004_ga4.py`
- Create: `backend/tests/ga4/`
- Create: `frontend/src/routes/dashboard/Ga4Page.tsx`

- [ ] **Step 1: Write failing GA4 report mapping tests**

```python
def test_page_report_maps_key_events_and_optional_revenue(map_report):
    row = map_report(
        dimensions={"date": "20260601", "pagePath": "/revisie"},
        metrics={
            "sessions": "42",
            "activeUsers": "31",
            "engagementRate": "0.63",
            "keyEvents": "4",
            "totalRevenue": "",
        },
    )

    assert row.key_events == 4
    assert row.revenue is None
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && uv run pytest tests/ga4 -q`

- [ ] **Step 3: Implement property selection and reports**

Use the Google Analytics Admin API to list properties and the Data API
`runReport` method for page/date and source-medium-campaign/date reports.

- [ ] **Step 4: Implement requested GA4 endpoints**

Support connect, sync, and data endpoints with idempotent daily upserts and
explicit quota/error states.

- [ ] **Step 5: Implement GA4 dashboard**

Show sessions, users, engagement rate, key events, revenue, page performance,
traffic sources, trends, best pages, and weak-conversion pages.

- [ ] **Step 6: Verify and commit**

Run backend and frontend GA4 tests, migrations, and build.
Commit `feat: integrate Google Analytics 4`.

### Task 7: External Crawl And Technical Findings

**Files:**
- Create: `backend/app/domains/crawls/provider.py`
- Create: `backend/app/domains/crawls/firecrawl.py`
- Create: `backend/app/domains/crawls/service.py`
- Create: `backend/alembic/versions/0005_crawls.py`
- Create: `backend/tests/crawls/`
- Create: `frontend/src/routes/dashboard/CrawlPage.tsx`

- [ ] **Step 1: Write failing provider contract tests**

```python
@pytest.mark.parametrize("provider", provider_contracts())
def test_provider_never_exceeds_project_limit(provider):
    request = provider.start("https://example.com", limit=9_000)

    assert request.limit == 5_000
```

- [ ] **Step 2: Write failing webhook idempotency test**

```python
def test_duplicate_firecrawl_webhook_is_processed_once(client, signed_payload):
    assert client.post("/webhooks/firecrawl", content=signed_payload).status_code == 202
    assert client.post("/webhooks/firecrawl", content=signed_payload).status_code == 202
    assert processed_event_count() == 1
```

- [ ] **Step 3: Verify RED**

Run crawl tests and confirm failures are due to missing implementation.

- [ ] **Step 4: Implement Firecrawl adapter**

Start, poll, cancel, paginate, verify webhook events, map errors, retry 429/5xx,
restrict domains, and enforce a 5,000 URL application cap.

- [ ] **Step 5: Persist pages, links, and technical issues**

Normalize URLs and detect broken links, redirect chains, duplicate metadata,
canonical conflicts, noindex conflicts, and orphan candidates.

- [ ] **Step 6: Implement crawl dashboard and history**

Provide crawl state, progress, issue filters, affected URLs, links, and run
comparison.

- [ ] **Step 7: Verify and commit**

Run provider contracts, worker tests, UI tests, and build.
Commit `feat: add external crawl analysis`.

### Task 8: Combined Priority And AI Recommendation Engines

**Files:**
- Create: `backend/app/domains/priorities/scoring.py`
- Create: `backend/app/domains/priorities/service.py`
- Create: `backend/app/domains/recommendations/ai_provider.py`
- Create: `backend/app/domains/recommendations/openai_provider.py`
- Create: `backend/tests/priorities/`
- Create: `backend/tests/recommendations/`
- Create: `frontend/src/routes/dashboard/OpportunitiesPage.tsx`
- Create: `frontend/src/routes/dashboard/PriorityPage.tsx`

- [ ] **Step 1: Write failing deterministic score tests**

```python
def test_high_impressions_low_ctr_and_low_seo_score_rank_first(score_pages):
    results = score_pages(
        [
            page(url="/a", seo_score=45, impressions=20_000, ctr=0.01),
            page(url="/b", seo_score=80, impressions=400, ctr=0.08),
        ]
    )

    assert results[0].url == "/a"
    assert results[0].priority_score > results[1].priority_score
```

- [ ] **Step 2: Write failing AI schema and evidence tests**

```python
def test_ai_recommendation_requires_evidence_and_never_auto_approves(generator):
    recommendation = generator.generate(page_facts())

    assert recommendation.evidence
    assert recommendation.approval_state == "proposed"
```

- [ ] **Step 3: Verify RED**

Run priority and recommendation tests.

- [ ] **Step 4: Implement normalized component scoring**

Combine audit severity, GSC opportunity, ranking opportunity, GA4 conversion,
trend, importance, and confidence into a bounded 0-100 score with explanations.

- [ ] **Step 5: Implement structured AI recommendations**

Use schema-validated outputs, bounded excerpts, evidence IDs, provider/model
metadata, deduplication, retries, usage metering, and rule-based fallback.

- [ ] **Step 6: Implement endpoint and opportunity interfaces**

Return all required fields from `/seo-priority-score`, component breakdowns,
concrete actions, confidence, filters, and recommendation detail.

- [ ] **Step 7: Verify and commit**

Run deterministic fixtures, OpenAI adapter contracts, UI tests, and build.
Commit `feat: add data-driven SEO priority engine`.

### Task 9: Approved Publishing, SEO Plugin Adapters, And Rollback

**Files:**
- Create: `plugin/wp-fixpilot-bridge/includes/class-change-controller.php`
- Create: `plugin/wp-fixpilot-bridge/includes/seo-adapters/`
- Create: `plugin/wp-fixpilot-bridge/tests/test-change-controller.php`
- Create: `backend/app/domains/wordpress/publishing.py`
- Create: `backend/alembic/versions/0006_wordpress_changes.py`
- Create: `backend/tests/wordpress/test_publishing.py`
- Create: `frontend/src/features/publishing/`

- [ ] **Step 1: Write failing content hash conflict test**

```python
def test_publish_rejects_changed_wordpress_base(publisher, proposal):
    proposal.base_content_hash = "old"
    publisher.wordpress.current_hash.return_value = "new"

    with pytest.raises(PublishConflict):
        publisher.publish(proposal)
```

- [ ] **Step 2: Write failing plugin adapter tests**

Test title, description, canonical, noindex, content, internal links, and
redirect writes for Yoast SEO, Rank Math, and All in One SEO.

- [ ] **Step 3: Verify RED**

Run pytest and PHPUnit focused publishing tests.

- [ ] **Step 4: Implement proposal, approval, and publish flow**

Require exact diffs, project role authorization, fresh content hashes, signed
bridge calls, immutable audit records, and safe error mapping.

- [ ] **Step 5: Implement rollback as audited mutation**

Rollback restores captured before values only after confirmation and records its
own actor, timestamp, before value, and after value.

- [ ] **Step 6: Implement review UI**

Build side-by-side diffs, evidence, approval controls, conflicts, publish
progress, history, and rollback confirmation.

- [ ] **Step 7: Verify and commit**

Run plugin, backend, frontend, and end-to-end publishing tests.
Commit `feat: add approved WordPress publishing and rollback`.

### Task 10: Three Dashboard Modes And Saved Preference

**Files:**
- Create: `frontend/src/routes/dashboard/views/AnalyticsConsole.tsx`
- Create: `frontend/src/routes/dashboard/views/ActionWorkspace.tsx`
- Create: `frontend/src/routes/dashboard/views/HybridCommandCenter.tsx`
- Create: `frontend/src/features/preferences/`
- Create: `frontend/tests/dashboard-modes.spec.ts`
- Modify: `backend/app/domains/dashboards/`
- Modify: `backend/app/domains/projects/models.py`

- [ ] **Step 1: Write failing saved preference test**

```tsx
it("restores the signed-in user's dashboard view", async () => {
  renderDashboard({ savedView: "action" });

  expect(await screen.findByRole("heading", {
    name: "Wat verdient vandaag aandacht?",
  })).toBeVisible();
});
```

- [ ] **Step 2: Verify RED**

Run focused Vitest and API profile tests.

- [ ] **Step 3: Implement shared dashboard data model**

Expose common summaries, trends, top pages, weak pages, top queries, sources,
and priorities without embedding presentation-specific response shapes.

- [ ] **Step 4: Implement all three responsive views**

Match the approved green visual direction. Add keyboard-accessible view switch,
chart table alternatives, mobile layouts, and persisted per-user preference.

- [ ] **Step 5: Verify and commit**

Run Vitest, Playwright at desktop/mobile sizes, accessibility checks, and build.
Commit `feat: add personalized dashboard modes`.

### Task 11: Deployment, Security, And End-To-End Verification

**Files:**
- Create: `infrastructure/render.yaml`
- Create: `infrastructure/supabase/config.toml`
- Create: `frontend/vercel.json`
- Create: `docs/deployment.md`
- Create: `docs/security.md`
- Create: `docs/operations.md`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Write deployment smoke tests**

Add scripts that validate required environment keys, migration state, API
health, worker health, frontend routing, and provider configuration.

- [ ] **Step 2: Configure deployment services**

Define Render web/worker services, Redis, release migration command, Vercel
rewrites, Supabase local configuration, CORS, trusted hosts, and health checks.

- [ ] **Step 3: Add security verification**

Run dependency audits, secret scanning, tenant isolation tests, OAuth state/PKCE
tests, replay tests, webhook verification, and authorization tests.

- [ ] **Step 4: Run complete verification**

Run:

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd ../frontend && npm run lint && npm test -- --run && npm run build
npx playwright test
cd ../plugin/wp-fixpilot-bridge && composer test
```

Expected: every command passes with no warnings treated as errors.

- [ ] **Step 5: Verify production-like local stack**

Start PostgreSQL and Redis, apply migrations, run API and worker, execute one
fixture WordPress sync, GSC sync, GA4 sync, crawl, priority calculation, proposal
approval, publish, and rollback flow.

- [ ] **Step 6: Final commit**

Commit `chore: finalize deployment and production verification`.
