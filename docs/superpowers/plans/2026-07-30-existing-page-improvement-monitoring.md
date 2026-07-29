# Existing Page Improvement And Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate reviewable improvement drafts for existing WordPress pages and retain explainable version, score, recommendation, and timeline history.

**Architecture:** An existing-page opportunity queues an outbound snapshot-capture job. The WordPress plugin captures the source through the existing snapshot store and builder adapters, then the backend binds the immutable snapshot to the normal proposal and draft workflow. WordPress inventory sync stores changed page versions and deterministic score snapshots; manual and weekly checks use the same idempotent service.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL/Supabase, React 19, TypeScript, WordPress/PHP 8.2, Render cron, existing snapshot and outbound authentication contracts.

## Global Constraints

- Existing live pages are immutable.
- Every proposed improvement creates a separate WordPress `page` with `draft` status.
- Snapshot capture and draft creation are outbound plugin operations.
- Builder structure, ACF rows, media IDs, SEO metadata, page template, and non-text metadata remain preserved.
- Page versions are added only when the canonical content hash changes.
- Scores are explainable evidence snapshots, not ranking claims.
- Checks run after WordPress sync, manually, and weekly.
- A check never generates or publishes a rewrite automatically.
- Add no queue dependency.

---

### Task 1: Persist Page Versions, Scores, Recommendations, And Timeline

**Files:**
- Create: `backend/alembic/versions/0024_page_monitoring_and_improvements.py`
- Modify: `backend/app/domains/wordpress/models.py`
- Modify: `backend/app/domains/page_packages/models.py`
- Create: `backend/tests/wordpress/test_page_monitoring_models.py`
- Create: `backend/tests/wordpress/test_page_monitoring_migration.py`

**Interfaces:**
- Produces: `PageObservedVersion(id, project_id, wordpress_page_id, content_hash, source, snapshot_payload, proposal_version_id, draft_job_id, observed_at, published_at)`
- Produces: `PageScoreSnapshot(id, page_version_id, overall_score, factors, created_at)`
- Produces: `PageRecommendation(id, page_version_id, fingerprint, state, evidence, suggested_action, created_at)`
- Produces: `PageTimelineEvent(id, project_id, wordpress_page_id, page_version_id, event_type, payload, created_at)`
- Produces: `WordPressSnapshotCaptureJob(id, project_id, wordpress_page_id, state, claim fields, snapshot result, attempt_count, timestamps)`
- Extends: `PagePackageProposal.source_wordpress_page_id` as a nullable project-scoped foreign key

- [ ] **Step 1: Write failing constraint and migration tests**

```python
def test_same_page_hash_is_unique(session, wordpress_page):
    session.add_all([
        observed_version(wordpress_page, "hash-a"),
        observed_version(wordpress_page, "hash-a"),
    ])
    with pytest.raises(IntegrityError):
        session.commit()


def test_capture_job_requires_claim_fields_only_while_claimed(session, wordpress_page):
    session.add(snapshot_job(wordpress_page, state="claimed", claim_token=None))
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: Run the focused tests**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress/test_page_monitoring_models.py tests/wordpress/test_page_monitoring_migration.py -q`

Expected: FAIL because migration `0024` and models are absent.

- [ ] **Step 3: Add models and migration**

Use JSON for immutable captured facts and score factors, unique `(wordpress_page_id, content_hash)`, unique recommendation `(page_version_id, fingerprint)`, capture job states `queued|claimed|completed|failed|cancelled`, and the same claim-field/terminal-hash invariants as `WordPressDraftJob`.

- [ ] **Step 4: Verify model rules and migration round trip**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress/test_page_monitoring_models.py tests/wordpress/test_page_monitoring_migration.py -q`

Run: `cd backend && .venv/bin/alembic upgrade head && .venv/bin/alembic downgrade 0023_keyword_opportunity_sync_lifecycle && .venv/bin/alembic upgrade head`

Expected: PASS and Alembic returns to `0024`.

- [ ] **Step 5: Obtain independent review and commit**

```bash
git add backend/alembic/versions/0024_page_monitoring_and_improvements.py \
  backend/app/domains/wordpress/models.py \
  backend/app/domains/page_packages/models.py \
  backend/tests/wordpress/test_page_monitoring_models.py \
  backend/tests/wordpress/test_page_monitoring_migration.py
