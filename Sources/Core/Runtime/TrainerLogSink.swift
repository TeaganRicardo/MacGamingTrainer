import Darwin
import Foundation

/// Sole persistent Trainer log owner for one game module.
///
/// Backend/sidecar diagnostics arrive through stderr and are appended here by
/// the Host. A target-process lifetime is persisted as a self-contained bundle:
/// manifest.json plus separate Host, Backend and Runtime text streams. The Host
/// remains the only writer/rotation/retention owner.
final class TrainerLogSink {
    static let maximumSessionBytes = 4 * 1_048_576
    static let maximumHostFileSize = 1_048_576
    static let maximumCompletedSessions = 8
    static let maximumTotalBytes = 32 * 1_048_576
    static let maximumPendingBytes = 1_048_576

    struct TargetIdentity: Equatable {
        let processName: String
        let bundleIdentifier: String
        let processIdentifier: Int32?
    }

    private enum SessionState: String, Codable {
        case active
        case finalizing
        case completed
    }

    private enum Stream: String, CaseIterable {
        case host = "HOST"
        case backend = "BACKEND"
        case runtime = "RUNTIME"

        var filename: String {
            switch self {
            case .host:
                return "host.log"
            case .backend:
                return "backend.log"
            case .runtime:
                return "runtime.log"
            }
        }

        var maximumBytes: Int {
            switch self {
            case .host:
                return 1 * 1_048_576
            case .backend:
                return 2 * 1_048_576
            case .runtime:
                return 1 * 1_048_576
            }
        }
    }

    private struct CurrentSessionPointer: Codable {
        let id: String
    }

    private struct SessionRecord: Codable, Equatable {
        static let currentSchemaVersion = 1

        let schemaVersion: Int
        let id: String
        let startedAt: String
        var endedAt: String?
        let targetProcessName: String
        let targetBundleIdentifier: String
        let targetPID: Int32?
        let appVersion: String
        let appBuild: String
        var gameVersion: String?
        var runtimeRevision: Int?
        var state: SessionState
        var endReason: String?
        let streams: [String: String]
        let legacy: Bool

