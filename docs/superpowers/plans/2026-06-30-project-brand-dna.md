# Project Brand DNA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace each project's mutable company profile with versioned Brand DNA that is used consistently by AI generation, SEO recommendations, and DataForSEO relevance.

**Architecture:** Store immutable Brand DNA versions per project and mark exactly one version current. Migrate existing `company_profiles` into version 1, expose manager-only write and member-readable API routes, and pass a normalized `BrandDnaContext` into existing generation services. Keep legacy company-profile reads temporarily available during frontend migration, but stop writing legacy rows after Brand DNA is enabled.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL/Supabase, React, TypeScript, Vitest, Testing Library.

## Execution Gate And Roadmap Position

This is **Roadmap Task 10**. Do not start any implementation task in this plan until the
current managed-blueprint Tasks 2 through 9 are complete, independently reviewed,
deployed through GitHub/Render/Vercel, and verified with live smoke tests. The numbered
tasks below are internal subtasks of Roadmap Task 10, not replacements for current Tasks
2 through 9.

## Global Constraints

- Brand DNA belongs to exactly one project and is never inherited account-wide.
- Updating Brand DNA creates an immutable new version; old versions remain reproducible.
- Existing projects with a company profile retain their data through migration.
- Only project owners and admins may create a new Brand DNA version.
- Project members may read the current Brand DNA but not API secrets or hidden data.
- Every generated proposal stores the Brand DNA version used.
- Brand DNA changes never rewrite existing WordPress content automatically.
- Never store API keys, OAuth secrets, passwords, or database URLs in Brand DNA.
- Preserve existing recommendation and page-package behavior until each consumer is migrated.

---

### Task 1: Persist Immutable Project Brand DNA Versions

**Files:**
- Create: `backend/app/domains/brand_dna/__init__.py`
- Create: `backend/app/domains/brand_dna/models.py`
- Create: `backend/app/domains/brand_dna/schemas.py`
- Create: `backend/app/domains/brand_dna/service.py`
- Create: `backend/alembic/versions/0018_project_brand_dna.py`
- Create: `backend/tests/brand_dna/__init__.py`
- Create: `backend/tests/brand_dna/test_service.py`
- Modify: `backend/alembic/env.py`

**Interfaces:**
- Produces: `ProjectBrandDna`, `BrandDnaWrite`, `BrandDnaRead`, `BrandDnaContext`, `current_brand_dna()`, `create_brand_dna_version()`, and `brand_dna_context()`.
- Consumes: `Project` and legacy `CompanyProfile` rows during migration only.

- [ ] **Step 1: Write failing version and project-isolation tests**

```python
def payload(name: str = "SHM Transmissie") -> BrandDnaWrite:
    return BrandDnaWrite(
        brand_name=name,
        mission="Betrouwbare transmissierevisie zonder onnodige vervanging.",
        positioning="Transmissiespecialist voor Rijnmond.",
        differentiators=["In-house revisie", "1 jaar BOVAG-garantie"],
        audiences=["Particuliere autobezitters"],
        locations=["Schiedam", "Rotterdam"],
        services=["Diagnose", "Revisie"],
        tone_of_voice="Transparant, geruststellend en technisch deskundig.",
        preferred_vocabulary=["deelherstel"],
        preferred_claims=["1 jaar BOVAG-garantie"],
        forbidden_claims=["2 jaar garantie"],
        forbidden_topics=[],
        formatting_preferences=["Korte alinea's", "Concrete tussenkoppen"],
        image_style="professional_illustrations",
        custom_prompt="Gebruik alleen aantoonbare claims.",
    )


def test_creating_brand_dna_makes_immutable_versions(session, projects):
    first = create_brand_dna_version(
        session, projects.member_project, payload(), projects.member.id
    )
    second = create_brand_dna_version(
        session,
        projects.member_project,
        payload("SHM Transmissie Schiedam"),
        projects.member.id,
    )

    assert first.version == 1
    assert first.is_current is False
    assert second.version == 2
    assert second.is_current is True
    assert first.brand_name == "SHM Transmissie"
    assert current_brand_dna(session, projects.member_project.id).id == second.id


def test_brand_dna_is_never_shared_between_projects(session, projects):
    create_brand_dna_version(
        session, projects.member_project, payload(), projects.member.id
    )

    assert current_brand_dna(session, projects.admin_project.id) is None
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/brand_dna/test_service.py -q
```

Expected: collection fails because `app.domains.brand_dna` does not exist.

- [ ] **Step 3: Add strict schemas and immutable model**

