# Next development stage

Current product baseline: **0.1**. Stable `main` remains Build 1. Build 2 release integration remains gated by the recovered pre-acceptance hardening branch.

## Immediate Phase 0 closure

### Candidate

- Frozen previously verified release head: `efc21268b8c075bd8b8d5ff3726d4548cb6b88e7` / runtime revision 33.
- Current hardening code head: `b09e49b15478588dfbd42ee44ef8a70d5f34e07a` / runtime revision 35.
- Branch: `audit/preacceptance-hardening`.
- The hardening branch is 15 commits ahead of the frozen release head and zero behind.
- Revision-33 RC is superseded for final acceptance.

The hardening audit found and fixed release-path issues in lifecycle readiness, same-process Lua session hook ownership, game-speed reset recovery, exit cleanup, hotkey result reporting, process-query failure handling, staged-restore corruption handling, and contract-suite coverage.

### Target-Mac preflight — PASS

Completed on the authorized target Mac:

1. clean branch/worktree verified;
2. full Linux contracts PASS;
3. full macOS contract suite PASS;
4. two clean Hades II arm64 builds PASS;
5. 0.1 / Build 2 package checks PASS;
6. exactly one packaged game module;
7. runtime revision 35 packaged;
8. strict codesign + debugger entitlement PASS;
9. no tracked-source mutation after either build.

The final RC is packaged only after the final handoff/docs commit. Exact artifact HEAD, size and SHA256 are recorded in PR #7.

### After preflight passes

1. fast-forward `feature/post-v0.1-improvements` to the verified hardening head;
2. update PR #7 / #1 / #11 to the exact revision-35 RC;
3. run the full manual acceptance checklist in PR #7 / PROJECT_STATUS.md and preserve `trainer.log`;
4. fix only a demonstrated acceptance regression if one appears;
5. after manual PASS and healthy hosted CI on the exact current head, mark PR #7 ready and merge to `main`;
6. verify merged `main` and capture the Build 2 release snapshot.

### Non-blocking follow-up

Issue #17 tracks a partial hand-edited schema-4 Profile shortcut collision. A RED→GREEN fix is retained on `fix/profile-shortcut-partial-conflict`. Normal Trainer-created Profiles contain the complete shortcut payload, so #17 does not block Phase 0.

## Phase 1 after Build 2

Draft PR #10 / issue #9 remains the mechanical cross-game module proof. Keep it draft during Phase 0.

After Build 2 lands:
1. synchronize PR #10 with the final Build 2 base;
2. prove it is conflict-free;
3. rerun Linux contracts and both macOS matrix entries;
4. merge #10;
5. close #9;
6. advance roadmap #8 to Phase 2.

## Deferred roadmap

- Phase 2: shared optional save-management Host capability with game-owned parsing/semantics.
- Phase 3: Hades II full save editor behind that capability.
- Phase 4: explicit Hades-I architecture gate.
- Phase 5: Hades I vertical slice.

## Reliability constraints

- No periodic LLDB/Lua polling.
- No unsafe replay of non-idempotent mutations.
- No game semantics in Core/Host.
- No speculative LLDB optimization; #4 remains closed with a measured baseline.
- Runtime source changes require a revision bump.