        init(
            id: String,
            startedAt: String,
            endedAt: String?,
            targetProcessName: String,
            targetBundleIdentifier: String,
            targetPID: Int32?,
            appVersion: String,
            appBuild: String,
            gameVersion: String?,
            runtimeRevision: Int?,
            state: SessionState,
            endReason: String?,
            streams: [String: String],
            legacy: Bool
        ) {
            self.schemaVersion = Self.currentSchemaVersion
            self.id = id
            self.startedAt = startedAt
            self.endedAt = endedAt
            self.targetProcessName = targetProcessName
            self.targetBundleIdentifier = targetBundleIdentifier
            self.targetPID = targetPID
            self.appVersion = appVersion
            self.appBuild = appBuild
            self.gameVersion = gameVersion
            self.runtimeRevision = runtimeRevision
            self.state = state
            self.endReason = endReason
            self.streams = streams
            self.legacy = legacy
        }
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
    private var handles: [Stream: FileHandle] = [:]
    private var activeSession: SessionRecord?

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
        for handle in handles.values {
            try? handle.synchronize()
            try? handle.close()
        }
        handles.removeAll()
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
                    // Diagnostics must never interfere with Trainer/game
                    // operation, and a log failure cannot recursively log itself.
                }
            }
        }

        if scheduleOverflowMarker {
            queue.async { [weak self] in self?.writeOverflowMarkerLocked() }
        }
    }

    func flush() {
        queue.sync {
            for handle in handles.values {
                try? handle.synchronize()
            }
        }
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
                    try finishTargetSessionLocked(reason: "target-exited")
                }
            } catch {
                // Session bookkeeping is diagnostics-only and fail-open.
            }
        }
    }

    /// Add runtime identity once the game-owned resident has reported it.
    /// This enriches the same OS target session; it never creates a new one.
    func updateCurrentSessionRuntimeIdentity(gameVersion: String?, runtimeRevision: Int?) {
        guard managedSessions, gameVersion != nil || runtimeRevision != nil else { return }
        queue.sync { [weak self] in
            guard let self, var record = self.activeSession ?? self.loadCurrentSessionLocked(),
                  record.state == .active else { return }

            let resolvedGameVersion = gameVersion ?? record.gameVersion
            let resolvedRuntimeRevision = runtimeRevision ?? record.runtimeRevision
            guard resolvedGameVersion != record.gameVersion ||
                    resolvedRuntimeRevision != record.runtimeRevision else { return }

            record.gameVersion = resolvedGameVersion
            record.runtimeRevision = resolvedRuntimeRevision
            self.activeSession = record

            do {
                try self.writeSessionRecord(record)
                let game = record.gameVersion ?? "unknown"
                let revision = record.runtimeRevision.map { String($0) } ?? "unknown"
                try self.appendLocked(
                    "session runtime gameVersion=\(game) residentRevision=\(revision)",
                    source: Stream.runtime.rawValue
                )
            } catch {
                // Runtime identity enrichment is diagnostics-only and fail-open.
            }
        }
    }

    /// Current target session log. This preserves the existing single-file
    /// caller contract by returning the Host stream inside the active bundle.
    func currentLogURL() -> URL {
        queue.sync {
            guard managedSessions else { return url }
            guard let record = activeSessionRecordLocked() else { return hostURL }
            return streamURL(for: .host, record: record)
        }
    }

    /// Self-contained target session bundle for the current target lifetime.
    /// Returns nil when only Host/app context exists.
    func currentSessionURL() -> URL? {
        queue.sync {
            guard managedSessions, let record = activeSessionRecordLocked() else { return nil }
            return sessionDirectoryURL(for: record)
        }
    }

    @discardableResult
    func clearCompletedSessions() -> Bool {
        guard managedSessions else { return false }
        return queue.sync {
            do {
                try ensureDirectoriesLocked()
                for (bundle, _) in try completedSessionBundlesLocked() {
                    try FileManager.default.removeItem(at: bundle)
                }
                return true
            } catch {
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
        try? appendLocked(
            "log queue overflow droppedBytes=\(dropped)",
            source: "LOGGER"
        )
    }

    private func appendLocked(_ line: String, source: String) throws {
        let stream = managedSessions ? streamForSource(source) : .host
        let destinationInfo = writeDestinationLocked(for: stream)
        let destination = destinationInfo.url
        let limit = destinationInfo.inSession
            ? stream.maximumBytes
            : Self.maximumHostFileSize

        let cleanSource = source.replacingOccurrences(of: "\n", with: " ")
        let prefix = "\(formatter.string(from: Date())) \(cleanSource) "
        let taggedLine = line.replacingOccurrences(of: "\n", with: "\n" + prefix)
        guard let prefixData = prefix.data(using: .utf8),
              var messageData = taggedLine.data(using: .utf8) else { return }

        let suffix = Data("\n".utf8)
        let maximumMessageBytes = max(0, limit - prefixData.count - suffix.count)
        if messageData.count > maximumMessageBytes {
            let start = messageData.count - maximumMessageBytes
            var boundary = start
            while boundary < messageData.count && (messageData[boundary] & 0xC0) == 0x80 {
                boundary += 1
            }
            messageData = Data(messageData[boundary...])
        }

        var data = Data()
        data.reserveCapacity(prefixData.count + messageData.count + suffix.count)
        data.append(prefixData)
        data.append(messageData)
        data.append(suffix)

        var destinationHandle = try ensureHandle(for: stream, destination: destination)
        let currentSize = try fileSize(destination)
        if currentSize + UInt64(data.count) > UInt64(limit) {
            try trimLogLocked(destination, stream: stream, keepingBytes: max(0, limit - data.count))
            destinationHandle = try ensureHandle(for: stream, destination: destination)
        }
        try destinationHandle.write(contentsOf: data)

        if managedSessions {
            try pruneRetentionForTotalCapLocked()
        }
    }

    private func streamForSource(_ source: String) -> Stream {
        Stream(rawValue: source.uppercased()) ?? .host
    }

    private func writeDestinationLocked(for stream: Stream) -> (url: URL, inSession: Bool) {
        guard managedSessions else { return (url, false) }
        guard let record = sessionRecordForWritingLocked() else { return (hostURL, false) }
        return (streamURL(for: stream, record: record), true)
    }

    private func sessionRecordForWritingLocked() -> SessionRecord? {
        if let activeSession, activeSession.state != .completed {
            return activeSession
        }
        guard let existing = loadCurrentSessionLocked(), existing.state != .completed else {
            return nil
        }
        activeSession = existing
        return existing
    }

    private func beginTargetSessionLocked(identity: TargetIdentity) throws {
        try ensureDirectoriesLocked()

        if let existing = loadCurrentSessionLocked() {
            let bundleExists = FileManager.default.fileExists(atPath: sessionDirectoryURL(for: existing).path)

            if !bundleExists {
                activeSession = nil
                try clearCurrentSessionPointerLocked()
            } else if let pid = identity.processIdentifier,
                      existing.targetPID == pid,
                      existing.targetProcessName == identity.processName,
                      existing.targetBundleIdentifier == identity.bundleIdentifier,
                      existing.state == .active || existing.state == .finalizing {
                var resumed = existing
                if resumed.state == .finalizing {
                    resumed.state = .active
                    resumed.endedAt = nil
                    resumed.endReason = nil
                    try writeSessionRecord(resumed)
                    try writeCurrentSessionPointerLocked(id: resumed.id)
                }
                activeSession = resumed
                try appendLocked(
                    "session resume id=\(resumed.id) targetPID=\(pid)",
                    source: Stream.host.rawValue
                )
                return
            } else if existing.state == .completed {
                try clearCurrentSessionPointerLocked()
                activeSession = nil
            } else {
                try completeSessionLocked(existing, reason: "target-replaced")
            }
        }

        if hasLegacyCurrentLogsLocked() {
            try archiveLegacyLogsLocked()
        }

        try createTargetSessionLocked(identity: identity)
    }

    private func createTargetSessionLocked(identity: TargetIdentity) throws {
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
            gameVersion: nil,
            runtimeRevision: nil,
            state: .active,
            endReason: nil,
            streams: Dictionary(uniqueKeysWithValues: Stream.allCases.map { ($0.rawValue, $0.filename) }),
            legacy: false
        )

        activeSession = record
        try FileManager.default.createDirectory(
            at: sessionDirectoryURL(for: record),
            withIntermediateDirectories: true
        )
        try writeSessionRecord(record)
        try writeCurrentSessionPointerLocked(id: record.id)
        try appendLocked(
            "session start id=\(record.id) target=\(record.targetProcessName) bundle=\(record.targetBundleIdentifier) targetPID=\(record.targetPID.map { String($0) } ?? "unknown") app=\(record.appVersion) build=\(record.appBuild)",
            source: Stream.host.rawValue
        )
    }

    private func finishTargetSessionLocked(reason: String) throws {
        guard var record = activeSession ?? loadCurrentSessionLocked() else {
            if hasLegacyCurrentLogsLocked() {
                try archiveLegacyLogsLocked()
            }
            return
        }

        guard record.state != .completed else {
            try clearCurrentSessionPointerLocked()
            activeSession = nil
            try closeAllHandlesLocked()
            return
        }

        record.endedAt = formatter.string(from: Date())
        record.state = .finalizing
        record.endReason = reason
        activeSession = record

        // Persist intent before log mutation. Because the session bundle already
        // contains its streams, recovery never has to move or replace log files.
        try writeSessionRecord(record)
        try? appendLocked("session end id=\(record.id)", source: Stream.host.rawValue)
        try closeAllHandlesLocked()

        record.state = .completed
        activeSession = record
        try writeSessionRecord(record)
        try clearCurrentSessionPointerLocked()
        activeSession = nil

        try pruneCompletedCountLocked()
        try pruneRetentionForTotalCapLocked()
    }

    private func completeSessionLocked(_ record: SessionRecord, reason: String) throws {
        var recovered = record
        recovered.endedAt = recovered.endedAt ?? formatter.string(from: Date())
        recovered.state = .finalizing
        recovered.endReason = recovered.endReason ?? reason
        activeSession = recovered

        // Persist finalization intent before adding recovery evidence. The bundle
        // remains the same filesystem object throughout recovery.
        try writeSessionRecord(recovered)
        if !recovered.legacy {
            try? appendLocked(
                "session recovered state=" + record.state.rawValue + " reason=" + reason,
                source: Stream.host.rawValue
            )
        }
        try closeAllHandlesLocked()
        recovered.state = .completed
        activeSession = recovered
        try writeSessionRecord(recovered)
        if loadCurrentSessionPointerIDLocked() == recovered.id {
            try clearCurrentSessionPointerLocked()
        }
        activeSession = nil

        try pruneCompletedCountLocked()
        try pruneRetentionForTotalCapLocked()
    }

    private func activeSessionRecordLocked() -> SessionRecord? {
        if let activeSession, activeSession.state == .active {
            return activeSession
        }
        guard let existing = loadCurrentSessionLocked(), existing.state == .active else {
            return nil
        }
        activeSession = existing
        return existing
    }

    private func ensureDirectoriesLocked() throws {
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try FileManager.default.createDirectory(
            at: historyURL,
            withIntermediateDirectories: true
        )
        try recoverUnindexedSessionBundlesLocked()
        try recoverOrphanedSessionsLocked()
    }

    private func recoverOrphanedSessionsLocked() throws {
        let currentID = loadCurrentSessionPointerIDLocked()
        for (_, record) in try sessionBundlesLocked() {
            guard record.state != .completed, record.id != currentID else { continue }
            try completeSessionLocked(record, reason: "interrupted")
        }
    }

    private func recoverUnindexedSessionBundlesLocked() throws {
        let entries = try FileManager.default.contentsOfDirectory(
            at: historyURL,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        )

        for bundle in entries {
            var isDirectory = ObjCBool(false)
            guard FileManager.default.fileExists(atPath: bundle.path, isDirectory: &isDirectory),
                  isDirectory.boolValue else { continue }

            let manifestURL = bundle.appendingPathComponent("manifest.json")
            if FileManager.default.fileExists(atPath: manifestURL.path) {
                // Atomic manifests are either valid/current or intentionally
                // left untouched for a future/unknown schema.
                continue
            }

            let id = bundle.lastPathComponent
            guard Self.isSafePathComponent(id) else { continue }

            var streams: [String: String] = [:]
            for stream in Stream.allCases {
                if FileManager.default.fileExists(
                    atPath: bundle.appendingPathComponent(stream.filename).path
                ) {
                    streams[stream.rawValue] = stream.filename
                }
            }
            if FileManager.default.fileExists(atPath: bundle.appendingPathComponent("legacy.log").path) {
                streams["LEGACY"] = "legacy.log"
            }

            if streams.isEmpty {
                try FileManager.default.removeItem(at: bundle)
                continue
            }

            let now = formatter.string(from: Date())
            let isLegacyBundle = streams.count == 1 && streams["LEGACY"] == "legacy.log"
            let recovered = SessionRecord(
                id: id,
                startedAt: now,
                endedAt: now,
                targetProcessName: "",
                targetBundleIdentifier: "",
                targetPID: nil,
                appVersion: "unknown",
                appBuild: "unknown",
                gameVersion: nil,
                runtimeRevision: nil,
                state: .completed,
                endReason: "orphan-recovery",
                streams: streams,
                legacy: isLegacyBundle
            )
            try writeSessionRecord(recovered, to: manifestURL)
        }
    }

    private func archiveLegacyLogsLocked() throws {
        try closeAllHandlesLocked()
        try FileManager.default.createDirectory(at: historyURL, withIntermediateDirectories: true)

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
            let record = SessionRecord(
                id: id,
                startedAt: formatter.string(from: Date()),
                endedAt: formatter.string(from: Date()),
                targetProcessName: "",
                targetBundleIdentifier: "",
                targetPID: nil,
                appVersion: "unknown",
                appBuild: "unknown",
                gameVersion: nil,
                runtimeRevision: nil,
                state: .completed,
                endReason: "legacy-migration",
                streams: ["LEGACY": "legacy.log"],
                legacy: true
            )
            let bundle = sessionDirectoryURL(for: record)
            try FileManager.default.createDirectory(at: bundle, withIntermediateDirectories: true)
            try combined.write(to: bundle.appendingPathComponent("legacy.log"), options: .atomic)
            try writeSessionRecord(record)
        }

        for candidate in candidates where FileManager.default.fileExists(atPath: candidate.path) {
            try? FileManager.default.removeItem(at: candidate)
        }

        try pruneCompletedCountLocked()
        try pruneRetentionForTotalCapLocked()
    }

    private func pruneCompletedCountLocked() throws {
        let sessions = try completedSessionBundlesLocked()
        guard sessions.count > Self.maximumCompletedSessions else { return }

        for (bundle, _) in sessions.prefix(sessions.count - Self.maximumCompletedSessions) {
            try FileManager.default.removeItem(at: bundle)
        }
    }

    private func pruneRetentionForTotalCapLocked() throws {
        var total = try fileSize(hostURL)
        for (bundle, _) in try sessionBundlesLocked() {
            total += try bundleSize(bundle)
        }

        guard total > UInt64(Self.maximumTotalBytes) else { return }

        for (bundle, _) in try completedSessionBundlesLocked() {
            let bytes = try bundleSize(bundle)
            try FileManager.default.removeItem(at: bundle)
            total = total > bytes ? total - bytes : 0
            if total <= UInt64(Self.maximumTotalBytes) { break }
        }
    }

    private func sessionBundlesLocked() throws -> [(URL, SessionRecord)] {
        guard FileManager.default.fileExists(atPath: historyURL.path) else { return [] }

        let entries = try FileManager.default.contentsOfDirectory(
            at: historyURL,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        )

        return entries.compactMap { entry in
            var isDirectory = ObjCBool(false)
            guard FileManager.default.fileExists(atPath: entry.path, isDirectory: &isDirectory),
                  isDirectory.boolValue else { return nil }
            let manifest = entry.appendingPathComponent("manifest.json")
            guard let record = loadSessionRecordLocked(at: manifest),
                  Self.isSafePathComponent(record.id),
                  record.id == entry.lastPathComponent else { return nil }
            return (entry, record)
        }
        .sorted {
            sessionDate($0.1.endedAt ?? $0.1.startedAt) < sessionDate($1.1.endedAt ?? $1.1.startedAt)
        }
    }

    private func completedSessionBundlesLocked() throws -> [(URL, SessionRecord)] {
        try sessionBundlesLocked().filter { $0.1.state == .completed }
    }

    private func sessionDate(_ value: String) -> Date {
        formatter.date(from: value) ?? .distantPast
    }

    private func bundleSize(_ bundle: URL) throws -> UInt64 {
        guard let enumerator = FileManager.default.enumerator(
            at: bundle,
            includingPropertiesForKeys: [.fileSizeKey],
            options: [.skipsHiddenFiles]
        ) else {
            return 0
        }

        var total: UInt64 = 0
        for case let fileURL as URL in enumerator {
            let values = try fileURL.resourceValues(forKeys: [.fileSizeKey])
            total += UInt64(max(0, values.fileSize ?? 0))
        }
        return total
    }

    private func trimLogLocked(_ file: URL, stream: Stream, keepingBytes: Int) throws {
        try closeHandleLocked(for: stream)
        let tail = keepingBytes > 0
            ? try tailData(file, maximumBytes: keepingBytes)
            : Data()
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

    private func ensureHandle(for stream: Stream, destination: URL) throws -> FileHandle {
        if let handle = handles[stream] {
            return handle
        }

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

        let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
        handles[stream] = handle
        return handle
    }

    private func closeHandleLocked(for stream: Stream) throws {
        guard let handle = handles.removeValue(forKey: stream) else { return }
        try handle.synchronize()
        try handle.close()
    }

    private func closeAllHandlesLocked() throws {
        let streams = Array(handles.keys)
        for stream in streams {
            try closeHandleLocked(for: stream)
        }
    }

    private func sessionDirectoryURL(for record: SessionRecord) -> URL {
        historyURL.appendingPathComponent(record.id, isDirectory: true)
    }

    private func streamURL(for stream: Stream, record: SessionRecord) -> URL {
        sessionDirectoryURL(for: record).appendingPathComponent(stream.filename)
    }

    private func writeSessionRecord(_ record: SessionRecord) throws {
        try writeSessionRecord(record, to: sessionDirectoryURL(for: record).appendingPathComponent("manifest.json"))
    }

    private func writeSessionRecord(_ record: SessionRecord, to destination: URL) throws {
        guard Self.isSafePathComponent(record.id) else {
            throw NSError(
                domain: "TrainerLogSink",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "非法日志 session ID。"]
            )
        }
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(record)
        try FileManager.default.createDirectory(
            at: destination.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: destination, options: .atomic)
    }

    private func writeCurrentSessionPointerLocked(id: String) throws {
        let data = try JSONEncoder().encode(CurrentSessionPointer(id: id))
        try data.write(to: metadataURL, options: .atomic)
    }

    private func clearCurrentSessionPointerLocked() throws {
        guard FileManager.default.fileExists(atPath: metadataURL.path) else { return }
        try FileManager.default.removeItem(at: metadataURL)
    }

    private func loadCurrentSessionLocked() -> SessionRecord? {
        guard managedSessions,
              let pointerData = try? Data(contentsOf: metadataURL),
              let pointer = try? JSONDecoder().decode(CurrentSessionPointer.self, from: pointerData),
              Self.isSafePathComponent(pointer.id) else { return nil }

        let manifest = historyURL
            .appendingPathComponent(pointer.id, isDirectory: true)
            .appendingPathComponent("manifest.json")
        return loadSessionRecordLocked(at: manifest)
    }

    private func loadCurrentSessionPointerIDLocked() -> String? {
        guard let data = try? Data(contentsOf: metadataURL),
              let pointer = try? JSONDecoder().decode(CurrentSessionPointer.self, from: data),
              Self.isSafePathComponent(pointer.id) else { return nil }
        return pointer.id
    }

    private func loadSessionRecordLocked(at manifest: URL) -> SessionRecord? {
        guard let data = try? Data(contentsOf: manifest),
              let record = try? JSONDecoder().decode(SessionRecord.self, from: data),
              record.schemaVersion == SessionRecord.currentSchemaVersion else { return nil }
        return record
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

    private static func isSafePathComponent(_ value: String) -> Bool {
        !value.isEmpty &&
        value != "." &&
        value != ".." &&
        !value.contains("/") &&
        !value.contains("\\") &&
        !value.contains("\0")
    }

    private static func sessionID(date: Date) -> String {
        let stamp = ISO8601DateFormatter().string(from: date)
            .replacingOccurrences(of: ":", with: "-")
        return stamp + "-" + String(UUID().uuidString.prefix(8)).lowercased()
    }
}
