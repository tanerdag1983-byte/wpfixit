# Multiple AI Providers And Project Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow an organization to configure multiple OpenAI, Anthropic Claude,
Google Gemini and OpenAI-compatible connections, while each project selects an
explicit primary and optional fallback model and retains its own prompt.

**Architecture:** Replace the single organization AI settings row with named AI
connections and a project-level model policy. Provider-specific adapters expose
one stable recommendation-generator contract. A policy resolver tries only the
configured primary connection and, on provider failure, the configured fallback;
it never silently selects another provider. All credentials remain encrypted and
all generated recommendations remain proposals requiring approval.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, requests, OpenAI Python
SDK, React, TypeScript, Vitest, Testing Library.

---

## File Structure

### Backend

- `backend/app/domains/recommendations/models.py`
  Stores named organization connections, project model policy and project
  profile prompt.
- `backend/app/domains/recommendations/provider.py`
  Defines provider-neutral generator errors and contracts.
- `backend/app/domains/recommendations/openai_provider.py`
  Implements OpenAI Responses structured output.
- `backend/app/domains/recommendations/anthropic_provider.py`
  Implements Claude Messages structured JSON output.
- `backend/app/domains/recommendations/gemini_provider.py`
  Implements Gemini `generateContent` structured JSON output.
- `backend/app/domains/recommendations/openai_compatible_provider.py`
  Implements compatible `/chat/completions` JSON output.
- `backend/app/domains/recommendations/provider_factory.py`
  Builds adapters from encrypted connection records.
- `backend/app/domains/recommendations/policy.py`
  Resolves primary/fallback policy and performs bounded fallback.
- `backend/app/api/routes/ai_settings.py`
  Exposes connection CRUD, connection testing, project policy and profile APIs.
- `backend/app/api/routes/priorities.py`
  Uses the project policy resolver for recommendation generation.
- `backend/alembic/versions/0011_multi_ai_connections.py`
  Migrates the existing single connection into the new connection table.

### Frontend

- `frontend/src/features/settings/AiConnectionsPanel.tsx`
  Lists, creates, edits, tests and removes named provider connections.
- `frontend/src/features/settings/ProjectAiPolicyPanel.tsx`
  Selects primary/fallback connection and model for the active project.
- `frontend/src/features/settings/CompanyProfilePanel.tsx`
  Owns the existing project-specific company profile and prompt fields.
- `frontend/src/features/settings/AiSettingsPanel.tsx`
  Composes the three focused settings panels.

## Task 1: Persist Multiple Connections And Project Policy

**Files:**
- Modify: `backend/app/domains/recommendations/models.py`
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0011_multi_ai_connections.py`
- Test: `backend/tests/recommendations/test_ai_connection_models.py`

- [ ] **Step 1: Write the failing model test**

Create fixtures that persist two named connections for one organization and a
project policy pointing to both:

```python
def test_organization_has_multiple_ai_connections_and_project_policy(
    session,
    projects,
) -> None:
    primary = AiConnection(
        id="ai-primary",
        organization_id=projects.organization.id,
        name="OpenAI productie",
        provider="openai",
        base_url="https://api.openai.com/v1",
        encrypted_api_key="encrypted-one",
        enabled=True,
    )
    fallback = AiConnection(
        id="ai-fallback",
        organization_id=projects.organization.id,
        name="Claude fallback",
        provider="anthropic",
        base_url="https://api.anthropic.com/v1",
        encrypted_api_key="encrypted-two",
        enabled=True,
    )
    session.add_all([primary, fallback])
    session.add(
        ProjectAiPolicy(
            project_id=projects.member_project.id,
            primary_connection_id=primary.id,
            primary_model="gpt-5.4-mini",
            fallback_connection_id=fallback.id,
            fallback_model="claude-sonnet-4-5",
        )
    )
    session.commit()

    connections = session.scalars(
        select(AiConnection).where(
            AiConnection.organization_id == projects.organization.id
        )
    ).all()
    assert {item.provider for item in connections} == {"openai", "anthropic"}
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd backend
.venv/bin/pytest -q tests/recommendations/test_ai_connection_models.py
```

Expected: collection fails because `AiConnection` and `ProjectAiPolicy` do not
exist.

- [ ] **Step 3: Implement the new models**

Replace `OrganizationAiSettings` with:

```python
class AiConnection(Base):
    __tablename__ = "ai_connections"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "name",
            name="uq_ai_connection_org_name",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    default_model: Mapped[str | None] = mapped_column(String(255))
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        nullable=False,
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_status: Mapped[str | None] = mapped_column(String(24))
    last_test_message: Mapped[str | None] = mapped_column(Text)
