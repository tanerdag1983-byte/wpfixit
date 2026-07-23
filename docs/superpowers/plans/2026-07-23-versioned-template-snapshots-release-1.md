# Versioned Template Snapshots Release 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mutable WordPress blueprint pages with hidden immutable snapshots, generate text through one field-ID-only contract, migrate existing blueprints safely, and create idempotent WordPress drafts from the exact captured snapshot.

**Architecture:** WordPress stores the complete builder-specific snapshot in a private custom post type. The backend registers its immutable identity and typed schema, persists resumable proposal stages, and accepts only `snapshot-text-v1` field replacements from AI. The existing outbound job queue carries a new strict `wordpress-snapshot-draft-job-v1` payload; the plugin clones the hidden snapshot, applies validated replacements, and always persists a normal draft page.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, Pydantic 2, PostgreSQL/SQLite tests, React 19, TypeScript, Vite/Vitest, WordPress 6.5+, PHP 8.1/8.2, existing builder and SEO adapters.

## Global Constraints

- Generated WordPress objects are always normal `page` records with persisted `draft` status.
- Source pages and captured snapshot versions are immutable during generation.
- Hidden snapshots are never public, queryable on the front end, or editable through the normal Pages interface.
- AI returns values only for IDs from the exact `snapshot-text-v1` schema.
- Unknown AI fields are recorded and ignored; invalid required fields put only the validation stage into `attention`.
- Plain-text fields never retain HTML; rich text is sanitized through the existing allowlist.
- A proposal is bound to one snapshot ID, version, structure hash, schema version, and immutable proposal version.
- One immutable proposal version creates at most one WordPress draft.
- Any failed builder, ACF, SEO, metadata, or status write deletes the incomplete clone.
- Existing `blueprint-v1`, `wordpress-draft-job-v1`, page-package routes, and manual handoff remain available during rollout.
- Existing source pages are never unpublished, converted, deleted, or modified by migration.
- Publishing remains a human action in WordPress.
- Do not add `backend/uv.lock` unless dependency resolution intentionally changes.
- Every task requires an independent review and resolution of important findings before the next task starts.

## File Map

### WordPress Plugin

- Create `includes/class-template-snapshot-store.php`: register and validate the private snapshot post type and snapshot metadata.
- Modify `includes/class-post-cloner.php`: clone a page or post into an explicit allowed destination post type.
- Modify `includes/class-blueprint-controller.php`: capture/read/delete immutable snapshots and create drafts from them.
- Modify `includes/class-draft-job-controller.php`: dispatch the new snapshot draft contract while retaining v1.
- Modify `wp-fixpilot-bridge.php`: register snapshot storage during plugin boot.
- Add focused PHP test files for snapshot storage, migration compatibility, and v2 draft processing.

### Backend

- Create Alembic revision `0020_versioned_template_snapshots.py`.
- Create Alembic revision `0021_resumable_proposal_stages.py`.
- Extend `page_blueprints/models.py` and `schemas.py` with explicit snapshot identity and `snapshot-text-v1`.
- Create `page_packages/stages.py` for persisted stage transitions and field-level validation results.
- Extend proposal persistence with immutable schema version and stage records.
- Modify blueprint routes/service for capture, verification, versioning, and migration.
- Modify generation/provider contracts so the new path accepts only a field-ID map.
- Modify outbound draft-job construction to emit `wordpress-snapshot-draft-job-v1`.

### Frontend

- Modify `BlueprintSettingsPanel.tsx` to show snapshot and migration state and expose `Nieuwe versie opnemen`.
- Modify `proposalTypes.ts` for snapshot identity, typed fields, and stage state.
- Modify `PagePackageReview.tsx` to show persisted stages and field-level recovery.
- Add focused Vitest coverage before changing component behavior.

---

### Task 1: Store Hidden Immutable Snapshots In WordPress

**Files:**
- Create: `plugin/wp-fixpilot-bridge/includes/class-template-snapshot-store.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-post-cloner.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- Modify: `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`
- Create: `plugin/wp-fixpilot-bridge/tests/template-snapshot-test.php`
- Modify: `plugin/wp-fixpilot-bridge/tests/blueprint-test.php`

**Interfaces:**
- Produces: `WPFixPilot_Template_Snapshot_Store::POST_TYPE = 'wpfixpilot_snapshot'`.
- Produces: `register(): void`, `is_snapshot(int $postId): bool`, `assert_snapshot(int $postId): WP_Post|WP_Error`.
- Changes: `WPFixPilot_Post_Cloner::clone_page(int $sourceId, string $title, bool $asBlueprint, array $allowedMetaKeys, ?string $targetPostType = null): int|WP_Error`.
- Snapshot capture response adds `wordpress_snapshot_id`, `snapshot_version`, `schema_version`, and keeps `wordpress_blueprint_id` as the same integer during compatibility rollout.

- [ ] **Step 1: Write failing hidden-snapshot tests**

```php
function test_snapshot_post_type_is_private(): void
{
    $store = new WPFixPilot_Template_Snapshot_Store();
    $store->register();
    $object = get_post_type_object(WPFixPilot_Template_Snapshot_Store::POST_TYPE);

    assert($object instanceof WP_Post_Type);
    assert($object->public === false);
    assert($object->publicly_queryable === false);
    assert($object->show_ui === false);
    assert($object->exclude_from_search === true);
}

