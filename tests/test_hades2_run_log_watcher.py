from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required for Hades2RunLogWatcher test")

main_source = r"""
import Foundation

if !Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: true, busy: false, exiting: false
) {
    fatalError("an armed runtime-ready event must be consumable even if the previous GUI snapshot was ready")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: false, connected: true, backendAvailable: true, busy: false, exiting: false
) {
    fatalError("no pending lifecycle refresh must mean no Lua boundary")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: false, backendAvailable: true, busy: false, exiting: false
) {
    fatalError("detached trainer must not cross the Lua boundary")
}
if Hades2RunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: true, busy: true, exiting: false
) {
    fatalError("busy trainer must defer the lifecycle refresh")
}

let fileManager = FileManager.default
guard CommandLine.arguments.count == 2 else {
    fatalError("temporary Hades support directory argument required")
}
let directory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let logURL = directory.appendingPathComponent("Hades II.log")

try? fileManager.removeItem(at: directory)
try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
try Data("seed\n".utf8).write(to: logURL)

var events: [Hades2RunLogEvent] = []
let watcher = Hades2RunLogWatcher(directoryURL: directory) { event in
    events.append(event)
}
watcher.start()

func pump(_ seconds: TimeInterval) {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.01))
    }
}

func append(_ text: String) throws {
    let handle = try FileHandle(forWritingTo: logURL)
    try handle.seekToEnd()
    try handle.write(contentsOf: Data(text.utf8))
    try handle.synchronize()
    try handle.close()
}

pump(0.35)

try append("2026-09-19 [MainThread] World.cpp INFO| World::Begin() G_Intro -> G_Combat04\n")
try append("2026-09-19 [MainThread] World.cpp INFO| Finished loadScreen onExit (0.04 seconds)\n")
try append("2026-09-19 [MainThread] World.cpp INFO| World::Stop()\n")
pump(0.35)
if !events.isEmpty {
    fatalError("ordinary room/pause lifecycle unexpectedly emitted events: \(events)")
}

try append("2026-09-19 [MainThread] GameAssetManager.cpp INFO| Loading package: MainMenu.pkg\n")
let menuDeadline = Date().addingTimeInterval(2)
while events.count < 1 && Date() < menuDeadline { pump(0.01) }
if events.map({ String(describing: $0) }) != ["mainMenu"] {
    fatalError("main-menu package load did not emit exactly mainMenu: \(events)")
}

try append("2026-09-19 [MainThread] App.cpp INFO| App.Reset Start\n")
try append("2026-09-19 [MainThread] LuaExt.cpp INFO| Lua interface destroyed\n")
try append("2026-09-19 [MainThread] World.cpp INFO| World::Begin()  -> G_Intro\n")
try append("2026-09-19 [MainThread] World.cpp INFO| Finished loadScreen onExit (0.18 seconds)\n")
let resetDeadline = Date().addingTimeInterval(2)
while events.count < 3 && Date() < resetDeadline { pump(0.01) }
if events.map({ String(describing: $0) }) != ["mainMenu", "runtimeReset", "runtimeReady"] {
    fatalError("profile reset lifecycle was not coalesced correctly: \(events)")
}

let rotatedURL = directory.appendingPathComponent("Hades II.log.previous")
try? fileManager.removeItem(at: rotatedURL)
try fileManager.moveItem(at: logURL, to: rotatedURL)
try Data("new session\n".utf8).write(to: logURL)
pump(0.5)
try append("2026-09-19 [MainThread] App.cpp INFO| App.Reset Start\n2026-09-19 [MainThread] World.cpp INFO| Finished loadScreen onExit (0.10 seconds)\n")
let rotationDeadline = Date().addingTimeInterval(2)
while events.count < 5 && Date() < rotationDeadline { pump(0.01) }
if Array(events.suffix(2)) != [.runtimeReset, .runtimeReady] {
    fatalError("log replacement lost reset lifecycle events: \(events)")
}

let truncating = try FileHandle(forWritingTo: logURL)
try truncating.truncate(atOffset: 0)
try truncating.write(contentsOf: Data("2026-09-19 [MainThread] LuaExt.cpp INFO| Lua interface destroyed\n2026-09-19 [MainThread] World.cpp INFO| Finished loadScreen onExit (0.10 seconds)\n".utf8))
try truncating.synchronize()
try truncating.close()
let truncationDeadline = Date().addingTimeInterval(2)
while events.count < 7 && Date() < truncationDeadline { pump(0.01) }
watcher.stop()
if Array(events.suffix(2)) != [.runtimeReset, .runtimeReady] {
    fatalError("log truncation lost reset lifecycle events: \(events)")
}

print("hades2_run_log_watcher_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-hades2-log-watcher-") as td:
    td = Path(td)
    main = td / "main.swift"
    binary = td / "watcher_test"
    main.write_text(textwrap.dedent(main_source), encoding="utf-8")
    subprocess.run([
        SWIFTC,
        str(ROOT / "Sources/Hades2/Services/Hades2RunLogRefreshGate.swift"),
        str(ROOT / "Sources/Hades2/Services/Hades2RunLogWatcher.swift"),
        str(main),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    support = td / "fake-hades-support"
    proc = subprocess.run([str(binary), str(support)], cwd=ROOT, text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
