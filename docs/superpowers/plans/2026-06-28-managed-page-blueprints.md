# Managed Page Blueprints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build reusable, versioned WordPress page blueprints that preserve complete ACF, Elementor, WPBakery, Bricks, or Gutenberg structure while AI changes only approved text and SEO fields.

**Architecture:** WordPress owns each builder-native blueprint as a marked draft `page`; the backend stores its registry, immutable version, schema, defaults, and proposal relationship. Builder adapters expose a shared block-and-field schema and apply validated text replacements to a cloned draft. AI returns replacements keyed by known field IDs rather than six generic page sections.

**Tech Stack:** WordPress/PHP 8.1+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Pydantic 2, React 19, TypeScript, Vitest, OpenAI-compatible structured output.

## Global Constraints

- A blueprint must remain a normal WordPress `page` with draft status so ACF location rules and builder support continue to work.
- Source pages and managed blueprints must never be modified during generation.
- Generated WordPress pages must always be drafts; publishing remains manual.
- Preserve layout rows, repeaters, images, media IDs, styles, widget types, PHP page template, and non-text metadata.
- AI may replace only schema-listed text fields and approved internal-link or CTA URLs.
- Every draft write requires the expected blueprint version and structure hash.
- Every proposal must remain idempotent and tied to one immutable blueprint version.
- Support `acf`, `elementor`, `wpbakery`, `bricks`, and `gutenberg` through one adapter contract.
- Keep the existing page-package routes operational until migration is complete.

---

## File Structure

### Backend

- Create `backend/alembic/versions/0017_managed_page_blueprints.py`: blueprint registry and proposal migration.
- Create `backend/app/domains/page_blueprints/models.py`: `PageBlueprint` persistence model.
- Create `backend/app/domains/page_blueprints/schemas.py`: API and AI schema contracts.
- Create `backend/app/domains/page_blueprints/service.py`: defaults, versioning, validation, and migration helpers.
- Create `backend/app/api/routes/page_blueprints.py`: blueprint CRUD and validation endpoints.
- Modify `backend/app/main.py`: register the blueprint router.
- Modify `backend/app/domains/wordpress/client.py`: bridge blueprint methods.
- Modify `backend/app/domains/page_packages/models.py`: attach proposals to immutable blueprints.
- Modify `backend/app/domains/page_packages/generation.py`: schema-driven prompt and output validation.
- Modify `backend/app/domains/page_packages/schemas.py`: replacement-based package contract.
- Modify `backend/app/api/routes/page_packages.py`: select defaults, generate replacements, and create drafts from blueprints.

### WordPress plugin

- Create `plugin/wp-fixpilot-bridge/includes/class-post-cloner.php`: safe builder-aware page cloning.
- Create `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`: capture, inspect, version, delete, and draft lifecycle.
- Create `plugin/wp-fixpilot-bridge/includes/builder-adapters/interface-blueprint-adapter.php`: shared adapter contract.
- Modify all five builder adapters to implement detection, schema extraction, hashing, and replacements.
- Modify `plugin/wp-fixpilot-bridge/includes/class-rest-controller.php`: blueprint REST routes.
- Modify `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`: load new classes and bump plugin version.
- Create `plugin/wp-fixpilot-bridge/tests/blueprint-test.php`: lifecycle and structure-preservation tests.
- Create `plugin/wp-fixpilot-bridge/tests/blueprint-adapters-test.php`: five adapter contract fixtures.

### Frontend

- Create `frontend/src/features/blueprints/BlueprintSettingsPanel.tsx`: blueprint management flow.
- Create `frontend/src/features/blueprints/BlueprintOutline.tsx`: grouped block and editable-field review.
- Create matching Vitest files for both components.
- Modify the settings screen to replace the six-slot panel once blueprints are available.
- Modify `frontend/src/features/page-packages/PagePackageReview.tsx`: blueprint version and grouped replacements.
- Modify `frontend/src/features/opportunities/OpportunitiesPage.tsx`: page type and selected default blueprint.

---

### Task 1: Persist Immutable Project Blueprints

**Files:**
- Create: `backend/app/domains/page_blueprints/__init__.py`
- Create: `backend/app/domains/page_blueprints/models.py`
- Create: `backend/app/domains/page_blueprints/schemas.py`
- Create: `backend/app/domains/page_blueprints/service.py`
- Create: `backend/alembic/versions/0017_managed_page_blueprints.py`
- Create: `backend/tests/page_blueprints/test_models.py`
- Create: `backend/tests/page_blueprints/test_service.py`
- Modify: `backend/app/domains/page_packages/models.py`

**Interfaces:**
- Produces: `PageBlueprint`, `BlueprintBlock`, `BlueprintField`, `BlueprintSchema`, `set_default_blueprint()`, and `create_blueprint_version()`.
- Consumes: `Project`, `WordPressPage`, and existing `PagePackageProposal` records.

- [ ] **Step 1: Write the failing model and service tests**

