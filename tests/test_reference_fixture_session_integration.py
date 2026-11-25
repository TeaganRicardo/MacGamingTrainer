MGT_PLATFORM = "macos"

from macos_fixture_policy import launch_fixture
from fixture_budgets.multi_game import JOURNEY_BUDGETS
from swift_test_compiler import compile_swift_test, main_actor_entrypoint
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "ContractFixtures/reference_module"

# Linux contracts discover every portable test automatically. This integration
# intentionally compiles SwiftUI/AppKit and runs a real Host backend process.
if sys.platform != "darwin":
    print("reference_fixture_session_integration_macos_only")
    raise SystemExit(0)

SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required")

fixture_source = (FIXTURE / "frontend/ReferenceFixtureModule.swift").read_text(encoding="utf-8")
assert "ReferenceFixtureLocalizationProbe" in fixture_source, (
    "reference fixture does not consume the Host localization seam"
)
assert "model.enabled.toggle()" not in fixture_source, (
    "fixture content still bypasses the backend session with a local-only toggle"
)

harness = r"""
import AppKit
import Combine
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func waitUntil(_ seconds: TimeInterval, _ predicate: @escaping () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if predicate() { return true }
        RunLoop.current.run(until: Date().addingTimeInterval(0.01))
    }
    return predicate()
}

"""