git commit -m "feat: persist page monitoring history"
```

---

### Task 2: Capture Existing Pages Through The Outbound Bridge

**Files:**
- Create: `backend/app/domains/wordpress/snapshot_jobs.py`
- Create: `backend/app/api/routes/wordpress_snapshot_jobs.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/domains/wordpress/client.py`
- Create: `backend/tests/wordpress/test_snapshot_job_service.py`
- Create: `backend/tests/wordpress/test_snapshot_job_routes.py`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-outbound-client.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-template-snapshot-store.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- Modify: `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`
- Create: `plugin/wp-fixpilot-bridge/tests/optimization-snapshot-job-test.php`

**Interfaces:**
- Produces: `create_or_get_snapshot_job(session, page) -> WordPressSnapshotCaptureJob`
- Produces: `claim_next_snapshot_job(session, project_id, site_url) -> ClaimedSnapshotJob | None`
- Produces: `complete_snapshot_job(session, job_id, claim_token, result) -> WordPressSnapshotCaptureJob`
- Adds outbound routes: `POST /projects/{project_id}/wordpress-snapshot-jobs/claim`, `/{job_id}/complete`, and `/{job_id}/fail`
- Plugin result: `{snapshot_id, snapshot_version, structure_hash, schema_version, schema, source_post_id, source_url, source_content_hash, captured_at}`

- [ ] **Step 1: Write failing backend claim/idempotency tests**

```python
def test_repeated_capture_request_returns_same_open_job(session, wordpress_page):
    first = create_or_get_snapshot_job(session, wordpress_page)
    second = create_or_get_snapshot_job(session, wordpress_page)
    assert first.id == second.id


def test_completion_rejects_a_different_source_page(session, claimed_job):
    with pytest.raises(SnapshotJobError, match="source page"):
        complete_snapshot_job(
            session,
            claimed_job.id,
            claimed_job.claim_token,
            snapshot_result(source_post_id=999),
        )
```

- [ ] **Step 2: Write failing PHP snapshot-kind test**

```php
$result = $controller->capture_optimization_snapshot(42);
assert($result['source_post_id'] === 42);
assert($result['snapshot_kind'] === 'optimization_source');
assert($store->load((int) $result['snapshot_id'])['source_post_id'] === 42);
```

- [ ] **Step 3: Run focused backend and plugin tests**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress/test_snapshot_job_service.py tests/wordpress/test_snapshot_job_routes.py -q`

Run: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/optimization-snapshot-job-test.php`

Expected: FAIL because the job contract and optimization snapshot kind are absent.

- [ ] **Step 4: Implement by reusing the existing contracts**

Copy the proven claim lease, terminal claim-token hash, safe error, and site binding rules from `draft_jobs.py`; do not generalize both job types. Extend the snapshot metadata with `snapshot_kind` and source identity. The plugin polls snapshot jobs before draft jobs in its existing outbound cycle and captures with registered builder adapters.

- [ ] **Step 5: Run focused and concurrency tests**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress/test_snapshot_job_service.py tests/wordpress/test_snapshot_job_routes.py tests/wordpress/test_snapshot_job_postgres_concurrency.py -q`

Run: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli sh -lc 'php -d zend.assertions=1 -d assert.exception=1 tests/optimization-snapshot-job-test.php && php -d zend.assertions=1 -d assert.exception=1 tests/template-snapshot-test.php && php -d zend.assertions=1 -d assert.exception=1 tests/snapshot-draft-job-test.php'`

Expected: PASS; the PostgreSQL concurrency test may skip only when its URL is absent.

- [ ] **Step 6: Obtain independent review and commit**

Review outbound authentication, lease races, immutable source identity, all registered builders, and absence of live-page writes.

```bash
git add backend/app/domains/wordpress/snapshot_jobs.py \
  backend/app/api/routes/wordpress_snapshot_jobs.py \
  backend/app/main.py backend/app/domains/wordpress/client.py \
  backend/tests/wordpress/test_snapshot_job_service.py \
  backend/tests/wordpress/test_snapshot_job_routes.py \
  backend/tests/wordpress/test_snapshot_job_postgres_concurrency.py \
  plugin/wp-fixpilot-bridge/includes/class-outbound-client.php \
  plugin/wp-fixpilot-bridge/includes/class-template-snapshot-store.php \
  plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php \
  plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php \
  plugin/wp-fixpilot-bridge/tests/optimization-snapshot-job-test.php
