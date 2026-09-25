# Engineering invariants

Stable architecture and failure-semantics contract for MacGamingTrainer.

This document describes rules that should remain true across feature work. `PROJECT_STATUS.md` owns current product status and planning issue #124 owns sequencing. Current code, Git history and executed tests remain the ultimate implementation evidence.

## 1. Ownership map

```text
App
  -> one TrainerBackendSession
  -> TrainerHostView
       -> TrainerTargetProcessMonitor
       -> TrainerConnectionPolicy
       -> optional TrainerSaveManagerModel
       -> selected TrainerGameModule
            -> game model/API
            -> game backend adapter/router
            -> game transport/persistence
            -> resident runtime when applicable
```

### Core / Host owns

- app shell and shared visual/interaction primitives;
- generic hotkey capture/registration and generic feedback vocabulary;
- target-process observation and automatic/manual connection policy;
- the single backend worker session, JSONL request ordering, queueing, timeout and protocol verification;
- generic Process Time Warp mechanics;
- optional cross-game save snapshot/restore/rollback/staging infrastructure;
- module discovery/build/package contract.

Core/Host does not own Hades command names, Hades desired/active/dormant semantics, boon/resource meaning, Hades save schema or LLDB/Lua policy.

### A game module owns

- command and payload semantics;
- typed decoding of its opaque backend payload;
- game-specific transport/debugger policy;
- durable game preferences/Profile semantics;
- runtime observation and game-specific lifecycle evidence;
- save codec/schema/edit semantics and game-specific save provider behavior;
- game-specific UI composition.

`reference_fixture` is the permanent proof that a second module does not require Hades-shaped Core APIs.

## 2. State sources of truth

| State class | Authoritative owner | Meaning | Replay rule |
| --- | --- | --- | --- |
| Host target/backend lifecycle | `TrainerTargetProcessMonitor`, `TrainerConnectionPolicy`, `TrainerBackendSession` | process presence, pending bounded reconnect/restart intent, worker health | event-driven only |
| Hades durable desired state | `Hades2PreferenceStore` / Profile service, projected by `Hades2Adapter` | user intent that should survive detach/backend restart when safe | replay when a verified compatible runtime is ready |
| Hades observable runtime state | resident Lua + Process Time Warp, decoded through `Hades2StatePatch` | what is actually active/available now | never infer active from desired alone |
| Hades dormant state | adapter/resident status projection | desired but currently not active in the observed runtime/scene | may become active after a valid lifecycle transition |
| UI optimistic/edit state | Swift model/view-local state | temporary presentation/input state | never becomes runtime truth without backend confirmation |
| Core Save transaction/recovery state | snapshot/restore service, staged claim files and contained rollback directories | durable filesystem transaction progress/outcome/recovery evidence | uncertain applying state is never auto-replayed; preserved recovery bytes remain discoverable |

Sparse payloads must preserve **absent vs explicit null** semantics. `Hades2FieldPatch` exists so an omitted field cannot accidentally erase observable state.

## 3. Lifecycle transition matrix

| Event | Required owner/action | Allowed | Forbidden |
| --- | --- | --- | --- |
| Trainer opens while target already runs | Host takes a presence snapshot | foreground/manual connection opportunity | treating discovery as a true launch/background-attach grant |
| Real target launch | Host records a new target lifetime | one bounded background recovery/connect opportunity | polling or repeated attach attempts |
| Target activation | Host records an opportunity | consume later when Trainer is foreground | immediate debugger attach merely because the game activated |
| Target exit / definitive replacement launch while request is busy | Host marks the prior connection observation stale and preserves one refresh until backend idle | refresh stale observed state before reconnect; the invalidation survives replacement process presence | clearing invalidation merely because a new target is running, or leaving stale `connected=true` |
| Backend unexpected exit | `TrainerBackendSession` clears observable game state and performs bounded worker recovery | Host may reconnect after worker recovery if target remains relevant | module-owned second backend session or request replay |
| Backend request timeout / terminal transport error | `BackendClient` terminates that backend instance | restart worker, then re-observe/reconcile | replaying the timed-out/in-flight request |
| Hades same-PID Lua reset | Hades log watcher invalidates runtime generation bookkeeping | bootstrap/status and durable replay in the existing debugger attachment | second debugger attachment, PID-only lifetime assumptions, periodic Lua polling |
| Hades runtime-ready after reset | Hades consumes the retained ready signal once backend is idle | status/bootstrap then replay safe durable state | losing a ready event because it arrived while attach/backend was busy |
| Process exit/new PID | Host/Hades clear session-local observable state | durable desired state can remain pending | assuming resident Lua/Time Warp state survived process lifetime |
| Manual debugger detach | Host suppresses automatic reconnect for the current target lifetime | explicit reconnect clears suppression | killing durable desired intent merely because debugger detached |

