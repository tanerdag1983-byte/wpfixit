# OpenCode Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable repository instructions and a launch-focused handoff so OpenCode can resume WP FixPilot at the Managed Page Blueprints implementation without rediscovering the project.

**Architecture:** `AGENTS.md` is the stable, repository-wide operating contract for any coding agent. `HANDOFF.md` is the time-sensitive continuation pointer; it records the current implementation baseline and delegates detailed execution to the existing Managed Page Blueprints design and plan.

**Tech Stack:** Markdown, Git, FastAPI/Python 3.12, React 19/TypeScript, PHP 8.2 WordPress bridge, PostgreSQL/Alembic, Vercel, Render, Supabase.

## Global Constraints

- Keep the handoff launch-focused and do not add product scope.
- Do not duplicate the complete Managed Page Blueprints plan.
- Do not include credentials, provider tokens, customer data, or private prompts.
- Preserve explicit user approval before WordPress mutations.
- Treat project and organization scoping as a security boundary.
- Do not deploy automatically; follow the existing deployment documents and obtain explicit authorization.
- Verify repository state at continuation time because commit and worktree details can change.

---

## File Structure

- Create `AGENTS.md`: durable project architecture, workflow, verification, security, Git, and deployment instructions shared by Codex and OpenCode.
- Create `HANDOFF.md`: current continuation point, launch priority, authoritative blueprint documents, restart procedure, and completion checks.

### Task 1: Add Durable Repository Instructions

**Files:**
- Create: `AGENTS.md`
- Reference: `.github/workflows/ci.yml`
- Reference: `docs/security.md`
- Reference: `docs/deployment.md`
- Reference: `docs/live-deploy.md`
- Reference: `docs/operations.md`

**Interfaces:**
- Consumes: repository layout, CI commands, architecture design, and operational documentation.
- Produces: repository-wide instructions automatically read by Codex and OpenCode.

- [ ] **Step 1: Create `AGENTS.md` with the durable operating contract**

Create `AGENTS.md` with this exact content:

```markdown
# WP FixPilot Agent Instructions

## Mission

Move WP FixPilot toward a reliable production release with the smallest safe
change set. Continue approved designs and plans before proposing new scope.
Avoid unrelated refactors, speculative abstractions, and cosmetic churn.

## Repository Map

- `backend/`: FastAPI API, SQLAlchemy models, Alembic migrations, domain
  services, provider clients, and pytest tests.
- `frontend/`: React 19, TypeScript, Vite, TanStack Query, and Vitest UI.
- `plugin/wp-fixpilot-bridge/`: PHP WordPress bridge, REST controllers,
  builder adapters, and standalone PHP contract tests.
- `infrastructure/`: Render configuration, Supabase resources, and smoke tests.
- `docs/`: architecture, security, operations, deployment, approved designs,
  and executable implementation plans.

Read the relevant design and implementation plan in `docs/superpowers/`
before changing a planned feature. Resume at the first genuinely incomplete
step after verifying the repository; do not assume checklist state is current.

## Development Workflow

1. Inspect `git status`, the current branch, recent commits, and relevant files.
2. Preserve user changes and do not rewrite unrelated work.
3. Follow test-driven steps from the approved implementation plan.
4. Run the smallest relevant test first, then the complete affected suite.
5. Keep migrations reversible and compatible with existing data.
6. Commit coherent, verified changes with focused messages when requested by
   the active plan or user.

Do not silently replace approved architecture. If a plan is stale or blocked,
record concrete evidence and ask before materially changing direction.

## Verification

Backend setup and full CI-equivalent checks:

```bash
cd backend
python -m pip install -e ".[dev]"
ruff check .
alembic upgrade head
pytest
```

Run focused backend tests with:

```bash
cd backend
pytest path/to/test_file.py -q
```

Frontend full checks:

```bash
cd frontend
npm ci
npm run lint
npm test -- --run
npm run build
```

Run a focused frontend test with:

```bash
cd frontend
npm test -- --run path/to/test-file.test.tsx
```

WordPress bridge contract checks:

```bash
cd plugin/wp-fixpilot-bridge
php tests/auth-test.php
php tests/change-controller-test.php
php tests/page-package-test.php
```

When adding a new bridge contract test, add its direct PHP command to CI and
to the relevant implementation plan.

## Product And Security Invariants

- Every tenant-owned query must be scoped through organization membership;
  possessing a project ID is never authorization.
- Never log or commit access tokens, refresh tokens, API keys, bridge secrets,
  encryption keys, full private prompts, or customer content payloads.
- AI output is untrusted, schema-validated proposal data. It must never write
  directly to WordPress.
- Every WordPress mutation requires explicit approval from an authorized user.
- WordPress writes must retain immutable before/after history and rollback
  behavior.
- Generated pages remain drafts until a user deliberately publishes them.
- Validate bridge signatures, timestamps, nonces, capabilities, mutation
  allowlists, expected versions, and structure hashes where applicable.
- Provider fallbacks may handle translated provider failures, but must not hide
  validation or application errors.

See `docs/security.md` and `docs/operations.md` for the authoritative details.

## Managed Page Blueprints

For the active blueprint work, the authoritative documents are:

- `docs/superpowers/specs/2026-06-27-managed-page-blueprints-design.md`
- `docs/superpowers/plans/2026-06-28-managed-page-blueprints.md`

Preserve complete ACF, Elementor, WPBakery, Bricks, or Gutenberg structure.
AI may replace only schema-listed text fields and approved internal-link or CTA
URLs. Source pages and managed blueprints are immutable during generation;
generated WordPress pages are always drafts. Keep existing page-package routes
operational until the planned migration is complete.

## Deployment

Do not infer permission to deploy, rotate credentials, change production data,
or publish WordPress content. When the user explicitly requests deployment:

1. Run the affected full verification suites.
2. Follow `docs/deployment.md`, `docs/live-deploy.md`, and `docs/operations.md`.
3. Apply migrations through the documented pre-deploy process.
4. Run `python3 infrastructure/smoke_check.py` against local or configured API
   state and again with the production API URL after deployment.
5. Complete the documented authentication, crawl, recommendation, WordPress,
   Search Console, GA4, publish, and rollback smoke checks.
```

