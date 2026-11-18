# Backend technical-debt audit (Python Core, Hades I, Hades II)

- **Source:** `main@73697aef`.
- **Mode:** read-only. Only one test was run: `python3 tests/test_host_watchdog_aggregate_budgets.py`, which passed.
- **Scope:** `Backend/core/*.py`, `Backend/debugger/*`, `Backend/games/hades/*.py` and `Backend/games/hades2/*.py`. `runtime/hades.lua` got a structural pass only.
- **Evidence labels:**
  - **[fact]** comes from source, git history or a command I ran.
  - **[inference]** is my reasoning. It has not been reproduced in the real game or in a fixture.

## 0. Context that changes earlier decisions

The 2026-09-21 governance audit (`docs/audits/2026-09-21-ai-development-governance.md` §7) deliberately decided against three things:

- splitting `hades.lua`;
- breaking up `Hades2Adapter` "just to reduce file size";
- moving Hades semantics into Core "without a second real game proving the abstraction".

When that audit was written, Hades II was the only real adapter. Hades I arrived on 2026-10-25 (`03669425`, `60a00bd4`). Since then, many mechanisms have been written twice. Some fixes had to land in both games in the same commit:

- `b1d0aa44` "quarantine failed detach cleanup";
- `747f0d18` "retain debugger and mailbox ownership through persistent close failures".

Other work was spent making Hades I match Hades II:

- `410f89a0` "Align Hades I equivalent features to the Hades II interaction contract (#657)";
- `c93a0f1e` "Align Hades I fixed-value metric locks with Hades II (#663)".

The "two real adapters" condition in `GAME_MODULES.md` §Architecture evolution is therefore now met for several **mechanisms**. It is still not met for Hades **semantics**. These are different things: semantics (desired/dormant/lock meaning, feature lists, Lua command vocabulary) correctly remain game-owned. The findings below propose sharing only mechanisms that are typed out twice.

Since Hades I landed, commits touching each pair of mirrored files split as follows [fact]:

| Pair | Commits touching both | Hades I only | Hades II only |
|---|---|---|---|
| `transport.py` | 3 | 12 | 2 |
| `lldb_worker.py` | 2 | 11 | 1 |
| `client.py` / `transport_client.py` | 0 | 7 | 4 |
| `preferences.py` | 0 | 7 | 2 |
| `save_workspace.py` | 1 | 4 | 1 |

Many of the Hades I-only transport commits relearn lifecycle lessons that Hades II had already absorbed: `ee0f46d1` "prevent debugserver cleanup leaks", `b1d0aa44`, `747f0d18`.

### What is already healthy

These are worth keeping as they are. No action is needed.

- **Core has no game literals.** Searching `Backend/core` for `hades`, `profile`, `.sav` and `zh-CN` finds nothing game-shaped. The Save stack (`save_resolution`, `save_snapshots`, `save_restore`, `save_service`, `structured_save_edit`) is generic.
- **Generic mechanisms are already shared.** `core/sidecar.py`, `core/framing.py`, `core/lz4_block.py` and `core/persistence.atomic_write_text` are genuinely shared.
- **The revision gate is metadata-driven.** `Tools/check_runtime_revision.py:1-14` already gates both games' resident Lua.
- **Game-owned semantics are correctly game-owned.** This covers feature lists in both `schema.py` files, Hades II `desired_reconciliation.py`, Hades II `preparation.py` (re-signing the game executable; there is only one adapter, so it stays game-owned for now), `terminology.py`, and the native mailbox versus Hades I's Lua trait-receipt polling.

---

## Findings

Each finding lists the next fields in this order: severity, category, evidence, why it matters, remediation with size, and verification.

### F1. Two debugger-transport lifecycle state machines, with confirmed drift

- **Severity:** HIGH
- **Category:** duplication / drift

**Evidence [fact]**

Both transports implement the same attach/stop/resume/detach/quarantine machine. The method names are largely identical: `cleanup_pending`, `_record_cleanup_failure`, `_quarantined_error`, `_clear_attachment`, `_rollback_failed_attach`, `detach`, `close`.

- `Backend/games/hades/transport.py`: 481 lines. The relevant methods are at :404-481 (`_quarantined_error` :412, `_rollback_failed_attach` :441, `detach` :457).
- `Backend/games/hades2/transport.py`: 628 lines (`_record_cleanup_failure` :514, `_quarantined_error` :519, `_rollback_failed_attach` :546, `detach` :569).

Fixes have been applied twice in the same commit:

- `b1d0aa44`: +84 lines in Hades I, +144 lines in Hades II;
- `747f0d18`: touched both transports.

**Drift 1: macOS stop-signal handoff.** Hades II sends a post-detach `os.kill(resume_pid, signal.SIGCONT)` (hades2/transport.py:614). Its comment reads "macOS may retain its BSD stop signal". It also tracks `pending_resume_pid`. This was introduced in `09e5a5b0` (2026-10-07). Hades I's `detach` (hades/transport.py:457-475) has no SIGCONT handoff, and there is no `pending_resume_pid` anywhere under `Backend/games/hades`.

**Drift 2: build-identity policy.**

- Hades I fails closed on an unknown UUID: `image.GetUUIDString() != self.supported_build['uuid']` → `unsupportedBuild` (hades/transport.py:90).
- Hades II accepts an unknown UUID and resolves symbols by name for "a new build" (hades2/transport.py:154-169: "A new build may move every address. Resolve only symbols owned by its live main image"). This code dates from the 0.1 baseline `31297c90`.

**Drift 3: quarantine error shapes differ.**

- Hades I returns `failure('detach_failed','detachFailed', note)`, which is a key.
- Hades II returns `TransportError('detach_failed', diagnostic, diagnostic=diagnostic)` (hades2/transport.py:539). Here the presentation field is a diagnostic sentence, not a key.

**Why it matters**

A third LLDB-backed game would copy one of these two files and inherit one set of gaps. Every lifecycle fix currently costs two edits plus two sets of tests.

[inference] Whether the SIGCONT handoff is needed under Rosetta for Hades I is unverified. Either Hades I has a latent "game left stopped after detach" defect, or Hades II has an unexplained step. Both outcomes are debt.

**Remediation (M–L)**

Extract a game-agnostic LLDB attachment-lifecycle helper. It should cover:

- stage-recorded cleanup;
- quarantine error construction (with a presentation-key factory injected by the game);
- rollback after a failed attach;
- the stop → restore-focus → delete-breakpoints → detach → OS-resume sequence.

Place it in an optional shared debugger package (for example `Backend/debugger/`), not in Core. `GAME_MODULES.md` keeps LLDB out of Core, but now allows a shared driver seam once a second real implementation exists. Symbol and UUID verification, boundary breakpoints, the mailbox, VM interruption and Lua execution stay with each game.

