# Task 7 Report

## Scope

Generate page proposals from an explicit page type and create reviewed WordPress drafts
from the immutable ready default blueprint for that project and type.

## RED Evidence

```text
.venv/bin/pytest -q tests/page_packages/test_proposal_routes.py -k requested_page_type
KeyError: 'blueprint'

.venv/bin/pytest -q tests/page_packages/test_proposal_routes.py
legacy proposal calls returned 422 and legacy edit/draft paths failed
```

## Implementation

- Added a required, allowlisted `page_type` proposal request.
- Selects only the project-local ready default blueprint for that exact page type.
- Snapshots blueprint ID, page type, version, hash, builder, and SEO plugin on proposals.
- Builds AI generation context from the immutable blueprint content schema.
- Fails queued generation cleanly if the blueprint is no longer ready.
- Validates generated and manually edited replacements against the captured schema.
- Rechecks live WordPress blueprint status/version/hash before approval and draft creation.
- Marks drifted blueprints stale, removes their default flag, and returns HTTP 409.
- Sends the bridge only replacements, SEO values, approved URLs, idempotency key,
  expected version, and expected structure hash.
- Uses `create_blueprint_draft()` and keeps repeated draft requests idempotent.
- Adds an explicit per-opportunity page-type selector to the frontend and disables
  generation until the user chooses a type.

## Verification

```text
backend: 214 passed
backend Ruff: clean
frontend: 26 files, 78 tests passed
frontend ESLint: clean
frontend production build: passed
PHP 8.2 blueprint lifecycle contract: passed
```

## Review Focus

- Project/page-type isolation of default blueprint selection.
- Proposal snapshot consistency across generation, approval, and draft creation.
- Stale detection and state transitions on WordPress drift.
- Exact bridge payload and idempotent repeated draft behavior.
- Frontend required page-type selection and request body.

## Review Adjudication

The review found that semantic-role edits can change `content_schema` without changing
the WordPress structure hash. This was accepted as an important snapshot-consistency
issue. Proposals now store the full schema and generation, approval, and draft creation
all reject a blueprint whose current schema differs from the proposal snapshot.

## Final Review

Approved after the schema-snapshot fix. No Critical or Important findings remain.