```python
def valid_schema() -> dict:
    return {
        "schema_version": "blueprint-v1",
        "blocks": [
            {
                "id": "block-hero",
                "layout": "hero_algemeen",
                "label": "Hero (algemeen)",
                "semantic_role": "hero",
                "fields": [
                    {
                        "id": "acf-title",
                        "path": "page_blocks/0/title",
                        "label": "Titel",
                        "value_type": "heading",
                        "current_value": "Transmissie onderhoud",
                        "required": True,
                        "max_length": 180,
                    }
                ],
            }
        ],
    }


def blueprint(project_id: str, page_type: str, version: int) -> PageBlueprint:
    return PageBlueprint(
        id=f"blueprint-{page_type}-{version}",
        project_id=project_id,
        name=f"{page_type.title()}pagina",
        page_type=page_type,
        source_wordpress_page_id="source-page",
        wordpress_blueprint_id=900 + version,
        builder="acf",
        seo_plugin="yoast",
        version=version,
        structure_hash=f"hash-v{version}",
        content_schema=valid_schema(),
        state="ready",
        is_default_for_page_type=False,
    )


def test_one_default_blueprint_per_project_page_type(session, projects):
    first = blueprint(projects.member_project.id, "service", version=1)
    second = blueprint(projects.member_project.id, "service", version=2)
    session.add_all([first, second])
    session.commit()

    set_default_blueprint(session, first)
    set_default_blueprint(session, second)

    session.refresh(first)
    session.refresh(second)
    assert first.is_default_for_page_type is False
    assert second.is_default_for_page_type is True


def test_new_version_is_immutable_and_supersedes_previous(session, projects):
    original = blueprint(projects.member_project.id, "brand", version=1)
    session.add(original)
    session.commit()

    replacement = create_blueprint_version(
        session,
        original,
        wordpress_blueprint_id=902,
        structure_hash="hash-v2",
        content_schema=valid_schema(),
    )

    assert replacement.version == 2
    assert replacement.supersedes_id == original.id
    assert original.structure_hash == "hash-v1"
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `cd backend && pytest tests/page_blueprints/test_models.py tests/page_blueprints/test_service.py -q`

Expected: FAIL because `app.domains.page_blueprints` does not exist.

- [ ] **Step 3: Add the blueprint model and schema contracts**

```python
class PageBlueprint(Base):
    __tablename__ = "page_blueprints"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "wordpress_blueprint_id",
            name="uq_page_blueprint_wordpress_identity",
        ),
        Index(
            "uq_page_blueprint_default_per_type",
            "project_id",
            "page_type",
            unique=True,
            postgresql_where=text("is_default_for_page_type = true"),
            sqlite_where=text("is_default_for_page_type = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    page_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_wordpress_page_id: Mapped[str] = mapped_column(
        ForeignKey("wordpress_pages.id", ondelete="RESTRICT"), nullable=False
    )
    wordpress_blueprint_id: Mapped[int] = mapped_column(Integer, nullable=False)
    builder: Mapped[str] = mapped_column(String(32), nullable=False)
    seo_plugin: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    structure_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    content_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    is_default_for_page_type: Mapped[bool] = mapped_column(Boolean, nullable=False)
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("page_blueprints.id", ondelete="RESTRICT")
    )
```

```python
class BlueprintField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    path: str
    label: str
    value_type: Literal["plain_text", "rich_text", "heading", "button_text", "url"]
    current_value: str
    required: bool = True
    max_length: int = Field(ge=1, le=20_000)


class BlueprintBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    layout: str
    label: str
    semantic_role: Literal[
        "hero", "introduction", "benefits", "process", "faq", "cta", "content"
    ]
    fields: list[BlueprintField] = Field(min_length=1)


class BlueprintSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["blueprint-v1"]
    blocks: list[BlueprintBlock] = Field(min_length=1)
```

- [ ] **Step 4: Add service behavior and proposal reference**

```python
def set_default_blueprint(session: Session, blueprint: PageBlueprint) -> None:
    session.execute(
        update(PageBlueprint)
        .where(
            PageBlueprint.project_id == blueprint.project_id,
            PageBlueprint.page_type == blueprint.page_type,
            PageBlueprint.id != blueprint.id,
        )
        .values(is_default_for_page_type=False)
    )
    blueprint.is_default_for_page_type = True
    session.commit()
