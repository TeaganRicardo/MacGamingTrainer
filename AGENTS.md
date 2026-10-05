# Development entrypoint

This file is the entrypoint for coding agents. It is intentionally short and does not duplicate project history.

## Source-of-truth order

Use this order when facts conflict:

1. current GitHub `main`, production code and executable tests;
2. `PROJECT_STATUS.md` for current operational state and active gate;
3. `ENGINEERING_INVARIANTS.md` for stable ownership, lifecycle, replay and Save-safety rules;
4. `GAME_MODULES.md` when a task crosses the Core/game-module boundary;
5. planning issue #124 for planned work and sequencing only.

`docs/audits/**`, closed PRs, Git history, old branches and prior conversations are historical evidence, not execution authority. Do not read them by default. Open them only when investigating why a current invariant exists or when current code contradicts current authority.

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
- For a demonstrated correctness defect: reproduce RED first, then identify the root cause and owning seam before choosing implementation scope. Make the smallest coherent fix of the demonstrated root cause, not the smallest diff. If the defect exposes a shallow module, duplicated policy, a wrong seam, or a responsibility split, expand the fix across that owning seam while keeping unrelated cleanup out of scope.
- Treat defensive guards, fallbacks, retries, fail-closed branches, compatibility aliases and implementation-shape tests as complete fixes only when the failure mode is intrinsically unavoidable at the owning seam. If they merely contain a structural defect, mark the containment incomplete and retain a root-cause successor.
- Repeated fixes that make several callers or tests understand the same implementation detail are architecture evidence. Prefer deepening the owning module so callers and tests cross one smaller interface instead of adding another caller-side special case.
- Treat user shorthand as intent, not canonical product terminology. For game-facing names, prefer the supported target build's official localization or catalog/reference terminology; when no official name exists, choose a neutral formal product term and use it consistently across UI, errors, tests and current docs. When both Chinese and English are exposed, an official game term must resolve both `zh-CN` and `en` from the same localization ID; Trainer-only product labels must declare an explicit bilingual pair and must not masquerade as native game terminology.
- Do not restore code merely because a historical branch is ahead/divergent; squash-merged and superseded branches are common in this repository.

## Verification routing

Verification **scope** and evidence **identity** are separate. Every check claimed as evidence must have run against the exact SHA named by the claim; exact-head evidence does not mean every task runs the full release matrix.

- **Task verification:** pull requests run the minimum gates owned by every changed seam on the actual final PR head. A root-cause refactor that legitimately widens the changed seam widens verification with it.
- **Integration verification:** any PR-head rewrite/rebase requires the task gates again so evidence binds to the new SHA. If overlapping work or a dependency changes inputs/semantics at the changed seam, also rerun those affected integration gates.
- **Convergence/release verification:** explicitly dispatch the existing workflows on one selected SHA. This is where mutation testing, retained release/reference artifacts, provenance and checksums belong.

The three standing workflow names are stable required checks. They run on `pull_request` plus explicit `workflow_dispatch`; merged `main` does not automatically repeat the same task verification.

Routing by changed seam:

- Linux-portable backend/contract work: `bash Tools/run_linux_checks.sh`. This remains the broad portable behavior suite; do not create a per-file test routing database.
- The resident-runtime revision gate is diff-based and therefore PR-only. Explicit convergence dispatch has no semantic base ref; it reruns behavior/build evidence rather than inventing a revision comparison.
- Swift/AppKit/build/package changes: also require `Build 2 macOS`, which runs macOS contracts plus an actual Hades build/package/signing verification in PR task mode.
- Module/Core boundary changes: require the module build matrix/reference fixture.
- Mutation testing is a convergence/release audit of test sensitivity, not an always-on correctness gate for ordinary PRs.
- RC ZIP/provenance/checksum creation and retained QA artifacts are convergence/release outputs, not ordinary PR requirements.
- `Backend/games/hades2/runtime/hades.lua` changes: resident revision must increase; automated tests are not final validation. Record real Hades II acceptance for changed runtime semantics.
- Tests must use temporary fixtures and must never read/write the real user/game save tree.
- New test files use descriptive subject names (`test_<subject>.py`), not historical epoch tokens such as `roundNN` or `v0xxx`. Existing epoch-named tests are grandfathered and should not be bulk-renamed.
- Manual QA handoff, when required, is one exact HEAD plus one prebuilt artifact and checksum produced by explicit convergence/QA dispatch.

## Review and scope discipline

- A focused task has one causal purpose, not an artificially small file count. A coherent root-cause fix may cross several files or existing subsystem seams when those edits are required to restore locality at the owning interface.
- Review evaluates whether the demonstrated root cause is removed, ownership is improved, and unrelated work stayed out of the change. Do not request scope reduction solely because the correct fix is larger than the originating defect.
- When a deeper module/interface replaces duplicated caller policy, migrate callers and tests to that interface and remove superseded implementation-shape checks instead of retaining both designs “for safety.”

## Governance budget

- Do not add another always-on workflow, required check, global mutation class, parity scan or source-text gate merely because a new invariant can be written down.
- New recurring gates need a concrete defect that escaped the existing owning behavior tests, or an independently proven cross-cutting seam that cannot be protected locally.
- Prefer one behavior test at the owning interface over several implementation-shape/parity tests across callers.
- A new cross-cutting gate should normally replace or subsume an older mechanism instead of accumulating beside it.
- Current readiness belongs in planning issue #124. Task issues own stable scope, dependencies and acceptance criteria; do not copy transient frontier/status prose into every issue.
- Do not open a status-reconciliation PR after every ordinary merge. Update `PROJECT_STATUS.md` only when the operational baseline, active gate, protocol/version state, compatibility target or manual-acceptance baseline materially changes; include that update in the owning PR when practical.

## Product versioning

- `Info.plist` is the only source of the current app product version.
- `CFBundleShortVersionString` is the three-part product SemVer; `CFBundleVersion` is the monotonic positive-integer bundle build number.
- Host/module protocol and schema/runtime revisions are independent compatibility versions, not product SemVer.
- See `VERSIONING.md` for release increment rules.

See `ENGINEERING_INVARIANTS.md` for the durable engineering rules behind these instructions.
