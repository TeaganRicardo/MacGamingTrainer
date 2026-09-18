import Foundation
#if canImport(Darwin)
import Darwin
#elseif canImport(Glibc)
import Glibc
#endif

/// Game-agnostic JSONL worker process. It knows nothing about any specific game or
/// trainer command schema; game modules own request semantics and state decode.
final class BackendProcess {
    private var process: Process?
    private var input: FileHandle?
    private var output: FileHandle?
    private var errorOutput: FileHandle?
    private let readQueue = DispatchQueue(label: "com.gao.macgamingtrainer.backend-process")
    private var buffer = Data()

    private let executableURL: URL
    private let argumentsPrefix: [String]
    private let maxStdoutBufferBytes: Int
    private let forceKillDelay: TimeInterval

    init(
        executableURL: URL = URL(fileURLWithPath: "/usr/bin/xcrun"),
        argumentsPrefix: [String] = ["python3", "-u"],
        maxStdoutBufferBytes: Int = 1_048_576,
        forceKillDelay: TimeInterval = 1.5
    ) {
        self.executableURL = executableURL
        self.argumentsPrefix = argumentsPrefix
        self.maxStdoutBufferBytes = max(4_096, maxStdoutBufferBytes)
        self.forceKillDelay = max(0.1, forceKillDelay)
    }

    var isRunning: Bool { process?.isRunning == true }
    var isStarted: Bool { process != nil }

    func start(
        scriptURL: URL,
        gameID: String,
        onMessage: @escaping ([String: Any]) -> Void,
        onProtocolError: @escaping (String) -> Void,
        onStderr: @escaping (String) -> Void,
        onTermination: @escaping (Int32) -> Void
    ) throws {
        guard process == nil else { return }
        readQueue.sync { buffer.removeAll(keepingCapacity: false) }

        let task = Process()
        let stdin = Pipe(), stdout = Pipe(), stderr = Pipe()
        task.executableURL = executableURL
        task.arguments = argumentsPrefix + [scriptURL.path, "--game", gameID]
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["MGT_GAME_ID"] = gameID
        task.environment = environment
        task.standardInput = stdin
        task.standardOutput = stdout
        task.standardError = stderr

        input = stdin.fileHandleForWriting
        output = stdout.fileHandleForReading
        errorOutput = stderr.fileHandleForReading

        stdout.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty else { return }
            self?.readQueue.async { [weak self] in
                self?.consume(data, onMessage: onMessage, onProtocolError: onProtocolError)
            }
        }
        stderr.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            guard let message = String(data: data, encoding: .utf8), !message.isEmpty else { return }
            DispatchQueue.main.async { onStderr(message) }
        }
        task.terminationHandler = { [weak self] task in
            let status = task.terminationStatus
            guard let owner = self else {
                DispatchQueue.main.async { onTermination(status) }
                return
            }
            DispatchQueue.main.async {
                owner.output?.readabilityHandler = nil
                owner.errorOutput?.readabilityHandler = nil
                owner.input = nil
                owner.output = nil
                owner.errorOutput = nil
                owner.process = nil
                owner.readQueue.async { owner.buffer.removeAll(keepingCapacity: false) }
                onTermination(status)
            }
        }

        do {
            try task.run()
            process = task
        } catch {
            stdout.fileHandleForReading.readabilityHandler = nil
            stderr.fileHandleForReading.readabilityHandler = nil
            try? stdin.fileHandleForWriting.close()
            input = nil
            output = nil
            errorOutput = nil
            process = nil
            throw error
        }
    }

    func send(_ object: [String: Any]) throws {
        guard let input, process?.isRunning == true else {
            throw NSError(domain: "BackendProcess", code: 1, userInfo: [NSLocalizedDescriptionKey: "后端进程未运行。"])
        }
        var data = try JSONSerialization.data(withJSONObject: object)
        data.append(10)
        try input.write(contentsOf: data)
    }

    /// Gracefully terminates the worker and escalates to SIGKILL if it ignores
    /// termination. The Process instance remains owned until terminationHandler
    /// runs, preventing a new backend from racing the old one.
    func stop() {
        let task = process
        try? input?.close()
        output?.readabilityHandler = nil
        errorOutput?.readabilityHandler = nil
        guard let task, task.isRunning else { return }

        task.terminate()
        let pid = task.processIdentifier
        let delay = forceKillDelay
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + delay) {
            guard task.isRunning else { return }
            #if canImport(Darwin) || canImport(Glibc)
            _ = kill(pid, SIGKILL)
            #endif
        }
    }

    private func consume(
        _ data: Data,
        onMessage: @escaping ([String: Any]) -> Void,
        onProtocolError: @escaping (String) -> Void
    ) {
        buffer.append(data)

        // Parse every complete JSONL line first, then discard the consumed
        // prefix once. Removing from the front for every line turns a burst of
        // replies into repeated O(n) Data shifts. This keeps the same message
        // delivery semantics while making stdout handling linear in burst size.
        var cursor = buffer.startIndex
        while cursor < buffer.endIndex,
              let newline = buffer[cursor...].firstIndex(of: 10) {
            let line = Data(buffer[cursor..<newline])
            cursor = buffer.index(after: newline)
            guard !line.isEmpty else { continue }
            guard line.count <= maxStdoutBufferBytes else {
                reportProtocolError("后端 stdout 单行超过 \(maxStdoutBufferBytes) bytes。", callback: onProtocolError)
                continue
            }
            do {
                guard let object = try JSONSerialization.jsonObject(with: line) as? [String: Any] else {
                    reportProtocolError("后端 stdout 包含非对象 JSON。", callback: onProtocolError)
                    continue
                }
                DispatchQueue.main.async { onMessage(object) }
            } catch {
                reportProtocolError("后端 stdout 包含无效 JSON：\(error.localizedDescription)", callback: onProtocolError)
            }
        }
        if cursor > buffer.startIndex {
            buffer.removeSubrange(buffer.startIndex..<cursor)
        }

        if buffer.count > maxStdoutBufferBytes {
            buffer.removeAll(keepingCapacity: false)
            reportProtocolError("后端 stdout 缓冲区超过 \(maxStdoutBufferBytes) bytes 且没有换行。", callback: onProtocolError)
        }
    }

    private func reportProtocolError(_ message: String, callback: @escaping (String) -> Void) {
        DispatchQueue.main.async { callback(message) }
    }
}
