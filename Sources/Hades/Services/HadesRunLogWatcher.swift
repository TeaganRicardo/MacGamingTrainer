import Darwin
import Foundation

enum HadesRunLogEvent: Equatable {
    case bootReady
    case mainMenu
    case runtimeReset
    case roomTransitionStarted
    case roomLoaded
}

/// Hades I lifecycle watcher over `Hades.log` (never polls the game process).
final class HadesRunLogWatcher {
    private let queue = DispatchQueue(label: "MacGamingTrainer.HadesRunLogWatcher", qos: .utility)
    private let directoryURL: URL
    private let logURL: URL
    private let deliver: (@escaping () -> Void) -> Void
    private var deliveryEpoch = UUID()
    private var sourceEpoch = UUID()
    private var directorySourceID = UUID()
    private var fileSourceID = UUID()
    private let onEvent: (HadesRunLogEvent) -> Void

    private var directorySource: DispatchSourceFileSystemObject?
    private var fileSource: DispatchSourceFileSystemObject?
    private struct Cursor {
        let identity: UInt64?
        let size: UInt64
    }

    private var waitingForTarget = false
    private var idleCursor: Cursor?
    private var fileIdentity: UInt64?
    private var offset: UInt64 = 0
    private var lineBuffer = Data()
    private var bootReadyEmitted = false
    private var runtimeResetPending = false
    private var roomLoadPending = false
    private var shuttingDown = false

    init(
        directoryURL: URL? = nil,
        deliver: @escaping (@escaping () -> Void) -> Void = { DispatchQueue.main.async(execute: $0) },
        onEvent: @escaping (HadesRunLogEvent) -> Void
    ) {
        let support = directoryURL ?? FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Supergiant Games/Hades", isDirectory: true)
        self.directoryURL = support
        self.logURL = support.appendingPathComponent("Hades.log")
        self.deliver = deliver
        self.onEvent = onEvent
    }

    deinit {
        let existingFile = fileSource
        let existingDir = directorySource
        fileSource = nil
        directorySource = nil
        queue.async {
            existingFile?.cancel()
            existingDir?.cancel()
        }
    }

    var canObserveLifecycle: Bool {
        FileManager.default.fileExists(atPath: directoryURL.path)
    }

    func start() {
        let epoch = deliveryEpoch
        queue.async { [weak self] in
            guard let self else { return }
            self.sourceEpoch = epoch
            self.startLocked()
        }
    }

    func stop() {
        deliveryEpoch = UUID()
        queue.async { [weak self] in self?.stopLocked() }
    }

    /// Host process replacement retires queued delivery before a new cursor is installed.
    func targetLifetimeChanged(running: Bool) {
        deliveryEpoch = UUID()
        let epoch = deliveryEpoch
        queue.sync {
            stopLocked()
            sourceEpoch = epoch
            if running {
                let catchUp = waitingForTarget
                waitingForTarget = false
                startLocked(catchUp: catchUp)
                idleCursor = nil
            } else {
                waitingForTarget = true
                idleCursor = metadata()
            }
        }
    }

    private func resetParserFlagsLocked() {
        bootReadyEmitted = false
        runtimeResetPending = false
        roomLoadPending = false
        shuttingDown = false
    }

    private func startLocked(catchUp: Bool = false) {
        guard !waitingForTarget, directorySource == nil,
              FileManager.default.fileExists(atPath: directoryURL.path) else { return }

        if catchUp, let current = metadata() {
            // Read bytes written after the last observed exit or absence.
            // A replaced or truncated log starts at byte zero.
            fileIdentity = current.identity
            if let idleCursor, current.identity == idleCursor.identity, current.size >= idleCursor.size {
                offset = idleCursor.size
            }
        } else {
            primeCursorToEnd()
        }
        installDirectorySourceLocked()
        installFileSourceLocked(readExisting: catchUp)
    }

