# Outbound WordPress Draft Jobs Release

Date: 2026-07-12
Branch: `feature/platform-build`
Plugin version: `0.3.19`
Plugin artifact: `/Users/tanerdag/Downloads/wp-fixpilot-bridge-update.zip`
Plugin SHA-256: `72697a43c3d470543e63f9e98da33b85713d9122cceca3eb47d777a2054f78cd`
Database revision: `0019_outbound_wp_draft_jobs`

## Local Verification

- Backend Ruff: passed.
- Backend tests: 274 passed, 3 skipped because `WP_FIXPILOT_POSTGRES_TEST_URL` was not configured.
- Alembic: PostgreSQL database reached revision `0019_outbound_wp_draft_jobs`.
- Frontend tests: 87 passed across 26 files.
- Frontend lint and production build: passed.
- WordPress plugin: all contract suites passed under PHP 8.2; PHP lint passed.
- ZIP inspection: contains the plugin directory and production PHP files only; tests, Git files, `.DS_Store`, logs, and local secrets are excluded.

## Release Commits

- Persistence: `831407c..0d570e8`
- Lifecycle: `66189d9`
- API: `7ab28b1`
- WordPress processor: `64952fa`
- WordPress controls: `0accc1a`
- Dashboard UI: `617e5ea`

## Live Acceptance

Pending deployment and staging smoke test. Record the production frontend and backend deployment URLs, WordPress draft ID and edit URL, duplicate-retry result, published-page count, and key-rotation result here before closing Task 7.
