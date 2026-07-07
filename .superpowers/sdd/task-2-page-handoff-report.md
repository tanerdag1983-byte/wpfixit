# Task 2 Report: Backend Version, Regeneration, Approval, And Handoff APIs

Status: complete

Base commit: `ffb26084d7c3f0ea44177f7df00a16228d817683`

## What changed

- Added focused backend route coverage for:
  - `POST /page-proposals/{id}/regenerate`
  - `POST /page-proposals/candidates/{id}/accept`
  - `POST /page-proposals/{id}/handoffs`
  - `POST /page-proposals/handoffs/redeem`
  - `POST /page-proposals/handoffs/{id}/complete`
  - `POST /page-proposals/handoffs/{id}/revoke`
- Added request schemas for regeneration, redeem, and complete payloads.
- Added backend lifecycle helpers for:
  - creating and discarding regeneration candidates
  - accepting a candidate while collecting revoked handoff ids
  - issuing, redeeming, completing, and revoking handoffs
  - building import URLs and plugin import payloads
- Added plugin-signature verification for the plugin-facing redeem and complete endpoints using the existing shared bridge secret.
- Extended proposal payloads to expose version metadata needed by the new lifecycle responses.
- Kept the existing page-package settings routes and managed-blueprint draft route in place.

## TDD record

1. Fixed the handoff test harness so the new tests fail on missing Task 2 behavior instead of fixture/setup mistakes.
2. Ran the required RED command:

```bash
cd /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build/backend && .venv/bin/python -m pytest --import-mode=importlib tests/page_packages/test_proposal_versions.py tests/page_packages/test_handoffs.py -q
```

Observed RED failures:
- missing regenerate route
- missing candidate accept route
- missing handoff issue/redeem/complete/revoke routes

3. Implemented the minimal backend production changes in the task-owned files.
4. Ran the focused GREEN command:

```bash
cd /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build/backend && .venv/bin/ruff check app tests alembic && .venv/bin/python -m pytest --import-mode=importlib tests/page_packages/test_proposal_versions.py tests/page_packages/test_handoffs.py -q
```

Result:
- Ruff clean
- `7 passed in 0.25s`

## Changed files

- `backend/app/domains/page_packages/service.py`
- `backend/app/domains/page_packages/schemas.py`
- `backend/app/domains/page_packages/generation.py`
- `backend/app/api/routes/page_packages.py`
- `backend/tests/page_packages/test_proposal_versions.py`
- `backend/tests/page_packages/test_handoffs.py`

## Notes / concerns

- This task intentionally stayed inside the backend Task 2 scope. Frontend and plugin implementation work was not touched.
- The existing `POST /page-proposals/{proposal_id}/create-draft` route remains present for compatibility, per the repo constraints, while the new manual-handoff primitives are now available alongside it.
