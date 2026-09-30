# MacGamingTrainer Project Status

Updated: 2026-09-30

This is the canonical current-development handoff. It records present state only. Stable engineering rules live in `ENGINEERING_INVARIANTS.md`; release/version rules live in `VERSIONING.md`; planned work and sequencing live in planning issue #124; historical audit evidence lives under `docs/audits/`.

Start every development thread at `AGENTS.md`.

## Current state

- Default branch: `main`.
- Implementation baseline used for this handoff: `dc48923acc9bb5c44a4df6c7cead98b03701a1a1` (PR #271 / #262 merged on top of PR #270). Resolve current remote `main` before starting work; later documentation commits may advance HEAD.
- Hades II resident runtime revision: 54. Revisions 52 (#251 / PR #255), 53 (#253 / PR #263), and 54 (#262 / PR #271) are merged automated implementation state; real-game acceptance for revisions 52–54 remains pending in the consolidated final user run.
- Hades II desired-state schema: 5.
- Host protocol: 6. Hades II module protocol: 6.
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
- #179 package/resource/artifact closeout required no duplicate implementation after #199/#205/#213 evidence review; #203 / PR #248 and #180 / PR #249 completed the final mutation and terminology/presentation drift enforcement chain.
- #251 / PR #255 makes Echo's synthetic `LastReward` fallback transaction-local and bumps the resident runtime to revision 52; automated checks passed, while real-game acceptance remains deferred.
- #252 / PR #256 closes the Core unavailable-send busy latch without changing crash/timeout/manual-restart no-replay semantics.
- #254 / PR #257 makes mutation-gate git worktree inspection fail closed when `git status` itself fails.
- #253 / PR #263 makes resident replacement fail closed when prior cleanup fails, preserves the old ownership reference, surfaces a stable restart-required path, and bumps the resident runtime to revision 53.
- #258 / PR #264 routes Core-owned protocol/server failures through Host-owned presentation identities while preserving stable codes, diagnostics, Core Save mapping, and module-owned presentation.
- #260 / PR #265 makes automatic Hades Save snapshot naming bilingual through generic localized snapshot presentation while preserving literal user renames and legacy manifest readability.
- PR #270 corrects catalog official-name resolution, including linked source-named rewards, without changing catalog identity or runtime semantics.
- #262 / PR #271 migrates the Trainer-owned invulnerability feature from live identity `godMode` to `invincibility` / 无敌模式 / Invincibility across desired state, Profiles, shortcuts, Swift/backend routing and resident state; legacy `godMode` remains only at versioned migration boundaries. Hades module protocol is 6, desired-state schema is 5, Profile schema is 6, and resident revision is 54.
- #214 exact-head convergence verified implementation commit `e560554917af8b03f161dfe166fbba62becd97e6` / tree `63e8a2c498b346ffbac02b749a20ce829c3f5026` across full portable contracts, macOS contracts, 33 declared mutations, Hades build/package/provenance, and the reference-fixture module build. Revision 51 remains the latest real-game accepted resident baseline; revision 52–54 gameplay acceptance remains deferred.

## Verification baseline

The latest behavior-changing Hades resident source accepted in the real game is resident revision 51, from the D01 current-run trait inventory and sell-safe removal line:

`a6cf37b41639229bd64938d9587a9735fb16dd91`

Its accepted resident source is `Backend/games/hades2/runtime/hades.lua` at `sha256:de4d0485e16d3dec3c9fda96e7d9d1aee321c9dab7fcdb428bf065d8f6347e37`, accepted in Hades II on 2026-09-28.

Revision 51 is revision 50 plus one deletion — the no-op loop in `traitOwner` that computed nothing and was never read — so no observable behaviour changed between the two. Any prebuilt artifact whose resident digest is `sha256:63c1436b…` is revision 50 and predates that cleanup; it is not evidence for revision 51.

The latest real-game accepted resident source remains revision 51 at `a6cf37b41639229bd64938d9587a9735fb16dd91`. Current main contains revision 54: revision 52 from #251 / PR #255 changed Echo transaction cleanup semantics, revision 53 from #253 / PR #263 changed resident-replacement cleanup failure semantics, and revision 54 from #262 / PR #271 migrated the Trainer-owned invulnerability runtime identity to `invincibility`. Revisions 52–54 remain explicitly pending consolidated real-game acceptance. Automated evidence for revisions 52–54 does not replace that user-run acceptance baseline.

Hades II 1.143476 / Steam 25481925 compatibility was previously accepted on PR #172 head `03e31b6963f888becc4e8027019a94fc48647645` with exact-head Linux contracts, module build matrix, Build 2 macOS, target-machine static compatibility checks, and user-run attach/status plus representative feature smoke checks.

Automated tests are not substitutes for real-game acceptance when a future change modifies resident Lua semantics.

### Exact-head convergence · #214

The post-hardening convergence source tested in full is commit `e560554917af8b03f161dfe166fbba62becd97e6`, tree `63e8a2c498b346ffbac02b749a20ce829c3f5026`. A later docs-only bookkeeping commit may advance `main`; it must not be described as the source that received this full execution.

On the target macOS machine, the exact source passed `Tools/run_linux_checks.sh` under Python 3.12, `Tools/run_macos_checks.sh`, and `Tools/mutation_gate.py` with 33 caught / 0 survived / 0 equivalent / 0 skipped / 0 error. Hades II and `reference_fixture` both built, passed strict signing/module-isolation verification, and produced local provenance bound to the exact commit/tree.

The retained Hades convergence artifact is `MacGamingTrainer-0.1.0-b3-e5605549-rc.zip`, SHA256 `b58a9dd138c40cd6eedaf5ee31022c3fca6928c9f00e5d9ae696a29a15f3537b`. Its resident source/package SHA256 is `680c1f7daabce9947dad2306023301272ad23dc5f1729c998489d148adbb1634`. The retained reference-fixture artifact is `MacGamingTrainer-reference_fixture-0.1.0-b3-e5605549-rc.zip`, SHA256 `cd98638ef7f12a275532256739b1d636cc8c87c27265d68974025ea364883f66`. Both artifacts, provenance files and checksum sidecars are retained in the draft GitHub verification release `convergence-e5605549`; this is evidence storage, not a product release or manual acceptance.

The resident comparison from accepted revision 51 to the revision-53 #214 convergence source contains the revision-52 Echo `LastReward` transaction cleanup and revision-53 fail-closed resident-cleanup transition. Revision discipline passed; both semantic changes were carried forward into the consolidated user-run acceptance backlog; current-main revision 54 is described in the current-state section above.

### Retained manual-acceptance evidence: Spawn labels

PR #241 was independently reviewed and tested at head `20ffefe42a7e489511ef5a21c6e3e070445b2a53`, then squash-merged as `db0683094fc009e32873092519c0eb07fd276ee1`. Both commits have source tree `56b26e9f7baea4795e9bd047145c66f2cf642fb9`; commit identity and tree identity remain distinct.

[Actual-head verification run 36554460524](https://github.com/TeaganRicardo/MacGamingTrainer/actions/runs/36554460524) checked out and asserted the PR head before running full Linux-portable contracts, macOS contracts, the declared mutation gate, Hades build, selected-module output verification, strict signing checks and artifact/provenance/checksum verification. Both jobs passed. [Independent review](https://github.com/TeaganRicardo/MacGamingTrainer/pull/241#issuecomment-5887716226) found no major issue on the same unchanged PR head.

The [retained exact-head artifact](https://github.com/TeaganRicardo/MacGamingTrainer/actions/runs/36554460524/artifacts/11027680745) contains its application ZIP, provenance and checksum. Application ZIP SHA256: `cc5db9771f810bfb2380d1fe77df2e2bc3a6819330d4438498f7d055dcacdddf`. Its resident bytes were rehashed and match the accepted revision-51 digest above. This artifact is implementation evidence, not the final consolidated acceptance build.

The ordinary PR workflow runs passed but checked out synthetic merge `e57688529f24193e1309c8b49c947b7ade1d96c9`; they must not be cited as exact-commit execution of `20ffefe...`. The permanent executable-checkout/provenance correction was delivered by #199. The separate fixed-head run above closes that evidence gap for this repair without changing production workflows. Post-merge runs are separate evidence and must be inspected before claiming they passed.

### Package identity and provenance

#199 merged through [PR #245](https://github.com/TeaganRicardo/MacGamingTrainer/pull/245) as `643e7a4a46e6151ea00ba7cb433209b579b2a828`. The reviewed head was `81db40df1118e75d8e9c5cdadebe9da5240fde3b`; its Linux, Build 2 macOS and reference-module jobs passed, as did local Linux/macOS contracts and the 21-case mutation gate. The selected app and module own package identity, artifact names and provenance; resident bytes are attributed only to the selected app. [Independent review](https://github.com/TeaganRicardo/MacGamingTrainer/pull/245#issuecomment-5892858814) found no major issue on that head. This changes packaging and verification contracts, not resident gameplay semantics. #179 later closed by criterion-to-evidence review without a duplicate implementation PR.

### Verification routing

Pull requests use merge-base -> exact PR head for scope classification and fail closed when scope cannot be resolved. Documentation takes the existing fast paths. Linux-portable Backend/tests/reference data run the broad Linux contracts; Swift/AppKit/native/build/package/macOS-only work and packaged module resources also run Build 2 macOS; module/Core/build-boundary paths additionally build the reference fixture.

Recurring CI is task verification only:

- the three stable workflow/check names run on `pull_request`, not again automatically on `push(main)`;
- Build 2 PR mode runs macOS contracts plus an actual Hades build and package/sign verification, but not the mutation audit or retained RC artifact/provenance pipeline;
- the module matrix PR mode builds and verifies reference-module isolation but does not retain a reference artifact/provenance package;
- Linux continues to run all portable tests when its lane is selected, including the resident-runtime revision gate.

For convergence, release or a manual QA artifact, explicitly dispatch the same three workflows on the selected SHA. Manual dispatch has no diff base and therefore fails closed to the full applicable lanes. Build 2 then adds the mutation audit and exact-SHA RC/provenance/checksum artifact; the module matrix adds retained reference provenance/artifact evidence.

## Architecture/governance state

Completed foundations include A01 terminology governance, A02 authoritative terminology registry (#168), A03 runtime/protocol boundary, A04 runtime observation/synchronization semantics (#181), B01 Host bilingual localization foundation (#131 / PR #183), B02 shared Host/Core presentation migration (PR #189), B03 Hades presentation migration (#177), C01 durable feature-identity parity (#132 / PR #159), C02 user-presentation/stable-error/diagnostic separation (#182), planning-authority reference cleanup (#133), and Profile versioning/migration compatibility (#108 / PR #109).

Post-B03 hardening now merged on the current baseline includes #196 (Core Time Warp presentation ownership), #197 (registry-derived Host forbidden-term governance), #198 (schema/protocol mirror cleanup), #200 (test naming governance), #201 (frozen-reference authority), #204 (single-source Hades error registry), #205 (module-driven shared CI discovery), #210 (reference-fixture handshake closeout), #213 (normal resident-runtime declaration validation), #220 (non-empty localized Spawn actions), #179 (package/resource/artifact closeout), #203 (final mutation protection), #180 (terminology/presentation drift enforcement), #251 (Echo LastReward rollback), #252 (Core unavailable-send recovery latch), #254 (mutation-gate git inspection fail-closed), #253 (resident cleanup fail-closed transition), #258 (Core protocol presentation ownership), #260 (bilingual automatic Hades Save naming), the catalog-name correction merged through PR #270, and #262 (Trainer invulnerability identity migration).

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

#214 exact-head convergence is complete on tested source `e560554917af8b03f161dfe166fbba62becd97e6`. #262 / PR #271 is also merged on current main. The revision-51 real-game acceptance baseline is retained and revision-52–54 gameplay checks remain pending for the consolidated final user run. The next selected feature implementation task is #227, the first bounded slice of complete current-run mounted boon management. Planning detail and later feature ordering remain authoritative in #124 rather than being duplicated here.

The user explicitly authorized independently reviewed, automated-green merges before ONE consolidated final manual acceptance after the selected index work is implemented. Missing gameplay/visual verification alone must not block unrelated eligible development, but all unexecuted checks remain pending and no merge is described as manual acceptance. No game launch or visual confirmation through RDC.

With convergence and the #262 identity migration complete, #227 is now the selected next feature task. Preserve unrelated local uncommitted changes and keep later family coverage linked to #221/#228/#236–#240 rather than collapsing it into a raw-trait bucket.

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