Decide one unknown-build policy (recommended: fail closed, as Hades I does) and record it in `ENGINEERING_INVARIANTS.md`.

**Verification**

- Hades I: `test_hades_transport_cleanup.py`, `test_hades_module_lifecycle.py`, `test_hades_rosetta_attach_cleanup.py`, `test_hades_native_stop.py`.
- Hades II: `test_hades2_transport_detach.py`, `test_hades2_transport_stop.py`, `test_hades2_disconnect_lifecycle.py`, `test_hades2_transport_outcome_unknown_taint.py`.
- Real-game attach/detach acceptance for both games, because this is native lifecycle.

---

### F2. Two incompatible runtime-sidecar architectures, each a template a third game would copy

- **Severity:** MED-HIGH
- **Category:** seam / duplication

**Evidence [fact]**

The two workers sit on opposite sides of the same seam.

**Hades I has a fat worker.** `hades/lldb_worker.py:130-218` holds the whole game command vocabulary (`set_feature`, `lock_vital`, `add_trait`, …). It assembles the Lua source itself (:47-78). It re-sends the entire `runtime.lua` with every call, including `status`: `source = 'local runtime = (function()\n' + self.source + ...` (:50). When I measured the assembled `status` source, it was 110,155 bytes against `LUA_SOURCE_LIMIT_BYTES = 128 * 1024` (hades/transport.py:10), leaving 20,917 bytes of headroom. `test_hades_transport_cleanup.py:336` guards this.

**Hades II has a thin worker.** `hades2/lldb_worker.py:112-161` exposes only `transport.*` and `time_warp.*` RPCs plus a `hello` handshake with `WORKER_PROTOCOL_VERSION = 1`. That version literal is repeated as `_WORKER_PROTOCOL_VERSION = 1` in `transport_client.py:19`. The resident Lua bootstrap is sent once per generation (`resident_session.py:293`).

The two designs also differ in details:

- **Cleanup policy.** Hades I sets `child_owns_cleanup=True` (`hades/client.py:38`). Hades II leaves it at the default `False` (`transport_client.py:65`).
- **Fallback error codes.** Hades I uses `'debugger_internal'` (`hades/lldb_worker.py:225`). Hades II uses `'debugger_worker_internal'` (`hades2/lldb_worker.py:34`).
- **Handshake.** Hades I has no worker protocol handshake at all.

**Why it matters**

A new LLDB/Lua game has no neutral template. The reference fixture deliberately has no sidecar, so the new game copies one of these two shapes. Hades I's shape grows per-call payload with every runtime change.

[inference] With `child_owns_cleanup=False`, a sidecar timeout in Hades II makes Core send SIGTERM (`core/sidecar.py:116-131`). Python's default SIGTERM handler exits without running the worker's `finally: worker.transport.close()` (`hades2/lldb_worker.py:180-186`). The SIGCONT handoff from F1 can therefore be skipped on exactly the failure path that needs it. Hades I adopted `child_owns_cleanup` for this class of problem in `eca25b9b`.

**Remediation (M)**

- Adopt the thin-worker shape as the documented LLDB pattern in `docs/development/add-a-game-module.md`.
- Move the following into a small shared worker helper next to the debugger helper from F1:
  - the hello/protocol handshake;
  - `error_payload`;
  - the "retain until target exits" close loop (`hades/lldb_worker.py:230-240`).
- Decide `child_owns_cleanup` per contract, not per game.
- Optionally migrate Hades I to resident-once bootstrap. This changes its resident revision and needs real-game acceptance.

**Verification**

- `test_sidecar_protocol.py`, `test_hades_worker.py`, `test_hades_recovery.py`, `test_hades_time_warp_worker.py`;
- `test_hades2_lldb_worker_protocol.py`, `test_hades2_lldb_worker_lifecycle.py`, `test_hades2_time_warp_sidecar_recovery.py`.

---

### F3. Three different mechanisms for "outcome-unknown is never replayed across restarts"

- **Severity:** MED
- **Category:** seam / duplication

**Evidence [fact]**

**Hades I: an on-disk journal.** It keeps `MacGamingTrainer/hades/runtime-request.json`, keyed by pid and `ps -o lstart=` (`hades/recovery.py:10-55`).

- `HadesRuntimeClient._call` journals every call that crosses into the runtime, including `status`: `crosses_runtime = method != 'time_warp.current_speed'` (`hades/client.py:45-49`). Every status poll therefore does an fsynced temp-file write, an `os.replace` and an unlink.
- The journal re-implements atomic write (`recovery.py:35-49`) instead of using `core.persistence.atomic_write_text`.
- `process_identity` runs `subprocess.run` with no timeout (`recovery.py:11`).

**Hades II: no disk journal.** Trust lives in the in-memory taint plus the resident and mailbox lease (`resident_session.py:364-384`, `transport.py:44-54`). `PROJECT_STATUS.md:33` describes it: "a claimed request without trustworthy completion permanently closes its lease".

**Host:** retains the unknown in-flight outcome across worker recovery (`ENGINEERING_INVARIANTS.md` §3).

**Why it matters**

`ENGINEERING_INVARIANTS.md` §4 describes this invariant once, but each game implements it differently. A third game has to design target-lifetime identity (pid plus start time) and durable unknown-outcome evidence from scratch. Hades I's version adds disk I/O to every status call.

**Remediation (M)**

Provide a Core primitive `TargetLifetime(pid) -> identity` that reads the process start time through `proc_pidinfo` (no subprocess). Add an optional `OutcomeJournal(data_dir)` with `guard`, `begin` and `complete`. Hades I adopts it. Hades II can adopt it for its sidecar-loss path.

Restrict journaling to calls classified as mutating. Status is "maintenance" per §4, so classify it explicitly rather than by the method-name rule.

**Verification**

- `test_hades_recovery.py`, `test_hades_process_identity_macos.py`;
- `test_backend_session_recovery_dev8.py`, `test_hades2_transport_outcome_unknown_taint.py`, `test_hades2_attach_terminal_recovery.py`.

---

### F4. Preference and profile storage mechanics are duplicated, and storage locations disagree

- **Severity:** MED
- **Category:** duplication / drift

**Evidence [fact]**

#620 (`7b161eb6`) "Consolidate shared persistence and management workflows" shared the Swift UI for profiles and diagnostics. On the backend side it extracted only `atomic_write_text` (`core/persistence.py`). Everything else is still duplicated.

**Name rules are identical, but files are named differently.**

