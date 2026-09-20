# Pre-feature deep audit design

Updated: 2026-09-20

## Goal

Freeze new feature development and establish a clean, conflict-free, regression-tested baseline before Hades II Save Editor work begins.

## Scope

Audit current `main` and every still-present remote branch as historical evidence. Cover Core/Host, Backend/Core, Hades II module/backend/runtime, shared UI/input, Process Time Warp, Core Save Management, build/package/CI, tests and handoff documentation.

No new product capability is in scope. Refactors are allowed only when a demonstrated defect, ownership violation, duplicated live path, stale conflict, or testability problem requires them.

## Success criteria

1. Every remote branch is classified as fully merged/superseded, documentation-only, unrelated, or carrying unique product code needing disposition.
2. Current main passes supported Linux contracts, cross-game module matrix, macOS exhaustive contract/build/package gates before and after fixes.
3. Core/Host remains game-agnostic; Hades II owns game semantics and does not duplicate shared Host/Core capabilities.
4. Lifecycle/backend-session repeated-entry transitions have one source of truth.
5. Outcome-unknown non-idempotent/native-modal operations are never implicitly replayed.
6. Save snapshot/restore/rollback/staged paths preserve containment, atomicity and the last recoverable copy.
7. Shared UI/input state remains shared; game-local code only maps Hades semantics into neutral inputs.
8. Every behavioral fix has root-cause evidence and RED -> GREEN coverage.
9. Runtime-source changes bump the resident revision.
10. Final audit branch is synchronized with then-current main with no unresolved product-code divergence.

## Method

Each segment begins read-only: map data/state flow, compare working references, run relevant tests and record findings. A finding moves to repair only after a reproducible test, static invariant failure, CI/build failure, or concrete branch divergence proves it.

Repairs target the true ownership boundary. No speculative abstraction, broad cleanup, dependency addition or new feature is permitted.

## Segments

A. Repository and evidence integrity: branch divergence, CI/test discovery, stale/conflicting docs.

B. Framework boundary and source ownership: App/Core/Backend-core versus module contract; duplicated shared capability.

C. Lifecycle, transport and concurrency: launch attach, same-PID reset, detach/reattach, backend timeout/restart, deferred probe, mutation scheduling and termination.

D. Persistence and Save safety: preferences/Profile writes plus Core snapshot/restore/staged/rollback containment, corruption and recovery.

E. Hades II command/runtime semantics: query/idempotent/durable/native-modal classification, retry/replay, runtime generation and resident revision.

F. Shared UI, hotkeys and observable state: shared primitives, shortcut ownership, speed control and stale model/view state.

G. Final verification and cleanup: full supported CI, macOS-only validation where required, final review, canonical status and merge gate.

## Severity

- Critical: data loss/security/corruption, unsafe mutation replay, build/package breakage, cross-game architectural breach, or lifecycle behavior that can corrupt live state.
- Important: reproducible functional defect, stale conflicting live path, race/state ownership bug, or missing protection around an existing invariant.
- Minor: maintainability/documentation hygiene without demonstrated behavioral impact.

Critical and Important findings block new feature development.
