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

## Second review adjudication
- Accepted: idempotent retries must not bypass blueprint existence, expected version, live structure hash, or field-schema validation. Move the existing-draft lookup after those checks and ensure an existing key belongs to the requested blueprint.
- Task boundary retained: the REST controller already supports injecting a blueprint controller; production registration of the five concrete adapters is Task 3. Add an executable REST-controller integration test with the injected fake adapter so route callbacks and authorization wiring are covered now.

## Task 2 Continuation 2 (Accepted Fixes)

### Files

- Modified `plugin/wp-fixpilot-bridge/tests/blueprint-test.php`
- Modified `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- Modified `.superpowers/sdd/task-2-report.md`

### RED / GREEN Evidence

- RED
  - Command: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php`
  - Result:

    ```text
    Fatal error: Uncaught AssertionError: assert(is_wp_error($mismatchedVersionRetry)) in /app/tests/blueprint-test.php:442
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

- Added RED coverage proving an existing idempotency key cannot bypass:
  - expected blueprint version checks;
  - expected live structure hash checks;
  - unknown replacement-field validation.
- Added a cross-blueprint reuse regression proving an idempotency key bound to one blueprint is rejected for another blueprint with HTTP 409 semantics.
- Added an executable REST-controller regression that:
  - constructs `WPFixPilot_REST_Controller` with an injected fake-adapter blueprint controller;
  - asserts the registered `/blueprints` permission callback is `authorize`;
  - executes the registered capture callback and verifies it returns HTTP 201;
  - exercises invalid signed authorization on the blueprint endpoint and expects `wp_fixpilot_forbidden`.
- Updated `WPFixPilot_Blueprint_Controller::create_draft()` so the idempotency lookup runs only after blueprint existence, expected version, live hash, and schema/replacement validation, and only reuses an existing draft when it belongs to the requested blueprint.

### Concerns

- No new scope concerns beyond the retained Task 3 adapter-registration boundary.

## Final lifecycle review adjudication
- Accepted: idempotent draft records must store and match blueprint ID, version, and structure hash before reuse.
- Accepted: managed blueprint operations require the WordPress page itself to remain post_status=draft.
- Accepted: capture validates schema shape and a non-empty structure hash before persisting ready metadata; invalid clones are deleted.
- Accepted: idempotent reuse reports the existing WordPress object's real status rather than hardcoding draft.

## Task 2 Continuation 3 (Accepted Final Lifecycle Fixes)

### Files

- Modified `plugin/wp-fixpilot-bridge/tests/blueprint-test.php`
- Modified `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- Modified `.superpowers/sdd/task-2-report.md`

### RED / GREEN Evidence

- RED
  - Command: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php`
  - Result:

    ```text
    Fatal error: Uncaught AssertionError: assert((string)get_post_meta($draft['wordpress_object_id'], '_wp_fixpilot_blueprint_structure_hash', true) === $captured['structure_hash']) in /app/tests/blueprint-test.php:452
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

- Stored the validated blueprint snapshot on generated drafts by persisting:
  - source blueprint ID;
  - blueprint version;
  - blueprint structure hash.
- Tightened idempotent reuse so the existing draft is reused only when its stored blueprint ID, version, and structure hash match the current validated snapshot; mismatches now return HTTP 409 instead of stale content.
- Enforced draft-only managed blueprint operations across `read()`, `create_draft()`, and `delete()` by rejecting marked blueprints whose live WordPress `post_status` is no longer `draft`.
- Validated adapter capture output before returning `ready`:
  - schema version must be `blueprint-v1`;
  - blocks must be non-empty;
  - every block must expose non-empty field IDs and field paths;
  - structure hash must be non-empty.
- Deleted invalid blueprint clones when capture output fails contract validation.
- Updated draft responses to derive the live WordPress object status safely, so idempotent reuse after manual publish reports `publish` and does not create a duplicate.

### Concerns

- No new scope concerns beyond the retained Task 3 real-adapter registration boundary and the existing backend ownership of proposal dependency checks.

### Commit

- `HEAD` at commit time: `fix: finalize task 2 blueprint lifecycle`

## Authentication-boundary review adjudication
- Accepted: make WPFixPilot_Auth an explicit injectable REST-controller dependency. Keep the public authorize permission callback for backward-compatible WordPress route registration, but delegate verification to the injected authenticator instead of constructing it inside each request.

## Task 2 Continuation 4 (Accepted API Contract Fixes)

### Files

- Modified `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- Modified `plugin/wp-fixpilot-bridge/includes/class-rest-controller.php`
- Modified `plugin/wp-fixpilot-bridge/tests/blueprint-test.php`

### RED / GREEN Evidence

- RED
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build:/app -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 plugin/wp-fixpilot-bridge/tests/blueprint-test.php`
  - Result:

    ```text
    Fatal error: Uncaught AssertionError: assert(false, 'whitespace name')
    ```

