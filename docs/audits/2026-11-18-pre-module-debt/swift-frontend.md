# Swift-side technical-debt audit: what a third game module would inherit

Scope: `Sources/App.swift`, `Sources/Core/**`, `Sources/Hades/**` (Hades I), `Sources/Hades2/**` (Hades II), `ContractFixtures/reference_module/frontend`, and the Swift seam emitted by `Tools/generate_game_binding.py`.
Method: read-only source reading, grep and `git log -S`/`git show` at `main@73697aef`. Nothing was built, run or tested.

Evidence labels:
- **[fact]**: read directly in the cited source.
- **[inference]**: follows from the code but has not been confirmed at runtime or by a test. Each one names the check that would confirm it.

---

## Executive summary

The Core/UI layer is in better shape than feared. Most of `Core/UI` is genuinely neutral and both Hades modules use it. The debt is concentrated in four places:

1. **The Host does not own the module lifecycle.**
   - Backend start, log-session start, hotkey scope, status observation and feedback state are each implemented inside every module, and each module does it differently.
   - The Host then reads lifecycle facts back *through* the module (`model.backendAvailable`, `model.hostActionsEnabled`).
   - One overloaded property, `hostActionsEnabled`, has divergent semantics. As a result the Host's backend-restart path is very likely dead for Hades I and for the reference fixture (F1).
2. **Each Hades module carries roughly 350–450 lines of Host-like plumbing, and the copies diverge.** This covers feedback/current-issues, the log and diagnostics menu, the management catalog and menu, the sidebar section list, workbench search, the save-editor transport envelope, shortcut store/perform/reject, presentation routing and the draft sync contract. A third module would copy one copy or the other (F3–F9).
3. **Hades II is still partly shaped by the single-game era.**
   - It declares unprefixed global Swift types, including `TrainerProfile`, which looks like a Core type.
   - Its UserDefaults keys are not namespaced (`shortcut.action.*`).
   - Its shortcut-migration tables live in Core `HotkeyChord`.
   - Its 2.3k-line model has 129 `@Published` properties, 101 of them publicly settable (F4, F12, F14).
4. **The "two real adapters" rule is satisfied by two sibling Hades games.** As a result, Hades-family vocabulary (trait manager geometry, acquisition rarity, fishing/portal/character-reward icons, the fixed management slots) sits in Core. The isolation test only bans Hades **II** tokens from Core (F11).

The reference fixture is meant to be "the canonical example of the module interface", but it demonstrates almost none of this plumbing. In one case, `hostActionsEnabled`, it teaches the defective variant.

---

## Findings index

| ID | Title | Category | Sev | Size |
|---|---|---|---|---|
| F1 | `hostActionsEnabled` overloaded; Host backend-restart likely dead for Hades I and the fixture | seam / hazard (latent defect) | **high** | S–M |
| F2 | Backend start, log-session start and target-lifetime ordering are module-owned, implemented 3 ways; legacy `running:` overload | seam / stopgap-became-constraint | **high** | M |
| F3 | Backend status mirrored into every model; Host reads it back from the module | seam | **high** | M |
| F4 | Hades II global namespace and UserDefaults keys are not module-scoped | stopgap-became-constraint / hazard | **high** | M |
| F5 | Feedback, current issues, logs and diagnostics actions duplicated per module, with divergent behavior | duplication | med | M |
| F6 | Management catalog, sidebar section list and workbench search duplicated; App menu omits Save actions | duplication / misplaced-ownership | med | M |
| F7 | Presentation registration bound to view `onAppear`, so every module has its own `resolveText` bypass, three placeholder syntaxes and per-call dictionary rebuilds | stopgap-became-constraint / duplication | med | S–M |
| F8 | Command transport: Hades I stringly typed with hand timeouts; Hades II generated timeouts but hand-written replay/trust classification | duplication / seam | med | M |
| F9 | Save Editor transport envelope duplicated on top of the Core reply coordinator | duplication | med | M |
| F10 | Draft/observation sync contract implemented twice, very differently (≈10 lines vs ≈250 lines) | duplication | med | M |
| F11 | Hades-family vocabulary in Core passes the "two adapters" rule via siblings; isolation test only guards Hades II tokens | misplaced-ownership | med | S–M |
| F12 | Hades II shortcut-migration tables in Core `HotkeyChord`; the two shortcut stores diverge | misplaced-ownership / stopgap | low–med | S |
| F13 | `TrainerFeaturePresentation.activationPending` means "request in flight" in Hades I and "0.9 s timer" in Hades II | seam (underspecified contract) | med | S |
| F14 | God objects: `Hades2Model`, `Hades2SaveEditorModel`, `Hades2View`, `HadesModule.swift`, `TrainerLogSink` | god-object | med | L (incremental) |
| F15 | Hotkey scope and log identity are free strings chosen by the module; Hades I hard-codes `"hades"` | seam / hazard | med | S |
| F16 | No main-actor isolation anywhere in the seam (Swift 5 mode); every model change invalidates the App root | hazard | med | M |
| F17 | Lifecycle defaults hide required behavior (`connectAutomaticallyFromHost` toggles; each module must stop its own session) | seam | low–med | S |
| F18 | Stale-PID adoption guard exists only in Hades I | duplication (missing in one) | low–med | S |
| F19 | Retired or unused seam surfaces still carried | dead-code | low | S |
| F20 | Small stopgaps: retired `multiplier:100` payload field, untranslated strings, CJK Core log text, `ViewState` typealias | stopgap / dead-code | low | S |

---

## Detailed findings

### F1. `hostActionsEnabled` has two meanings; Host backend-restart is likely dead for Hades I and the fixture (high)

**Evidence [fact]**
- **The Host uses one property for two purposes:**
  - As the recovery veto: `TrainerGameContext.swift:218-219` calls `consumeAutomaticBackendRestartIfEligible(backendAvailable:busy:actionsEnabled: model.hostActionsEnabled)`.
  - As the enabled state of the sidebar primary button: `TrainerHost.swift:95`, then `TrainerStatusControls.swift:35-46,50-54`. When `!backendAvailable`, that button becomes **"Restart backend"** and is enabled by `actionsEnabled`.
