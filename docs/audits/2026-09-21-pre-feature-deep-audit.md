# Pre-feature deep audit

Updated: 2026-09-21

Branch: `audit/pre-feature-deep-review-20260920`
PR: #40
Original audit baseline: `efa14e984dd619cc1db859047fe986469838d27f`
Original verified code baseline: `9b15d8393918ceab8de89688d1d08dcaef89dfa1`
Current merge base during final review: `6e1069dd9ff69283f132b5edfacf07d638db3160`

New product work remained frozen throughout this audit. Changes are limited to demonstrated defects, shared-component reuse, audit/CI support, tests and documentation.

## Executive result

Segments A-F are complete. Segment G final merge verification is pending the latest full CI run.

Confirmed Important defects fixed in this audit:

1. target-process exit while a Host request was busy could lose the only exit refresh and leave stale connected UI state;
2. a Lua boundary whose result became unknowable during host-side result read did not taint the transport, allowing later queued Lua mutations to continue;
3. Core Save restore used a stale stopped/running decision, so the game could launch between the initial probe and real-save mutation;
4. staged restore / normal restore did not treat SIGTERM -> KeyboardInterrupt and hard process loss conservatively enough across every mutation path;
5. one-shot next-room reward persistence could resurrect and replay an already-consumed reward after backend restart;
6. runtime teardown could be blocked by a durable-state write error even though resident hooks still needed best-effort cleanup.

No cross-game architecture breach or unique unmerged product behavior was found in historical MacGamingTrainer branches.

## Segment A — repository and evidence integrity

Status: complete.

### Baseline evidence

The original merged-code baseline `9b15d839...` was rechecked:

- Linux contracts run `35515313374`: PASS.
- Module matrix run `35515313389`: Hades II PASS; reference fixture PASS.
- Build 2 macOS run `35515313401`: full contract suite/build/package/artifact PASS.

`Tools/run_macos_checks.sh` enumerates `tests/test_*.py`, so every repository test file participates in the exhaustive macOS contract gate. Linux contracts intentionally run a curated cross-platform subset.

### Remote branch classification

Strictly behind main / no unique product files:
- `audit/preacceptance-hardening`
- `feature/generic-speed-control-ui`
- `feature/post-v0.1-improvements`
- `fix/batch-a-native-modals`
- `fix/batch-b-runtime-semantics-r40`
- `fix/special-choice-native-r39`
- `fix/special-choice-refresh-r38`
- `refactor/save-management`
- `spike/generic-process-time-warp`
- `spike/generic-process-timewarp`

Squash-merged / absorbed by later main commits:
- reference-module proof -> `d084f383...`
- Process Time Warp / mapped slider -> `8d99d743...`
- append-only trainer log -> `4eab391e...`
- proactive runtime reset -> `72d8c8c0...`
- deferred launch probe -> `07493f1b...`
- deferred-log availability guard -> `b65126df...`
- shortcut Profile collision v2 -> `7471edf9...`
- Save rollback recovery -> `347480ac...`
- Save storage containment -> `40f73d79...`
- empty-save error distinction -> `dc565f59...`
- invalid snapshot row sanitization -> `9b15d839...`

Superseded and must not be restored:
- `fix/profile-shortcut-partial-conflict` (replaced by v2);
- old `maintenance/*` status branches.

Unrelated repository contamination:
- `ci/lidkeep-rc1-build` is unrelated to MacGamingTrainer and must never merge into main.

The connector exposes no safe branch-delete mutation, so stale refs were classified but not physically deleted. Repository transport policy forbids working around that through container network access or RDC.

### Documentation conflicts corrected

- removed deleted `NEXT_PHASE_TODO.md` as a current execution source;
- retired stale LLDB profiling and reference-fixture TODOs;
- clarified that Core UI may own neutral visual composites without owning Hades business semantics.

## Segment B — architecture and duplicated ownership

Status: complete.

