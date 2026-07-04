### Task 9: Migrate, Release, And Prove The SHM ACF Flow

Required PostgreSQL concurrency regression: race blueprint deletion against creation of
a proposal and a successor version. Prove the Task 4 `SELECT ... FOR UPDATE` lock blocks
new foreign-key references until deletion commits and prevents WordPress/database drift.

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