- **The policy only reaches the restart branch when the backend is unavailable** (`TrainerConnectionPolicy.swift:146-157`: `if backendAvailable { … return false }`). Its comment says `actionsEnabled` is a veto "for terminal states such as an incompatible protocol".
- **The three implementations disagree:**
  - Hades II: `hostActionsEnabled = canAcceptRuntimeAction && !exiting && protocolCompatible` (`Hades2Model.swift:79`). It does **not** require `backendAvailable`, which matches the intent.
  - Hades I: `hostActionsEnabled = canUseBackend && !busy`, where `canUseBackend = backendAvailable && …` (`HadesModule.swift:86-87`).
  - Reference fixture: `backendAvailable && !busy && protocolCompatible` (`ReferenceFixtureModule.swift:23-25`).
  - The test harness copies the fixture shape (`tests/real_module_navigation_harness.py:134`).

**Why it matters [inference, high confidence]**
- For Hades I and the fixture, `actionsEnabled` is always false whenever the restart branch is reachable. So:
  - (a) the Host's one-shot automatic backend restart never fires;
  - (b) after `backend_start_failed` or `backend_recovery_failed`, the card's "Restart backend" button is disabled.
- No other Hades I UI path calls `restartBackendFromHost`; only `TrainerHost.swift:101` does.
- A new module that copies the fixture inherits the defect.
- Root cause: one module-supplied Bool encodes both "the UI may issue a request" and "recovery is not vetoed".

**Remediation (S–M)**
- Split the protocol into explicit, Host-derived semantics:
  - `hostRecoveryVetoed: Bool`, defaulting to `!session.status.protocolCompatible`;
  - `hostActionsEnabled`, used only for connect/refresh.
- Have the card enable "Restart backend" from Host-owned session state (`!backendAvailable && !busy && !vetoed`), not from a module projection.
- Fix the fixture and the harness stub.

**Verify**
- Model-level test per module: force a startup failure, then recovery exhaustion. Assert the card primary action is enabled and that `consumeAutomaticBackendRestartIfEligible` returns true while the target is running.
- Rerun the Hades I and Hades II frontend journeys and `test_host_connection_policy_dev8.py`.

---

### F2. Backend start, log-session start and target-lifetime ordering are module-owned and implemented three ways; legacy overload kept (high)

**Evidence [fact]**
- **The protocol carries both overloads** (`TrainerGameModule.swift:83-84`). The `observation:` variant was added later as a forwarding default "so existing modules can continue consuming only presence" (`:108-112`; commit `df38ada4`, 2026-10-16). The Host only ever calls `observation:` (`TrainerGameContext.swift:110,181`).
- **Hades II** implements both. Its `observation:` writes the log-session boundary, calls its own `running:`, then **starts the backend** (`Hades2Model.swift:479-498`). Commit `5db0cff4`, titled "bind backend startup after target session initialization", moved `startBackend()` from `init` into this hook. Its backend therefore starts only because `TrainerGameContext.init` calls the lifetime hook once, synchronously (`TrainerGameContext.swift:110`). That happens before the Context subscribes; see the comment and the patch at `:106-108,128-130`.
- **Hades I** starts the backend from `DispatchQueue.main.async` in `init` (`HadesModule.swift:144-147`). Its `observation:` writes the same log-session boundary with identical code (`:172-179`).
- **The fixture** starts from `DispatchQueue.main.async` in `init` (`ReferenceFixtureModule.swift:35-37`). It has no log sink and no lifetime handling.
- **Hades II re-runs `startBackend()` on every target lifetime change**, guarded by `!isStarted`. A stopped backend is therefore implicitly restarted by a game launch. This second restart owner sits outside `TrainerConnectionPolicy`. Hades I has no such path; combined with F1, it has none at all.

**Why it matters**
A new module must rediscover an unwritten ordering contract: target log session first, then backend start, then backend logs. It also has to pick among three start strategies, two of which depend on main-queue hop timing. "Who may restart the backend" has two owners for Hades II and zero working owners for Hades I.

**Remediation (M)**
- Make the Context own startup. Add `TrainerHostModel.hostStart(observation:)`, or have the Context call `session.start(...)` itself with closures the module supplies.
- Have the Context call `logSink.targetLifetimeChanged(...)` before notifying the module (see F15 for log ownership).
- Delete `hostTargetLifetimeChanged(running:)` from the protocol. Keep a private helper inside Hades II if it still wants one.
- Remove Hades II's lifetime-triggered `startBackend()` once F1 makes Host restart reliable.

**Verify**
- `test_backend_session_recovery_dev8.py` and `test_multi_game_context_state.py`.
- The Hades II log-session ordering tests (a target session exists before the first backend line).
- The reference session integration test.
- Hades II real-attach acceptance stays separate.

---

### F3. Backend status is mirrored into every model and read back by the Host (high)

**Evidence [fact]**
- `TrainerBackendSession` is "intentionally not ObservableObject" and delivers status to a **single** `onStatusChange` closure supplied by the module (`TrainerBackendSession.swift:20-23,36,72`).
- Each module therefore keeps a `@Published backendStatus` copy and re-derives the protocol's `backendAvailable`, `busy` and `operation` from it:
  - Hades I: `HadesModule.swift:7,82-84,803-815`
  - Hades II: `Hades2Model.swift:39,53-58,997-1024`
  - Fixture: `ReferenceFixtureModule.swift:5,13-15,73-75`
- The Host mixes sources inside one function. It reads `session.currentStatus.requiresTargetRestart` directly from the session (`TrainerGameContext.swift:210`), but `model.backendAvailable` and `model.busy` from the module (`:212,219,226`).
- **Hades II writes into its mirror.** Its `error` and `notice` setters mutate `backendStatus.error` and `backendStatus.notice` (`Hades2Model.swift:107-133`). `clearCompletedLogs()` sets `notice = "host.logs.cleared"` (`:2239-2245`). The next session status callback overwrites these values.
- Host-owned Save Management requests share the same session (`TrainerSaveManagerModel.swift:188`). Their busy state reaches the Host only through the module's mirror.