journey = r"""
let args = CommandLine.arguments
if args.count != 5 { fail("expected backend, Python, target PID and journey mode") }
let descriptor = ReferenceFixtureGameModule.descriptor
if !descriptor.targetBundleIdentifier.isEmpty { fail("suffix-only variant gained a Bundle ID") }
let monitor = TrainerTargetProcessMonitor(processName: descriptor.targetProcessName,
    bundleIdentifier: descriptor.targetBundleIdentifier,
    executablePathSuffix: descriptor.targetExecutablePathSuffix)
if args[3] == "absent" {
    if monitor.isRunning { fail("same-name unrelated executable was recognized as the reference target") }
} else if monitor.targetObservation.processIdentifier != pid_t(Int32(args[3])!) {
    fail("generated suffix-only descriptor did not recognize its exact target process")
}
if args[4] == "identity-only" { print("reference_suffix_identity_ok"); exit(0) }
if ReferenceFixtureGameModule.managedBackupEditor != nil {
    fail("A module without an editor must retain the default absent backup action")
}

// Exercise the actual connection card's callbacks without launching a game.
// The Host chooses placement and state; an optional module launch action is
// used only when the target is absent and the backend is available.
var selectedActions: [String] = []
func connectionCard(backend: Bool = true, connected: Bool = false,
                    running: Bool = false, supportsLaunch: Bool = true) -> TrainerConnectionStatusCard {
    TrainerConnectionStatusCard(
        connected: connected,
        backendAvailable: backend, actionsEnabled: true, restartEnabled: true,
        onRefresh: { selectedActions.append("refresh") },
        onPrimary: { selectedActions.append(connected ? "disconnect" : "connect") },
        onRestart: { selectedActions.append("restart") }, targetRunning: running,
        onLaunch: supportsLaunch ? { @MainActor in selectedActions.append("launch") } : nil
    )
}
for (card, title) in [
    (connectionCard(), "host.launchGame"),
    (connectionCard(running: true), "host.connectGame"),
    (connectionCard(connected: true, running: true), "host.disconnectGame"),
    (connectionCard(backend: false), "host.restartBackend"),
    (connectionCard(supportsLaunch: false), "host.connectGame"),
] {
    if card.primaryActionTitleKey != title { fail("connection action label does not match target state") }
    card.performPrimaryAction()
}
if selectedActions != ["launch", "connect", "disconnect", "restart", "connect"] {
    fail("connection card routed to the wrong module/Host action: \(selectedActions)")
}
let backendPythonURL = URL(fileURLWithPath: args[2])

guard let temporaryHome = ProcessInfo.processInfo.environment["HOME"] else { fail("HOME is not set") }
func testLog(_ name: String) -> TrainerLogSink {
    TrainerLogSink(url: URL(fileURLWithPath: temporaryHome).appendingPathComponent(name))
}
func logContents(_ sink: TrainerLogSink) -> String {
    sink.flush()
    return (try? String(contentsOf: sink.currentLogURL(), encoding: .utf8)) ?? ""
}

let missingSession = TrainerBackendSession(
    client: BackendClient(process: BackendProcess(executableURL: backendPythonURL))
)
let missingLog = testLog("missing.log")
let missingContext = TrainerGameContext<ReferenceFixtureGameModule>(
    session: missingSession, backendScriptURL: URL(fileURLWithPath: "/definitely/missing/mgt-backend.py"),
    logSink: missingLog
)
let missingModel = missingContext.model
guard waitUntil(1.0, { missingModel.backendStatus.errorCode != nil }) else {
    fail("missing backend startup failure was not surfaced")
}
if missingModel.backendStatus.errorCode != "backend_start_failed" {
    fail("missing backend startup failure identity changed")
}
if missingModel.backendStatus.error.contains("/definitely/missing") {
    fail("startup diagnostic path leaked into user presentation")
}
if !logContents(missingLog).contains("/definitely/missing") {
    fail("startup diagnostic detail did not reach logging")
}

// A session whose startup failed before recording a configuration cannot
// restart, so the Host must not offer an action that would do nothing.
if missingContext.backendRestartAllowed || missingContext.connectionStatusCard(onLaunch: nil).primaryActionEnabled {
    fail("Host offered a restart that a never-configured session cannot perform")
}

// A worker that keeps exiting exhausts the session's bounded recovery. That
// unavailable state is exactly when the Host must keep restart reachable. The
// script lives in the test's temporary HOME, which the runner removes.
let exitingScript = URL(fileURLWithPath: temporaryHome).appendingPathComponent("mgt-exiting-backend.py")
do { try "import sys\nsys.exit(3)\n".write(to: exitingScript, atomically: true, encoding: .utf8) }
catch { fail("could not write the exiting backend fixture: \(error)") }
let exhaustedSession = TrainerBackendSession(
    client: BackendClient(process: BackendProcess(executableURL: backendPythonURL))
)
let exhaustedContext = TrainerGameContext<ReferenceFixtureGameModule>(
    session: exhaustedSession, backendScriptURL: exitingScript, logSink: testLog("exhausted.log")
)
let exhaustedModel = exhaustedContext.model
func waitForExhaustedBackend(_ stage: String) {
    guard waitUntil(15.0, {
        let status = exhaustedModel.backendStatus
        return !status.backendAvailable && !status.busy && status.errorCode != nil
    }) else {
        fail("exiting backend did not exhaust recovery (\(stage)): \(exhaustedModel.backendStatus)")
    }
}
// `TrainerBackendSession.restart()` synchronously marks the session busy with
// the restart operation and clears any earlier notice, so a new request is
// distinguishable from a previous cycle's "restarted" notice.
func requireRestartRequested(_ stage: String) {
    let status = exhaustedSession.currentStatus
    guard status.busy, status.operation.key == "host.restartBackend", status.notice.isEmpty else {
        fail("\(stage) did not reach the backend session: \(status)")
    }
}
waitForExhaustedBackend("startup")
// The module request gate is false exactly while the backend is down; it must
// not disable either Host recovery path.
if exhaustedModel.hostActionsEnabled {
    fail("an unavailable backend unexpectedly accepts module requests")
}
let manualRestart = MainActor.assumeIsolated { () -> (title: String, enabled: Bool) in
    let card = exhaustedContext.connectionStatusCard(onLaunch: nil)
    let result = (card.primaryActionTitleKey, card.primaryActionEnabled)
    if result.1 {
        card.performPrimaryAction()
        requireRestartRequested("restart action")
    }
    return result
}
if manualRestart.title != "host.restartBackend" || !manualRestart.enabled {
    fail("Host restart action is unreachable for an unavailable backend: \(manualRestart)")
}
if !exhaustedSession.currentStatus.requiresTargetRestart {
    fail("worker restart cleared the unknown-outcome target trust gate")
}

// InMemoryDefaults (tests/fixtures/swift) keeps this harness off the real
// preferences directory; a real suite there cannot be cleaned up afterwards.
let localizationDefaults = InMemoryDefaults()

let session = TrainerBackendSession(
    client: BackendClient(process: BackendProcess(executableURL: backendPythonURL))
)
let capturedLog = testLog("reference.log")
var fixtureTarget = monitor.targetObservation
let fixtureMonitor = TrainerTargetProcessMonitor(snapshot: { fixtureTarget })
let context = TrainerGameContext<ReferenceFixtureGameModule>(
    session: session, backendScriptURL: URL(fileURLWithPath: args[1]), logSink: capturedLog,
    targetMonitor: fixtureMonitor,
    makeModel: { ReferenceFixtureModel(services: $0, defaults: localizationDefaults) }
)
let model = context.model

// This wait measures a subprocess round trip -- spawn the backend script,
// complete the JSONL hello, receive the protocol versions -- unlike every other
// wait in this harness, which observes a state flip. A 3s budget failed roughly
// one run in three on a loaded machine, and on a CI runner that has just
// compiled Swift for the preceding tests, which is the same 1-in-3 failure. The
// predicate is unchanged and still exact: a backend that never reports 6 and 1
// still fails, only later.
let handshakeBudget: TimeInterval = 30.0
guard waitUntil(handshakeBudget, {
    session.isStarted
        && model.backendAvailable
        && model.backendStatus.backendProtocolVersion == 6
        && model.backendStatus.backendModuleProtocolVersion == 1
}) else {
    // A slow runner and a wedged backend must not produce the same message, or
    // this cannot be triaged without a local reproduction.
    let lastLog = logContents(capturedLog).split(separator: "\n").last ?? "<none>"
    let detail = "within \(handshakeBudget)s status=\(model.backendStatus)"
        + " sessionStarted=\(session.isStarted) sessionRunning=\(session.isRunning)"
        + " lastLog=\(lastLog)"
    fail("reference model did not start the injected Host backend session \(detail)")
}

if model.connected { fail("fixture must start disconnected") }
if model.enabled { fail("fixture must start disabled") }

var failureDone: Bool? = nil
session.send(
    "fail",
    operation: "Reference failure",
    completion: { failureDone = $0 }
)
guard waitUntil(2.0, { failureDone != nil && !model.backendStatus.busy }) else {
    fail("reference failure did not complete")
}
if failureDone != false { fail("reference failure unexpectedly succeeded") }
if model.backendStatus.errorCode != "reference_failure" { fail("reference error identity was not preserved") }
if model.backendStatus.error != "referenceFixture.error.failed" { fail("reference presentation key did not reach Host status") }
if model.backendStatus.errorArguments != ["Fixture Game", "42"] { fail("reference presentation arguments did not reach Host status") }
if model.backendStatus.error.contains("reference fixture diagnostic detail") {
    fail("diagnostic detail leaked into user presentation")
}
if !logContents(capturedLog).split(separator: "\n").contains(where: {
    $0.contains("reference_failure") && $0.contains("reference fixture diagnostic detail")
}) {
    fail("reference diagnostic detail did not reach Host logging")
}

context.performConnectionAction()
guard waitUntil(2.0, { model.connected && !model.busy }) else {
    fail("connect did not round-trip through the real session")
}
model.connectFromHost(reason: .manual)
if model.busy { fail("an explicit connect on an existing connection dispatched work") }

model.setEnabled(true)
guard waitUntil(2.0, { model.enabled && !model.busy }) else {
    fail("set_enabled did not update model from backend reply")
}

// Prove the model observes the same Host-owned session even when the request
// originates outside the model helper.
var directCompletion: Bool? = nil
session.send(
    "set_enabled",
    params: ["value": false],
    operation: "direct session mutation",
    completion: { directCompletion = $0 }
)
guard waitUntil(2.0, { directCompletion != nil && model.enabled == false }) else {
    fail("model is not projecting replies from the injected session")
}
if directCompletion != true { fail("direct session request failed") }

model.setEnabled(true)
guard waitUntil(2.0, { model.enabled && !model.busy }) else {
    fail("fixture could not re-enable through session")
}

let protocolBeforeLanguageChange = model.backendStatus.backendProtocolVersion
let localizationContractPassed = MainActor.assumeIsolated {
    let localization = TrainerLocalizationStore(defaults: localizationDefaults)
    guard ReferenceFixtureLocalizationProbe.hostGameLibrary(using: localization) == "游戏库" else {
        return false
    }
    guard ReferenceFixtureLocalizationProbe.hostConnectionStatus(connected: false, using: localization) == "未连接" else {
        return false
    }
    localization.language = .en
    guard ReferenceFixtureLocalizationProbe.hostGameLibrary(using: localization) == "Game Library" else {
        return false
    }
    guard ReferenceFixtureLocalizationProbe.hostConnectionStatus(connected: true, using: localization) == "Connected" else {
        return false
    }
    guard localizationDefaults.string(forKey: TrainerLocalizationStore.userDefaultsKey) == "en" else {
        return false
    }
    // A module-owned namespace resolves through the same store, proving Core
    // needs no game-specific table. The fixture module supplies its own prefix
    // and resolver, so register exactly what a real module would.
    localization.registerModulePresentation(
        prefix: ReferenceFixtureGameModule.presentationKeyPrefix
    ) { key, arguments, language in
        ReferenceFixtureGameModule.presentationText(key: key, arguments: arguments, language: language)
    }
    guard localization.string(TrainerTextToken(key: "referenceFixture.connected")) == "Fixture Connected" else {
        return false
    }
    guard localization.presentation("referenceFixture.operable") == "Fixture Ready" else {
        return false
    }
    // The key the backend emits on a typed failure must resolve in the
    // fixture's OWN table, with its arguments filled. A key that only travels
    // the wire proves the envelope, not the seam.
    let rendered = localization.string(TrainerTextToken(
        key: "referenceFixture.error.failed", arguments: ["Fixture Game", "42"]))
    guard rendered == "Fixture request failed (Fixture Game, 42)." else {
        return false
    }
    guard localization.string(TrainerTextToken(key: "host.gameLibrary")) == "Game Library" else {
        return false
    }
    guard ReferenceFixtureGameModule.workbenchSections(model: model).map(\.id) == [
        "referenceFixture.main",
        "referenceFixture.management",
    ],
          localization.string("referenceFixture.section.main") == "General",
          localization.string("referenceFixture.section.management") == "Management & Diagnostics" else {
        return false
    }
    let groups = context.managementGroups(localization: localization)
    guard groups.map(\.id) == ["daily", "settings", "maintenance"],
          groups.flatMap(\.actions).map(\.id) == [
              "refreshStatus",
              "disableAll",
              "profiles",
              "shortcuts",
              "log",
              "diagnostics",
              "logHistory",
              "clearLogs",
          ],
          groups.map(\.title) == [
              localization.localized("host.manage.daily"),
              localization.localized("host.manage.settings"),
              localization.localized("host.manage.maintenance"),
          ] else {
        return false
    }
    return TrainerLocalizationStore(defaults: localizationDefaults).language == .en
}
if !localizationContractPassed {
    fail("reference fixture did not preserve the Host live/persisted localization contract")
}
if !model.connected || !model.enabled {
    fail("presentation language changed fixture runtime state")
}
if model.backendStatus.backendProtocolVersion != protocolBeforeLanguageChange || protocolBeforeLanguageChange != 6 {
    fail("presentation language changed protocol identity")
}

// Exercise remaining Host services: typed command binding, shortcuts, profile store, feedback, diagnostics.
if !ReferenceFixtureCommand.setEnabled.offlineIntent(connected: false)
    || ReferenceFixtureCommand.setEnabled.requiresTrustedTarget(connected: false)
    || !ReferenceFixtureCommand.setEnabled.requiresTrustedTarget(connected: true)
    || ReferenceFixtureCommand.diagnostics.requiresTrustedTarget(connected: true)
{
    fail("typed ReferenceFixtureCommand binding flags regressed")
}

model.reportSampleFeedback(argument: "42")
if context.feedback.currentIssues.first?.text != TrainerTextToken(key: "referenceFixture.issue.sample", arguments: ["42"])
    || context.feedback.notice?.text != TrainerTextToken(key: "referenceFixture.issue.sample", arguments: ["42"])
{
    fail("reference fixture feedback center integration failed")
}
model.clearSampleFeedback()
if !context.feedback.currentIssues.isEmpty || context.feedback.notice != nil {
    fail("reference fixture feedback center cleanup failed")
}

let defaultChord = model.shortcutText(.toggleFeature)
let customChord = HotkeyChord(keyCode: 23, modifiers: HotkeyChord.controlModifier | HotkeyChord.optionModifier, keyLabel: "5")
if model.setShortcut(.toggleFeature, chord: customChord) != .applied
    || model.shortcutText(.toggleFeature) != "⌃⌥5"
    || model.setShortcut(.toggleFeature, chord: TrainerHotkeyLayout.disableAllChord) != .conflict(actionID: ReferenceFixtureShortcutAction.disableAll.rawValue)
{
    fail("reference fixture shortcut store integration failed")
}

var savedProfileOK: Bool? = nil
model.saveProfile("fixture-preset") { savedProfileOK = $0 }
guard waitUntil(2.0, { savedProfileOK == true && model.profiles.map(\.name) == ["fixture-preset"] }) else {
    fail("reference fixture profile save failed")
}
model.resetShortcuts()
if model.shortcutText(.toggleFeature) != defaultChord {
    fail("reference fixture shortcut reset failed")
}
model.loadProfile("fixture-preset")
guard waitUntil(2.0, { !model.busy && model.shortcutText(.toggleFeature) == "⌃⌥5" }) else {
    fail("reference fixture profile load did not restore shortcuts")
}

// Hold a real load reply across target replacement. The profile inventory and
// shortcuts remain independent; its deliberately old connection state must be rejected.
model.resetShortcuts()
model.applyBackendPayload(["profiles": [[String: Any]]()])
let profileGate = URL(fileURLWithPath: temporaryHome).appendingPathComponent("hold-reference-profile")
let profileReady = URL(fileURLWithPath: temporaryHome).appendingPathComponent("reference-profile-ready")
do { try Data().write(to: profileGate) } catch { fail("could not hold reference profile reply") }
var staleConnectionApplied = false
let profileObservation = model.$connected.dropFirst().sink { if !$0 { staleConnectionApplied = true } }
model.loadProfile("fixture-preset")
guard waitUntil(2.0, { FileManager.default.fileExists(atPath: profileReady.path) }) else {
    fail("reference profile reply was not held")
}
fixtureTarget = TrainerTargetObservation(isRunning: true,
    launchGeneration: fixtureTarget.launchGeneration + 1,
    processIdentifier: (fixtureTarget.processIdentifier ?? 1000) + 1)
fixtureMonitor.refresh()
do { try FileManager.default.removeItem(at: profileGate) } catch { fail("could not release reference profile reply") }
guard waitUntil(2.0, { !model.busy && model.shortcutText(.toggleFeature) == "⌃⌥5"
    && model.profiles.map(\.name) == ["fixture-preset"] }) else {
    fail("target replacement discarded independent Profile metadata")
}
profileObservation.cancel()
if staleConnectionApplied || !model.connected || !model.enabled {
    fail("stale Profile connection state reached the current target")
}
model.deleteProfile("fixture-preset")
guard waitUntil(2.0, { !model.busy && model.profiles.isEmpty }) else {
    fail("reference fixture profile delete failed")
}

var exportedBundleData: Data? = nil
var exportedFilename: String? = nil
func rejectStaleDiagnosticsExport(_ stage: String) {
    let gate = URL(fileURLWithPath: temporaryHome).appendingPathComponent("hold-reference-diagnostics")
    let ready = URL(fileURLWithPath: temporaryHome).appendingPathComponent("reference-diagnostics-ready")
    try? FileManager.default.removeItem(at: ready)
    do { try Data().write(to: gate) } catch { fail("could not hold diagnostics reply") }
    context.feedback.clearNotice()
    var savedStaleReport = false
    model.exportDiagnostics { _, _, done in savedStaleReport = true; done(.saved) }
    guard waitUntil(2.0, { FileManager.default.fileExists(atPath: ready.path) }) else {
        fail("diagnostics export reply was not held (\(stage))")
    }
    fixtureTarget = TrainerTargetObservation(isRunning: true,
        launchGeneration: fixtureTarget.launchGeneration + 1,
        processIdentifier: (fixtureTarget.processIdentifier ?? 1000) + 1)
    fixtureMonitor.refresh()
    do { try FileManager.default.removeItem(at: gate) } catch { fail("could not release diagnostics reply") }
    guard waitUntil(2.0, { !model.busy
        && context.feedback.notice?.text.key == "host.error.diagnosticsExport" }) else {
        fail("rejected diagnostics export did not report failure (\(stage))")
    }
    if savedStaleReport { fail("rejected diagnostics export reused an earlier report (\(stage))") }
}
rejectStaleDiagnosticsExport("before any report")
model.runDiagnostics()
guard waitUntil(2.0, { !model.busy && model.diagnostics.map(\.id) == ["backend_session", "profile_store"] }) else {
    fail("reference fixture diagnostics refresh failed")
}
model.exportDiagnostics { data, filename, done in
    exportedBundleData = data
    exportedFilename = filename
    done(.saved)
}
guard waitUntil(2.0, { !model.busy && exportedBundleData != nil }),
      let exportedFilename,
      exportedFilename.hasSuffix("-Diagnostics.json"),
      let bundleData = exportedBundleData,
      let bundleJSON = try? JSONSerialization.jsonObject(with: bundleData) as? [String: Any],
      bundleJSON["gameID"] as? String == "reference_fixture",
      let bundleChecks = bundleJSON["checks"] as? [[String: Any]],
      bundleChecks.count == 2
else {
    fail("reference fixture diagnostics export failed")
}
rejectStaleDiagnosticsExport("after an accepted report")

model.setEnabled(false)
guard waitUntil(2.0, { !model.enabled && !model.busy }) else {
    fail("explicit fixture disable did not round-trip through session")
}

context.performConnectionAction()
guard waitUntil(2.0, { !model.connected && !model.busy }) else {
    fail("disconnect did not round-trip through session")
}

model.refreshFromHost()
guard waitUntil(2.0, { !model.connected && !model.enabled && !model.busy }) else {
    fail("status refresh did not preserve backend truth")
}

var canTerminate: Bool? = nil
context.beginTermination()
context.prepareForTermination { canTerminate = true }
guard waitUntil(2.0, { canTerminate == true && !session.isStarted }) else {
    fail("Context did not stop the session after the optional termination hook")
}

print("reference_fixture_session_integration_ok")
"""

