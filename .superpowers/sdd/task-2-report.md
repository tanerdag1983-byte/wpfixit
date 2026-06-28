# Task 2 Report

## Scope

Implemented Task 2 in `plugin/wp-fixpilot-bridge` for managed WordPress blueprint capture and lifecycle operations, while preserving the existing page-package routes and tests.

## Files

- Created `plugin/wp-fixpilot-bridge/includes/builder-adapters/interface-blueprint-adapter.php`
- Created `plugin/wp-fixpilot-bridge/includes/class-post-cloner.php`
- Created `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- Created `plugin/wp-fixpilot-bridge/tests/blueprint-test.php`
- Modified `plugin/wp-fixpilot-bridge/includes/class-rest-controller.php`
- Modified `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`

## RED Evidence

Focused lifecycle command before implementation:

```text
docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php
```

Observed failure:

```text
Warning: require_once(/app/tests/../includes/builder-adapters/interface-blueprint-adapter.php): Failed to open stream: No such file or directory
Fatal error: Uncaught Error: Failed opening required '/app/tests/../includes/builder-adapters/interface-blueprint-adapter.php'
```

## Implementation

- Added the shared `WPFixPilot_Blueprint_Adapter` contract for Task 2 controller integration and Task 3 follow-on work.
- Added `WPFixPilot_Post_Cloner` to clone draft pages without mutating the source and with strict meta allowlisting.
- Added `WPFixPilot_Blueprint_Controller` with `capture()`, `read()`, `create_draft()`, and `delete()`.
- Enforced:
  - draft-only managed blueprints
  - idempotent draft creation
  - version/hash conflict checks
  - unknown replacement rejection
  - partial draft cleanup on write failure
  - SEO metadata writes through the existing SEO adapter contract
- Registered authenticated REST lifecycle routes:
  - `POST /blueprints`
  - `GET /blueprints/{id}`
  - `POST /blueprints/{id}/drafts`
  - `DELETE /blueprints/{id}`
- Kept existing page-package routes operational.
- Bumped bridge plugin version to `0.3.0`.
- Excluded managed blueprint pages from normal bridge inventory.

## Commands And Results

- `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php`
  - PASS: `blueprint lifecycle tests passed`
- `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/auth-test.php`
  - PASS: `auth tests passed`
- `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/change-controller-test.php`
  - PASS: `change controller tests passed`
- `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/page-package-test.php`
  - PASS: `page package adapter tests passed`
- `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli sh -lc "find . -name '*.php' -print0 | xargs -0 -n1 php -l"`
  - PASS: all plugin PHP files lint clean

## Concerns

- The lifecycle is intentionally wired to fake adapters only for now; real builder adapters remain Task 3 work.
- `create_draft()` currently applies the blueprint page title to the cloned draft because Task 2 does not yet define title replacement behavior outside adapter-managed content fields.

## Commit Hash

- Task 2 code commit: `dfe61d2` (`feat: capture managed wordpress blueprints`)