git commit -m "feat: capture existing pages through outbound jobs"
```

---

### Task 3: Record Changed Page Versions And Explainable Scores

**Files:**
- Create: `backend/app/domains/wordpress/monitoring.py`
- Modify: `backend/app/domains/wordpress/service.py`
- Modify: `backend/app/api/routes/wordpress.py`
- Create: `backend/tests/wordpress/test_page_monitoring_service.py`
- Modify: `backend/tests/wordpress/test_routes.py`

**Interfaces:**
- Produces: `record_page_version(session, page, facts, *, source, proposal_version_id=None, draft_job_id=None) -> tuple[PageObservedVersion, bool]`
- Produces: `score_page_version(version) -> PageScoreSnapshot`
- Produces: `check_page(session, page, facts, *, trigger) -> PageCheckResult`
- Score factor shape: `{key, value, points, max_points, explanation, suggested_action, evidence}`

- [ ] **Step 1: Write failing deterministic monitoring tests**

```python
def test_unchanged_hash_reuses_version_without_duplicate_recommendations(session, page):
    first = check_page(session, page, page_facts("hash-a"), trigger="sync")
    second = check_page(session, page, page_facts("hash-a"), trigger="manual")
    assert first.version.id == second.version.id
    assert recommendation_count(session, first.version.id) == 1


def test_changed_hash_creates_version_score_and_timeline(session, page):
    first = check_page(session, page, page_facts("hash-a"), trigger="sync")
    second = check_page(session, page, page_facts("hash-b"), trigger="sync")
    assert first.version.id != second.version.id
    assert second.score.factors[0]["explanation"]
    assert timeline_types(session, page.id)[-1] == "score_created"
```

- [ ] **Step 2: Run the focused tests**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress/test_page_monitoring_service.py tests/wordpress/test_routes.py -q`

Expected: FAIL because versions and scores are not recorded.

- [ ] **Step 3: Implement one deterministic scoring module**

Calculate only evidence currently present: title, meta description, headings, indexability, canonical, keyword coverage, readability, link counts, featured/in-page image and alt text, and optional company-profile consistency. Fingerprint recommendations from canonical JSON containing factor key, evidence, and suggested action.

```python
@dataclass(frozen=True)
class PageCheckResult:
    version: PageObservedVersion
    version_created: bool
    score: PageScoreSnapshot
    recommendations_created: int
```

Call `check_page` after each successful inventory/current-state sync. Do not invoke an AI provider.

- [ ] **Step 4: Run monitoring and WordPress tests**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress/test_page_monitoring_service.py tests/wordpress/test_routes.py -q && .venv/bin/ruff check app tests alembic`

Expected: PASS.

- [ ] **Step 5: Obtain independent review and commit**

```bash
git add backend/app/domains/wordpress/monitoring.py \
  backend/app/domains/wordpress/service.py \
  backend/app/api/routes/wordpress.py \
  backend/tests/wordpress/test_page_monitoring_service.py \
  backend/tests/wordpress/test_routes.py
git commit -m "feat: version and score synchronized pages"
```

---

### Task 4: Generate Improvement Proposals From Captured Snapshots

**Files:**
- Modify: `backend/app/api/routes/page_packages.py`
- Modify: `backend/app/domains/page_packages/models.py`
- Modify: `backend/app/domains/page_packages/service.py`
- Modify: `backend/app/domains/page_packages/generation.py`
- Modify: `backend/tests/page_packages/test_routes.py`
- Create: `backend/tests/page_packages/test_existing_page_generation.py`
- Modify: `backend/tests/wordpress/test_draft_job_service.py`

**Interfaces:**
- Existing-page proposal creation returns `202` with `snapshot_job_id` until capture completes
- A retry after capture creates or returns one proposal bound to the immutable snapshot
- `PagePackageProposal.source_wordpress_page_id` identifies the existing source
- Existing `create_or_get_draft_job(session, proposal)` remains the only approved draft creation path

- [ ] **Step 1: Write failing route and immutability tests**

```python
def test_existing_page_opportunity_queues_snapshot_capture(client, existing_opportunity):
    response = client.post(
        f"/projects/{existing_opportunity.project_id}/page-proposals",
        json={"opportunity_id": existing_opportunity.id},
    )
    assert response.status_code == 202
    assert response.json()["stage"] == "waiting_for_wordpress_snapshot"


