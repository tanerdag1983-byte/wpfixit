# SEO Intelligence And Controlled Automation Design

## Goal

Extend WP FixPilot into a project-aware SEO intelligence platform that combines
WordPress, Google, crawler, sitemap, performance, competitor and AI data. The
platform may automatically activate audit rules sourced from official Google
publications, but every website change always requires explicit user approval.

## Non-Negotiable Safety Rules

- No content, metadata, link, redirect, builder or performance change is
  published without explicit approval.
- Every proposal records evidence, source dates, expected impact, confidence,
  risk, detected builder, detected SEO plugin and a reversible change set.
- Publishing is blocked when the builder is unknown or unsupported.
- Publishing is blocked when the current WordPress content hash differs from
  the hash used to create the proposal.
- Hosting, server, CDN and other infrastructure changes are instructions only
  unless a future dedicated, tested adapter is introduced.
- Official Google audit-rule updates may activate automatically. They may
  generate findings and proposals, but may never publish website changes.

## Architecture

All inputs feed a central evidence and proposal engine. Provider adapters
translate external APIs into stable internal records. Deterministic analyzers
produce opportunities and risk signals before AI is used to explain, enrich or
draft a change. The existing proposal, approval, publish and rollback workflow
remains the only route to modifying WordPress.

The system is divided into independent domains:

- AI provider registry and project model policy;
- project company profile and prompt;
- sitemap and URL inventory;
- WordPress capability detection and builder adapters;
- traffic intelligence;
- keyword and competitor intelligence;
- internal-link intelligence;
- performance and Core Web Vitals;
- official Google SEO updates;
- unified approval and publication.

## AI Provider Registry

An organization may store multiple encrypted AI connections:

- OpenAI;
- Anthropic Claude;
- Google Gemini;
- OpenAI-compatible endpoints such as OpenRouter, Groq and Ollama.

Each connection has its own name, provider, endpoint, encrypted credential,
available model identifiers and connection status. A project selects a primary
connection/model and an optional fallback connection/model. Provider failure
may use the configured fallback, but it may not silently select another model.

The project company profile, audience, services, tone of voice and custom
prompt remain project-specific. Generated recommendations record the provider,
model, prompt version and evidence IDs used.

## Sitemap And URL Inventory

Projects may contain multiple sitemap sources. The system:

- discovers `/sitemap.xml` and `/sitemap_index.xml`;
- imports sitemap indexes recursively with bounded depth and URL limits;
- recognizes common Yoast, Rank Math and All in One SEO sitemap locations;
- accepts manually entered sitemap URLs;
- validates that imported URLs belong to the verified project domain;
- records `lastmod`, source sitemap, discovery time and import status;
- deduplicates URLs shared by WordPress, crawls, sitemaps, GSC and GA4.

The unified URL inventory marks URLs that are indexed, receiving traffic,
linked internally, present in WordPress, or present only in a sitemap.

## WordPress Capabilities

The bridge health and inventory responses expose:

- active SEO plugin and version;
- active theme;
- builder used per object;
- supported write capabilities;
- sitemap URLs exposed by WordPress or the SEO plugin.

SEO plugin adapters remain available for:

- Yoast SEO;
- Rank Math;
- All in One SEO.

Builder adapters are introduced for:

- Gutenberg blocks;
- ACF Blocks;
- Elementor;
- WPBakery Page Builder;
- Bricks.

Adapters read and update native structured data instead of flattening a page
into HTML. A proposal carries the builder and adapter version detected during
analysis. Unknown builders allow analysis and proposals but block publication.

## Traffic Intelligence

Search Console and GA4 are analyzed together rather than displayed only as raw
charts. The engine identifies:

- declining clicks, impressions, CTR, position, sessions and conversions;
- high-impression queries with low CTR;
- ranking pages with insufficient clicks;
- landing pages with traffic but weak engagement or conversion;
- query-to-page mismatches and cannibalization;
- pages visible in GSC but absent from GA4, and the reverse;
- device and date-period differences where the source supports them.

Every insight includes comparison periods, source coverage, data freshness and
confidence. Missing or low-volume data is presented as insufficient evidence,
not converted into a definite recommendation.

## Keyword And Competitor Opportunities

Keyword discovery combines first-party and external evidence:

- GSC queries and landing pages;
- GA4 organic landing-page behavior and conversions;
- existing WordPress content and headings;
- sitemap and crawl inventory;
- DataForSEO search volume, SERP, intent, difficulty and competitor gaps.

DataForSEO is the first external provider behind a replaceable provider
interface. Opportunities record source, country, language, retrieval date,
volume, competition, intent, relevant project pages and confidence.

The engine may propose:

- improving an existing page;
- resolving cannibalization;
- creating a new page;
- changing title, description, headings or on-page copy;
- adding structured data where applicable;
- adding or revising internal links.

All generated changes enter the approval workflow.

