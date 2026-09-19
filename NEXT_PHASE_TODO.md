# Next development stage

Current product baseline: **0.1**. Build 2 lives on `feature/post-v0.1-improvements`; stable `main` and the published v0.1 release remain Build 1 until Phase 0 target-Mac acceptance succeeds.

## Immediate Phase 0 closure

### Code complete

- Background auto-connect is event-driven and bounded to a true target-process launch.
- Same-PID Lua runtime resets rebuild inside the existing debugger attachment.
- Persistent desired state is replayed in one Lua/LLDB batch.
- Shortcut defaults and settings-list order share `ShortcutAction.uiOrder`; untouched defaults flow 1-9 then A-Z.
- Generic hotkey sounds distinguish enabled / deferred / disabled.
- Native boon selling uses `OpenSellTraitMenu`.
- Special blessings keep direct-add and expose audited native three-choice where the game has a real native flow.
- God Mode blocks only audited hostile control effects through native effect blocks.
- Runtime revision is 33.
- Revision 33 preserves the native NPC source name through choice eligibility/rarity generation and applies the trainer bookkeeping name only immediately before the native menu opens.

### Required before manual testing

1. Obtain fresh GREEN Linux contracts on the exact final branch head.
2. Obtain fresh GREEN macOS Build 2 on the same head.
3. Produce a replacement Build 2 RC and record its artifact ID + inner SHA256.
4. Update PR #7, #1 and #11 with that exact head/artifact.
5. Do not use revision-32 artifact 10578439397 for final acceptance.

### Manual target-Mac acceptance

Run the complete checklist recorded in PR #7 / PROJECT_STATUS.md. Preserve `trainer.log`.

If acceptance passes:
1. close #1 and #11 with the log/result summary;
2. mark PR #7 ready;
3. merge PR #7 to `main`;
4. verify the merged `main` result;
5. capture the Build 2 release snapshot per VERSIONING.md.

If acceptance fails:
- leave PR #7 draft and #1/#11 open;
- attach the complete log and reproduce from the exact RC;
- fix only the demonstrated regression before another RC.

## Phase 1 after Build 2

Draft PR #10 / issue #9 contains the mechanical cross-game module proof. Keep it draft during Phase 0.

Before Phase 1 merge:
1. synchronize its head with the final Build 2 base;
2. ensure the PR is conflict-free;
3. rerun Linux contracts and both macOS matrix entries;
4. after Build 2 lands on `main`, retarget/update as required and merge;
5. then begin Phase 2 save-management capability work.

## Deferred roadmap

- Phase 2: shared optional save-management Host capability with game-owned parsing/semantics.
- Phase 3: Hades II full save editor behind that capability.
- Phase 4: explicit Hades-I architecture gate.
- Phase 5: Hades I vertical slice.

## Reliability constraints

- No periodic LLDB/Lua polling.
- No unsafe replay of non-idempotent mutations.
- No game semantics in Core/Host.
- No speculative LLDB optimization; #4 is already closed with a measured baseline.
- Runtime source changes require a revision bump.
