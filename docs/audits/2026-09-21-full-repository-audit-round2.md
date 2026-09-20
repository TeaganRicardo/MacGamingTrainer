# Full repository audit — round 2

Updated: 2026-09-21

Audit branch: `audit/full-review-20260921`
Repair PR: #41

## Scope and evidence rule

This audit was requested after the earlier pre-feature audit and deliberately did not treat green CI as a sufficient conclusion.

The review covered:

1. repository / evidence integrity;
2. Framework boundary ownership;
3. lifecycle / transport / concurrency;
4. Save / persistence safety;
5. Hades II runtime and command semantics;
6. UI / hotkey / observable state;
7. exhaustive test / CI / macOS build-package verification.

Product review baseline:
- latest product main at the start of the final replay: `ee258442f89a1e3ad4cb04f02bbfc7146488e148`;
- later main movement to `1f8d89f7fc0cf13e716ff97b94b1d81381d8d933` was documentation-only and was merged into the audit branch with a real two-parent merge commit;
- final branch comparison before documentation closeout: `ahead`, `behind=0`.

Exact product source was materialized through GitHub Actions, with an exact commit marker and SHA256, rather than reconstructed from selective file reads.

## 0. Repository and evidence integrity

### Remote branch audit

Every remote branch visible to the repository was classified.

#### Active audit work

- `audit/full-review-20260921` — current repair/audit branch only.

#### Fully contained by main / strictly behind

These had no unique commits/files relative to main and are not execution bases:

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

#### Historical audit evidence, not missing product code

- `audit/post-fix-linux-review-20260921` — corrected-main source/review evidence; its current file tree is already represented on main.
- `audit/fix-future-schema-runtime-cleanup` — its forward-schema teardown regression is already present on main.
- `audit/fix-save-target-probe-fail-closed` — equivalent implementation/regression is already on main via `6e1069dd...`.
- `audit/fix-staged-restore-marker` — older, weaker staged-claim implementation; current main contains the stronger applying/applied/indeterminate model and must not be downgraded.
- `audit/post-merge-linux-review-20260921` — temporary source-snapshot workflow evidence only.
- `audit/pre-feature-deep-review-20260920` — PR #40 audit history; squash-merged into main.

#### Branches identical to current main

- `audit/ai-governance-20260921`
- `governance/ai-development-audit-20260921`

Both compared identical to main and contain no unique product or documentation delta.

#### Squash-merged / superseded implementation branches

Git commit ancestry still reports divergence because these were squash-merged or replaced by stronger later commits. Their product intent is represented on main:

- `architecture/reference-module-proof`
- `architecture/reference-module-proof-v2`
  - represented by the permanent reference fixture / cross-game proof in `d084f383...`.
- `feature/game-speed-r41-integration`
- `feature/mapped-speed-slider`
- `feature/process-time-warp-host`
  - represented by the Process Time Warp + mapped-slider squash in `8d99d743...`.
- `fix/append-only-shared-trainer-log` -> `4eab391e...`.
- `fix/proactive-runtime-reset-bootstrap` -> `72d8c8c0...`.
- `fix/defer-launch-runtime-probe` -> `07493f1b...`.
- `fix/deferred-log-availability-guard` -> `b65126df...`.
- `fix/profile-shortcut-partial-conflict-v2` -> `7471edf9...`.
- `fix/profile-shortcut-partial-conflict` — superseded by the v2 fix and must not be restored.
- `fix/save-rollback-recovery-path` -> `347480ac...`.
- `fix/save-storage-root-containment` -> `40f73d79...`.
- `fix/save-empty-error-code` -> `dc565f59...`.
- `fix/invalid-snapshot-row-sanitization` -> `9b15d839...`.
- `fix/post-merge-review-save-completion` — PR #42 historical repair branch; its callback-completion fix and tests are squash-merged in `ee258442...`.

#### Historical documentation-only branches

These contain older status/handoff material, not current product behavior:

- `maintenance/current-status-20260920`
- `maintenance/repo-hygiene-20260920`
- `maintenance/status-after-lifecycle-fixes`
- `maintenance/status-after-log-qa`
- `maintenance/status-after-save-hardening`

#### Unrelated repository contamination

- `ci/lidkeep-rc1-build` contains LidKeep workflow/source payloads, not MacGamingTrainer product code. It must never be merged into main.