- The rule "1–64 visible characters, no `/` or `\`" exists in both `hades/profiles.py:23-30` and `hades2/profile_service.py:118-124`.
- Hades I uses the full sha256 for the filename (`profiles.py:33`). Hades II truncates it: `hexdigest()[:24]` (`profile_service.py:129`).

**Corrupt-file handling differs.**

- Hades II quarantines the file (`hades2/persistence.py:32-51`, `profile_service._quarantine`).
- Hades I logs and skips it (`profiles.py:63-66`).

**Newer-schema refusal is implemented twice:** `hades/preferences.py:10-20` and `hades2/persistence.UnsupportedSchemaVersionError`.

**Storage locations disagree.**

- Hades I: `MacGamingTrainer/hades/preferences.json` and `hades/profiles/` (`preferences.py:30`).
- Hades II: `MacGamingTrainer/desired-state.json`, `profiles/`, `backups/`, `diagnostics/` at the data root (`config.py:57-59`, with the comment "Preserve the existing Hades II data location. New game modules should use a namespaced directory").
- Core Save uses `<root>/<game_id>/saves` (`core/save_snapshots.py:108-113`).

**Errors are reported differently.** Hades I raises key-based `AdapterError`s. Hades II raises prose (`profile_service.py` has 21 raise sites with Chinese text).

**Why it matters**

The third game writes its own store and picks one of two conventions. Hades II's directories at the data root also share a namespace with `<root>/<game_id>/`. [inference] A future module with id `profiles`, `backups` or `diagnostics` would collide. That is low probability, but nothing prevents it.

**Remediation (M)**

Add a Core `VersionedDocumentStore` and `ProfileStore` with:

- an envelope of `schemaVersion`, `gameID`, `name`, `updatedAt` and `payload`;
- list/load/save/delete operations;
- quarantine and newer-schema refusal;
- a game-supplied `normalize(payload, version)` and error-key factory.

Add `data_dir` to `GameAdapterContext` (see F11).

Migrating Hades II's root-level files into `hades2/` is a **persistence-schema identity change**. Per the AGENTS version-impact procedure it needs migration and old-version-refusal tests.

**Verification**

- `test_atomic_persistence.py`, `test_hades_management.py`;
- `test_hades2_profile_workloads.py`, `test_hades2_currency_preference_migration.py`, `test_hades2_chaos_gate_preferences.py`, `test_hades2_gathering_preferences.py`;
- `test_module_management_actions.py`.

---

### F5. The Save Editor session wrapper and workspace lifecycle are typed out twice; Core's session is used through a mutable back door

- **Severity:** HIGH
- **Category:** duplication / misplaced ownership

**Evidence [fact]**

**The session wrappers are identical.** `diff Backend/games/hades/save_edit.py Backend/games/hades2/save_edit.py` shows only renamed identifiers. Both files are 139 lines. The only game-specific inputs are the document class and two `save_provider` functions (`editor_files`, `profile_file_identity`). Everything else is the same mechanism:

- target resolution;
- source matching;
- building the source-kind dict;
- forwarding eight properties to `StructuredSaveEditSession`.

**The workspace lifecycle is duplicated** in `hades/save_workspace.py:158-212,671-687` and `hades2/save_workspace.py:168-230,1127-1132,1873-1904`:

- random `identifier` and `baseline_generation` values;
- a `pending` map;
- inventory `{sources, targets, defaultSource}`;
- summary fields `recoveryPath`, `recoveryPaths`, `recoveryUnresolved`;
- the apply sequence: `session.document = candidate; try: apply() except: restore`, then clear `pending` and rotate the baseline.

**Workspace registries are duplicated in both adapters.**

- Hades I keeps them in `adapter.py:357-395`, inside one try block, and checks baselines inside each workspace method.
- Hades II spreads them over `adapter.py:1029-1094` (10 methods) and `command_contract.py:808-816`, which does the central baseline check (`workspace.require_baseline`).
- `bind_save_service` is overridden in Hades II only (`adapter.py:1029-1031`), to clear workspaces.

**The layering leaks.**

- Both games pass the candidate document to Core by assigning to `StructuredSaveEditSession.document` (`core/structured_save_edit.py`, the document setter at lines 168-174 of the file) before calling `apply()`.
- Hades II reaches through the Core service to the game's own provider: `getattr(getattr(save_service,"provider",None),"game_path",None)` (`hades2/save_workspace.py:214-215`).

**Workspaces are never evicted.** Both `save_workspaces` dicts are unbounded and are only cleared by an explicit `save_editor_close`. Each entry holds a decoded save document.

**Why it matters**

`ENGINEERING_INVARIANTS.md` §5 says Core's `StructuredSaveEditSession` "owns the shared structured-document lifecycle". In practice each game owns roughly 300–400 lines of identical lifecycle glue. A third game with a Save Editor copies it.

[inference] A crashed or abandoned Swift tool window leaks one decoded document per open, for the life of the backend.

**Remediation (M)**

1. Add `StructuredSaveEditSession.open_selected(save_service, codec, eligibility)`, where `eligibility` exposes `editor_files` and `is_source`. Delete both `save_edit.py` files.
2. Add `apply(candidate)` and remove the public `document` setter.
3. Add a Core `SaveEditorWorkspaceRegistry`. It owns workspace ids, the baseline generation and its check, close, a maximum number of open workspaces, and the standard `save_editor_{inventory,open,close,target}` routing. Games keep query, detail, stage, review and apply semantics.
4. Pass `game_path` into the game's workspace explicitly rather than through `save_service.provider`.

**Verification**

- `test_core_structured_save_edit.py`, `test_core_save_hot_replace.py`;
- `test_hades_save_workspace.py`, `test_hades_save_editor_recovery.py`, `test_hades_save_editor_conflicts.py`;
- `test_hades2_save_workspace.py`, `test_hades2_save_edit_transaction.py`, `test_hades2_save_editor_command_contract.py`, `test_hades2_managed_backup_save_editor.py`;
- the reply-coordinator assertions in `multi_game_context_harness.py`.

---

### F6. Supergiant save codec and provider helpers are duplicated across the two Hades games

- **Severity:** LOW (for a non-Supergiant third game) / MED (for another Supergiant title)
- **Category:** duplication (shared by the game family, not by all games)

**Evidence [fact]**