**Why it matters**
Every module must remember to mirror status exactly and promptly. A module that delays, filters or mutates the mirror silently changes the Host's connection policy (see F1). This is the clearest "Host behavior each module reimplements".

**Remediation (M)**
- Make the session status observable from the Context: a `@Published` on the Context, or a multi-observer `observeStatus` like the existing `observeLifecycle`.
- Have the Host derive `backendAvailable`, `busy` and `operation` itself and drop them from `TrainerHostModel`.
- Modules keep a read-only projection if they need one. Hades II's Core-error/notice bridging moves to its own feedback state (F5), not into the mirror.

**Verify**
- Context and connection-policy tests.
- Save-management-while-busy journeys.
- A Hades II feedback test confirming that the Core error banner and the module token still behave as specified.

---

### F4. Hades II global namespace and UserDefaults keys are not module-scoped (high)

**Evidence [fact]**
- **The whole product compiles as one Swift module** (`build.sh:338-349`: one `swiftc` call over `App + Core + all selected frontends`).
- **Hades I prefixes every top-level type.** Hades II declares 12 unprefixed globals:
  - `ShortcutAction`, `BoonOption`, `MaterialResource`, `ElementCount`, `TrainerProfile`, `DiagnosticCheck`, `CurrentRunTrait`, `CurrentRunTraitScope`, `TraitLevelCapability`, `TraitRarityCapability`, `TraitRemovalCapability`, plus an `extension Sequence where Element == BoonOption`.
  - Sources: `Hades2Types.swift:3,22,56,80,169,176,182,197,202,207,212,264`.
  - `TrainerProfile` uses Core's `Trainer*` prefix, so it reads as a Core type.
- **UserDefaults keys:**
  - Hades I uses `hades.shortcut.<action>` (`HadesTypes.swift:384-386`).
  - Hades II uses **unprefixed** `shortcut.action.<action>`, `shortcut.layoutVersion` and `shortcut.action.godMode` (`Hades2ShortcutStore.swift:162,312-331`).
  - All modules share `UserDefaults.standard` in the unified bundle.
- **History.** These names date from the single-game baseline (`31297c90`, 2026-09-18); the multi-game Host came later (`03669425`, 2026-10-25).
- **The isolation test** (`tests/test_cross_game_isolation.py`) checks only Core/build tokens and fixture↔Hades II leakage. It does not check identifier collisions between modules.

**Why it matters**
A third module that declares `ShortcutAction`, `DiagnosticCheck` or `TrainerProfile` fails to compile in the unified product, but only when built together. A module that uses `shortcut.action.*` corrupts Hades II's shortcuts. This is a single-game stopgap that became a constraint on every future module.

**Remediation (M)**
- Prefix the Hades II types: `Hades2ShortcutAction`, `Hades2BoonOption`, `Hades2Profile`, and so on. This is a mechanical rename; there is no wire or storage impact.
- Migrate the Hades II shortcut keys to `hades2.shortcut.*`. Do it once inside `Hades2ShortcutStore.loadAndMigrate`, which already owns versioned migration: bump `layoutVersion` to 7 and read the old keys once.
- Add a cheap build-time guard. In the module matrix, compile the fixture plus both Hades modules in one product (already done); add a lint that every top-level type in `Sources/<Game>/` carries that module's prefix and every UserDefaults key starts with `<id>.`.

**Verify**
- Unified `--typecheck --all`, plus a new shortcut-migration test (v6 unprefixed → v7 prefixed, no override loss).
- `test_shortcut_chord_semantics.py`.

---

### F5. Feedback, current issues, logs and diagnostics are duplicated per module, and the copies diverge (med)

**Evidence [fact]**
- **Feedback state machine, near-identical in both:**
  - State: `feedback`/`feedbackNotice`, `feedbackDetailsPresented`, `feedbackDetailsNoticeID`.
  - Methods: `presentFeedback`, `dismissFeedback`, `showFeedbackDetails`, `closeFeedbackDetails`.
  - Sources: `HadesModule.swift:57-59,611-630`; `Hades2Model.swift:98-100,1026-1048`.
  - The views are identical one-liners over `TrainerOperationFeedback` (`HadesTrainerView.swift:4-16`, `Hades2OperationFeedback.swift`).
- **Current issues.** Both append the backend error, with different dedupe rules (`HadesCurrentIssues.swift:8-18` dedupes by text; `Hades2CurrentIssues.swift:6-12` does not).
- **Log actions.** Both have `openLog`, `openLogHistory` and `clearCompletedLogs` over the Core `TrainerLogSink`.
  - Hades I reports a history-open failure (`HadesModule.swift:562-568`).
  - Hades II swallows it with `try?` (`Hades2Model.swift:2233-2237`).
  - They report success through different channels: `presentFeedback` versus the mutated status mirror (F3).
- **Diagnostics export: two unrelated implementations of one user feature.**
  - Hades I assembles JSON in Swift, inlines four log streams and runs `NSSavePanel` (`HadesModule.swift:574-608`).
  - Hades II sends a backend `export_diagnostics` command that reads the Host's log files (`Hades2Model.swift:1661-1668`).
  - `PROJECT_STATUS.md:13` calls Hades I export "Host-owned".
- **Shortcut refusal.** `rejectShortcut` (log + warning + sound) and `playOneShotShortcutResult` are copied. Hades I's comment literally reads "Hades II's refusal feedback" (`HadesModule.swift:686-695`; `Hades2Model.swift:2050-2054,2205-2207`).
- **The fixture has none of this**, so a new module's starting point lacks feedback, logs and diagnostics.

**Remediation (M)**
- Add a Context-owned `TrainerFeedbackCenter` (ObservableObject) holding the notice, the details state, a backend-error issue source and a module issue provider. The Host renders the overlay, so `makeFeedback` can become non-optional and Host-supplied.
- Add a Host-owned `TrainerDiagnosticsActions` (open log, history, clear, export bundle) built on the Context's log sink. Modules add game-specific checks only.
- Pick one export path; a Host-side bundle plus module-supplied report JSON is likely simplest.