- [ ] **Step 2: Verify the instruction file is complete and free of secrets**

Run:

```bash
test -s AGENTS.md
rg -n "Repository Map|Verification|Product And Security Invariants|Managed Page Blueprints|Deployment" AGENTS.md
git diff --check -- AGENTS.md
```

Expected: `test` exits 0, `rg` prints all five headings, and `git diff --check`
prints no errors.

Inspect the file for credential-shaped values:

```bash
rg -n "(sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,}|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY)" AGENTS.md
```

Expected: no matches.

- [ ] **Step 3: Review the diff**

Run:

```bash
git diff -- AGENTS.md
```

Expected: only the approved durable instructions appear.

### Task 2: Add The Launch-Focused Continuation Handoff

**Files:**
- Create: `HANDOFF.md`
- Reference: `AGENTS.md`
- Reference: `docs/superpowers/specs/2026-06-27-managed-page-blueprints-design.md`
- Reference: `docs/superpowers/plans/2026-06-28-managed-page-blueprints.md`

**Interfaces:**
- Consumes: `AGENTS.md`, Git state, the approved blueprint design, and its implementation plan.
- Produces: the exact startup sequence and first work item for the next OpenCode session.

- [ ] **Step 1: Capture the repository baseline**

Run:

```bash
git branch --show-current
git rev-parse --short HEAD
git status --short
git log -5 --oneline
```

Expected: branch `main`; the commit may include handoff-documentation commits
after product baseline `721dd07`; only the planned handoff files may be
uncommitted.

- [ ] **Step 2: Create `HANDOFF.md` with the continuation contract**

Create `HANDOFF.md` with this exact content:

