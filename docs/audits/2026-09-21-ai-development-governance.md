# AI-assisted development governance audit

Date: 2026-09-21

This is an audit/evidence record, not an execution queue. Current product status remains `PROJECT_STATUS.md`; stable engineering rules are in `ENGINEERING_INVARIANTS.md`; roadmap issue #8 remains roadmap authority.

## Baseline and evidence

The audit first observed `main` at `1f8d89f7fc0cf13e716ff97b94b1d81381d8d933`. While it was in progress, PR #41 and documentation follow-ups advanced `main`, so the governance work was discarded and replayed from the new baseline instead of merging a stale branch.

Current audit baseline: `1345b39c555df97dfea55074c7ae7d0ab71ad78f`.

A direct comparison from PR #41 merge `c2c4f39ffe5c943c76f2190c458d4ece384f6513` to `1345b39c...` changes only `PROJECT_STATUS.md` and audit documentation. The product/test/workflow tree is the PR #41 product tree.

Fresh exact-head baseline workflow: run `35529711449`.

It explicitly checked out `1345b39c...`, packaged the pristine source before executing tests, then passed:

- `Tools/run_linux_checks.sh`;
- all 81 Linux-portable `tests/test_*.py`;
- `python3 -m compileall -q Backend Tools tests`.

The four excluded platform-only entrypoints are:

- `test_core_save_batch_delete_round20.py`;
- `test_core_save_rename_completion_round24.py`;
- `test_hades2_run_log_watcher.py`;
- `test_trainer_log_sink_shared_append.py`.

PR #41's merged product tree has macOS Build 2 evidence in run `35529062368`, but that ancestor result is not described as an exact-`1345b39c...` macOS run. The final governance branch requires its own CI.

## System map

```text
App
  -> one TrainerBackendSession
  -> TrainerHostView
       -> TrainerTargetProcessMonitor
       -> TrainerConnectionPolicy
       -> optional Core Save manager
       -> selected TrainerGameModule
            -> typed game model/API
            -> game adapter/router
            -> game transport + persistence
            -> resident runtime where applicable
```

Authoritative ownership:

- Host/Core owns process observation, automatic/manual connection policy, the single backend worker/session, generic request ordering/timeouts, shared UI/Input, generic Process Time Warp mechanics and optional generic Save transactions.
- Hades II owns command meaning, typed state projection, LLDB/Lua transport, lifecycle-log interpretation, desired/Profile semantics, catalogs/resources/rewards and game-specific UI.
- Core Save owns snapshots, restore, rollback and staging. Hades owns save resolution/provider semantics and any Hades codec/schema/editor semantics.
- Build-only module metadata belongs to `Tools/**`; runtime module discovery belongs to Backend Core.

State authority:

- durable desired state: Hades preference/Profile layer;
- observable runtime state: resident Lua + Process Time Warp, decoded through Hades state patches;
- dormant state: desired but not currently active in the observed scene/runtime;
- Host lifecycle intent: Host policy/session only;
- Save transaction/recovery evidence: Core Save durable storage/claims, not UI optimism or a single process reply.

Desired, active and dormant are deliberately different facts. Sparse state patches must also preserve absent versus explicit-null semantics.

## Lifecycle and replay model

- Initial discovery of an already-running process is not a true-launch background-attach grant.
- A real target launch grants one bounded event-driven background recovery/connect opportunity.
- Target activation records an opportunity but does not itself justify debugger attachment.
- Target exit while the backend is busy preserves one deferred refresh until the backend becomes idle.
- Backend timeout/terminal transport uncertainty kills trust in that backend instance. The timed-out/in-flight request is never replayed automatically.
- Hades same-PID runtime reset is a Lua-generation transition, not a new process lifetime. It reuses the same debugger attachment, invalidates runtime-generation bookkeeping and later bootstraps/replays safe durable state.
- No periodic LLDB/Lua polling and no second debugger attachment are allowed for same-PID recovery.
- Native modal and direct one-shot actions never enter preference replay.
- Next-room reward is a durable one-shot only because it carries a stable token plus a resident consumption receipt.

Current Hades log evidence:

- main menu: `Loading package: MainMenu.pkg`;
- runtime reset: `App.Reset Start` / `Lua interface destroyed`;
- ready after reset: `Finished loadScreen onExit`.

`World::Stop()` is explicitly not a main-menu signal.

## Bug-family -> invariant -> enforcement

| Historical family | Invariant / authoritative owner | Current enforcement | Remaining governance action |
| --- | --- | --- | --- |
| lifecycle event misinterpreted | game lifecycle meaning must come from Hades evidence; watcher owns decoding | real watcher test + lifecycle contracts | preserve evidence requirement in stable invariant doc |
| PID treated as runtime generation | process lifetime and resident Lua generation differ | reset/watcher/adapter scenario tests | no PID-only recovery shortcuts |
| lifecycle event lost while busy | bounded event intent survives transient busy until consumed | `test_host_connection_policy_dev8.py` | keep behavior test primary |
| deferred action without observability | deferral is legal only when its completion signal can be observed | watcher availability + connect phase tests | no polling workaround |
| outcome-unknown replay | unknown execution terminates session trust | backend recovery harness + LLDB taint test | operation classification in stable matrix |
| durable intent mixed with one-shot | only replay-safe durable intent enters persistence replay | adapter replay + native-modal contracts | real-game acceptance remains final for native UI |
| consumed one-shot resurrected | durable one-shot needs identity and consumption receipt | next-room token regression | runtime revision + real-game gate |
| persistence failure blocks cleanup | durable reset and resident teardown are separate failure domains | exit/adapter contracts | no hidden success on persistence error |
| shared log writers overwrite | multi-writer append needs kernel append semantics | macOS `O_APPEND` behavior test | platform-only by nature |
| destructive staged restore replays | claim destructive intent before mutation; uncertain claim is indeterminate | Core Save service tests | never downgrade applying state into automatic retry |
| stale stopped decision / TOCTOU | process state is rechecked immediately before cold mutation | Save restore/service tests | unknown process state fails closed |
| rollback loses last recovery | recovery copy remains until rollback is complete and verified | Save restore/protocol tests | no cleanup for appearance |
| backend dies while rollback bytes survive | durable recovery evidence must be rediscoverable after producer death | PR #41 `recoveryPaths` behavior + Save Manager projection | expose evidence only; never auto-restore/delete |
| storage containment drift | Trainer-owned destructive paths remain inside configured root | snapshot/service symlink/path tests | Profile subdir symlink hardening remains Minor without new evidence |
| partial Profile merge collision | explicit imported assignments can displace/reflow omitted derived state deterministically | real Swift shortcut behavior test | no open gap |
| early terminal callback missing | async completion must be total on all terminal paths | rename behavior + portable contract | broaden only if another defect appears |
| shared ownership drifts | Core owns reusable interaction; game owns semantics | reference fixture/module matrix + boundary tests | avoid speculative Core abstraction |
| regression fossils protect spelling | prefer state/type/behavior contracts over old source shape | mixed existing suite | consolidate opportunistically, not wholesale |
| Linux curated list drifts | portable tests enter Linux CI by default | audit found only 34/85 listed, leaving 47 portable tests outside the lane | implemented exhaustive discovery |
| runtime source changes without revision bump | resident source change and identity bump are one atomic contract | prior exact literals only proved current spelling | implemented diff-based CI gate |
| verification claim drifts from Git | “passed/fixed” names exact tested SHA | audit discipline | repository required checks recommended |

## Technical-debt map

### Systemic

1. **Linux CI discovery drift.** At `1345b39c...`, the Linux positive list runs 34 of 85 entrypoints. Four are genuinely macOS-only, leaving 47 Linux-portable tests outside the lane. This includes backend session recovery, Core Save transaction suites, LLDB outcome-unknown taint and Process Time Warp behavior.
2. **Runtime revision discipline was prose plus duplicated literals.** Tests that say “revision is 42” do not express “a runtime diff requires an increased revision.”
3. **Future-agent entry cost is unnecessarily high.** Correct facts exist, but stable rules are distributed between status, module documentation and historical audits.
4. **Repository policy allows CI bypass.** `main` is unprotected and the repository has no rulesets.

### Local