function test_capture_creates_snapshot_without_mutating_source(): void
{
    $sourceBefore = get_post(41);
    $result = blueprint_controller()->capture([
        'source_page_id' => 41,
        'name' => 'Dienstpagina',
        'page_type' => 'service',
        'version' => 1,
    ]);

    assert(!is_wp_error($result));
    assert($result['wordpress_snapshot_id'] === $result['wordpress_blueprint_id']);
    assert(get_post($result['wordpress_snapshot_id'])->post_type === 'wpfixpilot_snapshot');
    assert(get_post(41) == $sourceBefore);
}
```

- [ ] **Step 2: Run the tests and confirm the class and post type are missing**

Run:

```bash
docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/template-snapshot-test.php
```

Expected: FAIL because `WPFixPilot_Template_Snapshot_Store` does not exist.

- [ ] **Step 3: Implement the private store and explicit clone target**

```php
final class WPFixPilot_Template_Snapshot_Store
{
    public const POST_TYPE = 'wpfixpilot_snapshot';

    public function register(): void
    {
        register_post_type(self::POST_TYPE, [
            'label' => 'WP FixPilot snapshots',
            'public' => false,
            'publicly_queryable' => false,
            'show_ui' => false,
            'show_in_rest' => false,
            'exclude_from_search' => true,
            'rewrite' => false,
            'query_var' => false,
            'supports' => ['title', 'editor', 'excerpt', 'custom-fields'],
        ]);
    }

    public function is_snapshot(int $postId): bool
    {
        $post = get_post($postId);
        return $post instanceof WP_Post && $post->post_type === self::POST_TYPE;
    }
}
```

Update the cloner so `$targetPostType` is accepted only when it equals
`WPFixPilot_Template_Snapshot_Store::POST_TYPE` or `page`. An ordinary `page` or
`post` may be cloned to the snapshot type. A snapshot may only be cloned back to
`page`. Without an explicit target, the source post type remains unchanged.
Snapshot clones must persist with `post_status=private` and draft clones with
`post_status=draft`. Verify the actual post type and status after
`wp_insert_post`.

- [ ] **Step 4: Make capture/read/delete operate on snapshots**

In `WPFixPilot_Blueprint_Controller::capture`, pass the snapshot post type to
the cloner, add stable document fields to the adapter schema, and persist:

```php
$schema['schema_version'] = 'snapshot-text-v1';
$schema['document_fields'] = [
    $this->snapshot_field('document:title', 'post_title', 'Paginatitel', 'heading', $source->post_title, true, 180),
    $this->snapshot_field('document:slug', 'post_name', 'Slug', 'plain_text', $source->post_name, true, 160),
    $this->snapshot_field('seo:title', 'seo.title', 'SEO-titel', 'seo_title', '', true, 70),
    $this->snapshot_field('seo:meta_description', 'seo.meta_description', 'Meta description', 'meta_description', '', true, 170),
    $this->snapshot_field('seo:focus_keyword', 'seo.focus_keyword', 'Focuszoekwoord', 'focus_keyword', '', true, 160),
];

$captureMeta = [
    '_wp_fixpilot_snapshot' => '1',
    '_wp_fixpilot_snapshot_version' => $version,
    '_wp_fixpilot_snapshot_schema_version' => 'snapshot-text-v1',
    '_wp_fixpilot_source_page_id' => $sourceId,
    '_wp_fixpilot_blueprint_builder' => $adapter->key(),
    '_wp_fixpilot_blueprint_page_type' => $pageType,
    '_wp_fixpilot_structure_hash' => $structureHash,
    '_wp_fixpilot_content_schema' => $schema,
    '_wp_fixpilot_seo_plugin' => $capturedSeoPlugin,
];
```

Add this private helper to the controller:

```php
/** @return array<string, mixed> */
private function snapshot_field(
    string $id,
    string $path,
    string $label,
    string $valueType,
    string $currentValue,
    bool $required,
    int $maxLength
): array {
    return [
        'id' => $id,
        'path' => $path,
        'label' => $label,
        'value_type' => $valueType,
        'current_value' => $currentValue,
        'required' => $required,
        'max_length' => $maxLength,
    ];
}
```

Replace the ordinary-draft eligibility check for blueprint records with
`Template_Snapshot_Store::is_snapshot`. Keep generated draft checks unchanged.
The source page status must not be consulted after capture.

- [ ] **Step 5: Run snapshot and legacy blueprint suites**

Run:

```bash
docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/template-snapshot-test.php
docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php
```

Expected: both suites pass; legacy capture responses still expose
`wordpress_blueprint_id`.

- [ ] **Step 6: Commit and request independent review**

```bash
git add plugin/wp-fixpilot-bridge/includes/class-template-snapshot-store.php plugin/wp-fixpilot-bridge/includes/class-post-cloner.php plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php plugin/wp-fixpilot-bridge/tests/template-snapshot-test.php plugin/wp-fixpilot-bridge/tests/blueprint-test.php
git commit -m "feat: store immutable WordPress template snapshots"
```

Review focus: public accessibility, source immutability, persisted post type and
status checks, and cleanup after partial capture.

### Task 2: Persist Snapshot Identity And Typed Text Schema

**Files:**
- Create: `backend/alembic/versions/0020_versioned_template_snapshots.py`
- Modify: `backend/app/domains/page_blueprints/models.py`
- Modify: `backend/app/domains/page_blueprints/schemas.py`
- Modify: `backend/app/domains/page_blueprints/service.py`
- Modify: `backend/tests/page_blueprints/test_models.py`
- Modify: `backend/tests/page_blueprints/test_service.py`
- Modify: `backend/tests/page_packages/test_model_registration.py`

**Interfaces:**
- Produces: `SnapshotTextField`, `SnapshotTextBlock`, `SnapshotTextSchema`.
- Schema discriminator: `schema_version: Literal["snapshot-text-v1"]`.
- `PageBlueprint` adds `wordpress_snapshot_id`, `snapshot_version`, `schema_version`, `adapter_version`, `capture_state`, `migration_state`, and `verified_at`.
- Existing `wordpress_blueprint_id` remains populated for legacy API consumers.

- [ ] **Step 1: Write failing model and schema tests**

```python
def sample_snapshot_schema() -> dict:
    def text_field(field_id: str, value_type: str) -> dict:
        return {
            "id": field_id,
            "path": field_id,
            "label": field_id,
            "value_type": value_type,
            "current_value": "",
            "required": True,
            "max_length": 180,
        }

    return {
        "schema_version": "snapshot-text-v1",
        "document_fields": [
            text_field("document:title", "heading"),
            text_field("document:slug", "plain_text"),
            text_field("seo:title", "seo_title"),
            text_field("seo:meta_description", "meta_description"),
            text_field("seo:focus_keyword", "focus_keyword"),
        ],
        "blocks": [{
            "id": "hero",
            "layout": "hero",
            "label": "Hero",
            "semantic_role": "hero",
            "fields": [text_field("acf:hero:title", "heading")],
        }],
    }


