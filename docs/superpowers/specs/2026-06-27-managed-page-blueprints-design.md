# Managed Page Blueprints Design

**Date:** 2026-06-27
**Status:** Approved

## Problem

The current page-package configuration treats a reference page as six independent
text destinations: hero, introduction, main content, FAQ, CTA title, and CTA text.
That loses the actual WordPress page structure. A real SHM page can contain ACF
flexible-content layouts, repeaters, images, buttons, colors, visibility settings,
and theme-template metadata. Elementor, WPBakery, Bricks, and Gutenberg have the
same problem in builder-specific storage.

The WordPress `page_template` value is only the PHP theme shell. It does not contain
the ACF rows or builder tree shown in the editor. A generated page must therefore be
based on a complete builder-native snapshot, not on the PHP template selector or a
small set of text slots.

## Goals

- Create a reusable blueprint from any suitable existing WordPress page.
- Preserve the complete layout, images, styling, repeaters, links, and builder data.
- Let AI replace only approved textual and SEO content inside that structure.
- Support multiple blueprints per project and one default per page type.
- Support ACF, Elementor, WPBakery, Bricks, and Gutenberg through adapters.
- Always create a WordPress draft and never modify the source page or publish it.
- Detect source or blueprint drift before creating a draft.
- Keep every generated proposal tied to an immutable blueprint version.

## Non-Goals

- Generating new visual layouts from scratch.
- Letting AI change images, colors, spacing, widgets, layout order, or PHP templates.
- Automatically publishing generated pages.
- Treating globally active builders as proof that a specific page uses that builder.

## Recommended Architecture

### WordPress-managed blueprint

The bridge plugin creates each managed blueprint as a normal WordPress `page` with
draft status and an internal `_wp_fixpilot_blueprint` marker. Keeping the `page` post
type is required because ACF location rules and builder support can depend on it.
Blueprint pages are excluded from the normal WP FixPilot inventory and new-page
opportunities, clearly prefixed in WordPress admin, and managed from project settings.
Creating a blueprint clones the chosen reference page, including:

- `post_content`, excerpt, parent, menu order, and `page_template`;
- ACF field values and flexible-content/repeater structure;
- Elementor, Bricks, and other builder-specific postmeta;
- featured image, PHP page template, and adapter-allowlisted builder/theme metadata;
- a source page ID, builder type, version, and structure hash.

The source page remains untouched. Updating a blueprint creates a new version rather
than changing proposals that already refer to an older version.

The backend stores the blueprint registry and mapping manifest, but WordPress remains
the source of truth for the full builder-native structure. This avoids moving large,
site-specific postmeta snapshots through the SaaS database.

### Blueprint registry

Replace the single `ProjectPagePackageSettings` concept with project blueprints:

- `id`
- `project_id`
- `name`
- `page_type` (`service`, `brand`, `location`, `blog`, or `generic`)
- `source_wordpress_page_id`
- `wordpress_blueprint_id`
- `builder`
- `seo_plugin`
- `version`
- `structure_hash`
- `content_schema`
- `state` (`capture_required`, `capturing`, `ready`, `stale`, or `invalid`)
- `is_default_for_page_type`
- timestamps

Only one ready blueprint can be the default for a given project and page type.
Existing single-template settings are retained for migration but are no longer used
for new proposals after a managed blueprint has been configured.

## Builder Adapters

Every adapter implements the same operations:

1. Detect whether the selected page actually uses the builder.
2. Clone complete builder-native data into the managed blueprint.
3. Produce a neutral content schema containing stable text-field paths.
4. Apply replacements to a cloned draft without changing structure.
5. Recalculate and verify a structure hash.

### ACF

Clone all ACF postmeta and preserve flexible-content layouts, repeater rows, groups,
images, links, booleans, and choices. The schema exposes editable textual leaves with
their parent layout, row, field label, field key, current value, and value type.
Non-text values remain locked. Updating text is performed on a complete copied field
value, so nested rows and sibling settings cannot disappear.

### Elementor

Clone `_elementor_data` and related page settings. Expose text-bearing widget settings
using stable element IDs and setting paths. Preserve widget types, sections, images,
responsive settings, and global styles.

### WPBakery

Clone `post_content` and parse the complete shortcode tree. Expose text attributes and
enclosed content while preserving rows, columns, shortcode attributes, and ordering.

### Bricks

Clone Bricks content and settings metadata. Expose text properties through stable
element IDs while preserving the element tree and styling.

### Gutenberg

Clone parsed blocks and expose text or HTML attributes by stable block path. Preserve
block names, attributes, media IDs, reusable-block references, and nesting.

## Content Schema And AI Contract

The six fixed semantic slots are replaced by a blueprint-derived content schema. Each
editable field contains:

- a stable field ID and builder-native path;
- block/layout name and human-readable label;
- text type (`plain_text`, `rich_text`, `heading`, `button_text`, or `url`);
- current value as an example;
- optional semantic role (`hero`, `introduction`, `benefits`, `process`, `faq`, `cta`);
- length guidance derived from the source value.