- `Hades2View.swift` is large but primarily one Hades presentation/editor composition boundary.
- `Hades2Model.swift` is large because lifecycle, sparse projection, command intent and termination cleanup genuinely coordinate there; watcher/scheduler/shortcut persistence are already extracted.
- `Hades2Adapter` is high cognitive load because it is the persistence/runtime synchronization boundary; router, transport, preferences/Profile, catalog and diagnostics already have separate owners.
- Core Save files are complex but split along coherent transaction responsibilities: resolution, immutable snapshots, destructive restore/rollback, and orchestration/staging/recovery discovery.

### Historical

- historical divergent branches are predominantly squash-merged/absorbed/superseded evidence;
- no unique unmerged MacGamingTrainer product behavior was found;
- `ci/lidkeep-rc1-build` is unrelated repository contamination and must never merge;
- legacy round/release documents are evidence, not execution queues.

### Speculative — do not change now

- split `runtime/hades.lua` before a multi-file loader is proven in the real game;
- broad Hades View/Model “clean architecture” rewrite based on file size;
- move Hades desired/dormant/resource semantics into Core;
- merge runtime bootstrap + preference replay without a new measured regression;
- add fsync/symlink hardening beyond demonstrated requirements merely for theoretical completeness;
- migrate the suite to pytest/new infrastructure solely to modernize style.

## Test-debt audit

Dominant classification of all 85 pre-governance `tests/test_*.py` entrypoints follows. Mixed tests can enforce secondary concerns, but each file is placed once so the suite has an explicit semantic map.

### A. Executable business/state behavior — 29

`test_backend_core_round12.py`, `test_boundary_performance_ledger_v0180.py`, `test_catalog_naming.py`, `test_core_save_manifest.py`, `test_core_save_protocol.py`, `test_core_save_resolution.py`, `test_core_save_restore.py`, `test_core_save_running_transition.py`, `test_core_save_service.py`, `test_core_save_snapshots.py`, `test_corrupt_file_quarantine_v0180.py`, `test_diagnostics_read_only_v0190.py`, `test_hades2_adapter_round12.py`, `test_hades2_save_provider_round21.py`, `test_hades2_services_round16.py`, `test_localization_cache_recovery_v0180.py`, `test_next_room_reward_restart_semantics.py`, `test_persistence_integrity_v0180.py`, `test_preference_commit_efficiency_dev8.py`, `test_preferences_schema_v0180.py`, `test_process_time_warp_controller.py`, `test_process_time_warp_hades_integration.py`, `test_profile_envelope_contract_v0180.py`, `test_profile_shortcut_schema_v0180.py`, `test_protocol_fixtures_v0180.py`, `test_runtime_boundary_efficiency_dev8.py`, `test_schema_versioning_v0180.py`, `test_shortcut_chord_semantics.py`, `test_v01711_catalog_localization_ui.py`.

These execute production Python or compiled Swift behavior/state logic. Some also contain source guards, but their primary value survives implementation rearrangement.

### B. Lifecycle scenario/state-transition behavior — 8

`test_backend_reply_callback_round20.py`, `test_backend_session_recovery_dev8.py`, `test_connect_phase_profile.py`, `test_global_host_cleanup_dev8.py`, `test_hades2_mutation_scheduler_round17.py`, `test_host_connection_policy_dev8.py`, `test_passive_ready_transition.py`, `test_runtime_reliability_round17.py`.

The strongest family-wide guards are the pure/compiled Host policy and backend-session recovery harnesses. `test_passive_ready_transition.py` still mixes source wiring checks with scenario intent and is an upgrade candidate.

### C. Cross-module architecture contracts — 9

`test_core_save_hades_decoupling_round20.py`, `test_cross_game_isolation.py`, `test_global_decoupling_round15.py`, `test_module_contract_round13.py`, `test_reference_fixture_host_contract.py`, `test_shared_backend_session_round20.py`, `test_swift_file_boundaries_round14_1.py`, `test_toggle_unification_v0178.py`, `test_ui_component_boundary_v0175.py`.

The reference fixture/module matrix is the highest-value executable proof; token/file-location guards should remain secondary.

### D. Build/package/CI contracts — 7

