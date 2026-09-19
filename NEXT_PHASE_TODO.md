# Next Development Stage

Current release integration is paused after revision-35 manual acceptance exposed multiple correctness/design gaps. Work proceeds in isolated repair batches; PR #7 remains DRAFT.

## Immediate: finish Batch A

Branch: `fix/batch-a-native-modals`. Runtime: revision 36.

Automated verification and first clean build are already PASS. Remaining steps:
1. commit current handoff/plan state;
2. rebuild from that exact final HEAD;
3. package `MacGamingTrainer-0.1-build2-rc-r36.zip`;
4. verify ZIP integrity, byte size and SHA256;
5. update PR #7 and relevant issue comments with exact artifact identity;
6. give the tester only the compiled App and the six focused Batch A checks.

Batch A manual retest scope:
- open sell UI and Cancel without selling;
- open sell UI, sell one boon, then exit normally;
- open one loot-style native three-choice source (Artemis/Athena preferred);
- open one fixed-choice source (Arachne/Narcissus preferred);
- confirm a normal special boon still direct-adds;
- confirm Heracles/Moros contain no native-choice action row.

Do not ask the tester to rerun game speed, sounds, God Mode, or the full lifecycle suite during Batch A unless a smoke regression appears.

## Batch B — game speed + God Mode

Re-plan implementation from the installed game scripts before coding.
- Redefine game speed as trainer-global state that remains effective outside combat and does not depend on the current Hero being capturable.
- Preserve native slowdown/time effects underneath the trainer factor instead of overwriting them.
- Audit current installed scripts for hostile debuff/control pathways (polymorph, slow/time stop, poison/DOT and other forced control).
- Replace the two-name God Mode effect list only after identifying a source-aware/common application boundary that avoids blocking player-selected/self effects.
- Prefer static/script-contract coverage for the complete audited set, then ask for only representative manual checks.

## Batch C — Trainer Host feedback sounds

- Replace Glass/Pop/Tink with one coherent bundled sound family.
- enabled/deferred/disabled must remain distinguishable at low volume.
- Preserve post-result semantics: never play a success sound before backend confirmation.
- Ensure completion playback is not swallowed by request latency or overlapping callbacks.
- Keep this entirely Core/Trainer Host; no Hades-specific sound semantics.

## Batch D — residual readiness stutter

- Use the retained r35 logs as baseline.
- Treat attach (~0.5s in observed runs) separately from first Lua/world boundary (~3–4s in observed runs).
- Do not add periodic polling.
- Target: attach can complete without synchronously freezing on world readiness; a lifecycle signal triggers the one required status/replay when ready.

## Closure order

Batch A focused PASS → Batch B focused PASS → Batch C sound PASS → Batch D lifecycle/performance PASS → final consolidated regression → hosted CI recovery on exact head → mark PR #7 ready → merge with explicit user authorization → sync PR #10.

## Permanent workflow

- Each tester handoff is one exact HEAD + one prebuilt signed `.app` ZIP + SHA256.
- Superseded RCs are never reused for PASS.
- User reports can be concise; assistant maps them to test IDs and gathers logs via RDC.
- Fix only demonstrated/root-caused failures, using RED→GREEN tests.
- Retest affected paths plus high-value smoke only; carry forward unrelated PASS evidence when code did not touch it.
- Keep GitHub status durable after each checkpoint.