```markdown
# WP FixPilot OpenCode Handoff

## Objective

Continue the existing WP FixPilot implementation and reach a reliable live
release quickly. Follow approved scope, finish launch-critical work, and avoid
unrelated refactoring or feature expansion.

## Repository Baseline

- Repository: `wp-fixpilot-new`
- Branch when prepared: `main`
- Last product implementation commit: `1d6f3a2` (`fix: support nested ACF page templates`)
- Managed Page Blueprints design commit: `1f27a51`
- Managed Page Blueprints plan commit: `721dd07`

The commit and working tree may have changed since this handoff was written.
Treat the values above as orientation, then verify current state before editing.

## Current Continuation Point

Managed Page Blueprints is the latest approved workstream. Its design and
implementation plan exist, but implementation had not started when this
handoff was prepared. The representative planned files below were absent:

- `backend/app/domains/page_blueprints/models.py`
- `backend/alembic/versions/0017_managed_page_blueprints.py`
- `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- `frontend/src/features/blueprints/BlueprintSettingsPanel.tsx`

Authoritative documents:

- `docs/superpowers/specs/2026-06-27-managed-page-blueprints-design.md`
- `docs/superpowers/plans/2026-06-28-managed-page-blueprints.md`

Begin with Task 1 of the implementation plan unless repository inspection
shows that part has since been implemented. Resume at the first incomplete
step supported by the actual files and tests, not merely by unchecked boxes.

## OpenCode Startup Prompt

Use this prompt from the repository root:

```text
Read AGENTS.md and HANDOFF.md completely. Inspect git status, the current
branch, recent commits, and all relevant existing files. Then read the Managed
Page Blueprints design and implementation plan. Continue at the first genuinely
incomplete plan step. Follow the plan's test-first sequence, preserve existing
page-package compatibility, and keep the change set focused on the fastest safe
route to production. Do not deploy or mutate production without explicit user
authorization. Report concrete blockers instead of changing approved scope.
```

## Before Editing

```bash
git status --short
git branch --show-current
git log -8 --oneline
test -f AGENTS.md
test -f docs/superpowers/specs/2026-06-27-managed-page-blueprints-design.md
test -f docs/superpowers/plans/2026-06-28-managed-page-blueprints.md
```

Read the relevant implementation files named in the plan before creating or
modifying them. Preserve user changes and investigate any divergence from this
baseline.

## Launch Discipline

- Complete and verify one plan task at a time.
- Prefer focused tests while iterating, then run complete affected suites.
- Keep existing page-package routes working until the planned migration is
  complete.
- Generated WordPress pages remain drafts and require explicit user approval.
- Do not expose credentials or weaken tenant, signature, nonce, capability,
  version, or structure-hash checks.
- Do not treat a passing build as production readiness. Follow
  `docs/deployment.md`, `docs/live-deploy.md`, and `docs/operations.md` when the
  user authorizes a deployment.

## Definition Of Done For The Handoff

The next agent has read the instructions, verified repository state, identified
the first incomplete blueprint step, run the relevant baseline test, and begun
work without adding new scope. The software is only ready for live deployment
after the complete affected test suites and documented smoke checks pass.
```

- [ ] **Step 3: Verify the handoff references and baseline**

Run:

```bash
test -s HANDOFF.md
test -f docs/superpowers/specs/2026-06-27-managed-page-blueprints-design.md
test -f docs/superpowers/plans/2026-06-28-managed-page-blueprints.md
rg -n '<[A-Z_]+>' HANDOFF.md
git diff --check -- HANDOFF.md
```

Expected: the first three `test` commands exit 0; `rg` prints no matches; and
`git diff --check` prints no errors.

- [ ] **Step 4: Verify the described continuation point against the repository**

Run:

```bash
for file in \
  backend/app/domains/page_blueprints/models.py \
  backend/alembic/versions/0017_managed_page_blueprints.py \
  plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php \
  frontend/src/features/blueprints/BlueprintSettingsPanel.tsx; do
  if test -e "$file"; then printf 'EXISTS %s\n' "$file"; else printf 'MISSING %s\n' "$file"; fi
done
```

Expected at the documented baseline: all four paths print `MISSING`. If any
prints `EXISTS`, update `HANDOFF.md` to state the actual first incomplete task.

- [ ] **Step 5: Review and commit both handoff files**

Run:

```bash
git diff -- AGENTS.md HANDOFF.md
git diff --check
git status --short
git add AGENTS.md HANDOFF.md
git commit -m "docs: add opencode project handoff"
```

Expected: the diff contains only the approved handoff content, whitespace
validation succeeds, and the commit includes exactly `AGENTS.md` and
`HANDOFF.md`.
