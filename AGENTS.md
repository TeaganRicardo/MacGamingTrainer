# Development entrypoint

This file is the entrypoint for coding agents. It is intentionally short and does not duplicate project history.

## Source-of-truth order

Use this order when facts conflict:

1. current GitHub `main`, production code and executable tests;
2. `PROJECT_STATUS.md` for current operational state and active gate;
3. `ENGINEERING_INVARIANTS.md` for stable ownership, lifecycle, replay and Save-safety rules;
4. `GAME_MODULES.md` when a task crosses the Core/game-module boundary;
5. planning issue #79 for planned work and sequencing only.

`docs/audits/**`, closed PRs, Git history, old branches and prior ChatGPT conversations are historical evidence, not execution authority. Do not read them by default. Open them only when investigating why a current invariant exists or when current code contradicts current authority.

## Minimal reading path

For an ordinary task, read only:

1. this file;
2. `PROJECT_STATUS.md`;
3. `ENGINEERING_INVARIANTS.md`;
4. the production files and nearest tests for the requested subsystem.

Read `GAME_MODULES.md` only for module/Core/build-boundary work. Read `VERSIONING.md` for release/version changes.

## Pick the owner before editing

- Host/process/backend lifecycle: `Sources/Core/Host/**`, `Sources/Core/Runtime/**`.
- Shared visual/interaction language and generic input: `Sources/Core/UI/**`, `Sources/Core/Input/**`.
- Generic optional Save infrastructure: `Backend/core/save_*`, `Sources/Core/Save/**`.
- Hades II commands, state meaning, transport, persistence, save codec/provider semantics and game UI: `Backend/games/hades2/**`, `Sources/Hades2/**`.
- Build/module metadata interpretation: `Tools/**` and module manifests.

A shared-looking Hades behavior does not move to Core merely because another game might someday need it. Prove a game-agnostic contract first.

## Before changing behavior

- Confirm current remote `main` HEAD and work on a branch.
- Identify authoritative state, durable desired state, observable runtime state and one-shot intent involved in the change.
- Decide whether an operation is replay-safe before adding retry/recovery behavior.
- For a demonstrated correctness defect: reproduce RED first, then make the smallest coherent fix at the owning boundary.
- Treat user shorthand as intent, not canonical product terminology. For Hades-facing names, prefer official target-build zh-CN strings or catalog/reference terminology; when no official name exists, choose a neutral formal product term and use it consistently across UI, errors, tests and current docs.
- Do not restore code merely because a historical branch is ahead/divergent; squash-merged and superseded branches are common in this repository.

## Verification routing

- Linux-portable backend/contract work: `bash Tools/run_linux_checks.sh`.
- Swift/AppKit/build/package changes: also require `Build 2 macOS`.
- Module/Core boundary changes: require the module build matrix/reference fixture.
- `Backend/games/hades2/runtime/hades.lua` changes: resident revision must increase; automated tests are not final validation. Record real Hades II acceptance for changed runtime semantics.
- Tests must use temporary fixtures and must never read/write the real user/game save tree.
- Manual QA handoff, when required, is one exact HEAD plus one prebuilt artifact and checksum.

## Product versioning

- `Info.plist` is the only source of the current app product version.
- `CFBundleShortVersionString` is the three-part product SemVer; `CFBundleVersion` is the monotonic positive-integer bundle build number.
- Host/module protocol and schema/runtime revisions are independent compatibility versions, not product SemVer.
- See `VERSIONING.md` for release increment rules.

## ChatGPT Project rule

Keep external ChatGPT Project Instructions thin. They should identify this repository, require GitHub as remote truth, enforce the reading path above, preserve the repository transport policy, and require branch/PR/exact-head verification. Do not copy architecture matrices, bug history or audit narratives into Project Instructions, and do not pin historical audit/handoff files as Project context.

See `ENGINEERING_INVARIANTS.md` for the durable engineering rules behind these instructions.
