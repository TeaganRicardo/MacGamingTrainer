# Development entrypoint

## Establish the task

1. Resolve current remote `main`, inspect local changes and overlapping open PRs, and work on a branch. A historical branch being ahead is not evidence that its code should return.
2. State the user outcome and the accepted product contract. Current user instructions govern the task; still-binding decisions and sequencing live in [planning issue #124](https://github.com/TeaganRicardo/MacGamingTrainer/issues/124). Code and executable tests establish current behavior, which may contain defects; they do not override an accepted requirement.
3. Read [PROJECT_STATUS.md](PROJECT_STATUS.md) for compatibility, operational limitations and manual-acceptance state. Read the relevant sections of [ENGINEERING_INVARIANTS.md](ENGINEERING_INVARIANTS.md), then the owning production files and nearest behavior tests.

For Core/game/build changes, also read [GAME_MODULES.md](GAME_MODULES.md); for release metadata, read [VERSIONING.md](VERSIONING.md). Historical audits, closed PRs and Git history are evidence to consult when explaining a current defect or invariant, not a default task queue. When documents conflict, resolve against the accepted contract and current evidence, and correct the stale instruction in the owning change.

## Choose the owner

| Responsibility | Owner |
| --- | --- |
| Host/process/backend lifecycle | `Sources/Core/Host/**`, `Sources/Core/Runtime/**` |
| Shared visual language and generic input | `Sources/Core/UI/**`, `Sources/Core/Input/**` |
| Generic optional Save transactions | `Backend/core/save_*`, `Sources/Core/Save/**` |
| Game commands, state, transport, persistence, saves and UI | Each game owns `Backend/games/<id>/**` and its frontend under `Sources/<Game>/**` |
| Build/module metadata interpretation | `Tools/**` and module manifests |

Keep game meaning in the game module. A shared abstraction needs a demonstrated game-agnostic contract; repeated Hades-only changes are evidence to improve the Hades owner first.

## Version impact procedure

For any change touching product release metadata, module manifests, supported game images, native symbols/C offsets, resident scripts, persistence formats, bundled references, toolchains or release workflows:

1. **Classify the identity that changed:** product SemVer/build, supported **game** build, Host/module protocol, resident Lua revision, persisted schema, or build toolchain/provenance. Different identities have different owners; a game update does not imply a product-version bump.
2. **Read the owner before writing:** `Info.plist` for product release identity; `Backend/games/<id>/module.json.supportedBuild` for verified native game identity; `module.json.protocolVersion` for frontend/backend compatibility; resident declaration and Lua source for resident revision; the corresponding schema owner for persistence. See [VERSIONING.md](VERSIONING.md) and [GAME_MODULES.md](GAME_MODULES.md).
3. **Update dependents through the owner:** for a newly verified game image, update its `supportedBuild`, revalidate `symbols.json` RVAs/prefixes and native offsets, regenerate the declared native UUID header with `python3 Tools/supported_build.py --write-native-header <id>`, and update/revalidate the game-owned reference snapshot, packaged resources and extraction generators. Never copy new version/UUID/hash literals into feature code or workflow scripts. Keep retired reference snapshots explicitly historical. Follow [the supported game build update runbook](docs/development/supported-game-build-update.md) when replacing a verified native image.
4. **Check behavior and migration:** changing a module protocol, resident revision, or persistence schema needs the owning compatibility/recovery tests and migration/old-version refusal behavior. Hades-native one-shots keep unknown-outcome non-replay and tested session ownership.
5. **Validate one exact SHA:** run `python3 Tools/supported_build.py` and affected portable/module/macOS checks once authorized, then independent final-head review and required PR CI once for the final batch. A changed head invalidates preceding QA claims. Respect testing pauses and distinguish source inspection, synthetic checks and actual-game acceptance.
6. **Prepare releases separately:** only an intentional release-preparation PR edits product SemVer/build in `Info.plist`; release tags follow verified GitHub-source artifact provenance. Do not retag or invent previous releases. Update the controlling Issue and any operational compatibility change rather than maintaining a second version-status table.

## Implement and prove the outcome

- For a demonstrated defect, reproduce the failing behavior before the production fix. Identify how the invalid state arises and which owner should prevent it. If real-game reproduction is unavailable, record the observed report and the limits of the fixture; source inspection alone is not RED evidence.
- Make the smallest coherent correction of that cause, including affected callers and tests. Judge scope by causal purpose and ownership. A new module or interface is useful only if it removes knowledge from callers; migrate them and remove the superseded policy/checks.
- Identify authoritative state, durable desired intent, runtime observation and one-shot intent where relevant. Classify replay safety before changing recovery. Preserve the original session/run/hero/room ownership of asynchronous work.
- Preserve native execution semantics when introducing shared handling: synchronous calls, yielding game coroutines, deferred callbacks, native menu lifetime and draw ownership may require different execution paths. Verify an existing successful path as well as the reproduced failure. A uniform result type does not authorize wrapping every native call in the same transaction/protected call.
- A guard or fail-closed result is a complete fix only for an unavoidable failure at its owner. When it merely contains a structural defect, label the remaining cause and retain a focused successor. Preserve recovery evidence and keep outcome-unknown non-idempotent actions from automatic replay.
- For user-facing changes, exercise the affected journey through input, commit, observation refresh, feedback and applicable recovery. Use actual native controls in the existing harness where practical; preserve focused drafts, refresh unfocused values and give compatible recovery steps. Distinguish these checks from rendered/game acceptance.
- Use supported-build official bilingual identity for native game terms, and explicit bilingual pairs for Trainer-owned labels. Consult the module's terminology registry rather than creating a parallel vocabulary or a prose mirror.

## Verification and completion

Evidence belongs to the exact SHA that executed it. Choose verification by the changed responsibility, then rerun its task gates after a head rewrite/rebase or an overlapping semantic change.

| Changed responsibility | Task verification |
| --- | --- |
| Portable backend/contracts | `bash Tools/run_linux_checks.sh` (broad portable discovery) |
| Swift/AppKit/build/package | `Build 2 macOS`: macOS contracts and actual Hades build/package/signing, plus applicable portable contracts |
| Core/module/build contract | Also the module build matrix/reference fixture |
| Core Save transactions | Full portable Save behavior coverage; macOS for Swift integration |
| `Backend/games/hades2/runtime/hades.lua` | Portable behavior and PR-only resident revision increase; real Hades II acceptance for changed runtime semantics |

The three existing checks remain `Linux contracts`, `Build 2 macOS` and `Module build matrix`; their change-scope classifier selects execution. Mutation audits, retained QA/release artifacts, provenance and checksums belong to explicit convergence/release dispatch on one selected SHA. Merged `main` does not automatically repeat PR checks. A manual handoff uses one fixed source/artifact/checksum, with unexecuted checks explicitly pending.

Tests use temporary fixtures, never the real user/game save tree. New test files use descriptive `test_<subject>.py` names; existing historical names need no bulk rename.

A task is ready for its authorized handoff when the cause/user journey is addressed, owning checks and independent final-head review pass, and any real-game limitations are stated. Automated-green development and user acceptance are distinct; follow the current authorization in `PROJECT_STATUS.md` without requesting approval again for already-authorized work.

## Keep the control plane current

- Prefer one behavior test at the owning interface. A new recurring global gate needs an escaped defect or a proven cross-cutting responsibility that local behavior tests cannot protect; replace subsumed mechanisms.
- Maintain one source for each fact. Reference registries, manifests and `Info.plist` instead of duplicating their current values into prose and testing the copies.
- #124 contains current priority, real dependencies and still-binding decisions. Task issues own detailed scope/acceptance; PRs own implementation evidence. Delete completed dispatch tables, superseded blockers and old handoff/status prose from the live index rather than appending a correction beside them. An unfinished requirement remains linked to its active task or explicit deferred disposition.
- Update `PROJECT_STATUS.md` when compatibility, operational policy or the manual-acceptance baseline materially changes. Include the update in the owning PR; ordinary merges need no separate status-reconciliation PR.