def test_snapshot_schema_contains_document_and_block_fields():
    schema = SnapshotTextSchema.model_validate(sample_snapshot_schema())
    assert set(schema.fields_by_id()) == {
        "document:title", "document:slug", "seo:title",
        "seo:meta_description", "seo:focus_keyword", "acf:hero:title",
    }


def test_snapshot_identity_is_complete_or_absent(session, blueprint):
    blueprint.wordpress_snapshot_id = 88
    blueprint.snapshot_version = None
    blueprint.schema_version = "snapshot-text-v1"
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: Run focused tests and verify missing types/columns**

Run:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_blueprints/test_models.py tests/page_blueprints/test_service.py
```

Expected: FAIL because snapshot schema and columns do not exist.

- [ ] **Step 3: Add `snapshot-text-v1` models**

```python
class SnapshotTextField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3, max_length=160)
    path: str = Field(min_length=1, max_length=512)
    label: str = Field(min_length=1, max_length=200)
    value_type: Literal[
        "plain_text", "rich_text", "heading", "button_text", "url",
        "seo_title", "meta_description", "focus_keyword",
    ]
    current_value: str
    required: bool = True
    max_length: int = Field(ge=1, le=20_000)


class SnapshotTextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=160)
    layout: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=200)
    semantic_role: Literal[
        "hero", "introduction", "benefits", "process", "faq", "cta", "content"
    ]
    fields: list[SnapshotTextField] = Field(min_length=1)


class SnapshotTextSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["snapshot-text-v1"]
    document_fields: list[SnapshotTextField] = Field(min_length=5)
    blocks: list[SnapshotTextBlock] = Field(min_length=1)

    def fields_by_id(self) -> dict[str, SnapshotTextField]:
        fields = self.document_fields + [
            field for block in self.blocks for field in block.fields
        ]
        if len({field.id for field in fields}) != len(fields):
            raise ValueError("snapshot field IDs must be unique")
        return {field.id: field for field in fields}
```

The migration adds nullable snapshot columns for legacy rows, a complete-or-none
check constraint, and a unique `(project_id, wordpress_snapshot_id)` constraint.
New snapshots require `capture_state='ready'`, `migration_state='native'`, and
`schema_version='snapshot-text-v1'`.

- [ ] **Step 4: Add service conversion for captured schemas**

Implement:

```python
def snapshot_schema_from_capture(captured: dict) -> SnapshotTextSchema:
    schema = SnapshotTextSchema.model_validate(captured["content_schema"])
    schema.fields_by_id()
    return schema
```

Do not convert arbitrary legacy AI packages here. This function validates only
the plugin capture contract.

- [ ] **Step 5: Run model tests, Ruff, and Alembic**

Run:

```bash
cd backend
.venv/bin/ruff check app tests alembic
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_blueprints/test_models.py tests/page_blueprints/test_service.py tests/page_packages/test_model_registration.py
.venv/bin/alembic upgrade head
```

Expected: all focused tests pass and Alembic reaches revision `0020`.

- [ ] **Step 6: Commit and request independent review**

```bash
git add backend/alembic/versions/0020_versioned_template_snapshots.py backend/app/domains/page_blueprints/models.py backend/app/domains/page_blueprints/schemas.py backend/app/domains/page_blueprints/service.py backend/tests/page_blueprints/test_models.py backend/tests/page_blueprints/test_service.py backend/tests/page_packages/test_model_registration.py
git commit -m "feat: persist versioned template snapshot identity"
```

Review focus: migration reversibility, legacy-row compatibility, uniqueness,
schema ID stability, and cross-project constraints.

### Task 3: Capture, Verify, Version, And Migrate Snapshots

**Files:**
- Modify: `backend/app/api/routes/page_blueprints.py`
- Modify: `backend/app/domains/page_blueprints/service.py`
- Modify: `backend/tests/page_blueprints/conftest.py`
- Modify: `backend/tests/page_blueprints/test_routes.py`
- Modify: `backend/tests/page_blueprints/test_migration.py`
- Modify: `backend/app/domains/wordpress/client.py`
- Modify: `backend/tests/wordpress/test_client.py`

**Interfaces:**
- `POST /projects/{project_id}/page-blueprints` captures a native snapshot.
- `POST /projects/{project_id}/page-blueprints/{id}/new-version` captures a new immutable snapshot.
- `POST /projects/{project_id}/page-blueprints/{id}/verify` checks the stored snapshot itself, never the source page.
- `POST /projects/{project_id}/page-blueprints/migrate` returns per-blueprint results without modifying failed legacy registrations.
- Produces migration states `pending`, `migrating`, `migrated`, `incompatible`, `failed`.

- [ ] **Step 1: Write failing route and migration tests**

```python
def test_publishing_source_after_capture_does_not_stale_snapshot(
    client, auth_as, projects, native_snapshot, monkeypatch
):
    blueprint, plugin_read = native_snapshot
    project_id = projects.member_project.id
    monkeypatch.setattr(WordPressClient, "blueprint", lambda *_: plugin_read)

    response = client.post(
        f"/projects/{project_id}/page-blueprints/{blueprint.id}/verify",
        headers=auth_as.manager,
    )
    assert response.status_code == 200
    assert response.json()["capture_state"] == "ready"


