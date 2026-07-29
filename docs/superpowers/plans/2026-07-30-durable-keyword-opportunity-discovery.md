# Durable Keyword Opportunity Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every DataForSEO sync fetch the next result window, retain earlier opportunities, and visibly identify newly discovered rows.

**Architecture:** Persist one cursor per project and one immutable record per sync attempt. The existing provider receives an offset, while the existing upsert service becomes additive and returns explicit created, updated, and rejected counts. The current opportunities route and screen expose the latest successful run without adding a new worker or queue.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL/Supabase, requests, React 19, TypeScript, TanStack Query, Vitest.

## Global Constraints

- DataForSEO Keyword Ideas uses `limit=50` and a persisted offset.
- A cursor advances only after the provider response and database transaction succeed.
- A changed normalized seed fingerprint resets the offset to zero.
- An exhausted range resets to zero on the following manual sync.
- Existing opportunities are never deleted because they are absent from one response.
- Publishing behavior is unchanged.
- Add no dependency.

---

### Task 1: Persist Sync State And Runs

**Files:**
- Create: `backend/alembic/versions/0023_keyword_opportunity_sync_lifecycle.py`
- Modify: `backend/app/domains/dataforseo/models.py`
- Create: `backend/tests/dataforseo/test_sync_models.py`
- Create: `backend/tests/dataforseo/test_sync_migration.py`

**Interfaces:**
- Produces: `KeywordOpportunitySyncState(project_id, seed_fingerprint, next_offset, exhausted, last_successful_run_id, last_synced_at, last_error)`
- Produces: `KeywordOpportunitySyncRun(id, project_id, seed_fingerprint, offset, limit, state, provider_count, accepted_count, created_count, updated_count, rejected_count, started_at, completed_at, error_message)`
- Extends: `KeywordOpportunity.first_seen_run_id`, `last_seen_run_id`, `last_seen_at`, and `dismissed_at`

- [ ] **Step 1: Write failing model and migration tests**

```python
def test_keyword_identity_survives_multiple_sync_runs(session, project):
    first = KeywordOpportunitySyncRun.started(project.id, "seed-a", 0, 50)
    second = KeywordOpportunitySyncRun.started(project.id, "seed-a", 50, 50)
    opportunity = keyword_opportunity(
        project,
        first_seen_run_id=first.id,
        last_seen_run_id=second.id,
    )
    session.add_all([first, second, opportunity])
    session.commit()
    assert opportunity.first_seen_run_id == first.id
    assert opportunity.last_seen_run_id == second.id


def test_sync_state_rejects_negative_offset(session, project):
    session.add(
        KeywordOpportunitySyncState(
            project_id=project.id,
            seed_fingerprint="seed-a",
            next_offset=-1,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: Run the tests and confirm the schema is missing**

Run: `cd backend && .venv/bin/python -m pytest tests/dataforseo/test_sync_models.py tests/dataforseo/test_sync_migration.py -q`

Expected: FAIL because the sync lifecycle models and migration do not exist.

- [ ] **Step 3: Add the minimum models and migration**

Use check constraints for run state `running|completed|failed`, non-negative counts and offsets, a unique sync-state row per project, and foreign keys from opportunity run IDs to sync runs. Keep `discovered_at` as the first-seen timestamp and backfill `last_seen_at=discovered_at`.

```python
class KeywordOpportunitySyncState(Base):
    __tablename__ = "keyword_opportunity_sync_states"
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    seed_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    next_offset: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exhausted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_successful_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("keyword_opportunity_sync_runs.id", ondelete="SET NULL")
    )
```

- [ ] **Step 4: Verify migration round trips and model constraints**

Run: `cd backend && .venv/bin/python -m pytest tests/dataforseo/test_sync_models.py tests/dataforseo/test_sync_migration.py -q`

Expected: PASS.

Run: `cd backend && .venv/bin/alembic upgrade head && .venv/bin/alembic downgrade 0022_snapshot_draft_job_contract && .venv/bin/alembic upgrade head`

Expected: all three commands complete and Alembic returns to `0023`.

- [ ] **Step 5: Obtain independent review and commit**

Review for nullable-safe foreign keys, PostgreSQL/SQLite compatibility, and downgrade data safety.

```bash
git add backend/alembic/versions/0023_keyword_opportunity_sync_lifecycle.py \
  backend/app/domains/dataforseo/models.py \
  backend/tests/dataforseo/test_sync_models.py \
  backend/tests/dataforseo/test_sync_migration.py
git commit -m "feat: persist keyword opportunity sync runs"
```

---

### Task 2: Request The Next Provider Window

**Files:**
- Modify: `backend/app/domains/dataforseo/provider.py`
- Modify: `backend/tests/dataforseo/test_provider.py`

**Interfaces:**
- Consumes: DataForSEO Keyword Ideas API
- Produces: `DataForSeoProvider.keyword_ideas(seeds, *, location_code=2528, language_code="nl", limit=50, offset=0) -> list[dict]`

- [ ] **Step 1: Write the failing request-body test**

```python
def test_keyword_ideas_sends_offset(requests_mock):
    requests_mock.post(
        "https://api.dataforseo.com/v3/dataforseo_labs/google/keyword_ideas/live",
        json=successful_keyword_response([]),
    )
    DataForSeoProvider("login", "password").keyword_ideas(
        ["versnellingsbak"], limit=50, offset=100
    )
    assert requests_mock.last_request.json()[0]["offset"] == 100
