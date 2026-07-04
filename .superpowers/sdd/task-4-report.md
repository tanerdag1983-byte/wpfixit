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
