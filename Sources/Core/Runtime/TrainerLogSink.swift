import Foundation

/// Shared append-only trainer log writer. Keeping one FileHandle on a serial
/// utility queue avoids reopening and seeking the log file for every backend
/// request while preserving line ordering across game modules.
final class TrainerLogSink {
    let url: URL

    private let queue = DispatchQueue(label: "com.gao.macgamingtrainer.log", qos: .utility)
    private let formatter = ISO8601DateFormatter()
    private var handle: FileHandle?

    init(url: URL? = nil) {
        self.url = url ?? FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/MacGamingTrainer/trainer.log")
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
                let handle = try self.ensureHandle()
                let text = "\(self.formatter.string(from: Date())) \(source) \(line)\n"
                if let data = text.data(using: .utf8) {
                    try handle.write(contentsOf: data)
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

    private func ensureHandle() throws -> FileHandle {
        if let handle { return handle }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        let newHandle = try FileHandle(forWritingTo: url)
        _ = try newHandle.seekToEnd()
        handle = newHandle
        return newHandle
    }
}
