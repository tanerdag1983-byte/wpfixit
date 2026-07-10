# Outbound WordPress Draft Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent WordPress-side outbound connection that retrieves approved draft jobs and creates exactly one managed WordPress draft without inbound SaaS-to-WordPress requests.

**Architecture:** The backend stores a hashed project key and an immutable, versioned draft-job queue. The plugin authenticates outbound with that key, claims one project-scoped job, and passes its strict `wordpress-draft-job-v1` payload to the existing blueprint controller. The frontend creates and monitors jobs while retaining the manual handoff as a temporary secondary fallback.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, PostgreSQL/SQLite tests, React 19, TypeScript, Vite/Vitest, WordPress 6.5+, PHP 8.1/8.2.

## Global Constraints

- Existing managed blueprints and source pages remain immutable and are never recreated by this feature.
- Every generated WordPress object is a normal `page` with persisted `draft` status.
- The plugin performs all SaaS communication outbound over HTTPS.
- Project keys contain at least 256 bits of randomness, are returned once, and are stored hashed in the backend.
- One immutable proposal version and snapshot can create exactly one draft job and one WordPress draft.
- Only schema-listed replacements and approved internal URLs may be written.
- Unknown job-contract versions are rejected without legacy fallback.
- Any failed ACF, builder, SEO, metadata, media, or status write deletes the incomplete clone.
- Automatic publication and WordPress application passwords are outside this release.
- Preserve the existing manual handoff as a secondary rollout fallback.
- Do not add `backend/uv.lock` to any commit unless dependency resolution intentionally changes.

---

### Task 1: Persist Project Keys And Draft Jobs

**Files:**
- Create: `backend/alembic/versions/0019_outbound_wordpress_draft_jobs.py`
- Create: `backend/app/domains/wordpress/draft_jobs.py`
- Modify: `backend/app/domains/wordpress/models.py`
- Test: `backend/tests/wordpress/test_draft_job_models.py`

**Interfaces:**
- Produces: `WordPressOutboundCredential`, `WordPressDraftJob`, `hash_project_key(raw_key: str) -> str`, `new_project_key() -> tuple[str, str]`.
- Draft job states: `queued`, `claimed`, `completed`, `failed`, `cancelled`.
- Contract version: `wordpress-draft-job-v1`.

- [ ] **Step 1: Write failing persistence and key tests**

```python
def test_project_key_is_256_bit_and_only_hash_is_persisted(session, projects):
    raw, digest = new_project_key()
    assert len(secrets.token_urlsafe(32)) <= len(raw)
    assert raw != digest
    credential = WordPressOutboundCredential(
        id="credential-1",
        project_id=projects.member_project.id,
        key_hash=digest,
        site_url="https://member.example",
    )
    session.add(credential)
    session.commit()
    assert session.get(WordPressOutboundCredential, "credential-1").key_hash == hash_project_key(raw)


def test_one_draft_job_per_proposal_version(session, approved_proposal):
    session.add(WordPressDraftJob(id="job-1", project_id=approved_proposal.project_id,
        proposal_version_id=approved_proposal.id, contract_version="wordpress-draft-job-v1",
        state="queued", payload_hash="hash", payload={}))
    session.commit()
    session.add(WordPressDraftJob(id="job-2", project_id=approved_proposal.project_id,
        proposal_version_id=approved_proposal.id, contract_version="wordpress-draft-job-v1",
        state="queued", payload_hash="hash", payload={}))
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: Run the tests and confirm the missing models fail**

Run: `cd backend && .venv/bin/python -m pytest --import-mode=importlib -q tests/wordpress/test_draft_job_models.py`

Expected: collection fails because the outbound credential and draft-job models do not exist.

- [ ] **Step 3: Add the models, deterministic hash helper, and migration**

```python
def new_project_key() -> tuple[str, str]:
    raw = "wpfx_" + secrets.token_urlsafe(32)
    return raw, hash_project_key(raw)