Findings:
- App creates one shared `TrainerBackendSession`; Host and Hades model share it.
- Core/Host contains no Hades business-state branch discovered by this audit.
- Hades protocol validation/routing remains in `Hades2CommandRouter`; profile, diagnostics, catalog and persistence services remain game-local.
- the permanent `reference_fixture` continues to enforce the second-module boundary.
- shared UI controls consume neutral bindings/booleans/callbacks; Hades still owns the meaning of supported/available/locked/resource/boon state.
- Hades did not retain a second native Toggle/Slider implementation.

A small UI cleanup replaced remaining bespoke number/primary-action styling with the existing shared `TrainerNumberField` / `TrainerPrimaryActionButton`. This is reuse, not a new UI abstraction.

No Important architecture defect remains open.

## Segment C — lifecycle, transport and concurrency

Status: complete.

### C1. Target exit lost while busy

Root cause:
`TrainerHost` refreshed on target stop only when the model was not busy. If the game exited during a non-runtime request such as `list_profiles`, the stop refresh was skipped; when busy later cleared, automatic reconcile had no memory that an exit refresh was still owed.

Fix:
- `TrainerConnectionPolicy` owns one-shot `targetExitRefreshRequested` state;
- all target-exit refresh consumption is centralized in `reconcileAutomaticConnection()`;
- the direct stop-callback refresh path was removed to avoid double refresh.

Evidence:
- RED tests: `test_host_connection_policy_dev8.py`, `test_target_exit_refresh_contract.py`;
- fixes: `cf099cbe...`, `cdc25cab...`;
- focused container tests: PASS.

### C2. outcome_unknown transport remained reusable

Root cause:
`EvaluateExpression` failure tainted the LLDB transport, but a later `ReadCStringFromMemory` failure raised the same `outcome_unknown` code without setting `tainted=true`. The JSONL request could fail while later queued mutations still crossed the same debugger/Lua boundary.

Fix:
every host-side result-read `outcome_unknown` now taints the transport. A later boundary fails with `restart_required`.

Evidence:
- RED/GREEN test: `test_hades2_transport_outcome_unknown_taint.py`;
- fix: `41b52638...`;
- focused container test: PASS.

### C3. teardown with durable-state write failure

A forward-schema / persistence error must not prevent best-effort resident hook cleanup. `disable_all/cleanup` now records the persistence error, still attempts runtime teardown, then surfaces the durable-state error without pretending the durable reset succeeded.

Evidence:
- fix `585c54ef...`;
- `test_exit_semantics.py` and forward-schema teardown coverage;
- focused/current CI coverage passes through this path.

No automatic replay of native modal/outcome-unknown mutations was found.

## Segment D — persistence and Core Save safety

Status: complete.

### D1. SIGTERM / hard-loss staged restore safety

The backend converts SIGTERM to `KeyboardInterrupt`. Restore mutation now catches the full control-flow path after mutation starts, attempts rollback before process termination, and preserves the rollback directory if rollback itself cannot be proven.

Staged restore claims now use explicit applying/applied marker states:
- a surviving applying marker is indeterminate and is never auto-replayed;
- it blocks new staging and backup deletion until explicit user action;
- successful commit acknowledgement moves applying -> applied before best-effort cleanup;
- the UI surfaces indeterminate state as warning, not a normal pending restore.

Evidence:
- fix `c6befb32...`;
- expanded `test_core_save_restore.py`, `test_core_save_service.py`, Swift model/UI contracts;
- focused container tests: PASS.

### D2. target launches during cold restore

Root cause:
`CoreSaveService.restore()` took one process-running snapshot and passed a static boolean into the transaction. The game could launch after that check but before real-save replacement.

Fix:
`SaveRestoreTransaction` receives the generic running probe and rechecks before/after rollback capture and immediately before mutation. A target that starts during a cold restore raises `SaveBusyError`; the service stages the restore when the module supports staged restore.

Evidence:
- RED tests: `test_core_save_running_transition.py` and service scenario;
- fixes: `0278a73c...`, `a9be00d6...`;
- focused container tests: PASS.

### D3. containment / integrity

Snapshot, staged metadata, rollback transaction and game-save destination containment remain fail-closed against the tested symlink/path escapes. Snapshot manifests and file hashes are reverified.

