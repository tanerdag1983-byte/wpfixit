# Security

- Supabase OAuth handles Google, Microsoft and passwordless email sessions.
- The API validates JWT signature, issuer and `authenticated` audience.
- Project and organization routes enforce membership and manager roles.
- Google OAuth uses one-time state records and PKCE.
- WordPress writes use timestamped HMAC requests and content-hash conflicts.
- Firecrawl webhooks require HMAC signatures and store unique event IDs.
- Provider tokens and user-supplied AI keys are encrypted at rest.
- CORS uses explicit origins; trusted hosts reject forged Host headers.
- Production API docs are disabled.

Never place service-role keys, OAuth client secrets, encryption keys or AI keys
in frontend variables. Rotate a provider credential immediately after suspected
exposure, then reconnect the affected organization.

Dependency and secret checks run in CI. Authorization, OAuth replay, webhook
replay and tenant-isolation tests must remain mandatory.