**Verify**
- Both module frontend suites (feedback dismissal and details), `test_viewport_feedback.py`, the log-sink tests and the diagnostics-export journeys.

---

### F6. Management catalog, sidebar section list and workbench search are duplicated; the App menu omits Save actions (med)

**Evidence [fact]**
- **`HadesManagementCatalog.make` and `Hades2ManagementCatalog.make` are line-for-line parallel** (`HadesManagementActions.swift:3-44`, `Hades2ManagementActions.swift:3-53`).
- **`TrainerManagementCatalog` has fixed, non-optional slots:** `refresh`, `disableAll`, `profiles`, `shortcuts`, `log`, `diagnostics`, `logHistory` and `clearLogs` (`TrainerManagementGroups.swift:78-113`). A module without profiles, diagnostics or Disable All cannot use it without dummy actions. Each module also supplies its own localized "daily/settings/maintenance" headings.
- **The App menu catalog is built with `openSaveEditor`/`openSaveManagement` = nil** because `Commands` lack the tool-window environment (`HadesTrainerView.swift:1064-1071`, `Hades2HostActions.swift:66-79`). The page builds them with those actions (`HadesManagement.swift:27-32`, `Hades2ManagementViews.swift:95`). The menu and the page therefore list different actions, and the Host-owned Save Management action is wired in by each module.
- **Sidebar section list and current-issues entry: copy-paste**, including the `selectedSection == nil && section == .values` default (`HadesWorkbenchNavigation.swift:255-285`, `Hades2HostActions.swift:3-33`).
- **Header search: same shape** (`HadesWorkbenchNavigation.swift:287-326`, `Hades2HostActions.swift:35-64`).
- **Both define the same six-section enum** (`values/common/boons/resources/rooms/management`) with identical section icons (`HadesWorkbenchNavigation.swift` ~L48-73; `Hades2WorkbenchNavigation.swift:145-169`). Both map icons by localization key strings (`icon(for titleKey:)`).

**Why it matters**
Four of the six `TrainerGameModule` factories (`makeSidebarActions`, `makeHeaderActions`, `makeFeedback`, `makeManagementCommands`) end up as near-identical bodies. A third module re-copies them.

**Remediation (M)**
- Replace those factories with data the module supplies: a section catalog (id, title key, icon, search entries) and a management catalog with **optional** slots plus `additional`.
- Have the Host render the sidebar sections, search, current-issues entry and menu, and inject the Host-owned Save Management and tool-window actions into both page and menu from the Context.
- Keep the six-section taxonomy in the Hades modules; it is Hades vocabulary.

**Verify**
- `test_global_hotkey_routing.py`, the navigation harnesses (`real_module_navigation_harness.py`), both frontend suites, and the reference fixture build (it should now receive a Host sidebar for free).

---

### F7. Presentation registration is bound to view `onAppear`, so each module bypasses it (med)

**Evidence [fact]**
- **Registration time.** The module resolver is registered in `TrainerHostView.onAppear` (`TrainerHost.swift:48-51`), not when the Context is built. `TrainerLocalizationStore.string(_:arguments:language:)` already routes by prefix (`TrainerLocalization.swift:103-111`).
- **Both modules add a static `resolveText` that re-implements the same prefix routing:**
  - Hades II: `Hades2Module.swift:31-47`.
  - Hades I: `HadesModule.swift:933-944`, added by `9ef46510` ("fix(hades): resolve Host-owned workbench labels through Host localization").
  - Hades I's version takes **no `arguments`**, so Host keys lose their arguments.
  - The games define 31 local `text(...)` helpers that call these bypasses.
- **Placeholder syntax:** Host uses `{0}` (`TrainerLocalization.swift:53-55`); Hades II uses `{0}` via JSON tables; Hades I uses sequential `%@` (`HadesModule.swift:963-969`); the fixture uses `{0}`.
- **Storage:** Hades I keeps 269 bilingual pairs in a dictionary literal **inside** `HadesPresentation.text(...)`, rebuilt on every call (`HadesPresentation.swift:4-280`). Hades II loads JSON resources once.
- **Prefix matching** iterates an unordered dictionary and takes the first `hasPrefix` hit (`TrainerLocalization.swift:117-121`). Overlapping or unchecked prefixes (for example `hades.` versus a future `hades.ext.`) would resolve nondeterministically [inference].

**Remediation (S–M)**
- Register every module's resolver when the catalog builds the contexts, so Commands and tool windows can resolve too. Pass the store into `TrainerApplicationCoordinator`, or register lazily on first `string(...)`.
- Delete both `resolveText` functions and route the `text()` helpers through `localization.string`.
- Validate prefixes as non-empty, dot-terminated and non-overlapping at registration.
- Standardize on `{n}`. Make the Hades I table `static let`.

**Verify**
- `test_hades_frontend.py` and the Hades II presentation/terminology parity tests.
- A language-switch journey that includes the App menu and an open Save Editor window.

---

### F8. Command transport: Hades I is stringly typed; Hades II generates timeouts but hand-writes replay classification (med)

**Evidence [fact]**
- **Hades I:**
  - Sends raw command strings with `[String: Any]` at more than 40 call sites in `HadesModule.swift`.
  - Timeouts come from a hand-written string switch (`HadesModule.swift:771-779`).
  - `requiresTrustedTarget` and the offline-intent classification are string arrays (`:783-787`). A typo silently changes replay-safety classification.
  - Its Save Editor passes `timeout: 30` inline (`HadesSaveEditorModel.swift:579-580`).
- **Hades II:**
  - Typed `Hades2Request` (`Hades2API.swift:6-64`) with a generated `Hades2Command.timeout` (`Generated/Hades2Command.generated.swift:66-82`, from `Backend/games/hades2/command_contract.py`).
  - The generator `Tools/generate_hades2_command_binding.py` is **Hades II-specific**, run by tests rather than by `build.sh`.
  - The same API still hand-codes trust and offline classification in Swift (`Hades2API.swift:300-312`).