Conclusion: no real unmerged MacGamingTrainer product implementation was found in the historical remote branches.

The connector still does not expose a safe delete-ref action. Branches were therefore classified rather than deleted; repository transport policy forbids deleting them through container network access or RDC.

### CI and test discovery

- `Tools/run_macos_checks.sh` enumerates every `tests/test_*.py`, so the macOS exhaustive gate cannot silently omit newly added tests.
- `.github/workflows/build2-macos.yml` calls that exhaustive runner before build/package.
- Linux contracts intentionally use a curated cross-platform subset.
- `tests/test_test_suite_discovery.py` asserts the exhaustive macOS discovery contract.
- PR #42 added `test_core_save_swift_model_round20.py` to the permanent Linux subset after the unavailable-backend completion defect was found.
- this round adds `test_core_save_service.py` to the permanent Linux subset so interrupted-rollback recovery discovery is continuously covered on Linux.
- the module matrix still builds Hades II and the permanent reference fixture independently and verifies one-module package isolation.

### Handoff consistency

At the start of this round:
- `PROJECT_STATUS.md` had advanced to the corrected PR #42 baseline;
- roadmap issue #8 still described the older PR #40 / `c2fe74c2...` review and incorrectly exposed Save Editor design as the current gate.

That is a real evidence/handoff inconsistency. It will be closed together with this repair so the canonical status and roadmap point to the same reviewed baseline.

## 1. Framework boundary audit

Result: no new Critical/Important boundary violation.

Evidence:
- no live Hades business token was found in `Backend/core` or `Sources/Core` after comment-only lines were excluded;
- Core/Host owns the shell, target-process monitor, backend session, generic save manager, shared UI primitives and global hotkey registration;
- exactly one `TrainerBackendSession()` constructor exists, in `Sources/App.swift`;
- Hades II maps the generic Host protocol to game commands but does not own a second backend process/session;
- Process Time Warp has one Core controller/driver owner and is consumed by Hades as shared infrastructure;
- `TrainerMappedSlider` is Core-owned and reused from Hades;
- global Carbon hotkey registration is Core-owned; Hades owns only Hades action semantics, layout/defaults and Profile override persistence;
- no second private Toggle/Slider implementation was found in Hades.

The existing raw Hades text fields are ordinary search/profile-name inputs and do not justify another shared abstraction.

## 2. Lifecycle / Transport / Concurrency audit

Result: no new Critical/Important defect after including the concurrent PR #42 fix.

Reviewed paths:
- attach -> ready -> reset -> reattach -> exit;
- same-PID runtime reset;
- backend restart;
- request timeout and worker termination;
- mutation queue ordering;
- mutation replay.

Key conclusions:
- target exit while Host is busy preserves one deferred exit refresh;
- same-PID reset invalidates pending Hades mutations and invalidates runtime-generation bookkeeping without a second debugger attachment;
- missing resident runtime generation is auto-recovered only for a read/status bootstrap in the same attachment; mutations are not blindly replayed;
- `BackendClient` has one FIFO request boundary; coalescing applies only to queued same-key work;
- request timeout terminates the backend and completes outstanding requests rather than replaying an outcome-unknown operation;
- LLDB result-read uncertainty taints the transport and forces restart;
- Hades delayed mutation flush feeds the same FIFO before Profile/barrier operations, so a flush cannot be overtaken by a later save-profile request;
- barriers invalidate delayed mutations;
- no periodic Lua/LLDB status polling was found.

Concurrent main fix reviewed:
- `ee258442...` completes Save Manager callbacks with failure when the backend is already unavailable;
- this correctly closes optimistic rename / sequential batch-delete state and does not introduce a new retry owner.

## 3. Save / Persistence audit

Reviewed:
- snapshot;
- restore;
- rollback;
- staged restore;
- symlink containment;
- atomic replacement;
- process-state TOCTOU;
- failure recovery.

Existing protections remain valid:
- real save resolution rejects symlink roots/files and unsafe relative paths;
- snapshot creation verifies pre-copy/post-copy hashes and file set;
- manifests verify size/hash and snapshot IDs/paths;
- cold restore rechecks target-process state before real mutation;
- restore writes through same-directory temporary files + `os.replace`;
- rollback captures a verified copy before mutation;
- staged restore uses a claimed applying marker and fails closed on indeterminate outcome;
- `SaveRollbackError` and raw control-flow interruption preserve applying state instead of converting it to auto-retry;
- Trainer-owned save storage is contained under the configured data root;
- target-process query failure is treated as unknown/busy, not “game stopped.”

