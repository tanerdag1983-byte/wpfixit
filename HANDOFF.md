# WP FixPilot Handoff

Updated: 2026-07-05

## Resume Here

Repository: `wp-fixpilot-new`

Active branch: `feature/platform-build`

Active worktree: `.worktrees/platform-build`

Read these first:

1. `AGENTS.md`
2. `.superpowers/sdd/progress.md`
3. `.superpowers/sdd/task-9-brief.md`
4. `.superpowers/sdd/task-8-report.md`
5. `docs/superpowers/specs/2026-06-27-managed-page-blueprints-design.md`
6. `docs/superpowers/plans/2026-06-28-managed-page-blueprints.md`
7. `docs/superpowers/specs/2026-06-30-content-operations-intelligence-design.md`

## Current Status

### Task 1: Complete And Approved

Immutable backend blueprint persistence is implemented and independently approved.

Implemented guarantees include:

- project/source ownership constraints;
- exact proposal-to-blueprint ID/version/hash relationship;
- immutable one-successor version lineages;
- project-local lineage links;
- lifecycle states `capture_required`, `capturing`, `ready`, `stale`, `invalid`;
- ready-only defaults;
- deterministic Alembic migration without runtime imports;
- PostgreSQL migration verification.

Commits: `721dd07..87fd133`

### Task 2: Complete And Approved

Task 2 implements the generic WordPress managed-blueprint lifecycle:

- safe cloning to normal draft pages with verified metadata writes;
- allowlisted metadata copying (excludes FixPilot ownership/idempotency keys);
- authenticated blueprint REST endpoints (`POST /blueprints`, `GET /blueprints/{id}`, `POST /blueprints/{id}/drafts`, `DELETE /blueprints/{id}`);
- source and blueprint immutability (read-only during capture/draft creation);
- live schema/hash drift detection (409 on structure mismatch);
- strict backend-compatible schema validation (required fields, max lengths enforced);
- SEO-plugin snapshot and drift checks;
- exact ID/version/hash/request-payload idempotency ownership (409 on changed content with same key);
- deterministic request hash (SHA-256 over canonicalized replacements + SEO payload);
- truthful 201/200 creation/reuse semantics;
- verified cleanup after clone, metadata, builder, and SEO write failures;
- verified `wp_delete_post()` via `get_post()` re-check for all cleanup paths;
- canonical signed REST route handling;
- managed-blueprint inventory exclusion (blueprints hidden from page lists);
- bridge version `0.3.0`.

Commits: `87fd133..d5e8279`

**Final review conclusion:** All 10 critical areas verified (atomicity, required fields, payload/schema validation, metadata persistence, delete verification, request hash idempotency, auth, drift, HTTP semantics, source immutability). All PHP 8.2 plugin tests PASS. Ready for Task 3.

## Remaining Managed-Blueprint Tasks

1. Task 6: schema-bound AI generation using the selected project blueprint.
2. Task 7: approved, idempotent WordPress draft creation and publication review flow.
3. Task 8: complete blueprint review in the frontend.
4. Task 9: migration, integration/E2E coverage, release, GitHub push, Render/Vercel deployment, plugin package, and live smoke
   tests.
5. Roadmap Task 10: Project Brand DNA, using
   `docs/superpowers/plans/2026-06-30-project-brand-dna.md`.
6. Roadmap Tasks 11 onward: Link Intelligence, Content Studio and SEO scoring, Image
    Studio, Content Calendar, and the GSC/GA4/PageSpeed Impact Timeline. Each receives a
    separate spec and implementation plan after Task 10.

## Live-First Product Sequence

The user wants the managed-blueprint workflow live before adding more product features.
After Task 9 has been deployed and verified, continue with the preserved roadmap:

- DataForSEO;
- configurable AI providers/models and per-project prompts;
- Google Search Console;
- GA4;
- sitemap import and URL discovery;
- internal-link analysis and approved updates;
- external-link validation and recommendations;
- PageSpeed/CrUX;
- Yoast, Rank Math, and All in One SEO;
- combined SEO priority engine and dashboards.

These items are required future product phases, not optional ideas.

The detailed approved architecture, calendar safeguards, project Brand DNA, rewrite
versioning, image styles, SEO score card, PageSpeed schedule, and one-year GSC/GA4 impact
timeline are specified in
`docs/superpowers/specs/2026-06-30-content-operations-intelligence-design.md`.

The first post-launch implementation plan is
`docs/superpowers/plans/2026-06-30-project-brand-dna.md`. Execute it only after the
managed-blueprint Task 9 deployment and smoke tests are complete.

## Deployment Context

- Frontend: Vercel.
- Backend: Render.
- Database/authentication: Supabase.
- Source control: GitHub repository `tanerdag1983-byte/wpfixit`.
- WordPress bridge is installed on the staging WordPress site.

Do not include credentials in this file or commits. Confirm environment variables in
their deployment platforms. Any credential pasted into chat or screenshots should be
treated as exposed and rotated before production launch.

## Important Decisions

- Human review is mandatory before creating the final WordPress draft.
- WordPress publishing remains manual.
- Multiple blueprints exist per project and page type; one ready default per type.
- Existing pages may be used as reference pages even when they are not formal WordPress
  templates.
- Full builder-native structure is cloned; AI receives only editable text/link fields.
- Builder-specific behavior belongs behind the shared adapter contract.
- Official Google SEO changes may be activated automatically only with a short dashboard
  update and optional email notification when enabled by the user.
