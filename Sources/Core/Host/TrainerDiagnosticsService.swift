import AppKit
import Foundation
import UniformTypeIdentifiers

package struct TrainerDiagnosticCheck: Identifiable, Equatable {
    package let id: String
    package let name: TrainerTextToken
    package let ok: Bool
    package let detail: TrainerTextToken

    package init(id: String, name: TrainerTextToken, ok: Bool, detail: TrainerTextToken) {
        self.id = id
        self.name = name
        self.ok = ok
        self.detail = detail
    }

    package init(
        name: String,
        nameArguments: [String] = [],
        ok: Bool,
        detail: String,
        detailArguments: [String] = []
    ) {
        self.init(
            id: ([name] + nameArguments).joined(separator: ":"),
            name: TrainerTextToken(key: name, arguments: nameArguments),
            ok: ok,
            detail: TrainerTextToken(key: detail, arguments: detailArguments)
        )
    }

    package static func decode(_ row: [String: Any]) -> TrainerDiagnosticCheck? {
        guard let name = row["name"] as? String, !name.isEmpty else { return nil }
        let nameArguments = (row["nameArguments"] as? [Any])?.map { String(describing: $0) } ?? []
        let detailKey = row["detail"] as? String ?? row["detail"].map { String(describing: $0) } ?? ""
        let detailArguments = (row["detailArguments"] as? [Any])?.map { String(describing: $0) } ?? []
        let id = (row["id"] as? String).flatMap { $0.isEmpty ? nil : $0 }
            ?? ([name] + nameArguments).joined(separator: ":")
        return TrainerDiagnosticCheck(
            id: id,
            name: TrainerTextToken(key: name, arguments: nameArguments),
            ok: row["ok"] as? Bool ?? false,
            detail: TrainerTextToken(key: detailKey, arguments: detailArguments)
        )
    }
}

package enum TrainerDiagnosticsExportOutcome: Equatable {
    case saved, cancelled, failed
}

/// Host-owned log access, retention cleanup, and diagnostic report export.
///
/// The Host reads only its own `TrainerLogSink` session bundle or fallback
/// log file and serializes module-supplied read-only check/state payloads into
/// one JSON report, keeping Python backends independent of Host log layout.
@MainActor
package final class TrainerDiagnosticsService {
    package typealias ExportSaveHandler = @MainActor (
        Data,
        String,
        @escaping @MainActor (TrainerDiagnosticsExportOutcome) -> Void
    ) -> Void

    package let descriptor: GameModuleDescriptor
    package let session: TrainerBackendSession
    package let logSink: TrainerLogSink
    package let feedback: TrainerFeedbackCenter
    private let defaultFilename: String

    package init(
        descriptor: GameModuleDescriptor,
        session: TrainerBackendSession,
        logSink: TrainerLogSink,
        feedback: TrainerFeedbackCenter
    ) {
        self.descriptor = descriptor
        self.session = session
        self.logSink = logSink
        self.feedback = feedback
        self.defaultFilename = Self.defaultExportFilename(for: descriptor.displayName)
    }

    package func openLog() {
        session.flushDiagnostics()
        logSink.flush()
        NSWorkspace.shared.open(logSink.currentSessionURL() ?? logSink.currentLogURL())
    }

    package func openLogHistory() {
        do {
            logSink.flush()
            try FileManager.default.createDirectory(at: logSink.historyURL, withIntermediateDirectories: true)
            NSWorkspace.shared.open(logSink.historyURL)
        } catch {
            feedback.present(TrainerTextToken(key: "host.error.logOpen"), tone: .warning)
        }
    }

    package func clearCompletedLogs() {
        let cleared = logSink.clearCompletedSessions()
        feedback.present(
            TrainerTextToken(key: cleared ? "host.logs.cleared" : "host.logs.clearFailed"),
            tone: cleared ? .success : .warning
        )
    }

    package func buildExportData(report: [String: Any]) throws -> Data {
        session.flushDiagnostics()
        logSink.flush()
        var payload = report
        var logs: [String: String] = [:]
        let urls: [URL]
        if let bundle = logSink.currentSessionURL() {
            urls = ["manifest.json", "host.log", "backend.log", "runtime.log"].map {
                bundle.appendingPathComponent($0)
            }
        } else {
            urls = [logSink.currentLogURL()]
        }
        for url in urls where FileManager.default.fileExists(atPath: url.path) {
            logs[url.lastPathComponent] = try String(contentsOf: url, encoding: .utf8)
        }
        payload["logs"] = logs
        if payload["gameID"] == nil { payload["gameID"] = descriptor.id }
        if payload["generatedAt"] == nil {
            let formatter = ISO8601DateFormatter()
            payload["generatedAt"] = formatter.string(from: Date())
        }
        return try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
    }

    package func exportReport(
        _ report: [String: Any],
        defaultFilename: String? = nil,
        saveHandler: ExportSaveHandler? = nil
    ) {
        do {
            let data = try buildExportData(report: report)
            let filename = defaultFilename ?? self.defaultFilename
            let handler = saveHandler ?? Self.defaultSaveHandler
            handler(data, filename) { [feedback] outcome in
                switch outcome {
                case .saved:
                    feedback.present(TrainerTextToken(key: "host.backend.notice.completed"), tone: .success)
                case .failed:
                    feedback.present(TrainerTextToken(key: "host.error.diagnosticsExport"), tone: .warning)
                case .cancelled:
                    break
                }
            }
        } catch {
            feedback.present(TrainerTextToken(key: "host.error.diagnosticsExport"), tone: .warning)
        }
    }

    private static func defaultExportFilename(for displayName: String) -> String {
        let trimmed = displayName.trimmingCharacters(in: .whitespacesAndNewlines)
        let sanitized = trimmed
            .replacingOccurrences(of: "/", with: "-")
            .replacingOccurrences(of: ":", with: "-")
        let prefix = sanitized.isEmpty ? "Trainer" : sanitized
        return "\(prefix)-Diagnostics.json"
    }

    @MainActor
    private static let defaultSaveHandler: ExportSaveHandler = { data, filename, completion in
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = filename
        panel.begin { response in
            guard response == .OK, let url = panel.url else {
                completion(.cancelled)
                return
            }
            do {
                try data.write(to: url, options: .atomic)
                completion(.saved)
            } catch {
                completion(.failed)
            }
        }
    }
}
