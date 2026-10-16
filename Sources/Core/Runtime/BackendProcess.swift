import Foundation
#if canImport(Darwin)
import Darwin
#elseif canImport(Glibc)
import Glibc
#endif

/// Body-free opt-in records carried by the existing diagnostic callback.
/// Local intervals can overlap; they do not measure view rendering or FPS.
struct BackendOperationProfile {
    static let enabled = ProcessInfo.processInfo.environment["MGT_PROFILE_OPERATIONS"] == "1"
    static func now() -> TimeInterval { ProcessInfo.processInfo.systemUptime }
    static func emit(_ phase: String, id: String, command: String = "", seconds: @autoclosure () -> TimeInterval,
                     bytes: Int? = nil, log: ((String) -> Void)?) {
        guard enabled, let log else { return }
        var record: [String: Any] = ["schema": 1, "component": "host", "phase": phase,
            "request_id": id, "command": command, "seconds": seconds()]
        if let bytes { record["reply_bytes"] = bytes }
        guard let data = try? JSONSerialization.data(withJSONObject: record, options: [.sortedKeys]),
              let text = String(data: data, encoding: .utf8) else { return }
        log("OperationProfile " + text)
    }
}

/// Game-agnostic JSONL worker process. It knows nothing about any specific game or
/// trainer command schema; game modules own request semantics and state decode.
final class BackendProcess {
    private var process: Process?
    private var input: FileHandle?
    private var output: FileHandle?
    private var errorOutput: FileHandle?
    private let readQueue = DispatchQueue(label: "com.gao.macgamingtrainer.backend-process")
    private var buffer = Data()
    private var stderrBuffer = Data()
    private var stderrDroppedBytes = 0
    private var stderrDeliveryScheduled = false
    private var stderrHandlerEnabled = false
    private var stderrCallback: ((String) -> Void)?
    private var profileLog: ((String) -> Void)?

    private let executableURL: URL
    private let argumentsPrefix: [String]
    private let maxStdoutBufferBytes: Int
    private let maxStderrBufferBytes: Int
    private let forceKillDelay: TimeInterval

    private static var bundledPythonExecutableURL: URL {
        guard let resources = Bundle.main.resourceURL else {
            preconditionFailure("Application resources are unavailable.")
        }
        #if arch(arm64)
        let architecture = "arm64"
        #elseif arch(x86_64)
        let architecture = "x86_64"
        #else
        preconditionFailure("Unsupported architecture for bundled Python runtime.")
        #endif
        return resources
            .appendingPathComponent("Python", isDirectory: true)
            .appendingPathComponent(architecture, isDirectory: true)
            .appendingPathComponent("bin", isDirectory: true)
            .appendingPathComponent("python3", isDirectory: false)
    }

