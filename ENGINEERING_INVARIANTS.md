# Engineering invariants

Stable architecture and failure-semantics contract for MacGamingTrainer.

Consult the sections relevant to the changed responsibility. `AGENTS.md` owns the development/verification process, `PROJECT_STATUS.md` owns operating limits and acceptance evidence, and #124 owns current sequencing. These contracts protect accepted behavior; current code/tests may need correction to implement it.

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
            -> optional game-owned runtime adapter
                 -> debugger sidecar / native helper / engine runtime / no sidecar
```

### Core / Host owns

- app shell and shared visual/interaction primitives;
- generic hotkey capture/registration and generic feedback vocabulary;
- target-process observation and automatic/manual connection policy;
- the single backend worker session, JSONL request ordering, queueing, timeout and protocol verification;
- generic optional-sidecar process lifecycle, bounded JSONL framing/request identity, reply timeout, interruption cleanup, crash handling and terminal outcome-unknown trust semantics;
- debugger-agnostic Process Time Warp controller mechanics;
- optional cross-game save snapshot/restore/rollback/staging infrastructure;
- module discovery/build/package contract.

Core/Host does not own Hades command names, Hades desired/active/dormant semantics, boon/resource meaning, Hades save schema, sidecar method vocabulary, debugger launch/configuration, or LLDB/Lua policy.

### A game module owns

- command and payload semantics;
- typed decoding of its opaque backend payload;
- game-specific transport/debugger policy, including concrete debugger/runtime drivers;
- optional runtime-sidecar launch command, handshake/method vocabulary, risk classification, error presentation and engine/debugger semantics;
- durable game preferences/Profile semantics;
- runtime observation and game-specific lifecycle evidence;
- save codec/schema/edit semantics and game-specific save provider behavior;
- game-specific UI composition.

`reference_fixture` is the permanent proof that a second module does not require Hades-shaped Core APIs, LLDB, Lua, or an optional sidecar.

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

Hades public mutation patches compare complete observations at one reply-projection owner; the Adapter retains complete internal state. Status/lifecycle snapshots remain full, and action receipts stay on each actual reply. Errors, independent reply shapes and delivery of a historical Core-cached reply invalidate the public baseline so the next live runtime reply reconstructs the receiver without replaying an action.

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

An `outcome_unknown` non-idempotent result terminates trust in that transport/session. Hades LLDB transport is tainted after an unknown Lua result; the user must inspect the game and restart it before reconnecting for further Lua mutation. Receipts, session status and recovery details must give compatible steps and discourage repeating the uncertain action.

Native execution lifetime is part of mutation correctness. Keep yielding game coroutines and native modal presentation under their native owners; classify Trainer-owned callbacks at the actual mutation seam. A shared result contract must preserve these execution differences, including captured owner identity, native spend, unwind and draw-group lifetime.

## 5. Core Save safety model

Core Save is generic infrastructure. Hades save bytes/schema/edit meaning remain Hades-owned.

### Snapshot

- resolve only declared save roots/files;
- reject unsafe symlinks/path escapes;
- copy to Trainer-owned contained storage;
- hash before/after copy and verify manifest/file set;
- corrupt snapshots remain visible as invalid inventory rows so users can reveal/delete them deliberately.

Reading an editor source crosses the declared/verified file identity through a captured contained directory chain and a regular-file handle. A path checked earlier cannot authorize following a later symbolic link; managed-source bytes must still match the verified manifest after the read.

### Restore

1. verify target snapshot;
2. establish target process state; unknown process state fails closed;
3. capture and verify a rollback copy of the current real save set;
4. re-check stopped state before cold mutation (TOCTOU guard);
5. mutate through same-root temporary replacement/delete operations;
6. verify the installed target set;
7. on any post-mutation failure, restore and verify rollback before deleting the recovery copy.

Actual temporary writes, replacements, deletions and rollback use the same captured physical directory descriptors. Rechecking a mutable pathname alone cannot establish mutation ownership. A directory rename/redirection cannot redirect a transaction into another save set; if the original namespace identity cannot be verified after recovery, retain the recovery copy and report an incomplete outcome. Content/inode replacement at a fixed selected file path remains allowed for a pinned Save Editor document.

The last recoverable copy must never be destroyed merely to make an operation appear clean. If the backend dies while rollback itself is in progress and no JSON reply can be emitted, a later `CoreSaveService` instance must rediscover contained, non-symlink `transactions/.rollback-*` directories as recovery evidence. Recovery paths are user-visible evidence only: Core must not auto-restore or auto-delete them.

### Static editor replacement

- Core file replacement is **cold by default**. Running-target replacement is available only through an explicit caller opt-in on the generic transaction seam; ordinary restore/staged-restore policy is unchanged.
- A game-owned structured Save Editor may opt into that running replacement for a deliberately selected pinned document/physical target. The transaction still captures recoverable pre-write bytes, verifies path identity, atomically replaces, validates the installed bytes and rolls back on any proven post-mutation failure.
- A selected replacement owns only its selected file set for mutation, verification and rollback. Concurrent writes to other declared files must survive both success and rollback. The retained pre-write snapshot may still capture the complete set for a later deliberate whole-set restore; that evidence does not authorize replacing unrelated live files during editor rollback.
- The observed process state is fixed for the transaction attempt. A replacement that began as cold does not silently promote itself to hot if the game launches during preparation; it fails closed.
- For an intentionally version-pinned editor, target bytes written **before** the transaction baseline is captured are deliberate overwrite input. A target change during capture or after mutation begins is a transaction race: it cannot be reported as confirmed success, and failed/uncertain rollback retains recovery evidence.
- `hot=true` proves only that the disk replacement completed and survived the transaction's immediate verification window while the target process was running. It does not mean the game reloaded in-memory state, and it does not promise that a later game-authored save will preserve the edited bytes.

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

## 6. Module and interaction contracts

Ownership is a responsibility, not a permanent assignment to a filename. An extraction earns its interface by removing duplicated policy or knowledge from callers; file size alone establishes neither a defect nor a useful module. Core/module evolution follows `GAME_MODULES.md`.

Resident packaging currently loads one Lua source. Internal ownership may change within that contract; a multi-file loading route requires proof in the real Hades II runtime before adoption. Preserve native lifecycle distinctions described in section 4.

UI drafts are owned through edit completion: background observation preserves a focused/in-progress draft, refreshes an unfocused displayed value and cannot redirect a captured edit to a replacement target. Query/loading/error state belongs to its operation; stronger locks apply only where an authority-changing operation requires them. A rejected edit preserves acknowledged pending work and leaves an actionable next step.

User-visible success and recovery are part of the contract. An individual model update, build or descriptor count does not prove that a player can find the target, edit it, inspect consequences and complete the intended action. Verify that affected journey through existing owning interfaces/native-control harnesses; record the separate rendered/gameplay acceptance boundary.

## 7. Executable architecture contracts

Prefer these protections over prose or implementation-shape tests:

- `test_host_connection_policy_dev8.py`: real pure-state lifecycle transitions;
- `test_backend_session_recovery_dev8.py`: worker crash/timeout/restart behavior and no request replay;
- `test_hades2_run_log_watcher.py`: real file-event lifecycle decoding on macOS;
- `test_hades2_transport_outcome_unknown_taint.py`: unknown Lua result taints transport;
- Core Save behavior suites: resolution, snapshots, restore, service and protocol;
- `test_shortcut_chord_semantics.py`: resolved shortcut collision/reflow behavior;
- `test_cross_game_isolation.py` + module build matrix/reference fixture: Core/module boundary;
- `Tools/check_runtime_revision.py`: diff-based runtime revision discipline in Linux PR CI;
- `Tools/run_linux_checks.sh`: exhaustive Linux-portable test discovery; new portable `test_*.py` files run by default.

Source-text contracts remain acceptable where they enforce a structural boundary that cannot reasonably be compiled/observed without the real game. Prefer compile/type/behavior tests whenever the same invariant can be expressed there. Mutation testing verifies that selected high-value tests are sensitive to known defect classes; it is a periodic/convergence audit, not evidence that must be regenerated for every ordinary feature PR.

## 8. Terminology ownership

The game module's terminology registry owns classifications, bilingual values, provenance and allowed surfaces. For Hades, consult `Backend/games/hades2/terminology.py` and its declared reference resource; prose contains no mirrored inventory.

- Native Game Terms resolve `zh-CN` and English from the same supported-build localization ID; re-verify provenance when compatibility changes.
- Trainer Product Terms declare an explicit bilingual pair and why the Trainer owns it; they are not native titles.
- Internal Domain Terms stay implementation vocabulary until deliberately mapped to a user-facing native/product label.
- Compatibility Aliases are limited to declared migration/import/input boundaries and targeted diagnostics, not new canonical UI, protocol or storage identities. Trainer Invincibility uses `invincibility`; legacy `godMode` is confined to versioned migration/import boundaries and reserved for a possible native God Mode implementation.

Apply this contract to new/touched UI, errors, logs, protocol, storage, tests and current docs. Existing terms need no unrelated bulk rename. Hades classifications remain Hades-owned.
