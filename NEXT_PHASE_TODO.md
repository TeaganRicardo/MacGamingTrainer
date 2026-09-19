# Next Development Stage

PR #7 remains DRAFT. r38 was superseded before manual acceptance by the native-parity re-review; current tester candidate is runtime r39.

## Immediate — r39 focused acceptance

Branch: `fix/special-choice-native-r39`. Runtime: revision 39.

Why r39 supersedes r38:
- fixed NPC choices now preserve the game's own special-choice eligibility rules instead of adding ordinary-boon `IsTraitEligible`;
- repeat counters reset per run;
- Trait detection follows the native `Type` field and fails closed on missing TraitData;
- direct invocation of the six native NPC `*Choice` wrappers was explicitly rejected after installed-game audit because those wrappers depend on narrative-screen / live-NPC / room-presentation state.

Automated status:
- r39 native-parity contract RED on r38 → GREEN on r39;
- full Linux contracts: PASS;
- signed r39 Build 2 package: PASS on `e610f3aba74d5878d59d66d6476966ad06effec2`;
- full macOS suite + real-save-tree sentinel is deferred while Hades II is running; this is a safety defer, not a failed test.

Current tester artifact:
- `/Users/gao/Downloads/Mac Gaming Trainer r39.app`
- `/Users/gao/Downloads/MacGamingTrainer-0.1-build2-rc-r39.zip`
- SHA256 `5f1e8609a60e8b7f4387915b5d22a97d9d7865e7e46552025a068fe3930d1c73`

Focused r39 manual acceptance:
- fixed-choice source (Arachne/Narcissus is sufficient): obtain one blessing, reopen the same source, confirm the acquired blessing is not re-offered and the candidate set is no longer pinned to the first deterministic offer;
- start a new run and open the same source once: the trainer counter must have reset, so the first-open path again uses the native seed-9 behavior;
- loot-style source (Artemis/Athena is sufficient): obtain one trait, reopen, confirm native `SetTraitsOnLoot` produces a valid pool without offering the owned trait;
- no need to repeat accepted r37 save/UI coverage unless this smoke exposes a regression.

After focused PASS, continue directly to Batch B.

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

r39 focused special-choice acceptance → Batch B → Batch C → Batch D → final consolidated regression → hosted CI recovery on exact head → PR #7 ready → merge only with explicit user authorization → sync PR #10.

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