- **The shared generator `generate_game_binding.py` emits only the descriptor and the catalog.** No generic per-module command-contract binding exists.
- `GAME_MODULES.md` requires that "each game isolates that untyped edge immediately behind a typed request encoder"; Hades I does not.

**Why it matters**
Replay-safety metadata (outcome-unknown, trusted target, offline intent) is a correctness contract. It has two sources of truth for Hades II and an untyped one for Hades I. A third module will copy one of them.

**Remediation (M)**
- Generalize `generate_hades2_command_binding.py` into `generate_module_commands.py`, driven by an optional `commandContract` in `module.json`. Emit an enum with `timeout`, `requiresTrustedTarget` and `offlineIntent` from the backend contract.
- Migrate Hades I to a typed `HadesRequest`.
- Keep the generated file checked in, with the existing parity test pattern.

**Verify**
- `test_hades2_command_binding.py`, extended with trust flags.
- A new Hades I binding parity test, `test_backend_session_recovery_dev8.py`, and the outcome-unknown taint tests.

---

### F9. Save Editor transport envelope duplicated on top of `TrainerSaveEditorReplyCoordinator` (med)

**Evidence [fact]**
- **The two `perform(...)` implementations are the same policy written twice** (`HadesSaveEditorModel.swift:560-613`, `Hades2SaveEditorModel.swift:1427-1510`):
  - check workspace ownership and emit `host.save.error.workspaceExpired`;
  - invalidate `.review` on stage/unstage/cancel/apply;
  - `open` maps to `beginNewDocumentRead()`;
  - release an abandoned workspace on a stale successful `open`;
  - map failures to `applyUnconfirmed` / `incomplete` / `notSent`;
  - outcome-unknown Apply calls `invalidateDocument()`.
- **The surrounding wiring is duplicated too:** lifecycle-observer setup and teardown (`HadesSaveEditorModel.swift:270-281`, `Hades2SaveEditorModel.swift:495-507`) and `close()` releasing only when the generation is current.
- **The wire vocabulary `save_editor_*` and the envelope fields** `workspaceId` / `baselineGeneration` are identical in both adapters.
- **Divergences with no game reason:**
  - search debounce of 0.2 s versus 280 ms (`HadesSaveEditorModel.swift:371`, `Hades2SaveEditorModel.swift:678`);
  - Hades I decodes with `Decodable`, while Hades II hand-parses (108 `as?` casts in `Hades2SaveEditorModel.swift`).
- **The Core coordinator's `Lane` enum lists `advancedDetail`**, which only Hades II uses (`TrainerSaveEditorReplyCoordinator.swift:10-17`).

**Remediation (M)**
Add a Core `TrainerStructuredSaveEditorClient` over the session and coordinator. It would own the envelope, ticketing, abandoned-workspace release, failure-token mapping and the lifecycle observer. Games keep the domain/query/draft semantics described in `ENGINEERING_INVARIANTS.md` §5. Make `Lane` caller-defined (a `Hashable` generic, or `String`).

**Verify**
`multi_game_context_harness.py` reply-coordinator assertions, both module Save workspace tests, and the Save Editor native journeys (convergence).

---

### F10. Draft/observation sync contract implemented twice, very differently (med)

**Evidence [fact]**
- **The invariant** (`ENGINEERING_INVARIANTS.md` §6): "background observation preserves a focused/in-progress draft, refreshes an unfocused displayed value…"
- **Hades I** implements it generically: a `drafts: [EditField: String]` dictionary, an `observedDrafts` projection and one `onChange` loop (`HadesTrainerView.swift:31-32,59-77`).
- **Hades II** implements it by hand: about 45 `@ViewState` string drafts plus `*Initialized` flags (`Hades2View.swift:27-71`), four snapshot structs (`Views/Hades2ViewSnapshots.swift`) and four sync functions with per-field `focusedField != …` checks (`Hades2View.swift:953-1160`).
- **`private typealias ViewState = SwiftUI.State`, with the comment "CLT does not ship SwiftUIMacros"** (`Hades2View.swift:5-6`, from the baseline). Hades I uses `@State` in the same compilation, so the workaround appears obsolete [inference].

**Remediation (M)**
- Promote the Hades I pattern to Core as `TrainerObservedDrafts<Field: Hashable>`, with an `observe(_:focused:)` / `binding(_:)` API. Two real adapters exist.
- Migrate Hades II field groups incrementally.
- Remove the typealias.

**Verify**
`test_runtime_text_edit_completion.py`, `test_hades2_view_state_flow.py`, the Hades II gathering, chaos-gate and force-rerolls frontend tests, plus native focus journeys (convergence).

---

### F11. Hades-family vocabulary sits in Core because the "two adapters" are siblings (med)

**Evidence [fact]**
- **`TrainerTraitManagerLayout`** is documented as "geometry for equivalent current-boon/effect manager controls". Its columns are level + rarity + remove (`TrainerTraitManagerLayout.swift:3-33`).
- **`TrainerAcquisitionRarity` and `TrainerAcquisitionPanel`.** The algorithm is a generic "reconcile a selection to a legal subset under a native order", but it is named for rarity. Hades I passes a literal Hades rarity order (`HadesModule.swift:449-453`).
- **`TrainerSemanticIcon.Context`** contains `fishing`, `portal` (Chaos) and `characterReward`. `Context.reward`, `Action.save` and `Action.load` are unused (`TrainerSemanticIcon.swift:40-46`).
- **Fixed management slots** require Profiles, Diagnostics and Disable All (F6). `TrainerHotkeyLayout.disableAllChord` reserves ⌃⌥⌫ for every module (`HotkeyChord.swift:123-128`).
- **`TrainerDualInlinePickerLayout`** is "Used by exact-boon rows" (`:4`).
- **`TrainerFeaturePresentation`'s `dormant` vocabulary** is listed as Core-owned in `ENGINEERING_INVARIANTS.md` §2. §1 says Core does not own "desired/active/dormant semantics", so the two sections are in tension.
- **The isolation test bans only Hades II tokens** (`Hades2`, `CurrentRun`, `boonRarity`, …) from Core (`tests/test_cross_game_isolation.py:20-31`). `hades`, `boon`, `trait` and `rarity` are not checked.

