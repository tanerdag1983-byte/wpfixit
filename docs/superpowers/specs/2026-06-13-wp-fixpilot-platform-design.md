# WP FixPilot Platform Design

## Goal

WP FixPilot is a multi-tenant SaaS platform that combines WordPress content,
technical crawl data, Google Search Console, Google Analytics 4, and AI-assisted
analysis into prioritized SEO recommendations. Users can approve selected
changes before WP FixPilot publishes them to WordPress.

The first release supports up to 5,000 crawled URLs per project and three
dashboard views: Analytics, Action Workspace, and Hybrid Command Center. Each
user's preferred view is stored independently.

## Product Scope

The platform includes:

- Supabase registration, login, user profiles, organizations, and projects;
- a WordPress bridge plugin for inventory, audits, approved writes, history,
  and rollback;
- Google OAuth 2.0 connections owned by an authenticated user;
- property selection for Search Console and GA4;
- scheduled and manually triggered data synchronization;
- external crawling through Firecrawl behind a provider-neutral interface;
- deterministic SEO audits and opportunity scoring;
- AI-generated recommendations based on structured evidence;
- subscriptions and usage limits;
- dashboards, filters, search, histories, and approval workflows.

The platform does not autonomously publish changes. Every WordPress mutation
requires an explicit approval from an authorized project member.

## Architecture

The first release uses a modular monolith plus background workers.

- `frontend`: React, Vite, TypeScript, Tailwind CSS, shadcn/ui, React Router,
  TanStack Query, Recharts, React Hook Form, and Zod.
- `backend`: FastAPI, Python 3.12, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL,
  Redis, and Celery.
- `database/auth`: Supabase PostgreSQL and Supabase Auth.
- `workers`: Celery workers for WordPress syncs, crawls, Google imports,
  audits, recommendation generation, and publishing.
- `crawler`: Firecrawl v2 through a `CrawlerProvider` interface.
- `AI`: OpenAI structured outputs through a provider interface.
- `hosting`: Vercel for the frontend, Render web and worker services, Supabase
  for database and authentication.

The API is organized by domain rather than kept in one route file:

- identity and memberships;
- projects;
- WordPress connections, sync, and publishing;
- crawls and crawl findings;
- Search Console;
- GA4;
- audits and recommendations;
- priority scoring;
- dashboards;
- subscriptions and usage.

Long-running operations return a job resource immediately. The frontend polls
the job endpoint and receives progress, completion, or actionable failure data.

## Security And Tenancy

Supabase access tokens authenticate API calls. The backend validates token
issuer, audience, signature, and expiry. Every project query is scoped through
organization membership; project IDs alone never grant access.

Google OAuth uses Authorization Code flow with PKCE, `state`, incremental
consent, and offline access. Refresh tokens are encrypted at application level
with versioned key encryption before storage. Logs and API responses never
contain access tokens, refresh tokens, WordPress credentials, or bridge secrets.

The Google connection belongs to the user who authorized it. A project binding
records which Search Console and GA4 properties use that connection. Revoking a
connection disables affected bindings without deleting historical metrics.

The WordPress bridge uses:

- a per-project secret;
- signed requests with timestamp and nonce;
- short replay windows;
- WordPress capability checks;
- an allowlist of supported mutation types;
- immutable change records before and after every write.

## Data Model

All primary keys are UUIDs. Timestamps use timezone-aware UTC values.

### Identity And SaaS

- `profiles`: Supabase user metadata and dashboard preference.
- `organizations`: tenant account.
- `organization_members`: user role per organization.
- `subscriptions`: provider status, plan, period, and limits.
- `projects`: organization, name, canonical domain, timezone, and status.
- `jobs`: asynchronous job type, state, progress, error, and timestamps.
- `usage_events`: crawled pages, AI operations, and sync consumption.

### WordPress And Audits

- `wordpress_connections`: project bridge URL, encrypted secret, plugin
  version, detected SEO plugin, and health state.
- `wordpress_pages`: WordPress object ID, type, status, canonical URL, title,
  slug, content hash, modified time, and last sync.
- `page_audits`: page score and normalized audit facts.
- `seo_issues`: typed issue, severity, evidence, and status.
- `seo_recommendations`: action type, priority, rationale, evidence, generated
  proposal, approval state, and model metadata.
- `wordpress_changes`: approved proposal, before value, after value, publish
  result, actor, and rollback state.

### Crawl

