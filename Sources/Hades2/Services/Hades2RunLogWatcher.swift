import Darwin
import Foundation

enum Hades2RunLogEvent: Equatable {
    case mainMenu
    case runtimeReset
    case runtimeReady
}

/// Hades-specific lifecycle signal. It watches the game's own log writes
/// instead of polling the process or crossing an LLDB boundary on a timer.
final class Hades2RunLogWatcher {
    private let queue = DispatchQueue(label: "MacGamingTrainer.Hades2RunLogWatcher", qos: .utility)
    private let directoryURL: URL
    private let logURL: URL
    private let onEvent: (Hades2RunLogEvent) -> Void

    private var directorySource: DispatchSourceFileSystemObject?
    private var fileSource: DispatchSourceFileSystemObject?
    private var fileIdentity: UInt64?
    private var offset: UInt64 = 0
    private var lineBuffer = Data()
    private var runtimeResetPending = false

    init(onEvent: @escaping (Hades2RunLogEvent) -> Void) {
        let support = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Supergiant Games/Hades II", isDirectory: true)
        directoryURL = support
        logURL = support.appendingPathComponent("Hades II.log")
        self.onEvent = onEvent
    }

    func start() {
        queue.async { [weak self] in self?.startLocked() }
    }

    func stop() {
        queue.async { [weak self] in self?.stopLocked() }
    }

    private func startLocked() {
        guard directorySource == nil,
              FileManager.default.fileExists(atPath: directoryURL.path) else { return }

        primeCursorToEnd()
        installDirectorySourceLocked()
        installFileSourceLocked(readExisting: false)
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
        next.setEventHandler { [weak self, weak next] in
            guard let self, let next else { return }
            let data = next.data
            if data.contains(.rename) || data.contains(.delete) {
                self.stopLocked()
                self.startLocked()
                return
            }

            guard let metadata = self.metadata() else { return }
            if self.fileSource == nil || self.fileIdentity != metadata.identity {
                self.fileSource?.cancel()
                self.fileSource = nil
                self.fileIdentity = metadata.identity
                self.offset = 0
                self.lineBuffer.removeAll(keepingCapacity: false)
                self.runtimeResetPending = false
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
        next.setEventHandler { [weak self, weak next] in
            guard let self, let next else { return }
            let data = next.data
            if data.contains(.rename) || data.contains(.delete) || data.contains(.revoke) {
                self.fileSource?.cancel()
                self.fileSource = nil
                self.fileIdentity = nil
                self.offset = 0
                self.lineBuffer.removeAll(keepingCapacity: false)
                self.runtimeResetPending = false

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
        fileSource?.cancel()
        fileSource = nil
        directorySource?.cancel()
        directorySource = nil
        fileIdentity = nil
        offset = 0
        lineBuffer.removeAll(keepingCapacity: false)
        runtimeResetPending = false
    }

    private func metadata() -> (identity: UInt64?, size: UInt64)? {
        guard let attributes = try? FileManager.default.attributesOfItem(atPath: logURL.path),
              let size = (attributes[.size] as? NSNumber)?.uint64Value else { return nil }
        let identity = (attributes[.systemFileNumber] as? NSNumber)?.uint64Value
        return (identity, size)
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
            runtimeResetPending = false
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
        var events: [Hades2RunLogEvent] = []
        while let newline = lineBuffer.firstIndex(of: 0x0A) {
            let line = String(decoding: lineBuffer[..<newline], as: UTF8.self)
            lineBuffer.removeSubrange(...newline)

            if line.contains("Loading package: MainMenu.pkg") {
                events.append(.mainMenu)
                continue
            }
            if line.contains("App.Reset Start") || line.contains("Lua interface destroyed") {
                if !runtimeResetPending {
                    runtimeResetPending = true
                    events.append(.runtimeReset)
                }
                continue
            }
            if runtimeResetPending && line.contains("Finished loadScreen onExit") {
                runtimeResetPending = false
                events.append(.runtimeReady)
            }
        }
        guard !events.isEmpty else { return }
        DispatchQueue.main.async { [onEvent] in
            for event in events { onEvent(event) }
        }
    }
}