### Important finding — preserved rollback bytes could become invisible after forced backend death

Root cause chain:
1. Save Manager Core requests use a 15-second timeout.
2. backend stop first sends SIGTERM; the Python server converts SIGTERM to `KeyboardInterrupt`.
3. once restore mutation has started, `SaveRestoreTransaction` attempts rollback before re-raising.
4. BackendProcess can SIGKILL the still-running worker after its grace interval.
5. if that second termination hits rollback itself, the `.rollback-*` directory remains on disk, but no `rollback_failed` JSON reply can be emitted.
6. after restart, `CoreSaveService.list_state()` previously returned only snapshots and pending staged restore. The preserved recovery bytes therefore existed but were invisible to the Save Manager.

Reproduction on exact current-product main:
- force target install to fail after one real replacement;
- interrupt the subsequent rollback replacement;
- live save set becomes partially target/partially previous;
- `transactions/.rollback-*` remains and contains the prior bytes;
- a new `CoreSaveService.list_state()` exposed no recovery path.

RED evidence:
- Core service regression failed with missing `recoveryPaths`;
- Swift model contract failed because no observable recovery collection existed;
- Save Manager UI contract failed because no persistent recovery warning/reveal surface existed.

Fix:
- Core Save enumerates only contained, non-symlink Trainer-owned `transactions/.rollback-*` directories;
- generic Core state exposes them as `recoveryPaths`;
- shared Save Manager model stores them as observable state;
- Save Manager displays a persistent warning, copyable paths and Finder reveal;
- no auto-restore and no auto-delete were added.

This keeps failure recovery fail-closed and game-agnostic.

## 4. Hades II runtime / command semantics audit

Result: no new Critical/Important command-class mismatch.

Classification:

### Query / lifecycle
Examples: scan, connect, status, diagnostics, list_profiles, metadata/status reads.

- no mutation replay is required;
- status may re-bootstrap a missing resident runtime once in the same debugger attachment.

### Durable desired state
Examples:
- feature desired toggles/multipliers;
- boon-rarity desired state;
- lock snapshots;
- next-room desired reward.

- persisted before runtime application where required;
- reconnect replay is deliberate;
- next-room reward uses durable token + resident consumed-token receipt (schema 4 / runtime revision 42) to avoid resurrection after backend restart.

### Direct/idempotency-protected mutation
Examples:
- set_resource;
- set_rerolls;
- spawning supported rewards where action ledger is used.

- external request IDs are injected;
- resident action ledger rejects an indeterminate duplicate and recognizes completed duplicates;
- Host/backend timeout code does not automatically retry an outcome-unknown mutation.

### Native one-shot modal
Examples:
- open_sell_traits;
- open_special_choice.

- request-ID action ledger protected;
- not included in durable preference replay;
- no reconnect/backend-restart auto replay.

`lock_resource` / `lock_rerolls` participate in durable desired-state reconciliation rather than automatic request retry. No unsafe replay path was found.

The resident action fingerprint does not include every possible native-modal parameter, but the outer JSON request cache rejects reuse of the same request ID with different payload before Lua, and internal callers do not reuse native-modal IDs. No reachable duplicate-conflict defect was demonstrated, so no speculative change was made.

## 5. UI / Hotkey / Observable state audit

Result: no new Critical/Important defect.

- shared UI control ownership remains in Core/UI;
- Hades uses shared Toggle/mapped slider/number/primary controls where applicable;
- shortcut collision detection covers direct assignment and partial Profile imports;
- Profile import allows explicit imported assignments to displace conflicting local overrides and recomputes unassigned defaults;
- Carbon registration failures surface system/external-app conflicts to the user;
- BackendClient applies replies before completion callbacks, so hotkey feedback reads updated active/deferred state;
- backend termination clears connection/pid/capabilities/active runtime state;
- durable desired state intentionally persists across disconnect/restart and is not mistaken for runtime-active state;
- game-speed drag preview and committed backend value remain separate.

The concurrent PR #42 completion fix was specifically re-reviewed because it touches observable optimistic state; its completion contract is now total.