```python
# backend/app/domains/brand_dna/schemas.py
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ImageStyle = Literal[
    "clean_minimal_flat",
    "professional_illustrations",
    "photorealistic",
    "stock_photo",
    "watercolor",
    "3d_render",
    "vintage",
    "abstract",
]


class BrandDnaWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    brand_name: str = Field(min_length=1, max_length=255)
    mission: str = Field(default="", max_length=5_000)
    positioning: str = Field(default="", max_length=5_000)
    differentiators: list[str] = Field(default_factory=list, max_length=100)
    audiences: list[str] = Field(default_factory=list, max_length=100)
    locations: list[str] = Field(default_factory=list, max_length=100)
    services: list[str] = Field(default_factory=list, max_length=100)
    tone_of_voice: str = Field(default="", max_length=2_000)
    preferred_vocabulary: list[str] = Field(default_factory=list, max_length=200)
    preferred_claims: list[str] = Field(default_factory=list, max_length=200)
    forbidden_claims: list[str] = Field(default_factory=list, max_length=200)
    forbidden_topics: list[str] = Field(default_factory=list, max_length=200)
    formatting_preferences: list[str] = Field(default_factory=list, max_length=100)
    image_style: ImageStyle = "professional_illustrations"
    custom_prompt: str = Field(default="", max_length=10_000)

    @field_validator(
        "differentiators",
        "audiences",
        "locations",
        "services",
        "preferred_vocabulary",
        "preferred_claims",
        "forbidden_claims",
        "forbidden_topics",
        "formatting_preferences",
    )
    @classmethod
    def normalize_lists(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        return list(dict.fromkeys(normalized))


class BrandDnaContext(BrandDnaWrite):
    project_id: str
    version: int
    content_hash: str


class BrandDnaRead(BrandDnaContext):
    id: str
    is_current: bool
    created_by: str
    created_at: datetime
```

```python
# backend/app/domains/brand_dna/models.py
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProjectBrandDna(Base):
    __tablename__ = "project_brand_dna"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_project_brand_dna_positive_version"),
        UniqueConstraint(
            "project_id", "version", name="uq_project_brand_dna_project_version"
        ),
        Index(
            "uq_project_brand_dna_current",
            "project_id",
            unique=True,
            postgresql_where=text("is_current = true"),
            sqlite_where=text("is_current = 1"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    brand_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mission: Mapped[str] = mapped_column(Text, default="", nullable=False)
    positioning: Mapped[str] = mapped_column(Text, default="", nullable=False)
    differentiators: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    audiences: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    locations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    services: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tone_of_voice: Mapped[str] = mapped_column(Text, default="", nullable=False)
    preferred_vocabulary: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    preferred_claims: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    forbidden_claims: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    forbidden_topics: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    formatting_preferences: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    image_style: Mapped[str] = mapped_column(String(64), nullable=False)
    custom_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 4: Implement deterministic hashing and version creation**

```python
# backend/app/domains/brand_dna/service.py
import hashlib
import json
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domains.brand_dna.models import ProjectBrandDna
from app.domains.brand_dna.schemas import BrandDnaContext, BrandDnaWrite
from app.domains.projects.models import Project


def _content_hash(payload: BrandDnaWrite) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def current_brand_dna(session: Session, project_id: str) -> ProjectBrandDna | None:
    return session.scalar(
        select(ProjectBrandDna).where(
            ProjectBrandDna.project_id == project_id,
            ProjectBrandDna.is_current.is_(True),
        )
    )