assert not (ROOT / "Backend/games/reference_fixture").exists()
assert not (ROOT / "Sources/ReferenceFixture").exists()

with tempfile.TemporaryDirectory(prefix="mgt-reference-fixture-session-") as td:
    temp = Path(td)
    project = temp / "project"
    (project / "Backend/games").mkdir(parents=True)
    (project / "Sources").mkdir(parents=True)

    shutil.copytree(ROOT / "Backend/core", project / "Backend/core")
    shutil.copytree(FIXTURE / "backend", project / "Backend/games/reference_fixture")
    adapter_path = project / "Backend/games/reference_fixture/adapter.py"
    adapter_path.write_text(adapter_path.read_text() + r'''

# A test-only barrier holds the actual Profile payload across a Host target change.
_fixture_dispatch = ReferenceFixtureAdapter.dispatch
def _held_profile_dispatch(self, command, params, request_id=None):
    result = _fixture_dispatch(self, command, params, request_id)
    if command == 'load_profile':
        import pathlib, time
        gate = pathlib.Path.home() / 'hold-reference-profile'
        if gate.exists():
            gate.with_name('reference-profile-ready').write_text('ready')
            deadline = time.monotonic() + 3
            while gate.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            return {**result, 'connected': False, 'enabled': False}
    return result
ReferenceFixtureAdapter.dispatch = _held_profile_dispatch

_fixture_diagnostics_dispatch = ReferenceFixtureAdapter.dispatch
def _held_diagnostics_dispatch(self, command, params, request_id=None):
    result = _fixture_diagnostics_dispatch(self, command, params, request_id)
    if command == 'diagnostics':
        import pathlib, time
        gate = pathlib.Path.home() / 'hold-reference-diagnostics'
        if gate.exists():
            gate.with_name('reference-diagnostics-ready').write_text('ready')
            deadline = time.monotonic() + 3
            while gate.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
    return result
ReferenceFixtureAdapter.dispatch = _held_diagnostics_dispatch
''')
    variant_path = project / "Backend/games/reference_fixture/module.json"
    variant = json.loads(variant_path.read_text())
    variant["targetApplication"] = {"processName": "ReferenceTarget",
        "executablePathSuffix": "Expected/ReferenceTarget"}
    variant_path.write_text(json.dumps(variant))
    shutil.copytree(ROOT / "Sources/Core", project / "Sources/Core")
    shutil.copytree(FIXTURE / "frontend", project / "Sources/ReferenceFixture")
    for language in ("zh-CN", "en"):
        shutil.copytree(
            ROOT / f"Resources/Localization/{language}.lproj",
            project / f"{language}.lproj",
        )
    shutil.copytree(ROOT / "Tools", project / "Tools")
    shutil.copy2(ROOT / "Info.plist", project / "Info.plist")

    main_swift = project / "main.swift"
    main_swift.write_text(harness + main_actor_entrypoint(journey), encoding="utf-8")
    binary = project / "reference_fixture_session_test"

    compile_swift_test(
        games=("reference_fixture",),
        checkout=project,
        harness_sources=[ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", main_swift],
        output=binary,
        swiftc=SWIFTC,
        cwd=project,
    )

    home = temp / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    native_source = temp / "target.c"
    native_source.write_text("#include <unistd.h>\nint main(void) { for (;;) sleep(1); }\n")
    target = temp / "Expected/ReferenceTarget"
    unrelated = temp / "Unrelated/ReferenceTarget"
    for executable in (target, unrelated):
        executable.parent.mkdir()
        subprocess.run(["clang", str(native_source), "-o", str(executable)], check=True)
    with subprocess.Popen([str(target)]) as target_process, subprocess.Popen([str(unrelated)]) as unrelated_process:
        try:
            proc = launch_fixture(
                [str(binary), str(project / "Backend/core/server.py"), PYTHON, str(target_process.pid), "session"],
                cwd=project, env=env, text=True, capture_output=True,
                journey="native.reference_fixture_session_integration", budgets=JOURNEY_BUDGETS,
            )
            target_process.terminate()
            target_process.wait(timeout=5)
            launch_fixture([str(binary), str(project / "Backend/core/server.py"), PYTHON, "absent", "identity-only"],
                           cwd=project, env=env, check=True, journey="reference_fixture.suffix_identity", budgets=JOURNEY_BUDGETS)
        finally:
            for process in (target_process, unrelated_process):
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    assert "reference_fixture_session_integration_ok" in proc.stdout

    log_path = home / "Library/Application Support/MacGamingTrainer/reference_fixture/trainer.log"
    assert not log_path.exists(), (
        "generic Backend process must not own a persistent trainer.log; "
        "the Host module owns persistence and retention"
    )

assert not (ROOT / "Backend/games/reference_fixture").exists()
assert not (ROOT / "Sources/ReferenceFixture").exists()

print("reference_fixture_session_integration_test_ok")