def test_migration_is_per_blueprint_and_preserves_failed_legacy_registration(
    client, auth_as, projects, session, legacy_snapshot_migration, monkeypatch
):
    good, bad, old_wordpress_id, capture_side_effect = legacy_snapshot_migration
    monkeypatch.setattr(
        WordPressClient,
        "capture_blueprint",
        capture_side_effect,
    )
    project_id = projects.member_project.id
    response = client.post(
        f"/projects/{project_id}/page-blueprints/migrate",
        headers=auth_as.manager,
    )
    assert response.json()["items"] == [
        {"blueprint_id": good.id, "state": "migrated"},
        {"blueprint_id": bad.id, "state": "failed", "action": "recapture"},
    ]
    assert session.get(PageBlueprint, bad.id).wordpress_blueprint_id == old_wordpress_id
```

- [ ] **Step 2: Run tests and confirm current source-page coupling**

Run:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_blueprints/test_routes.py tests/page_blueprints/test_migration.py
```

Expected: new verify/migrate route tests fail.

- [ ] **Step 3: Change capture validation to exact snapshot identity**

Validate:

```python
expected = {
    "wordpress_snapshot_id": wordpress_snapshot_id,
    "snapshot_version": version,
    "schema_version": "snapshot-text-v1",
    "source_page_id": source.wordpress_object_id,
    "page_type": page_type,
}
```

Persist `wordpress_snapshot_id` only after the backend confirms `created is
True`, the ID is positive, the returned post type is `wpfixpilot_snapshot`, and
the ID is not registered to another project blueprint.

- [ ] **Step 4: Implement atomic per-blueprint migration**

Add:

```python
@dataclass(frozen=True)
class SnapshotMigrationResult:
    blueprint_id: str
    state: Literal["migrated", "incompatible", "failed"]
    action: Literal["none", "new_proposal", "recapture"]
```

For each legacy blueprint, capture the source into a new hidden snapshot first.
Validate the complete response, then create a new successor `PageBlueprint` row
bound to the snapshot. Never rewrite the identity of the legacy row because
historical proposals reference it through a composite foreign key. Use one
database transaction per blueprint. On backend failure, delete only the newly
returned trusted snapshot ID. Never delete or alter the legacy WordPress
blueprint during the migration transaction.

- [ ] **Step 5: Revalidate compatible unapproved proposals**

Compatibility requires the same adapter block field IDs and compatible field
types. For a compatible unapproved proposal, create a new immutable current
proposal version bound to the successor snapshot; keep the old version and
identity unchanged. Mark incompatible unapproved proposals `failed` with
bounded code `snapshot_migration_requires_generation`. Approved proposals remain
bound to their legacy identity and use the compatibility draft path.

- [ ] **Step 6: Run routes, migration, and client tests**

Run:

```bash
cd backend
.venv/bin/ruff check app tests
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_blueprints/test_routes.py tests/page_blueprints/test_migration.py tests/wordpress/test_client.py
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit and request independent review**

```bash
git add backend/app/api/routes/page_blueprints.py backend/app/domains/page_blueprints/service.py backend/app/domains/wordpress/client.py backend/tests/page_blueprints/conftest.py backend/tests/page_blueprints/test_routes.py backend/tests/page_blueprints/test_migration.py backend/tests/wordpress/test_client.py
git commit -m "feat: migrate managed blueprints to snapshots"
```

Review focus: transaction boundaries, trusted cleanup identity, approved
proposal preservation, and no source-page writes.

### Task 4: Replace Page-Shaped AI Output With Field-ID Text Output

**Files:**
- Modify: `backend/app/domains/page_packages/schemas.py`
- Modify: `backend/app/domains/page_packages/generation.py`
- Modify: `backend/app/domains/recommendations/openai_compatible_provider.py`
- Modify: `backend/app/domains/recommendations/openai_provider.py`
- Modify: `backend/app/domains/recommendations/anthropic_provider.py`
- Modify: `backend/app/domains/recommendations/gemini_provider.py`
- Modify: `backend/tests/page_packages/test_generation.py`
- Modify: `backend/tests/page_packages/test_provider_page_packages.py`
- Modify: provider-specific tests under `backend/tests/recommendations/`

**Interfaces:**
- Produces: `SnapshotTextValue` and `GeneratedSnapshotTextPackage`.
- Produces: `normalize_snapshot_text_package(raw: object, context: PagePackageContext) -> SnapshotTextValidation`.
- `SnapshotTextValidation` contains normalized replacements, field errors, ignored IDs, and `ready: bool`.
- Legacy package normalization is not called for `snapshot-text-v1`.

- [ ] **Step 1: Write failing contract and field-isolation tests**

```python
def test_snapshot_contract_contains_only_field_id_values(snapshot_context):
    contract = page_package_contract(snapshot_context)
    assert contract is GeneratedSnapshotTextPackage
    assert set(contract.model_json_schema()["properties"]) == {"text_replacements"}


