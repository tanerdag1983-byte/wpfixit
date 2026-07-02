# Manual WordPress Handoff And Proposal Versions Design

## Goal

WP FixPilot must remain usable on WordPress hosting protected by Imunify360 or
similar bot protection without requiring customer IP allowlists. For the first
live release, an authorized user manually starts a browser handoff after
reviewing and approving a generated page proposal. The WordPress bridge then
retrieves the approved package outbound and creates exactly one WordPress
draft. It never publishes automatically.

The same release improves proposal review by persisting generated proposals,
showing a full-width preview, and supporting versioned full-page or single-block
regeneration with explicit comparison and acceptance.

The later fully automatic outbound polling connection is outside this design.
The manual handoff should provide reusable primitives for that future work.

## Product Workflow

### Generate And Review

1. A user selects `Pagina laten maken` for a new-page opportunity.
2. WP FixPilot generates and persists a proposal version.
3. The opportunity changes to `Gegenereerd` and exposes:
   - `Voorstel bekijken`;
   - `Opnieuw genereren`.
4. The review page shows the complete rendered preview at full desktop width.
5. Editable SEO and content fields appear below the preview in a single-column
   layout. Mobile uses the same vertical order.
6. The user may save edits and then approve the current proposal version.

### Regenerate

The review page contains one regeneration panel with:

- a mode selector: `Volledige pagina` or `Gekozen blok`;
- a block selector shown only for `Gekozen blok`;
- one shared `Extra instructies` textarea;
- a mode-specific generation action.

Full regeneration produces a complete candidate proposal. Partial regeneration
produces a candidate replacement for exactly one schema-listed block. Neither
operation mutates the accepted current version immediately.

After generation, WP FixPilot shows a comparison:

- desktop: current and candidate content side by side;
- mobile: current content above candidate content;
- actions: `Nieuwe versie accepteren` and `Annuleren`.

Accepting creates a new proposal version and makes it current. Cancelling
discards the candidate. The previous version remains immutable and available
for audit history. A new current version invalidates prior approval and every
unused handoff code for an earlier version.

### Manual WordPress Handoff

1. An organization owner or admin approves the current proposal version.
2. The owner or admin selects `Handmatig naar WordPress`.
3. The backend creates a short-lived, single-use handoff code and returns the
   known WordPress admin import URL with the opaque code in the URL fragment,
   never in the path or query string.
4. The browser navigates to the WP FixPilot Bridge import page on the connected
   WordPress site with `Referrer-Policy: no-referrer`.
5. Plugin JavaScript immediately removes the fragment from browser history and
   sends the code to a same-origin WordPress endpoint with a WordPress nonce.
   WordPress then redeems it outbound from WP FixPilot over HTTPS. The raw code
   must not be written to WordPress, proxy, analytics, or application logs.
6. The backend validates the code and returns the approved immutable package.
7. The plugin stores the package in a short-lived server-side import session
   bound to the WordPress user, site, and handoff identity.
8. WordPress displays a summary containing the page title, target template,
   builder, SEO plugin, proposal version, and draft-only outcome.
9. An authorized WordPress user selects `Concept importeren`.
10. The bridge revalidates the import session, template, and package and performs
   an outbound live check that the exact proposal version is still current and
   approved and that the handoff remains eligible. It then creates exactly one
   draft and reports the WordPress object ID and edit URL outbound to WP FixPilot.
11. WP FixPilot records `draft_created` and shows the WordPress edit link.

Cross-origin browser uploads, payloads in URLs, direct Render-to-WordPress
writes, and automatic publication are explicitly excluded.

## Architecture

### Backend

The backend owns proposal versions, regeneration candidates, approvals, and
handoff redemption.

New backend responsibilities:

- persist immutable proposal versions and point each opportunity to its current
  version;
- generate full-page and schema-bound single-block candidates;
- store the shared user instruction with generation metadata;
- atomically accept or discard a candidate;
- issue and redeem opaque handoff codes;
- return packages only to the connected WordPress site;
- accept idempotent completion callbacks from the plugin.

The backend never sends the package directly to WordPress for this workflow.

### Frontend

The frontend owns review and explicit user actions:

- show persistent generated state on opportunity cards;
- open the current or historical proposal version;
- render a full-width preview above editable fields;
- collect regeneration mode, target block, and one shared instruction;
- compare current and candidate versions before acceptance;
- require approval after every accepted content change;
- start browser navigation to the WordPress import page.

### WordPress Bridge

The plugin adds an authenticated admin import screen. It receives only an
opaque handoff code from the browser, then retrieves the package outbound from
WP FixPilot. Existing builder adapters, SEO adapters, template hashing,
idempotency behavior, draft-status checks, and cleanup rules remain the source
of truth for applying the package.

The import screen and its same-origin redemption endpoint require `edit_pages`.
Opening the URL alone must not redeem or execute the package. Redemption begins
only inside the authenticated admin screen, and draft creation requires a second
explicit WordPress confirmation.

## Data Model

### Proposal Versions

Each proposal version records:

- project and keyword opportunity;
- monotonically increasing version number;
- immutable generated package and rendered preview;
- generation mode: `full` or `block`;
- optional target block identifier;
- optional user instruction;
- parent version;
- provider, model, prompt version, and token usage;
- state and timestamps;
- approval actor and timestamp when applicable.

An opportunity points to one current proposal version. Historical versions are
retained and never overwritten.

### Regeneration Candidates

