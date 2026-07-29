# Controlled Blog Inline Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propose zero to four additional blog images at stable semantic anchors and import only approved selections without injecting image HTML into rich text.

**Architecture:** Blog-capable snapshot adapters expose stable insertion anchors between semantic blocks. A deterministic planner chooses eligible anchors from H2-level sections, then reuses the candidate, storage, approval, and draft-import contracts from template image proposals. Each adapter inserts its native image block or element at the approved anchor.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2, React 19, TypeScript, WordPress/PHP 8.2, existing image candidate and outbound draft v2 contracts.

## Global Constraints

- This plan starts only after `2026-07-30-template-image-proposals.md` is complete.
- Every blog already uses required featured and first in-page image roles.
- Additional inline image count is zero through four.
- AI never writes image HTML into rich-text values.
- An anchor is stable, adapter-owned, and adjacent to a concrete H2-level subject.
- Duplicate semantic subjects and duplicate content hashes are rejected.
- Text regeneration preserves approved images unless neighboring section meaning changes materially.
- Existing live pages are immutable and publication remains manual.
- Add no dependency.

---

### Task 1: Expose Stable Blog Image Anchors

**Files:**
- Modify: `backend/app/domains/page_blueprints/schemas.py`
- Modify: `backend/tests/page_blueprints/test_schemas.py`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/interface-blueprint-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-acf-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-gutenberg-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-elementor-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-wpbakery-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-bricks-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/tests/acf-blueprint-adapter-test.php`
- Modify: `plugin/wp-fixpilot-bridge/tests/blueprint-adapters-test.php`
- Create: `plugin/wp-fixpilot-bridge/tests/blog-image-anchor-test.php`

**Interfaces:**
- Produces: `SnapshotImageAnchor(id, after_block_id, semantic_section, heading_field_id, native_container_path)`
- Extends `snapshot-content-v2` with `image_anchors: list[SnapshotImageAnchor]`
- Adapter method: `image_anchors(int $postId): array|WP_Error`

- [ ] **Step 1: Write failing schema and adapter tests**

```python
def test_anchor_must_reference_a_known_block_and_heading():
    with pytest.raises(ValidationError, match="anchor"):
        SnapshotContentSchema.model_validate(
            snapshot_schema(
                image_anchors=[
                    anchor(after_block_id="missing", heading_field_id="missing-heading")
                ]
            )
        )
```

```php
$anchors = $adapter->image_anchors(42);
assert($anchors[0]['after_block_id'] === 'acf-content-2');
assert($anchors[0]['heading_field_id'] === 'acf-content-2-heading');
assert($anchors[0]['native_container_path'] !== '');
```

- [ ] **Step 2: Run focused tests**

Run: `cd backend && .venv/bin/python -m pytest tests/page_blueprints/test_schemas.py -q`

Run: `cd plugin/wp-fixpilot-bridge && docker run --rm -v "$PWD:/app" -w /app php:8.2-cli sh -lc 'php -d zend.assertions=1 -d assert.exception=1 tests/blog-image-anchor-test.php && php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-adapters-test.php'`

Expected: FAIL because anchors are absent.

- [ ] **Step 3: Add only anchors adapters can safely apply**

Build anchor IDs from existing stable block/element IDs and neighboring heading field IDs. Return no anchor for free-form rich text without a native container boundary. Preserve existing snapshot v1/v2 parsing.

- [ ] **Step 4: Run adapter and schema suites**

Run: `cd backend && .venv/bin/python -m pytest tests/page_blueprints -q`

Run: `cd plugin/wp-fixpilot-bridge && docker run --rm -v "$PWD:/app" -w /app php:8.2-cli sh -lc 'for test in tests/acf-blueprint-adapter-test.php tests/blueprint-adapters-test.php tests/blog-image-anchor-test.php tests/template-snapshot-test.php; do php -d zend.assertions=1 -d assert.exception=1 "$test" || exit 1; done'`

Expected: PASS.

- [ ] **Step 5: Obtain independent review and commit**

```bash
git add backend/app/domains/page_blueprints/schemas.py \
  backend/tests/page_blueprints/test_schemas.py \
  plugin/wp-fixpilot-bridge/includes \
  plugin/wp-fixpilot-bridge/tests/acf-blueprint-adapter-test.php \
  plugin/wp-fixpilot-bridge/tests/blueprint-adapters-test.php \
  plugin/wp-fixpilot-bridge/tests/blog-image-anchor-test.php