def create_brand_dna_version(
    session: Session,
    project: Project,
    payload: BrandDnaWrite,
    actor_id: str,
) -> ProjectBrandDna:
    version = (session.scalar(
        select(func.max(ProjectBrandDna.version)).where(
            ProjectBrandDna.project_id == project.id
        )
    ) or 0) + 1
    session.execute(
        update(ProjectBrandDna)
        .where(ProjectBrandDna.project_id == project.id)
        .values(is_current=False)
    )
    row = ProjectBrandDna(
        id=str(uuid4()),
        project_id=project.id,
        version=version,
        is_current=True,
        content_hash=_content_hash(payload),
        created_by=actor_id,
        **payload.model_dump(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def brand_dna_context(row: ProjectBrandDna) -> BrandDnaContext:
    return BrandDnaContext.model_validate(row, from_attributes=True)
```

- [ ] **Step 5: Add migration and legacy profile copy**

Create `0018_project_brand_dna.py` with frozen columns and constraints from the model.
In `upgrade()`, use `op.execute(sa.text(...))` to insert version 1 for every legacy
`company_profiles` row. Map `company_name` to `brand_name`, `description` to `mission`,
`audience` to a one-item `audiences` JSON array when non-empty, and preserve `services`,
`tone_of_voice`, and `custom_prompt`. Use `professional_illustrations` as image style.
Generate `content_hash` in a pre-migration Python data loop so every migrated row has a
real deterministic hash; do not use an empty placeholder.

Run:

```bash
cd backend
.venv/bin/alembic upgrade head
.venv/bin/ruff check app tests alembic
.venv/bin/python -m pytest tests/brand_dna/test_service.py -q
```

Expected: migration reaches `0018_project_brand_dna`, lint passes, focused tests pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add backend/app/domains/brand_dna backend/alembic backend/tests/brand_dna
git commit -m "feat: persist versioned project brand dna"
```

### Task 2: Expose Project Brand DNA API

**Files:**
- Create: `backend/app/api/routes/brand_dna.py`
- Create: `backend/tests/brand_dna/test_routes.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/api/routes/ai_settings.py`

**Interfaces:**
- Consumes: Task 1 `BrandDnaWrite`, `current_brand_dna()`, and `create_brand_dna_version()`.
- Produces: `GET /projects/{project_id}/brand-dna`, `PUT /projects/{project_id}/brand-dna`, and temporary read-compatible `GET /projects/{project_id}/company-profile`.

- [ ] **Step 1: Write failing authorization and version API tests**

```python
def test_manager_creates_new_brand_dna_version(client, auth_as, projects):
    auth_as(projects.admin)
    url = f"/projects/{projects.admin_project.id}/brand-dna"
    first = client.put(url, json=brand_dna_payload("Merk v1"))
    second = client.put(url, json=brand_dna_payload("Merk v2"))

    assert first.status_code == 200
    assert first.json()["version"] == 1
    assert second.json()["version"] == 2
    assert client.get(url).json()["brand_name"] == "Merk v2"


def test_project_member_cannot_write_brand_dna(client, auth_as, projects):
    auth_as(projects.member)
    response = client.put(
        f"/projects/{projects.member_project.id}/brand-dna",
        json=brand_dna_payload("Niet toegestaan"),
    )
    assert response.status_code == 403


def test_other_organization_cannot_read_brand_dna(client, auth_as, projects):
    auth_as(projects.outsider)
    response = client.get(f"/projects/{projects.member_project.id}/brand-dna")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests and verify RED**

Run: `cd backend && .venv/bin/python -m pytest tests/brand_dna/test_routes.py -q`

Expected: 404 for the new API route.

- [ ] **Step 3: Implement manager write and member read routes**

```python
router = APIRouter(tags=["brand-dna"])


@router.get("/projects/{project_id}/brand-dna")
def get_brand_dna(project_id: str, session: SessionDependency, user: UserDependency):
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    row = current_brand_dna(session, project.id)
    return {"configured": False} if row is None else _payload(row)


@router.put("/projects/{project_id}/brand-dna")
def put_brand_dna(
    project_id: str,
    payload: BrandDnaWrite,
    session: SessionDependency,
    user: UserDependency,
):
    project = get_project(session, user.id, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    membership = get_membership(session, user.id, project.organization_id)
    if membership is None or membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Manager role required")
    return _payload(create_brand_dna_version(session, project, payload, user.id))
```

Register the router in `backend/app/main.py`. Change the legacy company-profile GET route
to map the current Brand DNA back to its old response shape when Brand DNA exists. Change
legacy PUT to return HTTP 409 with `Use /brand-dna` once a Brand DNA row exists; projects
without Brand DNA keep the legacy route during the frontend rollout.

- [ ] **Step 4: Run API and regression tests**

```bash
cd backend
.venv/bin/ruff check app tests alembic
.venv/bin/python -m pytest tests/brand_dna tests/recommendations/test_ai_settings_routes.py -q
```

Expected: Brand DNA and legacy compatibility tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add backend/app/api/routes/brand_dna.py backend/app/api/routes/ai_settings.py backend/app/main.py backend/tests/brand_dna
git commit -m "feat: expose project brand dna api"
```

### Task 3: Use Brand DNA In AI And DataForSEO Context

**Files:**
- Create: `backend/tests/brand_dna/test_consumers.py`
- Modify: `backend/app/api/routes/priorities.py`
- Modify: `backend/app/api/routes/page_packages.py`
- Modify: `backend/app/domains/dataforseo/relevance.py`
- Modify: `backend/app/domains/recommendations/service.py`
- Modify: `backend/app/domains/page_packages/generation.py`
- Modify: `backend/app/domains/page_packages/models.py`
- Modify: `backend/app/domains/audits/models.py`
- Create: `backend/alembic/versions/0019_page_proposals_brand_dna_version.py`

**Interfaces:**
- Consumes: `BrandDnaContext` and `brand_dna_context()`.
- Produces: normalized prompt context and persisted `brand_dna_version` plus `brand_dna_hash` on new proposals.

- [ ] **Step 1: Write failing consumer and snapshot tests**

```python
def test_recommendation_prompt_uses_current_project_brand_dna(
    session, projects, prepared_page
):
    dna = create_brand_dna_version(
        session,
        projects.member_project,
        brand_dna_payload(forbidden_claims=["2 jaar garantie"]),
        projects.member.id,
    )
    context = recommendation_context(session, projects.member_project, prepared_page)

    assert context.brand_dna.version == dna.version
    assert "2 jaar garantie" in context.system_constraints


def test_proposal_persists_brand_dna_snapshot_version(client, auth_as, prepared_project):
    auth_as(prepared_project.manager)
    response = client.post(
        f"/projects/{prepared_project.id}/page-package-proposals",
        json={"page_type": "service"},
    )
    assert response.status_code == 202
    assert response.json()["brand_dna_version"] == 1
    assert len(response.json()["brand_dna_hash"]) == 64


def test_dataforseo_relevance_uses_services_and_forbidden_topics(session, projects):
    context = relevance_context(session, projects.member_project)
    assert "transmissierevisie" in context.allowed_terms
    assert "autosleutels" in context.excluded_terms
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `cd backend && .venv/bin/python -m pytest tests/brand_dna/test_consumers.py -q`

Expected: failures because consumers still load `CompanyProfile`.

- [ ] **Step 3: Add one normalized context formatter**

```python
def prompt_lines(context: BrandDnaContext) -> list[str]:
    return [
        f"Merk: {context.brand_name}",
        f"Missie: {context.mission}",
        f"Positionering: {context.positioning}",
        f"Doelgroepen: {', '.join(context.audiences)}",
        f"Locaties: {', '.join(context.locations)}",
        f"Diensten: {', '.join(context.services)}",
        f"Tone of voice: {context.tone_of_voice}",
        f"Voorkeursclaims: {', '.join(context.preferred_claims)}",
        f"Verboden claims: {', '.join(context.forbidden_claims)}",
        f"Verboden onderwerpen: {', '.join(context.forbidden_topics)}",
        f"Projectinstructie: {context.custom_prompt}",
    ]
```

Place this helper in `backend/app/domains/brand_dna/service.py` and make priorities,
page-package generation, recommendation generation, and DataForSEO relevance consume it.
Do not maintain separate prompt formatters after migration.

- [ ] **Step 4: Persist the immutable Brand DNA reference**

Add nullable `brand_dna_version: Integer` and `brand_dna_hash: String(64)` columns to
`PagePackageProposal` in `backend/app/domains/page_packages/models.py` and
`SeoRecommendation` in `backend/app/domains/audits/models.py`. Mirror all four columns in
migration `0019_page_proposals_brand_dna_version.py`. Historical proposals remain
nullable. Add an all-or-none check constraint per table so version and hash are either
both NULL or both present. New proposal services reject generation when no Brand DNA
exists and always write both values from the same current `BrandDnaContext`.

- [ ] **Step 5: Run consumer and full backend tests**

```bash
cd backend
.venv/bin/ruff check app tests alembic
.venv/bin/python -m pytest tests/brand_dna tests/dataforseo tests/recommendations tests/page_packages -q
.venv/bin/python -m pytest --import-mode=importlib -q
```

Expected: focused and full backend suites pass.

- [ ] **Step 6: Commit Task 3**

```bash
git add backend/app backend/alembic/versions/0019_page_proposals_brand_dna_version.py backend/tests
git commit -m "feat: apply brand dna to project generation"
```

### Task 4: Replace Company Profile UI With Project Brand DNA

**Files:**
- Create: `frontend/src/features/settings/BrandDnaPanel.tsx`
- Create: `frontend/src/features/settings/BrandDnaPanel.test.tsx`
- Modify: `frontend/src/features/settings/AiSettingsPanel.tsx`
- Delete: `frontend/src/features/settings/CompanyProfilePanel.tsx`
- Delete: `frontend/src/features/settings/CompanyProfilePanel.test.tsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: `GET` and `PUT /projects/{project_id}/brand-dna`.
- Produces: project-specific Brand DNA form and image-style selection.

- [ ] **Step 1: Write failing load, save, project-switch, and validation tests**

```tsx
it("loads and saves Brand DNA only for the selected project", async () => {
  apiRequest.mockResolvedValueOnce(brandDnaResponse).mockResolvedValueOnce({
    ...brandDnaResponse,
    version: 2,
  });
  render(<BrandDnaPanel projectId="project-1" />);

  expect(await screen.findByDisplayValue("SHM Transmissie")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Verboden claims"), {
    target: { value: "2 jaar garantie" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Brand DNA opslaan" }));

  await waitFor(() =>
    expect(apiRequest).toHaveBeenCalledWith(
      "/projects/project-1/brand-dna",
      expect.objectContaining({ method: "PUT" }),
    ),
  );
});


it("clears old project values before loading another project", async () => {
  const { rerender } = render(<BrandDnaPanel projectId="project-1" />);
  await screen.findByDisplayValue("SHM Transmissie");
  rerender(<BrandDnaPanel projectId="project-2" />);
  expect(screen.queryByDisplayValue("SHM Transmissie")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
cd frontend
npm test -- BrandDnaPanel.test.tsx
```

Expected: test fails because `BrandDnaPanel` does not exist.

- [ ] **Step 3: Implement the project Brand DNA form**

Build controlled fields for every `BrandDnaWrite` property. Render list properties as
newline-separated textareas, splitting on newlines and removing empty values before PUT.
Use these exact image-style option values and labels:

```typescript
const IMAGE_STYLES = [
  ["clean_minimal_flat", "Clean & Minimal Flat"],
  ["professional_illustrations", "Professional Illustrations"],
  ["photorealistic", "Photorealistic"],
  ["stock_photo", "Stock Photo Style"],
  ["watercolor", "Watercolor"],
  ["3d_render", "3D Render"],
  ["vintage", "Vintage"],
  ["abstract", "Abstract"],
] as const;
```

Show the current version and explain that saving creates a new version for this project.
Reset local state immediately when `projectId` changes, ignore stale async responses, and
display structured API validation errors rather than `[object Object]`.

- [ ] **Step 4: Replace the old panel and verify frontend**

```bash
cd frontend
npm test -- BrandDnaPanel.test.tsx AiSettingsPanel.test.tsx
npm run lint
npm run build
```

Expected: tests, lint, and production build pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add frontend/src/features/settings frontend/src/styles.css
git commit -m "feat: add project brand dna settings"
```

### Task 5: Verify Migration, Isolation, And Generation Auditability

**Files:**
- Create: `backend/tests/brand_dna/test_migration.py`
- Create: `backend/tests/brand_dna/test_auditability.py`
- Modify: `docs/superpowers/specs/2026-06-30-content-operations-intelligence-design.md`
- Modify: `HANDOFF.md`

**Interfaces:**
- Consumes all Task 1-4 Brand DNA interfaces.
- Produces release evidence and updated handoff state for the next Link Intelligence plan.

- [ ] **Step 1: Write migration and auditability tests**

```python
def test_legacy_company_profile_is_migrated_without_data_loss(migrated_session):
    row = current_brand_dna(migrated_session, "legacy-project")
    assert row.version == 1
    assert row.brand_name == "Legacy Bedrijf"
    assert row.services == ["Diagnose", "Revisie"]
    assert row.custom_prompt == "Gebruik bewijs."
    assert len(row.content_hash) == 64


def test_old_proposal_keeps_original_brand_dna_reference_after_update(
    session, prepared_proposal, projects
):
    original_version = prepared_proposal.brand_dna_version
    create_brand_dna_version(
        session,
        projects.member_project,
        brand_dna_payload("Nieuwe merkversie"),
        projects.member.id,
    )
    session.refresh(prepared_proposal)
    assert prepared_proposal.brand_dna_version == original_version
```

- [ ] **Step 2: Run complete verification**

```bash
cd backend
.venv/bin/ruff check app tests alembic
.venv/bin/alembic upgrade head
.venv/bin/python -m pytest --import-mode=importlib -q

cd ../frontend
npm test
npm run lint
npm run build
```

Expected: all commands exit 0 with no skipped Brand DNA migration or isolation tests.

- [ ] **Step 3: Update handoff and design implementation status**

Record exact migration revision, deployed API routes, frontend panel, test totals, and
remaining compatibility window in `HANDOFF.md`. In the approved design, mark only the
Project Brand DNA delivery-sequence item implemented; do not mark Link Intelligence or
other modules complete.

- [ ] **Step 4: Commit Task 5**

```bash
git add backend/tests/brand_dna docs/superpowers/specs/2026-06-30-content-operations-intelligence-design.md HANDOFF.md
git commit -m "test: verify project brand dna rollout"
```
