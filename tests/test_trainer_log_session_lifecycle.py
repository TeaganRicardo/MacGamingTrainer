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
    sink.append("host-in-session", source: "HOST")
    sink.append("backend-in-session", source: "BACKEND")
    sink.flush()
    if sink.currentLogURL() != current { fail("active target did not own current session log") }
    let text = (try? String(contentsOf: current, encoding: .utf8)) ?? ""
    if !text.contains("HOST host-in-session") || !text.contains("BACKEND backend-in-session") {
        fail("source-tagged records missing from current session")
    }
    if !FileManager.default.fileExists(atPath: metadata.path) { fail("current session metadata missing") }
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
    sink.clearCompletedSessions()
    if !completedLogs(history).isEmpty { fail("completed session cleanup left history behind") }
    let active = (try? String(contentsOf: current, encoding: .utf8)) ?? ""
    if !active.contains("active-survives-cleanup") { fail("cleanup removed the active session") }
    if !FileManager.default.fileExists(atPath: nativeLog.path) { fail("cleanup touched native Hades II.log") }
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
