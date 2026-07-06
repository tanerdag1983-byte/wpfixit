# Operations

## Deploy

1. Run backend and frontend verification.
2. Apply migrations through the Render pre-deploy command: `alembic upgrade head`.
3. Run `infrastructure/smoke_check.py` against the deployed API.
4. Verify Google and Microsoft login redirects from the production domain.

Render must use the Supabase PostgreSQL connection string for
`WP_FIXPILOT_DATABASE_URL`. The repository `render.yaml` runs migrations before
starting the new API release. A failed migration must stop the deployment; do
not bypass it by starting Uvicorn manually.

Before release, prove the migration chain against an empty PostgreSQL database:

```bash
cd backend
WP_FIXPILOT_DATABASE_URL="<empty-postgres-database-url>" alembic upgrade head
```

Then run the backend dependency audit in the same environment used for tests:

```bash
python -m pip install --upgrade -e '.[dev]'
python -m pip_audit --skip-editable
```

The release floors include `cryptography>=48.0.1`, `msgpack>=1.2.1`, and
`pydantic-settings>=2.14.2`. A high or critical finding blocks deployment.

## Managed Blueprint Release

The tested WordPress bridge artifact is:

```text
artifacts/wp-fixpilot-bridge-0.3.2.zip
SHA-256: 927bda866790343e371639fe5f73a8f51660a23198a9740e047b0e6626a472c2
```

Install this zip on staging before validating a managed blueprint release. The
plugin health response and plugin header must both report `0.3.2`.

Run the staging acceptance flow without publishing the generated page:

1. Capture **Transmissie onderhoud** as ACF blueprint **Dienstpagina**.
2. Confirm WordPress created a marked draft blueprint using the **Algemeen
   productdetail** PHP template and complete ACF flexible-content rows.
3. Set the blueprint as the default for `service` pages.
4. Generate a DataForSEO new-page proposal and review its replacements.
5. Approve the proposal and create the WordPress draft once.
6. Repeat the create request and confirm the same draft is returned.
7. Compare blueprint and draft: ACF layout names, row counts, images,
   style/settings values, PHP template, and non-text metadata must match.
8. Confirm approved copy plus Yoast title, description, and focus keyword were
   changed on the draft.
9. Confirm the source page and blueprint values were not modified.
10. Leave the generated page as a draft and record its WordPress edit URL.

Also test the lifecycle guard by attempting to delete an in-use blueprint. The
API must reject the deletion while a proposal or successor version references
it; no WordPress draft may be created from a deleted database blueprint.

## Monitoring

Alert on API health failures, 5xx rates, repeated OAuth failures, webhook
signature failures, sync failures and publish conflicts. Keep provider request
IDs and internal job IDs in logs, but never log tokens, prompts containing
private data or API keys.

## Recovery

Database migrations are reversible one revision at a time. WordPress publishes
have immutable change events and an explicit rollback action. Reconnect Google,
Firecrawl or AI providers after rotating credentials.

## AI Providers

Manage provider credentials in **Instellingen > AI-verbindingen**. Supported
connections are:

| Provider | Default base URL | Credential |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | OpenAI API key |
| Anthropic | `https://api.anthropic.com/v1` | Anthropic API key |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta` | Gemini API key |
| OpenAI-compatible | Provider-specific HTTPS endpoint | Provider API key |

An organization may keep multiple named connections. Each project explicitly
chooses one primary connection/model and may choose one fallback
connection/model. The fallback runs only for a translated provider failure; a
validation or application error is not hidden by trying another model. If no
project policy exists, recommendations use the deterministic rules engine.

Test a connection after creation and after credential or endpoint changes.
Monitor `last_test_status`, provider request failures and token usage. Never log
API keys, complete prompts or provider response bodies containing private data.

The company profile and custom prompt are project-specific. Changing that
context creates a new prompt version so an earlier recommendation is not reused
as though it were generated with the new instructions.

## Background Work

The current implementation executes provider synchronization through protected
API endpoints. Do not deploy a placeholder worker. Introduce a real queue
consumer and worker health signal when sync execution moves out of request
handling; only then add a Render background-worker service.