def test_source_change_after_capture_does_not_change_generation_context(
    session, captured_existing_page
):
    context = build_context(session, captured_existing_page.proposal)
    captured_existing_page.source.title = "Changed live title"
    assert build_context(session, captured_existing_page.proposal) == context
```

- [ ] **Step 2: Run focused proposal tests**

Run: `cd backend && .venv/bin/python -m pytest tests/page_packages/test_existing_page_generation.py tests/page_packages/test_routes.py tests/wordpress/test_draft_job_service.py -q`

Expected: FAIL on the current `new_page` restriction.

- [ ] **Step 3: Branch proposal setup by target classification**

For `new_page`, keep current default-template behavior. For `existing_page`, resolve `target_url` to one synchronized `WordPressPage`, create/reuse its capture job, and after completion bind the returned snapshot identity/schema. For `review`, return `409` until the user assigns a target. Include current values, prior score, target URL, and improvement evidence in the generation context.

- [ ] **Step 4: Prove draft creation clones the snapshot**

Run: `cd backend && .venv/bin/python -m pytest tests/page_packages/test_existing_page_generation.py tests/page_packages/test_routes.py tests/wordpress/test_draft_job_service.py -q`

Run: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/snapshot-draft-job-test.php`

Expected: PASS and the plugin test asserts source post values remain unchanged while the new post is `draft`.

- [ ] **Step 5: Obtain independent review and commit**

```bash
git add backend/app/api/routes/page_packages.py \
  backend/app/domains/page_packages/models.py \
  backend/app/domains/page_packages/service.py \
  backend/app/domains/page_packages/generation.py \
  backend/tests/page_packages/test_routes.py \
  backend/tests/page_packages/test_existing_page_generation.py \
  backend/tests/wordpress/test_draft_job_service.py
git commit -m "feat: propose draft improvements for existing pages"
```

---

### Task 5: Add Existing-Page Review And Page Timeline UI

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/routes/dashboard/OpportunitiesPage.tsx`
- Modify: `frontend/src/routes/dashboard/OpportunitiesPage.test.tsx`
- Modify: `frontend/src/features/page-packages/PagePackageReview.tsx`
- Modify: `frontend/src/features/page-packages/PagePackageReview.test.tsx`
- Create: `frontend/src/features/page-monitoring/PageTimeline.tsx`
- Create: `frontend/src/features/page-monitoring/PageTimeline.test.tsx`
- Create: `frontend/src/features/page-monitoring/ScoreFactors.tsx`
- Create: `frontend/src/features/page-monitoring/ScoreFactors.test.tsx`
- Modify: `backend/app/api/routes/wordpress.py`
- Modify: `backend/tests/wordpress/test_routes.py`

**Interfaces:**
- Adds `GET /projects/{project_id}/wordpress-pages/{page_id}/monitoring`
- Adds `POST /projects/{project_id}/wordpress-pages/{page_id}/checks`
- Existing-page opportunity action label: `Verbeteringsvoorstel maken`
- Review displays current/proposed values and current/projected score factors

- [ ] **Step 1: Write failing API and component tests**

```tsx
it("shows current and proposed content without hiding the full-width preview", async () => {
  render(<PagePackageReview proposal={existingPageProposal} />);
  expect(screen.getByRole("heading", { name: "Huidig en voorgesteld" })).toBeVisible();
  expect(screen.getByText("Huidige score 61")).toBeVisible();
  expect(screen.getByText("Verwachte score 78")).toBeVisible();
});
```

```python
def test_manual_check_returns_existing_version_when_content_is_unchanged(client, page):
    first = client.post(f"/projects/{page.project_id}/wordpress-pages/{page.id}/checks")
    second = client.post(f"/projects/{page.project_id}/wordpress-pages/{page.id}/checks")
    assert first.json()["version_id"] == second.json()["version_id"]
```

- [ ] **Step 2: Run focused tests**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress/test_routes.py -q`

Run: `cd frontend && npm test -- OpportunitiesPage.test.tsx PagePackageReview.test.tsx PageTimeline.test.tsx ScoreFactors.test.tsx`

Expected: FAIL because the endpoints and components are missing.

- [ ] **Step 3: Add the endpoints and UI**

Return ordered versions, scores, recommendations, events, latest sync, next weekly check, and page status. Keep the preview full width above fields. Use the current proposal version controls for regenerate/compare/approve and disable draft creation until approval.

