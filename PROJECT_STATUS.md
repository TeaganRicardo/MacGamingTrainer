# MacGamingTrainer Project Status

Updated: 2026-09-30

This file is the canonical **current operational handoff**. It is not a merge ledger or roadmap.

- Start at `AGENTS.md`.
- Stable engineering rules live in `ENGINEERING_INVARIANTS.md`.
- Game-module/build ownership lives in `GAME_MODULES.md`.
- Release/version rules live in `VERSIONING.md`.
- Planned work and sequencing live in planning issue #124.
- Historical implementation/evidence remains durable in Git history, closed issues/PRs, releases, prior revisions of this file, and `docs/audits/`.

Always resolve current remote `main` before work; do not treat a SHA written in an old handoff as the current branch tip.

## Current operational state

- Product release identity: `Info.plist` owns SemVer `0.1.0` and bundle build `3`. Do not duplicate these values into another source of truth.
- Host protocol: 6.
- Hades II module protocol: 6.
- Hades II desired-state schema: 5.
- Hades II Profile schema: 6.
- Hades II resident runtime revision: 54.
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

Current main contains revision 54:

- revision 52: Echo synthetic `LastReward` fallback cleanup became transaction-local;
- revision 53: resident replacement fails closed when prior cleanup fails;
- revision 54: Trainer invulnerability runtime identity migrated to `invincibility`.

Revisions 52–54 remain pending the user's consolidated final real-game acceptance. Automated verification does not replace this manual acceptance.

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
- **Next selected feature task: #227** — the first bounded current-run mounted-effect management slice.
- #221 remains the feature parent; later owner/lifecycle families remain explicitly split across #228 and #236–#240 rather than collapsing into a raw-trait mutator.

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