```

- [ ] **Step 2: Run the focused test**

Run: `cd backend && .venv/bin/python -m pytest tests/dataforseo/test_provider.py -q`

Expected: FAIL because `offset` is not accepted or sent.

- [ ] **Step 3: Add the offset argument and payload key**

```python
def keyword_ideas(
    self,
    seeds: list[str],
    *,
    location_code: int = 2528,
    language_code: str = "nl",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    if offset < 0:
        raise ValueError("Offset must be non-negative")
```

Send `"offset": offset` in the existing JSON task. Do not change parsing.

- [ ] **Step 4: Run provider tests**

Run: `cd backend && .venv/bin/python -m pytest tests/dataforseo/test_provider.py -q`

Expected: PASS, including the existing response and failure-message tests.

- [ ] **Step 5: Obtain independent review and commit**

```bash
git add backend/app/domains/dataforseo/provider.py \
  backend/tests/dataforseo/test_provider.py
git commit -m "feat: paginate DataForSEO keyword ideas"
```

---

### Task 3: Make Synchronization Additive And Atomic

**Files:**
- Modify: `backend/app/domains/dataforseo/service.py`
- Modify: `backend/app/api/routes/dataforseo.py`
- Create: `backend/tests/dataforseo/test_sync_service.py`
- Create: `backend/tests/dataforseo/test_sync_postgres_concurrency.py`
- Modify: `backend/tests/dataforseo/test_routes.py`

**Interfaces:**
- Produces: `seed_fingerprint(seeds: list[str]) -> str`
- Produces: `OpportunitySyncResult(run_id, offset, next_offset, exhausted, provider_count, accepted_count, created_count, updated_count, rejected_count)`
- Produces: `sync_keyword_opportunity_window(session, project, provider, *, limit=50) -> OpportunitySyncResult`
- Replaces route response with `{run_id, offset, next_offset, exhausted, provider_count, accepted_count, new_count, updated_count, rejected_count}`

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_successive_syncs_keep_old_rows_and_advance_offset(session, project):
    provider = StubProvider([[row("eerste")], [row("tweede")]])
    first = sync_keyword_opportunity_window(session, project, provider)
    second = sync_keyword_opportunity_window(session, project, provider)
    assert (first.offset, second.offset) == (0, 50)
    assert keywords(session, project.id) == {"eerste", "tweede"}


def test_provider_failure_keeps_cursor_and_rows(session, project):
    sync_keyword_opportunity_window(session, project, StubProvider([[row("eerste")]]))
    with pytest.raises(RuntimeError):
        sync_keyword_opportunity_window(session, project, FailingProvider())
    state = session.get(KeywordOpportunitySyncState, project.id)
    assert state.next_offset == 50
    assert keywords(session, project.id) == {"eerste"}


def test_changed_seeds_restart_at_zero(session, project):
    sync_keyword_opportunity_window(session, project, StubProvider([[row("eerste")]]))
    project.company_profile.services = ["nieuwe dienst"]
    sync_keyword_opportunity_window(session, project, StubProvider([[row("tweede")]]))
    assert latest_provider_offset() == 0
```

- [ ] **Step 2: Run service and route tests**

Run: `cd backend && .venv/bin/python -m pytest tests/dataforseo/test_sync_service.py tests/dataforseo/test_routes.py -q`

Expected: FAIL because additive sync runs and counters do not exist.

- [ ] **Step 3: Implement the transaction**

Normalize seeds with `casefold`, whitespace collapsing, sorting, and JSON encoding before hashing with SHA-256. Lock the project sync-state row with `SELECT ... FOR UPDATE` on PostgreSQL. Create a running run, call the provider at the selected offset, upsert accepted rows without deleting absent rows, then mark the run completed and advance the cursor in the same commit.

```python
@dataclass(frozen=True)
class OpportunitySyncResult:
    run_id: str
    offset: int
    next_offset: int
    exhausted: bool
    provider_count: int
    accepted_count: int
    created_count: int
    updated_count: int
    rejected_count: int
```

Treat `provider_count < limit` as exhausted. When the prior state is exhausted, request offset zero and start a new cycle. On provider failure, roll back changed opportunity data, persist only the failed run and safe error, and leave `next_offset` unchanged.

- [ ] **Step 4: Run lifecycle, route, and concurrency tests**

Run: `cd backend && .venv/bin/python -m pytest tests/dataforseo -q`

Expected: PASS.

Run: `cd backend && WP_FIXPILOT_POSTGRES_TEST_URL="$WP_FIXPILOT_POSTGRES_TEST_URL" .venv/bin/python -m pytest tests/dataforseo/test_sync_postgres_concurrency.py -q`

Expected: PASS when the PostgreSQL test URL is configured; otherwise the test is explicitly skipped.

- [ ] **Step 5: Obtain independent review and commit**

Review the lock/commit boundary, failed-run persistence, seed reset, exhaustion cycle, duplicate identities, and secret-safe errors.

```bash
git add backend/app/domains/dataforseo/service.py \
  backend/app/api/routes/dataforseo.py \
  backend/tests/dataforseo/test_sync_service.py \
  backend/tests/dataforseo/test_routes.py \
  backend/tests/dataforseo/test_sync_postgres_concurrency.py
git commit -m "feat: retain paginated keyword opportunities"
```

---

### Task 4: Show New Opportunities And Sync Counts

**Files:**
- Modify: `backend/app/domains/dataforseo/service.py`
- Modify: `backend/app/api/routes/dataforseo.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/routes/dashboard/OpportunitiesPage.tsx`
- Modify: `frontend/src/routes/dashboard/OpportunitiesPage.test.tsx`
- Modify: `backend/tests/dataforseo/test_routes.py`

**Interfaces:**
- Extends opportunity payload with `is_new: bool`, `first_seen_at`, and `last_seen_at`
- Orders API results by latest successful run first, then impact score and search volume
- Consumes the Task 3 sync response

- [ ] **Step 1: Write failing API and UI tests**

```python
def test_latest_run_rows_are_first_and_marked_new(client, seeded_runs):
    payload = client.get(f"/projects/{seeded_runs.project_id}/keyword-opportunities").json()
    assert payload["items"][0]["is_new"] is True
    assert payload["items"][-1]["is_new"] is False
```

```tsx
it("keeps old rows and reports the new sync counts", async () => {
  server.use(syncResult({ new_count: 14, updated_count: 31, rejected_count: 5 }));
  render(<OpportunitiesPage />);
  await user.click(screen.getByRole("button", { name: "Nieuwe kansen ophalen" }));
  expect(await screen.findByText("14 nieuw, 31 bijgewerkt, 5 niet relevant")).toBeVisible();
  expect(screen.getAllByText("Nieuw").length).toBeGreaterThan(0);
});
```

- [ ] **Step 2: Run focused backend and frontend tests**

Run: `cd backend && .venv/bin/python -m pytest tests/dataforseo/test_routes.py -q`

Run: `cd frontend && npm test -- OpportunitiesPage.test.tsx`

Expected: FAIL because `is_new`, ordering, and count copy are absent.

- [ ] **Step 3: Add the response fields and restrained UI**

Calculate `is_new` by comparing `first_seen_run_id` with the project's latest successful run. Add a small `Nieuw` badge to the existing opportunity metadata row and replace the old `synced` message with the explicit counts. Keep dismissed and older opportunities in the list.

- [ ] **Step 4: Run frontend and backend verification**

Run: `cd backend && .venv/bin/python -m pytest tests/dataforseo -q && .venv/bin/ruff check app tests alembic`

Run: `cd frontend && npm test -- OpportunitiesPage.test.tsx && npm run lint && npm run build`

Expected: all commands pass.

- [ ] **Step 5: Obtain independent review and commit**

```bash
git add backend/app/domains/dataforseo/service.py \
  backend/app/api/routes/dataforseo.py \
  backend/tests/dataforseo/test_routes.py \
  frontend/src/lib/api.ts \
  frontend/src/routes/dashboard/OpportunitiesPage.tsx \
  frontend/src/routes/dashboard/OpportunitiesPage.test.tsx
git commit -m "feat: surface newly discovered opportunities"
```

---

### Task 5: Release And Live Acceptance

**Files:**
- Modify: `.superpowers/sdd/progress.md`
- Modify: `docs/operations.md`

**Interfaces:**
- Produces a documented manual sync recovery and live acceptance record

- [ ] **Step 1: Run the complete required verification**

Run: `cd backend && .venv/bin/ruff check app tests alembic && .venv/bin/python -m pytest --import-mode=importlib -q && .venv/bin/alembic upgrade head`

Run: `cd frontend && npm test -- --run && npm run lint && npm run build`

Expected: all commands pass, with only documented optional PostgreSQL skips.

- [ ] **Step 2: Document operations and recovery**

Document that a failed sync is retried by pressing `Nieuwe kansen ophalen`, previous rows stay visible, and the cursor shown by the latest completed run is authoritative.

- [ ] **Step 3: Deploy the exact pushed commit**

Push the branch, wait for Render migration/API and Vercel frontend deployment, and record the deployment IDs in the progress ledger.

- [ ] **Step 4: Execute live acceptance**

On one staging project, run three consecutive syncs. Confirm offsets `0`, `50`, and `100`; confirm earlier rows remain; confirm no duplicate keyword identity; confirm the newest rows show `Nieuw`; force one provider failure and confirm the cursor and rows remain unchanged.

- [ ] **Step 5: Obtain final independent review and commit**

```bash
git add .superpowers/sdd/progress.md docs/operations.md
git commit -m "chore: verify durable opportunity discovery"
git push origin feature/platform-build
```
