# Versioned Template Snapshots Design

## Goal

WP FixPilot must create repeatable WordPress drafts without depending on the
current status or contents of an ordinary WordPress page. Publishing, editing,
or deleting the original source page must not invalidate an approved proposal.

The new flow replaces mutable blueprint pages with versioned, immutable template
snapshots. WordPress retains the complete builder-specific snapshot. WP FixPilot
retains the schema, version identity, allowed replacements, proposal versions,
and workflow state.

Generated pages remain WordPress drafts. WP FixPilot never publishes
automatically.

## Problems This Design Solves

The current implementation ties generation and draft creation to a live
WordPress blueprint page. That causes several recurring failure modes:

- a blueprint stops being eligible after its WordPress status changes;
- a template edit changes the structure hash after generation or approval;
- old and new AI package formats reach the same validation path;
- one malformed field causes the complete proposal to fail;
- HTML appears in fields that only accept plain text;
- retries can require a new proposal even when most generated content is valid;
- errors expose implementation details instead of a recoverable user action.

These failures share one cause: mutable WordPress state, AI output, proposal
state, and draft creation are coupled too tightly.

## Product Decisions

- Templates are hidden, immutable WordPress snapshots rather than ordinary
  draft pages.
- Existing templates are migrated automatically when they can be captured
  safely.
- WordPress stores the full structural snapshot; WP FixPilot stores the
  editable schema and exact snapshot identity.
- AI may return values only for known schema field IDs.
- Invalid optional fields fail independently instead of invalidating the entire
  package.
- All recognized image fields are supported.
- Blogs may also contain controlled inline image slots between content blocks.
- Text, image, validation, approval, and WordPress creation are persisted
  workflow stages that can be resumed independently.
- The current manual handoff remains a temporary recovery path until the
  outbound flow passes live acceptance.

## Architecture

### WordPress Snapshot Store

The bridge plugin owns complete template snapshots because it understands the
site's builders, ACF configuration, media references, page templates, and
WordPress metadata.

Each snapshot contains:

- an immutable snapshot ID and monotonically increasing version;
- original source page ID for lineage only;
- page builder and adapter version;
- PHP page template and allowlisted post metadata;
- complete builder content and ACF rows or repeaters;
- featured image, image fields, background images, and existing media IDs;
- SEO plugin metadata;
- an editable text and image schema;
- a canonical structure hash;
- capture timestamp and capture result.

Snapshots are stored as plugin-managed records that do not appear in the normal
Pages list. They cannot be published or edited through the standard page editor.
The source page is not used during generation or draft creation after capture.

Creating a new snapshot version never mutates an older version. A user replaces
the active template by selecting `Nieuwe versie opnemen`.

### WP FixPilot Snapshot Registry

WP FixPilot stores only the information required to generate, review, validate,
and address a WordPress snapshot:

- project and WordPress connection;
- remote snapshot ID and version;
- builder, template, adapter version, and structure hash;
- typed editable field schema;
- image slot definitions and constraints;
- schema version and prompt contract version;
- active, superseded, incompatible, or unavailable state;
- migration and last verification status.

The complete builder payload is not copied into the SaaS. WordPress-specific
structure remains local to WordPress.

### Version Binding

Every generated proposal is bound to exactly:

- one snapshot ID;
- one snapshot version;
- one structure hash;
- one editable schema version;
- one immutable proposal version.

Draft creation is idempotent for that identity. A retry returns the existing
draft when one was already created. A new template snapshot does not invalidate
historical proposals, but only the active snapshot may be used for a newly
generated proposal.

## Editable Schema

The plugin extracts one typed schema entry per editable field. Every entry has a
stable field ID derived from the structural path rather than its current value.

Supported text types include:

- `plain_text`;
- `heading`;
- `rich_text`;
- `button_text`;
- `url`;
- `seo_title`;
- `meta_description`;
- `focus_keyword`.

Supported image types include:

- featured image;
- ACF image field;
- ACF gallery item where replacement is explicitly supported;
- Gutenberg image block;
- supported builder image widget;
- supported builder background image;
- controlled blog inline image slot.

Each schema entry defines its label, location, required state, constraints,
allowed HTML policy, current fallback value, and adapter ownership.

Unknown builder data is preserved but never exposed to AI or edited.

## Generation Contract

AI no longer generates a complete page package or builder structure. It returns
one map of schema field IDs to candidate values plus optional image briefs.

Conceptually:

