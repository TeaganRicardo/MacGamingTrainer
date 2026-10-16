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

func directorySize(_ url: URL) -> Int {
    guard let enumerator = FileManager.default.enumerator(
        at: url,
        includingPropertiesForKeys: [.fileSizeKey],
        options: [.skipsHiddenFiles]
    ) else {
        return 0
    }
    var total = 0
    for case let fileURL as URL in enumerator {
        total += (try? fileURL.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
    }
    return total
}

func sessionBundles(_ history: URL) -> [(URL, [String: Any])] {
    let entries = (try? FileManager.default.contentsOfDirectory(
        at: history,
        includingPropertiesForKeys: nil,
        options: [.skipsHiddenFiles]
    )) ?? []
    return entries.compactMap { bundle in
        var isDirectory = false
        guard FileManager.default.fileExists(atPath: bundle.path, isDirectory: &isDirectory),
              isDirectory,
              let data = try? Data(contentsOf: bundle.appendingPathComponent("manifest.json")),
              let manifest = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        return (bundle, manifest)
    }
}

func readJSON(_ url: URL) -> [String: Any]? {
    guard let data = try? Data(contentsOf: url) else { return nil }
    return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
}

func streamText(_ bundle: URL, _ name: String) -> String {
    (try? String(contentsOf: bundle.appendingPathComponent(name), encoding: .utf8)) ?? ""
}

func writeRecoveryFixture(home: URL, id: String, state: String, pid: Int) throws -> (URL, URL) {
    let gameDirectory = home
        .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
        .appendingPathComponent("hades2", isDirectory: true)
    let history = gameDirectory.appendingPathComponent("sessions", isDirectory: true)
    let bundle = history.appendingPathComponent(id, isDirectory: true)
    try FileManager.default.createDirectory(at: bundle, withIntermediateDirectories: true)

    let manifest: [String: Any] = [
        "schemaVersion": 1,
        "id": id,
        "startedAt": "2026-10-16T10:00:00Z",
        "endedAt": state == "active" ? NSNull() : "2026-10-16T10:05:00Z",
        "targetProcessName": "Hades II",
        "targetBundleIdentifier": "com.supergiantgames.hades2",
        "targetPID": pid,
        "appVersion": "0.3.0",
        "appBuild": "6",
        "gameVersion": "1.143476",
        "runtimeRevision": 109,
        "state": state,
        "endReason": state == "active" ? NSNull() : "target-exited",
        "streams": [
            "HOST": "host.log",
            "BACKEND": "backend.log",
            "RUNTIME": "runtime.log"
        ],
        "legacy": false,
    ]
    try JSONSerialization.data(withJSONObject: manifest, options: [.prettyPrinted, .sortedKeys])
        .write(to: bundle.appendingPathComponent("manifest.json"), options: .atomic)
    try Data("ORIGINAL \(state)\n".utf8).write(
        to: bundle.appendingPathComponent("host.log"),
        options: .atomic
    )
    try Data("backend evidence\n".utf8).write(
        to: bundle.appendingPathComponent("backend.log"),
        options: .atomic
    )
    try Data("runtime evidence\n".utf8).write(
        to: bundle.appendingPathComponent("runtime.log"),
        options: .atomic
    )
    let pointer = gameDirectory.appendingPathComponent("current-session.json")
    try JSONSerialization.data(
        withJSONObject: ["id": id],
        options: [.prettyPrinted, .sortedKeys]
    ).write(to: pointer, options: .atomic)
    return (bundle, pointer)
}

guard CommandLine.arguments.count == 2 else { fail("temporary home required") }
let home = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let gameDirectory = home
    .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
    .appendingPathComponent("hades2", isDirectory: true)
let legacyCurrent = gameDirectory.appendingPathComponent("trainer.log")
let host = gameDirectory.appendingPathComponent("trainer-host.log")
let history = gameDirectory.appendingPathComponent("sessions", isDirectory: true)
let metadata = gameDirectory.appendingPathComponent("current-session.json")
let nativeLog = home.appendingPathComponent(
    "Library/Application Support/Supergiant Games/Hades II/Hades II.log"
)
try FileManager.default.createDirectory(
    at: nativeLog.deletingLastPathComponent(),
    withIntermediateDirectories: true
)
try Data("native game log must survive\n".utf8).write(to: nativeLog)

guard TrainerLogSink.moduleLogURL(gameID: "hades2", homeDirectory: home) == legacyCurrent else {
    fail("legacy module log path compatibility changed")
}

// Before a target lifetime exists, diagnostics belong to bounded Host context.
do {
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: home)
    sink.append("host-before-target")
    sink.append(String(repeating: "h", count: 1_200_000))
    sink.flush()

    if sink.currentLogURL() != host { fail("pre-target log did not resolve to Host context") }
    if sink.currentSessionURL() != nil { fail("pre-target context exposed a fake session bundle") }
    if fileSize(host) > TrainerLogSink.maximumHostFileSize {
        fail("Host context exceeded its cap")
    }
    if FileManager.default.fileExists(atPath: legacyCurrent.path) {
        fail("Host context created the legacy trainer.log")
    }
}