A candidate is temporary and belongs to one base version. It contains either a
complete package or one typed block replacement. Accepting it atomically creates
the next immutable proposal version. A candidate cannot be accepted when its
base version is no longer current.

### Handoff Codes

A handoff record contains:

- a server-side hash of a cryptographically random opaque code;
- project, WordPress connection, proposal version, and issuing user;
- ten-minute expiry;
- state: `issued`, `redeemed`, `completed`, `expired`, or `revoked`;
- redemption and completion timestamps;
- resulting WordPress object ID and edit URL.

Plain handoff codes are never stored. Codes are single-use for package
redemption. Draft creation is uniquely idempotent per immutable proposal version
and snapshot, regardless of how many handoff codes were issued. Completion
retries return the same existing draft and cannot create another page. The
plugin import session expires after ten minutes, is protected by a WordPress
nonce, and is deleted after successful import or cancellation.

## Security And Validation

The backend returns a package only when all of the following hold:

- the handoff code exists, is unexpired, unused, and not revoked;
- project and registered WordPress connection match;
- the referenced proposal version remains approved;
- the package belongs to that exact immutable version;
- the requesting plugin proves possession of its project credential;
- the reported WordPress site identity matches the connection.

Only an organization `owner` or `admin` may approve proposal versions or issue,
revoke, inspect, or retry handoffs. Ordinary members and users from another
organization receive no handoff metadata and no indication whether a record
exists.

Before writing, the plugin verifies:

- template WordPress ID, builder, SEO plugin, and structure hash;
- schema-listed writable fields and approved URLs only;
- the immutable proposal-version and snapshot idempotency identity;
- the authenticated WordPress user's capability.

The plugin always writes `post_type=page` and `post_status=draft`. It verifies
the persisted draft state after hooks run. Any failed metadata, builder, ACF,
SEO, featured-image, or status write deletes the incomplete clone and reports a
bounded error without secrets or package contents.

## States And Invalidation

Proposal versions use these user-visible lifecycle states:

- `generating`;
- `proposed`;
- `approved`;
- `draft_created`;
- `failed`.

Approval belongs to one immutable proposal version. Handoffs have their own
separate `issued`, `redeemed`, `completed`, `expired`, or `revoked` lifecycle;
redeeming a code does not change proposal state.

Saving an edit or accepting a regeneration candidate transactionally creates a
new current version in `proposed`, invalidates approval of the previous version,
and revokes its issued or redeemed-but-incomplete handoffs. Approving the new
version permits new handoff issuance. Immediately before draft creation, the
plugin live-revalidates that the version is still current and approved and that
the redeemed handoff is still eligible. Completing the handoff moves the proposal
version to `draft_created` but does not publish it.

If a draft already exists for the same proposal version, every retry returns
the same WordPress object ID and edit URL.

## Errors And Recovery

The UI must expose actionable errors for:

- expired, used, revoked, or unknown handoff codes;
- WordPress site or project mismatch;
- changed template structure, builder, or SEO plugin;
- offline WP FixPilot API during plugin retrieval;
- invalid or stale regeneration candidates;
- failed builder, ACF, SEO, media, or draft-status writes.

An expired handoff can be replaced from the still-approved proposal. Template
drift requires package revalidation and a new proposal or approval as required.
Failed WordPress writes remain retryable because no incomplete clone survives
and idempotency prevents duplicate completed drafts.

## Testing

### Backend

- proposal persistence and current-version selection;
- full and single-block candidate generation;
- stale candidate rejection and atomic candidate acceptance;
- approval invalidation after edits or accepted regeneration;
- handoff issue, expiry, revocation, redemption, site binding, and completion;
- concurrent redemption and completion idempotency;
- multiple handoffs for one immutable proposal version producing one draft;
- refusal after approval withdrawal or current-version invalidation;
- owner/admin authorization and member or cross-project refusal without metadata
  leakage;
- refusal to return unapproved or mismatched packages.

### Frontend

- full-width desktop preview above editable fields;
- stacked mobile layout without overlap;
- `Gegenereerd`, `Voorstel bekijken`, and `Opnieuw genereren` opportunity states;
- shared regeneration textarea and conditional block selector;
- full and partial comparison acceptance and cancellation;
- approval reset after accepted changes;
- handoff navigation, fragment removal, no-referrer behavior, and actionable
  error states.

### WordPress Plugin

- capability-protected import screen;
- fragment-to-same-origin POST and outbound code redemption with authenticated
  site identity;
- no raw handoff code in URLs after initialization or in application logs;
- no package execution from URL navigation alone;
- summary before confirmation;
- live approval, current-version, and handoff revalidation immediately before
  draft creation;
- builder and SEO drift detection;
- ACF rows and repeaters, media IDs, styles, widgets, templates, and allowlisted
  metadata preservation;
- exact draft-only creation, persisted draft verification, and cleanup;
- idempotent retry returning the same draft.

### End To End

On staging:

1. generate and persist a proposal;
2. regenerate one selected block with an instruction;
3. compare and accept the candidate;
4. approve the new proposal version;
5. open the WordPress import screen through a handoff code;
6. retrieve the package outbound;
7. confirm and create exactly one WordPress draft;
8. verify the edit link, ACF content, Yoast metadata, and draft status;
9. repeat the handoff and confirm no duplicate is created;
10. verify that no workflow publishes automatically.

## Out Of Scope

- recurring outbound polling and automatic command pickup;
- WebSockets or persistent plugin connections;
- per-customer IP allowlists;
- automatic or scheduled publication;
- WXR/XML export or field-by-field copy workflows;
- changes to unrelated roadmap integrations.
