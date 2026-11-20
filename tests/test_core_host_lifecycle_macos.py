"""Exercise Core Host context lifecycle, target monitor, management groups, and shortcut settings on macOS."""

MGT_PLATFORM = "macos"

from fixture_budgets.core_runtime import JOURNEY_BUDGETS
from macos_fixture_policy import launch_fixture
from swift_test_compiler import compile_swift_test
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if sys.platform != "darwin":
    print("core_host_lifecycle_macos_only")
    raise SystemExit(0)

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
CLANG = shutil.which("clang")
PYTHON = shutil.which("python3")
assert SWIFTC and CLANG and PYTHON, "swiftc, clang and python3 are required"

TARGET_C = r'''
#include <unistd.h>
int main(void) {
    for (int i = 0; i < 30; ++i) {
        sleep(1);
    }
    return 0;
}
'''

WORKER_PY = r'''
import argparse, json, sys, time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--game", required=True)
args = parser.parse_args()
for raw in sys.stdin:
    request = json.loads(raw)
    if request["command"] == "wait":
        release = Path(request["params"]["release"])
        deadline = time.monotonic() + 5
        while not release.exists() and time.monotonic() < deadline:
            time.sleep(0.005)
    if request["command"] == "unknown-reply":
        print(json.dumps({"type": "result", "id": request["id"], "ok": False,
            "protocolVersion": 6, "moduleProtocolVersion": 1, "gameID": args.game,
            "error": {"code": "outcome_unknown", "presentation": "host.backend.error.outcomeUnknown"}}), flush=True)
        continue
    print(json.dumps({"type": "result", "id": request["id"], "ok": True,
        "protocolVersion": 6, "moduleProtocolVersion": 1, "gameID": args.game,
        "result": {}}), flush=True)
'''

