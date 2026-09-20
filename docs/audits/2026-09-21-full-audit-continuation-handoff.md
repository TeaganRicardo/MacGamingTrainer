# Full repository audit continuation handoff

Updated: 2026-09-21

## User directive

Before any new product feature work resumes, the next development thread must perform another **complete, independent repository audit**.

This directive supersedes the previous handoff state that said the round-2 audit was closed and Hades II Save Editor design could resume.

Until the next full audit closes:
- **freeze all new feature development**;
- do not begin Hades II Save Editor implementation;
- do not approve binary save mutation;
- treat prior audit reports as evidence/reference, not as permission to skip any audit domain.

## Authoritative starting baseline

Current GitHub main documentation head at handoff:
`6f5bd33507098648bdcb36a88bdf6ded869f5e0d`

Current product-code baseline:
`c2c4f39ffe5c943c76f2190c458d4ece384f6513` (PR #41)

Earlier product baselines that remain relevant history:
- `ee258442f89a1e3ad4cb04f02bbfc7146488e148` — PR #42 Save Manager completion fix;
- `f1eacae8d8c52605e5d87317a59ddd208aad662a` — PR #40 deep-audit merge;
- `d3e4385054aaeddcad4c9ef10cdc1dbaea9dd8a4` — verified pre-squash product tree from PR #40.

Current Hades II runtime/schema baseline:
- resident runtime revision: 42;
- desired-state schema: 4;
- Hades II module protocol: 5;
- Host protocol: 5.

Current target-game reference:
- Hades II 1.139672 / Steam build 24556151.

## Fresh verification already attached to the starting product baseline

PR #41 merged-main verification:
- Linux contracts `35529062370`: PASS;
- module matrix `35529062382`: PASS;
- Build 2 macOS `35529062368`: PASS, including exhaustive tests, Hades II build, package verification and RC artifact.

These runs prove the baseline was green at merge time. They do **not** replace the next thread's required full audit or fresh final verification.

## Important defects already fixed in the audit lineage

Do not reopen these unless new evidence shows regression.

### PR #40 — deep pre-feature audit
- target exit while Host is busy preserves one deferred refresh;
- `outcome_unknown` Lua result taints transport and blocks later mutation until restart;
- cold Save restore rechecks target process state before mutation;
- staged/rollback interruption remains indeterminate and is never auto-replayed;
- one-shot next-room reward uses durable token + consumed receipt across backend restart;
- durable desired-state persistence failure no longer prevents best-effort resident teardown;
- shared UI ownership was tightened without moving Hades business semantics into Core.

### PR #42 — Save Manager completion contract
- unavailable-backend Save requests still invoke completion with failure;
- optimistic rename state and sequential batch-delete flows can no longer be stranded only because the backend stopped between UI action and request dispatch.

### PR #41 — rollback recovery discoverability
- if backend death interrupts rollback itself, contained Trainer-owned `.rollback-*` recovery directories remain discoverable after restart;
- Core exposes recovery evidence generically;
- shared Save Manager shows warning + recovery paths + Finder reveal;
- no automatic restore/delete was added;
- symlinked/out-of-root lookalikes are excluded.

## Previous round-2 audit report

Reference only:
`docs/audits/2026-09-21-full-repository-audit-round2.md`

It contains the previous branch classification, architecture review, lifecycle review, Save review, runtime command classification, UI/hotkey review and CI evidence.

**Next-thread rule:** do not simply accept that report's verdict. Re-run the audit from current main and use the report only to:
- know which old branches were previously classified;
- know which invariants were intentionally established;
- identify regressions or contradictions;
- avoid restoring superseded weaker implementations.

## Required audit scope for the next thread

### 0. Repository and evidence integrity

Re-enumerate **all** remote branches from the current repository state.

For every branch:
- compare against current `main`;
- distinguish:
  - strictly contained/behind;
  - squash-merged or superseded implementation;
  - historical audit evidence;
  - documentation-only history;
  - unrelated repository contamination;
  - genuinely unique unmerged MacGamingTrainer product code.

Do not treat `ahead > 0` as proof of missing code. Compare commit intent and file behavior because many historical branches were squash-merged.

Explicitly re-check:
- `audit/*`;
- `architecture/*`;
- `feature/*`;
- `fix/*`;
- `maintenance/*`;
- `refactor/*`;
- `spike/*`;
- `ci/lidkeep-rc1-build` (previously classified as unrelated contamination).

Also verify:
- open PRs;
- current workflows and triggers;
- test discovery;
- `PROJECT_STATUS.md`;
- roadmap issue #8;
- active audit/handoff docs;
- stale/deleted-document pointers;
- runtime revision/schema assertions in tests/docs.

### 1. Framework boundary audit

Verify from code, not summary:
- Core / Host / Backend Core remain game-agnostic;
- no Hades business semantics have leaked into Core/Host;
- Hades II has not taken ownership of Host/backend process/session responsibilities;
- exactly one authoritative backend session owner remains;
- shared UI/Input/Process Time Warp/Save infrastructure has one shared owner;
- no duplicate live implementation has reappeared in Hades;
- reference fixture still independently proves the second-module boundary.

Large-file size alone is not a defect. Refactor only if a real responsibility boundary or bug requires it.

### 2. Lifecycle / Transport / Concurrency audit

Trace complete behavior:
- attach -> ready -> reset -> reattach -> exit;
- true launch vs same-PID runtime reset;
- backend restart;
- target exit while busy;
- request timeout;
- SIGTERM -> `KeyboardInterrupt` -> SIGKILL escalation;
- delayed mutation scheduling;
- FIFO ordering;
- barrier semantics;
- backend/session termination;
- stale observable state;
- debugger ownership and runtime generation.

Verify invariants:
- no periodic LLDB/Lua polling;
- no second debugger attachment for same-PID recovery;
- no mutation replay after outcome-unknown;
- missing runtime bootstrap may be recovered only where read/idempotency semantics make it safe;
- completion callbacks are total where UI state depends on them.

### 3. Save / Persistence audit

Re-read the complete transaction path:
- resolution;
- snapshot;
- manifest/hash verification;
- restore;
- pre-restore backup;
- rollback;
- rollback failure;
- staged restore;
- staged applying/applied/indeterminate markers;
- target-process TOCTOU;
- symlink containment;
- internal data-root containment;
- atomic replace;
- recovery-copy persistence/discovery;
- rename/delete/open-folder operations;
- process death during each mutation stage.

Verify that tests never touch real user saves.

Audit the new PR #41 recovery discovery implementation as current production code, including:
- contained `.rollback-*` enumeration;
- symlink exclusion;
- UI observability;
- recovery path lifecycle;
- whether stale recovery evidence can be safely distinguished/retained.

Do not auto-delete or auto-restore recovery evidence without a separately proven transaction design.

### 4. Hades II runtime / command semantics audit

Build an explicit command classification from the current router/adapter/runtime:

#### Query/lifecycle
Examples include status/scan/connect/diagnostics/list-style reads.

#### Idempotent or ledger-protected mutation
Check request ID and fingerprint behavior.

#### Durable desired state
Check persistence ordering, reconnect replay and migration.

#### Native one-shot modal/action
Check that it is never preference-replayed after reconnect/backend restart.

For every externally reachable command, verify:
- timeout behavior;
- request cache behavior;
- resident action ledger behavior;
- retry behavior;
- backend-restart behavior;
- runtime-generation mismatch behavior;
- whether same request ID with a different payload is rejected at the correct boundary.

Re-check:
- next-room reward token/consumption receipt;
- special-choice;
- sell-traits;
- resource/reroll mutations;
- reward spawning;
- God Mode/runtime hooks;
- runtime revision discipline.

### 5. UI / Hotkey / Observable state audit

Verify:
- shared component ownership;
- no Hades-private copy of shared controls;
- no stale observable state after backend exit/restart/reset;
- desired state is not confused with runtime-active state;
- hotkey registration owner remains Core;
- Profile/import shortcut collision/reflow semantics;
- external/OS hotkey collision surfacing;
- hotkey feedback ordering vs model reply application;
- mapped slider preview vs committed backend value;
- Save Manager optimistic UI and completion semantics;
- recovery evidence visibility from PR #41.

### 6. Final verification

At the end of the next audit, on the **final product/test SHA**:

1. Materialize exact source from GitHub/CI into the container.
2. Run `Tools/run_linux_checks.sh`.
3. Attempt every current `tests/test_*.py` entrypoint.
4. Classify Linux platform-only failures explicitly; do not call them product test failures.
5. Run Backend compileall.
6. Parse every live Swift source with `swiftc -frontend -parse` where supported.
7. Scan for:
   - conflict markers;
   - duplicate Python definitions;
   - stale runtime/schema constants;
   - risky execution primitives;
   - duplicate session owners;
   - Hades business tokens in Core/Host;
   - polling regressions.
8. Trigger fresh GitHub:
   - Linux contracts;
   - module matrix;
   - Build 2 macOS full tests/build/package/artifact.
9. Use RDC only if a macOS behavior cannot be proven by Build 2/macOS CI. Never use RDC for repository/file transport.

Do not declare the audit complete until the final changed SHA, not merely the starting baseline, has fresh verification.

## Development/transport rules

- GitHub connector is authoritative for the remote repository.
- Do not repeatedly retry container `git clone/fetch/pull` or `curl github.com` after outbound-network failure.
- If the local working tree is absent, obtain an exact source snapshot through GitHub/CI and materialize it in the container.
- Container is for editing, diffing, static review and non-macOS tests.
- Push repository changes through GitHub connector.
- RDC is macOS-only validation.
- Never use RDC for segmented repository/file transfer.

## Debugging/fix rule

If the audit finds a real defect:
1. trace root cause first;
2. create the smallest behavioral RED reproduction;
3. verify RED for the intended reason;
4. fix at the true ownership boundary;
5. verify GREEN;
6. run the affected suite;
7. later run the final full suite/CI.

Do not mix speculative cleanup with a proven bug fix.

## Known non-blocking hardening ceilings

These were previously graded Minor. Re-evaluate them, but do not automatically promote/fix without new evidence:

1. Some Core directory metadata updates are not parent-directory-fsynced after every `os.replace`. This is an extreme sudden-power-loss durability ceiling.
2. Hades Profile storage does not use the full Core Save subdirectory-symlink containment discipline. It runs under the same user authority; no concrete exploit/data-loss path was previously demonstrated.

## Handoff state

At handoff creation:
- prior round-2 Important findings are fixed and merged;
- no new product change should begin;
- the next thread owns the new complete audit pass;
- Hades II Save Editor design/implementation is frozen until that audit explicitly closes;
- no binary save mutation is approved.

When the next audit closes, update:
- `PROJECT_STATUS.md`;
- roadmap issue #8;
- the new audit report;
- branch classification;
- exact final verification run IDs.