def test_invalid_optional_field_does_not_fail_valid_required_fields(snapshot_context):
    result = normalize_snapshot_text_package({
        "text_replacements": {
            "document:title": {"value": "<strong>Nieuwe titel</strong>"},
            "acf:hero:label": {"value": "<script>bad</script>"},
            "unknown:id": {"value": "ignore"},
        }
    }, snapshot_context)
    assert result.replacements["document:title"] == "Nieuwe titel"
    assert result.field_errors == {"acf:hero:label": "unsafe_html"}
    assert result.ignored_field_ids == ["unknown:id"]
    assert result.ready is True
```

- [ ] **Step 2: Run generation/provider tests and confirm failure**

Run:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_packages/test_generation.py tests/page_packages/test_provider_page_packages.py
```

Expected: FAIL because the snapshot contract and validation result do not exist.

- [ ] **Step 3: Implement the strict contract**

```python
class SnapshotTextValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str = Field(max_length=20_000)


class GeneratedSnapshotTextPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_replacements: dict[str, SnapshotTextValue] = Field(min_length=1)


class SnapshotTextValidation(BaseModel):
    replacements: dict[str, str]
    field_errors: dict[str, str]
    blocking_field_ids: list[str]
    ignored_field_ids: list[str]
    missing_required_field_ids: list[str]

    @property
    def ready(self) -> bool:
        return not self.blocking_field_ids and not self.missing_required_field_ids
```

Normalize each field according to its schema type. Preserve optional omitted
snapshot values. Force `seo:focus_keyword` to the opportunity keyword. Validate
slug syntax after stripping markup. Sanitize rich text and validate every URL
against approved URLs.

- [ ] **Step 4: Update all provider prompts and parsers**

When `context.blueprint_schema.schema_version == "snapshot-text-v1"`, providers
must request only:

```json
{"text_replacements":{"known-field-id":{"value":"candidate text"}}}
```

Do not unwrap `landing_page`, `package`, `hero_title`, `sections`, `faq`, or
`cta` for this contract. Return a bounded provider error when the top-level
shape is not `text_replacements`.

- [ ] **Step 5: Run all provider and generation tests**

Run:

```bash
cd backend
.venv/bin/ruff check app tests
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_packages/test_generation.py tests/page_packages/test_provider_page_packages.py tests/recommendations/test_openai_provider.py tests/recommendations/test_openai_compatible_provider.py tests/recommendations/test_anthropic_provider.py tests/recommendations/test_gemini_provider.py
```

Expected: all tests pass; legacy provider contracts remain green.

- [ ] **Step 6: Commit and request independent review**

```bash
git add backend/app/domains/page_packages/schemas.py backend/app/domains/page_packages/generation.py backend/app/domains/recommendations/openai_compatible_provider.py backend/app/domains/recommendations/openai_provider.py backend/app/domains/recommendations/anthropic_provider.py backend/app/domains/recommendations/gemini_provider.py backend/tests/page_packages/test_generation.py backend/tests/page_packages/test_provider_page_packages.py backend/tests/recommendations/test_openai_provider.py backend/tests/recommendations/test_openai_compatible_provider.py backend/tests/recommendations/test_anthropic_provider.py backend/tests/recommendations/test_gemini_provider.py
git commit -m "feat: generate snapshot text by field id"
```

Review focus: no legacy repair path on snapshots, HTML policy by type, required
field behavior, and focus-keyword preservation.

### Task 5: Persist Resumable Proposal Stages And Field Errors

**Files:**
- Create: `backend/alembic/versions/0021_resumable_proposal_stages.py`
- Modify: `backend/app/domains/page_packages/models.py`
- Create: `backend/app/domains/page_packages/stages.py`
- Modify: `backend/app/api/routes/page_packages.py`
- Create: `backend/tests/page_packages/test_proposal_stages.py`
- Modify: `backend/tests/page_packages/test_proposal_routes.py`
- Modify: `backend/tests/page_packages/test_proposal_versions.py`

**Interfaces:**
- Produces model `PageProposalStage`.
- Stage names in Release 1: `template`, `text`, `validation`.
- Stage states: `pending`, `running`, `ready`, `attention`, `failed`.
- Produces `begin_stage`, `complete_stage`, `attention_stage`, `fail_stage`, and `retry_stage`.
- Proposal response adds ordered `stages` and `field_errors`.

- [ ] **Step 1: Write failing stage persistence and retry tests**

```python
def test_text_success_survives_validation_attention(session, proposal):
    complete_stage(session, proposal.id, "text", result={"text_replacements": {"a": "b"}})
    attention_stage(session, proposal.id, "validation",
        errors={"acf:hero:label": "unsafe_html"})
    session.commit()
    assert stage(session, proposal.id, "text").state == "ready"
    assert stage(session, proposal.id, "text").result["text_replacements"] == {"a": "b"}


def test_retry_validation_does_not_run_provider_again(client, proposal, provider_spy):
    response = client.post(
        f"/projects/{proposal.project_id}/page-proposals/{proposal.id}/stages/validation/retry",
        headers=manager_headers,
    )
    assert response.status_code == 202
    assert provider_spy.call_count == 0
```

- [ ] **Step 2: Run tests and confirm stage model/functions are missing**

Run:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_packages/test_proposal_stages.py tests/page_packages/test_proposal_routes.py
```

Expected: FAIL during collection.

- [ ] **Step 3: Implement model constraints and transition helpers**

```python
ALLOWED_TRANSITIONS = {
    "pending": {"running"},
    "running": {"ready", "attention", "failed"},
    "attention": {"running"},
    "failed": {"running"},
    "ready": set(),
}


def retry_stage(session, proposal_id: str, stage_name: str) -> PageProposalStage:
    item = locked_stage(session, proposal_id, stage_name)
    if item.state not in {"attention", "failed"}:
        raise ValueError("stage_not_retryable")
    item.state = "running"
    item.retry_count += 1
    item.errors = {}
    return item
