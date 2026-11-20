# Add a game module

A normal module adds its backend directory, frontend directory, resources and behavior tests, then registers its ID in `app.json`. Start from the current `ContractFixtures/reference_module` and the contracts in [GAME_MODULES.md](../../GAME_MODULES.md). Keep game commands, terminology, state, target compatibility and persistence inside the game owner.

## Declare the integration

Create `Backend/games/<id>/module.json` and `Sources/<Game>/`. Use a safe module ID and an adapter inside `games.<id>`. The shared validator checks layout, paths and independent diagnostic identity before compilation.

`Sources/<Game>/` compiles as its own Swift module named `<Game>`. Its files `import TrainerCore` and see only Core's `package` declarations; the compiler rejects a reference to another game, and Core cannot import a game, so product Swift types need no game prefix. Swift test harnesses compile the same modules: a harness names the games it loads (`compile_swift_test(games=...)` in `tests/swift_test_compiler.py`), never their source files, and imports them `@testable`. Only a portable harness, which the Linux lane runs without SwiftUI/AppKit, lists Foundation-level files as explicit modules and says so. The generated `<moduleType>Binding` is the only declaration the App sees, so keep the module's own types at the default access level. `UserDefaults` is still one shared domain: give every key a `<id>.` prefix.

| Declaration | Use it when | Owning verification |
| --- | --- | --- |
| `targetApplication.bundleIdentifier` | The game has a stable native application identity | Target monitor and ownership tests, then actual game attach |
| `targetApplication.executablePathSuffix` | A target has no Bundle ID or a generic executable basename | Generated descriptor and kernel executable-path matching; same-name unrelated processes must be rejected |
| `frontend` | Every module | Generated binding in the game's Swift module, product module typecheck and isolated reference matrix when a shared boundary changes |
| `app` | Diagnostic defaults need a specific name or Bundle ID | Module identity/output tests; it must differ from the product in `app.json` |
| `supportedBuild` | Native symbols, offsets or injected code depend on an exact game image | [Supported build update runbook](supported-game-build-update.md), source-derived identities and actual game acceptance |
| `nativeLibraries` | The module builds code loaded into the game | Declared target architecture, native compilation, package/signature and supported-image tests |
| `residentRuntime` | Process-lifetime resident source has a revision contract | Declaration validation, changed-source revision gate and exact packaged-source provenance |
| `saveManagement` | The module supplies Save operations | Core transactions plus module codec/provider behavior; optional editor factory only for supported editable documents |
| `buildRequirements` | The integration needs an LLDB bridge or debugger entitlement | Its actual selected build/bridge path; the base reference fixture proves these dependencies remain optional |
| `appResources` | Runtime code needs bundled reference data | Source path from the owning manifest, package inventory and provenance |

The base reference fixture requires no LLDB, Lua, sidecar, Save provider or editor. Optional capability variants prove only their declared chains: the reference session fixture generates and consumes a suffix-only descriptor against temporary processes; the existing multi-module revision and provenance owner tests cover resident declarations and packaged source identity. These fixtures do not certify a game's native ABI.

Call the Host-facing model and module UI factories on Swift's main actor. Swift harnesses that exercise these APIs use a main-actor entry point.

`TrainerGameModule.makeModel(services:)` receives the Host-owned session, observable backend status, current target observation, descriptor, log sink and module-scoped hotkeys. The model supplies its game-specific payload and connection behavior. The Context records the target's log-session boundary before starting the backend and stops the session once the model's termination hook completes.

## Terminology, localization and shared responsibilities