## 6. Static integrity review

On the repaired tree:
- Backend compileall: PASS;
- all live Swift source files frontend-parse: PASS;
- Python duplicate top-level/class definition scan: clean;
- Git conflict-marker scan: clean;
- live TODO/FIXME/HACK/XXX scan: clean;
- risky execution primitive scan: no production `shell=True`, `os.system`, dynamic `eval/exec`, pickle or unsafe YAML loader;
- Core/Hades business-token boundary scan: clean after comments are excluded;
- exactly one backend session constructor;
- resident runtime revision references consistently use 42;
- desired-state schema references consistently use 4.

Broad exception handlers and destructive filesystem operations were manually reviewed. They either log/rethrow, quarantine, fail closed, or are diagnostics/cleanup boundaries; no new mutation-success swallowing path was found.

## 7. Test / CI / macOS verification

### Local exact-source verification after the new recovery fix

- domain-focused Core Save tests: PASS;
- lifecycle/transport tests: PASS;
- Hades command/runtime tests: PASS;
- UI/hotkey tests: PASS;
- `Tools/run_linux_checks.sh`: PASS / exit 0;
- all 85 `tests/test_*.py` entrypoints attempted:
  - 81 PASS on Linux;
  - four Linux platform-only compile failures (AppKit/Darwin), no business assertion failure:
    - `test_core_save_batch_delete_round20.py`;
    - `test_core_save_rename_completion_round24.py`;
    - `test_hades2_run_log_watcher.py`;
    - `test_trainer_log_sink_shared_append.py`.

### First repair PR CI

Repair head `e2959626209fdcc1665c376cf36b93a8c2a959d2`:
- Linux contracts `35528506356`: PASS;
- module matrix `35528506352`: PASS;
- Build 2 macOS `35528506442`: PASS.

The end-to-end regression was then strengthened to reproduce target-write failure followed by rollback interruption, and `test_core_save_service.py` was added to the permanent Linux gate.

### Final merge-candidate CI

Final tested product/test head:
`d4b1bbb1d5215b59e95ebae46cf021def16657c8`

Temporary source-snapshot workflow was removed before this final candidate.

Fresh evidence:
- Linux contracts `35528849520`: PASS;
- module matrix `35528849519`: PASS; Hades II and reference fixture both build and package in isolation;
- Build 2 macOS `35528849516`: PASS; exhaustive test suite, Hades II build, package verification and RC artifact upload all succeeded.

The final macOS log explicitly records PASS for:
- `test_core_save_service.py` -> `core_save_service_ok`;
- `test_core_save_swift_model_round20.py` -> `core_save_swift_model_round20_ok`;
- `test_core_save_ui_round20.py` -> `core_save_ui_round20_ok`;
- the four Linux platform-only tests:
  - `core_save_batch_delete_round20_ok`;
  - `core_save_rename_completion_round24_ok`;
  - `hades2_run_log_watcher_ok`;
  - `trainer_log_sink_shared_append_ok`.

## Remaining non-blocking hardening ceilings

Unchanged Minor notes:
- selected directory metadata updates are not parent-directory-fsynced after every `os.replace`; this is an extreme sudden-power-loss durability ceiling, not a demonstrated replay/logical corruption path;
- Hades Profile storage does not use Core Save's full explicit subdirectory-symlink containment. It runs with the same user authority and no privilege boundary; no concrete exploit/data-loss path was demonstrated in this audit.

## Current verdict

One new Important product defect was found and repaired: persistent discovery of preserved rollback recovery copies after the backend dies during rollback.

No other Critical/Important product defect or real unmerged historical branch implementation was found.

The repair is **ready to merge**:
- temporary audit workflow is removed;
- final Linux/module/macOS gates pass on `d4b1bbb...`;
- branch was synchronized with current main through a real two-parent merge and had `behind=0` before final documentation closeout;
- PROJECT_STATUS on the repair branch reflects the round-2 gate;
- roadmap issue #8 has been frozen on the round-2 audit repair instead of incorrectly allowing Save Editor work.

Remaining closeout:
1. merge PR #41;
2. verify merged-main push CI;
3. update PROJECT_STATUS and roadmap issue #8 to the merged SHA;
4. only then reopen the Hades II Save Editor design gate.
