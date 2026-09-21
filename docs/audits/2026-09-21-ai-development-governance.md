# AI-assisted development governance audit

Date: 2026-09-21  
Status: closed historical synthesis

This document records why the 2026-09-21 governance changes were made and what evidence supported them. It is **not** a current handoff, roadmap, architecture authority, or execution queue.

Use current sources in this order:

1. GitHub `main`, production code and executable tests;
2. `PROJECT_STATUS.md` for current operational state;
3. `ENGINEERING_INVARIANTS.md` for stable ownership/lifecycle/replay/Save rules;
4. `GAME_MODULES.md` for the Core/game-module contract;
5. roadmap issue #8 for planned sequencing.

Read this audit only when investigating why a current rule exists, reviewing historical technical debt, or challenging a governance decision.

## 1. Evidence chain

The audit began while `main` was moving. Instead of treating stale workspace results as current proof, the work was repeatedly rebound to exact GitHub SHAs.

| Phase | Exact source | Fresh evidence | Result |
| --- | --- | --- | --- |
| Rebased audit baseline | `1345b39c555df97dfea55074c7ae7d0ab71ad78f` | workflow `35529711449` | permanent Linux gate + all 81 then-portable tests + compileall PASS |
| Governance enforcement | `fed1093236db9ef0ab7840fc2e807ec47764989c` | Linux `35530429607`; module matrix `35530429595`; macOS `35530429621` | PR #44 exact-head gates PASS |
| Lifecycle adversarial fix | `0418cb3666518d47bed5f507fc8a9ff6cf72c5dd` | Linux `35552079532`; module matrix `35552079488`; macOS `35552080294` | PR #45 exact-head gates PASS |
| Active-context reset | `e7efd576379e44d2f104e2a1bc24eed490ca2703` | Linux `35552275804`; module matrix `35552275711`; macOS `35552275716` | PR #46 exact-head gates PASS |
| Historical-tree prune | `d071ddf9fb69c5c5d8bc09af17f43f8fe333587f` | Linux `35554188167`; module matrix `35554188185`; macOS `35554188120` | PR #47 exact-head gates PASS |
| Post-merge closure main before this doc-only refresh | `d64403f903fe386d246b5c1cbe57af39d496281e` | Linux `35554328783`; module matrix `35554328792`; macOS `35554328728` | merged-main gates PASS |

A passing ancestor commit was never treated as proof for a newer tree. That exact-head discipline is itself one of the governance outcomes.

## 2. What the audit established

The durable architecture is now expressed in `ENGINEERING_INVARIANTS.md`; this section records the conclusions, not a duplicate specification.

### Ownership

- Core/Host owns process observation, connection policy, the single shared `TrainerBackendSession`, generic request/timeout behavior, shared UI/Input, Process Time Warp mechanics, and optional generic Save infrastructure.
- A game module owns game command semantics, typed game state, transport/debugger policy, game persistence/Profile meaning, game-specific lifecycle evidence, save codec/schema/edit semantics, and game-specific UI.
- Hades II is the reference implementation, not the shape Core must force on future games.
- `reference_fixture` remains the executable proof that a second module can use Core without Hades-specific semantics.

### State and failure semantics

The audit found that several historical failures came from collapsing distinct state classes:

- process presence vs process lifetime validity;
- process lifetime vs same-PID resident Lua generation;
- durable desired state vs observable runtime state vs dormant state;
- replay-safe durable intent vs one-shot/non-idempotent intent;
- known failure vs `outcome_unknown`;
- user-visible Save operation state vs durable filesystem recovery evidence.

The stable definitions and transition rules now live in `ENGINEERING_INVARIANTS.md`.

### Save safety

Core Save is generic transaction infrastructure; Hades save meaning stays Hades-owned.

The important safety result is fail-closed transaction ownership:

- target-process uncertainty blocks destructive restore;
- rollback is captured and verified before mutation;
- stopped-state evidence is rechecked before cold mutation;
- the final recoverable copy is not destroyed for cosmetic cleanup;
- indeterminate staged/applying state is not automatically replayed;
- recovery bytes remain rediscoverable after the producer/backend dies;
- automated tests never use the real user/game save tree.

## 3. Historical bug family -> missing invariant -> enforcement