HARNESS = r'''
import AppKit
import Combine
import Foundation
import SwiftUI

func fail(_ message: String, file: StaticString = #fileID, line: UInt = #line) -> Never {
    fputs("FAIL (\(file):\(line)): \(message)\n", stderr)
    exit(1)
}

func check(_ condition: @autoclosure () -> Bool, _ message: String, file: StaticString = #fileID, line: UInt = #line) {
    if !condition() { fail(message, file: file, line: line) }
}

func pump(_ seconds: TimeInterval = 0.05) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

func waitUntil(_ timeout: TimeInterval = 3.0, message: String, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition(), Date() < deadline {
        pump(0.01)
    }
    if !condition() { fail("Timed out waiting for: \(message)") }
}

func waitWindow(_ host: NSView, _ timeout: TimeInterval = 3.0, message: String, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
        host.layoutSubtreeIfNeeded()
        if condition() { return }
        pump(0.02)
    }
    host.layoutSubtreeIfNeeded()
    if !condition() { fail("Timed out waiting for UI: \(message)") }
}

func hasAXText(_ text: String, in root: Any) -> Bool {
    nativeAccessibilityControls(root).contains {
        ($0.role == "AXStaticText" && $0.text == text) || $0.label == text || $0.valueText == text
    }
}

final class FakeRunningApp: NSRunningApplication, @unchecked Sendable {
    private let _pid: pid_t
    private let _bundle: String?
    private let _url: URL?
    private let _name: String?

    init(pid: pid_t, bundle: String?, url: URL?, name: String?) {
        self._pid = pid
        self._bundle = bundle
        self._url = url
        self._name = name
        super.init()
    }

    override var processIdentifier: pid_t { _pid }
    override var bundleIdentifier: String? { _bundle }
    override var executableURL: URL? { _url }
    override var localizedName: String? { _name }
}

final class LifecycleStubModel: TrainerHostModel {
    var connected: Bool = false
    var statusTitle = TrainerTextToken(key: "host.disconnected")
    var connectionDetailText = TrainerTextToken(key: "lifecycleFixture.detail")
    var hostActionsEnabled: Bool = true
    var launchActionFromHost: (@MainActor () -> Void)? = nil

    var manualConnectCount = 0
    var connectAutomaticallyCalls: [Bool] = []
    var refreshCount = 0
    var didBecomeActiveCount = 0
    var targetLifetimeObservations: [TrainerTargetObservation] = []
    var restartBackendCount = 0
    var staleReplyCount = 0

    func notifyChanged() {
        objectWillChange.send()
    }

    func connectFromHost(reason: TrainerHostConnectReason) {
        switch reason {
        case .manual: manualConnectCount += 1
        case .automatic(let targetJustLaunched): connectAutomaticallyCalls.append(targetJustLaunched)
        }
    }
    func disconnectFromHost() {}
    func refreshFromHost() { refreshCount += 1 }
    func hostDidBecomeActive() { didBecomeActiveCount += 1 }
    func hostTargetLifetimeChanged(observation: TrainerTargetObservation) {
        targetLifetimeObservations.append(observation)
    }
    func backendPayloadTarget(_ payload: [String: Any]) -> TrainerBackendPayloadTarget { .lifetime }
    func applyStaleBackendPayload(_ payload: [String: Any]) { staleReplyCount += 1 }
    func backendWillRestart() { restartBackendCount += 1 }
    func prepareForTermination(completion: @escaping () -> Void) { completion() }
}

final class DefaultBehaviorStubModel: TrainerHostModel {
    var connected: Bool = false
    var statusTitle = TrainerTextToken(key: "host.disconnected")
    var connectionDetailText = TrainerTextToken(key: "")
    var hostActionsEnabled: Bool = true

    var refreshCount = 0
    var restartBackendCount = 0

    var automaticConnectCount = 0
    func connectFromHost(reason: TrainerHostConnectReason) {
        if case .automatic = reason { automaticConnectCount += 1 }
    }
    func disconnectFromHost() {}
    func refreshFromHost() { refreshCount += 1 }
    func backendWillRestart() { restartBackendCount += 1 }
    func prepareForTermination(completion: @escaping () -> Void) { completion() }
}

enum LifecycleModuleSpec {
    static let bundleID = "test.host.lifecycle.fixture"
    static let processName = "mgt_host_tgt"
    static let suffix = "HostFixture/mgt_host_tgt"
    static let fakeAppURL = URL(fileURLWithPath: "/synthetic/\(suffix)")
}

enum LifecycleStubModule: TrainerGameModule {
    static let descriptor = GameModuleDescriptor(
        id: "lifecycle_stub",
        displayName: "Lifecycle Stub",
        targetProcessName: LifecycleModuleSpec.processName,
        targetBundleIdentifier: LifecycleModuleSpec.bundleID,
        targetExecutablePathSuffix: LifecycleModuleSpec.suffix,
        expectedHostProtocolVersion: 6,
        expectedModuleProtocolVersion: 1,
        supportsSaveManagement: false
    )
    static let presentation = TrainerGamePresentation(headerTitle: "Lifecycle Stub")
    static func makeModel(services: TrainerModuleServices) -> LifecycleStubModel { LifecycleStubModel() }
    static func makeContent(model: LifecycleStubModel) -> some View {
        Text("Lifecycle Content")
            .accessibilityIdentifier("lifecycleFixture.content")
    }
    static func makeSidebarActions(model: LifecycleStubModel) -> some View {
        Button("Sidebar Extra") {}
            .accessibilityIdentifier("lifecycleFixture.sidebarAction")
    }
    static func makeHeaderActions(model: LifecycleStubModel) -> some View { EmptyView() }
    static func makeManagementCommands(model: LifecycleStubModel, localization: TrainerLocalizationStore) -> TrainerEmptyCommands {
        TrainerEmptyCommands()
    }
    static var presentationKeyPrefix: String { "lifecycleFixture." }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String {
        switch (key, language) {
        case ("lifecycleFixture.hello", .en): return "Hello Fixture"
        case ("lifecycleFixture.hello", .zhCN): return "你好夹具"
        case ("lifecycleFixture.detail", .en): return "Fixture Detail"
        case ("lifecycleFixture.detail", .zhCN): return "夹具详情"
        default: return key
        }
    }
}

enum DefaultBehaviorStubModule: TrainerGameModule {
    static let descriptor = LifecycleStubModule.descriptor
    static let presentation = LifecycleStubModule.presentation
    static func makeModel(services: TrainerModuleServices) -> DefaultBehaviorStubModel { DefaultBehaviorStubModel() }
    static func makeContent(model: DefaultBehaviorStubModel) -> some View { EmptyView() }
    static func makeSidebarActions(model: DefaultBehaviorStubModel) -> some View { EmptyView() }
    static func makeHeaderActions(model: DefaultBehaviorStubModel) -> some View { EmptyView() }
    static func makeManagementCommands(model: DefaultBehaviorStubModel, localization: TrainerLocalizationStore) -> TrainerEmptyCommands {
        TrainerEmptyCommands()
    }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String { key }
}

func spawnTargetProcess(at url: URL) throws -> Process {
    let process = Process()
    process.executableURL = url
    process.standardInput = FileHandle.nullDevice
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    try process.run()
    // Ensure proc_pidpath and pgrep see the running target before refreshing.
    pump(0.05)
    return process
}

func terminateTarget(_ process: Process?) {
    guard let process else { return }
    if process.isRunning {
        process.terminate()
    }
    process.waitUntilExit()
    pump(0.05)
}

func postWorkspace(_ name: Notification.Name, pid: pid_t) {
    let fake = FakeRunningApp(
        pid: pid,
        bundle: LifecycleModuleSpec.bundleID,
        url: LifecycleModuleSpec.fakeAppURL,
        name: LifecycleModuleSpec.processName
    )
    NSWorkspace.shared.notificationCenter.post(
        name: name,
        object: NSWorkspace.shared,
        userInfo: [NSWorkspace.applicationUserInfoKey: fake]
    )
    pump(0.05)
}

final class TestHostApplication: NSApplication {
    var fakeActive = false
    override var isActive: Bool { fakeActive }
}

@main
struct Runner {
    @MainActor
    static func main() throws {
        let targetURL = URL(fileURLWithPath: CommandLine.arguments[1])
        let pythonURL = URL(fileURLWithPath: CommandLine.arguments[2])
        let workerURL = URL(fileURLWithPath: CommandLine.arguments[3])

        let app = TestHostApplication.shared as! TestHostApplication
        app.setActivationPolicy(.accessory)
        enableNativeAccessibility()
        check(!NSApp.isActive, "Headless lifecycle fixture must start with NSApp.isActive == false")

        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        check(localization.localized("host.shortcutSettings") != "host.shortcutSettings",
              "Host.strings table did not load beside test executable")

        func makeContext<Module: TrainerGameModule>(_ module: Module.Type, model: Module.Model) -> TrainerGameContext<Module> {
            let session = TrainerBackendSession(client: BackendClient(process: BackendProcess(
                executableURL: pythonURL, argumentsPrefix: ["-u"], forceKillDelay: 0.05
            )))
            let log = TrainerLogSink(url: workerURL.deletingLastPathComponent().appendingPathComponent(UUID().uuidString))
            return TrainerGameContext<Module>(session: session, backendScriptURL: workerURL, logSink: log) { _ in model }
        }

        func stopWorker(_ session: TrainerBackendSession) {
            session.stop()
            waitUntil(message: "worker stops with a restartable configuration") {
                !session.isStarted && !session.currentStatus.busy && session.canRestart
            }
        }

        // 1. Atomic launch observation and explicit automatic connect.
        do {
            let model = LifecycleStubModel()

            let context = makeContext(LifecycleStubModule.self, model: model)
            defer { context.session.stop() }
            var observations: [TrainerTargetObservation] = []
            let sub = context.targetMonitor.$targetObservation.dropFirst().sink { observations.append($0) }

            postWorkspace(NSWorkspace.didLaunchApplicationNotification, pid: 41001)
            check(observations.count == 1, "expected 1 atomic launch observation, got \(observations)")
            check(observations[0] == TrainerTargetObservation(isRunning: true, launchGeneration: 1, processIdentifier: 41001),
                  "unexpected atomic observation: \(observations[0])")
            check(model.targetLifetimeObservations.last == observations[0],
                  "model did not receive target lifetime observation")
            check(model.connectAutomaticallyCalls == [true],
                  "background launch attach lost targetJustLaunched == true: \(model.connectAutomaticallyCalls)")
            withExtendedLifetime(sub) {}

            let defaultModel = DefaultBehaviorStubModel()
            check(defaultModel.launchActionFromHost == nil,
                  "TrainerHostModel default launchActionFromHost must be nil")
            let defaultContext = makeContext(DefaultBehaviorStubModule.self, model: defaultModel)
            defer { defaultContext.session.stop() }
            localization.language = .en
            let defaultWindow = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 320, height: 320),
                styleMask: [.titled], backing: .buffered, defer: false
            )
            defaultWindow.isReleasedWhenClosed = false
            let defaultHost = NSHostingView(
                rootView: TrainerHostSidebarCard(context: defaultContext, selected: true, onSelect: {})
                    .environmentObject(localization)
                    .trainerTheme(.standard)
            )
            defaultWindow.contentView = defaultHost
            defaultWindow.orderBack(nil)
            waitWindow(defaultHost, message: "default model without launchActionFromHost renders Connect Game") {
                namedNativeControl(defaultHost, role: "AXButton",
                                 name: localization.localized("host.connectGame"))?.enabled == true
                    && namedNativeControl(defaultHost, role: "AXButton",
                                          name: localization.localized("host.launchGame")) == nil
            }
            defaultWindow.contentView = nil
            defaultWindow.close()

            postWorkspace(NSWorkspace.didLaunchApplicationNotification, pid: 41009)
            check(defaultModel.automaticConnectCount == 1,
                  "automatic launch did not call the explicit connect action")
            NotificationCenter.default.post(name: NSApplication.didBecomeActiveNotification, object: NSApp)
            pump(0.05)
            check(defaultModel.refreshCount == 0 && defaultModel.automaticConnectCount == 1
                  && defaultModel.restartBackendCount == 0,
                  "TrainerHostModel default hostDidBecomeActive caused unexpected side effects")
            withExtendedLifetime(defaultContext) {}
        }

        // 2. Background gate & didActivateApplicationNotification separation + allowDiscoveryConnect: false.
        do {
            let model = LifecycleStubModel()
            let context = makeContext(LifecycleStubModule.self, model: model)
            defer { context.session.stop() }
            stopWorker(context.session)

            // Silent discovery via refresh() must keep allowDiscoveryConnect == false.
            let discovered = try spawnTargetProcess(at: targetURL)
            defer { terminateTarget(discovered) }
            context.targetMonitor.refresh()
            pump(0.05)
            check(context.targetMonitor.isRunning, "targetMonitor.refresh did not discover running target")
            check(model.restartBackendCount == 0,
                  "discovery refresh unexpectedly authorized automatic backend restart")
            terminateTarget(discovered)
            context.targetMonitor.refresh()
            pump(0.05)

            // Activation before launch must not authorize restart.
            postWorkspace(NSWorkspace.didActivateApplicationNotification, pid: 41002)
            check(model.restartBackendCount == 0, "activation before launch triggered backend restart")

            // Launch consumes backend restart while preserving backgroundConnectionAllowed.
            let activeTarget = try spawnTargetProcess(at: targetURL)
            defer { terminateTarget(activeTarget) }
            postWorkspace(NSWorkspace.didLaunchApplicationNotification, pid: activeTarget.processIdentifier)
            check(model.restartBackendCount == 1, "launch did not consume backend restart")
            waitUntil(message: "backend availability after launch permits a single connection") {
                model.connectAutomaticallyCalls == [true]
            }

            // Becoming active before target activation must not invent targetActivated().
            app.fakeActive = true
            defer { app.fakeActive = false }
            NotificationCenter.default.post(name: NSApplication.didBecomeActiveNotification, object: NSApp)
            pump(0.05)
            check(model.connectAutomaticallyCalls == [true],
                  "applicationBecameActive connected before didActivateApplicationNotification: \(model.connectAutomaticallyCalls)")

            // Activation sets targetActivated() without calling reconcileAutomaticConnection().
            let activationsBefore = context.targetMonitor.activationGeneration
            postWorkspace(NSWorkspace.didActivateApplicationNotification, pid: activeTarget.processIdentifier)
            check(context.targetMonitor.activationGeneration == activationsBefore &+ 1,
                  "didActivate did not increment activationGeneration")
            check(model.restartBackendCount == 1 && model.connectAutomaticallyCalls == [true],
                  "activationGeneration sink called reconcileAutomaticConnection() directly: \(model.connectAutomaticallyCalls)")
            NotificationCenter.default.post(name: NSApplication.didBecomeActiveNotification, object: NSApp)
            pump(0.05)
            check(model.connectAutomaticallyCalls == [true, false],
                  "activationGeneration sink did not call connectionPolicy.targetActivated(): \(model.connectAutomaticallyCalls)")
            app.fakeActive = false

            model.connected = true
            model.notifyChanged()
            pump(0.05)
            model.connected = false
            model.notifyChanged()
            pump(0.05)
            postWorkspace(NSWorkspace.didActivateApplicationNotification, pid: activeTarget.processIdentifier)
            model.notifyChanged()
            pump(0.05)
            check(model.connectAutomaticallyCalls == [true, false],
                  "background reconnect ran without NSApp.isActive or launch permission: \(model.connectAutomaticallyCalls)")
        }

        // 3. PID-only target replacement while connected & running.
        do {
            let p1 = try spawnTargetProcess(at: targetURL)
            var p2: Process? = nil
            defer { terminateTarget(p1); terminateTarget(p2) }
            let pid1 = p1.processIdentifier

            let model = LifecycleStubModel()

            model.connected = true
            let context = makeContext(LifecycleStubModule.self, model: model)
            defer { context.session.stop() }
            check(context.targetMonitor.isRunning && context.targetMonitor.targetObservation.processIdentifier == pid1,
                  "initial monitor did not find target PID \(pid1)")
            model.refreshCount = 0
            model.connectAutomaticallyCalls.removeAll()

            terminateTarget(p1)
            let proc2 = try spawnTargetProcess(at: targetURL)
            p2 = proc2
            let pid2 = proc2.processIdentifier
            check(pid2 != pid1, "replacement process reused same PID")

            context.targetMonitor.refresh()
            pump(0.05)
            check(context.targetMonitor.targetObservation.processIdentifier == pid2,
                  "monitor did not pick up replacement PID \(pid2)")
            check(model.targetLifetimeObservations.last?.processIdentifier == pid2,
                  "model did not receive replacement PID lifetime observation")
            check(model.refreshCount == 1,
                  "PID-only replacement did not invalidate stale connected state via refreshFromHost")

            model.connected = false
            model.notifyChanged()
            pump(0.05)
            check(model.connectAutomaticallyCalls.isEmpty,
                  "PID-only replacement granted background attach permission")

            // Reconnect to replacement proc2 and verify a subsequent exit still invalidates connected state
            // (proves targetStateChanged(running: false) ran BEFORE observeTarget(running: true)).
            model.connected = true
            model.notifyChanged()
            pump(0.05)
            terminateTarget(proc2)
            context.targetMonitor.refresh()
            waitUntil(message: "subsequent exit after PID-only replacement triggers second refreshFromHost") {
                model.refreshCount == 2
            }
        }

        // 4. Discovery invalidates in-flight state. Session-owned busy then
        // delays exit and replacement refresh.
        do {
            let model = LifecycleStubModel()
            let context = makeContext(LifecycleStubModule.self, model: model)
            defer { context.session.stop() }
            func holdRequest() -> URL {
                let release = workerURL.deletingLastPathComponent().appendingPathComponent(UUID().uuidString)
                context.session.send("wait", params: ["release": release.path], operation: "hold", announceSuccess: false)
                check(context.backendStatus.busy && !context.canTerminate, "shared request did not block quit")
                return release
            }
            let discoveryRequest = holdRequest()
            let pExit = try spawnTargetProcess(at: targetURL)
            defer { terminateTarget(pExit) }
            context.targetMonitor.refresh()
            check(context.targetMonitor.isRunning && context.targetMonitor.launchGeneration == 0,
                  "fixture did not discover its target without a launch notification")
            try Data().write(to: discoveryRequest)
            waitUntil(message: "pre-discovery request settles") { !context.backendStatus.busy }
            check(model.staleReplyCount == 1 && model.connectAutomaticallyCalls.isEmpty,
                  "target discovery adopted the previous absence or started an automatic connection")

            model.connected = true
            let firstRequest = holdRequest()
            terminateTarget(pExit)
            context.targetMonitor.refresh()
            check(model.refreshCount == 0, "exit refresh ran while the session was busy")
            try Data().write(to: firstRequest)
            waitUntil(message: "idle session refreshes exited target while backgrounded") {
                model.refreshCount == 1 && context.canTerminate
            }

            model.refreshCount = 0
            let secondRequest = holdRequest()
            postWorkspace(NSWorkspace.didLaunchApplicationNotification, pid: 41003)
            check(model.refreshCount == 0 && model.connectAutomaticallyCalls.isEmpty,
                  "launch acted before the previous request completed")
            try Data().write(to: secondRequest)
            waitUntil(message: "replacement refresh precedes its launch connect") { model.refreshCount == 1 }
            check(model.connectAutomaticallyCalls.isEmpty, "launch connected before exit refresh")
            model.connected = false
            model.notifyChanged()
            waitUntil(message: "launch connects after old attachment refresh") {
                model.connectAutomaticallyCalls == [true]
            }

            // A consumed launch opportunity cannot grant background restart.
            stopWorker(context.session)
            pump(0.05)
            check(model.restartBackendCount == 0,
                  "automatic backend restart ran without foreground or launch permission")
        }

        // 5. NSApplication.didBecomeActiveNotification (applicationBecameActive).
        do {
            // 5a: Silent exit triggers refreshFromHost + hostDidBecomeActive.
            let pSilent = try spawnTargetProcess(at: targetURL)
            defer { terminateTarget(pSilent) }
            let model = LifecycleStubModel()

            model.connected = true
            let context = makeContext(LifecycleStubModule.self, model: model)
            defer { context.session.stop() }
            terminateTarget(pSilent)
            model.refreshCount = 0
            model.didBecomeActiveCount = 0
            NotificationCenter.default.post(name: NSApplication.didBecomeActiveNotification, object: NSApp)
            pump(0.05)
            check(!context.targetMonitor.isRunning, "applicationBecameActive did not refresh targetMonitor")
            check(model.refreshCount == 1, "applicationBecameActive exit did not trigger refreshFromHost")
            check(model.didBecomeActiveCount == 1, "applicationBecameActive did not notify model.hostDidBecomeActive")
        }
        do {
            // 5b: Silent start seen on didBecomeActive uses allowDiscoveryConnect: false.
            let model = LifecycleStubModel()
            let context = makeContext(LifecycleStubModule.self, model: model)
            defer { context.session.stop() }
            stopWorker(context.session)
            let pLate = try spawnTargetProcess(at: targetURL)
            defer { terminateTarget(pLate) }
            NotificationCenter.default.post(name: NSApplication.didBecomeActiveNotification, object: NSApp)
            pump(0.05)
            check(context.targetMonitor.isRunning, "didBecomeActive did not detect silently started target")
            check(model.restartBackendCount == 0,
                  "didBecomeActive target discovery granted automatic attach/restart")
        }

        // 6. Rendered TrainerHostView + TrainerHostSidebarCard + connectionStatusCard (en & zh-CN).
        do {
            for language in [TrainerPresentationLanguage.en, .zhCN] {
                localization.language = language
                let model = LifecycleStubModel()

                let context = makeContext(LifecycleStubModule.self, model: model)
                defer { context.session.stop() }

                let lateTarget = try spawnTargetProcess(at: targetURL)
                defer { terminateTarget(lateTarget) }

                let hostViewWindow = NSWindow(
                    contentRect: NSRect(x: 0, y: 0, width: 700, height: 500),
                    styleMask: [.titled], backing: .buffered, defer: false
                )
                hostViewWindow.isReleasedWhenClosed = false
                let hostViewHosting = NSHostingView(
                    rootView: TrainerHostView(context: context)
                        .environmentObject(localization)
                        .trainerTheme(.standard)
                )
                hostViewWindow.contentView = hostViewHosting
                hostViewWindow.orderBack(nil)
                waitWindow(hostViewHosting, message: "TrainerHostView onAppear refreshes monitor & registers presentation") {
                    context.targetMonitor.isRunning &&
                    localization.string(TrainerTextToken(key: "lifecycleFixture.hello")) ==
                        LifecycleStubModule.presentationText(key: "lifecycleFixture.hello", arguments: [], language: language)
                }
                hostViewWindow.contentView = nil
                hostViewWindow.close()
                terminateTarget(lateTarget)
            }

            // Sidebar card + connectionStatusCard interactions.
            localization.language = .en
            let model = LifecycleStubModel()

            var launchCount = 0
            model.launchActionFromHost = { launchCount += 1 }
            let context = makeContext(LifecycleStubModule.self, model: model)
            defer { context.session.stop() }
            check(!context.targetMonitor.isRunning, "expected absent target at sidebar setup")

            let sidebarWindow = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 320, height: 420),
                styleMask: [.titled], backing: .buffered, defer: false
            )
            sidebarWindow.isReleasedWhenClosed = false
            let sidebarHosting = NSHostingView(
                rootView: TrainerHostSidebarCard(context: context, selected: true, onSelect: {})
                    .environmentObject(localization)
                    .trainerTheme(.standard)
            )
            sidebarWindow.contentView = sidebarHosting
            sidebarWindow.orderBack(nil)

            waitWindow(sidebarHosting, message: "sidebar card renders actions and Launch button") {
                nativeAccessibilityControls(sidebarHosting).contains {
                    $0.role == "AXButton" && $0.identifier == "lifecycleFixture.sidebarAction"
                } && namedNativeControl(sidebarHosting, role: "AXButton",
                                      name: localization.localized("host.launchGame"))?.enabled == true
            }
            check(!hasAXText(localization.localized("host.gameLibrary"), in: sidebarHosting),
                  "sidebar card must not inject host.gameLibrary heading")
            check(namedNativeControl(sidebarHosting, role: "AXButton",
                                     name: localization.localized("host.launchGame"))!.press(),
                  "Launch button refused AX press")
            waitUntil(message: "Launch with absent target invokes launchAction") {
                launchCount == 1
            }
            check(model.manualConnectCount == 0,
                  "Launch with absent target unexpectedly connected")

            // Spawn target silently while UI still shows Launch -> pressing primary refreshes first and connects.
            let silent1 = try spawnTargetProcess(at: targetURL)
            defer { terminateTarget(silent1) }
            check(namedNativeControl(sidebarHosting, role: "AXButton",
                                     name: localization.localized("host.launchGame"))!.press(),
                  "stale Launch button refused AX press")
            waitUntil(message: "launchAction refreshes targetMonitor before choosing connect vs launch") {
                model.manualConnectCount == 1 && context.targetMonitor.isRunning
            }
            check(launchCount == 1, "launchAction invoked launch instead of connect for running target")

            // Refresh button refreshes both targetMonitor and model.
            terminateTarget(silent1)
            context.targetMonitor.refresh()
            pump(0.05)
            let silent2 = try spawnTargetProcess(at: targetURL)
            defer { terminateTarget(silent2) }
            check(!context.targetMonitor.isRunning, "monitor unexpectedly saw silent2 before Refresh press")
            model.refreshCount = 0
            waitWindow(sidebarHosting, message: "enabled Refresh button") {
                namedNativeControl(sidebarHosting, role: "AXButton",
                                 name: localization.localized("host.refreshStatus"))?.enabled == true
            }
            check(namedNativeControl(sidebarHosting, role: "AXButton",
                                     name: localization.localized("host.refreshStatus"))!.press(),
                  "Refresh button refused AX press")
            waitUntil(message: "connectionStatusCard Refresh refreshes targetMonitor and model") {
                context.targetMonitor.isRunning && model.refreshCount == 1
            }

            // Without launchActionFromHost, absent target offers Connect Game.
            terminateTarget(silent2)
            context.targetMonitor.refresh()
            pump(0.05)
            model.launchActionFromHost = nil
            model.notifyChanged()
            waitWindow(sidebarHosting, message: "Connect Game shown when onLaunch == nil") {
                namedNativeControl(sidebarHosting, role: "AXButton",
                                 name: localization.localized("host.connectGame"))?.enabled == true
            }
            let previousConnectCount = model.manualConnectCount
            check(namedNativeControl(sidebarHosting, role: "AXButton",
                                     name: localization.localized("host.connectGame"))!.press(),
                  "Connect Game refused AX press")
            waitUntil(message: "Connect Game invokes explicit connect") {
                model.manualConnectCount == previousConnectCount + 1
            }
            sidebarWindow.contentView = nil
            sidebarWindow.close()
        }

        // 7. TrainerManagementAction.Common, TrainerManagementCatalog & rendered TrainerManagementGroups (en & zh-CN).
        do {
            let expectedKeys: [(TrainerManagementAction.Common, String)] = [
                (.refreshStatus, "host.refreshStatus"),
                (.disableAll, "host.disableAll"),
                (.shortcuts, "host.shortcutSettings"),
                (.log, "host.viewLog"),
                (.logHistory, "host.viewLogHistory"),
                (.clearLogs, "host.clearCompletedLogs"),
                (.saveManagement, "host.saveManagement"),
            ]
            for language in [TrainerPresentationLanguage.en, .zhCN] {
                localization.language = language
                var fired: [String] = []
                var disabledEnabled = false
                func makeCommon(_ kind: TrainerManagementAction.Common, enabled: @escaping () -> Bool = { true }) -> TrainerManagementAction {
                    TrainerManagementAction(kind, localization: localization, enabled: enabled) {
                        fired.append(kind.rawValue)
                    }
                }
                func makeCustom(_ id: String) -> TrainerManagementAction {
                    TrainerManagementAction(id: id, title: id, icon: "gearshape") { fired.append(id) }
                }
                for (kind, key) in expectedKeys {
                    let action = makeCommon(kind)
                    check(kind.titleKey == key && action.title == localization.localized(key),
                          "Common action \(kind) title mismatch in \(language): \(action.title) != \(localization.localized(key))")
                    check(action.icon == kind.icon,
                          "Common action \(kind) icon mismatch: \(action.icon) != \(kind.icon)")
                }
                check(TrainerManagementAction.Common.disableAll.titleKey == "host.disableAll"
                      && TrainerManagementAction.Common.disableAll.icon == TrainerSemanticIcon.Tool.disableAll,
                      "Common.disableAll lost shared host key or icon")

                let withoutOptionals = TrainerManagementCatalog(
                    titles: .init(daily: "Daily", settings: "Settings", maintenance: "Maintenance"),
                    refresh: makeCommon(.refreshStatus),
                    disableAll: makeCommon(.disableAll),
                    profiles: makeCustom("profiles"),
                    shortcuts: makeCommon(.shortcuts),
                    log: makeCommon(.log),
                    diagnostics: makeCustom("diagnostics"),
                    logHistory: makeCommon(.logHistory),
                    clearLogs: makeCommon(.clearLogs)
                )
                check(withoutOptionals.groups[0].actions.map(\.id) == ["refreshStatus", "disableAll"],
                      "daily group without optional save actions drifted: \(withoutOptionals.groups[0].actions.map(\.id))")

                let saveEditorAction = makeCustom("saveEditor")
                let saveMgmtAction = makeCommon(.saveManagement, enabled: { disabledEnabled })
                let catalog = TrainerManagementCatalog(
                    titles: .init(daily: "Daily", settings: "Settings", maintenance: "Maintenance"),
                    refresh: makeCommon(.refreshStatus),
                    disableAll: makeCommon(.disableAll),
                    profiles: makeCustom("profiles"),
                    shortcuts: makeCommon(.shortcuts),
                    log: makeCommon(.log),
                    diagnostics: makeCustom("diagnostics"),
                    logHistory: makeCommon(.logHistory),
                    clearLogs: makeCommon(.clearLogs),
                    saveEditor: saveEditorAction,
                    saveManagement: saveMgmtAction
                )
                check(catalog.groups[0].actions.map(\.id) == ["refreshStatus", "saveEditor", "saveManagement", "disableAll"],
                      "daily group with saveEditor/saveManagement drifted: \(catalog.groups[0].actions.map(\.id))")

                // Disabled action guard inside perform().
                saveMgmtAction.perform()
                check(fired.isEmpty, "disabled TrainerManagementAction executed handler")
                disabledEnabled = true

                let mgmtWindow = NSWindow(
                    contentRect: NSRect(x: 0, y: 0, width: 640, height: 420),
                    styleMask: [.titled], backing: .buffered, defer: false
                )
                mgmtWindow.isReleasedWhenClosed = false
                let mgmtHost = NSHostingView(
                    rootView: TrainerManagementGroups(groups: catalog.groups)
                        .trainerTheme(.standard)
                )
                mgmtWindow.contentView = mgmtHost
                mgmtWindow.orderBack(nil)

                let allActions = catalog.groups.flatMap(\.actions)
                waitWindow(mgmtHost, message: "management group buttons rendered") {
                    allActions.allSatisfy { action in
                        nativeAccessibilityControls(mgmtHost).contains {
                            $0.role == "AXButton" && $0.identifier == "trainer.management.\(action.id)"
                        }
                    }
                }
                for action in allActions {
                    let ctrl = nativeAccessibilityControls(mgmtHost).first {
                        $0.role == "AXButton" && $0.identifier == "trainer.management.\(action.id)"
                    }!
                    check(ctrl.label == action.title && ctrl.enabled == action.isEnabled,
                          "rendered management action \(action.id) label/enabled mismatch: label=\(String(describing: ctrl.label)) expected=\(action.title)")
                }
                let mgmtSaveBtn = nativeAccessibilityControls(mgmtHost).first {
                    $0.role == "AXButton" && $0.identifier == "trainer.management.saveManagement"
                }!
                check(mgmtSaveBtn.press(), "saveManagement button refused AX press")
                waitUntil(message: "pressing saveManagement fires handler") {
                    fired == ["saveManagement"]
                }
                mgmtWindow.contentView = nil
                mgmtWindow.close()
            }
        }

        // 8. Rendered TrainerShortcutSettingsView localization & capture (en & zh-CN).
        do {
            for language in [TrainerPresentationLanguage.en, .zhCN] {
                localization.language = language
                var presented = true
                let isPresented = Binding(get: { presented }, set: { presented = $0 })
                let firstTitle = language == .en ? "Toggle God Mode" : "开启无敌"
                let secondTitle = language == .en ? "Disable All Effects" : "关闭全部效果"
                let entries = [
                    TrainerShortcutSettingsEntry(id: "first", title: firstTitle, icon: "shield", chordText: "⌃⌥1", isEditable: true),
                    TrainerShortcutSettingsEntry(id: "second", title: secondTitle, icon: "xmark", chordText: "⌃⌥⌫", isEditable: false),
                ]
                var assignedCalls: [(String, String)] = []
                var resetCalls = 0
                let failure: TrainerHotkeyRegistrationFailure = .registrationConflicts([
                    TrainerHotkeyRegistrationConflict(actionID: "first", chordText: "⌃⌥1", status: -9878)
                ])
                let view = TrainerShortcutSettingsView(
                    isPresented: isPresented,
                    entries: entries,
                    registrationFailure: failure,
                    resetTitle: localization.localized("host.hotkeys.resetDefaults"),
                    onReset: { resetCalls += 1 },
                    onAssign: { actionID, chord in
                        assignedCalls.append((actionID, chord.displayText))
                        return .conflict(actionID: "second")
                    }
                )
                .environmentObject(localization)
                .trainerTheme(.standard)

                let shortcutWindow = NSWindow(
                    contentRect: NSRect(x: 0, y: 0, width: 620, height: 520),
                    styleMask: [.titled], backing: .buffered, defer: false
                )
                shortcutWindow.isReleasedWhenClosed = false
                let shortcutHost = NSHostingView(rootView: view)
                shortcutWindow.contentView = shortcutHost
                shortcutWindow.orderBack(nil)

                let expectedTitle = localization.localized("host.shortcutSettings")
                let expectedHelp = localization.localized("host.hotkeys.help")
                let expectedDone = localization.localized("host.done")
                let expectedReset = localization.localized("host.hotkeys.resetDefaults")
                let expectedRegFailed = localization.localized(
                    "host.hotkeys.registrationFailed",
                    arguments: ["⌃⌥1 \(firstTitle) (-9878)"]
                )

                waitWindow(shortcutHost, message: "shortcut settings chrome & registration conflict in \(language)") {
                    hasAXText(expectedTitle, in: shortcutHost)
                        && hasAXText(expectedHelp, in: shortcutHost)
                        && hasAXText(expectedRegFailed, in: shortcutHost)
                        && namedNativeControl(shortcutHost, role: "AXButton", name: expectedReset)?.enabled == true
                        && namedNativeControl(shortcutHost, role: "AXButton", name: expectedDone)?.enabled == true
                        && nativeAccessibilityControls(shortcutHost).contains {
                            $0.role == "AXButton" && $0.identifier == "trainer.shortcut.capture.first"
                        }
                }
                check(namedNativeControl(shortcutHost, role: "AXButton", name: expectedReset)!.press(),
                      "resetDefaults button refused AX press")
                waitUntil(message: "resetDefaults invokes onReset in \(language)") {
                    resetCalls == 1
                }

                // Enter capture mode and verify pressNew label + Done disabled.
                let captureBtn = nativeAccessibilityControls(shortcutHost).first {
                    $0.role == "AXButton" && $0.identifier == "trainer.shortcut.capture.first"
                }!
                check(captureBtn.press(), "editable shortcut capture button refused AX press")
                let expectedPressNew = localization.localized("host.hotkeys.pressNew")
                waitWindow(shortcutHost, message: "pressNew capture label & Done disabled in \(language)") {
                    hasAXText(expectedPressNew, in: shortcutHost)
                        && namedNativeControl(shortcutHost, role: "AXButton", name: expectedDone)?.enabled == false
                }

                // Send unrecognized key -> shows host.hotkeys.unrecognized.
                let badKey = NSEvent.keyEvent(
                    with: .keyDown, location: .zero, modifierFlags: [],
                    timestamp: 0, windowNumber: 0, context: nil,
                    characters: "", charactersIgnoringModifiers: "",
                    isARepeat: false, keyCode: 200
                )!
                app.sendEvent(badKey)
                let expectedUnrecognized = localization.localized("host.hotkeys.unrecognized")
                waitWindow(shortcutHost, message: "unrecognized key issue in \(language)") {
                    hasAXText(expectedUnrecognized, in: shortcutHost)
                }

                // Send valid chord -> onAssign returns .conflict(actionID: "second") -> shows host.hotkeys.conflict.
                let chordKey = NSEvent.keyEvent(
                    with: .keyDown, location: .zero, modifierFlags: [.control, .option],
                    timestamp: 0, windowNumber: 0, context: nil,
                    characters: "1", charactersIgnoringModifiers: "1",
                    isARepeat: false, keyCode: 18
                )!
                app.sendEvent(chordKey)
                let expectedConflict = localization.localized(
                    "host.hotkeys.conflict", arguments: ["⌃⌥1", secondTitle]
                )
                waitWindow(shortcutHost, message: "capture conflict issue in \(language)") {
                    hasAXText(expectedConflict, in: shortcutHost)
                }
                check(assignedCalls.count == 1 && assignedCalls[0].0 == "first" && assignedCalls[0].1 == "⌃⌥1",
                      "shortcut assign callback received wrong values: \(assignedCalls)")

                shortcutWindow.contentView = nil
                shortcutWindow.close()
                pump(0.05)

                // Verify listenerInitialization failure renders localized message.
                let listenerWindow = NSWindow(
                    contentRect: NSRect(x: 0, y: 0, width: 620, height: 420),
                    styleMask: [.titled], backing: .buffered, defer: false
                )
                listenerWindow.isReleasedWhenClosed = false
                let listenerHost = NSHostingView(
                    rootView: TrainerShortcutSettingsView(
                        isPresented: .constant(true),
                        entries: entries,
                        registrationFailure: .listenerInitialization(status: -50),
                        onAssign: { _, _ in .applied }
                    )
                    .environmentObject(localization)
                    .trainerTheme(.standard)
                )
                listenerWindow.contentView = listenerHost
                listenerWindow.orderBack(nil)
                let expectedListenerFailed = localization.localized(
                    "host.hotkeys.listenerFailed", arguments: ["-50"]
                )
                waitWindow(listenerHost, message: "listenerInitialization failure in \(language)") {
                    hasAXText(expectedListenerFailed, in: listenerHost)
                }
                listenerWindow.contentView = nil
                listenerWindow.close()
                pump(0.05)

                // Verify ScrollView + maxHeight: 560 caps tall entry lists.
                if language == .en {
                    func findScrollViews(in view: NSView) -> [NSScrollView] {
                        (view as? NSScrollView).map { [$0] } ?? view.subviews.flatMap(findScrollViews)
                    }
                    let manyEntries = (0..<30).map { index in
                        TrainerShortcutSettingsEntry(
                            id: "entry.\(index)", title: "Action \(index)", icon: "star",
                            chordText: "⌃⌥\(index)", isEditable: true
                        )
                    }
                    let tallWindow = NSWindow(
                        contentRect: NSRect(x: 0, y: 0, width: 620, height: 800),
                        styleMask: [.titled], backing: .buffered, defer: false
                    )
                    tallWindow.isReleasedWhenClosed = false
                    let tallHost = NSHostingView(
                        rootView: TrainerShortcutSettingsView(
                            isPresented: .constant(true),
                            entries: manyEntries,
                            onAssign: { _, _ in .applied }
                        )
                        .environmentObject(localization)
                        .trainerTheme(.standard)
                    )
                    tallWindow.contentView = tallHost
                    tallWindow.orderBack(nil)
                    waitWindow(tallHost, message: "shortcut settings ScrollView caps tall list") {
                        guard let scroll = findScrollViews(in: tallHost).first else { return false }
                        let docHeight = scroll.documentView?.frame.height ?? 0
                        return scroll.frame.height > 100 && docHeight > scroll.frame.height
                    }
                    let scroll = findScrollViews(in: tallHost).first!
                    check(scroll.frame.height <= 562,
                          "shortcut settings ScrollView exceeded maxHeight 560: \(scroll.frame.height)")
                    tallWindow.contentView = nil
                    tallWindow.close()
                    pump(0.05)
                }
            }
        }

        // 9. Context trust-gate wiring: discovery and exit invalidate observation
        // without releasing an unknown outcome; only definitive launch or
        // replacement PID releases the trust gate.
        do {
            let model = LifecycleStubModel()
            let context = makeContext(LifecycleStubModule.self, model: model)
            defer { context.session.stop() }
            check(!context.targetMonitor.isRunning, "trust-gate check requires absent target initially")

            func sendOutcomeUnknown() {
                var done: Bool?
                context.session.send("unknown-reply", operation: "unknown", announceSuccess: false, completion: { done = $0 })
                waitUntil(message: "unknown-reply settles") { done != nil }
                check(done == false && context.backendStatus.requiresTargetRestart && context.backendStatus.errorCode == "outcome_unknown",
                      "unknown-reply did not lock Context trust gate: \(context.backendStatus)")
            }

            func sendRuntimeRequest(_ command: String) -> (completed: Bool, failure: BackendFailure?) {
                var done: Bool?
                var capturedFailure: BackendFailure?
                context.session.send(command, operation: command, announceSuccess: false,
                                     failed: { capturedFailure = $0 }, completion: { done = $0 })
                waitUntil(message: "\(command) request settles") { done != nil }
                return (done!, capturedFailure)
            }

            sendOutcomeUnknown()
            let beforeDiscovery = sendRuntimeRequest("blocked-before-discovery")
            check(!beforeDiscovery.completed && beforeDiscovery.failure?.presentation == "host.backend.error.targetRestartRequired",
                  "runtime request was not blocked before discovery")

            // Mere discovery (running=false -> true, launchGeneration=0, no prior PID) must not release the gate.
            let discovered = try spawnTargetProcess(at: targetURL)
            defer { terminateTarget(discovered) }
            context.targetMonitor.refresh()
            pump(0.05)
            check(context.targetMonitor.isRunning && context.targetMonitor.launchGeneration == 0,
                  "fixture did not discover target without launch")
            check(context.backendStatus.requiresTargetRestart && context.backendStatus.errorCode == "outcome_unknown",
                  "target discovery through Context released unknown-outcome trust gate: \(context.backendStatus)")
            let afterDiscovery = sendRuntimeRequest("blocked-after-discovery")
            check(!afterDiscovery.completed && afterDiscovery.failure?.presentation == "host.backend.error.targetRestartRequired",
                  "runtime request bypassed trust gate after target discovery")

            // Target exit (running=true -> false, processIdentifier=nil) must not release the gate.
            terminateTarget(discovered)
            context.targetMonitor.refresh()
            pump(0.05)
            check(!context.targetMonitor.isRunning && context.backendStatus.requiresTargetRestart,
                  "target exit through Context released unknown-outcome trust gate")

            // Replacement PID discovered (lastKnownTargetProcessIdentifier != newPID) releases the gate.
            let replacement = try spawnTargetProcess(at: targetURL)
            defer { terminateTarget(replacement) }
            context.targetMonitor.refresh()
            pump(0.05)
            check(!context.backendStatus.requiresTargetRestart && context.backendStatus.errorCode == nil,
                  "replacement PID through Context did not release trust gate: \(context.backendStatus)")
            let afterReplacement = sendRuntimeRequest("allowed-after-replacement")
            check(afterReplacement.completed && afterReplacement.failure == nil,
                  "runtime request failed after replacement PID released trust gate")

            // Definitive launch notification with an unchanged PID (launched=true, replacement=false) also releases the gate.
            sendOutcomeUnknown()
            postWorkspace(NSWorkspace.didLaunchApplicationNotification, pid: replacement.processIdentifier)
            check(!context.backendStatus.requiresTargetRestart && context.backendStatus.errorCode == nil,
                  "definitive launch through Context did not release trust gate: \(context.backendStatus)")
            let afterLaunch = sendRuntimeRequest("allowed-after-launch")
            check(afterLaunch.completed && afterLaunch.failure == nil,
                  "runtime request failed after definitive launch released trust gate")
        }

        print("core_host_lifecycle_macos_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-core-host-lifecycle-") as td:
    temp = Path(td)
    for language in ("zh-CN", "en"):
        (temp / f"{language}.lproj").mkdir()
        shutil.copy2(
            ROOT / f"Resources/Localization/{language}.lproj/Host.strings",
            temp / f"{language}.lproj/Host.strings",
        )

    target_c = temp / "target.c"
    target_c.write_text(TARGET_C, encoding="utf-8")
    target_bin = temp / "HostFixture" / "mgt_host_tgt"
    target_bin.parent.mkdir(parents=True)
    subprocess.run([CLANG, str(target_c), "-o", str(target_bin)], check=True)

    worker_py = temp / "worker.py"
    worker_py.write_text(WORKER_PY, encoding="utf-8")

    harness_swift = temp / "CoreHostLifecycleHarness.swift"
    harness_swift.write_text(HARNESS, encoding="utf-8")
    executable = temp / "core-host-lifecycle"
    compile_swift_test(
        harness_sources=[
            ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
            ROOT / "tests/fixtures/swift/NativeAccessibility.swift",
            harness_swift,
        ],
        output=executable,
        swiftc=SWIFTC,
        cwd=ROOT,
    )

    result = launch_fixture(
        [str(executable), str(target_bin), PYTHON, str(worker_py)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        journey="native.core_host_lifecycle",
        budgets=JOURNEY_BUDGETS,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    assert "core_host_lifecycle_macos_ok" in result.stdout, result.stdout
    print(result.stdout.strip())