    init(
        executableURL: URL? = nil,
        argumentsPrefix: [String] = ["-u"],
        maxStdoutBufferBytes: Int = 1_048_576,
        maxStderrBufferBytes: Int = 65_536,
        forceKillDelay: TimeInterval = 1.5
    ) {
        self.executableURL = executableURL ?? Self.bundledPythonExecutableURL
        self.argumentsPrefix = argumentsPrefix
        self.maxStdoutBufferBytes = max(4_096, maxStdoutBufferBytes)
        self.maxStderrBufferBytes = max(4_096, maxStderrBufferBytes)
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
        onTermination: @escaping (Int32) -> Void,
        onProfile: ((String) -> Void)? = nil
    ) throws {
        guard process == nil else { return }
        profileLog = onProfile
        stderrCallback = onStderr
        readQueue.sync {
            buffer.removeAll(keepingCapacity: false)
            stderrBuffer.removeAll(keepingCapacity: false)
            stderrDroppedBytes = 0
            stderrDeliveryScheduled = false
            stderrHandlerEnabled = true
        }

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
        stderr.fileHandleForReading.readabilityHandler = { [weak self] handle in
            self?.readQueue.async { [weak self] in
                guard let self, self.stderrHandlerEnabled else { return }
                let data = handle.availableData
                guard !data.isEmpty else { return }
                self.enqueueStderrLocked(data)
            }
        }
        task.terminationHandler = { [weak self] task in
            let status = task.terminationStatus
            guard let owner = self else {
                DispatchQueue.main.async { onTermination(status) }
                return
            }
            DispatchQueue.main.async {
                owner.flushStderr { message in
                    onStderr(message)
                }
                owner.output?.readabilityHandler = nil
                owner.errorOutput?.readabilityHandler = nil
                owner.input = nil
                owner.output = nil
                owner.errorOutput = nil
                owner.stderrCallback = nil
                owner.process = nil
                owner.readQueue.sync {
                    owner.buffer.removeAll(keepingCapacity: false)
                    owner.stderrBuffer.removeAll(keepingCapacity: false)
                    owner.stderrDroppedBytes = 0
                    owner.stderrDeliveryScheduled = false
                    owner.stderrHandlerEnabled = false
                }
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
            stderrCallback = nil
            readQueue.sync {
                stderrBuffer.removeAll(keepingCapacity: false)
                stderrDroppedBytes = 0
                stderrDeliveryScheduled = false
                stderrHandlerEnabled = false
            }
            process = nil
            throw error
        }
    }

    /// Deliver all stderr already read or available from the worker without
    /// blocking on an empty pipe. Normal stderr delivery is coalesced and bounded
    /// so a burst cannot enqueue an unbounded number of main-thread callbacks.
    func flushStderr(_ onMessage: @escaping (String) -> Void) {
        guard let handle = errorOutput else { return }
        handle.readabilityHandler = nil
        readQueue.sync {
            stderrHandlerEnabled = false
            drainStderrPipeLocked(handle)
        }

        let message = readQueue.sync {
            takeStderrBufferLocked()
        }
        if let message {
            onMessage(message)
        }

        readQueue.sync {
            stderrHandlerEnabled = true
        }
        handle.readabilityHandler = { [weak self] handle in
            self?.readQueue.async { [weak self] in
                guard let self, self.stderrHandlerEnabled else { return }
                let data = handle.availableData
                guard !data.isEmpty else { return }
                self.enqueueStderrLocked(data)
            }
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
        readQueue.sync { stderrHandlerEnabled = false }
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

    private func enqueueStderrLocked(_ data: Data) {
        guard !data.isEmpty else { return }
        let remaining = max(0, maxStderrBufferBytes - stderrBuffer.count)
        if remaining > 0 {
            stderrBuffer.append(data.prefix(remaining))
        }
        if data.count > remaining {
            stderrDroppedBytes = min(Int.max - (data.count - remaining), stderrDroppedBytes) + (data.count - remaining)
        }
        if !stderrDeliveryScheduled {
            stderrDeliveryScheduled = true
            DispatchQueue.main.async { [weak self] in
                self?.deliverStderr()
            }
        }
    }

    private func deliverStderr() {
        let message = readQueue.sync {
            takeStderrBufferLocked()
        }
        guard let message else { return }
        stderrCallback?(message)
    }

    private func takeStderrBufferLocked() -> String? {
        guard !stderrBuffer.isEmpty || stderrDroppedBytes > 0 else {
            stderrDeliveryScheduled = false
            return nil
        }
        var message = String(decoding: stderrBuffer, as: UTF8.self)
        if stderrDroppedBytes > 0 {
            if !message.isEmpty {
                message += "\n"
            }
            message += "[Trainer] stderr overflow droppedBytes=\(stderrDroppedBytes)"
        }
        stderrBuffer.removeAll(keepingCapacity: true)
        stderrDroppedBytes = 0
        stderrDeliveryScheduled = false
        return message.isEmpty ? nil : message
    }

    private func drainStderrPipeLocked(_ handle: FileHandle) {
        while true {
            #if canImport(Darwin) || canImport(Glibc)
            var descriptor = pollfd(
                fd: handle.fileDescriptor,
                events: Int16(POLLIN | POLLHUP),
                revents: 0
            )
            guard poll(&descriptor, 1, 0) > 0 else { break }
            #endif
            let data = handle.availableData
            guard !data.isEmpty else { break }
            enqueueStderrLocked(data)
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
                let decodeStarted = BackendOperationProfile.enabled ? BackendOperationProfile.now() : 0
                guard let object = try JSONSerialization.jsonObject(with: line) as? [String: Any] else {
                    reportProtocolError("后端 stdout 包含非对象 JSON。", callback: onProtocolError)
                    continue
                }
                let decodedAt = BackendOperationProfile.enabled ? BackendOperationProfile.now() : 0
                let log = profileLog
                DispatchQueue.main.async {
                    if BackendOperationProfile.enabled, let id = object["id"] as? String {
                        BackendOperationProfile.emit("host.payload_decode", id: id,
                            seconds: decodedAt - decodeStarted, bytes: line.count + 1, log: log)
                        BackendOperationProfile.emit("host.reply_delivery_queue", id: id,
                            seconds: BackendOperationProfile.now() - decodedAt, log: log)
                    }
                    onMessage(object)
                }
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