Hades lifecycle signals must be backed by observed game evidence. Current log semantics are:

- main menu: `Loading package: MainMenu.pkg`;
- runtime generation reset: `App.Reset Start` / `Lua interface destroyed`;
- ready after a pending reset: `Finished loadScreen onExit`.

Do not substitute generic-looking engine messages without target-log evidence. `World::Stop()` is explicitly not a main-menu signal.

Target-process **presence** and target-process **lifetime validity** are also distinct. An observed exit invalidates the current connection until that stale observation is refreshed. A definitive launch notification is itself new-lifetime evidence and must perform the same invalidation when a rapid replacement hides the intermediate stopped snapshot. Busy work may delay that refresh; later process presence must not cancel it.

## 4. Mutation and replay safety

Classify an operation before adding retry/recovery behavior.

| Operation family | Durable? | Safe automatic replay? | Enforcement/notes |
| --- | ---: | ---: | --- |
| scan/metadata | no | may be re-issued by a new explicit lifecycle action | still subject to process-query failure semantics |
| status | no | a later status may be issued | Hades status is not a pure snapshot: resident `synchronize()` maintenance can run |
| durable feature/multiplier/lock intent | yes | yes, after verified runtime readiness | adapter preference replay owns this |
| Process Time Warp desired speed | yes (Hades preference) | yes after transport/runtime identity is re-established | generic mechanism is Core; game-specific desired meaning is Hades-owned |
| direct absolute resource/stat/vital edits | generally no unless represented by a durable lock | never replay an outcome-unknown in-flight request | successful lock state may later enter durable preferences |
| reward spawn | no | no | request/action ledger prevents duplicate same-request execution where applicable |
| native sell/special-choice UI | no | no | one-shot native modal; never preference-replayed |
| next-room reward | durable one-shot with identity token | only while consumption is unproven | resident consumption receipt prevents resurrection after backend restart |
| disable/cleanup on app exit | durable reset + best-effort runtime cleanup | not a blind retry loop | persistence failure must not prevent best-effort resident teardown; failure still surfaces |

Global transport rule: an `outcome_unknown` non-idempotent result terminates trust in that transport/session. Hades LLDB transport is tainted after an unknown Lua result; later Lua mutation requires restart/reconnect rather than guessing whether the operation ran.

## 5. Core Save safety model

Core Save is generic infrastructure. Hades save bytes/schema/edit meaning remain Hades-owned.

### Snapshot

- resolve only declared save roots/files;
- reject unsafe symlinks/path escapes;
- copy to Trainer-owned contained storage;
- hash before/after copy and verify manifest/file set;
- corrupt snapshots remain visible as invalid inventory rows so users can reveal/delete them deliberately.

### Restore

1. verify target snapshot;
2. establish target process state; unknown process state fails closed;
3. capture and verify a rollback copy of the current real save set;
4. re-check stopped state before cold mutation (TOCTOU guard);
5. mutate through same-root temporary replacement/delete operations;
6. verify the installed target set;
7. on any post-mutation failure, restore and verify rollback before deleting the recovery copy.

