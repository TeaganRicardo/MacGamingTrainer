# MacGamingTrainer Project Status

Updated: 2026-10-05

This file is the canonical **current operational handoff**. It is not a merge ledger or roadmap.

- Start at `AGENTS.md`.
- Stable engineering rules live in `ENGINEERING_INVARIANTS.md`.
- Game-module/build ownership lives in `GAME_MODULES.md`.
- Release/version rules live in `VERSIONING.md`.
- Planned work and sequencing live in planning issue #124.
- Historical implementation/evidence remains durable in Git history, closed issues/PRs, releases, prior revisions of this file, and `docs/audits/`.

Always resolve current remote `main` before work; do not treat a SHA written in an old handoff as the current branch tip.

## Current operational state

- Product release identity: `Info.plist` owns SemVer `0.2.1` and bundle build `5`. Do not duplicate these values into another source of truth.
- Host protocol: 6.
- Hades II module protocol: 9.
- Hades II desired-state schema: 5.
- Hades II Profile schema: 6.
- Hades II resident runtime revision: 77.
- Current Trainer-owned invulnerability identity: `invincibility` / 无敌模式 / Invincibility. Legacy `godMode` is accepted only at versioned migration/import boundaries and is free for a future native God Mode implementation if deliberately added.
- Verified Hades II target: game 1.143476 / Steam build 25481925 / arm64 UUID `35CD2E50-2D78-3A63-835B-3EB1224C6D65`.
- `docs/reference/hades2/1.139672-24556151/` is a frozen census/research snapshot, not current planning authority. Its packaged `ui_terminology.json` remains an intentional executable-governance resource.
- `catalog_legality.csv` is generated deterministically from curated legality policy plus frozen authoritative name/version sources. The policy owns research conclusions; generated presentation/version columns are not hand-maintained.
- Hades terminology ownership, bilingual identity, compatibility aliases and allowed surfaces are governed through the Hades terminology registry.
- Core Save Management is optional cross-game infrastructure. Hades save schema/codec/provider semantics remain Hades-owned.
- `ContractFixtures/reference_module` remains the executable proof that shared Core/build paths do not require Hades-shaped semantics.
- Process Time Warp mechanics are Core-owned; Hades owns its desired meaning/persistence and runtime integration.
- Runtime observation distinguishes durable desired state from observed active/dormant state. Outcome-unknown non-idempotent mutations are never blindly replayed.

