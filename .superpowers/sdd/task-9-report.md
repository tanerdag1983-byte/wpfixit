# Task 9 Release Report

Status: in progress

## Released

- Release commit: `d9eb2c0aab3179cf5ea5f338b0a6f6cb17e1bad3`
- GitHub branches: `main` and `feature/platform-build`
- GitHub Actions run: `28755474664`
- Frontend: `https://frontend-nine-jade-0t9k15bffs.vercel.app`
- Vercel deployment: `dpl_EyRpL7JdEE7X4uqGpL5zWYAP7KKM`
- Backend health: `https://wp-fixpilot-api.onrender.com/health`
- Plugin artifact: `artifacts/wp-fixpilot-bridge-0.3.1.zip`
- Plugin SHA-256: `110ed320a85dbe8933b13d449dab7f446faf41a772aec712fbca95cc7a9f81cc`

## Verification Evidence

- Backend: 218 tests passed, Ruff clean.
- PostgreSQL: clean migration reached `0017_managed_page_blueprints (head)`.
- PostgreSQL lifecycle race: passed against PostgreSQL 17.
- Python dependencies: no known vulnerabilities.
- Frontend: 26 files and 81 tests passed, lint/build clean.
- npm audit: zero vulnerabilities.
- Plugin: all six PHP contract suites passed; all PHP files syntax-clean on PHP 8.2.
- GitHub Actions: secrets, backend, frontend and plugin jobs passed.
- Live frontend bundle contains the Render API and Supabase project configuration and does not contain the localhost API fallback.
- Browser smoke test: login page, Google SSO, Microsoft SSO and magic-link controls render without console errors.
- Live Render OpenAPI exposes managed blueprint, version, default, validation, proposal approval and idempotent `create-draft` endpoints.

## Remaining Acceptance Gate

Task 9 is not complete until the versioned plugin is installed on the SHM staging
site and the source-to-draft acceptance flow from `task-9-brief.md` is executed.
There was no authenticated WordPress staging browser session available during
this release run. Record the generated WordPress draft edit URL here after the
acceptance flow, then mark Task 9 complete.