    private func installDirectorySourceLocked() {
        guard directorySource == nil else { return }
        let fd = open(directoryURL.path, O_EVTONLY)
        guard fd >= 0 else { return }

        let next = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: fd,
            eventMask: [.write, .rename, .delete],
            queue: queue
        )
        directorySourceID = UUID()
        let identifier = directorySourceID
        let epoch = sourceEpoch
        next.setEventHandler { [weak self, weak next] in
            guard let self, let next, self.directorySourceID == identifier, self.sourceEpoch == epoch else { return }
            let data = next.data
            if data.contains(.rename) || data.contains(.delete) {
                self.stopLocked()
                self.startLocked()
                return
            }

            guard let metadata = self.metadata() else { return }
            if self.fileSource == nil || self.fileIdentity != metadata.identity {
                self.fileSourceID = UUID()
                self.fileSource?.cancel()
                self.fileSource = nil
                self.fileIdentity = metadata.identity
                self.offset = 0
                self.lineBuffer.removeAll(keepingCapacity: false)
                self.resetParserFlagsLocked()
                self.installFileSourceLocked(readExisting: true)
            }
        }
        next.setCancelHandler { close(fd) }
        directorySource = next
        next.resume()
    }

    private func installFileSourceLocked(readExisting: Bool) {
        guard fileSource == nil, let metadata = metadata() else { return }

        if fileIdentity != metadata.identity {
            fileIdentity = metadata.identity
            offset = readExisting ? 0 : metadata.size
            lineBuffer.removeAll(keepingCapacity: false)
        }

        let fd = open(logURL.path, O_EVTONLY)
        guard fd >= 0 else { return }

        let next = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: fd,
            eventMask: [.write, .rename, .delete, .revoke],
            queue: queue
        )
        fileSourceID = UUID()
        let identifier = fileSourceID
        let epoch = sourceEpoch
        next.setEventHandler { [weak self, weak next] in
            guard let self, let next, self.fileSourceID == identifier, self.sourceEpoch == epoch else { return }
            let data = next.data
            if data.contains(.rename) || data.contains(.delete) || data.contains(.revoke) {
                self.fileSourceID = UUID()
                self.fileSource?.cancel()
                self.fileSource = nil
                self.fileIdentity = nil
                self.offset = 0
                self.lineBuffer.removeAll(keepingCapacity: false)
                self.resetParserFlagsLocked()

                if self.metadata() != nil {
                    self.installFileSourceLocked(readExisting: true)
                }
                return
            }
            self.readNewContentLocked()
        }
        next.setCancelHandler { close(fd) }
        fileSource = next
        next.resume()

        if readExisting {
            readNewContentLocked()
        }
    }

    private func stopLocked() {
        fileSourceID = UUID()
        directorySourceID = UUID()
        fileSource?.cancel()
        fileSource = nil
        directorySource?.cancel()
        directorySource = nil
        fileIdentity = nil
        offset = 0
        lineBuffer.removeAll(keepingCapacity: false)
        resetParserFlagsLocked()
    }

    private func metadata() -> Cursor? {
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: logURL.path),
              let size = (attributes[.size] as? NSNumber)?.uint64Value else { return nil }
        let identity = (attributes[.systemFileNumber] as? NSNumber)?.uint64Value
        return Cursor(identity: identity, size: size)
    }

    private func primeCursorToEnd() {
        lineBuffer.removeAll(keepingCapacity: false)
        guard let metadata = metadata() else {
            fileIdentity = nil
            offset = 0
            return
        }
        fileIdentity = metadata.identity
        offset = metadata.size
    }

    private func readNewContentLocked() {
        guard let metadata = metadata() else { return }
        if fileIdentity != metadata.identity || metadata.size < offset {
            fileIdentity = metadata.identity
            offset = 0
            lineBuffer.removeAll(keepingCapacity: false)
            resetParserFlagsLocked()
        }
        guard metadata.size > offset,
              let handle = try? FileHandle(forReadingFrom: logURL) else { return }

        defer { try? handle.close() }
        do {
            try handle.seek(toOffset: offset)
            let count = Int(min(metadata.size - offset, UInt64(Int.max)))
            guard count > 0, let data = try handle.read(upToCount: count), !data.isEmpty else { return }
            offset += UInt64(data.count)
            consumeLines(data)
        } catch {
            return
        }
    }

    private func consumeLines(_ data: Data) {
        lineBuffer.append(data)
        var events: [HadesRunLogEvent] = []
        while let newline = lineBuffer.firstIndex(of: 0x0A) {
            var line = String(decoding: lineBuffer[..<newline], as: UTF8.self)
            lineBuffer.removeSubrange(...newline)
            if line.hasSuffix("\r") { line.removeLast() }

            if line.contains("App.cpp:") && line.contains("Shutting down") {
                shuttingDown = true
                runtimeResetPending = false
                roomLoadPending = false
                continue
            }
            guard !shuttingDown else { continue }

            if line.contains("App.Reset Start") || line.contains("Lua interface destroyed") {
                if !runtimeResetPending {
                    runtimeResetPending = true
                    events.append(.runtimeReset)
                }
                continue
            }
            if line.contains("Launch took ") || line.contains("Done with boot load") {
                runtimeResetPending = false
                if !bootReadyEmitted {
                    bootReadyEmitted = true
                    events.append(.bootReady)
                }
                continue
            }
            if line.contains("MainMenuScreen.sjson") {
                roomLoadPending = false
                runtimeResetPending = false
                events.append(.mainMenu)
                continue
            }
            if line.contains("World::Begin()") {
                roomLoadPending = true
                events.append(.roomTransitionStarted)
                continue
            }
            if (runtimeResetPending || roomLoadPending)
                && (line.contains("end of postLoadTask") || line.contains("Finished PostLaod")) {
                runtimeResetPending = false
                roomLoadPending = false
                events.append(.roomLoaded)
            }
        }
        guard !events.isEmpty else { return }
        let epoch = sourceEpoch
        deliver { [weak self] in
            guard let self, self.deliveryEpoch == epoch else { return }
            for event in events {
                guard self.deliveryEpoch == epoch else { return }
                self.onEvent(event)
            }
        }
    }
}