```

Add:

```python
class ProjectAiPolicy(Base):
    __tablename__ = "project_ai_policies"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    primary_connection_id: Mapped[str] = mapped_column(
        ForeignKey("ai_connections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    primary_model: Mapped[str] = mapped_column(String(255), nullable=False)
    fallback_connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_connections.id", ondelete="SET NULL"),
    )
    fallback_model: Mapped[str | None] = mapped_column(String(255))
```

Keep `CompanyProfile` project-scoped.

- [ ] **Step 4: Create migration `0011_multi_ai_connections`**

The migration must:

1. Create `ai_connections`.
2. Create `project_ai_policies`.
3. Copy each `organization_ai_settings` row into `ai_connections` with a stable
   generated ID, name `Bestaande AI-koppeling` and its old model stored as
   `default_model`.
4. Leave projects without an explicit policy unconfigured.
5. Drop `organization_ai_settings` only after copying its rows.
6. Recreate the old table and copy one connection per organization on downgrade.

- [ ] **Step 5: Verify model and migration round trip**

Run:

```bash
.venv/bin/pytest -q tests/recommendations/test_ai_connection_models.py
.venv/bin/alembic upgrade head
.venv/bin/alembic downgrade 0010_ai_settings
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

Expected: test passes and Alembic reports `0011_multi_ai_connections (head)`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/domains/recommendations/models.py \
  backend/alembic/env.py \
  backend/alembic/versions/0011_multi_ai_connections.py \
  backend/tests/recommendations/test_ai_connection_models.py
git commit -m "feat: store multiple AI connections and project policy"
```

## Task 2: Add Connection CRUD And Credential Safety

**Files:**
- Modify: `backend/app/api/routes/ai_settings.py`
- Modify: `backend/tests/recommendations/conftest.py`
- Create: `backend/tests/recommendations/test_ai_connection_routes.py`

- [ ] **Step 1: Write failing CRUD and authorization tests**

Cover:

```python
def test_owner_creates_lists_updates_and_deletes_named_ai_connection(...):
    created = client.post(
        f"/organizations/{org_id}/ai-connections",
        json={
            "name": "Claude productie",
            "provider": "anthropic",
            "base_url": "https://api.anthropic.com/v1",
            "api_key": "secret",
        },
    )
    assert created.status_code == 201
    assert "secret" not in created.text

    listed = client.get(f"/organizations/{org_id}/ai-connections")
    assert listed.json()["items"][0]["name"] == "Claude productie"
    assert "api_key" not in listed.text
```

Also test:

- member cannot create/update/delete connections;
- updating without `api_key` preserves the encrypted key;
- duplicate names return `409`;
- a connection used as a project primary returns `409` on delete;
- credentials never appear in any response.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/recommendations/test_ai_connection_routes.py
```

Expected: `404` for missing `/ai-connections` endpoints.

- [ ] **Step 3: Implement request and response schemas**

Use:

```python
ProviderName = Literal["openai", "anthropic", "gemini", "openai_compatible"]

class AiConnectionWrite(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    provider: ProviderName
    base_url: AnyHttpUrl
    default_model: str | None = Field(default=None, max_length=255)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)
    enabled: bool = True
```

Return only ID, name, provider, base URL, default model, enabled state and last
test status.

- [ ] **Step 4: Implement endpoints**

Add:

```text
GET    /organizations/{organization_id}/ai-connections
POST   /organizations/{organization_id}/ai-connections
PUT    /organizations/{organization_id}/ai-connections/{connection_id}
DELETE /organizations/{organization_id}/ai-connections/{connection_id}
POST   /organizations/{organization_id}/ai-connections/{connection_id}/test
```

Owner/admin is required for writes and tests. Read access requires membership.
Use `encrypt_text` on every new key and never decrypt a key for serialization.
The test endpoint accepts `{"model": "provider-model-id"}`; when omitted it uses
`default_model`, and returns `422` when neither is available. Testing must use
the provider adapter's smallest valid structured request rather than assuming
every provider exposes an OpenAI-style `/models` endpoint.

- [ ] **Step 5: Remove legacy single-settings routes**

Remove:

```text
GET  /organizations/{organization_id}/ai-settings
PUT  /organizations/{organization_id}/ai-settings
POST /organizations/{organization_id}/ai-settings/test
```

Do not remove project company-profile routes.

- [ ] **Step 6: Verify GREEN**

Run:

```bash
.venv/bin/pytest -q \
  tests/recommendations/test_ai_connection_routes.py \
  tests/recommendations/test_ai_settings_routes.py
.venv/bin/ruff check app/api/routes/ai_settings.py tests/recommendations
```

Expected: all tests pass; migrate or delete legacy route assertions that no
longer represent the public API.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/ai_settings.py backend/tests/recommendations
git commit -m "feat: add secure AI connection management API"
```

## Task 3: Implement Provider-Neutral Adapters

**Files:**
- Modify: `backend/app/domains/recommendations/provider.py`
- Modify: `backend/app/domains/recommendations/openai_provider.py`
- Create: `backend/app/domains/recommendations/anthropic_provider.py`
- Create: `backend/app/domains/recommendations/gemini_provider.py`
- Create: `backend/app/domains/recommendations/openai_compatible_provider.py`
- Create: `backend/tests/recommendations/provider_contract.py`
- Create: `backend/tests/recommendations/test_anthropic_provider.py`
- Create: `backend/tests/recommendations/test_gemini_provider.py`
- Create: `backend/tests/recommendations/test_openai_compatible_provider.py`
- Modify: `backend/tests/recommendations/test_openai_provider.py`

- [ ] **Step 1: Write a shared failing provider contract**

The contract must assert that every adapter:

- receives the same `PageFacts`;
- includes project company context;
- returns `RecommendationResult`;
- preserves only known evidence IDs;
- sets `approval_state="proposed"`;
- records provider, model and token usage;
- raises `ProviderGenerationError` for malformed output or unknown evidence.

Example:

```python
def assert_provider_contract(generator, expected_provider: str) -> None:
    result = generator.generate(page_facts())
    assert result.provider == expected_provider
    assert result.approval_state == "proposed"
    assert result.evidence == ["gsc:query:1"]
```

- [ ] **Step 2: Run provider tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/recommendations/test_*_provider.py
```

Expected: import failures for the three new adapters.

- [ ] **Step 3: Add stable provider errors and validation helper**

In `provider.py` add:

```python
class ProviderGenerationError(RuntimeError):
    pass

def validated_result(
    generated: GeneratedRecommendation,
    facts: PageFacts,
    *,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> RecommendationResult:
    valid_ids = {item.id for item in facts.evidence}
    if not set(generated.evidence).issubset(valid_ids):
        raise ProviderGenerationError("Provider referenced unknown evidence")
    return RecommendationResult(
        **generated.model_dump(),
        approval_state="proposed",
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
```

- [ ] **Step 4: Refactor OpenAI to the shared validator**

Keep the Responses API structured-output call, but translate SDK/network/output
errors to `ProviderGenerationError`.

- [ ] **Step 5: Implement Anthropic adapter**

Use `requests.post` against `{base_url}/messages` with:

- `x-api-key`;
- `anthropic-version: 2023-06-01`;
- a system prompt containing the project context and approval prohibition;
- a JSON-only user payload;
- bounded timeout and no internal unbounded retries.

Parse `content[0].text` through `GeneratedRecommendation.model_validate_json`.

- [ ] **Step 6: Implement Gemini adapter**

Use:

```text
POST {base_url}/models/{model}:generateContent?key={api_key}
```

Send `responseMimeType: application/json` and a JSON schema derived from
`GeneratedRecommendation.model_json_schema()`. Parse the first candidate text.

- [ ] **Step 7: Implement OpenAI-compatible adapter**

Use:

```text
POST {base_url}/chat/completions
```

Send bearer auth, `response_format={"type": "json_object"}`, system/user
messages and the configured model. Parse `choices[0].message.content`.

- [ ] **Step 8: Verify all provider contracts**

Run:

```bash
.venv/bin/pytest -q tests/recommendations/test_*_provider.py
.venv/bin/ruff check app/domains/recommendations tests/recommendations
```

Expected: all provider contract and failure tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/domains/recommendations backend/tests/recommendations
git commit -m "feat: add Claude Gemini and compatible AI adapters"
```

## Task 4: Add Provider Factory And Explicit Fallback

**Files:**
- Create: `backend/app/domains/recommendations/provider_factory.py`
- Create: `backend/app/domains/recommendations/policy.py`
- Create: `backend/tests/recommendations/test_provider_factory.py`
- Create: `backend/tests/recommendations/test_ai_policy.py`

- [ ] **Step 1: Write failing factory tests**

Assert each provider value creates the correct adapter using the decrypted key,
configured base URL, selected model and company context.

```python
@pytest.mark.parametrize(
    ("provider", "adapter_type"),
    [
        ("openai", OpenAIRecommendationGenerator),
        ("anthropic", AnthropicRecommendationGenerator),
        ("gemini", GeminiRecommendationGenerator),
        ("openai_compatible", OpenAICompatibleRecommendationGenerator),
    ],
)
def test_factory_builds_explicit_adapter(provider, adapter_type):
    assert isinstance(build_generator(connection(provider), "model", "context"), adapter_type)
```

- [ ] **Step 2: Write failing fallback tests**

Test:

- primary success does not call fallback;
- `ProviderGenerationError` calls configured fallback once;
- no fallback returns the primary error;
- disabled connection is rejected;
- cross-organization connection IDs are rejected;
- arbitrary exceptions are not hidden as successful fallback.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest -q \
  tests/recommendations/test_provider_factory.py \
  tests/recommendations/test_ai_policy.py
```

Expected: import failures for factory and policy modules.

- [ ] **Step 4: Implement `build_generator`**

The factory accepts `AiConnection`, selected model and project context. It
decrypts the credential only while constructing an adapter.

- [ ] **Step 5: Implement `PolicyRecommendationGenerator`**

Use:

```python
class PolicyRecommendationGenerator:
    def __init__(self, primary, fallback=None) -> None:
        self.primary = primary
        self.fallback = fallback

    def generate(self, facts: PageFacts) -> RecommendationResult:
        try:
            return self.primary.generate(facts)
        except ProviderGenerationError:
            if self.fallback is None:
                raise
            return self.fallback.generate(facts)
```

Do not catch schema-validation bugs outside `ProviderGenerationError`.

- [ ] **Step 6: Verify GREEN and commit**

Run:

```bash
.venv/bin/pytest -q \
  tests/recommendations/test_provider_factory.py \
  tests/recommendations/test_ai_policy.py
```

Then:

```bash
git add backend/app/domains/recommendations/provider_factory.py \
  backend/app/domains/recommendations/policy.py \
  backend/tests/recommendations/test_provider_factory.py \
  backend/tests/recommendations/test_ai_policy.py
git commit -m "feat: resolve primary and fallback AI providers"
```

## Task 5: Add Project AI Policy API

**Files:**
- Modify: `backend/app/api/routes/ai_settings.py`
- Create: `backend/tests/recommendations/test_project_ai_policy_routes.py`

- [ ] **Step 1: Write failing project policy route tests**

Cover:

```text
GET /projects/{project_id}/ai-policy
PUT /projects/{project_id}/ai-policy
```

The PUT body is:

```json
{
  "primary_connection_id": "ai-primary",
  "primary_model": "gpt-5.4-mini",
  "fallback_connection_id": "ai-fallback",
  "fallback_model": "claude-sonnet-4-5"
}
```

Test manager authorization, same-organization validation, disabled connection
rejection, fallback model requirement and clearing an existing fallback.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest -q tests/recommendations/test_project_ai_policy_routes.py
```

Expected: `404` because the policy routes do not exist.

- [ ] **Step 3: Implement schemas and routes**

Return connection display names and provider types with the selected model IDs,
but never return credentials.

- [ ] **Step 4: Verify policy and profile isolation**

Run:

```bash
.venv/bin/pytest -q \
  tests/recommendations/test_project_ai_policy_routes.py \
  tests/recommendations/test_ai_settings_routes.py \
  tests/projects/test_project_routes.py
```

Expected: policy and company profile remain project-scoped and tenant-safe.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/ai_settings.py \
  backend/tests/recommendations/test_project_ai_policy_routes.py
git commit -m "feat: add project AI model policy API"
```

## Task 6: Use Project Policy For Recommendation Generation

**Files:**
- Modify: `backend/app/api/routes/priorities.py`
- Modify: `backend/app/domains/audits/models.py`
- Create: `backend/tests/recommendations/test_policy_recommendation_routes.py`
- Create: `backend/alembic/versions/0012_recommendation_prompt_version.py`

- [ ] **Step 1: Write failing route tests**

Test:

- selected primary provider generates the recommendation;
- fallback provider is recorded when primary fails;
- missing project policy uses rule-based recommendations;
- generated recommendation records provider/model and prompt version;
- generated output remains `proposed`;
- no publication endpoint is called.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/pytest -q \
  tests/recommendations/test_policy_recommendation_routes.py
```

Expected: recommendation generation still reads the removed
`OrganizationAiSettings`.

- [ ] **Step 3: Add prompt version persistence**

Add nullable `prompt_version` to `seo_recommendations`. Build it as a SHA-256
hash of the normalized project profile fields and custom prompt. Create
migration `0012_recommendation_prompt_version`.

- [ ] **Step 4: Replace `_recommendation_generator`**

Load `ProjectAiPolicy`, verify both connections belong to the project
organization, build primary/fallback adapters and wrap them in
`PolicyRecommendationGenerator`. If no policy is configured, use
`RuleBasedRecommendationGenerator`.

- [ ] **Step 5: Verify migrations and route behavior**

Run:

```bash
.venv/bin/alembic upgrade head
.venv/bin/pytest -q \
  tests/recommendations/test_policy_recommendation_routes.py \
  tests/priorities/test_routes.py
```

Expected: all pass and recommendations remain proposals.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/priorities.py \
  backend/app/domains/audits/models.py \
  backend/alembic/versions/0012_recommendation_prompt_version.py \
  backend/tests/recommendations/test_policy_recommendation_routes.py
git commit -m "feat: generate recommendations with project AI policy"
```

## Task 7: Build AI Connections And Project Policy UI

**Files:**
- Create: `frontend/src/features/settings/AiConnectionsPanel.tsx`
- Create: `frontend/src/features/settings/AiConnectionsPanel.test.tsx`
- Create: `frontend/src/features/settings/ProjectAiPolicyPanel.tsx`
- Create: `frontend/src/features/settings/ProjectAiPolicyPanel.test.tsx`
- Create: `frontend/src/features/settings/CompanyProfilePanel.tsx`
- Create: `frontend/src/features/settings/CompanyProfilePanel.test.tsx`
- Modify: `frontend/src/features/settings/AiSettingsPanel.tsx`
- Modify: `frontend/src/features/settings/AiSettingsPanel.test.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing connection-panel tests**

Test that the owner can:

- see multiple named connections;
- select OpenAI, Claude, Gemini or compatible API;
- add a connection without exposing an existing key;
- test a connection;
- edit its name/model endpoint;
- remove an unused connection;
- see backend validation errors.

- [ ] **Step 2: Write failing project-policy tests**

Test that:

- primary and fallback connection selects use loaded connection IDs;
- each connection has a separate model input;
- fallback can be disabled;
- saving sends the exact policy payload;
- the active project ID is used.

- [ ] **Step 3: Run tests and verify RED**

Run:

```bash
cd frontend
npm test -- --run \
  src/features/settings/AiConnectionsPanel.test.tsx \
  src/features/settings/ProjectAiPolicyPanel.test.tsx \
  src/features/settings/CompanyProfilePanel.test.tsx
```

Expected: import failures for the new components.

- [ ] **Step 4: Extract the existing project profile form**

Move company name, description, audience, services, tone and custom prompt from
`AiSettingsPanel` into `CompanyProfilePanel`. Preserve the current GET/PUT
project profile API behavior.

- [ ] **Step 5: Implement `AiConnectionsPanel`**

Provider defaults:

```typescript
const providerDefaults = {
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  gemini: "https://generativelanguage.googleapis.com/v1beta",
  openai_compatible: "",
} as const;
```

Existing keys display only `API-key opgeslagen`; editing a connection sends
`api_key` only when the user enters a replacement.

- [ ] **Step 6: Implement `ProjectAiPolicyPanel`**

Load organization connections and project policy in parallel. Disable policy
save until a primary connection and model are selected. Exclude the primary
connection from the fallback select only when the same connection/model pair
would be duplicated.

- [ ] **Step 7: Compose the settings screen**

`AiSettingsPanel` renders:

1. AI Connections;
2. Project AI Policy;
3. Company Profile And Prompt.

Keep the existing visual system and responsive single-column mobile layout.

- [ ] **Step 8: Verify GREEN**

Run:

```bash
npm test -- --run src/features/settings
npm run lint
npm run build
```

Expected: all settings tests, lint and build pass.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/features/settings frontend/src/styles.css
git commit -m "feat: add multi-provider AI settings interface"
```

## Task 8: End-To-End Verification And Documentation

**Files:**
- Modify: `.env.example`
- Modify: `docs/security.md`
- Modify: `docs/operations.md`
- Modify: `docs/deployment.md`

- [ ] **Step 1: Document provider behavior**

Document:

- supported providers;
- required base URLs and credentials;
- organization connection versus project policy ownership;
- primary/fallback behavior;
- credential rotation;
- project prompt isolation;
- approval remains mandatory for all recommendations.

- [ ] **Step 2: Run backend verification**

Run:

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/pytest -q
.venv/bin/alembic current
.venv/bin/pip-audit --skip-editable
```

Expected: zero lint errors, zero test failures, Alembic at
`0012_recommendation_prompt_version`, no known dependency vulnerabilities.

- [ ] **Step 3: Run frontend verification**

Run:

```bash
cd frontend
npm run lint
npm test -- --run
npm run build
npm audit --audit-level=high
```

Expected: zero failures and zero high-severity vulnerabilities.

- [ ] **Step 4: Run plugin regression tests**

Run:

```bash
cd plugin/wp-fixpilot-bridge
docker run --rm -v "$PWD:/app" -w /app php:8.2-cli \
  sh -lc 'php tests/auth-test.php && php tests/change-controller-test.php'
```

Expected:

```text
auth tests passed
change controller tests passed
```

- [ ] **Step 5: Browser verification**

Open `http://127.0.0.1:5173/#settings` in the in-app browser and verify:

- desktop and mobile layouts;
- four provider choices;
- multiple connection cards;
- primary/fallback project policy;
- project-specific prompt;
- no credential is rendered after save.

- [ ] **Step 6: Final commit**

```bash
git add .env.example docs
git commit -m "docs: explain multi-provider AI operations"
```

## Completion Criteria

Phase 1 is complete only when:

- an organization can safely store multiple named AI connections;
- OpenAI, Claude, Gemini and OpenAI-compatible adapters pass one contract;
- a project explicitly selects primary and optional fallback models;
- the fallback runs only after a stable provider failure;
- each project retains its own profile and prompt;
- recommendation records identify provider, model and prompt version;
- all recommendations remain approval-required proposals;
- credentials never appear in API or frontend responses;
- migrations round-trip and all backend, frontend and plugin tests pass.