`test_build_contract_round14.py`, `test_packaged_module_round14.py`, `test_process_time_warp_preparation_contract.py`, `test_save_descriptor_round20.py`, `test_swift_integrity_v0172.py`, `test_swift_symbol_integrity_v0173.py`, `test_test_suite_discovery.py`.

This governance branch strengthens `test_test_suite_discovery.py` so Linux is exhaustive-by-default rather than a curated positive list.

### E. Source-level semantic/static invariants — 7

`test_background_boundary_policy_v0180.py`, `test_hades2_session_hook_ownership.py`, `test_hades2_timeout_policy_v0177.py`, `test_hades2_transport_outcome_unknown_taint.py`, `test_process_time_warp_native_contract.py`, `test_reward_naming_audit.py`, `test_swift_declaration_uniqueness_v0176.py`.

These intentionally guard semantic structure that is difficult to exercise without the real game/toolchain. The transport taint test already uses AST-level inspection where appropriate. The new `test_runtime_revision_gate.py` also belongs here after governance changes, but is not counted in the 85-file baseline.

### F. Brittle string/regex/source-shape contracts — 13

`test_core_save_header_rename_round23.py`, `test_core_save_modal_style_round22.py`, `test_core_save_swift_model_round20.py`, `test_core_save_ui_round20.py`, `test_core_save_ui_style_round21.py`, `test_exit_semantics.py`, `test_god_mode_hostile_effects.py`, `test_hades2_visual_baseline_v0174.py`, `test_hotkey_feedback_contract.py`, `test_mapped_slider_contract.py`, `test_native_sell_traits_contract.py`, `test_native_special_choice_contract.py`, `test_post_v01_feature_contracts.py`.

Do not delete them mechanically: several protect real engine-API or UI-boundary requirements. When those areas are next changed, prefer compiled/type/behavior verification and retain only source checks that protect an otherwise unobservable contract.

### G. Historical regression fossils — 8

`test_round12_static.py`, `test_round17_1_swift_scope.py`, `test_round17_static.py`, `test_swift_round12.py`, `test_target_exit_refresh_contract.py`, `test_user_reported_fixes_dev7.py`, `test_v01710_regressions.py`, `test_v0179_regressions.py`.

These remain green guards, but their release/round naming and bundled historical assertions are poor templates for future tests. `test_target_exit_refresh_contract.py` is the clearest consolidation candidate because the stronger Host policy/session tests now express the transition behavior. Consolidation should happen only in a change that proves equal-or-stronger coverage.

### H. Platform-only tests — 4

`test_core_save_batch_delete_round20.py`, `test_core_save_rename_completion_round24.py`, `test_hades2_run_log_watcher.py`, `test_trainer_log_sink_shared_append.py`.

These compile/use AppKit or Darwin behavior and are intentionally excluded from Linux. They remain mandatory in Build 2 macOS.


### Keep as primary semantic guards

Lifecycle/session:

- `test_host_connection_policy_dev8.py`;
- `test_backend_session_recovery_dev8.py`;
- `test_connect_phase_profile.py`;
- `test_runtime_reliability_round17.py`;
- `test_hades2_mutation_scheduler_round17.py`.

Save behavior:

- `test_core_save_resolution.py`;
- `test_core_save_snapshots.py`;
- `test_core_save_restore.py`;
- `test_core_save_service.py`;
- `test_core_save_protocol.py`.

Hades replay/persistence:

- `test_hades2_adapter_round12.py`;
- `test_hades2_transport_outcome_unknown_taint.py`;
- `test_next_room_reward_restart_semantics.py`;
- schema/Profile/corruption suites.

Architecture/build:

- `test_cross_game_isolation.py`;
- `test_module_contract_round13.py`;
- `test_packaged_module_round14.py`;
- reference fixture + module build matrix.

### Upgrade semantic level when next touched

- `test_passive_ready_transition.py`: retain lifecycle intent, but move sequencing assertions into executable state/harness tests when an isolatable interface exists.
- `test_exit_semantics.py`: persistence-vs-runtime teardown ordering deserves a fake adapter/transport behavior harness rather than only source slices.
- `test_native_sell_traits_contract.py` / `test_native_special_choice_contract.py`: static engine-API guards are useful; real Hades acceptance remains final proof.
- `test_core_save_swift_model_round20.py`: retain portable source guard until a practical portable Swift/AppKit behavior harness exists.
- visual/source contracts: prefer compile/type/snapshot behavior if a stable mechanism later exists; do not add a framework only for modernization.

