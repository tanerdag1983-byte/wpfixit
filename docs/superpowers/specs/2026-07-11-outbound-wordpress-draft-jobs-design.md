# Outbound WordPress Draft Jobs Design

## Goal

Replace the fragile browser handoff as the primary WordPress delivery path with
a persistent project connection initiated by the WP FixPilot Bridge plugin.
WordPress fetches approved draft jobs outbound over HTTPS, applies them through
the existing managed-blueprint pipeline, and reports the result to WP FixPilot.

Existing managed blueprints already present in WordPress remain unchanged. The
new flow reuses their WordPress IDs, versions, structure hashes, builder
adapters, SEO adapters, idempotency rules, cleanup, and persisted draft-status
verification. It never publishes automatically.

## Product Workflow

### Connect Once

1. An organization owner or admin creates or rotates a project WordPress key in
   WP FixPilot.
2. The key is displayed once and pasted into the WP FixPilot Bridge settings.
3. The plugin stores it in WordPress and verifies the connection with an
   outbound request to WP FixPilot.
4. WordPress shows the connection state, project identity, last successful
   contact, and last error.

### Create A Draft

1. A user generates, reviews, and approves the current proposal version.
2. The user selects `WordPress-concept aanmaken` in WP FixPilot.
3. The backend creates one immutable draft job for that approved proposal
   version and shows `Wachten op WordPress`.
4. The plugin immediately checks for pending work when an authorized WordPress
   user selects `Concepttaken ophalen`. A short recurring WordPress cron check
   may also retrieve jobs, but draft creation remains tied to an approved job
   and never publishes it.
5. The plugin claims one job, validates its blueprint identity and package, and
   creates the draft using the existing blueprint controller.
6. The plugin reports the WordPress object ID, edit URL, and bounded result
   metadata outbound to WP FixPilot.
7. WP FixPilot shows `Concept aangemaakt` with the edit link.

Repeated clicks, polling, retries, or multiple WordPress requests return the
same job and the same draft. They never create duplicate pages.

## Architecture

### Backend

The backend stores a hashed project WordPress key and immutable draft jobs. The
plaintext key is shown only at creation or rotation. A request authenticated by
the key may only access pending jobs for its own project and connected site.

Draft job states are:

- `queued`;
- `claimed`;
- `completed`;
- `failed`;
- `cancelled`.

Only an approved current proposal can create a job. A unique constraint binds
one job to one immutable proposal version and snapshot. Accepting a new proposal
version, withdrawing approval, deleting the blueprint, or detecting structure
drift cancels any unfinished incompatible job.

The backend endpoints support:

- connection verification;
- atomic claim of the next eligible job;
- completion with WordPress object ID and edit URL;
- bounded failure reporting;
- job status for the dashboard.

### Frontend

Project settings allow an owner or admin to create, rotate, or revoke the
WordPress key. The key is never returned again after its one-time display.

The proposal review page replaces the primary handoff action with
`WordPress-concept aanmaken`. It shows queued, claimed, completed, failed, and
cancelled states with a retry action where safe. The existing manual handoff
remains temporarily available as a secondary fallback during rollout.

### WordPress Bridge

The plugin adds:

- a project API-key field;
- `Verbinding testen`;
- `Concepttaken ophalen`;
- last-contact and last-job status;
- a short WordPress cron schedule for pending-job checks.

All SaaS communication is outbound from WordPress. The plugin never exposes the
project key in URLs or logs. Draft execution continues through the existing
blueprint controller; no parallel ACF cloning implementation is introduced.

## Job Contract

Each claimed job contains:

- job and project identity;
- immutable proposal-version and snapshot identity;
- WordPress blueprint ID;
- expected blueprint version and structure hash;
- schema-listed text and approved URL replacements;
- SEO title, description, and focus keyword;
- expiry and contract version.

The contract has an explicit version. The plugin rejects unknown versions and
reports `unsupported_contract` instead of falling back to a legacy page-package
shape. This removes the ambiguity that caused the current handoff failures.

## Security And Safety

- Keys contain at least 256 bits of randomness and are stored hashed in the
  backend.
- Key rotation immediately invalidates the previous key.
- Every request is restricted to its project and registered site URL.
- Claim and completion are atomic and idempotent.
- Only schema-listed fields and approved URLs may change.
- Existing blueprint pages and source pages remain immutable.
- Every generated WordPress page is a normal `page` with `draft` status.
- The plugin verifies persisted draft status after WordPress hooks run.
- Any failed ACF, builder, SEO, metadata, media, or status write deletes the
  incomplete clone.
- Errors and logs never include keys or complete content packages.

## Error Handling

Connection failures retain the queued job and show a retryable status. A claim
expires if WordPress stops before completion, after which the same plugin can
reclaim it. Completed jobs are immutable. Non-retryable validation failures use
bounded codes such as `blueprint_drift`, `unknown_field`, `url_not_approved`,
or `unsupported_contract`.

The dashboard distinguishes `WordPress niet bereikbaar` from a package or
blueprint validation error. No failure automatically switches to publication or
creates a simplified page.

## Testing

### Backend

- key creation, one-time return, hashing, rotation, and revocation;
- project and site isolation;
- approved-current-version requirement;
- unique job creation and concurrent atomic claiming;
- claim expiry and reclaim;
- completion and failure idempotency;
- cancellation after proposal or blueprint invalidation;
- refusal to expose jobs through an invalid or revoked key.

### WordPress Plugin

- connection verification and secret-safe storage;
- outbound retrieval with no inbound SaaS-to-WordPress request;
- strict contract-version rejection;
- existing blueprint version and structure-hash checks;
- ACF, SEO, media, template, and style preservation;
- persisted draft-only verification and incomplete-clone cleanup;
- retry returns the same draft and never creates a duplicate;
- cron and manual retrieval cannot process the same job twice.

### Frontend

- one-time key display and rotation warning;
- queued, waiting, completed, failed, and cancelled states;
- edit link after completion;
- retry only for eligible jobs;
- no publish action in this workflow.

### Staging Acceptance

1. keep the existing ACF blueprint unchanged;
2. connect the plugin with a newly generated project key;
3. approve the current generated proposal;
4. create one draft job in WP FixPilot;
5. retrieve it from WordPress;
6. verify ACF content, Yoast metadata, template, media, and draft status;
7. retry both sides and confirm the same WordPress page is returned;
8. rotate the key and confirm the old key is rejected;
9. confirm no page is published automatically.

## Rollout And Later Work

The outbound draft-job flow becomes the primary release path. The current
single-use handoff remains available during the first rollout and can be removed
after successful staging and production acceptance.

After live launch, WordPress application-password authentication may be added as
an optional second connection method. It must not replace the outbound default
or weaken draft-only and manual-approval requirements.

## Out Of Scope

- WordPress application passwords in the initial live release;
- automatic publication;
- customer IP allowlists;
- replacing or recreating existing blueprints;
- arbitrary WordPress commands unrelated to approved draft jobs;
- WebSockets or a continuously open plugin connection.