// A target lifetime is one self-contained bundle with independent source streams.
do {
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: home)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: 1001
        )
    )
    sink.updateCurrentSessionRuntimeIdentity(gameVersion: "1.143476", runtimeRevision: 112)
    sink.append("host-in-session", source: "HOST")
    sink.append("backend-in-session", source: "BACKEND")
    sink.append("runtime-in-session", source: "RUNTIME")
    sink.flush()

    guard let bundle = sink.currentSessionURL() else { fail("active session bundle missing") }
    if sink.currentLogURL() != bundle.appendingPathComponent("host.log") {
        fail("currentLogURL did not resolve to the active Host stream")
    }
    if FileManager.default.fileExists(atPath: legacyCurrent.path) {
        fail("new sessions still write the legacy trainer.log")
    }

    guard let pointer = readJSON(metadata),
          let id = pointer["id"] as? String else {
        fail("current session pointer missing")
    }
    if bundle.lastPathComponent != id {
        fail("current session pointer does not identify the active bundle")
    }

    guard let manifest = readJSON(bundle.appendingPathComponent("manifest.json")) else {
        fail("session manifest missing")
    }
    if manifest["schemaVersion"] as? Int != 1 { fail("unexpected manifest schema") }
    if manifest["state"] as? String != "active" { fail("active session state missing") }
    if manifest["targetProcessName"] as? String != "Hades II" { fail("target identity missing") }
    if manifest["targetBundleIdentifier"] as? String != "com.supergiantgames.hades2" {
        fail("target bundle identity missing")
    }
    if manifest["gameVersion"] as? String != "1.143476" { fail("game version identity missing") }
    if manifest["runtimeRevision"] as? Int != 112 { fail("resident revision identity missing") }

    guard let streams = manifest["streams"] as? [String: String] else {
        fail("manifest stream map missing")
    }
    if streams != [
        "HOST": "host.log",
        "BACKEND": "backend.log",
        "RUNTIME": "runtime.log"
    ] {
        fail("manifest stream map is not the declared Session Bundle layout")
    }

    if !streamText(bundle, "host.log").contains("HOST host-in-session") {
        fail("Host stream missing Host record")
    }
    if streamText(bundle, "host.log").contains("session runtime gameVersion=") {
        fail("Runtime identity enrichment leaked into the Host stream")
    }
    if !streamText(bundle, "backend.log").contains("BACKEND backend-in-session") {
        fail("Backend stream missing Backend record")
    }
    if !streamText(bundle, "runtime.log").contains("RUNTIME runtime-in-session") {
        fail("Runtime stream missing Runtime record")
    }
    if !streamText(bundle, "runtime.log").contains("session runtime gameVersion=1.143476") {
        fail("runtime identity enrichment did not use Runtime stream")
    }
}

// Trainer restart with the same target PID resumes the same bundle. A large
// Backend burst is bounded independently from Host and Runtime.
do {
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: home)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: 1001
        )
    )
    guard let resumed = sink.currentSessionURL() else { fail("same-PID session was not resumed") }
    sink.append("after-host-restart", source: "HOST")
    sink.append(String(repeating: "b", count: 4_800_000), source: "BACKEND")
    sink.flush()

    let bundles = sessionBundles(history)
    if bundles.filter({ ($0.1["state"] as? String) == "completed" }).count != 0 {
        fail("same target PID was split into multiple completed sessions")
    }
    if fileSize(resumed.appendingPathComponent("backend.log")) > 2 * 1_048_576 {
        fail("Backend stream escaped its 2 MiB per-session allocation")
    }
    if directorySize(resumed) > TrainerLogSink.maximumSessionBytes + 16_384 {
        fail("session bundle escaped its bounded size")
    }
    if !streamText(resumed, "backend.log").contains("BACKEND ") {
        fail("bounded backend record lost its source tag")
    }
}

