import Darwin
import Foundation

/// Shared append-only trainer log writer. Keeping one FileHandle on a serial
/// utility queue avoids reopening and seeking the log file for every backend
/// request while preserving line ordering across game modules.
final class TrainerLogSink {
    static let maximumFileSize = 1_048_576

    let url: URL

    private let queue = DispatchQueue(label: "com.gao.macgamingtrainer.log", qos: .utility)
    private let formatter = ISO8601DateFormatter()
    private var handle: FileHandle?

    init(url: URL) {
        self.url = url
    }

    init(gameID: String, homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser) {
        self.url = Self.moduleLogURL(gameID: gameID, homeDirectory: homeDirectory)
    }

    static func moduleLogURL(gameID: String, homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser) -> URL {
        homeDirectory
            .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
            .appendingPathComponent(gameID, isDirectory: true)
            .appendingPathComponent("trainer.log")
    }

    deinit {
        // Async append blocks capture self weakly. If the final strong reference
        // is released by a block already executing on `queue`, synchronously
        // re-entering the same serial queue here would deadlock. At deinit there
        // can be no other strong owner, so closing the current handle directly
        // is the safe terminal action; queued weak blocks simply observe nil.
        try? handle?.synchronize()
        try? handle?.close()
        handle = nil
    }

    func append(_ line: String, source: String = "GUI") {
        guard !line.isEmpty else { return }
        queue.async { [weak self] in
            guard let self else { return }
            do {
                let text = "\(self.formatter.string(from: Date())) \(source) \(line)\n"
                if let data = text.data(using: .utf8) {
                    let writeLimit = Self.maximumFileSize - 1
                    var bytesToWrite = data
                    if data.count > writeLimit {
                        var start = data.count - writeLimit
                        while start < data.count && (data[start] & 0xC0) == 0x80 {
                            start += 1
                        }
                        bytesToWrite = Data(data[start...])
                    }
                    var handle = try self.ensureHandle()
                    let fileAttributes = try? FileManager.default.attributesOfItem(atPath: self.url.path)
                    let externalFileSize = (fileAttributes?[.size] as? NSNumber)?.uint64Value ?? handle.offsetInFile
                    let currentFileSize = max(handle.offsetInFile, externalFileSize)
                    if currentFileSize + UInt64(bytesToWrite.count) > UInt64(Self.maximumFileSize) {
                        try self.rotateLogs(closing: handle)
                        handle = try self.ensureHandle()
                    }
                    try handle.write(contentsOf: bytesToWrite)
                }
            } catch {
                // Logging must never take down the trainer or interfere with a
                // debugger boundary. There is intentionally no recursive log.
            }
        }
    }

    func flush() {
        queue.sync { try? handle?.synchronize() }
    }

    private func rotateLogs(closing oldHandle: FileHandle) throws {
        try oldHandle.synchronize()
        try oldHandle.close()
        handle = nil

        for index in stride(from: 3, through: 1, by: -1) {
            let source = index == 1 ? url : url.appendingPathExtension("\(index - 1)")
            let destination = url.appendingPathExtension("\(index)")
            if FileManager.default.fileExists(atPath: destination.path) {
                try FileManager.default.removeItem(at: destination)
            }
            if FileManager.default.fileExists(atPath: source.path) {
                try FileManager.default.moveItem(at: source, to: destination)
            }
        }
        _ = FileManager.default.createFile(atPath: url.path, contents: nil)
        handle = try ensureHandle()
    }

    private func ensureHandle() throws -> FileHandle {
        if let handle { return handle }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        let fd = open(url.path, O_WRONLY | O_APPEND)
        guard fd >= 0 else {
            throw NSError(
                domain: NSPOSIXErrorDomain,
                code: Int(errno),
                userInfo: [NSLocalizedDescriptionKey: "无法以追加模式打开日志。"]
            )
        }
        let newHandle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
        handle = newHandle
        return newHandle
    }
}
