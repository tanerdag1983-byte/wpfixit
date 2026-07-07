# Task 1 Report: Immutable Proposal Versions And Handoff Persistence

## Scope

Task 1 ownership was limited to finalizing backend persistence foundations for immutable page proposal versions and manual WordPress handoffs in the existing `feature/platform-build` worktree, while preserving unrelated in-progress edits.

## Starting Point Reviewed

I began from the existing uncommitted work in:

- `backend/app/domains/page_packages/models.py`
- `backend/alembic/versions/0018_page_proposal_versions_and_handoffs.py`
- `backend/app/domains/page_packages/service.py`
- `backend/tests/page_packages/test_proposal_versions.py`
- `backend/tests/page_packages/test_handoffs.py`
- `backend/app/api/routes/page_packages.py`
- `backend/tests/page_blueprints/test_models.py`
- `backend/tests/page_blueprints/test_postgres_concurrency.py`
- `backend/tests/page_blueprints/test_routes.py`

I also checked the task brief at `.superpowers/sdd/task-1-page-handoff-brief.md`, the approved design, and the implementation plan to confirm scope boundaries.

## Findings

The existing Task 1 persistence slice was already in a green state when I picked it up:

- proposal-version lineage fields were present on `PagePackageProposal`;
- `PagePackageRegenerationCandidate` and `PagePackageHandoff` models existed;
- the Alembic migration backfilled `proposal_group_id` and created the new tables;
- compatibility call sites and tests had already been updated for the new non-null fields;
- focused persistence tests for version acceptance and hashed handoff storage already passed.

I did not find an additional Task 1 code correction that was required to satisfy the brief or to keep the backend suite green. Because the worktree was already in this state, I did not make production code changes beyond writing this report and creating the final commit.

## RED/GREEN Evidence

The task asked for focused RED/GREEN evidence if still available from the current changes.

- RED: not reproducible honestly from the current starting point. The focused tests were already passing before any new edits in this finishing pass.
- GREEN: verified by rerunning the focused persistence tests successfully.

## Verification Run

All commands were run fresh from `/Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build/backend`.

1. `ruff check app tests alembic`
   - Result: pass

2. `python -m pytest --import-mode=importlib tests/page_packages/test_proposal_versions.py tests/page_packages/test_handoffs.py -q`
   - Result: pass (`2 passed`)

3. `alembic upgrade head`
   - Result: pass on PostgreSQL

4. `python -m pytest --import-mode=importlib -q`
   - Result: pass (`221 passed, 1 skipped`)
   - Skip reason: `tests/page_blueprints/test_postgres_concurrency.py` requires `WP_FIXPILOT_POSTGRES_TEST_URL`

## Task 1 Scope Notes

Two supporting areas outside the exact Task 1 file list were already part of the in-progress worktree and were kept because they are necessary compatibility adjustments for the new persistence fields:

- `backend/app/api/routes/page_packages.py` initializes `proposal_group_id` for newly created proposals.
- the `backend/tests/page_blueprints/*` updates supply `proposal_group_id` where legacy fixtures create `PagePackageProposal` rows directly.

I kept those changes intact and did not revert or extend them.

## Concerns

No blocking Task 1 concern remains from the backend verification pass.

The only limitation is evidence-related: I cannot claim a fresh RED step for this finishing pass because the carried-over focused tests were already green at pickup time.

## Follow-up Fix Pass: Review Findings On d2aaacb

### What I changed

1. Exactly-one-current invariant and `current_version_id`
   - Added `current_version_id` to `PagePackageProposal` and backfilled it in the Task 1 Alembic migration.
   - Enforced pointer consistency with `ck_page_package_proposals_current_pointer_matches_flag`.
   - Added a partial unique index so each `proposal_group_id` can have only one row with `is_current = true`.
   - Updated proposal creation and legacy test fixtures so new and direct-created proposals initialize `current_version_id` to their own id.
   - Fixed `accept_regeneration_candidate()` to generate the next version id first, repoint the whole proposal group to that id, clear the old current flag, and then persist the new current version in one transaction.

2. Handoff issuance authorization contract
   - Tightened `issue_page_package_handoff()` so it now verifies the actor is an organization `owner` or `admin` for the proposal’s project before issuing a code.
   - Updated tests so the happy path uses a real owner and the refusal path exercises a same-organization `member` without normalizing that actor as acceptable.

3. Truthful generation provenance for accepted regenerated versions
   - Extended `PagePackageRegenerationCandidate` persistence with `provider`, `model`, `prompt_version`, `input_tokens`, and `output_tokens`.
   - Updated accepted-regeneration persistence so the new proposal version copies provenance from the accepted candidate, not stale metadata from the previous current version.

### Commands run and outputs summary

1. `cd backend && .venv/bin/python -m pytest --import-mode=importlib tests/page_packages/test_proposal_versions.py tests/page_packages/test_handoffs.py -q`
   - RED before fixes: `3 failed`
   - GREEN after fixes: `3 passed in 0.10s`

2. `cd backend && .venv/bin/ruff check app tests alembic`
   - First rerun caught one import-order error in `tests/page_packages/test_handoffs.py`
   - Final rerun: `All checks passed!`

3. `cd backend && .venv/bin/python -m pytest --import-mode=importlib -q`
   - Result: `222 passed, 1 skipped in 6.66s`
   - Skip reason: `tests/page_blueprints/test_postgres_concurrency.py` requires `WP_FIXPILOT_POSTGRES_TEST_URL`

### Residual concerns

- No blocking Task 1 persistence concern remains from this review-fix slice.
- `current_version_id` is enforced by the row-level check plus the partial unique current-row index; it is not a self-referential foreign key, which avoids cyclic flush problems during current-version transitions while still preserving the Task 1 interface and invariant.