The last recoverable copy must never be destroyed merely to make an operation appear clean. If the backend dies while rollback itself is in progress and no JSON reply can be emitted, a later `CoreSaveService` instance must rediscover contained, non-symlink `transactions/.rollback-*` directories as recovery evidence. Recovery paths are user-visible evidence only: Core must not auto-restore or auto-delete them.

### Staged restore

```text
pending staged-restore.json
  --atomic claim-->
.staged-restore-applying-<id>.json
  --verified success-->
.staged-restore-applied-<id>.json
  --best-effort cleanup--> removed
```

- The applying claim is obtained before crossing the destructive restore transaction.
- Ordinary failures whose transaction outcome is known may restore the instruction to pending.
- rollback failure, `KeyboardInterrupt`/termination or lost acknowledgement leaves an applying marker and is **indeterminate**.
- indeterminate state is surfaced and blocks automatic replay/deletion assumptions.
- tests use temporary save roots only. Never point automated tests at real Hades/user saves.

## 6. File boundaries and cognitive-load rules

File size alone is not a refactor reason.

- `runtime/hades.lua` intentionally co-locates resident state, hook ownership, reconciliation and dispatch. Do not split it until a multi-file loader is proven in the real Hades II runtime. Any source change requires a resident revision bump and real-game verification.
- `Hades2Model.swift` currently co-locates the Hades observable projection, lifecycle response, command scheduling and exit cleanup. Extract only a responsibility that already has a clear independent owner/interface; do not create pass-through stores merely to reduce line count.
- `Hades2View.swift` may be sliced only where presentation responsibility is genuinely independent; reusable visual language belongs in Core/UI while Hades meaning stays in Hades.
- `Hades2Adapter` is the synchronization boundary between persistence, transport and resident state. Prefer extracting already-independent services, not fragmenting the state machine across files.
- Core Save snapshot/service/restore files are separate transaction responsibilities and should remain game-agnostic.

## 7. Executable architecture contracts

Prefer these protections over prose or implementation-shape tests:

- `test_host_connection_policy_dev8.py`: real pure-state lifecycle transitions;
- `test_backend_session_recovery_dev8.py`: worker crash/timeout/restart behavior and no request replay;
- `test_hades2_run_log_watcher.py`: real file-event lifecycle decoding on macOS;
- `test_hades2_transport_outcome_unknown_taint.py`: unknown Lua result taints transport;
- Core Save behavior suites: resolution, snapshots, restore, service and protocol;
- `test_shortcut_chord_semantics.py`: resolved shortcut collision/reflow behavior;
- `test_cross_game_isolation.py` + module build matrix/reference fixture: Core/module boundary;
- `Tools/check_runtime_revision.py`: diff-based runtime revision discipline in Linux CI;
- `Tools/run_linux_checks.sh`: exhaustive Linux-portable test discovery; new portable `test_*.py` files run by default.

Source-text contracts remain acceptable where they enforce a structural boundary that cannot reasonably be compiled/observed without the real game. Prefer compile/type/behavior tests whenever the same invariant can be expressed there.

## 8. Verification matrix

| Change | Minimum automated gate | Additional requirement |
| --- | --- | --- |
| Backend/Core Python | `Tools/run_linux_checks.sh` | macOS only if packaging/platform behavior touched |
| Host/Swift lifecycle or AppKit UI | Linux portable contracts where applicable | `Build 2 macOS` |
| module/Core boundary/build graph | Linux contracts | module build matrix/reference fixture + macOS build |
| Core Save transaction semantics | full Linux portable Save behavior suite | macOS for Swift Save UI/model integration |
| Hades transport/adapter only | Linux contracts | real game only when target-runtime semantics cannot be simulated |
| `runtime/hades.lua` | Linux contracts + runtime revision gate | real Hades II acceptance; automated tests are not final verification |
| release/manual QA artifact | all relevant CI | exact tested HEAD, prebuilt artifact and SHA256 |

A passing ancestor commit is historical evidence only. Claims of “fixed/passed” must name the exact SHA whose source was executed or built.

## 9. Terminology governance