### Consolidate opportunistically

No-polling, target-exit wiring and Core/Hades decoupling are asserted in several round-specific files. Use the stronger lifecycle/reference-fixture tests as primary contracts and remove duplicates only when a stronger test demonstrably covers the same boundary in the same change.

### Delete now

None. Redundancy exists, but there is no deletion with unambiguous equal-or-stronger coverage that justifies a cleanup-only change.

### Legacy — do not copy as new-test templates

- `test_round12_static.py`;
- `test_round17_static.py`;
- `test_round17_1_swift_scope.py`;
- `test_user_reported_fixes_dev7.py`;
- `test_v01710_regressions.py`;
- `test_target_exit_refresh_contract.py`.

New tests should be named after the invariant/behavior, not a release round.

## Context-budget plan

Default startup for a normal future task:

1. `PROJECT_STATUS.md`;
2. `ENGINEERING_INVARIANTS.md`;
3. the production files and nearest behavior tests for the requested subsystem.

Add `GAME_MODULES.md` only when the task crosses module/Core/build boundaries.

Task-specific additions:

- Host/recovery: `TrainerHost.swift`, `TrainerConnectionPolicy.swift`, `TrainerBackendSession.swift`, `BackendClient.swift`, lifecycle harnesses.
- Hades runtime: relevant `Hades2Model.swift` lifecycle slice, `adapter.py`, `transport.py`, the specific `hades.lua` command/hook section and runtime tests.
- Save: `save_service.py`, `save_restore.py`, `save_snapshots.py`, `save_resolution.py` and behavior tests; Hades provider only when game-specific resolution is involved.
- UI: relevant Core primitive first, then Hades composition.
- persistence/Profile: `preferences.py`, `profile_service.py`, shortcut store as relevant.

Historical PRs, old branches and old audit plans are escalation material for “why does this invariant exist?”, not default context.

## Repository governance

Observed at `1345b39c...`:

- `main` branch protection: off;
- repository rulesets: none;
- permanent workflows: Linux contracts, module build matrix and Build 2 macOS.

Recommended user-controlled ruleset after this governance PR is proven:

- require a pull request before merge;
- require branch to be up to date;
- require `Linux contracts / backend-contracts`;
- require both module-build-matrix results;
- require `Build 2 macOS / build`;
- block force pushes and branch deletion;
- administrator emergency bypass only;
- do not require signed commits unless the project deliberately adopts signing.

This audit does not change repository settings or delete historical branches.

## High-cognitive-load files

- `runtime/hades.lua`: one resident lifetime currently owns state, hook ownership/release, reconciliation, catalogs/projection and dispatch. Do not split by size; require a proven loader and real-game validation first.
- `Hades2View.swift`: extract only independently owned presentation/subflows, not arbitrary line-count slices.
- `Hades2Model.swift`: complexity is mostly state-transition coupling; do not replace it with pass-through stores.
- `adapter.py`: synchronization boundary among durable preference state, transport observation and resident replay; mechanical method relocation would obscure ordering.
- Core Save: current file boundaries already match transaction responsibilities.

## Implemented governance changes

1. **Exhaustive Linux-portable discovery.** New `test_*.py` files run on Linux by default. Only the four explicit AppKit/Darwin entrypoints are skipped. `test_test_suite_discovery.py` enforces this.
2. **Diff-based resident runtime revision gate.** `Tools/check_runtime_revision.py` compares PR/push base and head. A `hades.lua` diff requires an increased and internally consistent resident revision. Existing runtime tests consume a semantic revision extractor instead of copying the current `42` literal.
3. **Low-context agent entry.** `AGENTS.md` is a thin reading/ownership index. `ENGINEERING_INVARIANTS.md` centralizes stable ownership, lifecycle, replay, Save and verification rules. `PROJECT_STATUS.md` links them without duplicating status authority.

No product behavior, Hades runtime source or save format is changed by this governance pass.