Native game terms come from the module's terminology owner and its verified reference sources. The current examples are `Backend/games/hades2/terminology.py` with the manifest-declared supported-build terminology resource, and Hades I's `catalog.py`, `world.py` and `save_owners.py`. Follow [terminology ownership](../../ENGINEERING_INVARIANTS.md#8-terminology-ownership) for bilingual native identities and Trainer-owned labels.

A frontend supplies `TrainerGameModule.presentationKeyPrefix` and `presentationText(key:arguments:language:)`; `TrainerGameContext.registerPresentation` registers that module resolver with `TrainerLocalizationStore`. Shared Host keys live in `Resources/Localization/en.lproj/Host.strings` and `zh-CN.lproj/Host.strings`. Game-owned examples are `Sources/Hades/HadesPresentation.swift` and `Sources/Hades2/Presentation/Hades2Presentation.swift`; the latter's English/Chinese JSON resources are packaged through its manifest's `appResources`. Reuse these Host/module entry points when adding labels and live language switching.

Put a responsibility in Core when actual behavior demonstrates a game-agnostic contract, as described in [architecture evolution](../../GAME_MODULES.md#architecture-evolution). Keep game meaning, validation and native execution semantics in the module. When an owner moves, migrate its consumers and remove the superseded policy rather than leaving both implementations active.

## Register behavior coverage

Provide a stable behavior entry using `test_<id>_model_flow.py`, `test_<id>_frontend.py` or `test_<id>_view_state_flow.py`. Put `MGT_PLATFORM = "macos"` at the test file's top level. The selector requires a stable PR entry for changed module Swift sources and for each module in `app.json` on shared Core changes.

Use a foreground-independent model/API/session journey for ordinary PR smoke. The Hades II model entry exercises typed commands, explicit commit, authoritative observation refresh, guarded actions and feedback. Native focus, field-editor, key-window, activation and rendered journeys remain in their own convergence entries. A model call does not prove physical keyboard/focus behavior.

Test discovery reads platform declarations without executing the files. Unmarked `test_*.py` entries run in the portable lane, including Foundation-only Swift behavior that also runs on Linux.

The selector follows Python imports and literal file paths through test helpers. It derives Swift sources and the manifests used to generate bindings from the product layout used by `compile_swift_test`. Declare opaque inputs in a top-level `MGT_INPUTS` tuple, such as interpolated resource paths, files copied into a scratch checkout, and Backend Python files that exercise platform-specific behavior. Use repository-relative paths and a trailing slash for a directory. Native fixture sources under `tests/` select the full native inventory.

Use `tests/macos_fixture_policy.py` for an actual native journey's outer watchdog. Give the journey one budget and one launch. Preserve named semantic predicates and their own failures inside the harness; compilation timeouts and an LLDB coordinator with its own worker cleanup are different contracts. Never multiply budgets or wrap an existing coordinator with a second watchdog. Unknown hosted profiles fail closed. Runtime timing is observation, never a speed threshold.

`Tools/select_macos_pr_tests.py` reads changed paths from the merge base and writes one structured relevant/selected/deferred result. Adding a native entry or editing its declared inputs changes the test file itself, which selects that entry. The runner executes the selected list and uses that same result to report any deferred tests, their reasons and the exact-SHA verification owner.

## Keep architecture identities separate

The Host executable and bundled Python run on the product architectures in `app.json`. A game module's diagnostic frontend may declare its own Host architectures. An LLDB bridge uses the selected debugger toolchain's Python and libraries, not arbitrary bundled CPython. The target game's verified Mach-O architecture belongs to `supportedBuild`; injected libraries and C ABI must match that target.

An arm64 Mac can therefore run an arm64 Trainer and debugger client against an x86_64 game through the supported debugger/Rosetta path. The runner architecture need not equal `supportedBuild.architecture`. For an x86_64 target, retain an explicitly verified Intel target/bridge path, compile its injected helper for x86_64 and run the owning native/game tests; an arm64 product build alone proves none of those steps.

## Check equivalent behavior at its owning interface

Shared semantics are contract assertions, not a quota of test files. Preserve game capability differences and identify the authoritative value, durable desired intent, runtime observation and one-shot intent before sharing an interface.

| Equivalent contract | Existing owning evidence | Boundary to preserve |
| --- | --- | --- |
| Continuous settings and observed active/dormant state | `test_hades_commands.py`, `test_hades_runtime.py`, `test_hades2_model_flow.py`, resident reconciliation tests | Desired state may survive disconnect; active state needs its native owner |
| Fixed-value locks and non-consuming resources | `test_hades_management.py`, Hades desired-state replay tests, Hades II runtime/resource tests | A fixed lock, retained gains and explicit numeric edits have different game semantics |
| Explicit commit, local draft and observation refresh | Module frontend journeys, `test_hades2_model_flow.py`, `test_runtime_text_edit_completion.py` | Model smoke proves commit/feedback; physical focus and input-method composition retain native/human acceptance |
| Two persistent contexts and hidden-page work | `test_multi_game_context_state.py`, reference session integration, global hotkey routing | Each worker, callback, tool and pending request retains its original context; selection affects visibility and shortcut scope |
| Workspace and document reply ownership (#615) | Shared reply-coordinator assertions in `multi_game_context_harness.py`, both module Save workspace tests | Old queries, source/target baselines and retired windows cannot adopt late replies; backend lifetime changes require document invalidation |
| Preferences, profiles and management (#620) | Core persistence tests, both module management/frontend suites | Core owns atomic storage/management mechanics; games own schemas and replay-safe application |
| Shortcut capture (#613) | `test_shortcut_chord_semantics.py`, `test_global_hotkey_routing.py`, native module capture journeys | One shared chord/capture contract; native event routing and spoken feedback need their actual execution paths |
| Disconnect/reconnect and unknown results | Backend session recovery tests, sidecar protocol and per-game recovery journal tests | A new worker is not a new target lifetime; unknown one-shot outcomes are never replayed |

When a gap in this table is a product defect, fix its production owner and nearest behavior test. Keep actual rendered App behavior, game actions, save loading, later game-authored persistence, accessibility speech and perceived performance with #429. A fixture or compiler pass cannot fill those acceptance cells.

## Shared files a module still touches

The contract above is the goal; these shared files still need edits or attention when a module is added. The [pre-module debt program (#766)](https://github.com/TeaganRicardo/MacGamingTrainer/issues/766) removes them; delete a row here when its owning change lands.

| Shared file | When | Removal owner |
| --- | --- | --- |
| An entry in `tests/fixture_budgets/` (for example `hades2_flow.py`, `multi_game.py`) | Each native journey; an unknown journey fails closed | #772 (provisional budgets) |
| `.github/workflows/module-build-matrix.yml`, `.github/workflows/build2-macos.yml` | Isolated diagnostic build and packaged-resource checks name the Hades modules | #772 (matrix from `app.json`, generic resource verification) |
| `tests/test_app_identity_contract.py` | Breaks when the module declares `supportedBuild` (copies only the Hades reference directories) | #772 |
| Lua 5.2 prerequisite steps in `linux-contracts.yml` and `build2-macos.yml` | The module's tests need a different runtime | #772 (generic prerequisites) |

## Run the owning lanes

Run `python3 Tools/validate_game_module.py --all`, `python3 Tools/supported_build.py` and the affected narrow behavior tests before publication. Portable changes use Linux contracts. Ordinary Swift changes use selected native smoke and unified product typecheck. Entrypoint, module, native, package or build inputs require the full linked and signed product. Shared module/build boundaries also require the reference fixture matrix.

For shared Python changes, create a virtual environment with the Python version used by Linux contracts and install the pinned tools with `python3 -m pip install -r Tools/python_static_requirements.txt`. From the repository root, run `python3 -m ruff check`, `python3 -m ruff format --check` and `python3 -m mypy`. `pyproject.toml` defines the shared packages Ruff checks and the protocol seams mypy checks.

A module-matrix workflow-only change exercises its own reference lane and Linux contracts; it does not force the unrelated unified product build. Mixed changes choose all applicable responsibilities, while an unknown diff fails closed. The three required check contexts stay present. Full inventory, isolated module packaging and retained artifact provenance belong to exact-SHA convergence.

Resolve the current main and open overlapping PRs before starting. Develop, independently review and merge the final tested head separately. Record the exact source and the scope each check proves. Product versions and releases are prepared in separate intentional work.