// A replacement PID closes the previous lifetime and creates a new bundle.
do {
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: home)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: 1002
        )
    )
    guard let replacement = sink.currentSessionURL() else { fail("replacement session missing") }
    sink.append("replacement-process", source: "HOST")
    sink.flush()

    let completed = sessionBundles(history).filter { ($0.1["state"] as? String) == "completed" }
    if completed.count != 1 { fail("replacement PID did not close the previous session") }
    guard let previous = completed.first else { fail("completed session missing") }
    if previous.1["endReason"] as? String != "target-replaced" {
        fail("replacement session did not record its close reason")
    }
    if replacement.lastPathComponent == (previous.1["id"] as? String ?? "") {
        fail("replacement PID reused the completed session ID")
    }

    sink.targetLifetimeChanged(
        running: false,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: nil
        )
    )
    guard let completedManifest = readJSON(replacement.appendingPathComponent("manifest.json")),
          completedManifest["state"] as? String == "completed" else {
        fail("normal finalization did not commit the completed bundle manifest")
    }
    for stream in ["host.log", "backend.log", "runtime.log"] {
        if !FileManager.default.fileExists(atPath: replacement.appendingPathComponent(stream).path) {
            fail("normal finalization moved or removed \(stream)")
        }
    }
    if !streamText(replacement, "host.log").contains("session end id=") {
        fail("session end evidence was not retained in the completed bundle")
    }
    if streamText(host, "session end id=").contains("session end id=") {
        fail("session end evidence leaked into Host context")
    }
    if FileManager.default.fileExists(atPath: metadata.path) {
        fail("ended target session pointer remained current")
    }
}

// Retention is session-oriented. Completed bundles are bounded by count and
// by the hard per-game total; active bundles are never evicted.
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
        sink.append(
            "bulk-\(index) " + String(repeating: "x", count: 3_900_000),
            source: "BACKEND"
        )
        sink.flush()
        sink.targetLifetimeChanged(
            running: false,
            identity: .init(
                processName: "Hades II",
                bundleIdentifier: "com.supergiantgames.hades2",
                processIdentifier: nil
            )
        )
    }

    let bundles = sessionBundles(history)
    let completed = bundles.filter { ($0.1["state"] as? String) == "completed" }
    if completed.count > TrainerLogSink.maximumCompletedSessions {
        fail("retained more than eight completed target sessions")
    }
    let total = fileSize(host) + bundles.reduce(0) { $0 + directorySize($1.0) }
    if total > TrainerLogSink.maximumTotalBytes {
        fail("per-game Trainer log retention exceeded 32 MiB")
    }
}

// Cleanup only removes completed Trainer session bundles. The active bundle and
// native Hades log remain untouched.
do {
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: home)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: 4001
        )
    )
    guard let active = sink.currentSessionURL() else { fail("active cleanup session missing") }
    sink.append("active-survives-cleanup", source: "HOST")
    sink.flush()
    if !sink.clearCompletedSessions() { fail("completed session cleanup reported failure") }
    if !sessionBundles(history).filter({ ($0.1["state"] as? String) == "completed" }).isEmpty {
        fail("completed session cleanup left history behind")
    }
    if !FileManager.default.fileExists(atPath: active.path) {
        fail("cleanup removed the active session bundle")
    }
    if !streamText(active, "host.log").contains("active-survives-cleanup") {
        fail("cleanup removed active session evidence")
    }
    if !FileManager.default.fileExists(atPath: nativeLog.path) {
        fail("cleanup touched native Hades II.log")
    }
}

// Queue overflow remains explicit and is recorded in the Host stream.
do {
    let queueHome = home.appendingPathComponent("queue-home", isDirectory: true)
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: queueHome)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: 4501
        )
    )
    let payload = String(repeating: "q", count: 65_536)
    for index in 0..<128 {
        sink.append("queue-\(index) " + payload, source: "BACKEND")
    }
    sink.append(
        String(repeating: "z", count: TrainerLogSink.maximumPendingBytes + 1),
        source: "BACKEND"
    )
    sink.flush()
    guard let active = sink.currentSessionURL() else { fail("queue session missing") }
    if !streamText(active, "host.log").contains("LOGGER log queue overflow droppedBytes=") {
        fail("Host log queue did not make burst truncation explicit")
    }
    if fileSize(active.appendingPathComponent("host.log")) > 1 * 1_048_576 {
        fail("Host stream escaped its bound")
    }
}

