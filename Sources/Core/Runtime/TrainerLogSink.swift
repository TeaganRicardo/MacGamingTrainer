import Darwin
import Foundation

/// Sole persistent Trainer log owner for one game module.
///
/// Backend/sidecar diagnostics arrive through stderr and are appended here by
/// the Host, so rotation, target-session boundaries and retention all share one
/// filesystem lifecycle.
final class TrainerLogSink {
    static let maximumSessionFileSize = 4 * 1_048_576
    static let maximumHostFileSize = 1_048_576
    static let maximumCompletedSessions = 8
    static let maximumTotalBytes = 32 * 1_048_576
    static let maximumPendingBytes = 1_048_576
    // Compatibility for unmanaged/test callers that referenced the old limit.
    static let maximumFileSize = maximumHostFileSize

    struct TargetIdentity: Equatable {
        let processName: String
        let bundleIdentifier: String
        let processIdentifier: Int32?
    }

    private struct SessionRecord: Codable, Equatable {
        let id: String
        let startedAt: String
        var endedAt: String?
        let targetProcessName: String
        let targetBundleIdentifier: String
        let targetPID: Int32?
        let appVersion: String
        let appBuild: String
        let legacy: Bool
    }

    let url: URL
    let hostURL: URL
    let historyURL: URL

    private let metadataURL: URL
    private let managedSessions: Bool
    private let queue = DispatchQueue(label: "com.gao.macgamingtrainer.log", qos: .utility)
    private let pendingLock = NSLock()
    private let formatter = ISO8601DateFormatter()
    private var pendingBytes = 0
    private var droppedPendingBytes = 0
    private var overflowMarkerScheduled = false
    private var handle: FileHandle?
    private var handleURL: URL?
    private var activeSession: SessionRecord?
    private var completedBytes: UInt64?

    init(url: URL) {
        self.url = url
        self.hostURL = url
        self.historyURL = url.deletingLastPathComponent().appendingPathComponent("sessions", isDirectory: true)
        self.metadataURL = url.deletingLastPathComponent().appendingPathComponent("current-session.json")
        self.managedSessions = false
    }

    init(gameID: String, homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser) {
        let gameDirectory = Self.moduleLogDirectory(gameID: gameID, homeDirectory: homeDirectory)
        self.url = gameDirectory.appendingPathComponent("trainer.log")
        self.hostURL = gameDirectory.appendingPathComponent("trainer-host.log")
        self.historyURL = gameDirectory.appendingPathComponent("sessions", isDirectory: true)
        self.metadataURL = gameDirectory.appendingPathComponent("current-session.json")
        self.managedSessions = true
    }

    static func moduleLogDirectory(
        gameID: String,
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
    ) -> URL {
        homeDirectory
            .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
            .appendingPathComponent(gameID, isDirectory: true)
    }

    static func moduleLogURL(
        gameID: String,
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
    ) -> URL {
        moduleLogDirectory(gameID: gameID, homeDirectory: homeDirectory)
            .appendingPathComponent("trainer.log")
    }

    deinit {
        try? handle?.synchronize()
        try? handle?.close()
        handle = nil
        handleURL = nil
    }

    func append(_ line: String, source: String = "HOST") {
        guard !line.isEmpty else { return }
        let bytes = min(Int.max - 128, line.utf8.count) + 128
        var accepted = false
        var scheduleOverflowMarker = false

        pendingLock.lock()
        if bytes <= Self.maximumPendingBytes,
           pendingBytes <= Self.maximumPendingBytes - bytes {
            pendingBytes += bytes
            accepted = true
        } else {
            droppedPendingBytes = min(Int.max - bytes, droppedPendingBytes) + bytes
            if !overflowMarkerScheduled {
                overflowMarkerScheduled = true
                scheduleOverflowMarker = true
            }
        }
        pendingLock.unlock()

        if accepted {
            queue.async { [weak self] in
                guard let self else { return }
                defer { self.releasePendingBytes(bytes) }
                do {
                    try self.appendLocked(line, source: source)
                } catch {
                    // Diagnostics must never interfere with Trainer/game operation,
                    // and a log failure cannot recursively log itself.
                }
            }
        }
        if scheduleOverflowMarker {
            queue.async { [weak self] in self?.writeOverflowMarkerLocked() }
        }
    }

    func flush() {
        queue.sync { try? handle?.synchronize() }
    }

