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

## Review Focus

- Transaction boundaries around WordPress clone cleanup.
- Proposal and lineage dependency checks before deletion.
- Immutability of field IDs and builder paths during semantic-role updates.
- Correct default transfer after successful version capture.
