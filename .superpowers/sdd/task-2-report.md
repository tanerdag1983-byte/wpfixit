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

## Review adjudication
- Deferred by explicit task boundary: production registration of the five real adapters is Task 3; Task 2 deliberately proves the controller through an injected fake adapter.
- Accepted: read and create_draft must recalculate the live schema/structure hash through the selected adapter so edited managed blueprints are detected before a draft clone is used.
- Deferred by ownership boundary: proposal dependency checks live in the backend Task 4 delete route, because the WordPress bridge has no proposal registry. The bridge delete endpoint remains a low-level authenticated operation called only after backend validation.
- Accepted test gap: add cleanup tests for capture schema failure and post-clone replacement/SEO failures.

## Task 2 Continuation (Accepted Fixes)

### Files

- Modified `plugin/wp-fixpilot-bridge/tests/blueprint-test.php`
- Modified `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- Modified `.superpowers/sdd/task-2-report.md`

### RED / GREEN Evidence

- RED
  - Command: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php`
  - Result:

    ```text
    Fatal error: Uncaught AssertionError: assert($staleRead['structure_hash'] !== $captured['structure_hash']) in /app/tests/blueprint-test.php:452
    ```

- GREEN
  - Command: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php`
  - Result: PASS `blueprint lifecycle tests passed`
  - Command: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/auth-test.php`
  - Result: PASS `auth tests passed`
  - Command: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/change-controller-test.php`
  - Result: PASS `change controller tests passed`
  - Command: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/page-package-test.php`
  - Result: PASS `page package adapter tests passed`
  - Command: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli sh -lc "find . -name '*.php' -print0 | xargs -0 -n1 php -l"`
  - Result: PASS all plugin PHP files lint clean

### Fix Summary

- Added a stale-blueprint regression that edits the managed blueprint after capture and proves `read()` returns the live schema/hash from the configured adapter while stored capture meta remains unchanged.
- Added cleanup regressions for:
  - capture clone deletion when adapter schema extraction fails;
  - draft clone deletion when adapter replacement application fails;
  - draft clone deletion when SEO meta writing throws after clone.
- Updated `WPFixPilot_Blueprint_Controller` so `read()` and `create_draft()` resolve the stored builder adapter and inspect the current blueprint schema/hash before validating replacements or cloning drafts.

### Commit

- `HEAD` commit: `fix: tighten blueprint stale-state handling`

### Concerns

- No new scope concerns beyond the accepted Task 3 adapter-registration boundary and Task 4 backend dependency checks.
