# Versioned Template Snapshots Release 1 - Task 7

## Scope

Replace mutable blueprint-page terminology with immutable WordPress template
snapshot identity and expose capture, verification, migration, and recovery
states in project settings.

## RED

- Snapshot identity, schema metadata, and native snapshot actions were absent.
- Migration outcomes were flattened into temporary UI state.
- Pending and incompatible recovery disappeared after reload.
- A targeted retry replaced sibling recovery states.
- Legacy page-package candidates exposed a migration action that could not
  process them.

## GREEN

- Settings show snapshot version, timestamps, builder, adapter/schema versions,
  editable field count, migration state, and source-page lineage.
- Native snapshots expose `Nieuwe versie opnemen` and `Controleren`, while
  referenced snapshots do not expose delete.
- The registry returns allowlisted persisted migration outcomes without raw job
  checkpoints or error details.
- Project migration and scoped per-template recovery use the same endpoint.
- Pending, incompatible, cleanup, and recapture guidance survives reload and
  targeted retries preserve all sibling recovery actions.
- Superseded legacy rows and non-migratable legacy settings do not show a
  misleading migration button.

## Verification

- Focused backend migration suite: 15 passed.
- Full backend: 381 passed, 6 optional PostgreSQL concurrency tests skipped.
- Focused frontend snapshot UI: 17 passed.
- Full frontend: 26 files, 92 tests passed.
- Ruff, ESLint, production build, and diff checks passed.

## Independent Review

- The first review found transient recovery state, sibling-state loss after a
  targeted retry, and a misleading legacy-candidate action.
- Regression tests were added before each production fix.
- Final independent re-review approved `799bc2e..76066dd` with no remaining
  Critical or Important findings.
