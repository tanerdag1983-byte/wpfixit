# DataForSEO Relevance Filtering Design

## Goal

WP FixPilot must only show keyword opportunities that are demonstrably relevant
to the project's company profile, services, and WordPress pages. Generic terms
such as `auto` or `kosten` must not be enough to connect an unrelated keyword to
an automotive transmission page.

## Root Cause

The current synchronizer sends the project domain, project name, and the most
recent WordPress page titles to the broad DataForSEO keyword ideas endpoint. It
then accepts every returned keyword and matches pages by counting any shared
token of four or more characters. This lets generic words such as `kosten` match
unrelated topics, while previously imported irrelevant opportunities remain in
the database after later synchronizations.

## Context And Seed Selection

The synchronizer will build a project vocabulary from:

- company name, description, target audience, and services from the project
  company profile;
- meaningful words and phrases from WordPress page titles and slugs;
- the project name as a fallback when no company profile exists.

Hostnames, boilerplate pages, and generic intent words are not standalone seed
terms. Multi-word service phrases take priority over individual words. The
number of submitted seeds remains bounded so one synchronization remains a
single predictable DataForSEO request.

## Relevance And Page Matching

Each candidate receives deterministic relevance evidence:

1. It must overlap with at least one business/service anchor.
2. It must overlap with a page-specific phrase or token before it can target
   that page.
3. Generic tokens such as `auto`, `kosten`, `bedrijf`, and `service` contribute
   no relevance by themselves.
4. Phrase matches and distinctive service-token matches receive more weight
   than incidental token overlap.

Candidates without business relevance are discarded. Relevant candidates that
do not fit an existing page may still become a new-page opportunity. Existing
page matches include the strongest matching page URL and a concrete action.

This filtering is deliberately deterministic. AI reranking is not required for
correctness, does not add provider cost, and cannot introduce an unrelated
keyword by overriding the relevance rules.

## Synchronization Semantics

A successful synchronization is a fresh snapshot. Accepted opportunities are
upserted, and previous DataForSEO opportunities for that project that are absent
from the new accepted set are deleted. A failed provider request leaves the
existing snapshot untouched.

## Settings Guidance

The DataForSEO password field will explicitly say that it requires the
automatically generated API password rather than the normal account password.
It will include a direct link to `https://app.dataforseo.com/api-access`.

## Tests

Backend tests will cover:

- profile services and relevant WordPress phrases becoming seeds;
- generic words not becoming standalone seeds;
- unrelated candidates such as `autosleutel bijmaken` and `krassen auto
  verwijderen kosten` being rejected for a transmission business;
- relevant candidates such as `koppeling vervangen kosten` and `DSG automaat
  reviseren` mapping to the correct pages;
- stale opportunities being removed only after successful synchronization.

Frontend tests will verify the API-password explanation and link.