def hash_project_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
```

`WordPressOutboundCredential` stores `id`, unique `project_id`, `key_hash`, normalized `site_url`, `revoked_at`, `last_seen_at`, and timestamps. `WordPressDraftJob` stores `id`, `project_id`, unique `proposal_version_id`, `contract_version`, `state`, immutable `payload` and `payload_hash`, claim token and expiry, WordPress result fields, bounded error code/message, attempt count, and timestamps. Add state and claim-consistency check constraints and project/state indexes in migration `0019`.

- [ ] **Step 4: Run model, migration, and metadata registration tests**

Run: `cd backend && .venv/bin/python -m pytest --import-mode=importlib -q tests/wordpress/test_draft_job_models.py tests/page_packages/test_model_registration.py`

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/alembic/versions/0019_outbound_wordpress_draft_jobs.py backend/app/domains/wordpress/models.py backend/app/domains/wordpress/draft_jobs.py backend/tests/wordpress/test_draft_job_models.py
git commit -m "feat: persist outbound WordPress draft jobs"
```

### Task 2: Implement Atomic Draft-Job State Transitions

**Files:**
- Modify: `backend/app/domains/wordpress/draft_jobs.py`
- Test: `backend/tests/wordpress/test_draft_job_service.py`
- Test: `backend/tests/wordpress/test_draft_job_postgres_concurrency.py`

**Interfaces:**
- Consumes: models and key hash from Task 1.
- Produces: `create_or_get_draft_job`, `claim_next_draft_job`, `complete_draft_job`, `fail_draft_job`, `cancel_ineligible_draft_jobs`.
- `claim_next_draft_job` returns `ClaimedDraftJob(job, claim_token)` or `None`.

- [ ] **Step 1: Write failing lifecycle and idempotency tests**

```python
def test_create_or_get_job_is_idempotent(session, approved_blueprint_proposal):
    first = create_or_get_draft_job(session, approved_blueprint_proposal)
    second = create_or_get_draft_job(session, approved_blueprint_proposal)
    assert first.id == second.id
    assert first.payload_hash == second.payload_hash


def test_claim_complete_and_replay_return_one_result(session, queued_job):
    claimed = claim_next_draft_job(session, queued_job.project_id, "https://member.example")
    assert claimed is not None
    completed = complete_draft_job(session, claimed.job.id, claimed.claim_token,
        wordpress_object_id=987, wordpress_edit_url="https://member.example/wp-admin/post.php?post=987&action=edit")
    replay = complete_draft_job(session, claimed.job.id, claimed.claim_token,
        wordpress_object_id=987, wordpress_edit_url=completed.wordpress_edit_url)
    assert replay.id == completed.id
    assert replay.state == "completed"
```

- [ ] **Step 2: Run the service tests and confirm they fail**

Run: `cd backend && .venv/bin/python -m pytest --import-mode=importlib -q tests/wordpress/test_draft_job_service.py`

Expected: fails because lifecycle functions are undefined.

- [ ] **Step 3: Implement strict payload creation and atomic transitions**

```python
JOB_CONTRACT_VERSION = "wordpress-draft-job-v1"
CLAIM_TTL = timedelta(minutes=5)


def complete_draft_job(session, job_id, claim_token, *, wordpress_object_id, wordpress_edit_url):
    job = session.get(WordPressDraftJob, job_id)
    if job is None:
        raise ValueError("draft_job_not_found")
    if job.state == "completed":
        if job.wordpress_object_id != wordpress_object_id:
            raise ValueError("draft_job_result_conflict")
        return job
    if job.state != "claimed" or not secrets.compare_digest(job.claim_token or "", claim_token):
        raise ValueError("draft_job_claim_invalid")
    job.state = "completed"
    job.wordpress_object_id = wordpress_object_id
    job.wordpress_edit_url = wordpress_edit_url
    job.completed_at = datetime.now(UTC)
    return job
```

Build the immutable payload only from the approved current proposal, its stored managed blueprint, normalized replacement package, approved URLs, SEO fields, exact blueprint version, and structure hash. Use row locking or a conditional update for claims. Expired claims return to `queued`; completed jobs never reopen.

- [ ] **Step 4: Run SQLite lifecycle and PostgreSQL concurrency tests**

Run: `cd backend && .venv/bin/python -m pytest --import-mode=importlib -q tests/wordpress/test_draft_job_service.py tests/wordpress/test_draft_job_postgres_concurrency.py`

