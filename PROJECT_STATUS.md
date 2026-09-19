# MacGamingTrainer Project Status

Updated: 2026-09-20

## Canonical integration state

- Product: 0.1 / Build 2.
- `main` now contains the verified r39 milestone. Code/test milestone SHA: `94e9128c43e5739b7ff1352d9ecaca81d7b3df7b`.
- PR #7 was integrated by a non-forced fast-forward on 2026-09-20 after explicit owner instruction to land verified increments early instead of keeping one ever-growing Phase 0 PR.
- Hades II resident runtime on the integrated milestone: revision 39.
- Host protocol 5; module protocol 5; desired-state schema 3; Profile schema 4.
- Target game build: Hades II 1.139672 / Steam build 24556151.
- Future work should use small, independently verified branches/PRs and land completed slices into `main` instead of reopening a mega integration branch.

## r39 evidence carried into main

The r39 milestone had the following evidence before integration:

- targeted native-special-choice contract: PASS;
- full `Tools/run_linux_checks.sh`: PASS / `linux_checks_ok`;
- clean Build 2 package: PASS;
- arm64 executable, debugger entitlement and strict codesign: PASS;
- ZIP integrity: PASS;
- tester ZIP: `MacGamingTrainer-0.1-build2-rc-r39.zip`;
- ZIP SHA256: `5f1e8609a60e8b7f4387915b5d22a97d9d7865e7e46552025a068fe3930d1c73`;
- focused r39 manual acceptance: PASS on 2026-09-19.

The last full macOS suite + real-save-tree before/after sentinel passed on r37. The final r39 full macOS suite was skipped because Hades II was actively running; r39's later code change was confined to the Hades Lua special-choice path.

Exact-head GitHub-hosted runs for r39 still fail before step 0:
- Linux run `35450922466`;
- macOS run `35450922471`;
- both expose `steps=null` and `logs_url=null`.

That remains infrastructure issue #16, not code-test evidence. The owner explicitly changed integration policy on 2026-09-20 so this infrastructure failure did not keep the already locally verified/manual-accepted r39 milestone out of `main`.

## Active work: Batch B / r40

Active branch: `fix/batch-b-runtime-semantics-r40`.

Relevant commits already on that branch:
- design spec: `1e5be31957aa6519e8aaac62d1084c99a4169929`;
- implementation plan: `6561b2783151be44afdf5ea0aa850b93be1bf670`;
- hit-count contract commit: `5c59a2dcc26931cd8a0fb72c7b974a6048dea1e7`;
- r40 implementation commit: `864ff8fcbf96c616564756d658d3535c1f570f94`;
- pre-handoff checkpoint: `b384fb837ba848eb9ba7d08edaf0858083fed38f`.

Implemented in the r40 branch, but **not yet accepted or integrated**:
- resident runtime 39 -> 40;
- God Mode captures the bound Hero's exact `CurrentRun.Hero.Hits` baseline;
- an original `nil` baseline remains `nil` rather than becoming 0;
- the God Mode `Damage` early-return restores the baseline first;
- the existing `UpdateTimers` guard reasserts that baseline without adding a new timer/thread/polling path;
- release restores the baseline one final time and clears the binding;
- no global `ApplyEffect` hook was added;
- the explicit God Mode effect block list is still only `HecatePolymorphStun` and `MiasmaSlow`.

Important verification correction:
- the current cloud environment has no repository checkout or runnable Lua 5.2;
- the authorized target Mac was offline when r40 was written;
- therefore no authoritative command-run RED/GREEN, full focused test, Linux suite, macOS suite, build, or manual acceptance exists for r40 yet.
- Treat r40 as **implementation present, verification pending**. Do not merge it until fresh command output exists.

Design/plan:
- `docs/superpowers/specs/2026-09-19-god-mode-hit-semantics-design.md`
- `docs/superpowers/plans/2026-09-19-god-mode-hit-semantics.md`

## Remaining Phase 0 work

### Batch B — game speed + God Mode

Still open after the r40 hit-count slice:
- prove the save-visible HeroHit field is the same persistence path as `CurrentRun.Hero.Hits`;
- fresh automated + target-Mac verification of the r40 hit invariant;
- complete hostile debuff/control audit rather than guessing from effect names;
- redesign game speed so the trainer factor is global across combat, non-combat and Crossroads while preserving native slow/time effects underneath it;
- do not add periodic LLDB/Lua polling.

### Batch C — Trainer Host feedback sounds

- one coherent bundled enabled/deferred/disabled sound family;
- reliable post-result playback, including delayed first operations;
- implementation remains entirely Core/Trainer Host.

### Batch D — readiness/attach stutter

- separate LLDB attach cost from first Lua/world-ready transition cost;
- preserve event-driven recovery;
- no second debugger attachment for same-PID recovery;
- no periodic polling.

Then run final consolidated regression/acceptance.

## GitHub state

- PR #7: MERGED into `main` at r39.
- PR #10: still DRAFT; retargeted to `main`. Its Phase 1 branch is intentionally unsynchronized with r39 until Phase 0 closes.
- Issue #1: keep open as lifecycle/manual-acceptance umbrella until the remaining Phase 0 lifecycle checks close.
- Issue #11: keep open for same-PID recovery/readiness performance until Batch D is accepted.
- Issue #16: keep open for hosted Actions step-0 failures.
- Issue #17: non-blocking partial schema-4 shortcut-profile robustness fix; proven branch exists, defer until an intentional integration point.

## Branch hygiene

The following are no longer development bases once r39 is on `main`:
- `feature/post-v0.1-improvements` (r39 milestone already integrated);
- merged Batch A / special-choice r38/r39 branches after ancestry is reconfirmed.

Retain:
- `fix/batch-b-runtime-semantics-r40` — active;
- `fix/profile-shortcut-partial-conflict` — issue #17;
- `architecture/reference-module-proof` — PR #10;
- unrelated `ci/lidkeep-rc1-build`.

Delete stale merged branches when branch-deletion tooling is available; do not force-delete anything with unique commits.

## Permanent non-regression constraints

- Tests must never mutate real user/game data; destructive filesystem tests require explicit temporary roots.
- Target-Mac full suites keep a before/after hash sentinel on the Hades II save tree while this release work remains active.
- No periodic LLDB/Lua polling.
- No second debugger attachment for same-PID runtime recovery.
- No replay of outcome-unknown non-idempotent mutations or native modal commands.
- No Hades-specific semantics in Core/Host.
- Native modal commands are one-shot and never preference-replayed.
- Save restore must never make the Hades II save root disappear.
- A failed rollback must preserve the last recoverable copy.
- Runtime source changes require a resident revision bump.
- GitHub is the durable source of truth for code, version, RC identity and handoff state.
- Use the target Mac only for target-specific build/game verification; normal development/review stays in the development environment/GitHub.
- Each tester handoff is one exact HEAD + one prebuilt signed App/ZIP + SHA256.
- Superseded RCs are never reused for PASS.
- Fix demonstrated/root-caused failures with RED -> GREEN coverage.
