# MacGamingTrainer Project Status

## Current baseline

- Product version: 0.1
- Development build: 2
- Published/stable baseline: v0.1 / Build 1 on `main`
- Active development branch: `feature/post-v0.1-improvements`
- Parent PR: #7 (draft until target-Mac Phase 0 acceptance passes)
- Host protocol: 5
- Hades II module protocol: 5
- Desired-state schema: 3
- Profile schema: 4
- Hades II resident Lua revision: 33
- Target game build last audited: Hades II 1.139672 / Steam build 24556151

## Phase 0 implementation state

Implemented and covered by contracts/builds before the final revision-33 closure rerun:

- event-driven background auto-connect: only a true target-process launch may consume the bounded background-connect opportunity;
- Hades readiness from Hades II.log events; no periodic LLDB/Lua polling;
- direct `sgg::World::Update(float)` debugger boundary;
- same-PID Lua-generation recovery without a second debugger attach;
- durable desired-state recovery replayed in one Lua/LLDB batch;
- automatic shortcut ordering from `ShortcutAction.uiOrder` with explicit user overrides only;
- generic Host/Core hotkey feedback sounds: enabled / deferred / disabled;
- native Hades boon-sale screen through `OpenSellTraitMenu`;
- direct-add special blessings retained;
- native special three-choice for Artemis, Athena, Dionysus, Hades, Arachne, Narcissus, Echo, Medea, Circe and Icarus;
- Heracles/Moros remain direct-add only;
- God Mode engine-level effect blocks for `HecatePolymorphStun` and `MiasmaSlow`;
- full interactable reward catalog audit against the installed game data.

Revision 33 adds one closure fix found during interrupted-session review: native special-choice source identity now stays unchanged while the game generates/filters native choices. The trainer-only synthetic bookkeeping name is applied only after native eligibility/rarity generation, preventing `LootData/FieldLootData` lookup and requirement logic from seeing a fake source name.

## Known automated evidence

The previous integrated revision-32 candidate passed:
- Linux contracts: run 35425398150;
- macOS Build 2: run 35425398158;
- Host connection policy harness;
- Hades log watcher harness;
- native arm64 build;
- 0.1 / Build 2 package/version/module checks;
- `codesign --verify --deep --strict`;
- artifact packaging/upload.

That revision-32 artifact (ID 10578439397, inner SHA256 `e7d57b865a422d92b01a0ddb2843b37c0d7a34208949432333b27b312f91d2f8`) is superseded and MUST NOT be used for final acceptance because revision 33 changed runtime behavior.

The revision-33 special-choice regression completed its RED→GREEN cycle:
- RED: native source-name ordering contract failed before the runtime fix;
- GREEN: `native_special_choice_contract_ok` after the fix.

Fresh equivalent revision-33 verification has now completed on the authorized target Mac from an exact detached worktree: full Linux contracts, Host policy harness, Hades log watcher harness, arm64 Hades II build, 0.1 / Build 2 package checks, one packaged module and strict codesign all passed. A replacement revision-33 RC was produced locally. GitHub Actions still intermittently fails jobs before checkout/any step with steps=null and no log blob; rerun cloud CI when runners recover for archival evidence, but do not treat those startup failures as code failures.

## Phase 0 issues

- #4 attach profiling: CLOSED with measured baseline. Do not reopen unless new measurements justify work.
- #1 passive/background ready lifecycle: OPEN until target-Mac acceptance.
- #11 background attach + same-PID recovery performance: OPEN until target-Mac acceptance.
- PR #7: OPEN/DRAFT; do not merge to `main` until #1/#11 pass.

## Pending manual acceptance

Use only the final revision-33 RC recorded below after the final handoff-head verification.

Acceptance must cover:
1. background launch and automatic connection;
2. first save entry and two same-process main-menu → save re-entries without the previous multi-second recovery stall;
3. at least one persistent modifier verified by actual gameplay effect, not UI color alone;
4. active/deferred/disabled hotkey sounds;
5. shortcut list/default order 1-9 then A-Z with explicit overrides preserved;
6. automatic state/indicator recovery after re-entry and no second debugger attach / `attach_denied`;
7. native boon selling;
8. direct-add and native special three-choice paths;
9. God Mode Hecate polymorph + Mourning Fields miasma blocking without suppressing ordinary player/self-selected effects;
10. preserved `trainer.log` for the complete run.

## Next phases

- Phase 1 cross-game isolation proof exists on draft PR #10 / issue #9. It must be synchronized with the final Phase 0 branch, reverified, and only merged after Build 2 lands on `main`.
- Phase 2 shared optional save-management capability: not started.
- Phase 3 Hades II full save editor: not started.
- Phase 4 pre-Hades-I architecture gate: not started.
- Phase 5 Hades I vertical slice: blocked by Phases 0-4.

## Non-regression constraints

- No periodic LLDB/Lua polling.
- No unsafe replay of outcome-unknown non-idempotent mutations.
- No game-specific semantics in Core/Host.
- Native modal commands are one-shot and never preference-replayed.
- Exit must never be permanently blocked by cleanup failure.
- Runtime source changes must bump the resident revision.


## Current revision-33 acceptance artifact

The exact final handoff head is recorded in PR #7 after the final docs-only closure commit and local revalidation.

Current locally produced RC location on the authorized target Mac:
- `~/Downloads/MacGamingTrainer-0.1-build2-rc-r33.zip`

The final SHA256/size are refreshed after this document commit so the RC, code head and handoff status remain aligned.

GitHub Actions archival rerun remains pending only because the service is currently creating some jobs with no workflow steps/log blob.