Minor hardening notes, not blockers:
- some Core rename paths do not parent-directory fsync after `os.replace`; this is an extreme power-loss durability ceiling, not a demonstrated logical replay/data-loss bug;
- Hades local Profile storage does not apply the same explicit subdirectory symlink guard as Core Save storage. It runs with the same user authority and no privilege boundary; record as future local-filesystem hardening only.

## Segment E — Hades II command/runtime semantics

Status: complete.

Command classification was rechecked:
- durable desired state is replayable;
- direct resource/reroll/spawn/native-modal actions use request-id / resident action ledger where required;
- `open_sell_traits`, `open_special_choice`, and reward spawning are not part of durable preference replay;
- native modal commands remain one-shot.

### E1. consumed next-room reward resurrected after backend restart

Root cause:
Lua correctly consumed `M.nextRoomReward` on room entry, and the adapter cleared durable state on a later clean status. If the backend process died after consumption but before that clean status, the durable value survived and a new backend could replay the already-consumed one-shot.

Fix:
- desired-state schema 3 -> 4;
- each armed next-room reward has a durable token;
- resident revision 42 tracks the active token and the last consumed token;
- restart status can prove whether the exact durable one-shot was consumed before deciding to clear or replay it;
- loading a Profile with a one-shot always mints a fresh token so an older consumption receipt cannot consume a newly loaded Profile intent;
- runtime source revision bumped 41 -> 42 as required.

Evidence:
- RED/GREEN `test_next_room_reward_restart_semantics.py`;
- fixes `806a0186...`, `c91b2817...`, `a6c33a60...`, `ff923f9d...`;
- schema/revision/static contracts updated;
- focused container tests: PASS.

## Segment F — shared UI, hotkeys and observable state

Status: complete.

Findings:
- global hotkey registration remains Core-owned in `GlobalHotkeys`;
- Hades owns action semantics/default layout/Profile overrides only;
- shortcut Profile collision/reflow logic remains single-source in `Hades2ShortcutStore`;
- BackendClient delivers `onReply` before request completion, so hotkey success/deferred/disabled feedback reads newly applied model state rather than stale state;
- mapped slider drag preview updates `gameSpeedPreview` only; backend `gameSpeed` mutation occurs after slider commit/input change, preserving the previously accepted preview/commit separation;
- no second backend client/session owner exists in Hades.

Focused UI/input tests run from the CI source snapshot:
- mapped slider: PASS;
- shared UI boundary: PASS;
- toggle unification: PASS;
- Profile shortcut schema/chord semantics: PASS;
- hotkey feedback: PASS;
- post-v0.1 feature contracts: PASS;
- Host cleanup contract: PASS.

No new Critical/Important issue was found in Segment F.

## Segment G — final verification

Status: pending latest CI.

Current PR branch is based directly on the latest main observed during final review:
- main / merge base: `6e1069dd9ff69283f132b5edfacf07d638db3160`;
- branch was `ahead` and `behind=0`; no upstream conflict was present.

Latest successful evidence before the final schema-assertion cleanup:
- Linux contracts on `b5f63ca...`: PASS (`35525691455`);
- module matrix on `b5f63ca...`: PASS (`35525691471`);
- macOS Build 2 reached `test_user_reported_fixes_dev7.py` and failed only on a stale `DESIRED_STATE_SCHEMA_VERSION == 3` assertion after all earlier tests passed.

That assertion is corrected in `304d8597...`. Final PASS claims must use fresh CI for that SHA or a later final SHA.

### Merge hygiene still required

Before merge:
1. obtain fresh Linux + module-matrix + macOS Build 2 success on final code;
2. update this report and `PROJECT_STATUS.md` with final evidence;
3. remove the temporary `.github/workflows/audit-source-snapshot.yml` so it does not enter main;
4. re-run final CI after that removal;
5. re-compare with main and perform final diff review;
6. merge only with all Critical/Important findings closed.

After merge, create a fresh exact-main source snapshot and perform the separate Linux code review requested by the user.
