# Content Operations And Intelligence Design

Date: 2026-06-30
Status: Approved design

## Purpose

Extend WP FixPilot from a safe WordPress blueprint and draft workflow into a project-
specific content operations platform. The platform plans approved content, applies each
project's Brand DNA, measures search and analytics results, and keeps a one-year page
history without confusing optimization scores with Google rankings.

The managed-blueprint workflow is completed and deployed first. The features in this
design are then delivered as independently testable modules.

## Product Principles

- Every project has its own Brand DNA.
- AI and images produce proposals, never silent content replacements.
- Rewriting one block or a whole page creates a new reviewable version.
- Automatic publication is available only for a version that was manually approved.
- A post-approval content change invalidates approval and blocks scheduled publication.
- Real Google outcomes come from Search Console and GA4.
- The SEO score is an explainable optimization score, not a Google PageRank claim.
- Existing and newly generated WordPress pages use the same scoring and history model.
- External API credentials and usage limits remain isolated per account or project.

## Delivery Sequence

1. Deploy and verify the managed-blueprint publication workflow.
2. Project Brand DNA.
3. Internal and external Link Intelligence.
4. Content Studio and page SEO scoring.
5. Image Studio.
6. Content Calendar and approved scheduling.
7. GSC, GA4, PageSpeed, and one-year Impact Timeline.

Each module can ship independently, but all modules write to one page history.

## Project Brand DNA

Replace the existing company and website profile concept with a Brand DNA owned by one
project. Projects do not inherit an account-wide Brand DNA.

Brand DNA contains:

- brand and company name;
- mission, positioning, and differentiators;
- target audiences and locations;
- products and services;
- tone of voice and vocabulary;
- preferred claims, evidence, and calls to action;
- forbidden claims, phrases, topics, and compliance rules;
- formatting and writing preferences;
- image style default;
- optional project instructions for AI.

Every generated proposal stores the Brand DNA version used. Updating Brand DNA does not
silently rewrite old content. It creates an option to generate a new proposal.

## Link Intelligence

### Source priority

Internal-link candidates are resolved in this order:

1. page-specific preferred links supplied by the user;
2. general project preferred links supplied by the user;
3. relevant URLs from the project's sitemap and crawl inventory;
4. a recommendation for a new destination page when no good match exists.

Preferred links are not forced when they conflict with page intent. The review explains
why a candidate was accepted or rejected and shows the fallback source.

### Internal links

The module detects orphan pages, weakly linked pages, repeated anchors, broken links,
redirect chains, topical mismatches, and opportunities to add or update links. Changes
remain proposals until approved.

### External links

External links are checked for availability, redirects, topic relevance, source quality,
and appropriate `nofollow`, `sponsored`, or `ugc` treatment. WP FixPilot recommends
changes and records the evidence used.

## Content Studio

All existing and newly created WordPress pages are available in the Content Studio.

Users can:

- rewrite one schema-listed block;
- rewrite the complete page;
- add an instruction such as shorter, more technical, or more conversion-focused;
- compare current and proposed versions;
- edit a proposal before approval;
- reject, approve, or return to an earlier version.

Every rewrite creates a new immutable proposal. Current WordPress content is never
overwritten during generation. The proposal records its blueprint, Brand DNA, prompt,
AI provider/model, source data, and link context.

## Explainable SEO Score

Every existing and new page receives an explainable score from 0 to 100. The score card
shows at least:

- primary keyword assessment;
- word count;
- readability;
- number and structure of headings;
- SEO title text and character count;
- meta description text and character count;
- featured image and alt-text presence;
- internal and external link count and quality;
- indexability and canonical status;
- Brand DNA consistency;
- mobile and desktop PageSpeed signals.

Each factor shows its status, contribution, explanation, and concrete recommended action.
The UI may label a strong result as `SEO Optimized`, but must explain its thresholds.

The score is calculated before publication and again after WordPress synchronization.
It is not presented as Google PageRank or a guaranteed ranking outcome.

## Image Studio

Each project selects one default image style. A user can override it for each page or
image proposal.

Supported choices:

- Clean & Minimal Flat;
- Professional Illustrations;
- Photorealistic;
- Stock Photo Style;
- Watercolor;
- 3D Render;
- Vintage;
- Abstract.

Generated images are always proposals. Review shows preview, prompt, style, dimensions,
alt text, intended block, and provider/model. An image is added to WordPress only after
approval. Rejected images remain in the audit history but are not attached to a page.

