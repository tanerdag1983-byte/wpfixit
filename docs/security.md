# Security

- Supabase OAuth handles Google, Microsoft and passwordless email sessions.
- The API validates JWT signature, issuer and `authenticated` audience.
- Project and organization routes enforce membership and manager roles.
- Google OAuth uses one-time state records and PKCE.
- WordPress writes use timestamped HMAC requests and content-hash conflicts.
- Firecrawl webhooks require HMAC signatures and store unique event IDs.
- Provider tokens and user-supplied AI keys are encrypted at rest.
- AI connection responses never contain plaintext or encrypted credentials.
- CORS uses explicit origins; trusted hosts reject forged Host headers.
- Production API docs are disabled.

Never place service-role keys, OAuth client secrets, encryption keys or AI keys
in frontend variables. Rotate a provider credential immediately after suspected
exposure. In **Instellingen > AI-verbindingen**, edit the affected connection,
enter the replacement key and test it before revoking the old key. Existing
keys are never displayed and are only replaced when a new value is submitted.

AI connections belong to an organization. Project model policies and company
prompts belong to one project and cannot reference connections from another
organization. Provider output is schema-validated against the supplied evidence.
Every generated recommendation remains in `proposed` state until an authorized
user approves it; configuring an AI provider never enables automatic publishing.

Dependency and secret checks run in CI. Authorization, OAuth replay, webhook
replay and tenant-isolation tests must remain mandatory.
