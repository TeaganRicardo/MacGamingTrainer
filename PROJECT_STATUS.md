# MacGamingTrainer Project Status

Updated: 2026-09-20

This is the canonical development handoff. Historical implementation plans, closed PRs and old branches are evidence only; current code, this file, open issues and roadmap issue #8 are execution authority.

## Current baseline

- Default branch: `main`.
- Verified code baseline: `4eab391e00421b9ec4dfca68030ae48ce04fc8b0` (`fix: preserve shared trainer log appends`). Documentation-only commits after this SHA do not change the code evidence.
- Hades II resident runtime: revision 41.
- Hades II module protocol: 5.
- Target game baseline used by current runtime contracts: Hades II 1.139672 / Steam build 24556151.
- Process Time Warp + mapped speed slider are shared Host/Core infrastructure.
- Core Save Management is integrated and optional per game module.
- Phase 1 cross-game isolation is integrated through the permanent non-production `reference_fixture`.
- Generic hotkey feedback sounds are integrated: enabled / deferred / disabled.
- Shortcut partial-Profile/local-override collision is fixed.
- Batch D lifecycle code changes are integrated; only target-Mac performance acceptance remains open.

## Exact merged-main verification

For `4eab391e00421b9ec4dfca68030ae48ce04fc8b0`:

- Linux contracts run `35511272539`: PASS.
- Module build matrix run `35511272494`: Hades II PASS; reference fixture PASS; one-module package isolation PASS.
- Build 2 macOS run `35511272525`: full macOS contract suite PASS; Hades II build PASS; package verification PASS; artifact creation/upload PASS.

Current RC:
- GitHub artifact id: `10606170480`.
- Artifact: `MacGamingTrainer-0.1-build2-rc`.
- Deliverable: `MacGamingTrainer-0.1-build2-rc.zip`.
- Deliverable SHA256: `35bc13e1021c9b16f877b112f2e59dfe8f7e85b530b7f191a69dc432b9063aae`.

Hosted Actions step-0 admission is healthy; issue #16 remains closed.

## Completed recent work

- PR #21: generic Process Time Warp + mapped speed slider.
- PR #22: repository handoff/history cleanup.
- PR #23: current-architecture cross-game isolation proof; issue #9 closed; old PR #10 superseded.
- PR #24: partial shortcut Profile conflict fix; issue #17 closed.
- PR #25: canonical status refresh.
- PR #26: same-PID runtime-reset signal invalidates backend generation bookkeeping before ready refresh, removing the normal doomed first resident status.
- PR #27: true-launch automatic connection can attach without an immediate pre-ready Lua/world probe; foreground/manual connect still probes immediately.
- PR #28: deferred launch probing is used only when the Hades lifecycle directory is observable; first-ever/no-directory launches fall back to the prior bounded immediate probe.
- PR #30: shared `trainer.log` GUI writes now use kernel-level `O_APPEND`, preventing the Swift GUI writer from overwriting Python backend profiling records after concurrent appends.

No PR #26–#30 change touched `hades.lua`; resident revision remains 41.

## Active work, in order

1. **Manual lifecycle performance acceptance — issues #1 and #11**
   - use the exact post-PR-30 RC above;
   - rerun true-launch background auto-connect so `LLDBAttachProfile` / `ConnectProfile` are captured in the now append-safe shared log;
   - perform one more genuine main-menu -> same-save re-entry without exiting Hades;
   - confirm desired state automatically becomes active again and no second debugger attachment / `attach_denied` occurs;
   - record subjective stall severity for the remaining bootstrap + replay pair.
   - Do not merge bootstrap + replay further unless the new sample still shows a severe visible stall.

2. **Save-management hardening / Hades II save-editor expansion**
   - begin after #11 acceptance;
   - build on the proven optional Core capability;
   - keep save schema, parsing, validation and editing semantics inside the Hades II module.

3. **Pre-Hades-I architecture gate**
   - recheck Host/Core boundaries after lifecycle/save-editor work.

4. **Hades I vertical slice**
   - begin only after the architecture gate.

## Lifecycle evidence and expected behavior

The code records separate phases:

- `LLDBAttachProfile`: createTarget / attachProcess / identity / symbols / resume.
- `ConnectProfile`: scan / attachTotal / firstStatusTotal / firstLuaBoundary / JSON decode / localization.
- `LuaBoundary`: command / duration / outcome / transport crossing / replay flag.

Old target-Mac evidence showed the actual bottleneck was primarily Lua/world readiness rather than debugger attach. A representative same-PID reset paid about 1.344 s for the doomed resident status, 1.799 s for re-bootstrap status and 0.699 s for replay. The old log also contained many ~3.22–3.25 s pre-ready waiting status boundaries.

The 2026-09-20 QA sample after PRs #26–#28 contains one genuine same-PID re-entry:
- run-log runtime reset bookkeeping crossed zero Lua boundaries;
- bootstrap/status took 0.868 s;
- one batched durable replay took 0.886 s;
- enabled persistent features became active again after replay;
- the old failed-resident-status boundary was absent.

The later apparent disconnect in that sample was not a failed same-PID recovery: Hades II.log shows `MainMenuScreen::ExitGame()` followed by `App Shutdown` at 20:31:40–20:31:41. The Host then correctly applied a staged save restore after target termination.

That QA sample could not reliably measure true-launch attach phases because the GUI and backend shared-log writers corrupted the first-launch profiling window. PR #30 fixes the logging substrate with `O_APPEND`; the post-PR-30 RC must therefore be used for the remaining true-launch measurement.

Current intended flow:

- True launch, lifecycle observable:
  `scan -> LLDB attach -> waiting/loading (zero Lua boundary) -> runtimeReady -> bootstrap/status -> optional batched replay`.
- True launch, lifecycle directory unavailable:
  bounded fallback to the previous immediate connect/status path.
- Same-PID runtime reset, normal signaled path:
  `runtimeReset bookkeeping (zero Lua boundary) -> runtimeReady -> bootstrap/status -> optional batched replay`.
- Missing lifecycle signal:
  existing status-side missing-generation fallback remains.

No periodic LLDB/Lua polling is present.

## GitHub state

Open:
- issue #1 — lifecycle/manual-acceptance umbrella.
- issue #11 — exact RC manual performance acceptance.
- issue #8 — current roadmap.

Closed:
- issue #9 — cross-game isolation proof complete.
- issue #16 — hosted Actions admission recovered.
- issue #17 — partial shortcut Profile collision fixed.
- PR #10 — superseded by merged PR #23.
- PR #19 — superseded by merged PR #21.
- PR #21 through #28 — merged as applicable.

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
- `fix/defer-launch-runtime-probe`
- `fix/deferred-log-availability-guard`
- `fix/append-only-shared-trainer-log`
- `fix/profile-shortcut-partial-conflict`
- `fix/profile-shortcut-partial-conflict-v2`
- `fix/proactive-runtime-reset-bootstrap`
- `fix/special-choice-native-r39`
- `fix/special-choice-refresh-r38`
- `maintenance/current-status-20260920`
- `maintenance/repo-hygiene-20260920`
- `maintenance/status-after-lifecycle-fixes`
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