    /// Enter or leave one OS target-process lifetime. Reconnects and Backend
    /// restarts never call this seam, so they remain inside the same session.
    func targetLifetimeChanged(running: Bool, identity: TargetIdentity) {
        guard managedSessions else { return }
        queue.sync {
            do {
                if running {
                    try beginTargetSessionLocked(identity: identity)
                } else {
                    try finishTargetSessionLocked()
                }
            } catch {
                // Session bookkeeping is diagnostics-only and fail-open.
            }
        }
    }

    /// Current target session when one exists; otherwise Host/app context.
    func currentLogURL() -> URL {
        queue.sync {
            if managedSessions, activeSession == nil {
                activeSession = loadCurrentSessionLocked()
            }
            return managedSessions && activeSession == nil ? hostURL : url
        }
    }

    @discardableResult
    func clearCompletedSessions() -> Bool {
        guard managedSessions else { return false }
        return queue.sync {
            do {
                if FileManager.default.fileExists(atPath: historyURL.path) {
                    try FileManager.default.removeItem(at: historyURL)
                }
                try FileManager.default.createDirectory(at: historyURL, withIntermediateDirectories: true)
                completedBytes = 0
                return true
            } catch {
                // Cleanup failure is reported to the caller, but diagnostics
                // storage must never interfere with the active Trainer session.
                return false
            }
        }
    }

    private func releasePendingBytes(_ bytes: Int) {
        pendingLock.lock()
        pendingBytes = max(0, pendingBytes - bytes)
        pendingLock.unlock()
    }

    private func writeOverflowMarkerLocked() {
        let dropped: Int
        pendingLock.lock()
        dropped = droppedPendingBytes
        droppedPendingBytes = 0
        overflowMarkerScheduled = false
        pendingLock.unlock()
        guard dropped > 0 else { return }
        try? appendLocked("log queue overflow droppedBytes=\(dropped)", source: "LOGGER")
    }

    private func appendLocked(_ line: String, source: String) throws {
        let destination = writeURLLocked()
        let limit = activeSession == nil ? Self.maximumHostFileSize : Self.maximumSessionFileSize
        let prefix = "\(formatter.string(from: Date())) \(source) "
        let taggedLine = line.replacingOccurrences(of: "\n", with: "\n" + prefix)
        guard let prefixData = prefix.data(using: .utf8),
              var messageData = taggedLine.data(using: .utf8) else { return }
        let suffix = Data("\n".utf8)
        let maximumMessageBytes = max(0, limit - prefixData.count - suffix.count)
        if messageData.count > maximumMessageBytes {
            var start = messageData.count - maximumMessageBytes
            while start < messageData.count && (messageData[start] & 0xC0) == 0x80 {
                start += 1
            }
            messageData = Data(messageData[start...])
        }
        var data = Data()
        data.reserveCapacity(prefixData.count + messageData.count + suffix.count)
        data.append(prefixData)
        data.append(messageData)
        data.append(suffix)

        var destinationHandle = try ensureHandle(for: destination)
        let currentSize = try fileSize(destination)
        if currentSize + UInt64(data.count) > UInt64(limit) {
            try trimLogLocked(destination, keepingBytes: max(0, limit - data.count))
            destinationHandle = try ensureHandle(for: destination)
        }
        try destinationHandle.write(contentsOf: data)

        if managedSessions {
            try pruneRetentionForTotalCapLocked()
        }
    }

    private func writeURLLocked() -> URL {
        guard managedSessions else { return url }
        if activeSession == nil {
            activeSession = loadCurrentSessionLocked()
        }
        return activeSession == nil ? hostURL : url
    }

    private func beginTargetSessionLocked(identity: TargetIdentity) throws {
        try ensureDirectoriesLocked()
        if let existing = loadCurrentSessionLocked() {
            if let pid = identity.processIdentifier,
               existing.targetPID == pid,
               FileManager.default.fileExists(atPath: url.path) {
                activeSession = existing
                try switchHandleLocked(to: url)
                try appendLocked(
                    "session resume id=\(existing.id) targetPID=\(pid)",
                    source: "HOST"
                )
                return
            }
            activeSession = existing
            try finishTargetSessionLocked()
        } else if hasLegacyCurrentLogsLocked() {
            try archiveLegacyLogsLocked()
        }

        let now = Date()
        let record = SessionRecord(
            id: Self.sessionID(date: now),
            startedAt: formatter.string(from: now),
            endedAt: nil,
            targetProcessName: identity.processName,
            targetBundleIdentifier: identity.bundleIdentifier,
            targetPID: identity.processIdentifier,
            appVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "unknown",
            appBuild: Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "unknown",
            legacy: false
        )
        activeSession = record
        try writeSessionRecord(record, to: metadataURL)
        try switchHandleLocked(to: url)
        try appendLocked(
            "session start id=\(record.id) target=\(record.targetProcessName) bundle=\(record.targetBundleIdentifier) targetPID=\(record.targetPID.map { String($0) } ?? "unknown") app=\(record.appVersion) build=\(record.appBuild)",
            source: "HOST"
        )
    }