Expected: lifecycle tests pass; PostgreSQL test passes when `WP_FIXPILOT_POSTGRES_TEST_URL` is set and otherwise skips explicitly.

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/app/domains/wordpress/draft_jobs.py backend/tests/wordpress/test_draft_job_service.py backend/tests/wordpress/test_draft_job_postgres_concurrency.py
git commit -m "feat: add outbound draft job lifecycle"
```

### Task 3: Expose Dashboard And Plugin Draft-Job APIs

**Files:**
- Create: `backend/app/api/routes/wordpress_draft_jobs.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/routes/page_packages.py`
- Modify: `backend/app/api/routes/page_blueprints.py`
- Modify: `backend/app/domains/page_packages/service.py`
- Test: `backend/tests/wordpress/test_draft_job_routes.py`

**Interfaces:**
- Dashboard endpoints use Supabase user authentication and manager authorization.
- Plugin endpoints use `Authorization: Bearer <project-key>` and `X-WP-FixPilot-Site`.
- Produces endpoints for credential create/rotate/revoke, job create/status, plugin verify/claim/complete/fail.

- [ ] **Step 1: Write failing route tests**

```python
def test_owner_creates_key_once_and_response_does_not_repeat_it(client, auth_headers, project):
    created = client.post(f"/projects/{project.id}/wordpress-outbound-credential",
        headers=auth_headers, json={"site_url": "https://member.example"})
    assert created.status_code == 201
    assert created.json()["key"].startswith("wpfx_")
    read = client.get(f"/projects/{project.id}/wordpress-outbound-credential", headers=auth_headers)
    assert "key" not in read.json()


def test_plugin_claim_is_project_scoped_and_contract_versioned(client, project_key, queued_job):
    response = client.post(f"/projects/{queued_job.project_id}/wordpress-draft-jobs/claim",
        headers={"Authorization": f"Bearer {project_key}", "X-WP-FixPilot-Site": "https://member.example"})
    assert response.status_code == 200
    assert response.json()["job"]["contract_version"] == "wordpress-draft-job-v1"
    assert "claim_token" in response.json()
```

- [ ] **Step 2: Run route tests and confirm 404 failures**

Run: `cd backend && .venv/bin/python -m pytest --import-mode=importlib -q tests/wordpress/test_draft_job_routes.py`

Expected: endpoints return 404 before router registration.

- [ ] **Step 3: Implement schemas, authentication dependency, and endpoints**

```python
def require_outbound_credential(project_id: str, authorization: str = Header(...),
    site_url: str = Header(..., alias="X-WP-FixPilot-Site"), session: Session = Depends(get_session)):
    raw = authorization.removeprefix("Bearer ").strip()
    credential = session.scalar(select(WordPressOutboundCredential).where(
        WordPressOutboundCredential.project_id == project_id,
        WordPressOutboundCredential.revoked_at.is_(None),
    ))
    if credential is None or not secrets.compare_digest(credential.key_hash, hash_project_key(raw)):
        raise HTTPException(status_code=401, detail="Invalid WordPress project key")
    if normalize_site_url(site_url) != credential.site_url:
        raise HTTPException(status_code=403, detail="WordPress site mismatch")
    return credential
```

Return `204` from claim when no eligible job exists. Completion accepts only positive object IDs, HTTPS or same-site admin edit URLs, and the exact claim token. Failure accepts only allowlisted bounded error codes and a 500-character message. The existing direct `create-draft` and manual handoff routes remain available but are no longer called by the primary frontend action.

Call `cancel_ineligible_draft_jobs` in the same transaction when accepting a new proposal version or withdrawing approval. Refuse blueprint deletion while a completed draft job references it, and cancel unfinished jobs before an otherwise valid blueprint deletion.

- [ ] **Step 4: Run all draft-job route tests and Ruff**

Run: `cd backend && .venv/bin/ruff check app tests && .venv/bin/python -m pytest --import-mode=importlib -q tests/wordpress/test_draft_job_routes.py tests/page_packages/test_proposal_routes.py`

Expected: Ruff passes and all focused tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add backend/app/api/routes/wordpress_draft_jobs.py backend/app/api/routes/page_packages.py backend/app/api/routes/page_blueprints.py backend/app/domains/page_packages/service.py backend/app/main.py backend/tests/wordpress/test_draft_job_routes.py
git commit -m "feat: expose outbound WordPress draft job API"
```

