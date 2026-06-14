# Operations

## Deploy

1. Run backend and frontend verification.
2. Apply migrations through the Render pre-deploy command.
3. Run `infrastructure/smoke_check.py` against the deployed API.
4. Verify Google and Microsoft login redirects from the production domain.

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