    private func finishTargetSessionLocked() throws {
        guard var record = activeSession ?? loadCurrentSessionLocked() else {
            if hasLegacyCurrentLogsLocked() {
                try archiveLegacyLogsLocked()
            }
            try switchHandleLocked(to: hostURL)
            return
        }

        activeSession = record
        try appendLocked("session end id=\(record.id)", source: "HOST")
        try closeHandleLocked()

        record.endedAt = formatter.string(from: Date())
        try ensureDirectoriesLocked()
        let completedLog = historyURL.appendingPathComponent(record.id).appendingPathExtension("log")
        let completedMetadata = historyURL.appendingPathComponent(record.id).appendingPathExtension("json")
        if FileManager.default.fileExists(atPath: completedLog.path) {
            try FileManager.default.removeItem(at: completedLog)
        }
        if FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.moveItem(at: url, to: completedLog)
        }
        try writeSessionRecord(record, to: completedMetadata)
        if FileManager.default.fileExists(atPath: metadataURL.path) {
            try FileManager.default.removeItem(at: metadataURL)
        }
        activeSession = nil
        completedBytes = nil
        try pruneCompletedCountLocked()
        try pruneRetentionForTotalCapLocked()
        try switchHandleLocked(to: hostURL)
    }

    private func archiveLegacyLogsLocked() throws {
        try closeHandleLocked()
        try ensureDirectoriesLocked()
        let candidates = [3, 2, 1].map { url.appendingPathExtension(String($0)) } + [url]
        var combined = Data()
        for candidate in candidates where FileManager.default.fileExists(atPath: candidate.path) {
            let tail = try tailData(candidate, maximumBytes: Self.maximumSessionFileSize)
            combined.append(tail)
            if combined.count > Self.maximumSessionFileSize {
                combined = Data(combined.suffix(Self.maximumSessionFileSize))
            }
        }
        if !combined.isEmpty {
            let id = "legacy-" + Self.sessionID(date: Date())
            let completedLog = historyURL.appendingPathComponent(id).appendingPathExtension("log")
            try combined.write(to: completedLog, options: .atomic)
            let legacy = SessionRecord(
                id: id,
                startedAt: formatter.string(from: Date()),
                endedAt: formatter.string(from: Date()),
                targetProcessName: "",
                targetBundleIdentifier: "",
                targetPID: nil,
                appVersion: "unknown",
                appBuild: "unknown",
                legacy: true
            )
            try writeSessionRecord(
                legacy,
                to: historyURL.appendingPathComponent(id).appendingPathExtension("json")
            )
        }
        for candidate in candidates where FileManager.default.fileExists(atPath: candidate.path) {
            try? FileManager.default.removeItem(at: candidate)
        }
        completedBytes = nil
        try pruneCompletedCountLocked()
        try pruneRetentionForTotalCapLocked()
    }

    private func pruneCompletedCountLocked() throws {
        let logs = try completedLogFilesLocked()
        guard logs.count > Self.maximumCompletedSessions else { return }
        for file in logs.prefix(logs.count - Self.maximumCompletedSessions) {
            try removeCompletedLogLocked(file)
        }
        completedBytes = nil
    }

    private func pruneRetentionForTotalCapLocked() throws {
        let hostBytes = try fileSize(hostURL)
        let currentBytes = try fileSize(url)
        var retained: UInt64
        if let completedBytes {
            retained = completedBytes
        } else {
            retained = try completedLogFilesLocked().reduce(UInt64(0)) { partial, file in
                partial + (try fileSize(file))
            }
        }
        completedBytes = retained
        var total = hostBytes + currentBytes + retained
        guard total > UInt64(Self.maximumTotalBytes) else { return }

        for file in try completedLogFilesLocked() {
            let bytes = try fileSize(file)
            try removeCompletedLogLocked(file)
            retained = retained > bytes ? retained - bytes : 0
            total = hostBytes + currentBytes + retained
            if total <= UInt64(Self.maximumTotalBytes) { break }
        }
        completedBytes = retained
    }

    private func removeCompletedLogLocked(_ file: URL) throws {
        try FileManager.default.removeItem(at: file)
        let metadata = file.deletingPathExtension().appendingPathExtension("json")
        if FileManager.default.fileExists(atPath: metadata.path) {
            try? FileManager.default.removeItem(at: metadata)
        }
    }

    private func completedLogFilesLocked() throws -> [URL] {
        guard FileManager.default.fileExists(atPath: historyURL.path) else { return [] }
        return try FileManager.default.contentsOfDirectory(
            at: historyURL,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        )
        .filter { $0.pathExtension == "log" }
        .sorted {
            let lhs = (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            let rhs = (try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
            return lhs < rhs
        }
    }

    private func trimLogLocked(_ file: URL, keepingBytes: Int) throws {
        try closeHandleLocked()
        let tail = keepingBytes > 0
            ? try tailData(file, maximumBytes: keepingBytes)
            : Data()
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try tail.write(to: file, options: .atomic)
    }

    private func tailData(_ file: URL, maximumBytes: Int) throws -> Data {
        guard maximumBytes > 0,
              FileManager.default.fileExists(atPath: file.path) else { return Data() }
        let read = try FileHandle(forReadingFrom: file)
        defer { try? read.close() }
        let size = try read.seekToEnd()
        let start = size > UInt64(maximumBytes) ? size - UInt64(maximumBytes) : 0
        try read.seek(toOffset: start)
        var data = try read.readToEnd() ?? Data()
        while !data.isEmpty && (data[data.startIndex] & 0xC0) == 0x80 {
            data.removeFirst()
        }
        return data
    }

    private func ensureDirectoriesLocked() throws {
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try FileManager.default.createDirectory(at: historyURL, withIntermediateDirectories: true)
    }

    private func ensureHandle(for destination: URL) throws -> FileHandle {
        if handleURL == destination, let handle { return handle }
        try switchHandleLocked(to: destination)
        guard let handle else {
            throw NSError(domain: "TrainerLogSink", code: 1)
        }
        return handle
    }

    private func switchHandleLocked(to destination: URL) throws {
        if handleURL == destination, handle != nil { return }
        try closeHandleLocked()
        try FileManager.default.createDirectory(
            at: destination.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        if !FileManager.default.fileExists(atPath: destination.path) {
            _ = FileManager.default.createFile(atPath: destination.path, contents: nil)
        }
        let fd = open(destination.path, O_WRONLY | O_APPEND)
        guard fd >= 0 else {
            throw NSError(
                domain: NSPOSIXErrorDomain,
                code: Int(errno),
                userInfo: [NSLocalizedDescriptionKey: "无法以追加模式打开日志。"]
            )
        }
        handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
        handleURL = destination
    }

    private func closeHandleLocked() throws {
        if let handle {
            try handle.synchronize()
            try handle.close()
        }
        handle = nil
        handleURL = nil
    }

    private func loadCurrentSessionLocked() -> SessionRecord? {
        guard managedSessions,
              let data = try? Data(contentsOf: metadataURL),
              let record = try? JSONDecoder().decode(SessionRecord.self, from: data) else { return nil }
        return record
    }

    private func writeSessionRecord(_ record: SessionRecord, to destination: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(record)
        try FileManager.default.createDirectory(
            at: destination.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: destination, options: .atomic)
    }

    private func hasLegacyCurrentLogsLocked() -> Bool {
        if FileManager.default.fileExists(atPath: url.path) { return true }
        return (1...3).contains {
            FileManager.default.fileExists(atPath: url.appendingPathExtension(String($0)).path)
        }
    }

    private func fileSize(_ file: URL) throws -> UInt64 {
        guard FileManager.default.fileExists(atPath: file.path) else { return 0 }
        let attributes = try FileManager.default.attributesOfItem(atPath: file.path)
        return (attributes[.size] as? NSNumber)?.uint64Value ?? 0
    }

    private static func sessionID(date: Date) -> String {
        let stamp = ISO8601DateFormatter().string(from: date)
            .replacingOccurrences(of: ":", with: "-")
        return stamp + "-" + String(UUID().uuidString.prefix(8)).lowercased()
    }
}