- [ ] **Step 4: Run frontend and route verification**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress/test_routes.py tests/page_packages -q`

Run: `cd frontend && npm test -- --run && npm run lint && npm run build`

Expected: PASS.

- [ ] **Step 5: Obtain independent review and commit**

```bash
git add frontend/src/lib/api.ts \
  frontend/src/routes/dashboard/OpportunitiesPage.tsx \
  frontend/src/routes/dashboard/OpportunitiesPage.test.tsx \
  frontend/src/features/page-packages/PagePackageReview.tsx \
  frontend/src/features/page-packages/PagePackageReview.test.tsx \
  frontend/src/features/page-monitoring \
  backend/app/api/routes/wordpress.py \
  backend/tests/wordpress/test_routes.py
git commit -m "feat: review existing page improvements and history"
```

---

### Task 6: Run Weekly Durable Checks

**Files:**
- Create: `backend/app/maintenance.py`
- Create: `backend/tests/wordpress/test_weekly_page_checks.py`
- Modify: `render.yaml`
- Modify: `docs/operations.md`

**Interfaces:**
- Produces CLI: `python -m app.maintenance weekly-page-checks`
- Calls `check_page` for pages whose last check is at least seven days old
- Render cron runs once daily; database due dates enforce weekly frequency

- [ ] **Step 1: Write the failing due-page test**

```python
def test_weekly_runner_checks_only_due_pages(session, due_page, recent_page):
    result = run_weekly_page_checks(session, now=utc_datetime(2026, 7, 30))
    assert result.checked_page_ids == (due_page.id,)
```

- [ ] **Step 2: Run the focused test**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress/test_weekly_page_checks.py -q`

Expected: FAIL because the maintenance command is absent.

- [ ] **Step 3: Add the CLI and Render cron**

Use `argparse` with one command, open the existing SQLAlchemy session, select due pages, run the same monitoring service, commit each page independently, and return a non-zero exit code if any page failed. Add one Render cron service with:

```yaml
- type: cron
  name: wp-fixpilot-weekly-page-checks
  runtime: python
  rootDir: backend
  schedule: "15 3 * * *"
  buildCommand: pip install -e .
  startCommand: python -m app.maintenance weekly-page-checks
```

Reuse the production database environment variable.

- [ ] **Step 4: Run the command and tests**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress/test_weekly_page_checks.py -q && .venv/bin/python -m app.maintenance weekly-page-checks --dry-run`

Expected: PASS; dry run reports due counts without writes.

- [ ] **Step 5: Obtain independent review and commit**

```bash
git add backend/app/maintenance.py \
  backend/tests/wordpress/test_weekly_page_checks.py \
  render.yaml docs/operations.md
git commit -m "feat: schedule weekly page monitoring"
```

---

### Task 7: Release And Live Acceptance

**Files:**
- Modify: `.superpowers/sdd/progress.md`

**Interfaces:**
- Produces deployment and staging acceptance evidence

- [ ] **Step 1: Run complete backend, frontend, and plugin verification**

Run: `cd backend && .venv/bin/ruff check app tests alembic && .venv/bin/python -m pytest --import-mode=importlib -q && .venv/bin/alembic upgrade head`

Run: `cd frontend && npm test -- --run && npm run lint && npm run build`

Run: `cd plugin/wp-fixpilot-bridge && docker run --rm -v "$PWD:/app" -w /app php:8.2-cli sh -lc 'for test in tests/*-test.php; do php -d zend.assertions=1 -d assert.exception=1 "$test" || exit 1; done; find . -name "*.php" -print0 | xargs -0 -n1 php -l'`

Expected: all commands pass.

- [ ] **Step 2: Deploy backend, frontend, cron, and one plugin package**

Install the plugin package once after local suites pass. Record exact commit and plugin version.

- [ ] **Step 3: Execute staging acceptance**

Create improvement proposals for two different existing pages, approve both, and verify two separate draft edit URLs while each source hash remains unchanged. Edit or publish one managed page manually, synchronize, and verify one new version and score. Run the manual check twice and verify no duplicate version or recommendation. Trigger the cron command and verify due-page handling.

- [ ] **Step 4: Obtain final independent review and commit**

```bash
git add .superpowers/sdd/progress.md
git commit -m "chore: verify existing page monitoring release"
git push origin feature/platform-build
```
