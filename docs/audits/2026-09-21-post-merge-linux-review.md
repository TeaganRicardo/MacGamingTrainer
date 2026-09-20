# Post-merge Linux code review

Updated: 2026-09-21

## Reviewed baseline

Two exact-main passes were performed.

Initial post-audit baseline:
- product merge: `f1eacae8d8c52605e5d87317a59ddd208aad662a` (PR #40);
- reviewed docs-only main head: `c2fe74c2dc6fd42bea48f40878e3c2ba760eb10b`;
- verified pre-squash audit SHA: `d3e4385054aaeddcad4c9ef10cdc1dbaea9dd8a4`.

Corrected final baseline after the review finding was fixed:
- merged main: `ee258442f89a1e3ad4cb04f02bbfc7146488e148` (PR #42);
- no runtime/Lua source changed in PR #42, so resident revision remains 42.

The source was not reconstructed from selective GitHub reads. A temporary workflow on the historical audit branch checked out the exact main SHA, packaged it, emitted a commit marker and SHA256, and ran the repository Linux contract suite.

Workflow evidence:
- post-merge snapshot/Linux run `35526388178`: PASS;
- artifact `mgt-main-linux-review-source`;
- artifact source commit marker: `c2fe74c2dc6fd42bea48f40878e3c2ba760eb10b`;
- source tar SHA256: `d8e7e39f812f9e1384fa2f5acfdb9236f6dca4a860c62d72a61a1495ea56e90f`.

The temporary workflow was deleted after the artifact was consumed and does not exist on main.

## Verification

### Standard Linux contracts

`bash Tools/run_linux_checks.sh`: PASS (`linux_checks_ok`).

This includes the backend/core contracts, Hades adapter contracts, lifecycle/status behavior, cross-game isolation/reference fixture, native modal contracts, persistence/schema integrity, shortcuts, shared UI boundary and current runtime/schema contracts.

### Broad test execution

Every `tests/test_*.py` file was attempted on the Linux review snapshot.

Result:
- 81 tests: PASS on Linux.
- 4 tests: Linux platform failure only; no assertion/business-logic failure.

The four platform-only tests were:
- `test_core_save_batch_delete_round20.py` — Linux Swift toolchain lacks AppKit;
- `test_core_save_rename_completion_round24.py` — Linux Swift toolchain lacks AppKit;
- `test_hades2_run_log_watcher.py` — Linux Swift toolchain lacks Darwin;
- `test_trainer_log_sink_shared_append.py` — Linux Swift toolchain lacks Darwin.

All four were independently present and PASS in the final macOS Build 2 job from run `35526120497`:
- `core_save_batch_delete_round20_ok`;
- `core_save_rename_completion_round24_ok`;
- `hades2_run_log_watcher_ok`;
- `trainer_log_sink_shared_append_ok`.

### Static review

PASS:
- `python3 -m compileall -q Backend`;
- every Swift file under `Sources/` parses with `swiftc -frontend -parse`;
- no duplicate Python top-level/class definitions found by AST scan;
- no Git conflict markers under Backend/Sources/Tools/tests/workflows;
- no TODO/FIXME/HACK/XXX markers in live code/test/workflow scope;
- no production `shell=True`, `os.system`, `eval`, `exec`, pickle or unsafe YAML loader found;
- main contains only the three permanent workflows: Linux contracts, module build matrix and Build 2 macOS;
- only one `TrainerBackendSession()` constructor exists, in `Sources/App.swift`;
- no periodic LLDB/Lua polling timer was found;
- Hades runtime revision references consistently use revision 42;
- desired-state schema references consistently use schema 4.

Broad exception sites and destructive filesystem operations were reviewed manually. The intentional `BaseException` handling is confined to Core Save termination/rollback fail-safe logic. Destructive Save operations remain behind the existing storage containment, snapshot-ID/path validation and rollback ownership. Other broad catches are diagnostic/error-boundary/cleanup paths that log, rethrow, quarantine or deliberately degrade rather than silently treating mutation as success.

## Findings

The initial broad pass found no Critical/Important issue, but the subsequent callback-flow review found one Important defect before feature work resumed.

### Important — Save Manager dropped completion when the backend was already unavailable

Root cause:
`TrainerSaveManagerModel.request()` returned directly from its `session.isRunning` guard without invoking `onComplete(false)`. Rename begins with an optimistic display name and clears that state only from the completion callback. If editing began while the backend was alive and the worker exited before click-away committed the rename, the optimistic name could remain indefinitely. The same incomplete callback contract could also strand a sequential batch-delete chain.

Fix:
- unavailable-backend requests still surface `后端未运行。`;
- the guard now also invokes `onComplete(false)`;
- no new state owner or retry path was introduced;
- the portable Core Save model contract is now part of `Tools/run_linux_checks.sh`;
- the macOS rename integration test includes the backend-stopped completion scenario.

RED evidence:
- the new portable contract failed because the guard contained no `onComplete?(false)`.

GREEN evidence before PR CI:
- `tests/test_core_save_swift_model_round20.py`: PASS;
- `Tools/run_linux_checks.sh`: PASS / `linux_checks_ok`.

Final fix/merge evidence:
- PR #42 tested head: `b0b1a1d9a7d27af22aca7e2a185c84bf372bb2a3`;
- Linux contracts `35527279524`: PASS, including the newly permanent `test_core_save_swift_model_round20.py`;
- module matrix `35527279475`: Hades II PASS; reference fixture PASS; package isolation PASS;
- Build 2 macOS `35527279464`: full contract suite PASS, build/package/artifact PASS;
- macOS log explicitly ran `test_core_save_rename_completion_round24.py` -> `core_save_rename_completion_round24_ok`;
- PR #42 squash-merged as `ee258442f89a1e3ad4cb04f02bbfc7146488e148`.

No new architecture conflict was found:
- Core/Host remains game-agnostic;
- Hades semantics remain module-local;
- Host/backend session ownership remains singular;
- native modal and outcome-unknown operations are not automatically replayed;
- Save indeterminate outcomes remain fail-closed.

Existing Minor hardening notes remain unchanged:
- selected Core rename paths do not parent-directory fsync after `os.replace`, which is an extreme power-loss durability ceiling;
- Hades Profile storage does not apply the same explicit subdirectory symlink containment as Core Save storage, within the same user authority.

Neither has a demonstrated current corruption, privilege-boundary or replay failure, so no speculative code was added during this review.

## Final exact-main re-review

The corrected merged main `ee258442f89a1e3ad4cb04f02bbfc7146488e148` was materialized independently after PR #42.

Source evidence:
- temporary review workflow run `35527702078`: PASS;
- artifact `mgt-post-fix-main` / artifact id `10609363650`;
- artifact commit marker: `ee258442f89a1e3ad4cb04f02bbfc7146488e148`;
- source tar SHA256: `f621f60f6636c7f24478180c7a532ee5c95dd802ec2704f4afee3dd76fa8b200`;
- the temporary branch was verified to differ from reviewed main only by its excluded snapshot workflow.

Fresh container verification from that exact archive:
- `bash Tools/run_linux_checks.sh`: PASS / `linux_checks_ok`;
- `python3 -m compileall -q Backend Tools tests`: PASS;
- all 81 Linux-portable `tests/test_*.py`: PASS;
- the remaining four AppKit/Darwin-only tests were already PASS in PR #42 Build 2 macOS;
- 47/47 live Swift source files: frontend parse PASS;
- Python duplicate-definition scan: PASS;
- conflict-marker and live TODO/FIXME/HACK/XXX scans: PASS;
- risky execution primitive scan: PASS;
- exactly one `TrainerBackendSession()` constructor remains;
- Core/Hades boundary token scan: PASS;
- periodic Hades live-Lua polling scan: PASS.

No Critical or Important finding remains open after the corrected-main re-review.

## Gate result

The pre-feature deep audit, post-merge Linux review, review fix and corrected-main re-review are complete.

The audit freeze can end. The next product gate returns to **Hades II Save Editor design**. No binary save mutation is approved by this review; codec ownership, stopped/live policy, pre-edit snapshot/recovery and the first editable schema still require an approved design before implementation.