Terminology is part of the product contract. Classify a term before introducing it; provenance and ownership determine where it may appear. The governance model applies to UI, user-visible errors, logs, protocol payloads, files, tests and current documentation. Existing terms are not bulk-renamed solely to satisfy this model; new or touched surfaces must follow it.

| Class | Ownership / provenance | Lifecycle | Allowed use | Forbidden use |
| --- | --- | --- | --- | --- |
| **Native Game Term** | Game-owned; sourced from the supported target build's official localization/catalog/reference, identified by its localization ID where available | Changes with the target build; re-verify when the supported build changes | Game-facing UI, game-facing errors, terminology-sensitive tests/docs, and protocol fields when they represent the native concept | Inventing a replacement label, silently mixing a different build's localization, or presenting an internal ID as the official name |
| **Trainer Product Term** | Trainer-owned; an explicit label for a Trainer aggregation or state with no single native equivalent | Stable while the Trainer contract needs it; change deliberately and document the bilingual pair | Trainer UI, Trainer status/errors, product docs and tests | Presenting it as a native game title, using it to overwrite a native term, or changing only one language |
| **Internal Domain Term** | Implementation-owned; stable identifier/model vocabulary chosen for code and contracts | Controlled by the implementation contract; may outlive a game-facing label | Code, protocol internals, fixtures and implementation-focused tests/docs | Exposing it as a native user-facing term without an explicit mapping |
| **Compatibility Alias** | Transitional Trainer-owned mapping from a legacy/shorthand term to a canonical term; alias source must be identifiable | Temporary; remove after migration or when compatibility is no longer required | Input compatibility, migration, targeted compatibility tests and explicit diagnostics | New user-facing copy, canonical storage, protocol naming, or silently preserving an obsolete alias as the preferred term |

### Bilingual and pairing rule

For a Native Game Term, Chinese and English must resolve from the **same target-build localization ID**. Do not hand-pair translations from different entries or substitute a remembered/third-party translation. For a Trainer Product Term, declare an explicit `zh-CN`/English pair and record why the Trainer owns the label; it must never masquerade as native terminology. Internal Domain Terms and Compatibility Aliases do not become bilingual product labels unless they are deliberately exposed, in which case they must resolve through one of the two user-facing classes above.

### Current Hades II examples

The target-build terminology reference used by #112 is the evidence source for these classifications:

- **Native Game Terms:** `祝福` / `Boon`, `奥林匹斯的祝福` / `Boon of Olympus`, `重塑命运` / `Change of Fate`, `净化之池` / `Pool of Purging`, `巫咒` / `Hex`, `生命值` / `Life`, `魔力值` / `Magick`, and `卡戎之井` / `Well of Charon`. Character/source names and native choice titles are also native terms when resolved from their target-build localization IDs.
- **Trainer Product Terms:** `角色奖励` / `Character Rewards`, `奖励选择界面` / `Reward Choice`, `奥林匹斯诸神` / `Olympians`, `资源与常规掉落` / `Resources & Standard Drops`, `局外资源奖励` / `Meta Resources`, `元素奖励` / `Element Rewards`, `其他房间奖励` / `Other Room Rewards`, `商店商品` / `Shop Items`, and `资源` / `Resources`. These are Trainer-owned aggregations, not native screen titles.
- **Internal Domain Terms:** identifiers such as `TalentDrop`, `SpellDrop`, `MetaCurrencyDrop`, `group = special`, and `group = olympian` remain implementation vocabulary. They may map to native or Trainer Product Terms, but they are not themselves player-facing terminology.
- **Compatibility Aliases:** the #112 reference marks legacy/shorthand forms such as `特殊祝福`, `诸神祝福`, `重骰`, `祝福出售界面`, `出售祝福`, `原生三选一`, and `卡俄斯祝福` as forbidden user-facing aliases. They may be recognized only where a compatibility boundary explicitly requires them; canonical UI/docs must use the classified term instead.

Game-specific classifications remain owned by the game module. In particular, Hades concepts must not be moved into Core merely because a label or grouping looks reusable; a cross-game abstraction requires an independently proven, game-agnostic contract.