### Task 4: Add The Plugin Outbound Client And Processor

**Files:**
- Create: `plugin/wp-fixpilot-bridge/includes/class-outbound-client.php`
- Create: `plugin/wp-fixpilot-bridge/includes/class-draft-job-controller.php`
- Modify: `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`
- Test: `plugin/wp-fixpilot-bridge/tests/draft-job-test.php`

**Interfaces:**
- `WPFixPilot_Outbound_Client::verify(): array|WP_Error`
- `WPFixPilot_Outbound_Client::claim(): array|null|WP_Error`
- `WPFixPilot_Outbound_Client::complete(string $jobId, string $claimToken, array $draft): true|WP_Error`
- `WPFixPilot_Draft_Job_Controller::process_next(): array|null|WP_Error`
- Consumes the existing `WPFixPilot_Blueprint_Controller::create_draft(int $blueprintId, array $payload)`.

- [ ] **Step 1: Write failing strict-contract and idempotency tests**

```php
$unknown = $controller->process_payload([
    'contract_version' => 'wordpress-draft-job-v2',
]);
assert(is_wp_error($unknown));
assert($unknown->get_error_code() === 'wp_fixpilot_unsupported_contract');

$result = $controller->process_next();
assert($result['status'] === 'draft');
assert($GLOBALS['wpfixpilot_created_drafts'][0]['blueprint_id'] === 321);
assert($GLOBALS['wpfixpilot_completed_jobs'][0]['wordpress_object_id'] === $result['wordpress_object_id']);
```

- [ ] **Step 2: Run the PHP test and confirm missing-class failure**

Run: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/draft-job-test.php`

Expected: fails because the outbound client and controller do not exist.

- [ ] **Step 3: Implement outbound requests and strict job processing**

```php
private function headers(): array
{
    return [
        'Authorization' => 'Bearer ' . $this->projectKey,
        'X-WP-FixPilot-Site' => get_site_url(),
        'Content-Type' => 'application/json',
    ];
}

public function process_payload(array $job): array|WP_Error
{
    if (($job['contract_version'] ?? '') !== 'wordpress-draft-job-v1') {
        return new WP_Error('wp_fixpilot_unsupported_contract', 'Deze concepttaak gebruikt een onbekende contractversie.');
    }
    return $this->blueprintController->create_draft((int) $job['wordpress_blueprint_id'], [
        'expected_version' => (int) $job['expected_blueprint_version'],
        'expected_structure_hash' => (string) $job['expected_structure_hash'],
        'idempotency_key' => (string) $job['proposal_version_id'],
        'replacements' => $this->replacement_map((array) $job['replacements']),
        'approved_urls' => (array) $job['approved_urls'],
        'seo' => (array) $job['seo'],
    ]);
}
```

Treat HTTP 204 as no work. Never log or append the key to a URL. Report a completed draft only after the existing blueprint controller verifies persisted `draft` status. Map known `WP_Error` codes to the bounded backend failure codes.

- [ ] **Step 4: Run draft-job and existing blueprint tests**

Run: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli sh -lc 'php -d zend.assertions=1 -d assert.exception=1 tests/draft-job-test.php && php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php'`

Expected: both suites pass and existing blueprint behavior remains unchanged.

- [ ] **Step 5: Commit Task 4**

```bash
git add plugin/wp-fixpilot-bridge/includes/class-outbound-client.php plugin/wp-fixpilot-bridge/includes/class-draft-job-controller.php plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php plugin/wp-fixpilot-bridge/tests/draft-job-test.php
git commit -m "feat: process outbound WordPress draft jobs"
```

### Task 5: Add WordPress Connection Controls And Cron

**Files:**
- Modify: `plugin/wp-fixpilot-bridge/includes/class-admin.php`
- Modify: `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`
- Test: `plugin/wp-fixpilot-bridge/tests/draft-job-admin-test.php`