```json
{
  "text_replacements": {
    "field-id": {
      "value": "Generated value"
    }
  },
  "image_briefs": {
    "image-slot-id": {
      "prompt": "Image generation brief",
      "alt_text": "Descriptive alternative text",
      "filename": "descriptive-filename"
    }
  }
}
```

Top-level title, slug, SEO fields, internal links, CTA fields, and content blocks
use the same typed field-ID contract. Legacy page-shaped AI payloads are not
accepted by the new path.

### Normalization

The backend normalizes every returned value before proposal validation:

- strip markup from plain text, headings, button text, titles, slugs, keywords,
  anchors, and metadata;
- sanitize allowed markup in rich-text fields;
- canonicalize and validate URLs;
- reject unsupported protocols and unapproved external destinations;
- ignore and record unknown field IDs;
- retain snapshot values for omitted optional fields;
- mark omitted required fields as needing attention;
- enforce the opportunity focus keyword instead of trusting AI to rename it.

A field-level error does not fail unrelated fields. The proposal becomes
reviewable when every required field is valid.

## Image Workflow

### Template Image Slots

Every recognized image location becomes a typed image slot. For each slot the
user can:

- keep the snapshot image;
- select an existing WordPress media item;
- request a generated image;
- remove the image only when the slot is optional.

Generated candidates are stored before WordPress upload and shown in the
proposal preview. The user must approve them explicitly.

Each approved generated image includes:

- provider and model;
- generation prompt and Brand DNA version;
- width, height, aspect ratio, and crop policy;
- alt text, media title, caption when applicable, and descriptive filename;
- content hash and approval metadata.

WordPress downloads an approved image outbound, verifies its type and size,
creates one Media Library attachment idempotently, and writes the resulting
media ID into the cloned draft.

### Blog Inline Images

Blog templates expose controlled insertion anchors between semantic content
blocks. WP FixPilot may propose inline image slots after the introduction or
between major sections. It may not inject arbitrary image HTML into rich text.

Each inline image is represented as a separate block or builder element owned
by the relevant adapter. Its position is bound to a stable neighboring section
ID. Regenerating text preserves approved images. When the meaning of the
neighboring section changes materially, WP FixPilot marks the image for review
instead of silently replacing it.

The project configuration controls maximum images per article, preferred aspect
ratios, visual Brand DNA, and whether stock, media-library, or generated images
are allowed.

## User Workflow

### Template

The template screen shows:

- active snapshot version and capture date;
- source page lineage;
- builder and adapter;
- number of editable text fields and image slots;
- migration, compatibility, and verification status;
- actions `Voorbeeld bekijken` and `Nieuwe versie opnemen`.

### Generate

The generation job persists separate stages:

1. template verified;
2. text generated;
3. image briefs generated;
4. requested images generated;
5. fields validated;
6. proposal ready for review.

Completed stages are never repeated automatically after an unrelated stage
fails.

### Review

The review screen shows the full-width page preview first and editable blocks
below it. Every field has its template label and field type. Image slots show
the current and proposed image with keep, choose, generate, regenerate, and
remove actions as allowed by the schema.

Full-page and block regeneration create comparison candidates. Accepting a
candidate creates a new immutable proposal version and invalidates prior
approval.

### Approve And Create Draft

Approval freezes:

- snapshot identity;
- normalized text replacements;
- approved links and SEO values;
- approved image selections or generated assets;
- proposal version and validation result.

The outbound WordPress job then:

1. claims the approved draft job;
2. verifies the exact local snapshot and structure hash;
3. clones the hidden snapshot into a new `page` with `draft` status;
4. applies only schema-listed text and URL replacements;
5. creates or reuses approved media attachments;
6. applies only schema-listed image replacements;
7. writes SEO metadata;
8. verifies builder structure, metadata, and persisted draft status;
9. reports the WordPress object ID and edit URL.

Any failed write deletes the incomplete page and media attachments created
solely for that failed attempt when they are not referenced elsewhere.

## States And Recovery

The user-visible pipeline is:

`Template gereed` -> `Tekst gereed` -> `Beelden gereed` -> `Gevalideerd` ->
`Goedgekeurd` -> `WordPress-concept`

Every stage stores its own result, error code, retry count, and last transition
time. Refreshing the browser or signing in again does not lose progress.

Errors include one actionable scope:

- template or snapshot;
- text field;
- image slot;
- proposal validation;
- approval;
- WordPress draft job.

Examples:

- `Titel bevat niet-toegestane opmaak` with `Waarde aanpassen`;
- `Hero-afbeelding kon niet worden gegenereerd` with `Opnieuw genereren`;
- `Templateversie ontbreekt in WordPress` with `Template opnieuw opnemen`;
- `WordPress-concept kon niet worden afgerond` with `Opnieuw proberen`.

Raw validation traces, provider payloads, credentials, and internal field values
are not shown to end users. They remain available in bounded diagnostic logs
with secret and content redaction.

Retries resume the failed stage using the same immutable inputs. They do not
regenerate valid content or create duplicate pages.

## Automatic Migration

Migration runs per existing active blueprint:

1. verify the WordPress connection and source page;
2. capture a hidden snapshot without changing the source page;
3. extract and validate the editable schema;
4. register the snapshot version in WP FixPilot;
5. compare the schema with pending proposal versions;
6. revalidate compatible unapproved proposals;
7. mark incompatible proposals with `Nieuw voorstel genereren`;
8. activate the snapshot and detach future generation from the source page.

Approved proposals are not silently rebound to a new identity. They either keep
their exact captured snapshot when it is available or require a new proposal.

Migration failure leaves the existing blueprint registration untouched and
shows the exact recovery action. No source page is unpublished, converted,
deleted, or modified.

## Compatibility And Rollout

Rollout occurs in three implementation releases:

### Release 1: Stable Snapshot Drafts

- hidden WordPress snapshot store;
- automatic migration;
- field-ID text contract;
- resumable text generation and validation;
- idempotent outbound draft creation;
- current manual handoff retained as fallback.

### Release 2: Template Images

- all recognized image slots;
- media-library selection;
- generated image candidates;
- outbound media upload and idempotent attachment reuse;
- preview, approval, and field-level retries.

### Release 3: Blog Inline Images

- controlled inline image anchors;
- Brand DNA image prompts and project constraints;
- semantic image review after text regeneration;
- blog-specific end-to-end acceptance.

The manual handoff may be removed only after the outbound flow passes live
acceptance and a rollback period. Removing it is a separate approved change.

## Security And Safety

- Snapshots and generated pages are never published automatically.
- Source pages and snapshot versions are immutable during generation.
- Only schema-listed fields and approved URLs can change.
- WordPress verifies the snapshot ID, version, structure hash, proposal version,
  and job idempotency identity immediately before writing.
- Plugin-managed snapshots are inaccessible through public front-end routes.
- Snapshot and draft endpoints use the existing authenticated outbound
  connection.
- Image downloads use trusted, expiring URLs and enforce MIME type, size, pixel,
  and timeout limits.
- Generated image provenance and user approval are auditable.
- Failed imports leave no incomplete draft or unreferenced generated media.

## Testing And Acceptance

### Backend

- schema-only generation and field-level normalization;
- unknown, omitted, malformed, and HTML-containing fields;
- stage persistence, restart, and isolated retry;
- immutable proposal and snapshot binding;
- text and image candidate acceptance;
- image asset approval and trusted download metadata;
- draft-job idempotency and stale snapshot refusal;
- migration compatibility classification.

### WordPress Plugin

- snapshot capture for ACF, Gutenberg, Elementor, WPBakery, and Bricks;
- hidden snapshot immutability and public inaccessibility;
- source-page edits or publication not affecting captured snapshots;
- exact clone structure and allowed replacement writes;
- media creation, reuse, cleanup, and image field application;
- controlled blog inline insertion;
- post-write structure and draft-status verification;
- repeat processing returning the same draft.

### Frontend

- persisted pipeline status and recovery after reload;
- full-width preview with text and image controls;
- field-level errors and retry actions;
- comparison and approval invalidation;
- migration status and incompatible proposal recovery;
- WordPress edit link after successful completion.

### Live Acceptance

Before the new flow replaces the current path:

- migrate and verify at least five different ACF page templates;
- create two drafts from each template in separate proposal versions;
- create at least two blog drafts with approved inline images;
- confirm the original source pages can be edited or published without
  invalidating captured snapshots;
- confirm no duplicate pages, incomplete drafts, orphaned generated media,
  structure loss, or manual plugin upload is required;
- run one forced failure and successful resume at every persisted stage;
- verify every created WordPress object remains a draft until a human publishes
  it.

## Out Of Scope

- automatic publication;
- arbitrary AI changes to builder structure;
- free-form image HTML inside generated rich text;
- replacing recognized media without explicit approval;
- deleting the manual handoff before live acceptance;
- roadmap integrations scheduled after the managed publication flow is stable.
