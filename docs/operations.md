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

## Background Work

The current implementation executes provider synchronization through protected
API endpoints. Do not deploy a placeholder worker. Introduce a real queue
consumer and worker health signal when sync execution moves out of request
handling; only then add a Render background-worker service.