**Interfaces:**
- Admin-post actions: `wp_fixpilot_save_outbound_connection`, `wp_fixpilot_test_outbound_connection`, `wp_fixpilot_fetch_draft_job`.
- Cron hook: `wp_fixpilot_poll_draft_jobs` every five minutes.
- WordPress options: backend base URL, project ID, project key, last contact, last job status, bounded last error.

- [ ] **Step 1: Write failing capability, nonce, option, and cron tests**

```php
assert(has_action('wp_fixpilot_poll_draft_jobs'));
$admin->save_outbound_connection();
assert(get_option('wp_fixpilot_outbound_project_id') === 'project-1');
assert(get_option('wp_fixpilot_outbound_project_key') === 'wpfx_secret');
$admin->fetch_draft_job();
assert($GLOBALS['wpfixpilot_processed_job_count'] === 1);
```

Also assert that users without `manage_options` cannot change credentials and users without `edit_pages` cannot manually fetch jobs.

- [ ] **Step 2: Run the admin test and confirm action/cron failures**

Run: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/draft-job-admin-test.php`

Expected: fails because actions and cron are not registered.

- [ ] **Step 3: Implement settings, actions, status display, and scheduling**

```php
add_filter('cron_schedules', static function (array $schedules): array {
    $schedules['wp_fixpilot_five_minutes'] = ['interval' => 300, 'display' => 'Iedere vijf minuten'];
    return $schedules;
});
add_action('wp_fixpilot_poll_draft_jobs', static function (): void {
    (new WPFixPilot_Draft_Job_Controller())->process_next();
});
```

Use password inputs for project keys, never render the stored key, and keep the existing bridge-secret and manual import sections available during rollout. Manual fetch shows `Geen concepttaken`, `Concept aangemaakt`, or the bounded validation/network error.

- [ ] **Step 4: Run all plugin contract tests and PHP lint**

Run: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli sh -lc 'for test in tests/*-test.php; do php -d zend.assertions=1 -d assert.exception=1 "$test"; done; find . -name "*.php" -print0 | xargs -0 -n1 php -l'`

Expected: every PHP suite and lint check passes.

- [ ] **Step 5: Commit Task 5**

```bash
git add plugin/wp-fixpilot-bridge/includes/class-admin.php plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php plugin/wp-fixpilot-bridge/tests/draft-job-admin-test.php
git commit -m "feat: add outbound draft job controls"
```

### Task 6: Add Dashboard Key Management And Job Status

**Files:**
- Modify: `frontend/src/features/settings/WordPressBridgePanel.tsx`
- Modify: `frontend/src/features/settings/WordPressBridgePanel.test.tsx`
- Modify: `frontend/src/features/page-packages/proposalTypes.ts`
- Modify: `frontend/src/features/page-packages/PagePackageReview.tsx`
- Modify: `frontend/src/features/page-packages/PagePackageReview.test.tsx`

**Interfaces:**
- Consumes dashboard endpoints from Task 3.
- `OutboundCredentialRead` never contains a key; `OutboundCredentialCreated` contains a one-time `key`.
- `DraftJob` exposes state, bounded error, and WordPress edit URL.

- [ ] **Step 1: Write failing frontend tests for one-time key and queued draft**

```tsx
fireEvent.click(screen.getByRole("button", { name: "Projectkey maken" }));
expect(await screen.findByLabelText("Eenmalige projectkey")).toHaveValue("wpfx_once");
expect(screen.getByText("Deze key wordt niet opnieuw getoond.")).toBeInTheDocument();

fireEvent.click(screen.getByRole("button", { name: "WordPress-concept aanmaken" }));
expect(await screen.findByText("Wachten op WordPress")).toBeInTheDocument();
expect(window.open).not.toHaveBeenCalled();
```

- [ ] **Step 2: Run focused frontend tests and confirm failures**

Run: `cd frontend && npm test -- --run src/features/settings/WordPressBridgePanel.test.tsx src/features/page-packages/PagePackageReview.test.tsx`

Expected: fails because key controls and draft-job status do not exist.

- [ ] **Step 3: Implement key management and replace the primary handoff action**