```

The stage table uses unique `(proposal_version_id, name)`, bounded JSON
`result`/`errors`, transition timestamps, retry count, and a proposal FK with
`ON DELETE CASCADE`.

- [ ] **Step 4: Split generation into persisted stage execution**

Initial proposal creation:

1. verify and store the snapshot identity in `template`;
2. call the provider once and store raw normalized field candidates in `text`;
3. validate candidates into `validation`;
4. set proposal `proposed` only when validation is `ready`;
5. leave proposal editable with state `needs_attention` and validation stage
   `attention` when required user-correctable fields remain.

Retrying `validation` reads the stored text result. Retrying `text` explicitly
calls the provider and creates a new immutable proposal version rather than
overwriting the old text result.

- [ ] **Step 5: Run stage, route, and version tests**

Run:

```bash
cd backend
.venv/bin/ruff check app tests alembic
.venv/bin/python -m pytest --import-mode=importlib -q tests/page_packages/test_proposal_stages.py tests/page_packages/test_proposal_routes.py tests/page_packages/test_proposal_versions.py
.venv/bin/alembic upgrade head
```

Expected: all focused tests pass and Alembic reaches revision `0021`.

- [ ] **Step 6: Commit and request independent review**

```bash
git add backend/alembic/versions/0021_resumable_proposal_stages.py backend/app/domains/page_packages/models.py backend/app/domains/page_packages/stages.py backend/app/api/routes/page_packages.py backend/tests/page_packages/test_proposal_stages.py backend/tests/page_packages/test_proposal_routes.py backend/tests/page_packages/test_proposal_versions.py
git commit -m "feat: persist resumable proposal stages"
```

Review focus: stage transition races, immutable version behavior, JSON bounds,
and provider not rerunning during validation retry.

### Task 6: Create Drafts From Exact Snapshots Through Contract V2

**Files:**
- Modify: `backend/app/domains/wordpress/draft_jobs.py`
- Modify: `backend/app/api/routes/wordpress_draft_jobs.py`
- Modify: `backend/tests/wordpress/test_draft_job_service.py`
- Modify: `backend/tests/wordpress/test_draft_job_routes.py`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-draft-job-controller.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- Create: `plugin/wp-fixpilot-bridge/tests/snapshot-draft-job-test.php`
- Modify: `plugin/wp-fixpilot-bridge/tests/draft-job-test.php`

**Interfaces:**
- Contract: `wordpress-snapshot-draft-job-v1`.
- Backend payload keys: `proposal_version_id`, `snapshot_id`,
  `snapshot_version`, `snapshot_structure_hash`, `schema_version`,
  `idempotency_key`, `text_replacements`, and `approved_urls`.
- Existing `wordpress-draft-job-v1` remains dispatched to its old handler.

- [ ] **Step 1: Write failing backend payload and plugin dispatch tests**

```python
def test_snapshot_job_contains_only_snapshot_contract_fields(session, approved_snapshot_proposal):
    job = create_or_get_draft_job(session, approved_snapshot_proposal)
    assert job.contract_version == "wordpress-snapshot-draft-job-v1"
    assert set(job.payload) == {
        "proposal_version_id", "snapshot_id", "snapshot_version",
        "snapshot_structure_hash", "schema_version", "idempotency_key",
        "text_replacements", "approved_urls",
    }
```

```php
function test_snapshot_job_clones_private_snapshot_to_page_draft(): void
{
    $result = draft_job_controller()->process_payload(snapshot_job_fixture());
    assert(!is_wp_error($result));
    $draft = get_post((int) $result['wordpress_object_id']);
    assert($draft->post_type === 'page');
    assert($draft->post_status === 'draft');
}
```

- [ ] **Step 2: Run tests and confirm v2 is unsupported**

Run:

```bash
cd backend
.venv/bin/python -m pytest --import-mode=importlib -q tests/wordpress/test_draft_job_service.py tests/wordpress/test_draft_job_routes.py
cd ..
docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/snapshot-draft-job-test.php
```

Expected: backend expects v1 and plugin returns `wp_fixpilot_unsupported_contract`.

- [ ] **Step 3: Emit immutable contract v2 from the backend**

Select v2 only when the proposal has complete native snapshot identity and a
ready validation stage. Derive the payload from stored normalized validation
output, not from provider output or mutable request data.

```python
SNAPSHOT_JOB_CONTRACT_VERSION = "wordpress-snapshot-draft-job-v1"

