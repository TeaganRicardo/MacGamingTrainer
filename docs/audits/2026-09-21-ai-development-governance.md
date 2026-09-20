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

| Debt | Concrete evidence / root cause | Blast radius | Current protection | Missing protection | Action / timing |
| --- | --- | --- | --- | --- | --- |
| Linux CI discovery drift | At `1345b39c...`, `Tools/run_linux_checks.sh` positively listed 34/85 entrypoints. Four are genuinely macOS-only, leaving 47 Linux-portable tests outside the lane. The root cause is duplicated test-registration ownership: file discovery in macOS vs a manual Linux list. | Any new/changed portable regression could miss the fastest required lane, including lifecycle, Save and outcome-unknown tests. | Build 2 macOS discovers all `test_*.py`; `test_test_suite_discovery.py` protected only that macOS property. | Linux exhaustive-by-default discovery. | **Fix now — implemented.** One explicit four-file platform denylist replaces the positive list; the discovery test enforces it. |
| Runtime revision discipline encoded as current spelling | Five tests asserted literal resident revision `42`. They prove the current source text, not “runtime source diff implies revision increase.” | A future `hades.lua` edit could keep 42 and still satisfy unrelated runtime assertions, producing stale resident code in a live process. | Human rule in status/audits; duplicated literal guards. | Diff-aware relation between base/head source and revision. | **Fix now — implemented.** Linux CI compares base/head and requires a monotonic, internally consistent resident revision whenever `hades.lua` differs. |
| Future-agent context/source-of-truth fan-out | Correct ownership/replay rules were distributed among `PROJECT_STATUS.md`, `GAME_MODULES.md`, audits and historical PRs. Root cause is that expensive incident knowledge accumulated as history instead of a small stable engineering contract. | Lower-context agents can edit the wrong layer, replay one-shots, or resurrect superseded designs. | Canonical status + roadmap exist; several behavior tests embody individual rules. | Minimal read path and stable cross-feature invariant index. | **Fix now — implemented.** Thin `AGENTS.md` entrypoint + `ENGINEERING_INVARIANTS.md`; status/roadmap authority remains unchanged. |
| Required CI is advisory only | `main` reports `protected=false`; repository rulesets list is empty. | A direct push or merged PR can bypass Linux/module/macOS evidence and exact-head discipline. | Workflows trigger on `main` and PRs, but GitHub does not require their success. | Repository ruleset/branch protection. | **Do after PR #44 proves check names.** User-controlled setting; this audit does not mutate repository settings. |
| Regression-fossil accumulation | Eight dominant G-class files and several F-class files retain round/version naming and implementation-shape assertions. Root cause is one-off regression additions without later semantic consolidation. | Future agents copy weak test patterns and must load obsolete round context. | Stronger lifecycle/module/Save harnesses now cover several families. | Opportunistic consolidation when touching the same invariant. | **Do not cleanup wholesale now.** Remove only with demonstrated equal-or-stronger semantic coverage. |

### Local

| Debt | Evidence / root cause | Blast radius | Current protection | Missing protection | Action / timing |
| --- | --- | --- | --- | --- | --- |
| Hades Model/View/adapter cognitive load | `Hades2Model.swift`, `Hades2View.swift` and `adapter.py` coordinate many operations; much complexity comes from real desired/runtime/lifecycle synchronization rather than accidental file size. | Slower agent comprehension and higher local edit risk. | Watcher, mutation scheduler, shortcut store, router, transport, persistence/Profile and catalogs are already separately owned. | No missing correctness invariant demonstrated. | **Do not mechanically split.** Extract only a responsibility with an already-independent interface/owner. |
| Core Save sudden-power-loss durability ceiling | Some directory metadata changes do not fsync every parent directory after `os.replace`. | Extreme power-loss window, not a demonstrated normal-process replay/corruption path. | Same-directory atomic replacement, file fsync, hashes, rollback/recovery evidence. | Full directory-fsync discipline. | **Defer.** Promote only with a concrete durability requirement/failure model. |
| Hades Profile subdirectory symlink hardening | Profile storage does not mirror every Core Save subdirectory-symlink containment guard. | Same-user local filesystem manipulation; no privilege boundary or demonstrated data-loss path. | filename/schema validation and same-user data root. | explicit contained-directory symlink discipline. | **Defer as Minor** unless a reachable failure is demonstrated. |

### Historical — solved, keep the invariant

| Historical family | Root cause that allowed it | Durable guardrail now |
| --- | --- | --- |
| `World::Stop()` treated as main-menu evidence | no explicit lifecycle evidence hierarchy; generic engine event was allowed to acquire game semantic meaning | real log-watcher evidence + lifecycle matrix; `World::Stop()` explicitly rejected |
| same-PID reset paid doomed probe / lost ready opportunity | PID lifetime and resident Lua generation were not distinct state variables; transient busy could discard event intent | runtime-generation invalidation + retained ready/exit intent + lifecycle scenario tests |
| Swift/Python trainer.log overwrite | “append” was treated as a seek position rather than a multi-writer file invariant | Darwin `O_APPEND` behavior test |
| staged restore repeated after successful commit/cleanup failure | destructive instruction had no durable consumed/applying claim | applying/applied state machine; unknown outcome is indeterminate |
| Save cold-restore TOCTOU | process stopped was treated as a durable decision instead of stale evidence | immediate pre-mutation recheck and fail-closed process query |
| rollback/recovery evidence lost from UI after backend death | recovery ownership ended with the failed producer process/reply | persistent contained `.rollback-*` discovery + shared Save Manager exposure |
| partial Profile shortcut collision | imported explicit state and omitted local explicit overrides had no deterministic merge ownership | compiled Swift shortcut reflow/collision behavior test |
| next-room reward resurrection | one-shot durable intent had no identity/consumption receipt across backend generations | schema-4 token + resident consumed-token receipt |

### Speculative — no current evidence, do not move now

| Proposal | Why it is speculative / risky now |
| --- | --- |
| Split `runtime/hades.lua` by size | multi-file loader/lifetime semantics are not proven in real Hades II; any runtime source change also requires revision bump and game acceptance |
| Broad MVVM/“clean architecture” rewrite of Hades View/Model | current complexity largely represents real state-transition coupling; pass-through layers would increase agent navigation cost |
| Move Hades desired/dormant/resource semantics into Core | violates proven module ownership and the reference-fixture contract without a second real game requiring the abstraction |
| Merge bootstrap + durable replay into fewer Lua boundaries | issue #4 measured the cost, but batching changes per-feature error isolation and outcome semantics; no current severe regression justifies it |
| Migrate to pytest/new test framework | no test-framework limitation is causing the current bug families; discovery drift can be fixed without dependency migration |
| Restore code from divergent historical branches | squash/superseded branches are historical evidence; current main contains the stronger behavior and no unique missing product implementation was found |

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
