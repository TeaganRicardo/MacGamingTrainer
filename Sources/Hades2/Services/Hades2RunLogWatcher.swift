import Darwin
import Foundation

/// Hades-specific readiness signal. It watches the game's own log directory
/// instead of polling the process or crossing an LLDB boundary on a timer.
final class Hades2RunLogWatcher {
    private let queue = DispatchQueue(label: "MacGamingTrainer.Hades2RunLogWatcher", qos: .utility)
    private let directoryURL: URL
    private let logURL: URL
    private let onReadySignal: () -> Void

    private var source: DispatchSourceFileSystemObject?
    private var fileIdentity: UInt64?
    private var offset: UInt64 = 0
    private var lineBuffer = Data()

    init(onReadySignal: @escaping () -> Void) {
        let support = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Supergiant Games/Hades II", isDirectory: true)
        directoryURL = support
        logURL = support.appendingPathComponent("Hades II.log")
        self.onReadySignal = onReadySignal
    }

    func start() {
        queue.async { [weak self] in self?.startLocked() }
    }

    func stop() {
        queue.async { [weak self] in self?.stopLocked() }
    }

    private func startLocked() {
        guard source == nil,
              FileManager.default.fileExists(atPath: directoryURL.path) else { return }

        primeCursorToEnd()
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
            self.readNewContentLocked()
        }
        next.setCancelHandler { close(fd) }
        source = next
        next.resume()
    }

    private func stopLocked() {
        source?.cancel()
        source = nil
        lineBuffer.removeAll(keepingCapacity: false)
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
        var foundSignal = false
        while let newline = lineBuffer.firstIndex(of: 0x0A) {
            let line = String(decoding: lineBuffer[..<newline], as: UTF8.self)
            lineBuffer.removeSubrange(...newline)
            if line.contains("World::Begin()") || line.contains("Finished loadScreen onExit") {
                foundSignal = true
            }
        }
        guard foundSignal else { return }
        DispatchQueue.main.async { [onReadySignal] in onReadySignal() }
    }
}