git commit -m "feat: expose stable blog image anchors"
```

---

### Task 2: Plan Zero To Four Additional Images

**Files:**
- Create: `backend/app/domains/page_packages/blog_images.py`
- Modify: `backend/app/domains/page_packages/image_generation.py`
- Create: `backend/tests/page_packages/test_blog_image_planner.py`
- Modify: `backend/tests/page_packages/test_image_generation.py`

**Interfaces:**
- Produces: `BlogImagePlan(anchor_id, semantic_section, subject, reason)`
- Produces: `plan_blog_images(schema, replacements, existing_candidates) -> tuple[BlogImagePlan, ...]`
- Produces at most four plans and no duplicates by normalized subject

- [ ] **Step 1: Write failing planner tests**

```python
def test_short_blog_gets_no_additional_images():
    assert plan_blog_images(short_blog_schema(), {}, ()) == ()


def test_long_blog_gets_at_most_four_distinct_anchor_plans():
    plans = plan_blog_images(long_blog_schema(sections=8), replacements(), ())
    assert 0 < len(plans) <= 4
    assert len({plan.anchor_id for plan in plans}) == len(plans)
    assert len({plan.subject.casefold() for plan in plans}) == len(plans)
```

- [ ] **Step 2: Run focused tests**

Run: `cd backend && .venv/bin/python -m pytest tests/page_packages/test_blog_image_planner.py tests/page_packages/test_image_generation.py -q`

Expected: FAIL because the planner is absent.

- [ ] **Step 3: Implement deterministic eligibility**

An eligible anchor must follow a non-empty H2-level heading, have at least 180 words in its neighboring semantic section, and have a subject not already used by required or additional image roles. Rank anchors by section word count and original order, then take four. Generate one candidate for each returned plan through the existing `generate_image_candidate` service.

- [ ] **Step 4: Run planner and generation tests**

Run: `cd backend && .venv/bin/python -m pytest tests/page_packages/test_blog_image_planner.py tests/page_packages/test_image_generation.py -q`

Expected: PASS and provider call count equals returned plan count.

- [ ] **Step 5: Obtain independent review and commit**

```bash
git add backend/app/domains/page_packages/blog_images.py \
  backend/app/domains/page_packages/image_generation.py \
  backend/tests/page_packages/test_blog_image_planner.py \
  backend/tests/page_packages/test_image_generation.py
git commit -m "feat: plan controlled blog images"
```

---

### Task 3: Preserve Or Invalidate Images When Text Changes

**Files:**
- Modify: `backend/app/domains/page_packages/blog_images.py`
- Modify: `backend/app/domains/page_packages/service.py`
- Modify: `backend/app/api/routes/page_packages.py`
- Create: `backend/tests/page_packages/test_blog_image_regeneration.py`

**Interfaces:**
- Produces: `section_meaning_fingerprint(heading: str, body: str) -> str`
- Produces: `reconcile_blog_image_approvals(session, old_proposal, new_proposal) -> None`
- Candidate approval state adds `needs_review`

- [ ] **Step 1: Write failing reconciliation tests**

```python
def test_small_text_edit_preserves_approved_image(session, approved_blog_image):
    regenerated = regenerate_section(approved_blog_image.proposal, body_suffix=" Extra zin.")
    reconcile_blog_image_approvals(session, approved_blog_image.proposal, regenerated)
    assert regenerated.image_candidate.approval_state == "approved"


def test_changed_heading_marks_neighbor_image_for_review(session, approved_blog_image):
    regenerated = regenerate_section(
        approved_blog_image.proposal, heading="Volledig ander onderwerp"
    )
    reconcile_blog_image_approvals(session, approved_blog_image.proposal, regenerated)
    assert regenerated.image_candidate.approval_state == "needs_review"