## Internal-Link Intelligence

The link graph combines crawler links, WordPress content and sitemap URLs. It
detects orphan risks, broken internal links, redirect chains, excessive depth,
weakly linked important pages and anchors that do not describe their target.

A link proposal identifies source URL, target URL, proposed anchor, insertion
context, reason and expected effect. Builder adapters apply approved changes to
the native content structure. Existing valid links are preserved, duplicate
links are avoided and no link is added solely to manipulate rankings.

## PageSpeed And Core Web Vitals

Performance analysis separates field and lab data:

- CrUX API for current real-user LCP, INP and CLS at URL or origin level;
- CrUX History API for regressions and trends;
- PageSpeed Insights and Lighthouse for mobile and desktop diagnostics.

Important URLs are selected from traffic, conversions, priorities, WordPress
inventory and sitemaps. The engine stores metric values, form factor, scope,
collection period, Lighthouse categories, diagnostics and data availability.

Recommendations cover images, fonts, render-blocking resources, JavaScript,
CSS, caching, layout shifts and WordPress-specific causes. Safe builder-aware
changes become approval proposals. Server, CDN, cache-plugin and hosting
changes become reviewed implementation instructions.

## Google SEO Update Center

Only official Google sources can automatically modify active audit rules:

- Google Search Central documentation update RSS;
- Google Search Central Blog;
- Google Search Status Dashboard and ranking incidents;
- Search Essentials and relevant structured-data documentation.

The system stores the original source URL, publication/update date, retrieval
time, content fingerprint and interpreted rule change. Duplicate updates are
ignored. An automatically activated rule must retain the official source and
must not claim requirements beyond the source.

Each activation creates a short Dutch dashboard update containing:

- what Google changed;
- which audit rule changed;
- affected projects or pages;
- recommended follow-up.

Dashboard delivery is mandatory. Users may opt in to the same concise update
by email. Email preferences are per user and default to off.

## Unified Proposal And Approval Center

Every proposed website change shows:

- project, URL and WordPress object;
- evidence and source dates;
- expected SEO, traffic, conversion or performance impact;
- confidence and risk;
- detected builder and SEO plugin;
- before/after structured diff;
- validation result;
- approval, publication and rollback state.

Approval is always explicit and attributable to a signed-in user. Publishing
revalidates permissions, builder support and content hash. Change events are
immutable. Rollback restores the recorded previous state through the same
builder and SEO-plugin adapter.

## User Interface

The existing visual direction remains. New or expanded screens are:

- AI Connections: multiple providers and connection tests;
- Project AI Policy: primary model, fallback model and project prompt;
- WordPress Connection: visible builder and SEO-plugin capability status;
- Sitemaps: discovery, multiple sources and import status;
- Traffic Intelligence: combined GSC and GA4 findings;
- Keyword Opportunities: first-party and DataForSEO evidence;
- Internal Links: graph findings and proposals;
- Performance: CrUX, PageSpeed and trend views;
- Google Updates: official changes and email preference;
- Approval Center: all proposed change types in one review flow.

## Error Handling And Data Quality

- Provider errors are translated into stable user-facing states.
- Syncs are idempotent and retain the last successful data.
- Credentials are never returned to the frontend after storage.
- Rate limits use bounded retries and backoff.
- Sitemap recursion, external URLs and malformed XML are bounded and rejected.
- AI output is schema validated and cannot manufacture evidence IDs.
- Low-confidence opportunities remain suggestions and receive lower priority.
- Failed publication never marks a proposal as published.

## Testing Strategy

- Contract tests for every AI and DataForSEO provider adapter.
- OAuth, encryption and credential-redaction tests.
- Sitemap index, malformed XML, domain-boundary and deduplication tests.
- GSC/GA4 comparison and low-data tests.
- Keyword evidence, country/language and confidence tests.
- Link-graph and duplicate-anchor tests.
- Builder fixture tests for Gutenberg, ACF, Elementor, WPBakery and Bricks.
- SEO metadata tests for Yoast, Rank Math and All in One SEO.
- CrUX and PageSpeed field/lab separation tests.
- Google update fingerprint, source allowlist and automatic-rule tests.
- Dashboard/email notification preference tests.
- Approval, stale-content conflict, publication and rollback tests.
- Responsive frontend tests for every new screen.

## Delivery Sequence

1. Multiple AI connections and project primary/fallback policy.
2. Sitemap manager and WordPress builder/SEO-plugin capability reporting.
3. Combined GSC and GA4 Traffic Intelligence.
4. DataForSEO keyword and competitor opportunities.
5. Internal-link graph and builder-aware proposals.
6. PageSpeed, CrUX and Core Web Vitals.
7. Google SEO Update Center and optional email delivery.
8. Unified Approval Center and end-to-end publication verification.

Each phase must result in independently testable software and may not bypass
the approval rules established in this design.