```ts
type DraftJobState = "queued" | "claimed" | "completed" | "failed" | "cancelled";
type DraftJob = {
  id: string;
  state: DraftJobState;
  wordpress_edit_url?: string | null;
  error_code?: string | null;
  error_message?: string | null;
};
```

Create or rotate the key only after an owner/admin action and show it in a readonly field once. The review action POSTs to `/projects/${projectId}/page-proposals/${proposal.id}/draft-jobs`, refreshes proposal/job status, and never opens WordPress. Show the manual handoff as `Handmatige import gebruiken` in a secondary rollout section.

- [ ] **Step 4: Run frontend tests, lint, and production build**

Run: `cd frontend && npm test -- --run && npm run lint && npm run build`

Expected: all frontend tests, lint, and build pass.

- [ ] **Step 5: Commit Task 6**

```bash
git add frontend/src/features/settings/WordPressBridgePanel.tsx frontend/src/features/settings/WordPressBridgePanel.test.tsx frontend/src/features/page-packages/proposalTypes.ts frontend/src/features/page-packages/PagePackageReview.tsx frontend/src/features/page-packages/PagePackageReview.test.tsx
git commit -m "feat: manage outbound WordPress draft jobs"
```

### Task 7: Release Verification And Staging Acceptance

**Files:**
- Modify: `.superpowers/sdd/progress.md`
- Modify: `docs/operations.md`
- Modify: `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`
- Create: `docs/superpowers/reports/2026-07-11-outbound-wordpress-draft-jobs-release.md`

**Interfaces:**
- Consumes every prior task.
- Produces a versioned plugin ZIP, backend migration evidence, frontend deployment evidence, and one live draft result.

- [ ] **Step 1: Run the complete backend verification**

Run: `cd backend && .venv/bin/ruff check app tests alembic && .venv/bin/python -m pytest --import-mode=importlib -q && .venv/bin/alembic upgrade head`

Expected: Ruff passes, the full test suite passes except the documented PostgreSQL concurrency skip when its URL is unavailable, and Alembic reaches revision `0019_outbound_wordpress_draft_jobs`.

- [ ] **Step 2: Run the complete frontend and plugin verification**

Run: `cd frontend && npm test -- --run && npm run lint && npm run build`

Run: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli sh -lc 'for test in tests/*-test.php; do php -d zend.assertions=1 -d assert.exception=1 "$test"; done; find . -name "*.php" -print0 | xargs -0 -n1 php -l'`

Expected: all checks pass.

- [ ] **Step 3: Bump the plugin version and build the update ZIP**

Update the plugin header and `WPFIXPILOT_BRIDGE_VERSION` to the same next patch version. Build `/Users/tanerdag/Downloads/wp-fixpilot-bridge-update.zip` containing the `wp-fixpilot-bridge/` directory and no test fixtures, Git files, or local secrets.

- [ ] **Step 4: Deploy and perform the live staging acceptance**

Deploy the backend migration and API, deploy the production frontend, upload and activate the plugin ZIP, create a new project key, paste it into WordPress, and select `Verbinding testen`. Queue the approved 7G DCT proposal, select `Concepttaken ophalen`, and verify:

```text
Job state: completed
WordPress post type: page
WordPress post status: draft
Blueprint identity: unchanged
ACF and Yoast values: generated values present
Second retrieval: same WordPress object ID
Published pages created: 0
```

- [ ] **Step 5: Rotate the key and verify revocation**

Rotate the key in WP FixPilot, confirm the old plugin key receives HTTP 401, save the new key, and confirm `Verbinding testen` succeeds.

- [ ] **Step 6: Record evidence and commit release documentation**

Record commit IDs, deployment URLs, plugin version, migration revision, test totals, WordPress draft ID, edit URL, duplicate-retry result, and key-rotation result in the release report. Update Task 9 in `.superpowers/sdd/progress.md` only after live draft acceptance passes.

```bash
git add .superpowers/sdd/progress.md docs/operations.md docs/superpowers/reports/2026-07-11-outbound-wordpress-draft-jobs-release.md plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php
git commit -m "chore: release outbound WordPress draft jobs"
```