- GREEN
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build:/app -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 plugin/wp-fixpilot-bridge/tests/blueprint-test.php`
  - Result: PASS `blueprint lifecycle tests passed`
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build:/app -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 plugin/wp-fixpilot-bridge/tests/auth-test.php`
  - Result: PASS `auth tests passed`
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build:/app -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 plugin/wp-fixpilot-bridge/tests/change-controller-test.php`
  - Result: PASS `change controller tests passed`
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build:/app -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 plugin/wp-fixpilot-bridge/tests/page-package-test.php`
  - Result: PASS `page package adapter tests passed`
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build:/app -w /app php:8.2-cli sh -lc "find plugin/wp-fixpilot-bridge -name '*.php' -print0 | xargs -0 -n1 php -l"`
  - Result: PASS all plugin PHP files lint clean

### Fix Summary

- Validated blueprint capture inputs after sanitization so:
  - `name` must remain non-empty after trimming;
  - `page_type` must be one of the supported blueprint types after `sanitize_key()`;
  - `version` must be a positive integer;
  - `builder` must remain a non-empty sanitized key.
- Added controller and REST regressions for whitespace-only names and unsupported page types.
- Added a `created` flag to blueprint draft responses so the controller can distinguish a freshly cloned draft from an idempotent reuse without changing existing response fields.
- Updated the blueprint draft REST route to return HTTP 201 for new drafts and HTTP 200 for idempotent replays.
- Expanded the lifecycle test to prove the first POST creates a draft, the replay reuses the same WordPress object, and the inventory does not duplicate the draft.

## Task 2 Continuation 4 (Authentication-Boundary Fix)

### Files

- Modified `plugin/wp-fixpilot-bridge/includes/class-rest-controller.php`
- Modified `plugin/wp-fixpilot-bridge/tests/blueprint-test.php`
- Modified `.superpowers/sdd/task-2-report.md`

### RED / GREEN Evidence

- RED
  - Command: `docker run --rm -v /tmp/wp-fixpilot-auth-red/plugin/wp-fixpilot-bridge:/app -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 -r 'final class WP_Error { public function __construct(public string $code, public string $message, public array $data = []) {} } final class WP_REST_Request { public function __construct(private string $method, private string $route, private array $headers = [], private string $body = "") {} public function get_method(): string { return $this->method; } public function get_route(): string { return $this->route; } public function get_header(string $key): string { return (string) ($this->headers[$key] ?? ""); } public function get_body(): string { return $this->body; } } final class WPFixPilot_Page_Package_Controller {} final class WPFixPilot_Blueprint_Controller {} final class WPFixPilot_Auth { public function __construct(private string $secret, private ?Closure $clock = null, private int $maxAge = 300) {} public static function sign(string $secret, string $method, string $route, string $timestamp, string $nonce, string $body): string { return hash_hmac("sha256", implode("\\n", [strtoupper($method), $route, $timestamp, $nonce, hash("sha256", $body)]), $secret); } public function verify(string $method, string $route, string $timestamp, string $nonce, string $body, string $signature): bool { return hash_equals(self::sign($this->secret, $method, $route, $timestamp, $nonce, $body), $signature); } } function get_option(string $key, mixed $default = false): mixed { return $key === "wp_fixpilot_secret" ? "test-secret" : $default; } function get_transient(string $key): mixed { return false; } function set_transient(string $key, mixed $value, int $expiration): void {} require_once "includes/class-rest-controller.php"; $auth = new WPFixPilot_Auth("injected-secret", static fn (): int => 1710000000); $controller = new WPFixPilot_REST_Controller(null, new WPFixPilot_Blueprint_Controller(), $auth); $route = "/wp-json/wpfixpilot/v1/blueprints"; $body = "{}"; $timestamp = "1710000000"; $nonce = "nonce-1"; $signature = WPFixPilot_Auth::sign("injected-secret", "POST", $route, $timestamp, $nonce, $body); $request = new WP_REST_Request("POST", $route, ["x-wp-fixpilot-timestamp" => $timestamp, "x-wp-fixpilot-nonce" => $nonce, "x-wp-fixpilot-signature" => $signature], $body); assert($controller->authorize($request) === true);'`
  - Result:

    ```text
    Fatal error: Uncaught AssertionError: assert($controller->authorize($request) === true) in Command line code:1
    ```

- GREEN
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build/plugin/wp-fixpilot-bridge:/app -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 -r 'final class WP_Error { public function __construct(public string $code, public string $message, public array $data = []) {} } final class WP_REST_Request { public function __construct(private string $method, private string $route, private array $headers = [], private string $body = "") {} public function get_method(): string { return $this->method; } public function get_route(): string { return $this->route; } public function get_header(string $key): string { return (string) ($this->headers[$key] ?? ""); } public function get_body(): string { return $this->body; } } final class WPFixPilot_Page_Package_Controller {} final class WPFixPilot_Blueprint_Controller {} final class WPFixPilot_Auth { public function __construct(private string $secret, private ?Closure $clock = null, private int $maxAge = 300) {} public static function sign(string $secret, string $method, string $route, string $timestamp, string $nonce, string $body): string { return hash_hmac("sha256", implode("\\n", [strtoupper($method), $route, $timestamp, $nonce, hash("sha256", $body)]), $secret); } public function verify(string $method, string $route, string $timestamp, string $nonce, string $body, string $signature): bool { return hash_equals(self::sign($this->secret, $method, $route, $timestamp, $nonce, $body), $signature); } } function get_option(string $key, mixed $default = false): mixed { return $key === "wp_fixpilot_secret" ? "test-secret" : $default; } function get_transient(string $key): mixed { return false; } function set_transient(string $key, mixed $value, int $expiration): void {} require_once "includes/class-rest-controller.php"; $auth = new WPFixPilot_Auth("injected-secret", static fn (): int => 1710000000); $controller = new WPFixPilot_REST_Controller(null, new WPFixPilot_Blueprint_Controller(), $auth); $route = "/wp-json/wpfixpilot/v1/blueprints"; $body = "{}"; $timestamp = "1710000000"; $nonce = "nonce-1"; $signature = WPFixPilot_Auth::sign("injected-secret", "POST", $route, $timestamp, $nonce, $body); $request = new WP_REST_Request("POST", $route, ["x-wp-fixpilot-timestamp" => $timestamp, "x-wp-fixpilot-nonce" => $nonce, "x-wp-fixpilot-signature" => $signature], $body); assert($controller->authorize($request) === true);'`
  - Result: PASS
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build/plugin/wp-fixpilot-bridge:/app -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php`
  - Result: PASS `blueprint lifecycle tests passed`
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build/plugin/wp-fixpilot-bridge:/app -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/auth-test.php`
  - Result: PASS `auth tests passed`
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build/plugin/wp-fixpilot-bridge:/app -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/change-controller-test.php`
  - Result: PASS `change controller tests passed`
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build/plugin/wp-fixpilot-bridge:/app -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/page-package-test.php`
  - Result: PASS `page package adapter tests passed`
  - Command: `docker run --rm -v /Users/tanerdag/projects/wp-fixpilot-new/.worktrees/platform-build/plugin/wp-fixpilot-bridge:/app -w /app php:8.2-cli sh -lc "find . -name '*.php' -print0 | xargs -0 -n1 php -l"`
  - Result: PASS all plugin PHP files lint clean