## Content Calendar

The calendar schedules approved landing pages and updates to existing pages.

Capabilities:

- month and week views;
- drag-and-drop between days and time slots;
- project, page type, author, and status filters;
- project-specific timezone, defaulting to `Europe/Amsterdam`;
- status values `draft`, `in_review`, `approved`, `scheduled`, `published`, `failed`, and
  `cancelled`;
- choice between manual publication and automatic publication per calendar item;
- reminders for manual publication;
- conflict and failed-publication messages.

Automatic publication is possible only after the exact page version was manually
approved. Editing its content, links, SEO metadata, image, or schedule-critical settings
invalidates the approval. The user must approve the new version before automation can
continue.

The schedule stores the intended time in UTC and renders it using the project's timezone.
Jobs use durable backend scheduling and idempotency, not an open browser tab.

## PageSpeed

PageSpeed checks run:

- manually on request;
- automatically after publication;
- periodically, weekly by default.

Both mobile and desktop are measured. Results include Lighthouse lab signals and CrUX
field data when available. The dashboard explains each issue, affected resources, likely
impact, confidence, and a safe recommended action. Automated changes follow the same
proposal and approval safeguards as content changes.

## Search Console And GA4

### Search Console

Store daily page and query metrics including:

- clicks;
- impressions;
- CTR;
- average position;
- query;
- page URL;
- date.

### GA4

Store daily page and acquisition metrics including:

- sessions;
- users;
- engagement rate;
- selected key events/conversions;
- revenue when available;
- page path;
- source/medium;
- date.

Key events are selected per project. All GA4 key events are enabled by default, and the
project can narrow the selection.

OAuth connections, selected properties, sync cursors, errors, and last successful sync
are persisted and visible to the user.

## One-Year Impact Timeline

WP FixPilot keeps daily GSC, GA4, SEO-score, and PageSpeed measurements for one year.
Every page change adds an event marker containing:

- page and immutable content version;
- change type;
- approval and publication actor;
- publication timestamp;
- old and new SEO score;
- available GSC position, clicks, and impressions;
- available GA4 sessions, users, engagement, key events, and revenue;
- PageSpeed mobile and desktop results.

The timeline compares pre-change and post-change windows without claiming causality.
After one year, detailed daily rows may be removed only after monthly aggregates have
been created. Publication and audit events remain available according to the product's
audit retention policy.

## Core Data Boundaries

Suggested bounded components:

- `ProjectBrandDna`: versioned project identity and generation constraints.
- `PreferredLink`: project-level or page-specific user-supplied link candidate.
- `PageContentVersion`: immutable current/proposed page content snapshot.
- `SeoScoreSnapshot`: explainable factor scores for one page version.
- `ImageProposal`: reviewable image generation output.
- `CalendarItem`: approved-version schedule and publication mode.
- `PageMetricDaily`: normalized GSC, GA4, SEO-score, and PageSpeed daily metrics.
- `PageTimelineEvent`: publication, rewrite, link, image, and measurement event.

Modules communicate through identifiers and immutable versions. A calendar item never
stores mutable page content directly; it references an approved `PageContentVersion`.

## Error Handling And Auditability

- Retry transient AI, image, Google, and PageSpeed failures with bounded backoff.
- Do not retry validation, permission, or rejected-approval errors automatically.
- Expired OAuth access blocks only the affected sync and requests reconnection.
- A failed scheduled publication keeps the approved version intact and marks the item
  failed with a retry option.
- Sitemap and link errors show source URL, HTTP status, and recommended resolution.
- Log actor, project, page, version, provider, operation, result, and timestamp.
- Show external API usage, quota, and estimated cost per project where available.

## Testing And Release Gates

Each module requires:

- backend service and persistence tests;
- authorization and project-isolation tests;
- frontend interaction and accessibility tests;
- WordPress contract tests for writes;
- idempotency, retry, and cleanup tests;
- migration tests;
- deployment smoke tests against staging.

Content Calendar specifically requires drag-and-drop interaction tests, timezone and DST
tests, stale-approval tests, duplicate-job prevention, and failed-publication recovery.

Analytics requires OAuth renewal, pagination, quota, late-arriving data, missing metrics,
and one-year retention/aggregation tests.

## Out Of Scope For The First Blueprint Release

These modules are required roadmap work but do not block deployment of the current
managed-blueprint flow. They begin after that flow is live and verified. No feature in
this design may weaken the current human-review, immutable-version, or draft-first
safety rules.

