# Keyword Opportunity Page Creation Design

## Goal

WP FixPilot must distinguish between a keyword that belongs on an existing page
and a keyword that deserves a new page. For new-page opportunities, it must
generate a complete, editable page package, require manual approval, and create
only a WordPress draft using the builder, template, block mapping, and SEO plugin
configured separately for each project.

## Opportunity Classification

Business relevance and page fit are separate decisions. A keyword can be valid
for the company without fitting any existing page.

Existing-page matching will use weighted project-local distinctiveness:

- exact or near-exact page phrases receive the highest weight;
- tokens that occur on only one or a few project pages receive more weight;
- common service words such as `versnellingsbak`, `revisie`, `problemen`, and
  `kosten` cannot establish a page match by themselves;
- a match must contain a sufficiently distinctive page entity or multiple
  supporting page-specific tokens;
- a weak match produces a new-page opportunity rather than guessing a page.

This prevents `vw dsg versnellingsbak reviseren` from targeting an Alfa Romeo
page and prevents a general automatic-transmission query from targeting a Cupra
page. A query containing the relevant rare entity, such as `cupra`, can still
target the Cupra page. The algorithm is project-derived and does not depend on a
hard-coded list of car brands.

Each opportunity exposes a target classification:

- `existing_page`: a strong page match with evidence and target URL;
- `new_page`: no sufficiently strong existing-page match;
- `review`: ambiguous evidence near the threshold, shown without an automatic
  target until the user chooses an existing page or a new page.

## Project Page-Package Settings

Every project has its own required page-package configuration:

- builder: Gutenberg, Elementor, Bricks, WPBakery, or ACF;
- WordPress template page;
- SEO plugin: detected from Yoast, Rank Math, or AIOSEO and user-confirmable;
- mapping from template fields or blocks to semantic slots;
- template content hash and validation timestamp.

The semantic slots are:

- page title;
- hero title;
- introduction;
- main content sections;
- FAQ;
- CTA title, text, and link;
- optional internal-link section.

Settings show the blocks discovered by the selected builder adapter. The user
maps them once for that project. A validation action confirms that required
slots exist and stores the template hash. New-page generation remains disabled
until the project configuration is valid.

## Builder Adapter Contract

The WordPress bridge owns builder-specific data handling. Every adapter exposes
the same operations:

1. detect whether the builder is active;
2. inspect a template and return editable slots with stable paths and labels;
3. validate a saved slot mapping against the current template;
4. clone the template into a new draft;
5. write approved package values only to mapped slots.

Adapter implementations:

- Gutenberg: block path and supported block attributes/content;
- Elementor: recursive element ID and supported settings key;
- Bricks: element ID and supported settings key;
- WPBakery: shortcode path and supported attribute/body;
- ACF: field key and supported scalar or WYSIWYG value.

The bridge never performs broad search-and-replace across builder payloads. If a
mapped path is missing or the template hash has changed, draft creation fails
with a conflict and creates no partial page.

## SEO Metadata

The existing SEO adapters are extended with draft metadata support:

- SEO title;
- meta description;
- focus keyword;
- canonical URL left empty for a new draft;
- indexability remains WordPress draft behavior until publication.

Yoast, Rank Math, and AIOSEO each write only their documented project-local
metadata. The active plugin detected by the bridge is compared with the project
configuration before a draft can be created.

## Page Package Proposal

New page proposals use their own database model rather than
`WordPressChangeProposal`, because no target WordPress page exists yet. A
proposal stores:

- project and keyword-opportunity identifiers;
- selected project page-package configuration snapshot;
- title and slug;
- SEO title, meta description, and focus keyword;
- structured hero, introduction, sections, FAQ, CTA, and internal links;
- rendered preview HTML;
- generation source, model, and prompt version;
- state: `generating`, `proposed`, `approved`, `creating_draft`,
  `draft_created`, `conflict`, or `failed`;
- actor and timestamps;
- created WordPress object ID and edit URL after success.