### Fix Summary

- Added an optional `WPFixPilot_Auth` dependency to `WPFixPilot_REST_Controller` while keeping the existing constructor call patterns valid.
- Moved REST authorization to the injected or default authenticator so route permission callbacks still call `authorize(WP_REST_Request)` and the controller no longer rebuilds auth state per request.
- Preserved the default production auth behavior for `wp_fixpilot_secret`, the 300-second timestamp window, and nonce replay protection via transients.
- Added a deterministic injected-auth regression in the blueprint lifecycle test that proves:
  - valid signed blueprint capture succeeds;
  - invalid signatures fail;
  - replayed nonces fail;
  - the registered permission callback and route callback both remain executable.

### Concerns

- None beyond the retained Task 3 adapter-registration boundary already noted above.

## Task 2 Continuation 5 (Contract Alignment Fixes)

### Files

- Modified `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- Modified `plugin/wp-fixpilot-bridge/tests/blueprint-test.php`
- Modified `plugin/wp-fixpilot-bridge/tests/auth-test.php`
- Modified `.superpowers/sdd/task-2-report.md`

### RED / GREEN Evidence

- RED
  - Command: `docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php`
  - Result:

    ```text
    Fatal error: Uncaught AssertionError: assert((string)get_post_meta($noneSeoBlueprintId, '_wp_fixpilot_seo_plugin', true) === '') in /app/tests/blueprint-test.php:691
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

- Tightened snapshot contract validation to mirror the backend `BlueprintSchema` shape:
  - `schema_version` must be exactly `blueprint-v1`;
  - top-level, block, and field keys now follow backend `extra=forbid` semantics;
  - block `semantic_role` is limited to `hero`, `introduction`, `benefits`, `process`, `faq`, `cta`, and `content`;
  - field `value_type`, `current_value`, `required`, and `max_length` now enforce backend-compatible types and ranges.
- Added compact table-driven invalid-schema regressions that prove invalid capture output deletes the cloned blueprint and returns `wp_fixpilot_blueprint_invalid`.
- Captured the detected SEO plugin exactly once per blueprint snapshot, always persisted `_wp_fixpilot_seo_plugin`, and kept `read()` truthful to the captured snapshot value, including the explicit empty-string `none` case.
- Added a plugin-drift regression and enforced a 409 conflict in `create_draft()` when the currently detected SEO plugin no longer matches the captured snapshot before any draft clone is created.
- Routed SEO metadata writes through the validated captured plugin snapshot rather than a second live detection pass.
- Corrected auth-route regressions to sign canonical WordPress REST routes as `WP_REST_Request::get_route()` returns them:
  - valid signatures now use `/wpfixpilot/v1/...`;
  - signatures built against `/wp-json/wpfixpilot/v1/...` are rejected in both `auth-test.php` and `blueprint-test.php`.
- Preserved prior Task 2 safety behavior, including stale blueprint detection, idempotency guards, draft-only blueprint enforcement, and cleanup on failed capture or draft writes.

### Concerns

- No new scope concerns beyond the retained Task 3 adapter-registration boundary and existing backend ownership of proposal dependency checks.
