# Development entrypoint

This file is a thin index for future coding agents. It is not a project-status or roadmap authority.

## Read first

For an ordinary task, read only these before opening historical material:

1. `PROJECT_STATUS.md` — current baseline, active product gate, exact recent verification.
2. `ENGINEERING_INVARIANTS.md` — stable ownership, lifecycle, replay, save-safety and verification rules.
3. `GAME_MODULES.md` — module/Core contract when the task crosses game-module boundaries.
4. The production files and tests for the subsystem being changed.

Roadmap issue #8 is the roadmap authority. Git/current source/tests are the implementation truth.

Do **not** default-read old PR descriptions, old branches, `docs/legacy-version-history/**`, or `DEFERRED_REFACTOR_PLAN.md`. Use them only when investigating why an invariant exists or when current code contradicts current authority.

## Pick the owner before editing

- Host/process/backend lifecycle: `Sources/Core/Host/**`, `Sources/Core/Runtime/**`.
- Shared visual/interaction language and generic input: `Sources/Core/UI/**`, `Sources/Core/Input/**`.
- Generic optional save infrastructure: `Backend/core/save_*`, `Sources/Core/Save/**`.
- Hades II commands, state meaning, transport, persistence, save codec/provider semantics and game UI: `Backend/games/hades2/**`, `Sources/Hades2/**`.
- Build/module metadata interpretation: `Tools/**` and module manifests.

A shared-looking Hades behavior does not move to Core merely because another game might someday need it. Prove a game-agnostic contract first.

## Before changing behavior

- Confirm current `main` HEAD and work on a branch.
- Identify durable desired state, observable runtime state and one-shot intent involved in the change.
- Decide whether the operation is replay-safe before adding any retry/recovery path.
- For a demonstrated correctness defect: RED reproducer first, then the smallest coherent fix at the owning boundary.

## Verification routing

- Linux-portable backend/contract work: `bash Tools/run_linux_checks.sh`.
- Swift/AppKit/build/package changes: also require macOS CI (`Build 2 macOS`).
- Module/Core boundary changes: require the module build matrix/reference fixture.
- `Backend/games/hades2/runtime/hades.lua` changes: resident revision must increase; automated tests are not final validation. Record real Hades II acceptance for the changed runtime semantics.
- Tests must use temporary fixtures and must never read/write the real user/game save tree.
- Manual QA handoff, when required, is one exact HEAD plus one prebuilt artifact and checksum.

See `ENGINEERING_INVARIANTS.md` for the failure/replay matrices behind these rules.
