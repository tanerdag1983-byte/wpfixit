# Opportunity Lifecycle, Page Monitoring, And Images Design

Date: 2026-07-30
Status: Approved design

## Goal

WP FixPilot must keep discovering useful keyword opportunities, create safe
improvement proposals for existing pages, monitor pages after publication, and
add reviewable generated images to new and existing page proposals.

The work ships in four independently releasable phases:

1. durable keyword opportunity discovery;
2. existing-page improvement and monitoring;
3. template image proposals;
4. controlled blog inline images.

Every generated page or update remains a WordPress draft until a human publishes
it. Live pages are never changed during generation or approval.

## Product Decisions

- Old opportunities remain available when new opportunities are fetched.
- Each successful sync requests the next DataForSEO result window.
- Newly discovered opportunities appear first and receive a `Nieuw` label.
- Existing pages receive the same compare, edit, approve, and draft workflow as
  new pages.
- Improving an existing page creates a draft clone. It never overwrites the live
  page.
- Published and externally changed pages remain in continuous version, score,
  and recommendation history.
- New pages receive two different generated images by default: one featured
  image and one in-page image.
- Existing pages preserve current images. Missing images are proposed
  automatically and existing images can be replaced on request.
- One image candidate is generated per request. Regeneration instructions create
  another retained candidate rather than replacing an earlier candidate.
- Blog proposals may receive additional controlled inline images when content
  length and semantic sections justify them, with a maximum of four additional
  images.
- Generated images are proposals and require explicit selection and approval.
- Publication remains manual.

## Phase 1: Durable Keyword Opportunities

### Provider Pagination

The DataForSEO Keyword Ideas request uses `limit=50` and a persisted `offset`.
DataForSEO officially supports offset-based pagination for this endpoint.

Each project stores an opportunity sync state containing:

- the normalized seed fingerprint;
- next offset;
- last successful sync time;
- last completed sync run;
- last provider error;
- whether the current result range was exhausted.

When the seed fingerprint changes because the company profile, services, or
WordPress page inventory changed, the next offset resets to zero. An exhausted
result range also resets to zero for the following manual sync.

### Sync Runs

Each fetch creates a durable sync run with:

- project, seed fingerprint, offset, and limit;
- started and completed timestamps;
- provider result count;
- accepted, newly discovered, updated, and rejected counts;
- terminal state and safe error message.

A provider failure marks only the sync run failed. It does not remove or mutate
previously stored opportunities.

### Opportunity History

Keyword identity remains project, keyword, location, and language. Each
opportunity additionally records:

- first seen sync and timestamp;
- last seen sync and timestamp;
- latest metrics and target classification;
- current recommendation;
- optional dismissed timestamp;
- whether it was discovered by the latest successful sync.

Sync updates existing opportunities and inserts new ones. It no longer deletes
opportunities absent from one provider response.

The opportunities screen orders:

1. newly discovered items from the latest successful run;
2. remaining items by impact score and search volume.

The sync result reports counts such as `14 nieuw, 31 bijgewerkt, 5 niet
relevant`. Repeating an exhausted range creates no duplicates.

## Phase 2: Existing-Page Improvement And Monitoring

### Immutable Source Snapshot

An existing-page improvement starts by asking the WordPress bridge to capture an
immutable optimization snapshot of the target page. It reuses the proven
snapshot store and builder adapters but is scoped as a page revision source
rather than a reusable default template.

The snapshot contains:

- source WordPress post ID and canonical URL;
- source content hash and capture time;
- full builder structure, ACF data, media IDs, SEO metadata, and page template;
- typed text and image schema;
- adapter version and structure hash.

Editing or publishing the source page after capture does not change the
snapshot or proposal.

### Improvement Proposal

Both `new_page` and `existing_page` opportunities can create a proposal.

- `new_page` uses the selected default template snapshot.
- `existing_page` uses the immutable optimization snapshot of its matched page.
- `review` must first be assigned to an existing or new-page target by the user.

An existing-page proposal shows:

- current captured content and score;
- proposed content and projected score;
- field-level differences;
- evidence and expected benefit;
- retained images and proposed image changes;
- the target canonical URL.

Approval creates an outbound draft job bound to the source snapshot, proposal
version, and structure hash. WordPress creates a separate `page` in `draft`
status and returns one idempotent edit URL.

### Page Versions And Timeline

Every managed URL has durable page versions. A version records:

- WordPress post ID, canonical URL, and content hash;
- source type: synchronized, generated draft, or detected publication;
- captured text, SEO metadata, links, images, and builder identity;
- publication and observation timestamps;
- originating proposal and draft job when applicable.

WordPress synchronization creates a new version only when the canonical content
hash changes. The page timeline records:

- detected external edits;
- proposals and candidate versions;
- approvals and rejections;
- WordPress draft creation;
- detected publication;
- score snapshots and recommendations.

### Explainable Scores

Scores are versioned evidence, not mutable columns on the page and not claims
about Google ranking. Each factor stores its value, contribution, explanation,
and suggested action.

The first release calculates:

- on-page and technical SEO;
- title, meta description, headings, indexability, and canonical status;
- keyword coverage and search intent match;
- content quality, readability, and AI-answer readability;
- internal and external link evidence available from the current crawl;
- featured image, in-page image, and alt-text coverage;
- Brand DNA consistency when a project profile is available.

Later integrations add GSC, GA4, PageSpeed, CrUX, and richer link evidence to the
same score snapshot contract.

### Monitoring

Pages are checked:

- after every WordPress synchronization;
- manually on request;
- weekly by the durable scheduler.

A check compares the latest page version, score snapshot, keyword metrics, and
prior recommendations. It creates a new suggestion only when evidence or the
recommended change differs materially. It never generates a rewrite or changes
WordPress automatically.

Page status is one of:

- `monitoring`;
- `improved`;
- `needs_attention`;
- `proposal_ready`;
- `draft_ready`.

## Phase 3: Template Image Proposals

### Required Image Roles

Every new page proposal requires two different generated assets:

1. `featured_image`;
2. the first recognized in-page image slot.

The two selected assets must have different content hashes. If a template has no
recognized in-page image slot, it is not eligible for image-enabled generation
until a new template snapshot exposes one.

Existing-page proposals keep current images by default. A missing featured or
in-page image creates an automatic image request. A present image changes only
when the user requests a replacement.

### Image Candidates

Each candidate records:

- proposal version and stable image slot ID;
- role and intended semantic section;
- provider, model, prompt, and project image-style version;
- generation instruction;
- width, height, aspect ratio, crop policy, MIME type, and byte size;
- object-storage key, content hash, and preview URL;
- alt text, media title, caption, and filename;
- state, failure details, creation time, selection, and approval.

The first text proposal automatically queues one candidate for each required
image role. A regeneration request accepts additional instructions and creates
one new candidate. Previous candidates remain visible and selectable.

Selecting a candidate does not delete other candidates. Changing the selected
candidate invalidates image approval but does not invalidate approved text.

### Provider And Storage

Release 1 of image generation uses an image-capable OpenAI connection configured
for the project. The internal generation contract remains provider-neutral.

Generated bytes are stored in private object storage. Browser previews and
WordPress downloads use short-lived signed URLs. API keys and permanent storage
credentials are never returned to the browser or WordPress.

### WordPress Media Import

The outbound draft package contains approved image asset descriptors, not raw
image bytes. WordPress:

1. validates the trusted download origin and expiry;
2. downloads with timeout and byte limits;
3. verifies MIME type, file signature, dimensions, and pixel count;
4. creates or reuses a Media Library attachment by immutable asset identity;
5. writes alt text and allowed media metadata;
6. sets the featured image or schema-listed builder image field;
7. verifies the resulting media IDs and draft status.

Retrying the same job reuses the same attachments and draft. Any failed media or
field write deletes the incomplete clone and newly orphaned attachments.

The draft button remains disabled until required text and image selections are
approved.

## Phase 4: Controlled Blog Inline Images

Blog templates expose stable inline image anchors between semantic blocks.
Images are separate adapter-owned blocks or elements; AI may not inject image
HTML into rich text.

Every blog already receives the required featured and first in-page images.
Additional inline images are proposed only when:

- the article contains enough distinct H2-level sections;
- the neighboring section has a concrete visual subject;
- the new image does not duplicate an earlier image role.

The planner may add zero to four additional images. Each uses the same
candidate, regeneration, selection, approval, storage, and WordPress import
workflow as template image slots.

Regenerating nearby text preserves an approved image unless the section meaning
changes materially. In that case the image is marked `needs_review`.

## User Experience

### Opportunities

- `Nieuwe kansen ophalen` shows progress and the completed sync counts.
- Newly discovered rows show `Nieuw`.
- Existing-page rows show `Verbeteringsvoorstel maken`.
- Generated rows show `Voorstel bekijken` and `Opnieuw genereren`.
- Old opportunities remain available and keep their proposal history.

### Proposal Review

The current full-width preview remains above the editable fields.

Existing-page proposals add a current-versus-proposed comparison and score
factor changes. Image slots show:

- current image when present;
- all generated candidates;
- selected candidate;
- prompt, style, dimensions, and alt text;
- `Afbeelding opnieuw genereren` with one shared instruction field;
- explicit select, approve, reject, and keep-current actions.