- **Two luabins codecs.** `hades/save_document.py:52-200` (`LuaTable`, `decode_lua`, `encode_lua`) and `hades2/save_document.py:79-400` (`LuaTable`, `_decode_luabins`, `_encode_luabins`) implement the same luabins format and the same rule for ambiguous duplicate keys. The key-identity functions are written differently but are equivalent: `same_key` versus `_lua_key_identity`.
- **Identical provider helpers.** `_PROFILE_FILE` regex, `profile_file_identity` and the SGB1 `activeProfile` parsing are the same in `hades/save_provider.py:7-33` and `hades2/save_provider.py:9-70`.
- **Drift.** Hades II selects `_Temp.sav` over the main save when the `.v.sav` marker is newer (`save_provider.py:69-90`). Hades I has no `_Temp` logic.
- **Exception types differ:** `SaveFormatError` versus `HadesSaveFormatError`.
- Both `save_provider.resolve` implementations are pass-throughs (see F11).

**Why it matters**

This does not block a non-Supergiant module. It is the cheapest duplication to remove if the product adds another Supergiant title. The `_Temp` drift may hide a Hades I correctness gap [inference; Hades I's save-slot semantics are unverified].

**Remediation (S–M)**

Create a family library such as `Backend/games/_supergiant/{luabins.py,sgb.py}`. It must be non-Core and have no manifest. Decide explicitly whether Hades I needs the `_Temp`/`.v` rule.

**Verification**

`test_hades_save_document.py`, `test_hades2_save_document.py`, `test_hades_save_provider.py`, `test_hades2_save_provider_round21.py`.

---

### F7. Error presentation: three strategies in the modules, and a duck-typed Core contract

- **Severity:** HIGH
- **Category:** stopgap that became a constraint / god module

**Evidence [fact]**

**Strategy 1: Hades I runtime raises keys directly**, for example `AdapterError('not_connected','hades.error.notConnected')`.

**Strategy 2: the Hades I Save Editor wraps raw English text into one key.** `AdapterError(..., 'hades.saveEditor.error', arguments=[str(error)])` (`hades/adapter.py:388-395`). The Swift template is `"存档编辑失败：%@"` (`Sources/Hades/HadesPresentation.swift:34`). Chinese players therefore see English backend text inside a Chinese frame.

**Strategy 3: Hades II raises Chinese or English prose and maps it back to keys afterwards.**

- Raise sites containing Chinese text, per file: `command_contract.py` 51, `transport.py` 31, `profile_service.py` 21, `preparation.py` 17, `schema.py` 9, `preferences.py` 7, `resident_session.py` 6, `adapter.py` 5. There are also English prose raise sites throughout the `save_*` modules.
- `error_presentation.py` (1,033 lines) holds a `REGISTRY` of 302 rules: 267 literal, 14 prefix, 12 regex, 6 delimited, 2 affix and 1 segmented. 96 of them are runtime-scoped, and they produce 207 distinct keys. Its own header says the Chinese text "is retained as the authoritative source for each key".
- `command_contract.py:831-845` runs `presentation_for(str(error))` on every exception.
- An escape hatch exists: `_hades2_presentation_ready` (`save_advanced.py:22`, `save_workspace.py:120`).
- `test_hades2_presentation_contract.py` AST-scans raise sites to force every message into the registry.

**Core's error contract is duck-typed.** `core/protocol.py:258-281` reads `code`, `presentation`, `diagnostic`, `arguments` and `recovery_path` through `getattr`/`hasattr`. At least five error shapes reach it:

- `AdapterError`;
- `HostPresentationError`;
- Core `RuntimeError`s with a class attribute `code` but no presentation (`save_restore.py:17-30`), which fall back to `host.backend.error.operationFailed`;
- `StructuredSaveEditRecoveryError(ValueError)` carrying presentation attributes (`structured_save_edit.py:38-60`);
- Hades II's `_SaveEditorActionValidationError`.

**Hades I borrows Host keys.** It raises Host-owned `host.timeWarp.error.verifyFailed` through a plain `AdapterError` (`hades/simulation_time_warp.py:137,149,182`), bypassing `HostPresentationError`.

**Why it matters**

- In Hades II the message text is the semantic identifier. Rewording a message changes behaviour.
- Each new message costs: the prose, a registry rule, two translations, and staying inside the AST scanner's visibility.
- The duck-typed Core seam means a new module learns the contract by reading `protocol.py`.
- [inference] Wrapping an error rebuilds it as a new `Hades2PresentationError` (`command_contract.py:839-845`) and drops non-standard attributes such as `recovery_path`. Today no registered rule matches Core rollback messages, so this has not happened, but it is a latent risk.

**Remediation (L, incremental)**

1. Add an explicit Core `PresentableError` protocol or base class. Give Core Save errors `host.save.*` keys.
2. Convert Hades II raise sites to `Hades2PresentationError(code, key, args, diagnostic=prose)`, one module at a time. The registry then shrinks to resident-Lua runtime messages only, which really do arrive as text.
3. Give the Hades I Save Editor typed keys.
4. Give Hades I its own Time Warp keys, or route them through `HostPresentationError` deliberately.

**Verification**

- `test_hades2_presentation_contract.py`, `test_hades2_error_registry_single_source.py`, `test_error_presentation_behaviour.py` (snapshot), `test_hades2_runtime_error_presentation.py`;
- `test_host_shared_localization_coverage.py`, `test_core_save_protocol.py`;
- the Hades I Save Editor frontend tests.

---

### F8. Operation budgets: two disconnected sources of truth, and nesting that is not verified

- **Severity:** MED-HIGH
- **Category:** drift / hazard

**Evidence [fact]**

**Hades II budget constants are asserted but never used.** `operation_budgets.py:17-19` defines `LUA_BOUNDARY_TIMEOUT_SECONDS=3`, `LUA_EXPRESSION_TIMEOUT_SECONDS=2` and `LUA_CLEANUP_TIMEOUT_SECONDS=3`. Searching for consumers finds only `tests/test_host_watchdog_aggregate_budgets.py`. Production code hard-codes the values instead:

- `transport.py:133,488,491,581` use `time.monotonic()+3`;
- `transport.py:342,349,401` use `expression_timeout_seconds=2.0`;
- `native_mailbox.py:138,142` use `+3`.

The test does arithmetic on the copies. `AGENTS.md` names this pattern as the thing to avoid ("instead of duplicating their current values into prose and testing the copies").

**Hades II command timeouts are typed by hand.** `command_contract.py:778-779` and `:776-777` contain the literals 560, 240, 70 and 85. They are not derived from the budgets (515, 215, 65, 75). The test only asserts `>` (`test_host_watchdog_aggregate_budgets.py:93-94,112-113`).

**Two commands are not covered by the budget test.**

- **`scan`** has a 15 s Host budget (`command_contract.py:659`). It calls `preparation.compatibility()`, which runs `xcrun dwarfdump` with a 30 s timeout (`preparation.py:23,33,54`) and then `pgrep` with 5 s (`adapter.py:727`).
- **`launch`** has a 10 s budget (`:663`). It runs `open` with a 10 s timeout and then the whole of `scan` (`command_contract.py:609-616`).

**Hades I splits its budgets across Swift and Python.**

- Host timeouts are a hand-written Swift switch: `Sources/Hades/HadesModule.swift:771-779` (connect 190, `load_profile` 120, traits 60, locks 55, default 30).
- Sidecar timeouts are separate Python literals: `hades/client.py:13-18` (90/50/22).
- Keeping the inner timeout below the outer one is maintained by hand across two languages.

**Hades II reverses the nesting.** Its sidecar timeout is 30 s (`config.py:36`), while the Host timeout for most commands is 6–15 s. Its comment says this is allowed.

**Why it matters**

When an inner bound exceeds the outer Host deadline, the Host times out first. Core then treats that backend instance as terminal and outcome-unknown. A read-only `scan` can kill a backend [inference: needs a slow `xcrun`, for example a cold cache or a toolchain prompt]. A third game gets two inconsistent patterns to copy and no shared generator.

**Remediation (M)**

1. Make the budget constants the inputs. The transport reads them, and `CommandSpec.timeout` is computed from its components.
2. Add an assertion that "outer > sum(inner worst case)" for **every** command, including `scan`, `launch` and `status`.
3. Generalise `Tools/generate_hades2_command_binding.py` into a module-agnostic generator. Hades I's Swift timeouts are then generated from a backend table.
4. Cache `compatibility()` per (path, mtime) so `scan` stops running a subprocess on every refresh.

**Verification**

`test_host_watchdog_aggregate_budgets.py`, the generated-binding tests, `test_hades_commands.py`, `test_hades_frontend.py`.

---

### F9. Three process-discovery implementations, and a hard-coded Hades II install path (latent user-facing defect)

- **Severity:** HIGH
- **Category:** duplication / stopgap that became a constraint

**Evidence [fact]**

There are three ways of finding the game process:

| Owner | Location | Method | Timeout |
|---|---|---|---|
| Core | `target_probe.py:15-30` | `ps -axo comm=` path suffix or basename | 2 s |
| Hades I | `adapter.py:38-65` | `ps -axo pid=,comm=` + `proc_pidpath` | none |
| Hades II | `adapter.py:727` | `pgrep -x` | 5 s |

Core's own comment warns that pgrep is unreliable: "the kernel name that `pgrep` compares is truncated to MAXCOMLEN and cannot identify long names" (`target_probe.py:12-13`).

Hades II hard-codes the install location:

- `app_path=STEAMAPPS / 'common/Hades II/Hades II.app'` (`config.py:50`; unchanged since the 0.1 baseline `31297c90`, 2026-09-18).
- `scan()` → `compatibility()` reads `GAME/'Contents/Info.plist'`, then the Steam ACF, then runs dwarfdump (`preparation.py:63-73`). On any exception it sets `status='incompatible'` and re-raises (`adapter.py:718-725`).
- `connect` runs `scan()` first (`adapter.py:753-758`).
- `localization.py:43` and `save_investigation.py:245-248` also default to this path.

Hades I instead resolves the running executable through `proc_pidpath` and the manifest's `executablePathSuffix`.

**Why it matters**

[inference] A Hades II install in a non-default Steam library folder (an external drive, for example) is found by bundle id but cannot connect, because `compatibility()` raises. This has not been reproduced. A third game must pick one of three discovery methods, none of which matches the Host's `TrainerTargetProcessMonitor` identity rules exactly.

**Remediation (M)**

Add a Core `locate_target(manifest) -> (pid, executable_path, bundle_path)`. It applies the same identity rules as the Host (bundle id or executable suffix, verified with `proc_pidpath`) and has a bounded timeout.

Hades II then derives `GAME`, localization roots and investigation roots from the **running** process when one is available. When the game is not running, it falls back to Steam `libraryfolders.vdf`.

**Verification**

- `test_core_save_target_probe_macos.py`, `test_hades_process_identity_macos.py`, `test_hades_module.py`, `test_host_target_ownership.py`;
- Hades II scan/connect tests;
- actual-game acceptance with a non-default Steam library.

---

### F10. Core `GameSpec` is a single-consumer abstraction that duplicates manifest facts

- **Severity:** LOW-MED
- **Category:** misplaced ownership / dead code

**Evidence [fact]**

`core/game_spec.py` has one production consumer, `hades2/config.py:45-54`. Its fields duplicate facts that already have owners:

| `GameSpec` field | Duplicates |
|---|---|
| `save_path` | `module.json saveManagement.roots[0].path` |
| `minimum_architecture='arm64'` | `supportedBuild.architecture` |
| `executable_name='Hades II'` | `targetApplication.processName` |

`app_path` is documented as a "Compatibility alias for modules that require a macOS app bundle" (`game_spec.py:49-50`). Its only other user is `tests/test_backend_core_round12.py:111-116`.

**Why it matters**

It breaks the two-adapter rule and the "one source for each fact" rule. A new module may believe it should construct one.

**Remediation (S)**

Delete `core/game_spec.py`. Hades II derives these values from `MODULE_MANIFEST`, plus the runtime path from F9.

**Verification**

`test_backend_core_round12.py` (remove the `GameSpec` case), the Hades II config consumers (`preparation`, `diagnostics`, `localization`, `save_investigation`), `test_supported_build_governance.py`.

---

### F11. GameAdapter contract gaps: implicit hooks, no data directory, untyped extras

- **Severity:** MED
- **Category:** seam

**Evidence [fact]**

**An undeclared `state` hook.** `core/protocol.py:228,234,260` attaches `getattr(self.adapter, 'state', None)` to error replies. Only Hades II defines `.state` (`hades2/adapter.py:136-145`). Hades I and the reference fixture do not.

**No data directory in the context.** `GameAdapterContext` (`core/adapter.py:41-50`) has no `data_dir` or log directory. The path `Library/Application Support/MacGamingTrainer` is therefore built in five places:

- `core/protocol.py:56`;
- `core/log_paths.py:14`;
- `hades/preferences.py:30`;
- `hades/recovery.py:19`;
- `hades2/config.py:59`.

**A second adapter-construction path.** When `context=None`, `Hades2Adapter.__init__` builds its own `GameAdapterContext` (`adapter.py:100-109`) and omits `executable_path_suffix`.

**Save-service binding happens after construction.** `bind_save_service` is called after `__init__` (`core/protocol.py:61`), so adapters cannot use the save service at construction time.

**Hello metadata extras with no consumer.** `steamAppId` and `transport: 'supergiant-lldb-lua'` (`hades2/adapter.py:1096-1102`) are read by no Swift code. A grep of `Sources` finds nothing; only `tests/test_hades2_adapter_round12.py:205` uses them.

**`steamAppId` is unvalidated and parsed twice.**

- Neither `core/module_manifest.py` nor `Tools/*.py` validates it.
- Each game re-parses the raw JSON (`hades/config.py:10-15`, `hades2/config.py:40-44`).
- The two produce different launch URLs: `steam://run/<id>` versus `steam://rungameid/<id>`.

**Save-provider hooks are inverted.** In `save_resolution.py:120-127` and `save_service.py:55-87`:

- `resolve` is required whenever a provider exists, yet both implementations are pass-throughs (`hades/save_provider.py:37-38`, `hades2/save_provider.py:96-98`);
- `restore_busy` and `describe_snapshot` are optional and discovered with `getattr`;
- there is no `Protocol` class;
- the provider is constructed with no arguments (`save_resolution.py:69`), so Hades II's `game_path` parameter is never set in production.

**Why it matters**

These are the places where a new module must read Core code to discover the real contract.

**Remediation (S–M)**

- Add `data_dir` (`<root>/<game_id>`) and `log_dir` to `GameAdapterContext`.
- Either declare `state_for_error()` as an optional documented hook, or drop the `state` attachment.
- Define a `SaveProvider` `Protocol` with a default pass-through `resolve`.
- Pass a provider context (for example the module dir and the runtime game path).
- Validate `steamAppId` in `Tools/validate_game_module.py`, or move it under a typed `distribution` block. Unify the URL form.
- Remove the unconsumed metadata extras.

**Verification**

`test_cross_game_isolation.py`, `test_module_contract_round13.py`, the reference-fixture matrix, `test_core_save_resolution.py`, `test_core_save_service.py`, `test_hades2_adapter_round12.py`.

---

### F12. Diagnostics: two report formats, and a game module parsing the Host's log layout

- **Severity:** MED
- **Category:** duplication / misplaced ownership

**Evidence [fact]**

**Hades I** (`hades/diagnostics.py:10-27`) returns check names as keys, for example `'hades.diagnostics.backend'`. Swift builds the export: `HadesModule.swift:574-599` writes a JSON file with logs through `NSSavePanel`.

**Hades II** (`hades2/diagnostics.py`) does it differently:

- It returns Chinese check names (`add('运行时状态刷新',…)`, `add('协议版本',…)`; :18-89).
- `export_diagnostics` builds its own ZIP in `DATA/diagnostics` (:98-173).
- To do so it parses Host-owned log artifacts: `current-session.json`, `sessions/<id>/manifest.json` and `trainer-host.log` (:108-162). These are written by `Sources/Core/Runtime/TrainerLogSink.swift:137,146`.
- It reaches them through `core/log_paths.trainer_log_directory`.

`core/log_paths.trainer_log_path` (the "legacy flat log path") is used only by `tests/test_core_log_paths.py`.

**Why it matters**

A change to the Host log format now requires a Python game-module change. A third game would choose between a Swift export and a Python ZIP. Hades II's check names are not localizable.

**Remediation (M)**

Make diagnostics export Host-owned in Swift, built on #620's `TrainerDiagnosticsView`. Modules return only `checks` (keys plus arguments) and a `state`. Then delete Hades II's ZIP builder and the test-only `trainer_log_path`.

**Verification**

`test_hades2_diagnostics_log_scope.py`, `test_diagnostics_live_status.py`, `test_diagnostics_read_only_v0190.py`, `test_core_log_paths.py`, `test_hades_management.py`.

---

### F13. `MGT_HADES2_TRANSPORT=lldb` keeps a second execution route and the old unknown-build fallback alive

- **Severity:** MED
- **Category:** stopgap that became a constraint

**Evidence [fact]**

- `transport.py:24-26` selects between `mailbox` (the default) and `lldb`.
- `execute` dispatches to `_execute_mailbox` (:349) or `_execute_lldb` (:401-497, about 100 lines).
- In mailbox mode, an unknown UUID fails at attach through `prepare_command_mailbox` → `load_native_library`, with "Native library requires the supported Hades II image UUID" (`native_library.py:40-41`, `native_mailbox.py:72-74`).
- The name-based symbol fallback for new builds (`transport.py:154-169`) is therefore reachable only through the `lldb` switch.
- Consumers of the switch are `tests/hades2_lldb_fixture.py`, `tests/test_hades2_transport_detach.py` and `Tools/profile_hades2_operations.py`.
- `PROJECT_STATUS.md:33` says mailbox "Native game-process acceptance has not been performed".

**Why it matters**

Two runtime execution paths are maintained without an exit criterion. The fallback path also carries a weaker build-identity policy than the mailbox path (see F1).

**Remediation (S–M)**

Record exit criteria in the owning issue (#499): mailbox acceptance, then remove `_execute_lldb` from production or move it to a fixture. Until then, make `address()` fail closed for unknown UUIDs in both modes.

**Verification**

`test_hades2_transport_detach.py`, `test_hades2_mailbox_protocol.py`, `test_hades2_mailbox_client.py`, real-game acceptance.

---

### F14. The retired `damageEnabled` toggle is still a first-class identity across four layers

- **Severity:** LOW-MED
- **Category:** stopgap that became a constraint

**Evidence [fact]**

The toggle still appears in every layer:

| Layer | Evidence |
|---|---|
| Backend schema | `hades2/schema.py:3-7` keeps it in `TOGGLES` |
| Resident Lua | 15 occurrences in `runtime/hades.lua`, including the generated durable state at :19-58 |
| Generated Swift | `Hades2Feature.generated.swift:10` |
| Swift model | `Hades2Model.swift:165,1948,2303` |

`preferences.py:36-37` says "both keys are always written together". `canonicalize_damage(…, legacy_toggle_veto=…)` (:41-69) and `Hades2Adapter.set_desired` (`adapter.py:548-566`) translate old toggle writes.

A related leftover: `gardenQoL` is retired in `profile_service.py:26` but still listed in `Sources/Hades2/Services/Hades2ShortcutStore.swift:23`.

**Why it matters**

Every new multiplier-backed feature must reason about a derived toggle. The Lua durable state, the profile envelopes and the Swift enum all carry it.

**Remediation (M)**

Make `damageEnabled` a read-only projection at the Swift edge. Remove it from `TOGGLES` and from the Lua durable state; this needs a resident revision bump. Migrate desired-state and profile schemas with old-version refusal.

**Verification**

The Hades II preference and profile migration tests, `Tools/check_runtime_revision.py` / `test_runtime_revision_gate.py`, the generated-binding tests, `test_hades2_model_flow.py`.

---

### F15. Build-dependent content hashes are hard-coded in feature code

- **Severity:** MED
- **Category:** drift risk

**Evidence [fact]**

- `hades2/save_investigation.py:20` hard-codes `_SUPPORTED_STORY_SHA = "58509042…"`.
- The same hash also appears in a comment at `save_native_ids.py:97`.
- `save_native_ids.py:11-15` holds `QUEST_REWARD_OWNER_SHA256`.
- `docs/development/supported-game-build-update.md` mentions neither file.
- `AGENTS.md` says: "Never copy new version/UUID/hash literals into feature code".

**Why it matters**

When the game updates, the dialogue investigation silently refuses or misreports. Nothing in the runbook or in `Tools/supported_build.py` points at these literals.

**Remediation (S)**

Move the installed-source hashes into the `supportedBuild` reference snapshot (`docs/reference/hades2/<build>/`) and read them through the module's reference resolver. Add a `Tools/supported_build.py` check and a runbook step.

**Verification**

`python3 Tools/supported_build.py`, `test_supported_build_governance.py`, `test_hades2_save_dialogue_presentation.py`.

---

### F16. Incident-specific logging sits inside the generic runtime execution path

- **Severity:** LOW
- **Category:** special case

**Evidence [fact]**

`hades2/adapter.py:943-966` contains the WorldActions target-catalog diagnostic logging inside `_execute_runtime`. It was added and adjusted in three commits on 2026-11-17 for #720: `a2f188c1`, `a7f18974`, `c2086450`.

**Remediation (S)**

Move it into a world-action projection helper, or onto the operation-profile channel. Retire it when #720 closes.

---

### F17. Dead or vestigial code and shims

- **Severity:** LOW
- **Category:** dead code

**Evidence [fact]**

- **Unreachable remap in Hades I.** `hades/time_warp_worker.py:10-16` remaps `host.timeWarp.error.*` presentations for the codes `outcome_unknown` and `restart_required`. After `4053ae42` (#744), Hades I does not import Core Process Time Warp, and its only `host.timeWarp` raises use code `time_warp_verify_failed`. The branch cannot be reached.
- **"Shared" module with one consumer.** `Backend/debugger/lldb_time_warp.py` describes itself as "Shared LLDB driver". Its only production consumer is Hades II (`lldb_worker.py:19` and the fallback at `adapter.py:130`), which contradicts `GAME_MODULES.md:77`, under which a concrete debugger driver stays game-owned.
- **Unused adapter fallback.** `hades2/adapter.py:126-133` builds an in-process `ProcessTimeWarpController(LLDBProcessTimeWarpDriver(transport))`. It is used only when the transport lacks `create_time_warp_controller`. The production transport always has it.
- **Compatibility re-exports for tests.** `hades2/adapter.py:41-54` exports `__all__` and aliases `TransportError = AdapterError`, "for established adapter-module consumers. In particular, tests".
- **Test-only Core helper.** `core/log_paths.trainer_log_path` (see F12).
- **Stale comment.** `runtime/hades.lua:1` says "Loaded before every command", but the bootstrap is now sent once per generation (`resident_session.py:293`).

**Remediation (S)**

Delete the dead code. Move `lldb_time_warp.py` under `games/hades2/` or into the F1 debugger package. Fix the comment.

**Verification**

The affected tests, including `test_packaged_module_round14.py:88-91` and `test_ci_pr_macos_selection.py:156`, which reference the path.

---

### F18. `Hades2Adapter` and `command_contract.py` mix non-synchronizing responsibilities into the synchronization boundary

- **Severity:** MED
- **Category:** god module

**Evidence [fact]**

`adapter.py` (1,123 lines) holds eight responsibilities:

1. a public/internal state dict and its projections (`clear_active`, `mark_disconnected`: :56-91);
2. the preference store and profile CRUD (:165-222);
3. a per-command durable lock-capture if-chain (`_capture_command_preferences`, :423-541, about 120 lines). This is separate from the `CommandSpec` table and from the replay in `desired_reconciliation.py`;
4. Time Warp projection and apply (:261-362);
5. process scan and compatibility (:718-751);
6. runtime execution with outcome-unknown handling (:879-1012);
7. Save Editor routing (:1029-1094);
8. metadata (:1096).

`command_contract.py` (845 lines) holds:

- validators for 60 commands;
- the spec table with timeouts;
- presentation translation (:831-845);
- the Save Editor workspace and baseline gate (:808-816);
- subprocess side effects (`open -R` at :600, `open steam://` at :609);
- stopped-operation orchestration (:619-626).

**Why it matters**

Adding one lock family touches several places:

- `schema`;
- preferences `normalize`;
- adapter capture;
- `desired_reconciliation` replay;
- the `CommandSpec` validator;
- Lua.

None of these declare that they belong together. The 2026-09-21 audit kept the adapter whole because it is the synchronization boundary, and that reasoning still holds for items 1, 2, 4 and 6.

**Remediation (M)**

Keep the synchronization core and extract only what does not synchronize:

- Save Editor routing → the F5 registry;
- scan and compatibility → F9;
- diagnostics and launch side effects → F12;
- durable capture → a declarative `durable_capture` field on `CommandSpec`, placed next to the matching reconciler replay.

**Verification**

`test_hades2_model_flow.py`, `test_hades2_preference_replay_batch.py`, `test_hades2_adapter_round12.py`, the resident reconciliation tests.

---

### F19. Hades II Save Editor modules mix parsing, query, staging and presentation

- **Severity:** MED
- **Category:** god module

**Evidence [fact]**

`save_workspace.py` (1,904 lines) covers:

- the workspace lifecycle (F5);
- resource and player-stat descriptors;
- discovery search (:575-838);
- narrative investigation (:840-880);
- entity query (:882-996);
- batch staging validation with localized error presentation (:1301-1350);
- linked-effect presentation (:1372-1473);
- apply with continuity of drafts (:1838-1904).

It imports nine sibling `save_*` modules (:13-21).

`save_investigation.py` (874 lines) covers:

- a hand-written Lua tokenizer and table parser for the installed game scripts (:29-160);
- the SHA pin (F15);
- probing installation layout (:245-260);
- semantic query and presentation (:476-874).

**Why it matters**

Query and presentation code is welded to lifecycle code. A third game would be tempted to copy the lifecycle and get the Hades II semantics along with it.

**Remediation (M)**

After F5, `Hades2SaveWorkspace` becomes a domain facade. Move investigation parsing into its own reader module.

**Verification**

`test_hades2_save_workspace.py`, `test_hades2_save_editor_player_journey.py`, `test_hades2_save_dialogue_presentation.py`, `test_hades2_save_editor_summary_contract.py`.

---

### F20. The single-file resident Lua constraint is encoded in tooling, not in the game

- **Severity:** MED
- **Category:** stopgap that became a constraint

**Structure [fact]**

- `runtime/hades.lua` is 12,753 lines inside one `if __MacGamingTrainerV1 == nil then local M = {…} … end` chunk.
- It has 543 local functions and about 16 `(function() … end)()` factories. The top-level ones are `M.observationRetention` :125, `M.castControl` :697, `nativeOperations` :1545, `M.catalogProjection` :1806, `traitManagement` :3146, `M.gardenMaturity` :8302, `M.rerollCurrency` :10982 and `rewardAcquisition` :11522.
- Those factories exist to stay under Lua 5.2's 200-local limit. That limit is enforced by `tests/lua_local_reserve.py` with `test_hades2_runtime_local_reserve_probe.py` and `test_hades2_runtime_compile.py`, which look for `"too many local variables (limit is 200)"`.
- `Tools/generate_hades2_feature_bindings.py` splices four generated blocks into the hand-written file (:19, :41, :8545, :12440).
- Dispatch is a roughly 540-line `if command == …` chain (`M.dispatch` :12193 to `dispatchBatch` :12729).
- The revision number is written twice: `previousModule.revision ~= 140` (:9) and `revision = 140` (:18). The gate checks that the two agree (`check_runtime_revision.py`).

**Where the constraint actually lives [fact]**

- `residentRuntime.source` must be a single string (`Tools/resident_runtime.py:47-62`).
- The gate runs `git diff --quiet` on exactly one path (`check_runtime_revision.py:141`).
- Provenance hashes the single declared source (`GAME_MODULES.md:31`).
- `Hades2ResidentSession` reads one file (`resident_session.py:126`).
- The bootstrap travels as one string through the mailbox or LLDB (`resident_session.py:293`).

**Why it matters**

[inference] `ENGINEERING_INVARIANTS.md` §6 asks for real-game proof before adopting a multi-file **loading** route, and that is right for runtime `require` or multiple load calls. Assembling N source files deterministically into **one** chunk at build or session time keeps the loaded artifact a single string. That may need much weaker proof: byte-identical assembly and the existing compile and local-reserve probes.

Today, every edit anywhere in a 12.7k-line file needs a hand revision bump, an awareness of the local budget, and care to avoid the generated blocks. The same "previous module cleanup + revision" protocol is also hand-written in Hades I's `runtime.lua`, so a third Lua game copies it again.

**Remediation (M)**

1. Allow an ordered list in `residentRuntime.sources`, or an assembly manifest.
2. Assemble deterministically in `Tools/` and in `Hades2ResidentSession`. The gate and provenance hash the **assembled** text.
3. Generate both revision literals from one declaration.
4. Keep the local-reserve probe per factory.
5. The first step can be a byte-identical split: assemble, diff against the current file, and confirm zero difference. That step needs no real-game acceptance; later restructuring does.

**Verification**

`test_runtime_revision_gate.py`, `test_resident_runtime_manifest_validation.py`, `test_build_provenance_contract.py`, `test_hades2_runtime_compile.py`, the local-reserve probe, real Hades II bootstrap acceptance once the assembled bytes differ.

---

### F21. Blocking or unbounded I/O on request paths

- **Severity:** MED
- **Category:** hazard

**Evidence [fact]**

Subprocess calls on request paths without a timeout:

- Hades I `_locate_process`: `subprocess.check_output(['/bin/ps', …])` (`adapter.py:39`);
- `process_identity`: `subprocess.run(['/bin/ps', '-p', …])` (`recovery.py:11`);
- `launch`: `subprocess.run(['/usr/bin/open', …], check=True)` (`adapter.py:139`).

Other repeated or heavy work:

- Hades I fsyncs a journal write and unlink on every status call (F3).
- Hades II `scan` runs `xcrun dwarfdump` on every call, with no caching (`preparation.py:54`; F8).
- Hades II Save Editor inventory fully decodes every candidate profile save just to decide whether to list it (`save_workspace.py:194-197` → `save_provider.editor_files(source_bytes=…)` → `Hades2SaveDocument.from_bytes`).

Global state is bounded or keyed: `_NATIVE_CACHE` holds at most 2 entries (`save_investigation.py:464-474`). `_OFFICIAL_TEXT_CACHE` is keyed by (game path, language) and has no invalidation when the game updates.

The backend is single-threaded; a search found no `threading` imports, so thread safety is not a current concern.

**Why it matters**

When a call has no timeout, the Host deadline is the only bound. Hitting it is terminal for the backend (Core §3).

**Remediation (S–M)**

- Add a Core `bounded_run(argv, budget)` helper that maps a timeout to a typed error. It feeds F8.
- Cache compatibility per (path, mtime).
- Admit Save Editor sources lazily, for example by header parse only.

**Verification**

`test_hades_module.py`, `test_hades2_save_editor_command_contract.py`, the budget test.

---

## Severity summary and suggested order

| Order | Findings | Why first | Size |
|---|---|---|---|
| 1 — quick, low risk | F10, F15, F16, F17 | Single-source fixes and deletions; no behaviour change | S each |
| 2 — Core seams that new modules consume | F11 (`data_dir`, explicit hooks, `SaveProvider` `Protocol`), F5 (save-edit session and workspace registry), F9 (target locator), F8 (budgets and generator), F4 (profile store) | These decide what a third module copies versus imports; each has two real adapters today | M each |
| 3 — debugger/sidecar consolidation | F1, F2, F3 | Highest drift risk, but needs real-game attach/detach acceptance for both games | M–L |
| 4 — Hades II internal paydown | F7, F18, F19, F14, F13, F12, F20 | Reduces the cost of Hades II changes; F7 and F20 can proceed one module or step at a time | M–L |
| Optional | F6 | Only if another Supergiant title is planned | S–M |

## Facts versus inference

**Confirmed from source or git:**

- every file:line citation;
- the `save_edit.py` identity diff;
- the SIGCONT asymmetry;
- the different unknown-UUID policies;
- the budget constants that no production code uses;
- the hard-coded Steam path;
- the Python code that parses the Host log layout;
- the Lua structure and its tooling;
- the per-pair commit counts;
- the 110,155-byte Hades I status payload (measured).

**Inference, not reproduced:**

- whether the Hades I SIGCONT gap matters in practice (F1);
- whether SIGTERM bypassing Hades II worker cleanup can leave the game stopped (F2);
- the non-default Steam library failure (F9);
- `scan`/`launch` hitting the Host timeout (F8);
- the memory growth from unbounded workspaces (F5);
- the possible collision between root-level directories and future module ids (F4);
- the attribute loss in presentation wrapping (F7);
- that build-time Lua assembly needs weaker real-game proof than runtime multi-file loading (F20).
