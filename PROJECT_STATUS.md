# MacGamingTrainer Project Status

Updated: 2026-09-29

This is the canonical current-development handoff. It records present state only. Stable engineering rules live in `ENGINEERING_INVARIANTS.md`; release/version rules live in `VERSIONING.md`; planned work and sequencing live in planning issue #124; historical audit evidence lives under `docs/audits/`.

Start every development thread at `AGENTS.md`.

## Current state

- Default branch: `main`.
- Implementation baseline used for this handoff: `db0683094fc009e32873092519c0eb07fd276ee1` (PR #241 merged).
- Hades II resident runtime revision: 51.
- Hades II desired-state schema: 4.
- Host protocol: 6. Hades II module protocol: 5.
- Verified Hades II compatibility target: 1.143476 / Steam build 25481925 / arm64 UUID `35CD2E50-2D78-3A63-835B-3EB1224C6D65`.
- The retained `docs/reference/hades2/1.139672-24556151/` tree is a **frozen census/research snapshot**, not live planning authority; historical P-identifiers inside it are traceability only. Static compatibility work for 1.143476 confirmed that the currently consumed native terminology identities/values and curated reward/runtime dependencies remain valid. The packaged `ui_terminology.json` remains an explicit executable-governance exception; do not treat the snapshot directory name as the current executable identity.
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
- B01 / #131 / PR #183 completed the Host bilingual localization foundation: one persisted live zh-CN/English language state, packaged Host resources, and reference-fixture consumption of the same game-agnostic seam. B02 / PR #189 then migrated the remaining shared Host/Core product copy onto that seam in `Resources/Localization/{zh-CN,en}.lproj/Host.strings`, with `test_host_shared_localization_coverage.py` as the leakage gate. B03 / #177 migrated Hades-owned presentation through the terminology registry.
- Hades durable feature identity has executable parity coverage across Swift controls/model paths, Python router/adapter paths, resident Lua consumers, and the separate Core-owned `gameSpeed` path without adding another production feature schema.
- Hades terminology is packaged through module `appResources`; selected-module builds verify the intended app identity instead of accepting arbitrary stale output.
- macOS build/sign publication uses isolated staging, removes only signing-blocking FinderInfo/ResourceFork metadata, preserves permitted provenance metadata, rejects unsafe publish roots, and verifies the published selected-module app.
- Core-owned Process Time Warp failures resolve through Host-owned bilingual presentation identities; Hades runtime issue state preserves those structured Host tokens without flattening them into module copy.
- Hades raised and resident-runtime player-facing errors now share one Hades-owned declarative registry. Runtime command scope and producer provenance are registry metadata, reverse producer coverage rejects dead entries, and the behavior snapshot/mutation gate protect key + argument semantics.
- Shared module/CI discovery is metadata-driven. Normal module validation and the diff-based resident-runtime revision gate consume one Tools-owned `residentRuntime` declaration parser; malformed declarations cannot silently opt out of revision enforcement.
- New test files use descriptive subject names; historical epoch-named tests remain grandfathered rather than being bulk-renamed.
- #220 / PR #241 removes the default-empty Spawn action title. Olympian, pickup and character-reward rows share the module-owned live localized Generate label; command callbacks, enablement and resident semantics are unchanged.

## Verification baseline

The latest behavior-changing Hades resident source accepted in the real game is resident revision 51, from the D01 current-run trait inventory and sell-safe removal line:

`a6cf37b41639229bd64938d9587a9735fb16dd91`

Its accepted resident source is `Backend/games/hades2/runtime/hades.lua` at `sha256:de4d0485e16d3dec3c9fda96e7d9d1aee321c9dab7fcdb428bf065d8f6347e37`, accepted in Hades II on 2026-09-28.

Revision 51 is revision 50 plus one deletion — the no-op loop in `traitOwner` that computed nothing and was never read — so no observable behaviour changed between the two. Any prebuilt artifact whose resident digest is `sha256:63c1436b…` is revision 50 and predates that cleanup; it is not evidence for revision 51.

The implementation baseline `db0683094fc009e32873092519c0eb07fd276ee1` contains no later resident-Lua semantic change, so this remains the latest real-game acceptance baseline.

Hades II 1.143476 / Steam 25481925 compatibility was previously accepted on PR #172 head `03e31b6963f888becc4e8027019a94fc48647645` with exact-head Linux contracts, module build matrix, Build 2 macOS, target-machine static compatibility checks, and user-run attach/status plus representative feature smoke checks.

Automated tests are not substitutes for real-game acceptance when a future change modifies resident Lua semantics.

### Latest implemented change: Spawn labels

PR #241 was independently reviewed and tested at head `20ffefe42a7e489511ef5a21c6e3e070445b2a53`, then squash-merged as `db0683094fc009e32873092519c0eb07fd276ee1`. Both commits have source tree `56b26e9f7baea4795e9bd047145c66f2cf642fb9`; commit identity and tree identity remain distinct.

[Actual-head verification run 36554460524](https://github.com/TeaganRicardo/MacGamingTrainer/actions/runs/36554460524) checked out and asserted the PR head before running full Linux-portable contracts, macOS contracts, the declared mutation gate, Hades build, selected-module output verification, strict signing checks and artifact/provenance/checksum verification. Both jobs passed. [Independent review](https://github.com/TeaganRicardo/MacGamingTrainer/pull/241#issuecomment-5887716226) found no major issue on the same unchanged PR head.

The [retained exact-head artifact](https://github.com/TeaganRicardo/MacGamingTrainer/actions/runs/36554460524/artifacts/11027680745) contains its application ZIP, provenance and checksum. Application ZIP SHA256: `cc5db9771f810bfb2380d1fe77df2e2bc3a6819330d4438498f7d055dcacdddf`. Its resident bytes were rehashed and match the accepted revision-51 digest above. This artifact is implementation evidence, not the final consolidated acceptance build.

The ordinary PR workflow runs passed but checked out synthetic merge `e57688529f24193e1309c8b49c947b7ade1d96c9`; they must not be cited as exact-commit execution of `20ffefe...`. The permanent executable-checkout/provenance correction belongs to #199. The separate fixed-head run above closes that evidence gap for this repair without changing production workflows. Post-merge runs are separate evidence and must be inspected before claiming they passed.

### Verification routing

PR #184 established the change-scope routing baseline. Pull-request change scope and runtime-revision enforcement use merge-base -> PR head, and missing/invalid scope decisions fail closed. PR #216 then made shared module/reference routing and `validate_game_module.py --all` derive from module metadata rather than a Hades-specific list; PR #223 made normal module validation and the diff revision gate share one `residentRuntime` declaration parser. Ordinary documentation keeps the existing required check names but takes lightweight Ubuntu fast paths. Linux-portable Backend/tests/reference data run Linux contracts only. Paths that are not Linux-portable, including Swift/AppKit/native/build/package/macOS-only work and packaged module resources, also run Build 2 macOS. Module/Core/build-boundary paths additionally run the reference-fixture module build. The explicit shared Backend/Core seams `__init__.py`, `adapter.py`, `game_spec.py`, `module_manifest.py`, `protocol.py`, `registry.py`, and `server.py` are conservatively routed through macOS + reference-fixture verification, while ordinary portable Core Python such as `save_service.py` remains Linux-only. In the standing CI routing, Build 2 is the production Hades build/package/signing lane; the module matrix builds only `reference_fixture`.

## Architecture/governance state

Completed foundations include A01 terminology governance, A02 authoritative terminology registry (#168), A03 runtime/protocol boundary, A04 runtime observation/synchronization semantics (#181), B01 Host bilingual localization foundation (#131 / PR #183), B02 shared Host/Core presentation migration (PR #189), B03 Hades presentation migration (#177), C01 durable feature-identity parity (#132 / PR #159), C02 user-presentation/stable-error/diagnostic separation (#182), planning-authority reference cleanup (#133), and Profile versioning/migration compatibility (#108 / PR #109).

Post-B03 hardening now merged on the current baseline includes #196 (Core Time Warp presentation ownership), #197 (registry-derived Host forbidden-term governance), #198 (schema/protocol mirror cleanup), #200 (test naming governance), #201 (frozen-reference authority), #204 (single-source Hades error registry), #205 (module-driven shared CI discovery), #210 (reference-fixture handshake closeout), #213 (normal resident-runtime declaration validation), and #220 (non-empty localized Spawn actions).

Planning issue #124 remains the sequencing authority. This status file records only the current operational gate and does not mirror the roadmap.

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

The shared-presentation migration remains complete: B01 / #131 / PR #183, B02 / PR #189, and B03 / #177 all merged, with B02 and B03 accepted in the real game at `a6cf37b`; subsequent presentation hardening did not change resident Lua semantics.

#199 (app identity / dist naming / provenance ownership) is the next ready implementation task; #179 remains serialized behind it. #220 merged through its independent two-file repair lane under the explicit #124 scheduling decision. The remaining governance sequence is #199 -> #179 -> #203 -> #180 -> #214. Selected feature commitments, including expanded #221 and #227-#240, remain after #214 and are not completed by the Spawn-label fix.

The user explicitly authorized independently reviewed, automated-green merges before ONE consolidated final manual acceptance after the selected index work is implemented. Missing gameplay/visual verification alone must not block unrelated eligible development, but all unexecuted checks remain pending and no merge is described as manual acceptance. No game launch or visual confirmation through RDC.

At this handoff, no #199 development worker is confirmed running: the prior local Codex session was rejected by authentication, the remote device was offline at the continuation check, and the GitHub cloud-task request reported no usable repository environment. Independent GitHub PR review remains available. Recheck actual worker/remote outcomes before retrying dispatch; preserve unrelated local uncommitted changes. Current prompts and execution blockers are recorded on #124 and the individual tasks.

Hades II Save Editor is not implicitly authorized by the current governance sequence. If selected later, its binary mutation design still requires separate explicit design/safety approval.

## Known non-blocking risks

- Some Core filesystem metadata updates do not parent-directory fsync after every atomic replace. This is an extreme sudden-power-loss durability ceiling, not a demonstrated normal-operation corruption bug.
- Hades Profile storage does not mirror every Core Save subdirectory-symlink containment guard. It runs with the same user authority and has no demonstrated exploit/data-loss path.

Promote these only when new evidence or a selected requirement justifies work.

## Historical evidence

Historical material is evidence only and must not be used as current instructions.

The retained repository-level synthesis is:

- `docs/audits/2026-09-21-ai-development-governance.md` — system map, debt/test audit, and governance rationale.

Closed PRs and Git history preserve completed implementation detail. Do not add new round handoffs, audit-continuation files, or duplicate status documents for ordinary development.