**Judgement**
- Genuinely neutral: `TrainerStatControls` (vital/amount/counter/stat/multiplier cards with an optional lock), `TrainerResourceControls`, `TrainerFeatureControls` toggle/multiplier rows and `TrainerSaveEditorShell`.
- Hades vocabulary in disguise: the trait-manager layout, the acquisition-rarity naming, the `Context` icons and the required management slots.
- Low risk at runtime; the cost is that a third author cannot tell what is optional.

**Remediation (S–M)**
- Rename to neutral names (for example `TrainerOrderedOptionReconciler`, `TrainerInventoryRowLayout` with caller-specified columns), or move the Hades-only constants back into each Hades module.
- Make the management slots optional (F6).
- Extend the isolation test token list to include `Hades`, `hades.`, `boon` and `Boon` for Core code. Comments can be excluded if needed.
- Restate the "two adapters" rule as "two adapters, at least one of which is not a sibling of the other", or document a deliberate "Hades family" exception.

**Verify**
Isolation test, unified typecheck and fixture matrix.

---

### F12. Hades II shortcut migrations live in Core; the two shortcut stores diverge (low–med)

**Evidence [fact]**
- **Core `HotkeyChord` carries `legacyV4Keys`, `controlOptionDefault(index:)` ("Historical v4 migration only") and `controlOptionDigit`** (`HotkeyChord.swift:59-118`). These are consumed only by `Hades2ShortcutStore.swift:235,270,276,284`. This contradicts the same file's comment at `:121`: "Modules own action identities, persistence and migrations".
- **`Hades2ShortcutStore` carries v3, v4 and v5 migrations**, a "known broken v4 migrated layout" reconstruction (`:161-293`), and also strips `godMode`/`damageEnabled`/`gardenQoL` keys on every init (`:39-40,328-329`).
- **The two stores differ in behavior:**
  - Hades II drops an override equal to the default (`:89-93`); Hades I persists it (`HadesTypes.swift:371-375`).
  - Hades II Profiles carry shortcut payloads (`Hades2API.swift:262`, `Hades2Model.swift:1638-1642`); Hades I Profiles do not (`HadesModule.swift:551-552`). The product's "Profile" therefore means different things per game.

**Remediation (S)**
- Move the three legacy helpers into `Hades2ShortcutStore` (private).
- Extract a Core `TrainerShortcutStore<Action>` covering overrides, defaults, the conflict rule and namespaced persistence, used by both modules; Hades II keeps its migration preamble. This combines with F4's key prefixing.
- Decide product-wide whether Profiles include shortcuts.

**Verify**
`test_shortcut_chord_semantics.py`, the Hades II shortcut migration tests and `test_global_hotkey_routing.py`.

---

### F13. `activationPending` has different meanings in each adapter (med)

**Evidence [fact]**
- **Core derives the phases** pending → waiting/mismatch from `activationPending` (`TrainerFeatureControls.swift:27-35`).
- **Hades I** sets it to `pendingFeatureIntents[feature] != nil`, meaning the request is in flight (`HadesModule.swift:206`).
- **Hades II** sets it to `isFeatureActivationPending`, backed by a **0.9 s `asyncAfter` timer** started on enable, on connect and when observed state disagrees (`Hades2Model.swift:1128-1146,1167-1170,891-905`; `Hades2FeaturePresentation.swift:12`).
- So for Hades II the UI flips from "pending" to the warning state "mismatch" after a fixed delay, regardless of request outcome.

**Why it matters**
The shared phase contract is underspecified. A third module must guess which meaning to implement, and a time-based heuristic in a presentation input conflicts with the event-driven policy.

**Remediation (S)**
- Define `activationPending` in Core as "an intent request is in flight or awaiting its first post-reply observation".
- Replace the Hades II timer with a request-scoped intent, as Hades I does. If a settling window is truly needed for resident hooks, make it an explicit, documented Hades II-owned observation rather than a timer.

**Verify**
`test_hades2_model_flow.py` feature-phase assertions and a Hades I phase test. Real-game observation of activation latency is a separate acceptance item.

---

### F14. God objects: file size reflects mixed responsibilities (med; large but incremental)

All evidence below is **[fact]**.

**`Hades2Model.swift` (2,314 lines)**
- 129 `@Published` properties, of which 101 are `@Published var` (publicly settable), including observations such as `connected`, `pid`, `health` and `capabilities` (`:37-270`). By contrast, Hades I uses `private(set)` for observations.
- It mixes:
  - Host lifecycle and launch gate (`:457-616`);
  - backend start and reset (`:624-746`);
  - sparse-patch projection (`:749-926`);
  - feedback and receipts (`:927-1048`);
  - transport admission counters (`:1062-1123`);
  - text-edit validation (`:1257-1372`);
  - about ten domain action families (`:1384-1975`);
  - shortcuts, about 230 lines (`:1976-2224`);
  - logs (`:2225-2249`);
  - termination (`:2251-2293`).
- It writes Core status mirrors (F3).

**`Hades2SaveEditorModel.swift` (1,604 lines)**
- 15 value types, transport (F9), manual JSON decoding (108 `as?` casts; `decodeEntry`, `intValue`/`doubleValue`/`hashableScalar` at `:1512-1604`), text/typed/membership/retired drafts, debounce, paging and review/receipt.

**`Hades2View.swift` (2,012 lines)**
- About 45 draft states plus sync (F10).
- Hard-coded native catalog tables: `worldActionGodIDs`, `worldActionRoomIDs` and more than 40 `worldActionUnavailableReasonIDs` (`:1254-1332`). These are native identifiers in a view instead of the terminology owner.

**`HadesModule.swift` (970 lines)**
- Named "Module", but it holds the model (contrary to the `GAME_MODULES.md` file layout), the `HadesGameModule` declaration and an NSSavePanel diagnostics exporter.