- `crawl_runs`: provider, root URL, 5,000 URL limit, state, totals, and timing.
- `crawl_pages`: normalized URL, status, redirect target, canonical, robots,
  title, description, headings, content hash, indexability, performance facts,
  and structured data summary.
- `crawl_links`: source URL, target URL, anchor, internal flag, follow flag,
  and HTTP state.
- `crawl_issues`: broken links, redirect chains, duplicate metadata, orphan
  candidates, canonical conflicts, noindex conflicts, and crawlability issues.

### Google

- `google_connections`: user, encrypted tokens, scopes, expiry, and revocation.
- `gsc_connections`: project, Google connection, property URI, permission,
  state, and last sync.
- `gsc_page_performance`: project, property, date, normalized page URL, clicks,
  impressions, CTR, and average position.
- `gsc_queries`: project, property, date, query, optional page URL, clicks,
  impressions, CTR, and average position.
- `ga4_connections`: project, Google connection, account ID, property ID,
  display name, currency, timezone, state, and last sync.
- `ga4_page_performance`: project, property, date, normalized page path,
  sessions, active users, engagement rate, key events, and revenue.
- `ga4_traffic_sources`: project, property, date, source, medium, campaign,
  sessions, users, engagement rate, key events, and revenue.

Daily metric tables use unique composite constraints and upserts so syncs are
idempotent. Raw provider payloads are not retained unless needed for a failed
job diagnosis and are then time-limited.

## URL Identity

Cross-source joins use a project URL normalizer:

- lowercase host;
- remove default ports;
- normalize trailing slashes;
- drop fragments;
- retain query parameters only when configured;
- map GA4 page paths onto the project's canonical origin;
- retain original provider URL for traceability.

Each data source keeps its own record, while `normalized_url` enables page-level
aggregation without forcing destructive merges.

## Google Integrations

One OAuth consent can request read-only Search Console and Analytics scopes.
The connection wizard then loads:

- Search Console properties accessible to the user;
- GA4 accounts and properties accessible to the user.

Search Console syncs daily data using `date`, `query`, and `page` dimensions.
It stores page aggregates separately from query-page rows. Sync windows overlap
recent dates so delayed Google data is corrected through upserts.

GA4 syncs separate reports for:

- page path by date;
- session source/medium/campaign by date.

Metrics include sessions, active users, engagement rate, key events, and total
revenue where available. The UI labels GA4 key events as conversions while
preserving the provider field meaning internally.

## Crawl Integration

`FirecrawlProvider` implements:

- start crawl;
- query crawl status;
- retrieve paginated results;
- cancel crawl;
- translate provider failures into stable application errors.

The crawl is restricted to the verified project domain, follows internal links,
respects robots rules, excludes logout/admin/search-space traps, and caps each
run at 5,000 URLs. Provider webhooks are verified and made idempotent. Polling
remains available as a fallback.

The interface allows a later provider replacement without changing audit,
priority, or dashboard services.

## Audit And Recommendation Engines

The deterministic engine runs first. It evaluates:

- titles, descriptions, slugs, headings, canonicals, indexability, and status;
- broken internal links, redirect chains, duplicate metadata, and orphan risks;
- WordPress page state and detected SEO plugin;
- GSC CTR and position opportunities;
- GA4 engagement, key events, revenue, and traffic quality;
- trend changes against a comparable previous period.

The AI engine receives only structured facts and bounded page excerpts. It
returns schema-validated proposals, rationale, expected impact, confidence, and
evidence references. AI output never directly writes to WordPress.

Recommendations include:

- SEO title and meta description proposals;
- content expansion and content gap actions;
- internal link additions with suggested source, target, and anchor;
- redirect, canonical, and noindex changes;
- CTR and conversion improvements;
- technical remediation instructions.

## Priority Score

Each page receives a score from 0 to 100:

- audit severity and low SEO score: 25 points;
- impressions and CTR opportunity: 20 points;
- ranking opportunity: 15 points;
- traffic with weak key-event rate: 15 points;
- negative trend: 10 points;
- page importance from traffic, revenue, links, and page type: 10 points;
- confidence and data completeness: 5 points.

Signals are normalized within the project and bounded to avoid a single large
metric dominating the score. Missing sources lower confidence but do not force
the score to zero. Each result includes the component scores, evidence, and one
concrete next action.

`GET /projects/{id}/seo-priority-score` returns URL, current SEO score, clicks,
impressions, CTR, average position, sessions, key events, priority score,
confidence, reasons, and concrete action.