Recent governance simplification (#277, #279, #281, #283) changed verification/test structure only, not product/runtime semantics: recurring PR verification is leaner, redundant evidence/meta-tests were removed, CI/provenance contracts were consolidated, and one historical regression grab-bag was moved into owning tests.

## Real-game acceptance baseline

The latest Hades resident source accepted in the real game is **revision 51**, accepted on 2026-09-28 from commit `a6cf37b41639229bd64938d9587a9735fb16dd91`.

Accepted resident source SHA256:

`de4d0485e16d3dec3c9fda96e7d9d1aee321c9dab7fcdb428bf065d8f6347e37`

Current source contains resident revision 77. Revisions 52–77 remain pending the user's consolidated final real-game acceptance. Notable later resident changes include:

- revision 55: first live boon level/rarity/force-removal slice;
- revision 56: separate exact-boon acquisition;
- revision 57: seamless Cast recast follows transformed/thrown delivery weapons;
- revision 58: resident main-chunk local pressure reduced below stock Lua 5.2's compile limit;
- revision 59: Cast diagnostics sequences use the resident JSON array contract;
- revision 60: current-run boon level mutation accepts one explicit higher target level while preserving live-target revalidation and game-owned recomputation; #306 also reworks the manager UI around that contract;
- revision 61: Trainer infinite ammo stops spoofing the native `UnlimitedAmmo` trait value so Argent Skull fire/death/pickup bookkeeping remains game-owned while negative ammo deltas stay suppressed for uninterrupted firing;
- revision 62: Chaos exact acquisition and mounted lifecycle management preserve paired curse→blessing ownership, instance identity, remaining encounters, effect recomputation, explicit cancellation, and deliberate immediate transformation.
- revision 63: Selene exact acquisition and mounted management use the native SlottedSpell / Path of Stars owner state, with typed spell replacement and talent tree synchronization; real-game acceptance remains pending.
- revision 64: Daedalus Hammer exact acquisition follows current WeaponUpgrade eligibility for the equipped weapon/aspect; mounted Hammer rarity/removal use game-owned recomputation/teardown, while runtime Aspect state remains observation-only and permanent weapon progression is untouched.
- revision 65: Arachne costume exact acquisition and mounted removal use the costume owner lifecycle so trait teardown, armor-source state and active appearance remain coherent.
- revision 66: Echo previous-run exact targets materialize concrete eligible God boons directly from the latest run history without opening the native random choice screen; automated and real-game acceptance remain pending.
- revision 67: Well / temporary mounted effects support owner-aware RemainingUses editing, explicit cancellation without expiry side effects, and deliberate immediate expiry through native OnExpire teardown; automated and real-game acceptance remain pending.
- revision 68: equipped Familiar effects are owned by the active Familiar bundle rather than trait-name heuristics; safe runtime stack edits use native trait recomputation, while forced removal tears down the equipped runtime owner and linked Toula Last Stand without changing Familiar unlocks or purchased upgrades; real-game acceptance remains pending.
- revision 69: the currently selected Keepsake is recognized through `GameState.LastAwardTrait`; forced current-run removal delegates to native `UnequipKeepsake` while preserving durable Keepsake selection and chamber progression. Runtime level/rarity semantics remain explicitly deferred under #329; real-game acceptance remains pending.
- revision 70: selected Keepsake runtime rank is an exact rarity override rebuilt through native Unequip/Equip owner semantics with `PersistentKeepsakeKeys` preservation and no `KeepsakeChambers` mutation; StackNum-style level remains not meaningful. #329/#332 implementation is complete pending consolidated real-game acceptance.
- revision 71: mounted Arcana effects are owned only by an exact equipped `MetaUpgradeCardData[card].TraitName` mapping. Safe declarative cards can receive a current-run rank/rarity override through native owner-shaped teardown/rebuild with adjacency and derived health/mana/weapon refreshes, while permanent Arcana state remains read-only; one-shot/setup-state cards and runtime-only removal fail closed. #330 implementation is complete pending automated and consolidated real-game acceptance.
- revision 72: direct special-NPC mounted management is derived from native source identity and processed runtime semantics rather than a trait allowlist. Meaningful declarative level/rarity/removal operations are exposed; one-shot acquisition and unsupported setup/counter lifecycles fail closed; Icarus CostumeArmor teardown refreshes costume owner state. The residual #239 `directSpecial` deferred bucket is removed.
- revision 73: final #236–#240 convergence removes the stale closed-#239 Arachne costume deferral marker; no mutation capability or durable progression semantics change.
- revision 75: Trainer mutations close an open native Trait Tray through its owner lifecycle before handing off the operation; an unsuccessful close refuses the mutation. This supersedes the earlier fail-closed Trait Tray behavior. Real-game acceptance remains pending.
- revision 76: deterministic Chaos acquisition accepts an explicit current-build blessing + curse pair in one non-replayable request, revalidates both against the live TrialUpgrade pools/eligibility immediately before mutation, mounts exactly the selected curse, and queues exactly the selected blessing through the native curse lifecycle shape. Real-game acceptance remains pending.
- revision 77: deterministic Chaos pair acquisition delegates repeat-instance eligibility to the native transforming-trait rules instead of rejecting every already-owned phase. Existing instances keep their identities; request deduplication remains separate from trait ownership. Real-game acceptance remains pending.

Automated verification does not replace this manual acceptance.

The 1.143476 / Steam 25481925 compatibility target was previously accepted with target-machine static checks plus user-run attach/status and representative feature smoke checks. Future resident semantic changes still require user-run Hades II acceptance.

No game launch, in-game test, or visual acceptance is performed through RDC.

## Verification model

Evidence scope and evidence identity are separate.

### Ordinary pull requests

The three stable workflow/check names run on the exact PR head:

- **Linux contracts** — broad Linux-portable behavior suite plus PR-only resident revision diff discipline;
- **Build 2 macOS** — macOS-only contracts plus real Hades app build/package/sign verification when the changed seam requires it;
- **Module build matrix** — reference-fixture build/isolation when the module/Core/build seam requires it.

Ordinary PRs do **not** regenerate the mutation audit, retained RC ZIP, provenance/checksum package, or QA artifact unless the task directly changes those mechanisms.

There is no automatic duplicate `push(main)` rerun after every merge.

### Convergence / release / manual-QA artifact

Explicitly dispatch the same workflows on one selected SHA.

A no-diff manual dispatch fails closed to the applicable behavior/build lanes. Build 2 additionally runs the mutation audit and creates/verifies the exact-SHA RC/provenance/checksum artifact; the module matrix can retain reference-module provenance/artifact evidence.

The resident revision comparison remains PR-only because it requires a semantic base diff.

Mutation testing audits selected test sensitivity. It is not an ordinary feature-PR correctness gate.

## Current development gate

Planning issue #124 is the sequencing authority.

- #214 exact-head governance convergence is complete.
- #262 / PR #271 identity migration is complete.
- Control-plane/catalog/CI/test hygiene through #273, #275, #277, #279, #281 and #283 is complete.
- #227 and #228 are complete; #229 is complete with follow-up correctness fixes #291/#292.
- #306 corrective current-run boon manager work is complete in this source.
- #230 pickup-compatible infinite-ammo correction is complete in this source.
- #236 Chaos lifecycle acquisition and mounted management is complete in this source.
- #344–#347 manual-QA follow-ups are implemented in this source: recognizable current-run effect labels, stable Boon Management geometry, compact two-level Exact Boon navigation, and deterministic Chaos blessing + curse pair acquisition. Resident revision 77 still requires the consolidated user-run exact-build acceptance.
- #348 native Trait Tray close/handoff is implemented in this source; the earlier #341 fail-closed shipping behavior is superseded. Consolidated real-game acceptance remains pending.
- #232 game-related shortcut settings, module log access and optional Save Management are composed in the game's management area. Host retains the single Save manager and backend session; consolidated visual acceptance remains pending.
- #312 boon-management UX consolidation is complete in this source: Exact Boons uses a compact source → boon/effect navigation flow with search, while mounted effects use one two-row grouped selector/editor with stable common controls and Hades-owned contextual actions. Chaos acquisition is intentionally separated into its dedicated blessing + curse pair control.
- #237 Selene Hex / Path of Stars exact acquisition and mounted management is complete in this source at resident revision 63; final real-game acceptance remains part of the consolidated manual pass.
- #238 weapon/aspect-aware Hammer exact acquisition and mounted-effect management is complete in this source at resident revision 64; final real-game acceptance remains part of the consolidated manual pass.
- #239 is split into focused owner-lifecycle children: #318 Arachne costumes, #319 Echo previous-run acquisition, #320 Well/temporary effects, and #335 direct special-NPC mounted management.
- #318 Arachne costume exact acquisition and owner-aware removal is complete in this source at resident revision 65; final real-game acceptance remains part of the consolidated manual pass.
- #319 Echo previous-run exact acquisition is complete in this source at resident revision 66: concrete eligible previous-run God boons materialize directly without opening the native random choice screen; final real-game acceptance remains part of the consolidated manual pass.
- #320 Well/temporary lifecycle management is complete in main at resident revision 67; final real-game acceptance remains part of the consolidated manual pass.
- #335 completes the residual direct special-NPC mounted-management frontier at resident revision 72: native source/processed semantics decide level, rarity and removal capability; one-shot/external/setup-owned effects receive explicit not-applicable dispositions rather than a deferred bucket.
- #239 implementation children are complete; parent manual acceptance remains pending and is intentionally consolidated with the later resident acceptance pass.
- #327 implements the equipped Familiar runtime owner at resident revision 68; final real-game acceptance remains part of the consolidated manual pass.
- #329 selected-Keepsake owner-aware removal is implemented at resident revision 69.
- #332 completes the meaningful Keepsake runtime upgrade surface at resident revision 70: rank/rarity can be overridden through owner rebuild without advancing durable progression, while a separate StackNum-style level is explicitly not meaningful.
- #330 implements exact Arcana runtime ownership at resident revision 71. Safe declarative card effects can receive a current-run rank override without changing durable `Unlocked`, `Equipped`, `Level`, adjacency or Grasp ownership; callback/setup-state cards fail closed, and runtime-only removal remains unavailable because durable equipped ownership would reapply it.
- #240 implementation children are complete; parent real-game acceptance remains intentionally consolidated with the later resident acceptance pass.
- #221 remains the feature parent; owner/lifecycle families stay explicitly split across #237–#240 rather than collapsing into a raw-trait mutator.

Do not start another global governance phase before the selected feature queue. New governance work may preempt only when concrete correctness, ownership, runtime/data-safety, compatibility, presentation-identity, packaging or verification-trust evidence requires it.

The user authorizes independently reviewed, automated-green merges before one consolidated final manual acceptance after the selected index work. Missing gameplay/visual verification alone does not block unrelated eligible development, but unexecuted manual checks remain pending and must not be described as accepted.

Hades II Save Editor is not implicitly authorized by the current sequence. Any future binary save mutation design still requires explicit design/safety approval.

## Current non-blocking risks

- Some Core filesystem metadata updates do not parent-directory fsync after every atomic replace. This is an extreme sudden-power-loss durability ceiling, not a demonstrated normal-operation corruption bug.
- Hades Profile storage does not mirror every Core Save subdirectory-symlink containment guard. It runs with the same user authority and has no demonstrated exploit/data-loss path.

Promote either item only when new evidence or a selected requirement justifies work.

## Historical evidence policy

Historical material is evidence, not current instruction.

The repository-level synthesis remains `docs/audits/2026-09-21-ai-development-governance.md`. Exact old SHAs, workflow runs, artifacts, checksums, review links and completed-PR chronology remain recoverable from GitHub and prior versions of this file. Do not copy them back into current status or create round/continuation handoff files for ordinary development.