**`TrainerLogSink.swift` (910 lines)**
- It mixes:
  - bounded async append with backpressure (`:175-212`);
  - target-session bundle lifecycle (`:224-270,391-546`);
  - **legacy single-file log migration** (`archiveLegacyLogsLocked`, legacy bundle recovery: `:569-674,883`);
  - retention pruning (`:676-748`);
  - a **test-only unmanaged mode**: `init(url:)`, used by about 10 tests and no production code. Its `managedSessions` flag branches at 8 sites (`:133-139,225,242,274,284,291,327,365,375`).

**`BackendProcess.swift` (753 lines)**
- Mixed (process, Linux pipe reader, stderr buffering, file-session transport, profiler), but invisible to modules; not a module-cost driver.

**Remediation (incremental)**
- Split `Hades2Model` along the seams F2, F3, F5 and F12 remove. The Host-owned parts disappear first.
- Then split `Hades2RuntimeLifecycle` (launch gate + run-log) and per-domain controllers (world actions, acquisition, traits, gathering) that share one `send` admission object.
- Make observations `private(set)`.
- For `TrainerLogSink`: extract `LegacyLogMigration` (with a removal date once supported installs have migrated) and replace `init(url:)` with a test double behind a small protocol.

**Verify**
Each extraction keeps `test_hades2_model_flow.py`, `test_hades2_view_state_flow.py` and the log-sink tests green. Tests must not shift.

---

### F15. Hotkey scope and log identity are free strings chosen by the module (med)

**Evidence [fact]**
- **`GlobalHotkeys(gameID:)` registers only when `registry.selectedGameID == gameID`** (`GlobalHotkeys.swift:147-170`). The Host sets `selectedGameID` from `descriptor.id` (`TrainerGameContext.swift:299,314`).
- **The two modules supply the ID differently:**
  - Hades I hard-codes `"hades"` for hotkeys and the log sink (`HadesModule.swift:78,142`).
  - Hades II uses `Hades2GameModule.descriptor.id` (`Hades2Model.swift:2209-2211`, `Hades2Module.swift:50`).
- **Each module also re-builds the same `TrainerLogSink.TargetIdentity`** from its descriptor (`HadesModule.swift:173-176`, `Hades2Model.swift:488-495`).

**Why it matters**
A typo or a renamed module ID makes shortcuts never register, or makes logs land in another game's directory. Neither failure is visible at compile time.

**Remediation (S)**
Pass a `TrainerModuleServices` to `makeModel`, holding the session, a scoped `GlobalHotkeys` factory, the `TrainerLogSink` and the descriptor. The Context constructs all of them from `Module.descriptor`.

**Verify**
`test_global_hotkey_routing.py`, `test_multi_game_context_state.py` and the log-directory tests.

---

### F16. No main-actor isolation anywhere in the seam; root invalidation fan-out (med)

**Evidence [fact]**
- **Compilation** is `swiftc -parse-as-library -O` in Swift 5 language mode, with no strict-concurrency flags (`build.sh:338-349`).
- **Isolation:** `TrainerGameContext`, the coordinator and the localization store are `@MainActor`.
  - Not isolated: `TrainerHostModel`, `TrainerBackendSession`, `BackendClient`, `GlobalHotkeys`, `TrainerTargetProcessMonitor`, and all three models.
- **Main-thread correctness relies on convention:**
  - `DispatchQueue.main.async` in model `init` (`HadesModule.swift:144`, `Hades2Model.swift:447`, `ReferenceFixtureModule.swift:35`);
  - `asyncAfter` for recovery and timeouts (`TrainerBackendSession.swift:455`, `BackendClient.swift:400`);
  - Carbon callbacks hopping to main (`GlobalHotkeys.swift:106`).
- **Every `@Published` change in any game's model re-renders the root:**
  - it fires `TrainerGameContext.modelChanged`, which always ends with `objectWillChange.send()` (`TrainerGameContext.swift:112-114,147-166`);
  - `AnyTrainerGameContext` forwards it (`:270`);
  - the coordinator forwards and calls `attemptTermination()` (`:316-319`);
  - `TrainerGamePages` observes the coordinator and rebuilds all sidebar cards (`TrainerGamePages.swift:5,13-18`).
  - A Hades II payload apply touches dozens of properties, each scheduling a `receive(on: main)` hop and a reconcile.

**Why it matters [inference]**
- A new module that uses `async`/`Task` or a background queue gets no compiler help.
- Root invalidation grows with module count and per-module churn: hidden games still re-render the root.
- The doc claim that "switching modules does not invalidate every control" covers page visibility only.

**Remediation (M)**
- Annotate `TrainerHostModel`, `TrainerBackendSession` (public API), `GlobalHotkeys` and the monitor as `@MainActor`.
- Turn on `-strict-concurrency=targeted` in the typecheck lane first.
- In the Context, forward only the Host-relevant fields: `removeDuplicates` on a `(backendAvailable, busy, connected, operation, status tokens)` snapshot rather than every `objectWillChange`. The coordinator should observe only termination readiness.

**Verify**
Typecheck under the targeted strict mode; `test_multi_game_context_state.py`; and a render-count probe in the visual hierarchy harness, as an observation and not an assertion.

---

### F17. Lifecycle defaults hide required behavior (low–med)

**Evidence [fact]**
- **The default `connectAutomaticallyFromHost` calls `toggleConnectionFromHost()`** (`TrainerGameModule.swift:95-97`). The protocol has no idempotent "connect" primitive; Hades I's toggle sends `disconnect` if `connected` is true (`HadesModule.swift:167-169`). The policy guards `!connected` before calling, so this is safe today [inference]. It is safe only by caller discipline.
- **`prepareForTermination` has no default.** Every module must stop the session itself, with `suppressTerminationError`, and flush diagnostics: `HadesModule.swift:752-767`, `Hades2Model.swift:2287-2292`, `ReferenceFixtureModule.swift:56-59`.
- **`beginTerminationFromHost`, `hostDidBecomeActive` and `launchActionFromHost`** are defaulted no-ops that the fixture does not exercise.