## WordPress Publishing

The bridge supports Yoast SEO, Rank Math, and All in One SEO through plugin-side
adapters. Supported approved changes are:

- SEO title and meta description;
- post or page content;
- internal links;
- redirects;
- canonical URL;
- noindex state.

Publishing uses a two-step workflow:

1. create or generate a proposal with an exact diff;
2. an authorized user approves and publishes it.

Before mutation, the backend verifies that the WordPress content hash still
matches the proposal base. Conflicts require a refreshed proposal. Every
successful mutation stores before and after values. Rollback is another audited
mutation and requires confirmation.

## API Surface

The API keeps the requested routes and adds callback, property, job, crawl, and
publishing resources.

Core requested routes:

- `POST /projects/{id}/connect-search-console`
- `POST /projects/{id}/sync-search-console`
- `GET /projects/{id}/search-console-data`
- `POST /projects/{id}/connect-ga4`
- `POST /projects/{id}/sync-ga4`
- `GET /projects/{id}/ga4-data`
- `GET /projects/{id}/seo-priority-score`

Supporting routes include:

- Google OAuth start and callback;
- accessible Google properties;
- project property binding and disconnect;
- WordPress connect, health, inventory, sync, and publish;
- crawl start, status, result, and history;
- jobs and job cancellation;
- audit, issues, recommendations, approvals, publishing, and rollback;
- dashboard overview and saved user preference;
- project CRUD, membership, subscription, and usage.

Collection endpoints accept date ranges, pagination, sort, search, and combined
filters. Expensive exports are asynchronous.

## Frontend

The authenticated application uses:

- organization and project switchers;
- onboarding for WordPress, Google, and crawl setup;
- connection health and last-sync status;
- global date range and comparison controls;
- accessible charts with tabular alternatives;
- searchable and filterable page tables;
- recommendation review with evidence and exact diffs;
- publish and rollback confirmation dialogs.

The user can switch among:

1. **Analytics Console**: KPI and trend-forward reporting.
2. **SEO Action Workspace**: prioritized tasks and approval queues.
3. **Hybrid Command Center**: trends and highest-impact actions together.

The preference is stored on `profiles.dashboard_view`. The three views consume
the same API resources and do not duplicate business logic.

Primary tabs include Overview, Search Console, GA4, Opportunities, SEO Priority,
Issues, Recommendations, Crawl, and History.

## Failure Handling

Provider and job errors use stable error codes with user-safe messages.
Retryable failures use exponential backoff with jitter. OAuth revocation,
property access loss, API quota exhaustion, crawl limits, WordPress conflicts,
and partial imports are represented explicitly in connection and job states.

Imports stage data and commit in bounded batches. A failed batch can resume from
its checkpoint. Existing successful historical data remains visible when a new
sync fails.

## Testing

The backend uses pytest with:

- unit tests for URL normalization, audits, adapters, and priority scoring;
- route tests for authorization and tenant isolation;
- contract fixtures for Google, Firecrawl, OpenAI, and WordPress responses;
- database integration tests against PostgreSQL;
- worker tests for idempotency, retry, and resume behavior.

The frontend uses Vitest, Testing Library, and Playwright for:

- connection and property-selection flows;
- all three dashboard views and saved preference;
- filters, searches, date comparison, loading, empty, and error states;
- recommendation approval, conflict, publish, and rollback flows;
- accessibility checks.

The WordPress plugin uses PHPUnit for authentication, capability checks, plugin
adapters, writes, and rollback.

## Delivery

The work is implemented as one continuous build, but internally sequenced so
each milestone remains testable:

1. repository, local infrastructure, CI, auth, tenancy, and project CRUD;
2. WordPress bridge, inventory, audits, issues, and recommendations;
3. dashboard foundation, filters, search, history, and subscriptions;
4. Google OAuth, Search Console, and GA4;
5. Firecrawl integration and crawl findings;
6. combined priority engine and AI recommendations;
7. approval, WordPress publishing, rollback, and all three dashboard views;
8. deployment configuration, security checks, and end-to-end verification.

## External API Basis

The design targets the current official APIs:

- Search Console Search Analytics for date/query/page performance;
- Google Analytics Data API `runReport` for page and acquisition reporting;
- Firecrawl v2 crawl and map endpoints with an application limit of 5,000 URLs.

Provider-specific behavior remains isolated behind adapters so API changes do
not leak into the audit and dashboard domains.