```

Add `blueprint_id`, `blueprint_version`, and `blueprint_structure_hash` to
`PagePackageProposal`; keep them nullable for historical legacy proposals while every
new proposal requires all three at service-validation level.

- [ ] **Step 5: Add and run migration `0017_managed_page_blueprints`**

Run: `cd backend && alembic upgrade head`

Expected: migration reaches `0017_managed_page_blueprints` and creates the partial
default index plus proposal foreign key.

- [ ] **Step 6: Run tests and commit**

Run: `cd backend && ruff check app tests alembic && pytest tests/page_blueprints -q`

Expected: all blueprint tests pass.

```bash
git add backend/app/domains/page_blueprints backend/app/domains/page_packages/models.py backend/alembic/versions/0017_managed_page_blueprints.py backend/tests/page_blueprints
git commit -m "feat: persist managed page blueprints"
```

### Task 2: Capture Complete WordPress Blueprint Pages

**Files:**
- Create: `plugin/wp-fixpilot-bridge/includes/class-post-cloner.php`
- Create: `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`
- Create: `plugin/wp-fixpilot-bridge/includes/builder-adapters/interface-blueprint-adapter.php`
- Create: `plugin/wp-fixpilot-bridge/tests/blueprint-test.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-rest-controller.php`
- Modify: `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`

**Interfaces:**
- Produces: `WPFixPilot_Blueprint_Controller::capture()`, `read()`, `create_draft()`, and `delete()`.
- Produces: `WPFixPilot_Blueprint_Adapter`; the lifecycle test supplies a fake adapter so the controller does not depend on Task 3 implementations.
- Produces bridge routes `POST /blueprints`, `GET /blueprints/{id}`, `POST /blueprints/{id}/drafts`, and `DELETE /blueprints/{id}`.
- Consumes the existing SEO adapter contract for final draft metadata.

- [ ] **Step 1: Write failing lifecycle tests**

```php
$captured = $controller->capture([
    'source_page_id' => 19,
    'name' => 'Dienstpagina',
    'page_type' => 'service',
    'builder' => 'acf',
    'version' => 1,
]);

assert($captured['status'] === 'ready');
assert($captured['source_page_id'] === 19);
assert($captured['wordpress_blueprint_id'] === 200);
assert(get_post(200)->post_type === 'page');
assert(get_post(200)->post_status === 'draft');
assert(get_post_meta(200, '_wp_fixpilot_blueprint', true) === '1');
assert(get_post_meta(200, '_wp_page_template', true) === 'algemeen-productdetail.php');
assert(get_post_meta(19, '_wp_fixpilot_blueprint', true) === '');

$draft = $controller->create_draft(200, [
    'expected_version' => 1,
    'expected_structure_hash' => $captured['structure_hash'],
    'idempotency_key' => 'proposal-123',
    'replacements' => ['field-title' => 'Nieuwe titel'],
    'seo' => ['title' => 'SEO titel', 'description' => 'SEO omschrijving', 'keyword' => 'dsg revisie'],
]);
assert($draft['status'] === 'draft');
assert(get_post($draft['wordpress_object_id'])->post_type === 'page');
assert(get_post_meta($draft['wordpress_object_id'], '_wp_fixpilot_blueprint', true) === '');
```

- [ ] **Step 2: Run lifecycle test and verify RED**

Run:

```bash
docker run --rm -v "$PWD/plugin/wp-fixpilot-bridge:/app" -w /app php:8.2-cli php -d zend.assertions=1 -d assert.exception=1 tests/blueprint-test.php
```

Expected: FAIL because `WPFixPilot_Blueprint_Controller` is undefined.

- [ ] **Step 3: Implement the safe post cloner**

```php
final class WPFixPilot_Post_Cloner
{
    private const EXCLUDED_META = [
        '_edit_lock', '_edit_last', '_wp_old_slug', '_wp_fixpilot_idempotency_key',
        '_wp_fixpilot_source_template', '_wp_fixpilot_blueprint',
    ];

