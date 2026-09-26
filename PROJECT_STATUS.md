# MacGamingTrainer Project Status

Updated: 2026-09-27

This is the canonical current-development handoff. It records present state only. Stable engineering rules live in `ENGINEERING_INVARIANTS.md`; release/version rules live in `VERSIONING.md`; planned work and sequencing live in planning issue #124; historical audit evidence lives under `docs/audits/`.

Start every development thread at `AGENTS.md`.

## Current state

- Default branch: `main`.
- Baseline main used for this handoff: `6c1f3979592b4198d0802fa856ea84d6a4de3751`.
- Hades II resident runtime revision: 49.
- Hades II desired-state schema: 4.
- Host protocol: 6. Hades II module protocol: 5.
- Verified Hades II compatibility target: 1.143476 / Steam build 25481925 / arm64 UUID `35CD2E50-2D78-3A63-835B-3EB1224C6D65`.
- The retained target-build census/reference data remains under `docs/reference/hades2/1.139672-24556151/`. Static compatibility work for 1.143476 confirmed that the currently consumed native terminology identities/values and curated reward/runtime dependencies remain valid; do not treat the directory name as the current executable identity.
- The Hades terminology registry is the executable governance source for stable term identity, ownership, bilingual presentation, lifecycle, alias targets, provenance, and allowed/forbidden surfaces.
- Runtime observation is explicit: `observe_runtime()` performs fresh resident status observation with resident synchronization maintenance while suppressing Host adoption/replay/persistence and desired-state projection.
- Host protocol failures use stable machine `code`, user-facing `presentation`, optional developer `diagnostic`, and optional structured `recoveryPath`; module protocol revisions remain independent.
- Process Time Warp zero-hook installation is retryable without duplicate dyld callback registration or weakening successful-install filter immutability.
- Core Save Management remains optional cross-game infrastructure; Hades save codec/schema/edit semantics remain Hades-owned.
- `ContractFixtures/reference_module` remains the executable proof that a second module does not require Hades-shaped Core APIs.
- Current product release metadata is owned only by `Info.plist`; do not duplicate its current values in status documentation.

The current hardening baseline also includes:

- Core Save preserves staged recovery evidence across uncertain failures, persists snapshot payloads before manifests, contains stale staging/rollback recovery, exposes deliberate reveal/delete for invalid inventory rows, keeps Swift busy state tied to outstanding requests, and rejects reveal paths outside the effective Trainer data root or through symlink escape.
- Hades transport/diagnostics preserve trust boundaries after host-side decode failure, refresh diagnostics from current runtime state, distinguish absent warning fields from explicit clears, reset runtime-only observation when the backend terminates, and use explicit aggregate operation budgets.
- Backend JSONL input is bounded; Host trainer logs rotate within bounds; Process Time Warp uses serialized installation and fixed system tool paths.
- Host zh-CN/English resources and a persisted live language selector are packaged for participating Host presentation. #131 owns completion of the full Host/reference-fixture bilingual foundation and its acceptance.
- Hades durable feature identity has executable parity coverage across Swift controls/model paths, Python router/adapter paths, resident Lua consumers, and the separate Core-owned `gameSpeed` path without adding another production feature schema.
- Hades terminology is packaged through module `appResources`; selected-module builds verify the intended app identity instead of accepting arbitrary stale output.
- macOS build/sign publication uses isolated staging, removes only signing-blocking FinderInfo/ResourceFork metadata, preserves permitted provenance metadata, rejects unsafe publish roots, and verifies the published selected-module app.

## Verification baseline

The latest behavior-changing Hades resident source accepted in the real game remains resident revision 49 from the terminology-normalization line:

`6239a770e9a2e3d39d01e9562a8a6a0817bbd2db`

Its recorded real-game acceptance artifact is `10721008543`, digest `sha256:c605bde145f4547611560c52de02647e0237ba01a0fec3b7b6975c817c2bfb1a`.

The newer compatibility and governance work did not change `Backend/games/hades2/runtime/hades.lua`, so no resident revision bump was required. Hades II 1.143476 / Steam 25481925 compatibility was additionally accepted on PR #172 head `03e31b6963f888becc4e8027019a94fc48647645` with exact-head Linux contracts, module build matrix, Build 2 macOS, target-machine static compatibility checks, and user-run attach/status plus representative feature smoke checks.

Automated tests are not substitutes for real-game acceptance when a future change modifies resident Lua semantics.

## Architecture/governance state

Completed foundations include A01 terminology governance, A02 authoritative terminology registry (#168), A03 runtime/protocol boundary, A04 runtime observation/synchronization semantics (#181), C01 durable feature-identity parity (#132 / PR #159), C02 user-presentation/stable-error/diagnostic separation (#182), and Profile versioning/migration compatibility (#108 / PR #109).

The current active governance package is #131, completing the Host bilingual localization foundation. Subsequent governance sequencing remains owned by planning issue #124. Under the current user direction, ordinary Phase D feature expansion remains held until the final governance lock #180 closes; this is a sequencing choice, not a repository-wide emergency freeze.

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
