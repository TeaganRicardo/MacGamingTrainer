# Pre-feature Deep Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute this plan task-by-task.

**Goal:** Establish a conflict-free, regression-tested baseline before any new feature work.

**Architecture:** Preserve the existing Core/Host versus game-module boundary and lifecycle invariants. Audit read-only first, then fix only demonstrated defects at their true owner with RED -> GREEN evidence.

**Tech Stack:** Swift/SwiftUI, Python, Lua, C/fishhook, shell, GitHub Actions, macOS build/codesign tooling.

**Spec:** `docs/superpowers/specs/2026-09-20-pre-feature-deep-audit-design.md`

## Global constraints

- New product features remain frozen.
- GitHub connector is authoritative for remote repository operations.
- Container is for local editing/diffing/non-macOS tests; RDC is macOS-only validation and never repository transport.
- Tests never mutate real user/game data.
- No periodic LLDB/Lua polling; no second debugger attachment for same-PID recovery.
- No replay of outcome-unknown non-idempotent/native-modal operations.
- No Hades-specific business semantics in Core/Host.
- Runtime source changes require a resident revision bump.
- No code fix before root-cause evidence.

## Review focus

1. Historical branch carries unique product code main never received.
2. Same-PID reset/re-entry leaves stale Host/backend/runtime generation state.
3. Timeout/restart replays a mutation whose first outcome is unknown.
4. Save containment/rollback/staged restore has a crash, symlink, race or failure path that can lose the last recoverable state.
5. Shared UI/input/session capability has a second game-local implementation that can drift.

### Task 1 — Repository and test baseline

- Compare every remote branch against current main and classify unique product code versus superseded history.
- Verify workflow/test discovery and exact CI coverage.
- Materialize exact audit-head source through GitHub/CI artifact into the container.
- Run the supported non-macOS baseline locally.
- Record concurrent-main changes and update the audit branch before proceeding.

### Task 2 — Architecture and duplicated ownership

- Trace App/Core/Backend-core responsibilities and search for Hades-specific branches/strings.
- Trace Hades-local implementations for duplicated shared UI/session/process capabilities.
- For every proven violation, add the smallest failing invariant/behavior test before repair.
- Run focused plus cross-game isolation tests after each coherent fix.

### Task 3 — Lifecycle, transport and concurrency

- Map authoritative state for attach -> ready -> reset -> reattach -> exit and backend restart.
- Exercise repeated-entry, deferred-probe, timeout and mutation-scheduler tests.
- Trace stale/duplicate state to origin, reproduce, then fix one root cause at a time.
- Re-run lifecycle and cross-game regressions after each fix.

### Task 4 — Persistence and Core Save safety

- Trace create/list/rename/delete/stage/commit/cancel/rollback filesystem paths end to end.
- Exercise corruption, missing-save, containment/symlink, rollback and process-state failure tests.
- Investigate crash recovery for staged-restore claims before changing behavior.
- Add RED tests for demonstrated destructive/race gaps, then repair only the owning transaction/storage layer.

### Task 5 — Hades II command/runtime semantics

- Classify each externally reachable command as query, idempotent mutation, durable desired state or one-shot native modal.
- Compare classification to retry/replay/timeout behavior.
- Reproduce mismatches before fixing; bump resident revision only if runtime source changes.
- Run Hades contract and lifecycle regressions.

### Task 6 — Shared UI, hotkeys and observable state

- Search for duplicate shared controls/input registration/state formatting.
- Trace hotkey assignment/update/removal, model observable-state ownership and Process Time Warp UI state.
- Add regressions for concrete drift/stale-state defects and fix at shared owner.
- Run focused UI/input and cross-game contracts.

### Task 7 — Final verification and merge gate

- Re-sync with then-current main and resolve only real divergence.
- Run complete supported local/CI suites.
- Use RDC only for behavior CI cannot validate.
- Perform final whole-branch review.
- Close all Critical/Important findings or record explicit user acceptance.
- Update PROJECT_STATUS and prepare merge; do not merge automatically.