    public function clone_page(
        int $sourceId,
        string $title,
        bool $asBlueprint,
        array $allowedMetaKeys
    ): int|WP_Error
    {
        $source = get_post($sourceId);
        if (!$source instanceof WP_Post || $source->post_type !== 'page') {
            return new WP_Error('wp_fixpilot_source_missing', 'Bronpagina niet gevonden.', ['status' => 404]);
        }
        $newId = wp_insert_post([
            'post_type' => 'page',
            'post_status' => 'draft',
            'post_title' => $title,
            'post_content' => (string) $source->post_content,
            'post_excerpt' => (string) $source->post_excerpt,
            'post_parent' => (int) $source->post_parent,
            'menu_order' => (int) $source->menu_order,
        ], true);
        if (is_wp_error($newId)) {
            return $newId;
        }
        $allowed = array_unique(array_merge(
            ['_thumbnail_id', '_wp_page_template'],
            $allowedMetaKeys
        ));
        foreach ((array) get_post_meta($sourceId) as $key => $values) {
            if (
                in_array($key, self::EXCLUDED_META, true)
                || !in_array($key, $allowed, true)
            ) {
                continue;
            }
            foreach ((array) $values as $value) {
                add_post_meta((int) $newId, $key, maybe_unserialize($value));
            }
        }
        if ($asBlueprint) {
            update_post_meta((int) $newId, '_wp_fixpilot_blueprint', '1');
        }
        return (int) $newId;
    }
}
```

- [ ] **Step 4: Implement controller validation and idempotency**

`capture()` must call `clone_page()` with `clone_meta_keys()`, inspect the clone, store
source ID, builder, version,
and structure hash as postmeta, and delete the clone if schema extraction fails.
`create_draft()` must compare version/hash with `hash_equals`, reject unknown replacement
IDs, clone the blueprint, apply replacements, write SEO metadata, and delete partial
drafts after any error.

- [ ] **Step 5: Register authenticated REST routes**

```php
register_rest_route(self::NAMESPACE, '/blueprints', [
    'methods' => WP_REST_Server::CREATABLE,
    'callback' => [$this, 'capture_blueprint'],
    'permission_callback' => [$this->auth, 'authorize'],
]);
register_rest_route(self::NAMESPACE, '/blueprints/(?P<id>\d+)', [
    [
        'methods' => WP_REST_Server::READABLE,
        'callback' => [$this, 'read_blueprint'],
        'permission_callback' => [$this->auth, 'authorize'],
    ],
    [
        'methods' => WP_REST_Server::DELETABLE,
        'callback' => [$this, 'delete_blueprint'],
        'permission_callback' => [$this->auth, 'authorize'],
    ],
]);
register_rest_route(self::NAMESPACE, '/blueprints/(?P<id>\d+)/drafts', [
    'methods' => WP_REST_Server::CREATABLE,
    'callback' => [$this, 'create_blueprint_draft'],
    'permission_callback' => [$this->auth, 'authorize'],
]);
```

- [ ] **Step 6: Verify and commit**

Run the lifecycle test plus `find plugin/wp-fixpilot-bridge -name '*.php' -print0 | xargs -0 -n1 php -l` in PHP 8.2.

```bash
git add plugin/wp-fixpilot-bridge
git commit -m "feat: capture managed wordpress blueprints"
```

### Task 3: Extract and Replace Complete Builder Content

**Files:**
- Create: `plugin/wp-fixpilot-bridge/tests/blueprint-adapters-test.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-acf-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-elementor-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-wpbakery-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-bricks-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/builder-adapters/class-gutenberg-adapter.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php`

**Interfaces:**
- Consumes: `WPFixPilot_Blueprint_Adapter` and lifecycle controller from Task 2.
- Produces: `uses_page(int): bool`, `clone_meta_keys(int): array`, `schema(int): array`, `structure_hash(int): string`, and `apply_replacements(int, array, array): bool|WP_Error`.
- Produces schema shape `{schema_version: blueprint-v1, blocks: BlueprintBlock[]}`.

- [ ] **Step 1: Write a shared adapter contract test**

```php
foreach ($fixtures as $builder => $fixture) {
    $adapter = $adapters[$builder];
    assert($adapter->uses_page($fixture['post_id']) === true);
    $schema = $adapter->schema($fixture['post_id']);
    assert($schema['schema_version'] === 'blueprint-v1');
    assert(count($schema['blocks']) === $fixture['block_count']);
    assert($schema['blocks'][0]['fields'][0]['id'] !== '');
    assert($adapter->apply_replacements(
        $fixture['post_id'],
        $schema,
        [$schema['blocks'][0]['fields'][0]['id'] => 'Nieuwe tekst']
    ) === true);
    assert($fixture['read_first_text']() === 'Nieuwe tekst');
    assert($fixture['read_structure']() === $fixture['expected_structure']);
}
```

- [ ] **Step 2: Run test and verify RED**

Expected: FAIL because the shared interface and methods do not exist.

- [ ] **Step 3: Implement the interface and stable field IDs**

```php
interface WPFixPilot_Blueprint_Adapter
{
    public function key(): string;
    public function is_active(): bool;
    public function uses_page(int $postId): bool;
    public function clone_meta_keys(int $postId): array;
    public function schema(int $postId): array|WP_Error;
    public function structure_hash(int $postId): string;
    public function apply_replacements(
        int $postId,
        array $schema,
        array $replacements
    ): bool|WP_Error;
}

