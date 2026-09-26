# MacGamingTrainer Project Status

Updated: 2026-09-26

This is the canonical current-development handoff. It records present state only. Stable engineering rules live in `ENGINEERING_INVARIANTS.md`; release/version rules live in `VERSIONING.md`; planned work and sequencing live in planning issue #124; historical audit evidence lives under `docs/audits/`.

Start every development thread at `AGENTS.md`.

## Current state

- Default branch: `main`.
- Current main at this handoff: `290fffdb60416ce332942df9bf6fd28f6cfa2dd9`.
- Hades II resident runtime revision: 49.
- Hades II desired-state schema: 4.
- Host protocol: 5. Hades II module protocol: 5.
- Verified Hades II compatibility target: 1.143476 / Steam build 25481925 / arm64 UUID `35CD2E50-2D78-3A63-835B-3EB1224C6D65`.
- The retained target-build census/reference data remains under `docs/reference/hades2/1.139672-24556151/`. Static compatibility work for 1.143476 confirmed that the currently consumed native terminology identities/values and curated reward/runtime dependencies remain valid; do not silently treat the directory name as the current executable identity.
- The Hades terminology registry is now an executable governance source for stable term identity, ownership, bilingual presentation, lifecycle, alias targets, provenance, and allowed/forbidden surfaces.
- Runtime observation is explicit: `observe_runtime()` performs fresh resident status observation with resident synchronization maintenance while suppressing Host adoption/replay/persistence and desired-state projection.
- Core Save Management remains optional cross-game infrastructure; Hades save codec/schema/edit semantics remain Hades-owned.
- `ContractFixtures/reference_module` remains the executable proof that a second module does not require Hades-shaped Core APIs.
- Current product release metadata is owned only by `Info.plist`; do not duplicate its current values in status documentation.

## Recent accepted implementation state

The 2026-09-26 governance/hardening sequence now present on `main` includes:

- Process Time Warp zero-hook installation can recover to a retryable state without duplicating dyld callback registration or weakening successful-install immutability (#167).
- The Hades terminology registry carries authoritative governance metadata and validates native bilingual provenance, compatibility alias targets, and surface restrictions (#168).
- Hades II 1.143476 / Steam build 25481925 is the verified macOS target; executable identity and transport symbol evidence were updated without changing resident Lua (#172).
- Runtime observation vs Host adoption/replay/persistence semantics are explicit; Diagnostics and live Profile reconciliation consume `observe_runtime()` instead of the former adapter-facing `read_only` execution mode (#181).

PR #172 head `03e31b6963f888becc4e8027019a94fc48647645` passed Linux contracts, module build matrix, Build 2 macOS, target-machine static compatibility checks, and user-run real-game smoke acceptance before merge.

PR #181 head `6293204733fa1b9bdfb245aaf8d3ed9047ae50f9` passed Linux contracts, module build matrix, and Build 2 macOS before merge.

## Resident runtime acceptance

The latest behavior-changing Hades resident source accepted in the real game remains resident revision 49 from the terminology-normalization line. The newer compatibility and governance work did not change `Backend/games/hades2/runtime/hades.lua`, so no resident revision bump was required.

The previously recorded resident-revision-49 real-game acceptance remains valid for resident behavior. In addition, the 1.143476 / 25481925 compatibility artifact from PR #172 received user-run attach/status and representative feature smoke acceptance on the new game build.

Automated tests are not substitutes for real-game acceptance when a future change modifies resident Lua semantics.

## Architecture/governance state

Completed foundations:

- A01 terminology governance foundation: complete.
- A02 authoritative terminology registry: complete via #168.
- A03 Runtime / Protocol Boundary: complete. `GAME_MODULES.md`, the reference fixture, Backend Core contracts, and the module matrix prove Core remains game-agnostic.
- A04 Runtime Observation / Synchronization Semantics: complete via #181.
- Profile versioning/migration compatibility: complete via #108 / PR #109.
- C01 durable feature identity parity: complete via #132 / PR #159.

Current governance frontier:

1. #175 — separate localized user presentation, stable machine error identity, and developer diagnostics.
2. #131 — complete the Host bilingual foundation.
3. #176 — migrate Core/shared Host presentation.
4. #177 — migrate Hades presentation through the terminology registry.
5. #178 — evidence-driven repository naming governance.
6. #179 — package/module-resource/artifact naming governance.
7. #180 — terminology and presentation drift CI.

Per current project direction, ordinary Phase D feature expansion is intentionally held until #180 closes. This is a governance-first sequencing choice, not a repository-wide emergency freeze.

## Current development gate

For every task:

1. confirm current remote `main` HEAD;
2. create one focused branch/PR and serialize overlapping implementation work;
3. read the owning production files and nearest behavior tests;
4. preserve the contracts in `ENGINEERING_INVARIANTS.md`;
5. use RED -> GREEN for demonstrated correctness defects;
6. run the applicable Linux/module/macOS gates on the final changed SHA;
7. hand the actual PR head to an independent review thread before merge;
8. use manual user execution for any game launch, in-game test, or visual acceptance requirement.

Do not stack new implementation on unmerged overlapping PR heads.

Hades II Save Editor is not implicitly authorized by the current governance sequence. If selected later, its binary mutation design still requires separate explicit design/safety approval.

## Known non-blocking risks

- Docs-only changes keep the normal required check names but use the repository fast path instead of running heavy Linux/module/macOS work.
- Some Core filesystem metadata updates do not parent-directory fsync after every atomic replace. This is an extreme sudden-power-loss durability ceiling, not a demonstrated normal-operation corruption bug.
- Hades Profile storage does not mirror every Core Save subdirectory-symlink containment guard. It runs with the same user authority and has no demonstrated exploit/data-loss path.

Promote these only when new evidence or a selected requirement justifies work.

## Historical evidence

Historical material is evidence only and must not be used as current instructions.

The retained repository-level synthesis is:

- `docs/audits/2026-09-21-ai-development-governance.md` — system map, debt/test audit, and governance rationale.

Closed PRs and Git history preserve completed implementation detail. Do not add new round handoffs, audit-continuation files, or duplicate status documents for ordinary development.
