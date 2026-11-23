"""Compile and exercise Host-owned TrainerFeedbackCenter and TrainerDiagnosticsService."""

MGT_PLATFORM = "macos"
MGT_INPUTS = (
    "Resources/Localization/",
    "Sources/Core/Host/",
    "Sources/Core/Runtime/",
    "Sources/Core/UI/",
)

from pathlib import Path
import shutil
import subprocess
import tempfile
from swift_test_compiler import compile_swift_test

ROOT = Path(__file__).resolve().parents[1]
SWIFT = shutil.which("swiftc")
assert SWIFT, "swiftc is required for the macOS Host feedback/diagnostics behavior test"

harness = r"""import AppKit
import Combine
import Foundation
import SwiftUI

@MainActor
final class StubModuleModel: TrainerHostModel, ObservableObject {
    var connected = false
    var statusTitle: TrainerTextToken { TrainerTextToken(key: "stub.status") }
    var connectionDetailText: TrainerTextToken { TrainerTextToken(key: "stub.detail") }
    var hostActionsEnabled: Bool { true }
    @Published var hostIssues: [TrainerCurrentIssue] = []
    var hostCurrentIssues: [TrainerCurrentIssue] { hostIssues }

    let services: TrainerModuleServices

    init(services: TrainerModuleServices) {
        self.services = services
    }

    func connectFromHost(reason: TrainerHostConnectReason) {}
    func disconnectFromHost() {}
    func refreshFromHost() {}
    func backendPayloadTarget(_ payload: [String: Any]) -> TrainerBackendPayloadTarget { .independent }
}

struct StubModule: TrainerGameModule {
    static let descriptor = GameModuleDescriptor(
        id: "stub",
        displayName: "Stub Game",
        targetProcessName: "StubProcess",
        targetBundleIdentifier: "com.example.stub",
        expectedHostProtocolVersion: 6,
        expectedModuleProtocolVersion: 1,
        supportsSaveManagement: false
    )
    static let presentation = TrainerGamePresentation(sidebarIconSystemName: "star")
    static let presentationKeyPrefix = "stub."
    @MainActor static func makeModel(services: TrainerModuleServices) -> StubModuleModel { StubModuleModel(services: services) }
    @MainActor static func makeContent(model: StubModuleModel) -> some View { EmptyView() }
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String {
        key
    }
}

@MainActor
@main
struct HostFeedbackDiagnosticsTest {
    static func main() throws {
        let tempRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("mgt-host-feedback-diag-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempRoot) }

        let gameLogDir = tempRoot.appendingPathComponent("stub-logs")
        let logSink = TrainerLogSink(gameID: "stub", homeDirectory: tempRoot)
        let missingScript = tempRoot.appendingPathComponent("missing-backend.py")
        let session = TrainerBackendSession()
        let context = TrainerGameContext<StubModule>(
            session: session,
            backendScriptURL: missingScript,
            logSink: logSink
        )
        defer { session.stop(suppressTerminationError: true) }

        // 1. Observable backend status on TrainerModuleServices without manual observeStatus bridges.
        let services: TrainerModuleServices = context.services
        precondition(services.backendStatus.isStartFailure, "missing script startup failure must already be reflected on services")
        precondition(
            context.feedback.notice?.text.key == "host.backend.error.startFailed"
                && context.feedback.notice?.tone == .warning,
            "TrainerFeedbackCenter must present backend startup failures automatically"
        )
        precondition(
            context.feedback.currentIssues.contains { $0.id == "backend" && $0.text.key == "host.backend.error.startFailed" },
            "TrainerFeedbackCenter must expose backend error in currentIssues"
        )

        let isolatedSession = TrainerBackendSession()
        let isolatedServices = TrainerModuleServices(
            descriptor: StubModule.descriptor,
            session: isolatedSession,
            logSink: logSink,
            targetObservation: TrainerTargetObservation(isRunning: false, launchGeneration: 0, processIdentifier: nil)
        )
        var publishedStatuses: [TrainerBackendStatus] = []
        let statusSub = isolatedServices.$backendStatus.sink { publishedStatuses.append($0) }
        precondition(!isolatedServices.backendStatus.isStartFailure, "fresh session status must not be start failure")
        do {
            try isolatedSession.start(
                descriptor: StubModule.descriptor,
                backendScriptURL: missingScript,
                applyPayload: { _ in },
                resetGameState: {},
                log: { _ in },
                backendLog: nil
            )
        } catch {
            // Expected startup error.
        }
        precondition(isolatedServices.backendStatus.isStartFailure, "services must expose startup failure cleanly")
        precondition(publishedStatuses.contains(where: \.isStartFailure), "observable backendStatus must publish updates")
        precondition(
            isolatedServices.feedback.notice?.text.key == "host.backend.error.startFailed",
            "standalone TrainerModuleServices must wire feedback center notifications"
        )

        // 2. Notice dismiss / stale-ID rejection / module issue merging & details flow.
        let startNoticeID = context.feedback.notice!.id
        context.feedback.dismiss(UUID())
        precondition(context.feedback.notice?.id == startNoticeID, "mismatched dismiss UUID must not clear notice")
        context.feedback.dismiss(startNoticeID)
        precondition(context.feedback.notice == nil, "matching dismiss UUID must clear notice")

        context.feedback.showDetails(for: UUID())
        precondition(!context.feedback.detailsPresented, "stale notice ID must not open details")

        context.model.hostIssues = [
            TrainerCurrentIssue(id: "runtime.sample", text: TrainerTextToken(key: "stub.runtimeError")),
        ]
        context.feedback.present(TrainerTextToken(key: "stub.oneShot"), tone: .warning)
        let activeID = context.feedback.notice!.id
        context.feedback.showDetails(for: activeID)
        precondition(
            context.feedback.detailsPresented && context.feedback.detailsNoticeID == activeID,
            "active notice must open feedback details when issues exist"
        )
        let issueIDs = Set(context.feedback.currentIssues.map(\.id))
        precondition(issueIDs == Set(["runtime.sample", "backend"]), "expected merged module + backend issues, got \(issueIDs)")
        context.feedback.closeDetails()
        precondition(!context.feedback.detailsPresented && context.feedback.detailsNoticeID == nil)

        // Resolving observed module issues without backend status change still notifies and retires details.
        let cleanSession = TrainerBackendSession()
        defer { cleanSession.stop(suppressTerminationError: true) }
        let cleanServices = TrainerModuleServices(
            descriptor: StubModule.descriptor,
            session: cleanSession,
            logSink: logSink,
            targetObservation: TrainerTargetObservation(isRunning: false, launchGeneration: 0, processIdentifier: nil)
        )
        let cleanModel = StubModuleModel(services: cleanServices)
        var cleanUpdates = 0
        let cleanSub = cleanServices.feedback.objectWillChange.sink { _ in cleanUpdates += 1 }
        cleanServices.feedback.setIssueProvider(observing: cleanModel) { [weak cleanModel] in
            cleanModel?.hostCurrentIssues ?? []
        }
        cleanModel.hostIssues = [
            TrainerCurrentIssue(id: "runtime.clean", text: TrainerTextToken(key: "stub.runtimeError")),
        ]
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        cleanServices.feedback.showDetails()
        precondition(cleanServices.feedback.detailsPresented, "clean module issue should open details")
        let beforeClearUpdates = cleanUpdates
        cleanModel.hostIssues = []
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))
        precondition(
            !cleanServices.feedback.detailsPresented && cleanUpdates > beforeClearUpdates,
            "resolving observed module issues must notify feedback center and retire details"
        )
        withExtendedLifetime(cleanSub) {}

        // 3. Host-rendered feedback overlay renders directly via TrainerHostView without Module.makeFeedback.
        _ = AnyTrainerGameContext(context)
        _ = gameLogDir

        // 4. TrainerDiagnosticsService owns log clear + single Swift JSON export scoped to LogSink.
        logSink.append("host line for export", source: "HOST")
        logSink.targetLifetimeChanged(running: true, identity: .init(
            processName: "StubProcess",
            bundleIdentifier: "com.example.stub",
            processIdentifier: 4242
        ))
        logSink.append("session runtime line", source: "RUNTIME")
        logSink.flush()

        let report: [String: Any] = [
            "checks": [
                ["name": "stub.diagnostics.check", "nameArguments": ["arg1"], "ok": true, "detail": "ok"],
            ],
            "state": ["connected": false],
        ]
        var exportedData: Data?
        var exportedFilename: String?
        let diagnostics = context.diagnostics
        diagnostics.exportReport(report, defaultFilename: "Stub-Diagnostics.json") { data, filename, done in
            exportedData = data
            exportedFilename = filename
            done(.saved)
        }
        precondition(exportedFilename == "Stub-Diagnostics.json", "unexpected export filename")
        let exportedJSON = try JSONSerialization.jsonObject(with: exportedData!) as! [String: Any]
        let logs = exportedJSON["logs"] as! [String: String]
        precondition(logs["host.log"]?.isEmpty == false && logs["runtime.log"]?.contains("session runtime line") == true,
                     "Host export must bundle active TrainerLogSink session streams")
        let exportedChecks = exportedJSON["checks"] as! [[String: Any]]
        precondition((exportedChecks.first?["name"] as? String) == "stub.diagnostics.check")
        precondition(context.feedback.notice?.text.key == "host.backend.notice.completed" && context.feedback.notice?.tone == .success,
                     "Host diagnostics export completion must present success feedback")

        context.feedback.clearNotice()
        diagnostics.exportReport(report, defaultFilename: "Stub-Diagnostics.json") { _, _, done in
            done(.cancelled)
        }
        precondition(context.feedback.notice == nil, "Cancelled diagnostics export must not present a notice")

        diagnostics.exportReport(report, defaultFilename: "Stub-Diagnostics.json") { _, _, done in
            done(.failed)
        }
        precondition(
            context.feedback.notice?.text.key == "host.error.diagnosticsExport" && context.feedback.notice?.tone == .warning,
            "Failed diagnostics export must present warning feedback"
        )

        diagnostics.clearCompletedLogs()
        precondition(context.feedback.notice?.text.key == "host.logs.cleared", "clearCompletedLogs must publish host notice")

        // 5. Status suppression clears completely across either notice/error consumption or explicit reset.
        let suppressionCenter = TrainerFeedbackCenter()
        suppressionCenter.suppressNextStatus(error: true) { $0.error != "host.keep" }
        var noticeStatus = TrainerBackendStatus()
        noticeStatus.notice = "host.backend.notice.completed"
        suppressionCenter.receiveBackendStatus(previous: TrainerBackendStatus(), current: noticeStatus)
        precondition(suppressionCenter.notice == nil, "suppressed notice transition should stay suppressed")
        var laterIdleError = noticeStatus
        laterIdleError.notice = ""
        laterIdleError.error = "host.backend.error.terminated"
        suppressionCenter.receiveBackendStatus(previous: noticeStatus, current: laterIdleError)
        precondition(
            suppressionCenter.notice?.text.key == "host.backend.error.terminated" && suppressionCenter.notice?.tone == .warning,
            "consumed notice transition leaked suppressNextStatusError onto a later idle error"
        )

        suppressionCenter.clearNotice()
        suppressionCenter.suppressNextStatus(error: true)
        suppressionCenter.clearStatusSuppression()
        var resetErrorStatus = TrainerBackendStatus()
        resetErrorStatus.error = "host.backend.error.terminated"
        suppressionCenter.receiveBackendStatus(previous: TrainerBackendStatus(), current: resetErrorStatus)
        precondition(
            suppressionCenter.notice?.text.key == "host.backend.error.terminated" && suppressionCenter.notice?.tone == .warning,
            "clearStatusSuppression must clear both notice and error suppression"
        )

        withExtendedLifetime(statusSub) {}
        print("host_feedback_diagnostics_ok")
    }
}
"""

with tempfile.TemporaryDirectory(prefix="mgt-host-feedback-diag-") as temporary:
    temp = Path(temporary)
    for language in ("zh-CN", "en"):
        (temp / f"{language}.lproj").mkdir()
        shutil.copy2(ROOT / f"Resources/Localization/{language}.lproj/Host.strings", temp / f"{language}.lproj/Host.strings")
    harness_path = temp / "HostFeedbackDiagnosticsTest.swift"
    harness_path.write_text(harness, encoding="utf-8")
    executable = temp / "host-feedback-diagnostics-tests"
    compile_swift_test(
        harness_sources=[ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", harness_path],
        output=executable,
        swiftc=SWIFT,
        cwd=ROOT,
    )
    result = subprocess.run([str(executable)], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "host_feedback_diagnostics_ok" in result.stdout