The user reviews an outline of complete blocks rather than a flat list of 70 values.
WP FixPilot proposes semantic roles automatically from layout names and labels, but
the user can adjust them once while creating the blueprint.

AI receives the company profile, project prompt, keyword opportunity, internal-link
candidates, and the blueprint schema. It returns only a map of field IDs to replacement
values plus SEO fields. Unknown IDs, missing required fields, structural data, media
changes, and changed repeater counts are rejected.

This contract lets the amount and shape of generated content follow the selected
page. A five-section reference page produces five populated sections; WP FixPilot no
longer squeezes every template into six generic fields.

## User Flow

### Create a blueprint

1. Open project settings and choose **New blueprint**.
2. Enter a name and page type.
3. Select any existing WordPress reference page.
4. WP FixPilot detects the builder used by that page.
5. WordPress creates a managed blueprint clone.
6. WP FixPilot shows the block outline and proposed semantic roles.
7. The user confirms the outline and sets it as the default for that page type.
8. Validation confirms the clone, schema, SEO plugin, and structure hash.

Multiple blueprints can coexist, for example **Merkpagina**, **Dienstpagina**, and
**Blogartikel**.

### Generate a page

1. A DataForSEO opportunity is classified as a new-page opportunity and page type.
2. WP FixPilot selects the ready default blueprint for that page type.
3. AI generates field replacements that match the blueprint schema.
4. The review screen shows the blueprint name/version, SEO fields, and complete content
   grouped by the original page blocks.
5. The user can edit replacements and approve the proposal.
6. WordPress clones the managed blueprint to a normal page draft and applies only the
   approved text and SEO replacements.
7. WP FixPilot returns the WordPress edit link. Publishing remains manual.

## Validation And Safety

- Every write requires the expected blueprint version and structure hash.
- A changed blueprint becomes `stale`; generation and draft creation stop until it is
  revalidated or versioned.
- Source pages and managed blueprints are never modified during generation.
- Draft creation is idempotent per approved proposal.
- The plugin allowlists builder metadata that can be cloned and excludes edit locks,
  revisions, analytics state, and WP FixPilot proposal metadata.
- AI output is validated against known field IDs and text-compatible field types.
- Images, layout rows, widget types, styles, and hidden settings cannot be supplied by AI.
- URL replacements are accepted only when they match an approved internal-link or CTA
  destination from the proposal context.
- Failed writes delete the incomplete draft.
- Existing manual publication and approval controls remain mandatory.

## API Changes

Backend routes:

- `GET /projects/{id}/page-blueprints`
- `POST /projects/{id}/page-blueprints`
- `GET /projects/{id}/page-blueprints/{blueprint_id}`
- `PUT /projects/{id}/page-blueprints/{blueprint_id}`
- `POST /projects/{id}/page-blueprints/{blueprint_id}/validate`
- `POST /projects/{id}/page-blueprints/{blueprint_id}/set-default`
- `POST /projects/{id}/page-blueprints/{blueprint_id}/new-version`
- `DELETE /projects/{id}/page-blueprints/{blueprint_id}`

WordPress bridge routes:

- `POST /blueprints` to capture a reference page
- `GET /blueprints/{id}` to read its schema and hash
- `POST /blueprints/{id}/drafts` to create an idempotent draft
- `DELETE /blueprints/{id}` to remove a managed blueprint only when no active proposal
  depends on it

The existing page-package routes remain temporarily available for migration and are
removed after all projects use managed blueprints.

## Error Handling

- Unsupported or ambiguous builders return a clear selection error before capture.
- Missing ACF definitions or corrupt builder data mark the blueprint invalid without
  changing the source page.
- Builder/plugin version changes that alter the structure hash mark blueprints stale.
- AI responses with unknown fields or structural changes fail before WordPress is called.
- WordPress cloning or field-write errors remove the partial draft and retain the
  proposal for retry.

## Testing

- Contract tests for all five adapter operations.
- Nested ACF flexible-content, repeater, group, image, link, and empty-field fixtures.
- Elementor, Bricks, WPBakery, and Gutenberg structure-preservation fixtures.
- Assertions that source pages and blueprint versions remain unchanged.
- Backend tests for multiple blueprints, one default per page type, migration, stale
  hashes, authorization, and idempotency.
- AI contract tests for valid replacements, unknown field IDs, missing required fields,
  and attempted media/layout changes.
- Frontend tests for blueprint creation, outline review, defaults, validation, and
  proposal review grouped by original blocks.
- End-to-end staging test that creates a draft from the SHM **Transmissie onderhoud**
  reference and confirms the ACF structure, PHP page template, images, and SEO fields
  are preserved while the approved text changes.

## Success Criteria

- A draft based on an ACF reference page contains the same layouts, row counts, images,
  styling settings, PHP page template, and non-text metadata as its blueprint.
- Generated text fills all approved textual fields from the selected reference page.
- The source page and managed blueprint remain unchanged.
- The WordPress result is a draft with a working edit URL and populated SEO metadata.
- The same workflow succeeds through the shared adapter contract for Elementor,
  WPBakery, Bricks, and Gutenberg.
