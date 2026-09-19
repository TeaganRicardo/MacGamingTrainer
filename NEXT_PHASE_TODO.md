# Next Development Stage

Updated: 2026-09-20

## Start here

Integrated baseline:
- `main` now contains r40; verified code/test milestone: `39c66b702d66c650eeb992f7016d5e9cb7c3f64c`.
- PR #7 (r39) and PR #18 (r40) are merged.
- r40 production implementation commit: `864ff8fcbf96c616564756d658d3535c1f570f94`.
- r40 automated/Linux/macOS/build/package gates and focused HeroHit manual acceptance are **PASS**.
- Next active development slice: global Hades II game speed, from current `main` on a new isolated branch.

Read before coding:
- `PROJECT_STATUS.md`;
- `docs/superpowers/specs/2026-09-19-god-mode-hit-semantics-design.md`;
- `docs/superpowers/plans/2026-09-19-god-mode-hit-semantics.md`.

## r40 acceptance checkpoint — PASS

Verified on the authorized target Mac against exact code/test head `39c66b702d66c650eeb992f7016d5e9cb7c3f64c`:

- save persistence path for `CurrentRun.Hero.Hits`: proven from installed Hades II 1.139672 scripts;
- focused God Mode contract: PASS;
- full Linux suite: PASS / `linux_checks_ok`;
- full macOS suite: PASS / `macos_checks_ok`;
- real-save-tree sentinel: `REAL_SAVE_TREE_UNCHANGED`;
- clean Hades II build/package: PASS;
- tester ZIP: `MacGamingTrainer-0.1-build2-rc-r40.zip`, 1,976,217 bytes, SHA256 `45b623fcb70986af6ad604b69f62192925b7fb9e97854573f7d7daab30acc0c0`;
- manual HeroHit acceptance used hot backup `saves-20260920-011751-3qk9q5zy` before the test and `saves-20260920-012157-js8mys43` after it. Read-only extraction shows current-run Hero `Hits = 182` in both, `Health = 157` in both, and God Mode active in the after snapshot;
- per owner instruction, a deliberate post-disable hit to prove resumed increment is not required for this slice;
- Hecate polymorph and Mourning Fields miasma behavior is unchanged from the pre-existing implementation; r40 did not alter those effect blocks.

r40 is integrated. Next action: create a new isolated game-speed branch from current `main`, re-audit Hades II 1.139672 time/speed ownership, write the design and RED contracts, then implement only the demonstrated minimal slice.

## Next Batch B slice

### Global game speed

Re-audit installed Hades II 1.139672 scripts before coding.

Required semantics:
- trainer factor applies across combat, non-combat and Crossroads;
- native slow/time-stop effects continue to layer underneath the trainer factor;
- no repeated multiplicative compounding across room/session changes;
- same-PID `SessionState` reset rebinds cleanly;
- disabling returns to native 1x without undoing game-owned time modifiers;
- no periodic polling.

Treat game speed as a separate TDD sub-project; do not fold speculative hostile-effect changes into it.

### Hostile debuff/control audit

Do not broaden `godModeBlockedEffects` by name alone.

For each candidate path determine:
- whether it is hostile, player-owned/self-selected, narrative/presentation-coupled, or mixed;
- whether normal invulnerability already blocks it;
- whether it bypasses the `Damage` router;
- the narrowest safe interception boundary.

Only add blocks with a demonstrated source/behavioral reason and a regression contract.

## Then Batch C

Trainer Host sounds:
- replace Glass/Pop/Tink with one coherent bundled family;
- enabled/deferred/disabled remain distinguishable at low volume;
- preserve post-result semantics;
- delayed backend completion must not swallow first-toggle feedback;
- keep Hades-specific semantics out of Core.

## Then Batch D

Residual attach/world-readiness stutter:
- use retained logs as baseline;
- separate LLDB attach from first Lua/world-ready cost;
- use lifecycle signals rather than timers;
- never create a second debugger attachment for same-PID recovery.

## Integration policy from this point

Do not recreate PR #7 as another giant accumulation branch.

For each independently verified slice:
1. isolate on a small branch;
2. RED -> GREEN / full relevant contracts;
3. target-Mac build/manual acceptance when required;
4. merge the verified slice into `main` promptly;
5. update `PROJECT_STATUS.md` and this file;
6. continue the next slice from current `main`.

Hosted Actions issue #16 remains tracked separately. If hosted jobs still fail before step 0, record exact run/job evidence; do not mislabel that as a code failure.

## Phase 1 / PR #10

PR #10 is now based directly on `main` and remains DRAFT.

Its branch is intentionally behind the current Phase 0 baseline and must not be synchronized in the middle of Batch B/C/D. After Phase 0 closes:
1. update/rebase it against final `main`;
2. resolve only real integration conflicts;
3. rerun Linux + both macOS module builds;
4. merge only after fresh verification.
