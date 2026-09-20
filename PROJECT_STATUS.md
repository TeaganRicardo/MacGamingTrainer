# MacGamingTrainer Project Status

Updated: 2026-09-20

This is the canonical development handoff. Historical implementation plans, closed PRs and old branches are evidence only; current code, this file and roadmap issue #8 are execution authority.

## Current baseline

- Default branch: `main`.
- Verified code baseline: `9b15d8393918ceab8de89688d1d08dcaef89dfa1` (`fix: keep corrupt save snapshots visible`). Documentation-only commits after this SHA do not change the code evidence.
- Hades II resident runtime: revision 41.
- Hades II module protocol: 5.
- Target game baseline used by current runtime contracts: Hades II 1.139672 / Steam build 24556151.
- Process Time Warp + mapped speed slider are shared Host/Core infrastructure.
- Core Save Management is integrated, cross-game optional, and has completed its first hardening pass.
- Phase 1 cross-game isolation remains proven by the permanent non-production `reference_fixture`.
- Lifecycle acceptance issues #1 and #11 are closed. The final acceptance-only rerun was explicitly waived by the user; this is a waiver, not an invented manual pass.

## Exact merged-main verification

For `9b15d8393918ceab8de89688d1d08dcaef89dfa1`:

- Linux contracts run `35515313374`: PASS.
- Module build matrix run `35515313389`: Hades II PASS; reference fixture PASS; one-module package isolation PASS.
- Build 2 macOS run `35515313401`: full macOS contract suite PASS; Hades II build PASS; package verification PASS; artifact creation/upload PASS.

No Hades runtime source changed in the save-hardening series; resident revision remains 41.

## Completed recent work

Lifecycle / Host:
- PR #21: generic Process Time Warp + mapped speed slider.
- PR #23: cross-game isolation proof; issue #9 closed.
- PR #24: partial shortcut Profile conflict fix; issue #17 closed.
- PR #26: normal signaled same-PID reset no longer pays a doomed first resident status.
- PR #27: true-launch auto-connect can attach before the first Lua/world probe.
- PR #28: deferred launch probing is used only when lifecycle observation is available.
- PR #30: shared `trainer.log` GUI writes use `O_APPEND`, preventing backend profile records from being overwritten.

Core Save Management hardening:
- PR #32: `rollback_failed` now carries the preserved recovery-copy path through JSONL -> BackendReply -> Save Manager error UI.
- PR #33: Trainer-owned save-data storage is contained under the configured data root. Snapshot, staged metadata, staged cancellation and rollback transaction paths share one symlink/containment guard.
- PR #34: an empty resolved real-save set now reports `save_not_found` instead of `snapshot_invalid`.
- PR #35: corrupt/invalid snapshots emit safe inventory metadata and remain visible/revealable/deletable instead of disappearing from Swift decoding.

## Current gate

**Hades II save-editor design — no binary mutation is approved yet.**

Architecture boundary:
- Core continues to own generic snapshot/restore/rollback/staged-restore infrastructure.
- Hades II module owns Hades save schema, decode/encode, field validation, edit semantics and game-specific editor UI.
- No Hades save-field semantics move into Core/Host.
- Initial editor implementation must use temporary fixtures and must never mutate the user's real Hades II save tree in automated tests.

Codec research completed so far:
- TheNormalnij/Hades-SavesExtractor (MIT) supports Hades II extract/import and exposes the format as SGB1 header + LZ4-compressed luabins payload + Adler-32 rewrite.
- Its Hades II PATH11 version is `0x12`, matching the repository's current version-18 header assumptions.
- MarcosGalan/HadesSaveEditor (MIT) has a Python version-18 schema using `construct`, `lz4` and `luabins_py`, and demonstrates round-trip mutation of the decompressed Lua state.
- These are references/candidate reuse points only. No third-party codec/dependency choice has been approved or integrated.

The next design must explicitly decide:
1. codec ownership/reuse strategy;
2. stopped-only vs live editing policy for the first vertical slice;
3. pre-edit snapshot and failure rollback contract;
4. which fields are in the first editable schema;
5. read -> validate -> mutate -> encode -> checksum -> verify -> atomic replace flow;
6. UI placement inside the Hades II module while reusing shared Core/Host visual components.

## Planned sequence

1. Approve the Hades II save-editor design.
2. Write an implementation plan from that design.
3. Implement the smallest safe vertical slice with RED -> GREEN fixtures.
4. Re-run cross-game isolation and exact merged-main macOS/package gates.
5. Pre-Hades-I architecture gate.
6. Hades I vertical slice.

## Lifecycle evidence retained for history

The 2026-09-20 QA sample after PRs #26–#28 contains one genuine same-PID re-entry:
- run-log runtime reset bookkeeping crossed zero Lua boundaries;
- bootstrap/status took 0.868 s;
- one batched durable replay took 0.886 s;
- enabled persistent features became active again;
- the old failed-resident-status boundary was absent.

A later apparent disconnect was an actual game exit: Hades II.log recorded `MainMenuScreen::ExitGame()` followed by `App Shutdown`.

## GitHub state

Open:
- issue #8 — current roadmap.

Closed:
- issue #1 — lifecycle/manual-acceptance umbrella.
- issue #9 — cross-game isolation proof.
- issue #11 — lifecycle performance acceptance (final acceptance-only rerun waived).
- issue #16 — hosted Actions admission recovered.
- issue #17 — partial shortcut Profile collision.
- PR #21 through #35 — merged as applicable; superseded historical PRs remain evidence only.

## Branch hygiene

No historical feature branch is an execution base. New implementation work must branch from current `main`.

Remote branches eligible for deletion once a supported delete-ref interface is available include all merged/superseded branches already recorded previously, plus:
- `fix/append-only-shared-trainer-log`
- `fix/save-rollback-recovery-path`
- `fix/save-storage-root-containment`
- `fix/save-empty-error-code`
- `fix/invalid-snapshot-row-sanitization`
- `maintenance/status-after-log-qa`
- `maintenance/status-after-save-hardening`

The current GitHub connector exposes ref movement but no branch-delete mutation. Do not work around this with container network access or RDC.

## Permanent constraints

- GitHub connector is the authoritative remote-repository interface.
- The container is for materialized local editing, diffing and non-macOS tests; do not depend on direct container access to github.com.
- RDC is only for macOS-specific build/runtime validation and never for repository/file transport.
- Tests must never mutate real user/game data; destructive filesystem tests require explicit temporary roots.
- Target-Mac save-sensitive suites keep a before/after hash sentinel on the Hades II save tree.
- No periodic LLDB/Lua polling.
- No second debugger attachment for same-PID runtime recovery.
- No replay of outcome-unknown non-idempotent mutations or native modal commands.
- No Hades-specific semantics in Core/Host.
- Native modal commands are one-shot and never preference-replayed.
- Save restore must never make a declared save root disappear.
- A failed rollback must preserve the last recoverable copy.
- Runtime source changes require a resident revision bump.
- Each tester handoff is one exact HEAD + one prebuilt signed App/ZIP + SHA256.
- Fix demonstrated/root-caused failures with RED -> GREEN coverage.
