# DataForSEO Relevance Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict DataForSEO opportunities to the project's real business and page topics, remove stale irrelevant results, and explain that the settings field requires the generated API password.

**Architecture:** Add a deterministic relevance module that derives bounded seeds, business anchors, and page topics from `CompanyProfile` and `WordPressPage`. The existing synchronization service will filter and match candidates through that context before upserting a fresh project snapshot. The frontend change is limited to explanatory copy and the official API-access link.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, pytest, React 19, TypeScript, Vitest, Testing Library.

## Global Constraints

- Generic terms such as `auto` and `kosten` cannot establish business relevance or a page match by themselves.
- One project synchronization remains one bounded DataForSEO keyword-ideas request.
- A failed provider request must leave stored opportunities unchanged.
- A successful request replaces the previous DataForSEO snapshot, including when all returned candidates are irrelevant.
- AI cannot override deterministic relevance filtering.
- No database migration is required.

---

### Task 1: Build project keyword context and relevance scoring

**Files:**
- Create: `backend/app/domains/dataforseo/relevance.py`
- Create: `backend/tests/dataforseo/test_relevance.py`

**Interfaces:**
- Consumes: `Session`, `Project`, `CompanyProfile`, and `WordPressPage`.
- Produces: `KeywordContext`, `build_keyword_context(session, project, limit=20)`, `is_relevant(keyword, context)`, and `target_url(keyword, context)`.

- [ ] **Step 1: Write failing context tests**

Create fixtures for a transmission company with services including `transmissie revisie`, `koppeling vervangen`, and `DSG automaat revisie`, plus pages `/koppeling-vervangen-kosten/` and `/dsg-automaat-reviseren/`. Assert that seeds include service/page phrases but exclude the hostname and standalone `kosten`.

- [ ] **Step 2: Run the context test and confirm RED**

Run: `./.venv/bin/pytest -q tests/dataforseo/test_relevance.py`

Expected: collection fails because `app.domains.dataforseo.relevance` does not exist.

- [ ] **Step 3: Implement normalized context types**

Implement immutable `PageTopic` and `KeywordContext` dataclasses. Tokenize with lowercase alphanumeric tokens, remove Dutch utility/intent words such as `auto`, `kosten`, `bedrijf`, `service`, `pagina`, `contact`, `over`, `ons`, `voor`, and `bij`, and preserve normalized service phrases. Build business anchors primarily from profile services, then profile description and relevant WordPress page phrases as fallback. Limit seeds to 20 unique multi-word values.

- [ ] **Step 4: Add failing relevance and page-match tests**

Assert:

```python
assert not is_relevant("autosleutel bijmaken", context)
assert not is_relevant("krassen auto verwijderen kosten", context)
assert is_relevant("koppeling vervangen kosten", context)
assert is_relevant("dsg automaat reviseren", context)
assert target_url("koppeling vervangen kosten", context).endswith(
    "/koppeling-vervangen-kosten/"
)
assert target_url("dsg automaat reviseren", context).endswith(
    "/dsg-automaat-reviseren/"
)
```

- [ ] **Step 5: Implement deterministic filtering and weighted matching**

Require at least one non-generic business token. Score page phrases above token overlap, then score distinctive overlapping tokens. Return no page when the best score is zero. Resolve equal scores deterministically by URL.

- [ ] **Step 6: Run tests and commit**

Run: `./.venv/bin/pytest -q tests/dataforseo/test_relevance.py`

Expected: all relevance tests pass.

Commit: `feat: add project-aware keyword relevance`

### Task 2: Apply relevance filtering and snapshot cleanup during sync

**Files:**
- Modify: `backend/app/domains/dataforseo/service.py`
- Modify: `backend/tests/dataforseo/test_routes.py`

**Interfaces:**
- Consumes: `build_keyword_context`, `is_relevant`, and `target_url` from Task 1.
- Produces: existing `project_seed_terms(...)` and `upsert_keyword_opportunities(...)` APIs with stricter behavior.