Generation uses the project's company profile, custom prompt, AI model policy,
WordPress page inventory, internal-link candidates, keyword metrics, and search
intent. The AI returns a strict structured package. Server-side validation
enforces required fields, safe HTML, unique internal links, slug format, and
reasonable SEO lengths before the proposal becomes reviewable.

## Review And Draft Flow

1. The Kansen page labels weak matches as `Nieuwe pagina aanbevolen` and shows
   `Pagina laten maken`.
2. The user starts generation. The operation runs as a persisted background job
   so refresh does not lose progress.
3. The review page shows an editable preview plus separate title, slug, SEO,
   content, FAQ, CTA, and internal-link fields.
4. The user saves edits and explicitly approves the proposal.
5. `Concept aanmaken` sends the approved package, saved mapping, and expected
   template hash to the WordPress bridge.
6. The bridge validates everything, clones the template, writes mapped content
   and SEO metadata, and forces `post_status=draft`.
7. WP FixPilot stores the returned WordPress ID and edit URL. Publication itself
   remains a later manual WordPress action and is not part of this flow.

Repeated clicks are idempotent. A proposal with a stored WordPress object ID
returns the existing draft instead of creating a duplicate.

## API Surface

Backend endpoints:

- `GET /projects/{id}/page-package-settings`
- `PUT /projects/{id}/page-package-settings`
- `POST /projects/{id}/page-package-settings/inspect-template`
- `POST /projects/{id}/page-package-settings/validate`
- `POST /projects/{id}/keyword-opportunities/{opportunity_id}/page-proposal`
- `GET /projects/{id}/page-proposals/{proposal_id}`
- `PUT /projects/{id}/page-proposals/{proposal_id}`
- `POST /projects/{id}/page-proposals/{proposal_id}/approve`
- `POST /projects/{id}/page-proposals/{proposal_id}/create-draft`

WordPress bridge endpoints:

- `GET /wpfixpilot/v1/builders`
- `GET /wpfixpilot/v1/templates/{id}/slots?builder=...`
- `POST /wpfixpilot/v1/draft-pages`

All bridge calls use the existing signed-request protocol. Settings and draft
creation require project owner or admin permissions.

## UI Changes

Project settings gain a `Standaard paginapakket` section containing builder,
template page, SEO plugin, discovered-slot mapping, validation state, and a
template revalidation warning.

The Kansen page displays one of:

- `Bestaande pagina verbeteren` with the matched URL;
- `Nieuwe pagina aanbevolen` with the generation button;
- `Keuze controleren` with actions to select a page or choose a new page.

The proposal review is a dedicated route and does not reuse the existing-page
before/after screen. It always has a back link to Kansen and clearly states that
the final action creates a draft, not a published page.

## Failure Handling

- Missing or invalid project template settings block generation and explain the
  exact setting to complete.
- AI or network failure keeps the opportunity intact and records a retryable
  failed job.
- A changed template produces a conflict and requires revalidation.
- Builder or SEO-plugin mismatch creates no page.
- WordPress errors leave the approved proposal available for retry.
- Duplicate draft requests return the previously created draft.
- Logs and API responses never contain WordPress secrets or AI credentials.

## Testing

Tests cover:

- VW-to-Alfa and generic-query-to-Cupra mismatches becoming new-page
  opportunities;
- strong entity and exact phrase matches retaining existing target pages;
- project isolation for builder, template, mapping, and SEO settings;
- slot inspection and stale-template conflicts for every builder adapter;
- strict AI package validation and persisted generation jobs;
- manual approval being required before draft creation;
- idempotent draft creation and forced WordPress draft status;
- Yoast, Rank Math, and AIOSEO metadata;
- UI states for existing, new, ambiguous, generating, approved, conflict, and
  draft-created proposals.

## Delivery Order

The feature is delivered vertically:

1. stricter opportunity classification and visible new-page choice;
2. project page-package settings and template inspection;
3. structured AI proposal generation and review;
4. Gutenberg draft creation end to end;
5. Elementor, Bricks, WPBakery, and ACF adapters;
6. SEO metadata adapters, production verification, and plugin rollout.

Every stage remains testable. Draft creation is not enabled for a builder until
its adapter and conflict tests pass.