```

- [ ] **Step 2: Run focused regeneration tests**

Run: `cd backend && .venv/bin/python -m pytest tests/page_packages/test_blog_image_regeneration.py -q`

Expected: FAIL because image approvals are not reconciled.

- [ ] **Step 3: Implement a bounded semantic fingerprint**

Normalize the heading and the first 80 meaningful body words. Preserve approval when the heading is unchanged and at least 70 percent of normalized body terms overlap. Otherwise set only the neighboring image to `needs_review`; do not delete its candidates or invalidate unrelated slots.

- [ ] **Step 4: Run regeneration and page-package tests**

Run: `cd backend && .venv/bin/python -m pytest tests/page_packages/test_blog_image_regeneration.py tests/page_packages -q`

Expected: PASS.

- [ ] **Step 5: Obtain independent review and commit**

```bash
git add backend/app/domains/page_packages/blog_images.py \
  backend/app/domains/page_packages/service.py \
  backend/app/api/routes/page_packages.py \
  backend/tests/page_packages/test_blog_image_regeneration.py
git commit -m "feat: reconcile blog images after text changes"
```

---

### Task 4: Insert Native Image Blocks During Draft Creation

**Files:**
- Modify: `backend/app/domains/wordpress/draft_jobs.py`
- Modify: `backend/tests/wordpress/test_draft_job_service.py`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/interface-blueprint-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-acf-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-gutenberg-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-elementor-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-wpbakery-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-bricks-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- Modify: `plugin/wp-fixpilot-bridge/tests/image-import-test.php`
- Modify: `plugin/wp-fixpilot-bridge/tests/blog-image-anchor-test.php`
- Modify: `plugin/wp-fixpilot-bridge/tests/snapshot-draft-job-test.php`

**Interfaces:**
- Extends v2 image descriptor with `anchor_id` for additional blog images
- Adapter method: `insert_image_at_anchor(int $postId, array $anchor, int $attachmentId): bool|WP_Error`
- Required template image slots continue using their existing field paths

- [ ] **Step 1: Write failing draft-payload and PHP insertion tests**

```python
def test_v2_payload_contains_only_approved_blog_anchor_images(session, blog_proposal):
    payload = build_snapshot_draft_payload(blog_proposal)
    assert [item["anchor_id"] for item in payload["image_replacements"] if "anchor_id" in item] == [
        "anchor-process"
    ]
```

```php
$result = $adapter->insert_image_at_anchor(100, $anchor, 321);
assert($result === true);
assert($adapter->native_image_after('acf-content-2') === 321);
assert(strpos($adapter->rich_text_value(), '<img') === false);
```

- [ ] **Step 2: Run backend and plugin tests**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress/test_draft_job_service.py -q`

Run: `cd plugin/wp-fixpilot-bridge && docker run --rm -v "$PWD:/app" -w /app php:8.2-cli sh -lc 'php -d zend.assertions=1 -d assert.exception=1 tests/blog-image-anchor-test.php && php -d zend.assertions=1 -d assert.exception=1 tests/image-import-test.php && php -d zend.assertions=1 -d assert.exception=1 tests/snapshot-draft-job-test.php'`

Expected: FAIL because anchor descriptors are not applied.

- [ ] **Step 3: Apply approved anchors through adapters**

Validate every `anchor_id` against the immutable snapshot schema before media download. Import with the existing image importer, insert the builder-native image block/row/element, preserve neighboring IDs and ordering, then verify the attachment ID at the anchor. On any failure, use existing draft and orphan-attachment cleanup.

- [ ] **Step 4: Run all plugin and backend contract tests**

Run: `cd backend && .venv/bin/python -m pytest tests/wordpress tests/page_packages -q`

Run: `cd plugin/wp-fixpilot-bridge && docker run --rm -v "$PWD:/app" -w /app php:8.2-cli sh -lc 'for test in tests/*-test.php; do php -d zend.assertions=1 -d assert.exception=1 "$test" || exit 1; done; find . -name "*.php" -print0 | xargs -0 -n1 php -l'`

Expected: PASS with no rich-text image injection.

- [ ] **Step 5: Obtain independent review and commit**

Review unknown-anchor rejection, adapter structure preservation, ordering, idempotent replay, and cleanup.

```bash
git add backend/app/domains/wordpress/draft_jobs.py \
  backend/tests/wordpress/test_draft_job_service.py \
  plugin/wp-fixpilot-bridge/includes \
  plugin/wp-fixpilot-bridge/tests/image-import-test.php \
  plugin/wp-fixpilot-bridge/tests/blog-image-anchor-test.php \
  plugin/wp-fixpilot-bridge/tests/snapshot-draft-job-test.php
git commit -m "feat: insert approved blog images at safe anchors"
```