payload = {
    "proposal_version_id": proposal.id,
    "snapshot_id": blueprint.wordpress_snapshot_id,
    "snapshot_version": blueprint.snapshot_version,
    "snapshot_structure_hash": blueprint.structure_hash,
    "schema_version": blueprint.schema_version,
    "idempotency_key": proposal.id,
    "text_replacements": validation.result["replacements"],
    "approved_urls": validation.result["approved_urls"],
}
```

- [ ] **Step 4: Validate and apply v2 in the plugin**

The plugin must:

1. require the exact key set;
2. load `snapshot_id` through `Template_Snapshot_Store::assert_snapshot`;
3. compare snapshot version, schema version, and current adapter structure hash;
4. validate every replacement against the stored schema;
5. derive document title, slug, and SEO writes from their field IDs;
6. pass only block fields to the builder adapter;
7. clone the snapshot into `post_type=page`, `post_status=draft`;
8. verify all writes and persisted status;
9. clean up on any failure;
10. return the existing draft for an identical idempotency identity.

- [ ] **Step 5: Run backend and all plugin draft suites**

Run:

```bash
cd backend
.venv/bin/ruff check app tests
.venv/bin/python -m pytest --import-mode=importlib -q tests/wordpress/test_draft_job_service.py tests/wordpress/test_draft_job_routes.py
cd ..
docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/snapshot-draft-job-test.php
docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/draft-job-test.php
docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/page-package-test.php
```

Expected: snapshot and legacy draft suites pass.

- [ ] **Step 6: Commit and request independent review**

```bash
git add backend/app/domains/wordpress/draft_jobs.py backend/app/api/routes/wordpress_draft_jobs.py backend/tests/wordpress/test_draft_job_service.py backend/tests/wordpress/test_draft_job_routes.py plugin/wp-fixpilot-bridge/includes/class-draft-job-controller.php plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php plugin/wp-fixpilot-bridge/tests/snapshot-draft-job-test.php plugin/wp-fixpilot-bridge/tests/draft-job-test.php
git commit -m "feat: create drafts from immutable snapshots"
```

Review focus: payload immutability, v1/v2 dispatch separation, idempotency,
snapshot verification, and cleanup.

### Task 7: Show Snapshot And Migration State In Settings

**Files:**
- Modify: `frontend/src/features/blueprints/BlueprintSettingsPanel.tsx`
- Modify: `frontend/src/features/blueprints/BlueprintSettingsPanel.test.tsx`
- Modify: `frontend/src/features/blueprints/BlueprintOutline.tsx`
- Modify: `frontend/src/features/blueprints/BlueprintOutline.test.tsx`

**Interfaces:**
- Blueprint UI consumes `wordpress_snapshot_id`, `snapshot_version`,
  `schema_version`, `capture_state`, `migration_state`, and `verified_at`.
- Actions: `Nieuwe versie opnemen`, `Controleren`, and project-level
  `Bestaande templates omzetten`.

- [ ] **Step 1: Write failing UI tests**

```tsx
it("shows immutable snapshot identity instead of a mutable blueprint page", async () => {
  render(<BlueprintSettingsPanel projectId="project-1" />);
  expect(await screen.findByText("Snapshotversie 2")).toBeInTheDocument();
  expect(screen.getByText("Verborgen WordPress-template")).toBeInTheDocument();
  expect(screen.queryByText("Blueprintpagina")).not.toBeInTheDocument();
});

