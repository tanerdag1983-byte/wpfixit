# Versioned Template Snapshots Release 1 Report

Date: 2026-07-29
Status: complete
Commit range: `980b8c5..569b81e`

## Release Artifact

- Bridge version: `0.3.29`
- ZIP: `plugin/wp-fixpilot-bridge-release-1.zip`
- SHA-256: `029db6ff56edd2ed38b42b108e01f915769a0d020c30cf8dcdf829bb3df81636`
- ZIP contents: plugin root only; test files and `.DS_Store` excluded
- Installed once on staging and verified active
- Backend: `https://wp-fixpilot-api.onrender.com`
- Frontend: `https://frontend-nine-jade-0t9k15bffs.vercel.app`

## Verification

Backend:

```text
.venv/bin/ruff check app tests alembic
.venv/bin/python -m pytest --import-mode=importlib -q
.venv/bin/alembic upgrade head
```

Result: Ruff clean, 384 passed, 6 optional PostgreSQL skips, Alembic head
`0022_snapshot_draft_jobs`.

Frontend:

```text
npm test -- --run
npm run lint
npm run build
```

Result: 107 tests passed, lint clean, production build clean.

WordPress plugin:

```text
docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli \
  sh -lc 'for test in tests/*-test.php; do php -d zend.assertions=1 \
  -d assert.exception=1 "$test" || exit 1; done; find . -name "*.php" \
  -print0 | xargs -0 -n1 php -l'
```

Result: all 11 PHP suites passed and PHP lint was clean under PHP 8.2.

## Staging Migration

All five retained v1 templates have a ready native v2 snapshot:

| Page type | Blueprint ID | Snapshot post | Version | State |
| --- | --- | ---: | ---: | --- |
| service | `6fd1af59-c4a4-52e2-88d1-7d4e0e2ec142` | 12318 | 2 | ready |
| brand | `8218e6c3-7d50-58f6-9698-69a9c29721d6` | 12319 | 2 | ready |
| generic | `8eca34c1-5922-5a35-a31b-17f2dde8d283` | 12320 | 2 | ready |
| location | `f665603a-09a1-5cb3-8377-964f44e2b731` | 12321 | 2 | ready |
| blog | `de47d159-7841-5df2-a56b-032f4e2d65dd` | 12322 | 2 | ready |

Migration reported four direct conversions and one proposal requiring
regeneration. The resulting five v2 rows all report `ready`, capture state
`ready`, and migration state `native`.

The published source page `Transmissie onderhoud` was updated after capture.
The service snapshot remained version 2, adapter `0.3.29`, schema
`snapshot-text-v1`, 46 text fields, and ready after revalidation.

## Draft Acceptance

Two separate approved proposals per template were delivered through outbound
jobs. Every resulting WordPress object was independently opened and verified as
post type `page`, status `draft`, with the `SHM Page Blocks` structure present.

| Page type | Draft 1 | Draft 2 |
| --- | --- | --- |
| service | [12323](https://staging.shmtransmissie.nl/wp-admin/post.php?post=12323&action=edit) | [12325](https://staging.shmtransmissie.nl/wp-admin/post.php?post=12325&action=edit) |
| brand | [12327](https://staging.shmtransmissie.nl/wp-admin/post.php?post=12327&action=edit) | [12329](https://staging.shmtransmissie.nl/wp-admin/post.php?post=12329&action=edit) |
| generic | [12331](https://staging.shmtransmissie.nl/wp-admin/post.php?post=12331&action=edit) | [12333](https://staging.shmtransmissie.nl/wp-admin/post.php?post=12333&action=edit) |
| location | [12335](https://staging.shmtransmissie.nl/wp-admin/post.php?post=12335&action=edit) | [12337](https://staging.shmtransmissie.nl/wp-admin/post.php?post=12337&action=edit) |
| blog | [12339](https://staging.shmtransmissie.nl/wp-admin/post.php?post=12339&action=edit) | [12342](https://staging.shmtransmissie.nl/wp-admin/post.php?post=12342&action=edit) |

All ten jobs reached `completed`, used
`wordpress-snapshot-draft-job-v1`, and returned distinct WordPress edit URLs.
No manual plugin upload was required between drafts.

## Recovery Evidence

- Location proposal 1 generated an empty required slug. Only
  `document:slug` was corrected; validation resumed and the draft was created
  without another provider generation.
- Location proposal 2 generated a non-allowlisted hero CTA. Only that URL field
  was changed to the approved offer URL; validation resumed and the draft was
  created without another provider generation.
- Both blog proposals also required only a missing slug correction and resumed
  from validation.
- No incomplete or duplicate draft was observed. All ten final objects retained
  their captured ACF page-block structure.

## Completed-Job Replay

The production review UI now exposes `Conceptstatus opnieuw controleren` for a
completed draft job. The action reuses the authenticated idempotent
`POST .../draft-job` route and keeps a completed response in
`draft_created`.

The completed service proposal was replayed through that supported UI action.
Before and after the request, the WordPress edit URL remained
`post.php?post=12323&action=edit`; the job remained completed and the UI
confirmed the check. No new WordPress object was created.

## Independent Review

Independent release review approved the completed-job replay, verification
evidence, artifact checksum, and production deployment. No blocking bugs,
regressions, security findings, or important test gaps remained.

## Known Limitations

- Live acceptance covered the five retained ACF and Yoast template types on
  staging. Other registered builder adapters remain contract-tested but were
  not part of this five-template live matrix.
- Release 1 changes only schema-listed text and approved URLs. Snapshot media,
  layout, and styling remain immutable; image generation is not part of this
  release.
- Generated WordPress objects remain drafts. Publication is always a manual
  WordPress action.

## Rollback

- Keep the five v1 template registrations as the rollback source.
- Disable v2 defaults per page type if a snapshot-specific issue appears.
- Use the retained manual handoff path for draft creation.
- Reinstall the previous tested plugin ZIP only if bridge rollback is required.
- Never publish generated drafts automatically; WordPress publication remains a
  human action.
