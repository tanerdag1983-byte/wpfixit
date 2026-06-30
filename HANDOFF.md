# WP FixPilot Handoff

Updated: 2026-06-30

## Resume Here

Repository: `wp-fixpilot-new`

Active branch: `feature/platform-build`

Active worktree: `.worktrees/platform-build`

Read these first:

1. `AGENTS.md`
2. `.superpowers/sdd/progress.md`
3. `.superpowers/sdd/task-2-brief.md`
4. `.superpowers/sdd/task-2-report.md`
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

Ledger entry: `.superpowers/sdd/progress.md`.

### Task 2: Implementation Complete, Final Review Still Required

Task 2 implements the generic WordPress managed-blueprint lifecycle:

- safe cloning to normal draft pages;
- allowlisted metadata copying;
- authenticated blueprint REST endpoints;
- source and blueprint immutability;
- live schema/hash drift detection;
- strict backend-compatible schema validation;
- SEO-plugin snapshot and drift checks;
- exact ID/version/hash idempotency ownership;
- truthful 201/200 creation/reuse semantics;
- cleanup after clone, metadata, builder, and SEO failures;
- canonical signed REST route handling;
- managed-blueprint inventory exclusion;
- bridge version `0.3.0`.

Latest Task 2 commit: `3484de7` (`fix: close blueprint clone and payload validation gaps`).

The latest fix added:

- atomic failure handling for `add_post_meta()` and blueprint marker writes;
- strict `expected_version` and `expected_structure_hash` validation;
- schema-aware string replacement validation, required values, and max lengths;
- strict SEO payload validation;
- regressions for malformed/nested payloads and metadata-write failures.

All reported PHP 8.2 plugin tests and lint passed after that commit. Do not mark Task 2
complete yet: generate a fresh review package from Task 2 base `87fd133` to `HEAD`, run
an independent task review, fix any concrete findings, and only then update the ledger.

Suggested next commands:

```bash
git status --short
git log --oneline -12
/Users/tanerdag/.codex/plugins/cache/claude-plugins-official/superpowers/6.0.3/skills/subagent-driven-development/scripts/review-package 87fd133 HEAD
```

## Remaining Managed-Blueprint Tasks

1. Finish and approve Task 2.
2. Task 3: implement and register ACF, Elementor, WPBakery, Bricks, and Gutenberg
   adapters with shared contract fixtures.
3. Task 4: backend manager-only blueprint CRUD/validate/default/version/delete API.
4. Task 5: project blueprint management UI and semantic block outline.
5. Task 6: schema-bound AI generation using the selected project blueprint.
6. Task 7: approved, idempotent WordPress draft creation and publication review flow.
7. Task 8: legacy page-package migration plus integration and end-to-end tests.
8. Task 9: release, GitHub push, Render/Vercel deployment, plugin package, and live smoke
   tests.

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
