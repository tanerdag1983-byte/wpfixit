# Task 4 Report

## Scope

Implemented the manager-only backend API for managed page blueprints and the
WordPress bridge client methods required by later generation tasks.

## Files

- Created `backend/app/api/routes/page_blueprints.py`
- Created `backend/tests/page_blueprints/conftest.py`
- Created `backend/tests/page_blueprints/test_routes.py`
- Modified `backend/app/domains/wordpress/client.py`
- Modified `backend/app/main.py`

## RED Evidence

Command:

```text
cd backend && .venv/bin/python -m pytest --import-mode=importlib tests/page_blueprints/test_routes.py -q
```

Observed failure before implementation:

```text
ImportError: cannot import name 'page_blueprints' from 'app.api.routes'
```

## Implementation

- Added project-scoped list, detail, capture, validate, metadata update, default,
  new-version, and delete routes.
- Restricted all mutations to organization owners and admins while allowing project
  members to inspect blueprints.
- Resolved reference pages by project before sending the numeric WordPress object ID
  to the bridge.
- Validated bridge content through `BlueprintSchema` before registry persistence.
- Removed invalid WordPress captures when schema validation or persistence fails.
- Restricted updates to name, page type, and semantic roles for existing block IDs.
- Marked live schema/hash drift as stale and removed stale blueprints as defaults.
- Created immutable successor rows and transferred the default only after a ready
  replacement had been captured and validated.
- Blocked deletion when proposals or successor versions still reference a blueprint,
  then removed the WordPress clone before deleting the backend registry row.
- Added signed WordPress client methods for blueprint capture, inspection, draft
  creation, and deletion.

## Verification

```text
cd backend && .venv/bin/ruff check app tests alembic
All checks passed!

cd backend && .venv/bin/python -m pytest --import-mode=importlib tests/page_blueprints -q
34 passed in 0.64s

cd backend && .venv/bin/python -m pytest --import-mode=importlib -q
183 passed in 8.25s

cd backend && .venv/bin/alembic upgrade head
PostgreSQL migration command exited 0 at head.
```

# Versioned Template Snapshots Release 1 - Task 4

## Outcome

Implemented the strict `snapshot-text-v1` field-ID-only generation contract from
base commit `7ee2e256e8be3350791351bf7d893b86e2367aeb`.

Commits:

- `18ff8d2` - `feat: generate snapshot text by field id`
- `192a8a6` - `fix: reject encoded snapshot markup`

## RED And GREEN

The existing generation/provider baseline was `34 passed`. After adding the
snapshot contract and provider regressions first, the focused command failed
during collection because `normalize_snapshot_text_package` and
`GeneratedSnapshotTextPackage` did not exist.

Additional focused RED cases proved that:

- URLs in rich-text tags removed by sanitization were initially not validated;
- encoded markup could initially reappear after entity decoding;
- nested entity encoding initially survived as encoded markup.

Each regression was observed failing before its production fix. Final focused
verification:

```text
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q \
  tests/page_packages/test_generation.py \
  tests/page_packages/test_provider_page_packages.py \
  tests/recommendations/test_openai_provider.py \
  tests/recommendations/test_openai_compatible_provider.py \
  tests/recommendations/test_anthropic_provider.py \
  tests/recommendations/test_gemini_provider.py

57 passed in 0.06s
```

## Invariants

- `snapshot-text-v1` accepts only top-level `text_replacements`.
- Snapshot providers never call legacy page-shape unwrap or field-ID repair.
- Plain text, headings, buttons, metadata, slugs, rich text, and URLs normalize
  according to their schema field type.
- Optional invalid fields produce local field errors without blocking otherwise
  complete required fields.
- Missing or invalid required fields block readiness.
- Unknown field IDs are ignored and reported with a 100-ID bound.
- `seo:focus_keyword` always uses the opportunity keyword.
- Slugs are validated after markup and entity normalization.
- Rich text uses a bounded allowlist, and URL attributes are checked before
  sanitization against approved URLs.
- Entity decoding reaches a bounded stable value before safety checks; values
  exceeding that bound fail locally as `unsafe_html`.
- Existing page-package, `blueprint-v1`, and all provider flows remain green.

## Changed Files

- `backend/app/domains/page_packages/schemas.py`
- `backend/app/domains/page_packages/generation.py`
- `backend/app/domains/recommendations/openai_compatible_provider.py`
- `backend/tests/page_packages/test_generation.py`
- `backend/tests/page_packages/test_provider_page_packages.py`
- `backend/tests/recommendations/test_openai_provider.py`
- `backend/tests/recommendations/test_openai_compatible_provider.py`
- `backend/tests/recommendations/test_anthropic_provider.py`
- `backend/tests/recommendations/test_gemini_provider.py`

OpenAI, Anthropic, and Gemini use the shared strict contract selection and parser
path. Only the OpenAI-compatible provider required a provider-specific production
branch to bypass its legacy unwrap/repair logic.

## Verification

```text
cd backend
.venv/bin/ruff check app tests alembic
All checks passed!

.venv/bin/python -m pytest --import-mode=importlib -q
348 passed, 4 skipped in 10.71s

.venv/bin/alembic upgrade head
PostgreSQL migration command exited 0 at head.
```

The four skips are the optional PostgreSQL concurrency suites requiring
`WP_FIXPILOT_POSTGRES_TEST_URL`; no Task 4 test was skipped.

## Independent Review

