# MacGamingTrainer Project Status

Updated: 2026-09-20

This is the canonical development handoff. Historical implementation plans, closed PRs and old branches are evidence only; current code, this file, open issues and the roadmap issue are execution authority.

## Current baseline

- Default branch: `main`.
- Verified code baseline: `7471edf9dfaa20a56936de0497883c296b7afac3` (`fix: resolve partial shortcut Profile override collisions`). Subsequent documentation-only commits do not change that code evidence.
- Hades II resident runtime: revision 41.
- Hades II module protocol: 5.
- Target game baseline used by current runtime contracts: Hades II 1.139672 / Steam build 24556151.
- Process Time Warp + mapped speed slider are shared Host/Core infrastructure.
- Core Save Management is integrated and optional per game module.
- Phase 1 cross-game isolation proof is integrated through the permanent non-production `reference_fixture`.
- Generic hotkey feedback sounds are integrated: enabled / deferred / disabled.
- Shortcut partial-Profile/local-override collision is fixed.

## Exact merged-main verification

For `7471edf9dfaa20a56936de0497883c296b7afac3`:

- Linux contracts run `35507015701`: PASS.
- Module build matrix run `35507015708`: Hades II PASS; reference fixture PASS; one-module package isolation PASS.
- Build 2 macOS run `35507015713`: full macOS contract suite PASS; Hades II build PASS; package verification PASS; artifact creation/upload PASS.
- Hosted Actions step-0 admission has recovered; issue #16 is closed.

## Completed recent work

- PR #21: generic Process Time Warp + mapped speed slider.
- PR #22: repository handoff/history cleanup.
- PR #23: current-architecture cross-game isolation proof; issue #9 closed; old PR #10 superseded.
- PR #24: partial shortcut Profile conflict fix with explicit RED -> GREEN evidence; issue #17 closed.
- Batch C Host feedback sounds were already integrated in commit `6e4fac50301a4906600ce072a7a50e81fdc2c065` and remain covered by `test_hotkey_feedback_contract.py`.

## Active work, in order

1. **Attach / world-readiness stutter — issues #1 and #11**
   - distinguish LLDB attach cost from first Lua boundary, runtime re-bootstrap and durable-preference replay;
   - preserve true-launch-only bounded background attach;
   - preserve same-PID single-debugger-attachment recovery;
   - remove redundant/avoidable boundaries rather than adding polling;
   - final acceptance requires repeated main-menu/save re-entry without severe serialized stalls and with persistent features correctly reapplied.

2. **Save-management hardening / Hades II save-editor expansion**
   - build on the proven optional Core capability;
   - keep save schema, parsing, validation and editing semantics inside the Hades II module.

3. **Pre-Hades-I architecture gate**
   - recheck Host/Core boundaries after lifecycle/save-editor work.

4. **Hades I vertical slice**
   - begin only after the architecture gate.

## Current lifecycle evidence

The code already records separate attach/connect phases:

- `LLDBAttachProfile`: createTarget / attachProcess / identity / symbols / resume.
- `ConnectProfile`: scan / attachTotal / firstStatusTotal / firstLuaBoundary / JSON decode / localization.
- `LuaBoundary`: command / duration / outcome / transport crossing / replay flag.

Current same-PID recovery is event-driven through the Hades II run log and does not use periodic LLDB/Lua polling. Runtime-generation loss is re-bootstrapped inside the existing debugger attachment.

The next lifecycle change must be driven by measured phase evidence from #11 rather than by adding retry loops.

## GitHub state

Open:
- issue #1 — lifecycle/manual-acceptance umbrella; Batch D remains.
- issue #11 — attach/world-readiness performance.
- issue #8 — current roadmap.

Closed:
- issue #9 — cross-game isolation proof complete.
- issue #16 — hosted Actions admission recovered.
- issue #17 — partial shortcut Profile collision fixed.
- PR #10 — superseded by merged PR #23.
- PR #19 — superseded by merged PR #21.
- PR #21, #22, #23, #24 — merged.

## Branch hygiene

No historical feature branch is an execution base. New work must branch from current `main`.

Remote branches eligible for deletion once a supported delete-ref interface is available include:

- `architecture/reference-module-proof`
- `architecture/reference-module-proof-v2`
- `audit/preacceptance-hardening`
- `ci/lidkeep-rc1-build`
- `feature/game-speed-r41-integration`
- `feature/generic-speed-control-ui`
- `feature/mapped-speed-slider`
- `feature/post-v0.1-improvements`
- `feature/process-time-warp-host`
- `fix/batch-a-native-modals`
- `fix/batch-b-runtime-semantics-r40`
- `fix/profile-shortcut-partial-conflict`
- `fix/profile-shortcut-partial-conflict-v2`
- `fix/special-choice-native-r39`
- `fix/special-choice-refresh-r38`
- `maintenance/repo-hygiene-20260920`
- `refactor/save-management`
- `spike/generic-process-time-warp`
- `spike/generic-process-timewarp`

The current GitHub connector exposes ref updates but no ref deletion mutation. Do not work around this with container network access or RDC.

## Permanent constraints

- GitHub connector is the authoritative remote-repository interface.
- The container is for materialized local editing, diffing and non-macOS tests; do not depend on direct container access to github.com.
- RDC is only for macOS-specific build/runtime validation and never for repository/file transport.
- Tests must never mutate real user/game data; destructive filesystem tests require explicit temporary roots.
- Target-Mac save-sensitive suites keep a before/after hash sentinel on the Hades II save tree.
- No periodic LLDB/Lua polling.
- No second debugger attachment for same-PID runtime recovery.
- No replay of outcome-unknown non-idempotent mutations or native modal commands.
- No Hades-specific semantics in Core/Host.
- Native modal commands are one-shot and never preference-replayed.
- Save restore must never make a declared save root disappear.
- A failed rollback must preserve the last recoverable copy.
- Runtime source changes require a resident revision bump.
- Each tester handoff is one exact HEAD + one prebuilt signed App/ZIP + SHA256.
- Fix demonstrated/root-caused failures with RED -> GREEN coverage.