function wpfixpilot_field_id(string $builder, string $path): string
{
    return $builder . '-' . substr(hash('sha256', $path), 0, 20);
}
```

- [ ] **Step 4: Implement ACF block-level schema**

Group every flexible-content row as one `BlueprintBlock`. Traverse ACF field definitions
and current values together so empty text fields remain available. Include nested groups
and repeaters for text, textarea, WYSIWYG, and URL leaves. Keep image, file, boolean,
choice, number, relationship, and layout keys out of replacements. `clone_meta_keys()`
returns every top-level ACF field name plus its underscore-prefixed field-key reference.
Include the ACF field key/name path in each schema field and update the complete copied
top-level ACF value once after applying all replacements.

- [ ] **Step 5: Implement the other four adapters**

- Elementor: inspect `_elementor_data`, use element IDs plus setting paths, and lock
  widget type, responsive settings, media, and style values.
- WPBakery: parse the shortcode tree, expose text attributes and enclosed text, then
  serialize the unchanged tree with replacements.
- Bricks: inspect `_bricks_page_content_2`, use element IDs plus setting paths, and lock
  element names, parent IDs, media, and styles.
- Gutenberg: use `parse_blocks()` and `serialize_blocks()`, expose text/HTML attributes,
  and preserve block names, nesting, media IDs, and reusable references.

- [ ] **Step 6: Verify structure preservation and commit**

Run all plugin tests in PHP 8.2. Expected: each adapter changes only the selected text
and returns the same normalized structure before and after.

```bash
git add plugin/wp-fixpilot-bridge/includes/builder-adapters plugin/wp-fixpilot-bridge/tests/blueprint-adapters-test.php plugin/wp-fixpilot-bridge/includes/class-blueprint-controller.php
git commit -m "feat: add builder blueprint adapters"
```

### Task 4: Add Backend Blueprint CRUD And Bridge Client

**Files:**
- Create: `backend/app/api/routes/page_blueprints.py`
- Create: `backend/tests/page_blueprints/conftest.py`
- Create: `backend/tests/page_blueprints/test_routes.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/domains/wordpress/client.py`

**Interfaces:**
- Produces backend routes from the design spec.
- Consumes WordPress responses containing `wordpress_blueprint_id`, `version`, `structure_hash`, and `content_schema`.

- [ ] **Step 1: Write failing route tests**

```python
def captured_blueprint() -> dict:
    return {
        "wordpress_blueprint_id": 901,
        "source_page_id": 19,
        "builder": "acf",
        "seo_plugin": "yoast",
        "version": 1,
        "structure_hash": "hash-v1",
        "content_schema": valid_schema(),
        "status": "ready",
    }


class FakeBlueprintBridge:
    def __init__(self, captured: dict) -> None:
        self.captured = captured

    def capture_blueprint(self, payload: dict) -> dict:
        assert payload["source_page_id"] == 19
        return self.captured


def test_captures_lists_and_sets_default_blueprint(client, auth_as, projects, monkeypatch):
    auth_as(projects.member)
    bridge = FakeBlueprintBridge(captured_blueprint())
    monkeypatch.setattr(page_blueprints, "_bridge", lambda session, project_id: bridge)

    created = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints",
        json={
            "name": "Dienstpagina",
            "page_type": "service",
            "source_wordpress_page_id": "template-page",
        },
    )
    assert created.status_code == 201
    blueprint_id = created.json()["id"]
    assert created.json()["builder"] == "acf"
    assert created.json()["state"] == "ready"

    defaulted = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/{blueprint_id}/set-default"
    )
    assert defaulted.status_code == 200
    assert defaulted.json()["is_default_for_page_type"] is True

    versioned = client.post(
        f"/projects/{projects.member_project.id}/page-blueprints/{blueprint_id}/new-version"
    )
    assert versioned.status_code == 201
    assert versioned.json()["version"] == 2
    assert versioned.json()["supersedes_id"] == blueprint_id
```

- [ ] **Step 2: Run route tests and verify RED**

Expected: 404 because the router is not registered.

- [ ] **Step 3: Add bridge client methods**

```python
def capture_blueprint(self, payload: dict) -> dict:
    return self._post("blueprints", payload)

def blueprint(self, wordpress_blueprint_id: int) -> dict:
    return self._get(f"blueprints/{wordpress_blueprint_id}")

def create_blueprint_draft(self, wordpress_blueprint_id: int, payload: dict) -> dict:
    return self._post(f"blueprints/{wordpress_blueprint_id}/drafts", payload)

def delete_blueprint(self, wordpress_blueprint_id: int) -> dict:
    return self._delete(f"blueprints/{wordpress_blueprint_id}")
```

- [ ] **Step 4: Implement manager-only CRUD routes**

Capture must resolve the source `WordPressPage`, call the bridge, validate
`BlueprintSchema`, persist a ready blueprint, and return 201. Validation must compare
the current bridge hash/schema with the stored version. Delete must reject blueprints
referenced by proposals and remove the WordPress clone before deleting the registry.
`PUT /page-blueprints/{blueprint_id}` accepts only name, page type, and semantic-role
changes for existing block IDs; field IDs and builder paths remain immutable.
`POST /new-version` captures a fresh WordPress clone, increments `version`, sets
`supersedes_id`, leaves the previous row unchanged, and transfers the default flag only
after the new version validates successfully.

- [ ] **Step 5: Verify and commit**

Run: `cd backend && ruff check app tests alembic && pytest tests/page_blueprints -q`

```bash
git add backend/app/api/routes/page_blueprints.py backend/app/main.py backend/app/domains/wordpress/client.py backend/tests/page_blueprints
git commit -m "feat: expose project blueprint api"
```

### Task 5: Build Blueprint Management UI

**Files:**
- Create: `frontend/src/features/blueprints/BlueprintSettingsPanel.tsx`
- Create: `frontend/src/features/blueprints/BlueprintSettingsPanel.test.tsx`
- Create: `frontend/src/features/blueprints/BlueprintOutline.tsx`
- Create: `frontend/src/features/blueprints/BlueprintOutline.test.tsx`
- Modify: `frontend/src/features/settings/PagePackageSettingsPanel.tsx`
- Modify: `frontend/src/features/settings/AiSettingsPanel.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes backend blueprint CRUD routes.
- Produces a blueprint list, creation form, grouped outline, default action, version state, and validation action.

