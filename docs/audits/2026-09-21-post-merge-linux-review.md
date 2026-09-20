# Post-merge Linux code review

Updated: 2026-09-21

## Reviewed baseline

- Exact main source reviewed: `c2fe74c2dc6fd42bea48f40878e3c2ba760eb10b`.
- Product merge beneath that docs-only head: `f1eacae8d8c52605e5d87317a59ddd208aad662a` (PR #40).
- Verified pre-squash product-code SHA: `d3e4385054aaeddcad4c9ef10cdc1dbaea9dd8a4`.

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

Final merge evidence is pending fresh PR CI.

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

## Gate result

The review gate is temporarily reopened for the Save Manager completion fix above.

New product feature work remains frozen until that fix is merged with fresh Linux, module-matrix and macOS Build 2 verification. After the corrected main is reviewed again, the next product gate can return to **Hades II Save Editor design**. No binary save mutation is approved by this review.