**Remediation (S)**
- Replace the toggle with `connectFromHost(reason:)` and `disconnectFromHost()`.
- Have the Context stop the session after the module's completion fires, keeping the module hook for game-specific finalization only.

**Verify**
Quit and termination tests in the context harness; Hades I and Hades II exit-cleanup journeys.

---

### F18. Stale-PID adoption guard exists only in Hades I (low–med)

**Evidence [fact]**
- Hades I rejects a `connected` observation whose `pid` differs from the Host's current target observation, or that arrives after exit (`HadesModule.swift:869-873`).
- Hades II only invalidates text edits on a PID change (`Hades2Model.swift:760-761`). It never compares against Host target identity.

**Why it matters**
"Never adopt an observation from a prior OS process lifetime" is a Host-level invariant (`ENGINEERING_INVARIANTS.md` §3). It is enforced in one adapter only, and a new module would not know to add it.

**Remediation (S)**
- Have the Context expose the current `TrainerTargetObservation` to the model, or validate a module-declared `observedPID` in the reply envelope.
- Add the check to Hades II.

**Verify**
Context lifecycle tests covering a rapid-replacement launch; a Hades II model test with a mismatched PID.

---

### F19. Retired or unused seam surfaces (low)

All evidence below is **[fact]**.

- **`TrainerGamePresentation.headerTitle`** is a *required* init parameter, and `platformLabel` is optional. Neither is read by production code; only `sidebarIconSystemName` is used (`TrainerGameModule.swift:49-59`, `TrainerSidebar.swift:103`).
- **`TrainerPageHeader`** is used only by `tests/visual_hierarchy_harness.py`.
- **`typealias ActiveGameModule`** is emitted for single-module builds (`generate_game_binding.py:38-39`) and consumed only by tests (`test_host_target_ownership.py`, `test_module_contract_round13.py`). It is a relic of the single-game App.
- **The root file `ACTIVE_GAME_ID`** (contents `hades2`, since baseline) is not read by any tool; `build.sh:482` writes a separate copy into the bundle.
- **`GameModuleDescriptor.backendGameID`** is always generated equal to `id` (`generate_game_binding.py:21`).
- **Unused:** `TrainerLocalizationStore.removeModulePresentation` and `TrainerSemanticIcon.Context.reward` / `Action.save` / `Action.load`.

**Remediation (S)**
Delete them, or make them read where intended (for example, show `headerTitle` or drop it). Update the affected test harnesses at the same time.

**Verify**
Unified typecheck, fixture matrix and the affected harness tests.

---

### F20. Small stopgaps (low)

All evidence below is **[fact]**.

- **Hades II still sends the retired `"multiplier": 100`**, with the comment "Keep the v17 payload shape; the retired probability value is neutral" (`Hades2API.swift:188-190`). The backend contract should either drop the field or reject it.
- **Hades I's Save Editor embeds an untranslated English sentence** as a token argument (`HadesSaveEditorModel.swift:303-306`).
- **Core `TrainerBackendSession` writes Chinese log text** (`:116,241,320,334,346,371,440`). Hades II states that logs "stay language-neutral" (`Hades2Model.swift:2226-2227`).
- **`TrainerTextToken`**, a presentation type, lives in `Core/Runtime/BackendClient.swift:12-20`.

**Remediation (S)**
Remove or translate these one at a time, each with its owning test.

---

## Suggested sequencing (so new modules become cheap)

1. **Quick, low-risk (S).**
   - F1: split recovery veto from actions-enabled; fix the fixture. Highest value per line.
   - F19: dead surfaces.
   - F12: move the Hades II legacy helpers out of Core.
   - F20.
   - F7: register presentations at Context build; delete `resolveText`.
2. **Host owns lifecycle services (M).** Do F2, F3, F15 and F17 together:
   - introduce `TrainerModuleServices` (session, observable status, log sink, scoped hotkeys, descriptor, target observation);
   - have the Context start the backend and own log-session ordering;
   - drop `hostTargetLifetimeChanged(running:)`.
   - Then upgrade the reference fixture to use the new services, so it becomes a real template.
3. **Extract the duplicated plumbing (M).** Each item has two real adapters today:
   - F5: feedback center + diagnostics actions;
   - F6: data-driven sections, search and management with optional slots, with Host-injected Save actions in both page and menu;
   - F9: structured save-editor client;
   - F10: observed drafts;
   - F12: shortcut store.
4. **Hades II single-game residue (M).** F4: prefix types and keys, with a v6→v7 migration and an identifier-prefix lint.
5. **Contract tightening.**
   - F8: generic command-contract binding carrying replay-safety flags.
   - F13: event-based `activationPending`.
   - F11: neutral renames and a broader isolation test.
   - F16: `@MainActor` and strict concurrency in the typecheck lane.
6. **Incremental.** F14: god-object splits, which shrink naturally after steps 2–3.

## Checked and found acceptable (to avoid false positives)

- **Neutral Core components** used by both modules with no game semantics:
  - `TrainerStatControls` (lockable metric cards), `TrainerResourceControls` (picker + amount + optional lock);
  - `TrainerFeatureToggleRow` / `TrainerFeatureMultiplierRow`;
  - `TrainerSaveEditorShell` (header, document bar, workbench, paging);
  - `TrainerSaveTypes`, `TrainerSaveManagerModel`/`View`.
- **No timer polling in Core lifecycle.** `TrainerTargetProcessMonitor` is NSWorkspace event-driven (`:21-28`), `Hades2RunLogWatcher` uses `DispatchSource` file events, and `TrainerConnectionPolicy` is pure state. The only timers are request timeouts, recovery backoff, search debounce and the F13 grace timer.
- **Core `TrainerSaveEditorReplyCoordinator`** is a sound shared primitive. The debt is only in the duplicated layer above it (F9).
- **Generated binding seam** (`generate_game_binding.py`): the descriptor and catalog generation are clean and game-agnostic. The Commands composition only shows the selected game's menu. The gap is F8 (no generic command binding) and F19 (`ActiveGameModule` relic).