| Failure family | Why the bug could enter | Durable enforcement after governance |
| --- | --- | --- |
| Generic engine event treated as Hades lifecycle meaning | no explicit evidence hierarchy for game lifecycle events | real Hades log evidence + watcher/lifecycle tests; `World::Stop()` is explicitly not a main-menu signal |
| Same PID treated as same runtime generation | process lifetime and resident Lua lifetime were conflated | same-PID generation invalidation, retained ready signal, one debugger attachment, no periodic Lua polling |
| Busy transition dropped lifecycle intent | event intent was represented as an immediate action rather than durable bounded state | Host policy behavior scenarios retain target-exit/ready intent until eligible |
| Replacement launch restored trust in stale connection | process presence was allowed to erase old-lifetime connection invalidation | PR #45: definitive launch/exit marks old connection observation stale; busy may delay but not cancel revalidation |
| Timed-out/non-idempotent request replay | execution outcome uncertainty was not a first-class terminal state | backend/session recovery tests + Hades transport taint; unknown in-flight mutation is never auto-replayed |
| Durable preference mixed with one-shot intent | persistence layer had no explicit replay classification | preference replay excludes native modal/direct one-shot actions |
| Consumed next-room one-shot resurrected after restart | durable one-shot lacked identity + consumption receipt | schema-4 token + resident consumed-token receipt |
| Persistence failure prevented runtime cleanup | durable write and resident teardown were treated as one failure domain | best-effort runtime teardown proceeds while persistence failure remains visible |
| Shared trainer log writers overwrote each other | “append” was modeled as seek position rather than kernel multi-writer semantics | Darwin `O_APPEND` behavior contract |
| Staged restore repeated after successful destructive commit | no durable claim distinguished pending from applying/committed work | atomic applying/applied markers; uncertain applying state is indeterminate |
| Save restore TOCTOU | “target stopped” was treated as a durable decision rather than stale evidence | process state rechecked immediately before destructive mutation |
| Rollback/recovery disappeared after backend death | recovery ownership ended with the producing request/process | contained rollback discovery + Save Manager recovery projection |
| Partial Profile shortcut override collision | explicit imported state and omitted local explicit state had no deterministic merge rule | compiled Swift shortcut collision/reflow behavior test |
| Linux test-registration drift | portable tests had two owners: filesystem discovery on macOS and a manual Linux allow-list | exhaustive Linux `test_*.py` discovery with only explicit platform-only exclusions |
| Runtime source changed without identity bump | tests protected the current revision literal, not the base/head relationship | diff-based `Tools/check_runtime_revision.py` gate |
| AI source-of-truth drift | current state, stable rules, historical audits and old branches all looked like executable authority | thin `AGENTS.md`, short `PROJECT_STATUS.md`, stable `ENGINEERING_INVARIANTS.md`, historical tree/branch pruning |

## 4. Adversarial correction to the initial audit

The first governance pass overstated one lifecycle conclusion.

It originally treated “target exit while busy preserves one refresh” as sufficient protection for the entire stale-connection family. A later adversarial review composed transitions that the original test did not:

1. old target is connected;
2. a request is busy;
3. old target exits;
4. replacement target launches before the request settles;
5. presence becomes running again;
6. old `connected=true` can survive and suppress reconnect.

A second case existed when aggregate process presence missed the intermediate stopped snapshot and only a definitive launch notification proved a new target lifetime.

RED evidence:

- `cab0a8e439d04f12f523742ba2b9e4ed40b08358` / Linux `35531543074`: `replacement launch erased stale-connection refresh intent`;
- `31630d8fea67378d417f840f1a74dd1f4174c4f7` / Linux `35531727425`: `definitive launch did not invalidate the prior connected lifetime`.

PR #45 moved the invariant into `TrainerConnectionPolicy`: process presence and connection-lifetime validity are now separate facts. This correction is important because it demonstrates a general audit lesson:

> a locally fixed historical bug is not a system invariant until composed transitions are executable.

## 5. Test-system assessment at governance closure

At closure the repository had 86 `tests/test_*.py` entrypoints.

The pre-governance 85-file suite was classified by dominant semantic strength as:

| Class | Meaning | Count |
| --- | --- | ---: |
| A | executable business/state behavior | 29 |
| B | lifecycle/state-transition scenarios | 8 |
| C | cross-module architecture contracts | 9 |
| D | build/package/CI contracts | 7 |
| E | source-level semantic/static invariants | 7 |
| F | brittle string/regex/source-shape contracts | 13 |
| G | historical regression fossils | 8 |
| H | platform-only tests | 4 |

PR #44 added `test_runtime_revision_gate.py`, bringing the current total to 86.

### Strong family-wide guards

The highest-value contracts are behavior/state oriented:

- `test_host_connection_policy_dev8.py`;
- `test_backend_session_recovery_dev8.py`;
- `test_hades2_run_log_watcher.py`;
- `test_hades2_transport_outcome_unknown_taint.py`;
- Core Save resolution/snapshot/restore/service/protocol suites;
- `test_shortcut_chord_semantics.py`;
- `test_cross_game_isolation.py` + module matrix/reference fixture;
- `test_runtime_revision_gate.py`;
- exhaustive Linux-portable discovery in `Tools/run_linux_checks.sh`.

### Remaining test debt

Some source-shape and round/version-named regressions remain. They are intentionally not bulk-deleted or renamed because several still protect unique wiring/engine/API constraints.

When one of those areas is next modified:

- prefer compile/type/behavior/state verification;
- keep source-text checks only where the real game/toolchain makes a semantic test impractical;
- remove a historical guard only when equal-or-stronger coverage is demonstrated in the same change;
- do not copy `roundXX`, `v0xxx`, or `devX` naming into new tests.

This is maintenance debt, not a current feature freeze.

## 6. Systemic debt disposition

### Closed by PR #44–#47

- Linux portable-test discovery drift;
- resident-runtime revision bump enforcement;
- future-agent source-of-truth fan-out;
- stale connection invalidation across busy rapid relaunch;
- mandatory full-audit freeze / obsolete audit handoff;
- active-tree noise from completed plans/specs, version diffs, validation transcripts and redundant audit reports.

### Remaining non-blocking risks

These were evidence-backed at closure but did not justify expanding governance scope:

1. **Repository protection is still external to code.** At the last audit check `main` reported `protected=false` and repository rulesets were empty. CI exists, but repository settings can still permit bypass. Check current GitHub settings rather than assuming this remains true.
2. **Source-shape regression debt.** Some tests still guard implementation form because the equivalent real-game or AppKit behavior is expensive to exercise.
3. **Core Save sudden-power-loss ceiling.** Not every directory metadata transition fsyncs its parent directory after atomic replace. Existing rollback/hash/recovery behavior covers normal process failures; no current evidence justified broader durability work.
4. **Profile-directory symlink hardening.** Hades Profile storage does not mirror every Core Save containment guard. It runs under the same user authority and had no demonstrated corruption/exploit path.
5. **Build environment reproducibility.** macOS workflows use `macos-latest` and the selected Xcode/toolchain rather than a hermetic compiler image. Exact workflow/SHA evidence is strong, but future runner-image changes may affect reproducibility.

None of these is a reason to reopen a repository-wide audit automatically.

## 7. Deliberate non-actions

The audit explicitly rejected several attractive but weakly justified refactors:

- do not split `runtime/hades.lua` merely because it is large; first prove multi-file loading/lifetime behavior in real Hades II;
- do not perform a broad MVVM/“clean architecture” rewrite of `Hades2Model.swift` or `Hades2View.swift` based on line count;
- do not fragment `Hades2Adapter` just to reduce file size; it is the synchronization boundary among durable preference state, transport observation and resident runtime state;
- do not move Hades desired/dormant/resource semantics into Core without a second real game proving the abstraction;
- do not migrate the suite to pytest/new infrastructure for style alone;
- do not restore code from divergent historical branches without proving a unique behavior missing from current `main`.

These are not permanent bans. Revisit only with current code evidence and a concrete ownership or correctness benefit.

## 8. Governance assets that survived the audit

The lasting output is deliberately small:

- `AGENTS.md` — low-context entrypoint and source-of-truth order;
- `PROJECT_STATUS.md` — current operational state only;
- `ENGINEERING_INVARIANTS.md` — stable engineering contract;
- `GAME_MODULES.md` — Core/game-module contract;
- roadmap issue #8 — planning/sequencing only;
- executable CI/tests — machine enforcement;
- this file — historical rationale only.

PR #47 removed older round/version diffs, validation transcripts, completed plans/specs and redundant audits from the active tree. Git history and closed PRs remain the place to recover that evidence when needed.

## 9. Audit closure

The governance phase is closed.

The repository should not require another broad audit before ordinary development. A future audit is justified only by new evidence such as:

- repeated failures crossing the same ownership boundary;
- a new game module exposing an invalid Core assumption;
- a lifecycle/replay/data-loss defect not covered by current contracts;
- CI or repository settings no longer enforcing the intended gates;
- a major architecture change that invalidates the existing invariant model.

For ordinary work, start at `AGENTS.md` and use the current code/tests rather than this historical report.
