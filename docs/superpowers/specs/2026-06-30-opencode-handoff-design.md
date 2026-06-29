# OpenCode Handoff Design

## Goal

Make `wp-fixpilot-new` immediately understandable and safely resumable in
OpenCode when the active Codex session or allowance is unavailable. The
handoff must help the next agent continue the existing implementation instead
of rediscovering the repository or introducing new scope.

The immediate product objective is to reach a reliable production release as
quickly as possible. Work that does not reduce launch risk or complete an
already approved feature remains out of scope.

## Artifacts

### `AGENTS.md`

Create a durable repository-level instruction file shared by Codex and
OpenCode. It will summarize:

- the modular-monolith architecture and the responsibilities of `backend`,
  `frontend`, `plugin`, `infrastructure`, and `docs`;
- the approved design and implementation-plan workflow;
- focused and full verification commands for Python, TypeScript, and the
  WordPress bridge;
- security and tenancy invariants, including explicit approval before any
  WordPress mutation and the prohibition on logging credentials;
- Git discipline, migration safety, deployment checks, and avoidance of
  unrelated refactors.

The instructions will point to existing authoritative documents instead of
duplicating their full contents.

### `HANDOFF.md`

Create a short-lived operational handoff describing the exact continuation
point:

- branch `main` at commit `721dd07` (`docs: plan managed page blueprints`);
- a clean working tree when the handoff was prepared;
- Managed Page Blueprints is designed and planned but not implemented;
- the implementation starts at Task 1 in
  `docs/superpowers/plans/2026-06-28-managed-page-blueprints.md`;
- representative planned implementation files are still absent;
- OpenCode must inspect `git status`, read `AGENTS.md`, the blueprint design,
  and the blueprint plan before editing;
- OpenCode must execute the existing plan task by task, use focused tests, and
  preserve compatibility with the existing page-package routes;
- launch-critical verification and deployment documentation must be followed
  before declaring the software ready.

Because repository state can change, `HANDOFF.md` will explicitly instruct the
next agent to verify commit and working-tree assumptions rather than treating
them as permanent truth.

## Continuation Flow

1. Start OpenCode in the repository root.
2. Read `AGENTS.md` and `HANDOFF.md`.
3. Verify the current branch, commit, worktree, and existing implementation.
4. Read the Managed Page Blueprints design and implementation plan.
5. Resume at the first genuinely incomplete plan step.
6. Run focused tests after each task and the complete relevant verification
   before launch or deployment.

## Scope And Safety

- Do not copy credentials, provider tokens, or private customer data into the
  handoff.
- Do not claim the blueprint implementation has started when only its design
  and plan exist.
- Do not make `HANDOFF.md` a second implementation plan; the existing plan is
  authoritative.
- Do not deploy automatically. Deployment remains an explicit, verified action
  following `docs/deployment.md`, `docs/live-deploy.md`, and
  `docs/operations.md`.
- If Managed Page Blueprints proves nonessential for the first production
  release, surface that decision to the user instead of silently abandoning
  the approved plan.

## Success Criteria

- A fresh OpenCode session can identify the architecture and safety rules
  without repository-wide rediscovery.
- It can identify the exact active feature and first incomplete task.
- It can run the correct verification commands and avoid unsafe WordPress,
  tenancy, credential, or migration changes.
- The handoff stays concise enough to be read before implementation begins.