it("migrates existing templates and keeps per-item recovery visible", async () => {
  render(<BlueprintSettingsPanel projectId="project-1" />);
  await userEvent.click(await screen.findByRole("button", {
    name: "Bestaande templates omzetten",
  }));
  expect(await screen.findByText("4 templates omgezet")).toBeInTheDocument();
  expect(screen.getByText("1 template opnieuw opnemen")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run focused tests and confirm missing UI**

Run:

```bash
cd frontend
npm test -- --run src/features/blueprints/BlueprintSettingsPanel.test.tsx src/features/blueprints/BlueprintOutline.test.tsx
```

Expected: new assertions fail.

- [ ] **Step 3: Implement snapshot-focused settings**

Replace mutable-page terminology. Show:

- snapshot version and capture timestamp;
- builder, adapter/schema version, text field count;
- migration and verification state;
- source page as lineage only;
- `Nieuwe versie opnemen` and `Controleren`;
- a migration summary with one action per failed item.

Do not expose delete for a referenced snapshot. Preserve project-switch race
guards already present in the component.

- [ ] **Step 4: Run frontend tests, lint, and build**

Run:

```bash
cd frontend
npm test -- --run src/features/blueprints/BlueprintSettingsPanel.test.tsx src/features/blueprints/BlueprintOutline.test.tsx
npm run lint
npm run build
```

Expected: tests, lint, and production build pass.

- [ ] **Step 5: Commit and request independent review**

```bash
git add frontend/src/features/blueprints/BlueprintSettingsPanel.tsx frontend/src/features/blueprints/BlueprintSettingsPanel.test.tsx frontend/src/features/blueprints/BlueprintOutline.tsx frontend/src/features/blueprints/BlueprintOutline.test.tsx
git commit -m "feat: show immutable template snapshots"
```

Review focus: recovery copy, race guards, accessible status, and no suggestion
that the source page must stay a draft.

### Task 8: Show Resumable Generation Stages And Field Recovery

**Files:**
- Modify: `frontend/src/features/page-packages/proposalTypes.ts`
- Modify: `frontend/src/features/page-packages/PagePackageReview.tsx`
- Modify: `frontend/src/features/page-packages/PagePackageReview.test.tsx`
- Create: `frontend/src/features/page-packages/ProposalStageList.tsx`
- Create: `frontend/src/features/page-packages/ProposalStageList.test.tsx`

**Interfaces:**
- Consumes ordered proposal stages and `field_errors`.
- `ProposalStageList` exposes retry callbacks for `text` and `validation`.
- A proposal with state `needs_attention` remains editable and never renders a blank general error page.

- [ ] **Step 1: Write failing stage and field-error tests**

```tsx
it("keeps successful text and shows only the invalid field recovery", async () => {
  render(<PagePackageReview projectId="project-1" />);
  expect(await screen.findByText("Tekst gereed")).toBeInTheDocument();
  expect(screen.getByText("Hero-label bevat niet-toegestane opmaak")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Waarde aanpassen" })).toBeEnabled();
  expect(screen.queryByText(/validation errors for/i)).not.toBeInTheDocument();
});

it("retries validation without replacing the generated text", async () => {
  render(<PagePackageReview projectId="project-1" />);
  await userEvent.click(await screen.findByRole("button", {
    name: "Validatie opnieuw uitvoeren",
  }));
  expect(apiRequest).toHaveBeenCalledWith(
    "/projects/project-1/page-proposals/proposal-1/stages/validation/retry",
    { method: "POST" },
  );
});
```

- [ ] **Step 2: Run tests and confirm current general-error behavior**

Run:

```bash
cd frontend
npm test -- --run src/features/page-packages/PagePackageReview.test.tsx src/features/page-packages/ProposalStageList.test.tsx
```

Expected: FAIL because stage rendering and retry actions do not exist.

- [ ] **Step 3: Implement persisted stage UI**

Render the fixed Release 1 sequence:

```ts
const stageLabels = {
  template: "Template gereed",
  text: "Tekst gereed",
  validation: "Gevalideerd",
} as const;
```

Show `running`, `ready`, `attention`, and `failed` distinctly. Field errors use
the schema label, bounded Dutch message, and direct edit/retry action. Raw
Pydantic/provider traces are never rendered.

- [ ] **Step 4: Preserve review, approval, compare, and manual fallback**

The existing full-width preview, editable fields, proposal version comparison,
approval, outbound draft action, and manual handoff fallback remain. Approval is
disabled until required validation errors are resolved.

- [ ] **Step 5: Run focused and full frontend verification**

Run:

```bash
cd frontend
npm test -- --run src/features/page-packages/PagePackageReview.test.tsx src/features/page-packages/ProposalStageList.test.tsx
npm test -- --run
npm run lint
npm run build
```

Expected: all tests, lint, and production build pass.

- [ ] **Step 6: Commit and request independent review**

```bash
git add frontend/src/features/page-packages/proposalTypes.ts frontend/src/features/page-packages/PagePackageReview.tsx frontend/src/features/page-packages/PagePackageReview.test.tsx frontend/src/features/page-packages/ProposalStageList.tsx frontend/src/features/page-packages/ProposalStageList.test.tsx
git commit -m "feat: show resumable page generation stages"
```

Review focus: blank/error states, retry semantics, approval gating, accessibility,
and preservation of the existing comparison flow.

### Task 9: Complete Release 1 Regression, Migration, And Live Acceptance

**Files:**
- Modify: `.superpowers/sdd/progress.md`
- Create: `.superpowers/sdd/task-versioned-template-snapshots-release-1-report.md`
- Modify: plugin version in `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`
- Modify only tests or production files required by verified acceptance findings.

**Interfaces:**
- Release artifact includes backend migrations `0020` and `0021`, frontend build, and one plugin ZIP.
- Existing manual handoff remains available.
- Release 2 image work does not start until this task is independently approved.

- [ ] **Step 1: Run the complete backend verification**

Run:

```bash
cd backend
.venv/bin/ruff check app tests alembic
.venv/bin/python -m pytest --import-mode=importlib -q
.venv/bin/alembic upgrade head
```

Expected: Ruff passes, all non-environmental tests pass, optional PostgreSQL
concurrency tests either pass or skip only because
`WP_FIXPILOT_POSTGRES_TEST_URL` is unset, and Alembic reaches `0021`.

- [ ] **Step 2: Run the complete frontend verification**

Run:

```bash
cd frontend
npm test -- --run
npm run lint
npm run build
```

Expected: all tests, lint, and production build pass.

- [ ] **Step 3: Run all plugin suites and PHP lint under PHP 8.2**

Run:

```bash
docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli sh -lc 'for test in tests/*-test.php; do php -d zend.assertions=1 -d assert.exception=1 "$test" || exit 1; done; find . -name "*.php" -print0 | xargs -0 -n1 php -l'
```

Expected: every suite and PHP syntax check passes.

- [ ] **Step 4: Build one plugin ZIP after all plugin tests pass**

Run:

```bash
cd plugin
rm -f wp-fixpilot-bridge-release-1.zip
zip -qr wp-fixpilot-bridge-release-1.zip wp-fixpilot-bridge -x 'wp-fixpilot-bridge/tests/*'
unzip -l wp-fixpilot-bridge-release-1.zip
```

Expected: one archive containing the plugin root and no test files.

- [ ] **Step 5: Perform staging migration and acceptance**

On `staging.shmtransmissie.nl`:

1. install the single tested plugin ZIP once;
2. run `Bestaande templates omzetten`;
3. verify at least five ACF templates report `migrated`;
4. publish or edit one original source page;
5. verify its hidden snapshot still reports `ready`;
6. generate and approve two separate proposals per template;
7. create both drafts through outbound jobs;
8. verify every resulting object is a `page` in `draft`;
9. retry one completed job and confirm the same edit URL returns;
10. force one validation error, fix only that field, and resume without another provider call;
11. confirm no duplicate pages, incomplete drafts, structure loss, or manual plugin upload per draft.

- [ ] **Step 6: Record evidence and obtain independent release review**

The report records:

- commit range;
- exact backend/frontend/plugin commands and counts;
- Alembic head;
- plugin version and ZIP checksum;
- migrated template IDs and snapshot versions;
- created WordPress draft IDs and edit links;
- forced-failure recovery evidence;
- remaining known limitations;
- rollback procedure using the retained v1/manual path.

- [ ] **Step 7: Commit the release report and progress update**

```bash
git add .superpowers/sdd/progress.md .superpowers/sdd/task-versioned-template-snapshots-release-1-report.md plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php
git commit -m "chore: verify template snapshot release one"
```

Release 1 is complete only after the independent reviewer approves the evidence
and no important finding remains.

## Deferred Follow-Up Plans

After Release 1 is stable and live:

1. write `Versioned Template Snapshots Release 2` for all recognized template
   image slots, generated candidates, Media Library selection, and idempotent
   media upload;
2. write `Versioned Template Snapshots Release 3` for controlled blog inline
   image anchors and Brand DNA image prompts.

Do not implement either image release inside Release 1.