Text, images, links, SEO data, and scores are persisted independently. Reloading
the browser resumes the current stage without repeating completed provider work.

### Page Monitoring

Every page receives:

- current score and factor explanations;
- score trend by version;
- latest sync and next scheduled check;
- open suggestions;
- complete page timeline.

## Failure And Recovery

- DataForSEO failure retains all existing opportunities and the prior cursor.
- A sync cursor advances only after a successful committed run.
- Snapshot capture failure creates no proposal.
- Text generation, validation, image generation, and WordPress draft creation
  are independently resumable stages.
- One failed image candidate does not remove older candidates or approved text.
- Retrying a candidate or draft uses an idempotency key.
- A stale source or template snapshot is rejected before any WordPress write.
- Partial WordPress clones and orphaned imported media are cleaned up.
- User-facing errors name the failed stage and offer one specific recovery
  action without exposing secrets or raw provider payloads.

## Security And Safety

- WP FixPilot never publishes automatically.
- Existing live pages remain immutable during generation and approval.
- AI may change only schema-listed text, approved URLs, and recognized image
  slots.
- Image downloads require signed, expiring URLs and strict file validation.
- Provider credentials remain encrypted server-side.
- Every proposal, score, image candidate, approval, import, and retry is
  auditable.
- Changing text, links, SEO metadata, or selected images after approval
  invalidates only the affected approval and blocks draft creation until
  reviewed.

## Testing And Acceptance

### Keyword Opportunities

- offset advances only after successful provider and database completion;
- seed changes and exhaustion reset pagination correctly;
- old opportunities survive successful and failed syncs;
- new and updated counts are accurate;
- repeated windows create no duplicates;
- frontend order, `Nieuw` labels, loading, and errors are covered.

### Existing Pages And Monitoring

- all supported builders capture immutable optimization snapshots;
- source edits after capture do not change proposals;
- existing-page proposals compare and approve correctly;
- draft creation never mutates the source page and is idempotent;
- page versions are created only for changed hashes;
- factor scores and recommendations are reproducible and explainable;
- weekly and manual checks do not create duplicate suggestions.

### Images

- two distinct required images are generated for every eligible new proposal;
- missing images are proposed for existing pages without replacing present media;
- regeneration adds one candidate and retains earlier candidates;
- selection and approval survive reload;
- signed URL, MIME, signature, size, dimensions, and pixel limits are enforced;
- WordPress import, attachment reuse, cleanup, and field application pass under
  PHP 8.2;
- text regeneration preserves approved image selections;
- controlled blog anchors support zero to four additional images.

### Live Acceptance

Each phase is deployed and accepted independently:

1. fetch at least three consecutive DataForSEO windows and confirm new rows are
   retained without duplicates;
2. create, approve, and import two improvement drafts from different existing
   pages without modifying either source;
3. synchronize a manually published or edited page and verify a new page
   version and score snapshot;
4. create two new-page drafts with distinct featured and in-page images;
5. regenerate one image, choose between retained candidates, and confirm only
   the selected asset reaches WordPress;
6. create two blog drafts with controlled additional inline images;
7. force one failure in every persisted stage and resume without duplicate
   provider charges, drafts, or media attachments.

## Delivery Order

The implementation order is binding:

1. durable keyword opportunity discovery;
2. existing-page snapshots, proposals, versions, scores, and monitoring;
3. required template image candidates and WordPress media import;
4. controlled blog inline images.

No phase is marked complete without migrations, real API behavior, visible
status, error handling, tests, independent review, deployment, and staging
acceptance.

## Roadmap After These Releases

The following approved work remains open and must stay in the progress ledger:

1. complete per-project AI providers, models, company profile, and prompt;
2. Google Search Console OAuth, property selection, sync, trends, and
   opportunities;
3. GA4 OAuth, property selection, traffic, engagement, conversion, and revenue;
4. sitemap import and recurring URL discovery;
5. internal-link analysis, approved updates, orphan detection, and suggestions;
6. external-link validation, quality checks, and recommendations;
7. PageSpeed and CrUX checks with safe recommendations;
8. Yoast, Rank Math, and All in One SEO metadata support;
9. combined SEO priority scoring using WordPress, crawl, GSC, GA4, and
   DataForSEO;
10. drag-and-drop Content Calendar with manual or explicitly pre-approved
    publication;
11. project Brand DNA, rewrite versions, image style, and explainable score
    history across every page.

## Out Of Scope

- automatic publication;
- direct mutation of a live WordPress page;
- free-form AI changes to builder structure;
- arbitrary image HTML inside rich text;
- silent replacement of an existing image;
- multiple image candidates per provider request;
- GSC, GA4, PageSpeed, advanced links, and calendar implementation inside these
  four releases.
