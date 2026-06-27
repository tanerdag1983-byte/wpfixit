# Keyword Opportunity Page Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify weak DataForSEO page matches as new-page opportunities, generate a complete AI page package for review, and create an approved WordPress draft from project-specific builder and template settings.

**Architecture:** Introduce a `page_packages` backend domain with project configuration and page proposal models. Keep classification deterministic, generation behind the existing project AI policy, and draft creation inside the signed WordPress bridge through builder and SEO adapter contracts. Existing-page proposals remain unchanged.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, pytest, React 19, TypeScript, Vitest, PHP 8.1, WordPress REST API.

## Global Constraints

- Weak page matches must never receive an automatic existing-page URL.
- Builder, template, slot mapping, and SEO plugin are configured per project.
- New-page generation is disabled until the project template configuration validates.
- AI output is always reviewed and manually approved.
- WordPress creation always forces `post_status=draft`.
- Repeated create-draft calls are idempotent.
- Template, builder, or SEO-plugin conflicts create no partial WordPress page.
- Existing signed WordPress requests and project owner/admin authorization remain mandatory.

---

### Task 1: Classify keyword targets conservatively

**Files:**
- Modify: `backend/app/domains/dataforseo/relevance.py`
- Modify: `backend/app/domains/dataforseo/models.py`
- Modify: `backend/app/domains/dataforseo/service.py`
- Create: `backend/alembic/versions/0014_page_packages.py`
- Modify: `backend/tests/dataforseo/test_relevance.py`
- Modify: `backend/tests/dataforseo/test_routes.py`
- Modify: `frontend/src/routes/dashboard/OpportunitiesPage.tsx`
- Modify: `frontend/src/routes/dashboard/OpportunitiesPage.test.tsx`

**Interfaces:**
- Produces `PageMatch(classification, url, score, evidence)` from `classify_target(keyword, context)`.
- Adds `target_classification`, `target_score`, and `target_evidence` to `KeywordOpportunity`.

- [ ] Write failing tests for VW-to-Alfa and generic-query-to-Cupra mismatches, plus exact/entity matches.
- [ ] Run targeted tests and confirm current matching fails.
- [ ] Compute project token document frequency and score phrase, rare-token, and common-token evidence. Return `existing_page`, `new_page`, or `review` using fixed thresholds.
- [ ] Persist and expose classification evidence; migrate existing rows with `new_page` when no URL and `review` when a prior URL has insufficient evidence after the next sync.
- [ ] Update Kansen cards with `Bestaande pagina verbeteren`, `Nieuwe pagina aanbevolen`, or `Keuze controleren`; show `Pagina laten maken` only for new-page targets.
- [ ] Run backend and frontend targeted tests.
- [ ] Commit: `feat: classify keyword page targets`

### Task 2: Store project page-package configuration

**Files:**
- Create: `backend/app/domains/page_packages/__init__.py`
- Create: `backend/app/domains/page_packages/models.py`
- Create: `backend/app/domains/page_packages/schemas.py`
- Create: `backend/app/api/routes/page_packages.py`
- Modify: `backend/app/main.py`
- Extend: `backend/alembic/versions/0014_page_packages.py`
- Create: `backend/tests/page_packages/test_settings_routes.py`

**Interfaces:**
- Produces `ProjectPagePackageSettings` keyed by project ID with `builder`, `template_wordpress_page_id`, `seo_plugin`, `slot_mapping`, `template_content_hash`, `validation_state`, and `validated_at`.
- Produces GET/PUT/validate endpoints from the design.

- [ ] Write failing model and route tests for project isolation, manager-only updates, required builder values, and invalid template ownership.
- [ ] Run tests and confirm RED.
- [ ] Add model, schema validation, migration, project-scoped routes, and payload redaction.
- [ ] Require semantic mappings for `hero_title`, `introduction`, `main_content`, `faq`, `cta_title`, and `cta_text` before marking settings valid.
- [ ] Run migration/model/route tests.
- [ ] Commit: `feat: add project page package settings`

### Task 3: Detect builders and inspect template slots

**Files:**
- Create: `plugin/wp-fixpilot-bridge/includes/builder-adapters/interface-builder-adapter.php`
- Create: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-gutenberg-adapter.php`
- Create: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-elementor-adapter.php`
- Create: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-bricks-adapter.php`
- Create: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-wpbakery-adapter.php`
- Create: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-acf-adapter.php`
- Create: `plugin/wp-fixpilot-bridge/includes/class-page-package-controller.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-rest-controller.php`
- Modify: `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`
- Modify: `backend/app/domains/wordpress/client.py`
- Modify: `backend/app/api/routes/page_packages.py`
- Create: `plugin/wp-fixpilot-bridge/tests/page-package-test.php`
- Create: `backend/tests/page_packages/test_template_routes.py`

**Interfaces:**
- Bridge GET `/builders` returns detected builders and SEO plugin.
- Bridge GET `/templates/{id}/slots?builder=...` returns template hash and `[{path, label, value_type}]`.
- Python client exposes `builders()` and `template_slots(object_id, builder)`.

- [ ] Write failing PHP adapter contract tests and backend signed-client/route tests.
- [ ] Implement detection and read-only slot inspection for all five builders.
- [ ] Reject unsupported field types and templates not owned by the connected site.
- [ ] Validate saved mappings against returned paths and store the current template hash.
- [ ] Run PHP and backend tests.
- [ ] Commit: `feat: inspect wordpress page package templates`

### Task 4: Add settings UI and one-time slot mapping

**Files:**
- Create: `frontend/src/features/settings/PagePackageSettingsPanel.tsx`
- Create: `frontend/src/features/settings/PagePackageSettingsPanel.test.tsx`
- Modify: `frontend/src/features/settings/AiSettingsPanel.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes page-package settings and template-inspection endpoints.
- Produces a validated project-local default package.

