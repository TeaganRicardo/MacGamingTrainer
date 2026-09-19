# MacGamingTrainer Project Status

Updated: 2026-09-20

## Canonical integration state

- Product: 0.1 / Build 2.
- `main` now contains the verified r40 God Mode hit-semantics slice. Verified code/test milestone SHA: `39c66b702d66c650eeb992f7016d5e9cb7c3f64c`; acceptance-evidence integration SHA: `7428c0b4afc72ca1e6c626c49ec1272f26957623`.
- PR #7 (r39) and PR #18 (r40) were integrated by non-forced fast-forward under the small verified-slice policy.
- Hades II resident runtime on the integrated milestone: revision 40.
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

## r40 evidence integrated into main

PR #18 / `fix/batch-b-runtime-semantics-r40` is merged into `main`.

Relevant commits already on that branch:
- design spec: `1e5be31957aa6519e8aaac62d1084c99a4169929`;
- implementation plan: `6561b2783151be44afdf5ea0aa850b93be1bf670`;
- hit-count contract commit: `5c59a2dcc26931cd8a0fb72c7b974a6048dea1e7`;
- r40 implementation commit: `864ff8fcbf96c616564756d658d3535c1f570f94`;
- pre-handoff checkpoint: `b384fb837ba848eb9ba7d08edaf0858083fed38f`;
- verified r40 code/test head: `39c66b702d66c650eeb992f7016d5e9cb7c3f64c`.

Integrated r40 behavior:
- resident runtime 39 -> 40;
- God Mode captures the bound Hero's exact `CurrentRun.Hero.Hits` baseline;
- an original `nil` baseline remains `nil` rather than becoming 0;
- the God Mode `Damage` early-return restores the baseline first;
- the existing `UpdateTimers` guard reasserts that baseline without adding a new timer/thread/polling path;
- release restores the baseline one final time and clears the binding;
- no global `ApplyEffect` hook was added;
- the explicit God Mode effect block list is still only `HecatePolymorphStun` and `MiasmaSlow`.

Verification checkpoint — 2026-09-20:
- installed Hades II 1.139672 scripts prove `CurrentRun.Hero.Hits` is save-backed: `SaveLogic.lua` serializes `CurrentRun`, `EndRun()` moves that same run into `GameState.RunHistory`, and the latest-run Hero blacklist does not remove `Hits`;
- focused `tests/test_god_mode_hostile_effects.py`: PASS / `god_mode_hostile_effects_ok`;
- the first full Linux run exposed three stale revision-39 assertions in existing tests; root cause was incomplete test-contract propagation of the intentional r40 revision bump;
- test-only commit `39c66b702d66c650eeb992f7016d5e9cb7c3f64c` advances those contracts to revision 40; no production code changed in that commit;
- full `Tools/run_linux_checks.sh`: PASS / `linux_checks_ok`;
- full `Tools/run_macos_checks.sh`: PASS / `macos_checks_ok`;
- real Hades II save-tree before/after SHA-256 sentinel: `REAL_SAVE_TREE_UNCHANGED`;
- clean Hades II build/package: PASS; packaged runtime 40, arm64, debugger entitlement, strict codesign, exactly one packaged game module and clean git diff all confirmed;
- tester ZIP: `MacGamingTrainer-0.1-build2-rc-r40.zip`, size `1976217` bytes, SHA256 `45b623fcb70986af6ad604b69f62192925b7fb9e97854573f7d7daab30acc0c0`; ZIP integrity PASS;
- focused real-game HeroHit acceptance: PASS using hot backups `saves-20260920-011751-3qk9q5zy` (`godmode测试前`) and `saves-20260920-012157-js8mys43` while r40 God Mode was active. Read-only SGB1 extraction shows `LUA_DATA.CurrentRun.Hero.Hits = 182` before and `182` after; `Health = 157` before and after; the after snapshot contains `MacGamingTrainerGodMode = true`. The latest completed historical run independently remains `Hero.Hits = 248`, confirming the current-run field was not confused with run history;
- per owner instruction, the post-disable deliberate hit/increment check is not required for this slice. Release still restores/clears the baseline by contract and implementation review;
- Hecate polymorph and Mourning Fields miasma interception are pre-existing r39 behavior and were not modified by r40, so this r40 acceptance does not claim a new manual retest of those paths.

r40 is **verified, accepted and integrated into `main`**.

Design/plan:
- `docs/superpowers/specs/2026-09-19-god-mode-hit-semantics-design.md`
- `docs/superpowers/plans/2026-09-19-god-mode-hit-semantics.md`

## Remaining Phase 0 work

### Batch B — game speed + God Mode

Still open after the accepted r40 hit-count slice:
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
- PR #18: MERGED into `main` at r40 by non-forced fast-forward; GitHub reports state `MERGED`.
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
- `fix/profile-shortcut-partial-conflict` — issue #17;
- `architecture/reference-module-proof` — PR #10;
- unrelated `ci/lidkeep-rc1-build`.

The merged audit/Batch A/r38/r39/r40/release branches have no development role once ancestry against current `main` is reconfirmed. Delete merged branches only after confirming they hold no unique commits; never force-delete anything with unique commits.

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