---

### Task 5: Show Additional Blog Images In Proposal Review

**Files:**
- Modify: `frontend/src/features/page-packages/ImageCandidateReview.tsx`
- Modify: `frontend/src/features/page-packages/ImageCandidateReview.test.tsx`
- Modify: `frontend/src/features/page-packages/PagePackageReview.tsx`
- Modify: `frontend/src/features/page-packages/PagePackageReview.test.tsx`
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Groups additional candidates by semantic section and anchor
- Reuses candidate select, regenerate, approve, reject, and signed preview actions
- Shows `Opnieuw beoordelen` for `needs_review`

- [ ] **Step 1: Write failing blog image review tests**

```tsx
it("groups additional images below their semantic sections", () => {
  render(<PagePackageReview proposal={blogProposalWithThreeImages} />);
  expect(screen.getByRole("heading", { name: "Proces: diagnose" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Kosten en garantie" })).toBeVisible();
  expect(screen.getAllByText("Extra afbeelding")).toHaveLength(3);
});

it("blocks draft creation while one changed section needs image review", () => {
  render(<PagePackageReview proposal={blogProposalNeedingImageReview} />);
  expect(screen.getByRole("button", { name: "WordPress-concept aanmaken" })).toBeDisabled();
  expect(screen.getByText("Opnieuw beoordelen")).toBeVisible();
});
```

- [ ] **Step 2: Run focused UI tests**

Run: `cd frontend && npm test -- ImageCandidateReview.test.tsx PagePackageReview.test.tsx`

Expected: FAIL because anchor grouping and `needs_review` are absent.

- [ ] **Step 3: Extend the existing image review component**

Render anchor candidates with the existing controls and shared instruction textarea. Do not create a separate blog editor. Keep stable dimensions and show zero additional-image controls when the planner returns none.

- [ ] **Step 4: Run frontend verification**

Run: `cd frontend && npm test -- --run && npm run lint && npm run build`

Expected: PASS.

- [ ] **Step 5: Obtain independent review and commit**

```bash
git add frontend/src/features/page-packages/ImageCandidateReview.tsx \
  frontend/src/features/page-packages/ImageCandidateReview.test.tsx \
  frontend/src/features/page-packages/PagePackageReview.tsx \
  frontend/src/features/page-packages/PagePackageReview.test.tsx \
  frontend/src/lib/api.ts
git commit -m "feat: review controlled blog images"
```

---

### Task 6: Release And Live Acceptance

**Files:**
- Modify: `docs/operations.md`
- Modify: `.superpowers/sdd/progress.md`

**Interfaces:**
- Produces release recovery instructions and staging evidence

- [ ] **Step 1: Run complete required verification**

Run: `cd backend && .venv/bin/ruff check app tests alembic && .venv/bin/python -m pytest --import-mode=importlib -q && .venv/bin/alembic upgrade head`

Run: `cd frontend && npm test -- --run && npm run lint && npm run build`

Run: `cd plugin/wp-fixpilot-bridge && docker run --rm -v "$PWD:/app" -w /app php:8.2-cli sh -lc 'for test in tests/*-test.php; do php -d zend.assertions=1 -d assert.exception=1 "$test" || exit 1; done; find . -name "*.php" -print0 | xargs -0 -n1 php -l'`

Expected: all commands pass.

- [ ] **Step 2: Deploy one tested release**

Deploy backend and frontend, then install the plugin package once after all local checks and independent review pass.

- [ ] **Step 3: Execute staging acceptance**

Create two blog proposals with different lengths. Confirm each has required featured/in-page images and zero through four additional images. Regenerate one candidate and choose between retained candidates. Change nearby text once without invalidation and once with a material heading change that sets `needs_review`. Create both drafts and verify native image blocks, no rich-text `<img>`, no duplicate attachments, and unchanged source pages.

- [ ] **Step 4: Force and recover one persisted-stage failure**

Fail one anchor insertion, confirm clone and new attachment cleanup, retry the same approved proposal, and verify one final draft with the same approved candidate identities.

- [ ] **Step 5: Obtain final independent review and commit**

```bash
git add docs/operations.md .superpowers/sdd/progress.md
git commit -m "chore: verify controlled blog image release"
git push origin feature/platform-build
```