The first review found encoded markup could be reintroduced after plain-text tag
stripping. A rereview then found nested entity encoding was not yet canonical.
Both Important findings were fixed with RED regressions. Final independent
rereview of `18ff8d2..192a8a6` reported no findings and approved Task 4; its
focused generation run passed `21/21`.

## Remaining Concerns

No open Critical or Important findings. The only unexecuted checks are the four
environment-dependent PostgreSQL concurrency tests noted above; they are unrelated
to the pure generation/provider changes in this task.

## Third Review Adjudication

The third review found that WordPress may parse classic/WPBakery content as a nameless
Gutenberg freeform block, and that auxiliary ACF fields can coexist with a primary page
builder. This was accepted and fixed:

- Gutenberg detection now requires at least one real named Gutenberg block, including
  nested blocks; classic/freeform content no longer counts.
- Elementor, Bricks, and WPBakery are treated as primary builder structures; one primary
  match takes precedence over auxiliary ACF or Gutenberg content.
- ACF takes precedence over Gutenberg when no primary builder matches.
- Multiple matches at the same highest priority remain an explicit ambiguity conflict.
- Contract tests cover WPBakery versus Gutenberg and Elementor with auxiliary ACF.

All six PHP 8.2 plugin suites and PHP lint passed after these changes.

## Fourth Review Adjudication

The fourth review found two remaining lifecycle gaps, both accepted:

- A backend page-type edit now marks the current blueprint `stale`. Live validation
  compares the captured WordPress page type, and a fresh successor capture is required
  before the changed type can become ready.
- Delete now acquires a `SELECT ... FOR UPDATE` lock on the blueprint registry row
  before checking proposal and successor foreign-key dependencies. PostgreSQL therefore
  prevents a new referencing row from racing the remote WordPress deletion.

Final regression verification for this round:

```text
cd backend && .venv/bin/ruff check app tests alembic
All checks passed!

cd backend && .venv/bin/python -m pytest --import-mode=importlib tests/page_blueprints -q
45 passed in 1.24s

cd backend && .venv/bin/python -m pytest --import-mode=importlib -q
194 passed in 6.32s

cd backend && .venv/bin/alembic upgrade head
PostgreSQL migration command exited 0 at head.

Plugin PHP 8.2: all six suites and full PHP lint passed.
```

## Fifth Review Adjudication

The fifth review found that cleanup trusted the returned WordPress blueprint ID before
proving that it represented a newly created clone. This was accepted and fixed:

- `created` must be exactly `true` and the WordPress ID must be a positive integer.
- The project registry must not already contain that WordPress ID.
- Cleanup is armed only after both checks pass; malformed, reused, or non-created IDs
  are rejected without any remote delete call.
- The same guard protects initial capture and successor creation.

The requested PostgreSQL concurrency race test is assigned to the final migration and
end-to-end task. Task 4 already takes the required row lock; the release test must prove
that lock blocks concurrent proposal and successor insertion.

Verification after the trusted-capture fix:

```text
Blueprint tests: 49 passed in 1.22s
Full backend: 198 passed in 6.53s
Ruff: clean
Alembic PostgreSQL upgrade: clean
Plugin PHP 8.2: all six suites and full PHP lint passed
```

## Second Review Adjudication

The second review confirmed the six original findings were fixed, but rejected making
`builder` a client-controlled create field. This was accepted. The WordPress bridge now
detects exactly one active adapter from the selected reference page. Zero matches return
an unsupported-builder error and multiple matches return an ambiguity error before any
clone is created. The backend sends only the approved name, page type, reference page,
and version capture data, then validates the detected builder from WordPress against a
strict allowlist. A successor version must retain the original detected builder.

Final verification after the contract correction:

```text
Plugin PHP 8.2: blueprint, ACF adapter, shared adapter, auth, change controller,
and page-package suites all passed; all PHP files lint clean.

cd backend && .venv/bin/ruff check app tests alembic
All checks passed!

cd backend && .venv/bin/python -m pytest --import-mode=importlib tests/page_blueprints -q
43 passed in 0.87s

cd backend && .venv/bin/python -m pytest --import-mode=importlib -q
192 passed in 5.78s

cd backend && .venv/bin/alembic upgrade head
PostgreSQL migration command exited 0 at head.
```

## Review Focus

- Transaction boundaries around WordPress clone cleanup.
- Proposal and lineage dependency checks before deletion.
- Immutability of field IDs and builder paths during semantic-role updates.
- Correct default transfer after successful version capture.

## First Review Adjudication

The first independent review was not approved. All findings were accepted:

- Added the complete WordPress capture payload (`name`, `page_type`, `builder`, and
  `version`) and strict response identity validation.
- Preserved backend semantic-role overrides while comparing the immutable live schema.
- Added non-committing service modes so successor creation and default transfer commit
  atomically in the route.
- Made remote deletion retry-safe when WordPress reports that the clone is already
  absent after an earlier partial attempt.
- Validation now rejects non-ready status and mismatched WordPress ID, source page,
  version, builder, or SEO plugin.
- Default blueprints must be replaced as the default before their page type changes.
- Blueprint list and detail routes now enforce the same manager role as mutations.

Regression verification after fixes:

```text
cd backend && .venv/bin/ruff check app tests alembic
All checks passed!

cd backend && .venv/bin/python -m pytest --import-mode=importlib tests/page_blueprints -q
43 passed in 0.86s

cd backend && .venv/bin/python -m pytest --import-mode=importlib -q
192 passed in 6.07s

cd backend && .venv/bin/alembic upgrade head
PostgreSQL migration command exited 0 at head.
```