- [ ] Write failing UI tests for loading project settings, selecting builder/template, mapping required slots, validation, and project switching.
- [ ] Add `Standaard paginapakket` settings section with detected values and explicit validation state.
- [ ] Disable save/validation for duplicate required mappings or missing fields and display stale-template conflicts.
- [ ] Run tests, lint, and build.
- [ ] Commit: `feat: configure project page package templates`

### Task 5: Generate and persist complete AI page proposals

**Files:**
- Create: `backend/app/domains/page_packages/generation.py`
- Create: `backend/app/domains/page_packages/service.py`
- Extend: `backend/app/domains/page_packages/models.py`
- Extend: `backend/app/domains/page_packages/schemas.py`
- Modify: `backend/app/api/routes/page_packages.py`
- Extend: `backend/alembic/versions/0014_page_packages.py`
- Modify provider implementations under `backend/app/domains/recommendations/`
- Create: `backend/tests/page_packages/test_generation.py`
- Create: `backend/tests/page_packages/test_proposal_routes.py`

**Interfaces:**
- Adds `PagePackageProposal` and project-scoped create/get/update/approve endpoints.
- Adds provider method `generate_page_package(context) -> GeneratedPagePackage` for OpenAI, Anthropic, Gemini, OpenAI-compatible, and OpenRouter.

- [ ] Write failing schema tests for required title, slug, SEO fields, sections, FAQ, CTA, links, safe HTML, and length rules.
- [ ] Write provider contract tests using strict structured JSON responses.
- [ ] Build generation context from company profile, custom prompt, opportunity metrics, inventory, internal-link candidates, and template slots.
- [ ] Persist a `Job` and proposal state so refresh resumes status; record model, prompt version, and token usage.
- [ ] Require valid page-package settings and a `new_page`/user-confirmed target.
- [ ] Add update and explicit approval rules; approved proposals become immutable except by returning to proposed state through regeneration.
- [ ] Run generation and route tests.
- [ ] Commit: `feat: generate reviewable keyword page packages`

### Task 6: Build the proposal review UI

**Files:**
- Create: `frontend/src/features/page-packages/PagePackageReview.tsx`
- Create: `frontend/src/features/page-packages/PagePackageReview.test.tsx`
- Modify: `frontend/src/routes/dashboard/OpportunitiesPage.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- `Pagina laten maken` creates or resumes a proposal and navigates to `#page-proposal` with persisted proposal ID.
- Review UI saves edits, approves, and later invokes draft creation.

- [ ] Write failing tests for generation progress surviving refresh, all editable package fields, preview sanitization, back navigation, approval, and disabled draft creation before approval.
- [ ] Add dedicated review route and structured editor for title, slug, SEO, hero, sections, FAQ, CTA, and internal links.
- [ ] Display clear `Concept` wording and never show `Publiceren` in this flow.
- [ ] Run tests, lint, and build.
- [ ] Commit: `feat: review generated keyword pages`

### Task 7: Create idempotent WordPress drafts

**Files:**
- Extend builder adapters and `class-page-package-controller.php`
- Modify SEO adapter files under `plugin/wp-fixpilot-bridge/includes/seo-adapters/`
- Modify `plugin/wp-fixpilot-bridge/includes/class-rest-controller.php`
- Modify `backend/app/domains/wordpress/client.py`
- Modify `backend/app/api/routes/page_packages.py`
- Modify `frontend/src/features/page-packages/PagePackageReview.tsx`
- Extend PHP, backend, and frontend page-package tests.

**Interfaces:**
- Bridge POST `/draft-pages` accepts template ID, expected hash, builder, mapping, SEO plugin, idempotency key, and approved package.
- Returns `{wordpress_object_id, edit_url, status: "draft", content_hash}`.

- [ ] Write failing tests proving approval is mandatory, `post_status` is forced to `draft`, template conflicts create nothing, and repeated idempotency keys return one page.
- [ ] Clone template post attributes and builder-owned metadata, then write only mapped slots through the selected adapter.
- [ ] Write Yoast, Rank Math, or AIOSEO title, description, and focus keyword through the matching adapter.
- [ ] Add backend create-draft orchestration and persist returned WordPress identifiers atomically.
- [ ] Add review-page `Concept aanmaken` and WordPress edit link on success.
- [ ] Run all PHP, backend, and frontend tests.
- [ ] Commit: `feat: create approved wordpress page drafts`

### Task 8: Verify and release

**Files:**
- Modify plugin version and deployment documentation if required.

- [ ] Run `php` bridge tests, complete backend pytest/compile/ruff, and complete frontend tests/lint/build.
- [ ] Run Alembic from the previous production revision through head on PostgreSQL-compatible configuration.
- [ ] Review the complete diff for authorization, secret leakage, unsafe HTML, idempotency, and destructive WordPress behavior.
- [ ] Push `feature/platform-build`, fast-forward `main`, and push without force.
- [ ] Deploy Vercel and Render, update the WordPress bridge on staging, reconnect/synchronize inventory, configure the staging project template, and verify one opportunity through draft creation without publishing it.