- [ ] **Step 1: Write failing route test for filtering and correct mapping**

Store the transmission company profile and two WordPress pages. Return four provider rows: two relevant and the two known irrelevant examples. Assert that only the relevant rows are returned and stored, and each has the correct target URL.

- [ ] **Step 2: Run the test and confirm RED**

Run: `./.venv/bin/pytest -q tests/dataforseo/test_routes.py`

Expected: irrelevant provider rows are currently stored.

- [ ] **Step 3: Filter before upsert and use weighted page matching**

Replace the current hostname/title seed builder with `build_keyword_context(...).seeds`. Build one context inside `upsert_keyword_opportunities`, skip candidates for which `is_relevant` is false, and use `target_url` for accepted candidates.

- [ ] **Step 4: Write failing stale-snapshot test**

Pre-store a `KeywordOpportunity` named `krassen auto verwijderen kosten`, run a successful sync returning only `koppeling vervangen kosten`, and assert the stale row is deleted. Retain the existing provider-error behavior to prove failed calls do not enter snapshot replacement.

- [ ] **Step 5: Implement successful snapshot replacement**

Track accepted `(keyword, location_code, language_code)` identities. After processing all rows, delete existing project opportunities with source `dataforseo` whose identity is absent. Commit once after upserts and deletions.

- [ ] **Step 6: Run backend DataForSEO tests and commit**

Run: `./.venv/bin/pytest -q tests/dataforseo`

Expected: all DataForSEO tests pass.

Commit: `fix: filter dataforseo opportunities by project`

### Task 3: Explain the generated API password in settings

**Files:**
- Modify: `frontend/src/features/settings/DataForSeoPanel.tsx`
- Modify: `frontend/src/features/settings/DataForSeoPanel.test.tsx`
- Modify: `frontend/src/styles.css` only if existing helper-text styles cannot be reused.

**Interfaces:**
- Produces accessible explanatory text linked to the DataForSEO password input.

- [ ] **Step 1: Write failing frontend test**

Assert that the panel renders text containing `automatisch gegenereerde API-wachtwoord`, that the official link points to `https://app.dataforseo.com/api-access`, and that the password input references the explanation through `aria-describedby`.

- [ ] **Step 2: Run the test and confirm RED**

Run: `npm test -- --run src/features/settings/DataForSeoPanel.test.tsx`

Expected: helper text and link are absent.

- [ ] **Step 3: Add the accessible helper text**

Add this text directly below the field:

```text
Gebruik het automatisch gegenereerde DataForSEO API-wachtwoord, niet je normale accountwachtwoord.
```

Link `API-wachtwoord bekijken` to the official API Access page with safe external-link attributes.

- [ ] **Step 4: Run the test and commit**

Run: `npm test -- --run src/features/settings/DataForSeoPanel.test.tsx`

Expected: the panel tests pass.

Commit: `fix: clarify dataforseo api credentials`

### Task 4: Full verification and live release

**Files:**
- No production files expected.

**Interfaces:**
- Verifies all prior task outputs together.

- [ ] **Step 1: Run complete backend verification**

Run: `./.venv/bin/pytest -q && ./.venv/bin/python -m compileall -q app`

Expected: all tests pass and compilation exits zero.

- [ ] **Step 2: Run complete frontend verification**

Run: `npm test -- --run && npm run lint && npm run build`

Expected: all tests, ESLint, TypeScript, and Vite build pass.

- [ ] **Step 3: Check and publish Git state**

Run `git diff --check`, inspect the final diff, commit any remaining plan-status updates, push `feature/platform-build`, fast-forward `main`, and push `main` without force.

- [ ] **Step 4: Deploy and verify production**

Deploy the linked Vercel frontend from `frontend/`, verify the production bundle contains the API-password guidance, and verify Render OpenAPI still exposes the DataForSEO endpoints. Confirm that the backend deployment is on the released commit before asking the user to synchronize opportunities again.
