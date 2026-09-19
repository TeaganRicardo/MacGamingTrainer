# Next Development Stage

PR #7 remains DRAFT. r36 native modal functionality is manually accepted; r37 is a safety/UI follow-up.

## Immediate — finalize r37

Branch: `fix/batch-a-native-modals`. Runtime: revision 37.

Remaining release-candidate steps:
1. commit this handoff status;
2. run fresh exact-HEAD Linux/macOS verification, with the real-save-tree hash sentinel around macOS tests;
3. clean-build Build 2 from the exact final HEAD;
4. verify 0.1 / Build 2, one Hades II module, runtime 37, arm64, debugger entitlement, strict codesign;
5. create `Mac Gaming Trainer r37.app` and `MacGamingTrainer-0.1-build2-rc-r37.zip`;
6. verify ZIP integrity and record exact SHA256/size;
7. push the exact candidate to the release branch and update PR #7;
8. keep PR #7 DRAFT.

Focused r37 manual smoke only:
- confirm `出售祝福` sits below the three generation controls and its button is `出售`;
- confirm special native-choice rows render as `XXX的祝福 · XXX Boon` and the action button is always `生成`;
- confirm Heracles/Moros do not appear as special-boon source groups;
- with Hades II stopped, use `直接恢复` on the known-good `修改器测试` backup and confirm no new `恢复前自动备份` appears; launch once and confirm the save is present.

Do not retest r36 selling/native-choice behavior unless the above smoke exposes a regression.

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

r37 focused smoke → Batch B → Batch C → Batch D → final consolidated regression → hosted CI recovery on exact head → PR #7 ready → merge only with explicit user authorization → sync PR #10.

## Permanent workflow corrections

- No test may point a destructive filesystem operation at a real user directory.
- Filesystem tests must receive a temporary root explicitly.
- For target-Mac full suites, keep a before/after hash sentinel on Hades II saves until this release closes.
- Each tester handoff is one exact HEAD + one prebuilt signed App/ZIP + SHA256.
- Superseded RCs are never reused for PASS.
- Fix demonstrated/root-caused failures with RED→GREEN coverage.
- Keep GitHub/project status durable after each checkpoint.