// Finalization recovery is in-place: no log file is moved or overwritten.
// A finalizing bundle can resume when the same target identity returns;
// a stale active bundle is sealed as interrupted before a replacement starts.
do {
    let recoveryHome = home.appendingPathComponent("recovery-same-pid", isDirectory: true)
    let (bundle, pointer) = try writeRecoveryFixture(
        home: recoveryHome,
        id: "interrupted-finalizing",
        state: "finalizing",
        pid: 9000
    )
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: recoveryHome)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: 9000
        )
    )
    sink.flush()
    guard let resumed = sink.currentSessionURL(),
          resumed.lastPathComponent == "interrupted-finalizing" else {
        fail("finalizing session was not resumed for the same target identity")
    }
    if !streamText(bundle, "host.log").contains("ORIGINAL finalizing") {
        fail("finalization recovery overwrote the existing Host stream")
    }
    guard let resumedManifest = readJSON(bundle.appendingPathComponent("manifest.json")),
          resumedManifest["state"] as? String == "active" else {
        fail("same-PID finalization recovery did not reopen the bundle as active")
    }
    if !(resumedManifest["endedAt"] is NSNull) && resumedManifest["endedAt"] != nil {
        fail("same-PID finalization recovery retained a terminal end time")
    }
    sink.targetLifetimeChanged(
        running: false,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: nil
        )
    )
    if FileManager.default.fileExists(atPath: pointer.path) {
        fail("completed recovered session pointer remained current")
    }
}

do {
    let recoveryHome = home.appendingPathComponent("recovery-replacement", isDirectory: true)
    let (oldBundle, _) = try writeRecoveryFixture(
        home: recoveryHome,
        id: "interrupted-active",
        state: "active",
        pid: 9100
    )
    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: recoveryHome)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: 9101
        )
    )
    sink.flush()

    guard let oldManifest = readJSON(oldBundle.appendingPathComponent("manifest.json")),
          oldManifest["state"] as? String == "completed",
          oldManifest["endReason"] as? String == "target-replaced" else {
        fail("stale active session was not sealed before replacement")
    }
    if !streamText(oldBundle, "host.log").contains("ORIGINAL active") {
        fail("stale active session evidence was overwritten")
    }
    guard let current = sink.currentSessionURL(),
          current.lastPathComponent != "interrupted-active" else {
        fail("replacement reused stale session bundle")
    }
}

// Legacy root trainer.log(.1-.3) is migrated into a completed Session Bundle.
do {
    let legacyHome = home.appendingPathComponent("legacy-root", isDirectory: true)
    let directory = legacyHome
        .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
        .appendingPathComponent("hades2", isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let current = directory.appendingPathComponent("trainer.log")
    try Data("legacy-current\n".utf8).write(to: current)
    try Data("legacy-older\n".utf8).write(to: current.appendingPathExtension("1"))

    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: legacyHome)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: 5001
        )
    )
    sink.flush()

    let bundles = sessionBundles(sink.historyURL)
    let migrated = bundles.filter { ($0.1["legacy"] as? Bool) == true }
    if migrated.count != 1 { fail("legacy trainer.log was not migrated to a bundle") }
    guard let legacyBundle = migrated.first else { fail("legacy bundle missing") }
    let legacyText = streamText(legacyBundle.0, "legacy.log")
    if !legacyText.contains("legacy-older") || !legacyText.contains("legacy-current") {
        fail("legacy migration lost retained records")
    }
    if !FileManager.default.fileExists(atPath: sink.currentSessionURL()!.path) {
        fail("new target session was not created after legacy migration")
    }
}

// An interrupted bundle creation must preserve already-written stream bytes
// even if its manifest was never committed.
do {
    let orphanHome = home.appendingPathComponent("orphan-bundle", isDirectory: true)
    let directory = orphanHome
        .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
        .appendingPathComponent("hades2", isDirectory: true)
    let orphan = directory
        .appendingPathComponent("sessions", isDirectory: true)
        .appendingPathComponent("orphaned-session", isDirectory: true)
    try FileManager.default.createDirectory(at: orphan, withIntermediateDirectories: true)
    try Data("ORPHANED BACKEND EVIDENCE\n".utf8).write(
        to: orphan.appendingPathComponent("backend.log"),
        options: .atomic
    )

    let sink = TrainerLogSink(gameID: "hades2", homeDirectory: orphanHome)
    sink.targetLifetimeChanged(
        running: true,
        identity: .init(
            processName: "Hades II",
            bundleIdentifier: "com.supergiantgames.hades2",
            processIdentifier: 8801
        )
    )
    sink.flush()

    guard let recoveredManifest = readJSON(orphan.appendingPathComponent("manifest.json")),
          recoveredManifest["state"] as? String == "completed",
          recoveredManifest["legacy"] as? Bool == false,
          recoveredManifest["endReason"] as? String == "orphan-recovery" else {
        fail("unindexed current-format bundle was not recovered cleanly")
    }
    if !streamText(orphan, "backend.log").contains("ORPHANED BACKEND EVIDENCE") {
        fail("orphaned stream bytes were lost during recovery")
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
    proc = subprocess.run(
        [str(binary), str(home)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