- [ ] **Step 1: Write failing UI tests**

```tsx
it("creates a blueprint from a reference page and shows grouped blocks", async () => {
  render(<BlueprintSettingsPanel projectId="project-1" />);
  await user.type(screen.getByLabelText("Blueprintnaam"), "Dienstpagina");
  await user.selectOptions(screen.getByLabelText("Paginatype"), "service");
  await user.selectOptions(screen.getByLabelText("Referentiepagina"), "page-19");
  await user.click(screen.getByRole("button", { name: "Blueprint maken" }));

  expect(await screen.findByText("Hero (algemeen)")).toBeInTheDocument();
  expect(screen.getByText("Symptomen")).toBeInTheDocument();
  expect(screen.getByText("Klaar voor conceptpagina's")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run Vitest and verify RED**

Run: `cd frontend && npm test -- BlueprintSettingsPanel.test.tsx --run`

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement creation and list states**

The form must contain name, page type, and reference page. Builder and SEO plugin are
read-only detected results. Show `capture_required`, `capturing`, `ready`, `stale`, and `invalid` badges,
the blueprint version, source page, and one default button per page type.

- [ ] **Step 4: Implement grouped outline review**

Render blocks as expandable rows with layout label, semantic role selector, and nested
editable fields. Saving roles calls `PUT /page-blueprints/{blueprint_id}`. Images and
locked structural settings appear as a preserved summary,
not as replacement controls. Remove the six generic mapping selects when at least one
managed blueprint exists; keep the old panel under a migration notice otherwise.

- [ ] **Step 5: Verify and commit**

Run: `cd frontend && npm test -- --run && npm run lint && npm run build`

```bash
git add frontend/src/features/blueprints frontend/src/features/settings frontend/src/styles.css
git commit -m "feat: manage project page blueprints"
```

### Task 6: Generate Schema-Keyed AI Replacements

**Files:**
- Modify: `backend/app/domains/page_packages/schemas.py`
- Modify: `backend/app/domains/page_packages/generation.py`
- Modify: `backend/app/domains/recommendations/openai_provider.py`
- Modify: `backend/app/domains/recommendations/anthropic_provider.py`
- Modify: `backend/app/domains/recommendations/gemini_provider.py`
- Modify: `backend/app/domains/recommendations/openai_compatible_provider.py`
- Modify: `backend/tests/page_packages/test_generation.py`
- Modify: `backend/tests/recommendations/test_openai_provider.py`
- Modify: `backend/tests/recommendations/test_anthropic_provider.py`
- Modify: `backend/tests/recommendations/test_gemini_provider.py`
- Modify: `backend/tests/recommendations/test_openai_compatible_provider.py`

**Interfaces:**
- Produces: `GeneratedBlueprintPackage`, `FieldReplacement`, and `validate_blueprint_replacements()`.
- Consumes: `BlueprintSchema`, company profile, project prompt, opportunity, and approved links.

- [ ] **Step 1: Write failing contract tests**

```python
def blueprint_context() -> PagePackageContext:
    return PagePackageContext(
        keyword="dsg revisie schiedam",
        search_volume=320,
        intent="commercial",
        company_context="SHM Transmissie in Schiedam",
        project_domain="https://member.example",
        internal_link_candidates=[
            InternalLink(anchor="Transmissie diagnose", url="/transmissie-diagnose/")
        ],
        approved_cta_urls=["/offerte-aanvragen/"],
        blueprint_schema=BlueprintSchema.model_validate(valid_schema()),
    )


def package(
    *,
    field_id: str = "acf-title",
    url: str = "/offerte-aanvragen/",
) -> GeneratedBlueprintPackage:
    return GeneratedBlueprintPackage(
        title="DSG revisie specialist Schiedam",
        slug="dsg-revisie-schiedam",
        seo_title="DSG revisie Schiedam door een specialist",
        meta_description="Laat uw DSG onderzoeken en gericht reviseren door SHM Transmissie in Schiedam.",
        focus_keyword="dsg revisie schiedam",
        replacements=[
            FieldReplacement(field_id=field_id, value="DSG revisie Schiedam"),
            FieldReplacement(field_id="acf-cta-url", value=url),
        ],
        internal_links=[
            InternalLink(anchor="Transmissie diagnose", url="/transmissie-diagnose/")
        ],
    )


def test_accepts_only_known_text_fields_and_approved_urls():
    context = blueprint_context()
    generated = GeneratedBlueprintPackage(
        title="DSG revisie specialist Schiedam",
        slug="dsg-revisie-schiedam",
        seo_title="DSG revisie Schiedam door een specialist",
        meta_description="Laat uw DSG onderzoeken en gericht reviseren door SHM Transmissie in Schiedam.",
        focus_keyword="dsg revisie schiedam",
        replacements=[
            FieldReplacement(field_id="acf-title", value="DSG revisie Schiedam"),
            FieldReplacement(field_id="acf-cta-url", value="/offerte-aanvragen/"),
        ],
        internal_links=[InternalLink(anchor="Transmissie diagnose", url="/transmissie-diagnose/")],
    )
    validated = validate_blueprint_replacements(generated, context)
    assert validated.replacements[0].field_id == "acf-title"


