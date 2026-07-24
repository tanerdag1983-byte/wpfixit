# Versioned Template Snapshots Release 1 - Task 8

## Scope

Show the fixed template, text, and validation stages; preserve successful work
after failures; and let users correct, retry, compare, and approve snapshot-bound
page proposals without exposing provider validation details.

## RED

- Snapshot proposals did not expose resumable stage state or bounded field errors.
- Regeneration candidates used the legacy package path and lost stage readiness.
- Optional errors blocked approval or exposed a recovery action that could not edit.
- Validation retries could replace saved corrections with stale generated text.
- Candidate comparison hid changed or omitted snapshot fields.
- Accepted candidates could reuse stale URL evidence or lose optional values.
- Raw provider and Pydantic errors could reach the review screen.

## GREEN

- The review screen shows the ordered template, text, and validation stages.
- Required field errors block approval; optional errors remain editable and do not.
- Corrected values are saved before retry, and retries use the current stored package.
- Text retries follow the new immutable proposal version.
- Snapshot candidates compare changed and omitted fields before acceptance.
- Omitted optional values and current validated URL allowlists survive acceptance.
- Accepted candidates receive ready stages, can be reapproved, and produce a valid
  outbound WordPress draft-job contract.
- Failed or generating candidates never expose an acceptance action.
- User-facing actions map only allowlisted errors and otherwise show bounded Dutch
  fallback messages.

## Verification

- Focused backend proposal route and version suites: 40 passed.
- Full backend: 384 passed, 6 optional PostgreSQL concurrency tests skipped.
- Full frontend: 27 files, 106 tests passed.
- Ruff, ESLint, production build, and diff checks passed.

## Independent Review

- Four independent review rounds found and drove regressions for optional approval,
  snapshot-stage acceptance, comparison visibility, URL evidence, local correction
  persistence, omitted fields, and candidate status actions.
- Every finding received a failing regression before the production fix.
- Final independent review approved `ab1f94a..8818e8b` with zero Critical,
  Important, or Normal findings.
