# Next Development Stage

Updated: 2026-09-20

## Start here

Integrated baseline:
- `main` code/test milestone: r39 / `94e9128c43e5739b7ff1352d9ecaca81d7b3df7b`.
- PR #7 is merged.
- Active unfinished work: `fix/batch-b-runtime-semantics-r40` / Draft PR #18.
- r40 production implementation commit: `864ff8fcbf96c616564756d658d3535c1f570f94`.
- r40 is **not verified yet**. Do not assume the prior source-level inspection is equivalent to running the tests.

Read before coding:
- `PROJECT_STATUS.md`;
- `docs/superpowers/specs/2026-09-19-god-mode-hit-semantics-design.md`;
- `docs/superpowers/plans/2026-09-19-god-mode-hit-semantics.md`.

## First action in the next development thread

When an authorized build environment / target Mac is available:

1. Fetch `fix/batch-b-runtime-semantics-r40` and confirm the working tree is clean. Do not hard-reset unknown local changes.
2. Run the focused God Mode contract:
   `python3 tests/test_god_mode_hostile_effects.py`
3. Run:
   `bash Tools/run_linux_checks.sh`
4. With Hades II stopped, wrap the macOS suite in the existing before/after real-save-tree hash sentinel and run:
   `bash Tools/run_macos_checks.sh`
5. Clean-build Hades II:
   `rm -rf dist && ./build.sh hades2`
6. Confirm packaged runtime revision 40, arm64, debugger entitlement, strict codesign, one packaged game module and a clean git diff.
7. Only after those gates pass, cut an r40 tester App/ZIP and record exact size + SHA256.

If any gate fails, use systematic debugging and keep the r40 branch out of `main`.

## r40 manual acceptance

The new acceptance condition is stronger than "no damage":

1. Record the save-visible/current HeroHit count before enabling God Mode.
2. Enable God Mode.
3. Take repeated ordinary hostile hits that would normally damage health/armor and produce hit reactions.
4. Confirm health/armor are not lost through the blocked ordinary damage path.
5. Confirm HeroHit remains exactly at the pre-God-Mode baseline.
6. Exercise the already-audited Hecate polymorph and Mourning Fields miasma protections.
7. Disable God Mode.
8. Take one real normal hit.
9. Confirm HeroHit resumes native counting and increments normally rather than staying frozen or jumping.
10. Preserve `trainer.log` and the exact observation method used for the save-visible HeroHit value.

If the save-visible HeroHit value is not actually backed by `CurrentRun.Hero.Hits`, stop and trace the persistence path before changing more runtime code.

## Continue Batch B only after the r40 slice is proven

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

Its branch is intentionally behind r39 and must not be synchronized in the middle of Batch B/C/D. After Phase 0 closes:
1. update/rebase it against final `main`;
2. resolve only real integration conflicts;
3. rerun Linux + both macOS module builds;
4. merge only after fresh verification.