def test_rejects_unknown_field_media_and_unapproved_url():
    with pytest.raises(ValueError, match="unknown blueprint field"):
        validate_blueprint_replacements(package(field_id="image-1"), blueprint_context())
    with pytest.raises(ValueError, match="URL is not approved"):
        validate_blueprint_replacements(package(url="https://outside.example"), blueprint_context())
```

- [ ] **Step 2: Run tests and verify RED**

Expected: imports fail because replacement models do not exist.

- [ ] **Step 3: Add replacement models and context**

```python
class FieldReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    field_id: str = Field(min_length=3, max_length=128)
    value: str = Field(max_length=20_000)


class GeneratedBlueprintPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=10, max_length=180)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    seo_title: str = Field(min_length=20, max_length=70)
    meta_description: str = Field(min_length=70, max_length=170)
    focus_keyword: str = Field(min_length=3, max_length=160)
    replacements: list[FieldReplacement] = Field(min_length=1)
    internal_links: list[InternalLink] = Field(default_factory=list, max_length=12)
```

- [ ] **Step 4: Replace the page-package prompt contract**

The system prompt must say: preserve every block and field ID, return one replacement
for each required schema text field, respect per-field type and max length, never return
media/layout/style data, use only approved URLs, and follow project context without
inventing claims. Update OpenAI, Anthropic, Gemini, and OpenAI-compatible providers to
parse `GeneratedBlueprintPackage`.

- [ ] **Step 5: Verify and commit**

Run all page-package and provider tests.

```bash
git add backend/app/domains/page_packages backend/app/domains/recommendations backend/tests/page_packages backend/tests/recommendations
git commit -m "feat: generate blueprint field replacements"
```

### Task 7: Generate And Create Drafts From Default Blueprints

**Files:**
- Modify: `backend/app/api/routes/page_packages.py`
- Modify: `backend/tests/page_packages/test_proposal_routes.py`
- Modify: `backend/tests/page_packages/test_provider_page_packages.py`

**Interfaces:**
- Consumes the default ready `PageBlueprint` for an opportunity page type.
- Produces proposals with blueprint ID/version/hash snapshots and bridge draft payloads.

- [ ] **Step 1: Write failing proposal tests**

```python
def test_proposal_uses_requested_page_type_default_blueprint(client, prepared_blueprint_project):
    response = client.post(
        f"/projects/{prepared_blueprint_project.id}/keyword-opportunities/opportunity-new/page-proposal",
        json={"page_type": "service"},
    )
    assert response.status_code == 202
    proposal = wait_for_proposal(client, response.json()["id"])
    assert proposal["blueprint"]["name"] == "Dienstpagina"
    assert proposal["blueprint"]["version"] == 2
    assert proposal["config_snapshot"]["structure_hash"] == "hash-v2"


def test_draft_payload_contains_only_validated_replacements(client, approved_proposal, bridge):
    created = client.post(
        f"/projects/{approved_proposal.project_id}/page-proposals/{approved_proposal.id}/create-draft"
    )
    assert created.status_code == 200
    assert bridge.payload["expected_version"] == 2
    assert bridge.payload["expected_structure_hash"] == "hash-v2"
    assert bridge.payload["replacements"] == {"acf-title": "Nieuwe titel"}
```

- [ ] **Step 2: Run tests and verify RED**

Expected: proposal still reads `ProjectPagePackageSettings` and has no blueprint data.

- [ ] **Step 3: Select blueprint and build generation context**

Add `PageProposalRequest` with required `page_type` limited to `service`, `brand`,
`location`, `blog`, or `generic`. Require one `ready` default blueprint for that explicit
page type. Put the full validated content schema and immutable version/hash in
`PagePackageContext` and the proposal snapshot. The frontend must require this selection
before enabling generation.

- [ ] **Step 4: Replace draft call and stale checks**

Before approval and draft creation, read the current WordPress blueprint and compare
version/hash. Mark the backend blueprint `stale` and return HTTP 409 on a mismatch.
Send only replacements, SEO fields, approved internal links, idempotency key, expected
version, and expected hash to `create_blueprint_draft()`.

- [ ] **Step 5: Verify and commit**

Run: `cd backend && pytest tests/page_packages tests/page_blueprints -q`

```bash
git add backend/app/api/routes/page_packages.py backend/tests/page_packages
git commit -m "feat: create drafts from immutable blueprints"
```

### Task 8: Review Complete Blueprint Content In The Frontend

**Files:**
- Modify: `frontend/src/features/page-packages/PagePackageReview.tsx`
- Modify: `frontend/src/features/page-packages/PagePackageReview.test.tsx`
- Modify: `frontend/src/routes/dashboard/OpportunitiesPage.tsx`
- Modify: `frontend/src/routes/dashboard/OpportunitiesPage.test.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes proposal blueprint summary, grouped schema, and replacements.
- Produces editable approved values without exposing layout/media controls.

