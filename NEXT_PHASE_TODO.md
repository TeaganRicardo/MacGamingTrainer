# Next Development Stage

PR #7 remains DRAFT. Runtime r39 focused acceptance is **PASS** as of 2026-09-19.

## Current state

- r39 special-choice native-parity follow-up: automated PASS + manual PASS.
- Repeated special-choice opens succeeded in one run, then succeeded again after restore/relaunch in a different run.
- No remaining r39 special-choice blocker is open.
- Continue directly with Batch B; do not reopen Batch A unless a regression is demonstrated.

## Batch B — game speed + God Mode

Re-plan from installed game scripts before coding.
- Make trainer game speed global across combat, non-combat, menus and crossroads rather than Hero-bound.
- Preserve native slow/time effects underneath the trainer factor.
- Audit hostile debuff/control pathways including polymorph, slow/time stop, DOT/poison and forced control.
- Replace the current two-effect God Mode list only after identifying a source-aware/common application boundary.
- Cover the audited set statically first, then request only representative manual checks.

## Batch C — Trainer Host feedback sounds

- Replace Glass/Pop/Tink with one coherent bundled family.
- enabled/deferred/disabled must remain distinguishable at low volume.
- Preserve post-result semantics.
- Ensure delayed backend completion cannot swallow first-toggle feedback.
- Keep the feature entirely Core/Trainer Host.

## Batch D — residual readiness stutter

- Use retained r35/r36 logs as baseline.
- Separate LLDB attach cost from first Lua/world-boundary delay.
- Do not add periodic polling.
- Target lifecycle signals for the one required status/replay transition.

## Closure order

Batch B → Batch C → Batch D → final consolidated regression → hosted CI recovery on exact head → PR #7 ready → merge only with explicit user authorization → sync PR #10.

## Permanent workflow corrections

- No test may point a destructive filesystem operation at a real user directory.
- Filesystem tests must receive a temporary root explicitly.
- For target-Mac full suites, keep a before/after hash sentinel on Hades II saves until this release closes.
- GitHub remains the source of truth; code/docs/version state are updated there before each tester handoff.
- Prefer the development environment + GitHub connector for normal development. Use RDC only for target-Mac-specific build/game work.
- Each tester handoff is one exact HEAD + one prebuilt signed App/ZIP + SHA256.
- Superseded RCs are never reused for PASS.
- Fix demonstrated/root-caused failures with RED→GREEN coverage.
- Keep GitHub/project status durable after each checkpoint.
