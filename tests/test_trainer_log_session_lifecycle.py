import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required for TrainerLogSink test")

main_source = r"""
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func fileSize(_ url: URL) -> Int {
    guard let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
          let size = attributes[.size] as? NSNumber else {
        return 0
    }
    return size.intValue
}

func completedLogs(_ url: URL) -> [URL] {
    ((try? FileManager.default.contentsOfDirectory(at: url, includingPropertiesForKeys: nil)) ?? [])
        .filter { $0.pathExtension == "log" }
}

guard CommandLine.arguments.count == 2 else { fail("temporary home required") }
let home = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let gameDirectory = home
    .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
    .appendingPathComponent("hades2", isDirectory: true)
let current = gameDirectory.appendingPathComponent("trainer.log")
let host = gameDirectory.appendingPathComponent("trainer-host.log")
let history = gameDirectory.appendingPathComponent("sessions", isDirectory: true)
let metadata = gameDirectory.appendingPathComponent("current-session.json")
let nativeLog = home.appendingPathComponent("Library/Application Support/Supergiant Games/Hades II/Hades II.log")
try FileManager.default.createDirectory(at: nativeLog.deletingLastPathComponent(), withIntermediateDirectories: true)
try Data("native game log must survive\n".utf8).write(to: nativeLog)

guard TrainerLogSink.moduleLogURL(gameID: "hades2", homeDirectory: home) == current else {
    fail("module log path lost per-game scoping")
}

// Before a target lifetime exists, diagnostics belong to bounded Host context.
do {
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: home)
    sink.append("host-before-target")
    sink.append(String(repeating: "h", count: 1_200_000))
    sink.flush()
    if sink.currentLogURL() != host { fail("pre-target log did not resolve to Host context") }
    if fileSize(host) > TrainerLogSink.maximumHostFileSize { fail("Host context exceeded its cap") }
    if FileManager.default.fileExists(atPath: current.path) { fail("Host context created a fake target session") }
}

// First app instance begins the target lifetime.
do {
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: home)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(processName: "Hades II", bundleIdentifier: "com.supergiantgames.hades2", processIdentifier: 1001)
    )
    sink.updateCurrentSessionRuntimeIdentity(gameVersion: "1.143476", runtimeRevision: 112)
    sink.append("host-in-session", source: "HOST")
    sink.append("backend-in-session", source: "BACKEND")
    sink.flush()
    if sink.currentLogURL() != current { fail("active target did not own current session log") }
    let text = (try? String(contentsOf: current, encoding: .utf8)) ?? ""
    if !text.contains("HOST host-in-session") || !text.contains("BACKEND backend-in-session") {
        fail("source-tagged records missing from current session")
    }
    if !FileManager.default.fileExists(atPath: metadata.path) { fail("current session metadata missing") }
    let identity = try JSONSerialization.jsonObject(with: Data(contentsOf: metadata)) as? [String: Any]
    if identity?["targetProcessName"] as? String != "Hades II" { fail("target process identity missing") }
    if identity?["targetBundleIdentifier"] as? String != "com.supergiantgames.hades2" { fail("target bundle identity missing") }
    if identity?["gameVersion"] as? String != "1.143476" { fail("game version identity missing") }
    if identity?["runtimeRevision"] as? Int != 112 { fail("resident revision identity missing") }
    if identity?["appVersion"] == nil || identity?["appBuild"] == nil { fail("Host build identity missing") }
}

// A Trainer restart while the same target PID lives resumes, rather than
// manufacturing a second game session.
do {
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: home)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(processName: "Hades II", bundleIdentifier: "com.supergiantgames.hades2", processIdentifier: 1001)
    )
    sink.append("after-host-restart", source: "HOST")
    sink.append(String(repeating: "b", count: 4_800_000), source: "BACKEND")
    sink.flush()
    if completedLogs(history).count != 0 { fail("same target PID was split into multiple sessions") }
    if fileSize(current) > TrainerLogSink.maximumSessionFileSize {
        fail("backend-originated traffic escaped the per-session cap")
    }
    let boundedText = (try? String(contentsOf: current, encoding: .utf8)) ?? ""
    if !boundedText.contains("BACKEND ") {
        fail("bounded backend record lost its source tag")
    }

    // A definitive replacement PID closes the old target lifetime even if the
    // termination notification was hidden by rapid replacement.
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(processName: "Hades II", bundleIdentifier: "com.supergiantgames.hades2", processIdentifier: 1002)
    )
    sink.append("replacement-process", source: "HOST")
    sink.flush()
    if completedLogs(history).count != 1 { fail("replacement PID did not close the previous session") }
    let metadataObject = try JSONSerialization.jsonObject(with: Data(contentsOf: metadata)) as? [String: Any]
    if metadataObject?["targetPID"] as? Int != 1002 { fail("current session metadata lost target PID") }

    sink.targetLifetimeChanged(
        running: false,
        identity: .init(processName: "Hades II", bundleIdentifier: "com.supergiantgames.hades2", processIdentifier: nil)
    )
}
if FileManager.default.fileExists(atPath: metadata.path) { fail("ended session metadata remained current") }

// Produce enough completed sessions to exercise both count and hard total
// retention. Each target lifetime remains independently bounded.
do {
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: home)
    for index in 0..<10 {
        sink.targetLifetimeChanged(
            running: true,
            identity: .init(
                processName: "Hades II",
                bundleIdentifier: "com.supergiantgames.hades2",
                processIdentifier: Int32(2000 + index)
            )
        )
        sink.append("bulk-\(index) " + String(repeating: "x", count: 3_900_000), source: "BACKEND")
        sink.flush()
        sink.targetLifetimeChanged(
            running: false,
            identity: .init(processName: "Hades II", bundleIdentifier: "com.supergiantgames.hades2", processIdentifier: nil)
        )
    }
    let retained = completedLogs(history)
    if retained.count > TrainerLogSink.maximumCompletedSessions {
        fail("retained more than eight completed target sessions")
    }
    let total = retained.reduce(fileSize(host) + fileSize(current)) { $0 + fileSize($1) }
    if total > TrainerLogSink.maximumTotalBytes {
        fail("per-game Trainer log retention exceeded 32 MiB")
    }

    // User cleanup removes completed Trainer sessions only. The active session
    // and native Hades log are outside that deletion set.
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(processName: "Hades II", bundleIdentifier: "com.supergiantgames.hades2", processIdentifier: 4001)
    )
    sink.append("active-survives-cleanup", source: "HOST")
    sink.flush()
    if !sink.clearCompletedSessions() { fail("completed session cleanup reported failure") }
    if !completedLogs(history).isEmpty { fail("completed session cleanup left history behind") }
    let active = (try? String(contentsOf: current, encoding: .utf8)) ?? ""
    if !active.contains("active-survives-cleanup") { fail("cleanup removed the active session") }
    if !FileManager.default.fileExists(atPath: nativeLog.path) { fail("cleanup touched native Hades II.log") }
}

// Sustained backend output cannot turn the Host writer queue into an
// unbounded in-memory backlog. Dropped diagnostics remain explicit.
let queueHome = home.appendingPathComponent("queue-home", isDirectory: true)
do {
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: queueHome)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(processName: "Hades II", bundleIdentifier: "com.supergiantgames.hades2", processIdentifier: 4501)
    )
    let payload = String(repeating: "q", count: 65_536)
    for index in 0..<128 {
        sink.append("queue-\(index) " + payload, source: "BACKEND")
    }
    // Guarantee the overflow path even on an unusually fast filesystem.
    sink.append(String(repeating: "z", count: TrainerLogSink.maximumPendingBytes + 1), source: "BACKEND")
    sink.flush()
    let text = (try? String(contentsOf: sink.url, encoding: .utf8)) ?? ""
    if !text.contains("LOGGER log queue overflow droppedBytes=") {
        fail("Host log queue did not make burst truncation explicit")
    }
    if fileSize(sink.url) > TrainerLogSink.maximumSessionFileSize {
        fail("bounded Host queue escaped the per-session file cap")
    }
}

// Recovery fixtures model the three durable boundaries in finalization. Each
// fixture is the exact on-disk state a terminated Trainer can leave behind;
// the next Trainer instance must preserve the completed evidence and continue
// with a fresh active session.
func writeSessionFixture(home: URL, phase: String) throws -> (URL, URL, URL, String) {
    let directory = home
        .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
        .appendingPathComponent("hades2", isDirectory: true)
    let current = directory.appendingPathComponent("trainer.log")
    let history = directory.appendingPathComponent("sessions", isDirectory: true)
    let metadata = directory.appendingPathComponent("current-session.json")
    try FileManager.default.createDirectory(at: history, withIntermediateDirectories: true)

    let id = "interrupted-\(phase)"
    let record: [String: Any] = [
        "id": id,
        "startedAt": "2026-10-16T10:00:00Z",
        "endedAt": "2026-10-16T10:05:00Z",
        "targetProcessName": "Hades II",
        "targetBundleIdentifier": "com.supergiantgames.hades2",
        "targetPID": 9000,
        "appVersion": "0.3.0",
        "appBuild": "6",
        "gameVersion": "1.143476",
        "runtimeRevision": 109,
        "legacy": false,
        "finalizing": true,
    ]
    let metadataData = try JSONSerialization.data(withJSONObject: record, options: [.prettyPrinted, .sortedKeys])
    let completedMetadata = history.appendingPathComponent(id).appendingPathExtension("json")
    let completedLog = history.appendingPathComponent(id).appendingPathExtension("log")
    try metadataData.write(to: completedMetadata, options: .atomic)

    switch phase {
    case "after-finalizing-marker":
        try metadataData.write(to: metadata, options: .atomic)
        try Data("ORIGINAL after-finalizing-marker\n".utf8).write(to: current, options: .atomic)
    case "after-completed-metadata":
        try metadataData.write(to: metadata, options: .atomic)
        try Data("ORIGINAL after-completed-metadata\n".utf8).write(to: current, options: .atomic)
    case "after-log-move":
        try metadataData.write(to: metadata, options: .atomic)
        try Data("ORIGINAL after-log-move\n".utf8).write(to: completedLog, options: .atomic)
    case "after-current-metadata-removal":
        try Data("ORIGINAL after-current-metadata-removal\n".utf8).write(to: completedLog, options: .atomic)
    default:
        fail("unknown finalization fixture")
    }
    return (directory, current, history, id)
}

for phase in ["after-finalizing-marker", "after-completed-metadata", "after-log-move", "after-current-metadata-removal"] {
    let fixtureHome = home.appendingPathComponent("finalization-\(phase)", isDirectory: true)
    let (directory, current, history, interruptedID) = try writeSessionFixture(home: fixtureHome, phase: phase)
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: fixtureHome)
    let host = directory.appendingPathComponent("trainer-host.log")
    if sink.currentLogURL() != host {
        fail("finalization recovery \(phase) exposed stale target log before target lifetime")
    }
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: phase == "after-finalizing-marker" ? 9000 : 9001
        )
    )
    sink.flush()

    let retained = completedLogs(history)
    guard retained.count == 1 else {
        fail("finalization recovery \(phase) did not retain exactly one completed log")
    }
    let retainedLog = history.appendingPathComponent(interruptedID).appendingPathExtension("log")
    let retainedText = (try? String(contentsOf: retainedLog, encoding: .utf8)) ?? ""
    if !retainedText.contains("ORIGINAL \(phase)") {
        fail("finalization recovery \(phase) overwrote the completed log")
    }
    guard let newMetadata = try? JSONSerialization.jsonObject(
        with: Data(contentsOf: fixtureHome
            .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
            .appendingPathComponent("hades2", isDirectory: true)
            .appendingPathComponent("current-session.json"))
    ) as? [String: Any] else {
        fail("finalization recovery \(phase) did not establish a new active session")
    }
    let expectedPID = phase == "after-finalizing-marker" ? 9000 : 9001
    if newMetadata["id"] as? String == interruptedID
        || newMetadata["targetPID"] as? Int != expectedPID
        || newMetadata["finalizing"] as? Bool == true {
        fail("finalization recovery \(phase) reused the interrupted session identity")
    }
    if !FileManager.default.fileExists(atPath: current.path) {
        fail("finalization recovery (phase) did not create a new current log")
    }
}

// Legacy trainer.log(.1-.3) is migrated into history instead of silently lost.
let legacyHome = home.appendingPathComponent("legacy-home", isDirectory: true)
let legacyDirectory = legacyHome
    .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
    .appendingPathComponent("hades2", isDirectory: true)
try FileManager.default.createDirectory(at: legacyDirectory, withIntermediateDirectories: true)
let legacyCurrent = legacyDirectory.appendingPathComponent("trainer.log")
try Data("legacy-current\n".utf8).write(to: legacyCurrent)
try Data("legacy-older\n".utf8).write(to: legacyCurrent.appendingPathExtension("1"))
do {
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: legacyHome)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(processName: "Hades II", bundleIdentifier: "com.supergiantgames.hades2", processIdentifier: 5001)
    )
    sink.flush()
    let migrated = completedLogs(sink.historyURL)
    if migrated.count != 1 { fail("legacy trainer.log history was not migrated") }
    let text = (try? String(contentsOf: migrated[0], encoding: .utf8)) ?? ""
    if !text.contains("legacy-older") || !text.contains("legacy-current") {
        fail("legacy migration lost retained records")
    }
}

print("trainer_log_session_lifecycle_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-log-session-") as td:
    td = Path(td)
    main = td / "main.swift"
    binary = td / "log_session_test"
    home = td / "home"
    home.mkdir()
    main.write_text(textwrap.dedent(main_source), encoding="utf-8")
    subprocess.run([
        SWIFTC,
        str(ROOT / "Sources/Core/Runtime/TrainerLogSink.swift"),
        str(main),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    proc = subprocess.run([str(binary), str(home)], cwd=ROOT, text=True, capture_output=True, timeout=30)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