- [ ] **Step 1: Write failing review tests**

```tsx
it("shows the selected blueprint and all replacement fields grouped by block", async () => {
  render(<PagePackageReview projectId="project-1" proposalId="proposal-1" />);
  expect(await screen.findByText("Dienstpagina · versie 2")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Hero (algemeen)" })).toBeInTheDocument();
  expect(screen.getByLabelText("Titel")).toHaveValue("DSG revisie Schiedam");
  expect(screen.getByText("Afbeeldingen en vormgeving blijven uit de blueprint behouden.")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test and verify RED**

Expected: blueprint version and grouped fields are absent.

- [ ] **Step 3: Implement grouped replacement editing**

Show blueprint name, version, page type, and source page. Group fields by original block
order. Render plain inputs, rich-text textareas, and allowlisted URL selectors according
to field type. Keep title, slug, SEO title, description, and focus keyword editable.
Never render media, layout, style, row count, or widget-type inputs.

- [ ] **Step 4: Add opportunity blueprint visibility**

Show the selected page type and default blueprint before generation. Disable generation
with a direct settings link when no ready default exists.

- [ ] **Step 5: Verify and commit**

Run full frontend tests, lint, and build.

```bash
git add frontend/src/features/page-packages frontend/src/routes/dashboard/OpportunitiesPage.tsx frontend/src/routes/dashboard/OpportunitiesPage.test.tsx frontend/src/styles.css
git commit -m "feat: review complete blueprint content"
```

### Task 9: Migrate, Release, And Prove The SHM ACF Flow

**Files:**
- Modify: `backend/app/domains/page_blueprints/service.py`
- Modify: `backend/tests/page_blueprints/test_migration.py`
- Modify: `docs/operations.md`
- Modify: `plugin/wp-fixpilot-bridge/wp-fixpilot-bridge.php`
- Modify: `plugin/wp-fixpilot-bridge/includes/class-rest-controller.php`

**Interfaces:**
- Produces `LegacyBlueprintCandidate`, an in-memory DTO derived from valid legacy settings; it does not create an incomplete `PageBlueprint` database row.
- Migrates valid legacy settings into a capture-required blueprint candidate without deleting legacy data.
- Produces a versioned plugin zip and verified staging draft.

- [ ] **Step 1: Write migration test**

```python
def test_legacy_page_package_becomes_capture_required_candidate(session, legacy_settings):
    candidates = legacy_blueprint_candidates(session, legacy_settings.project_id)
    assert len(candidates) == 1
    assert candidates[0].source_wordpress_page_id == legacy_settings.template_wordpress_page_id
    assert candidates[0].state == "capture_required"
    assert legacy_settings.validation_state == "valid"
```

- [ ] **Step 2: Implement non-destructive migration helper and UI notice**

Create candidates from valid legacy settings only after the project owner opens settings.
Do not delete or invalidate legacy settings until a managed blueprint is ready and set
as default.

- [ ] **Step 3: Run complete verification**

Backend:

```bash
cd backend
ruff check app tests alembic
pytest -q
alembic upgrade head
pip-audit --skip-editable
```

Frontend:

```bash
cd frontend
npm audit --audit-level=high
npm test -- --run
npm run lint
npm run build
```

Plugin: run all PHP tests and syntax checks in PHP 8.2.

- [ ] **Step 4: Build and install the versioned bridge plugin**

Bump the plugin header and health response to `0.3.0`, build
`wp-fixpilot-bridge-0.3.0.zip`, compute SHA-256, and install it on the SHM staging
site before the end-to-end test.

- [ ] **Step 5: Execute the staging acceptance test**

1. Capture **Transmissie onderhoud** as ACF blueprint **Dienstpagina**.
2. Confirm WordPress created a marked draft blueprint with the `Algemeen productdetail`
   PHP template and complete ACF flexible-content rows.
3. Set it as default for `service` pages.
4. Generate one DataForSEO new-page proposal.
5. Review and approve replacements.
6. Create the WordPress draft.
7. Confirm identical ACF layout names, row counts, images, style/settings values, PHP
   template, and non-text metadata between blueprint and draft.
8. Confirm approved text and Yoast title, description, and focus keyword changed.
9. Confirm source page and blueprint values did not change.
10. Leave the generated page as draft.

- [ ] **Step 6: Commit, push, and verify deployment**

```bash
git add backend frontend plugin docs/operations.md
git commit -m "feat: complete managed page blueprint workflow"
git push origin main
```

Wait for all GitHub Actions jobs, Render health/migrations, and Vercel production build
to succeed. Record the commit SHA, deployment URLs, plugin SHA-256, and staging draft
edit URL in the completion report.
