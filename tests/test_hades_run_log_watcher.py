MGT_PLATFORM = "macos"

from macos_fixture_policy import launch_fixture
from fixture_budgets.hades import JOURNEY_BUDGETS
from pathlib import Path
import shutil
from swift_test_compiler import compile_swift_test
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required for HadesRunLogWatcher test")

main_source = r"""
import Foundation

// HadesLaunchAttachGate belongs to target lifetime and refuses unverified readiness or restart-required state.
var readyGate = HadesLaunchAttachGate()
readyGate.observeRuntimeReady()
if !readyGate.deferUntilReady(targetJustLaunched: true, canObserveLifecycle: true) {
    fatalError("Hades launch-time readiness gate was not armed")
}
if readyGate.consumeIfEligible(
    backendAvailable: true, busy: false, connected: false, exiting: false, requiresTargetRestart: true
) {
    fatalError("Hades launch gate attached when restart was required")
}
if !readyGate.consumeIfEligible(
    backendAvailable: true, busy: false, connected: false, exiting: false, requiresTargetRestart: false
) {
    fatalError("Hades launch gate lost boot-ready signal")
}
readyGate.targetLifetimeChanged()
if !readyGate.deferUntilReady(targetJustLaunched: true, canObserveLifecycle: true) {
    fatalError("replacement target failed to arm launch gate")
}
if readyGate.consumeIfEligible(
    backendAvailable: true, busy: false, connected: false, exiting: false, requiresTargetRestart: false
) {
    fatalError("old process readiness escaped target lifetime")
}

// HadesRunLogRefreshGate must refuse while busy, disconnected, exiting, or restart-required.
if HadesRunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: true, busy: false, exiting: false, requiresTargetRestart: true
) {
    fatalError("refresh gate consumed while restart was required")
}
if !HadesRunLogRefreshGate.shouldConsume(
    pending: true, connected: true, backendAvailable: true, busy: false, exiting: false, requiresTargetRestart: false
) {
    fatalError("refresh gate rejected clean room-load refresh")
}

let fileManager = FileManager.default
guard CommandLine.arguments.count == 2 else {
    fatalError("temporary Hades support directory argument required")
}
let directory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let logURL = directory.appendingPathComponent("Hades.log")

try? fileManager.removeItem(at: directory)
try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
try Data("seed\n".utf8).write(to: logURL)

var events: [HadesRunLogEvent] = []
let watcher = HadesRunLogWatcher(directoryURL: directory) { event in
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

// Boot sequence: early Lua destroy + Done with boot load + Launch took coalesces to runtimeReset + single bootReady.
try append(
    "2026-11-27 App.cpp:414 DBG| App Initialize\n" +
    "2026-11-27 LuaExt.cpp:453 INFO| Lua interface destroyed\n" +
    "2026-11-27 LaunchScreen.cpp:301 DBG| Done with boot load\n" +
    "2026-11-27 LaunchScreen.cpp:667 DBG| Launch took 5.852 seconds\n"
)
let bootDeadline = Date().addingTimeInterval(2)
while events.count < 2 && Date() < bootDeadline { pump(0.01) }
if events != [.runtimeReset, .bootReady] {
    fatalError("Hades boot log sequence mismatch: \(events)")
}

// Pause menu (World::Stop + PauseScreen.sjson) must NEVER trigger mainMenu or refresh.
events.removeAll()
try append(
    "2026-11-27 UnixFileSystem.cpp DBG| Content/Game/GUI/PauseScreen.sjson\n" +
    "2026-11-27 World.cpp:1593 INFO| World::Stop()\n"
)
pump(0.3)
if !events.isEmpty {
    fatalError("Pause menu unexpectedly emitted events: \(events)")
}

// Save load & room transition: App.Reset Start -> World::Begin() -> end of postLoadTask.
try append(
    "2026-11-27 App.cpp:1488 DBG| App.Reset Start\n" +
    "2026-11-27 LuaExt.cpp:453 INFO| Lua interface destroyed\n" +
    "2026-11-27 World.cpp:1526 INFO| World::Begin() -> DeathArea\n" +
    "2026-11-27 World.cpp:1440 DBG| end of postLoadTask\n"
)
let roomDeadline = Date().addingTimeInterval(2)
while events.count < 3 && Date() < roomDeadline { pump(0.01) }
if events != [.runtimeReset, .roomTransitionStarted, .roomLoaded] {
    fatalError("Save load / room transition mismatch: \(events)")
}

// Quit to Main Menu emits mainMenu; Shutdown suppresses trailing Lua interface destroyed.
events.removeAll()
try append(
    "2026-11-27 World.cpp:1593 INFO| World::Stop()\n" +
    "2026-11-27 UnixFileSystem.cpp:94 ERR| Error opening file: .../Content/Game/MainMenuScreen.sjson\n" +
    "2026-11-27 App.cpp:255 DBG| Shutting down\n" +
    "2026-11-27 LuaExt.cpp:445 INFO| Lua interface destroyed\n"
)
let menuDeadline = Date().addingTimeInterval(2)
while events.isEmpty && Date() < menuDeadline { pump(0.01) }
pump(0.2)
if events != [.mainMenu] {
    fatalError("MainMenu / Shutting down mismatch: \(events)")
}

// Log rotation & truncation recover and re-arm events cleanly.
events.removeAll()
let rotatedURL = directory.appendingPathComponent("Hades.log.previous")
try? fileManager.removeItem(at: rotatedURL)
try fileManager.moveItem(at: logURL, to: rotatedURL)
try Data("new run log\n".utf8).write(to: logURL)
pump(0.4)
try append("2026-11-27 World.cpp:1526 INFO| World::Begin() DeathArea -> RoomPreRun\n2026-11-27 World.cpp:1433 DBG| Finished PostLaod\n")
let rotDeadline = Date().addingTimeInterval(2)
while events.count < 2 && Date() < rotDeadline { pump(0.01) }
if events != [.roomTransitionStarted, .roomLoaded] {
    fatalError("Log rotation recovery mismatch: \(events)")
}

let truncating = try FileHandle(forWritingTo: logURL)
try truncating.truncate(atOffset: 0)
try truncating.write(contentsOf: Data("2026-11-27 World.cpp:1526 INFO| World::Begin() RoomPreRun -> A_Combat01\n2026-11-27 World.cpp:1440 DBG| end of postLoadTask\n".utf8))
try truncating.synchronize()
try truncating.close()
let truncDeadline = Date().addingTimeInterval(2)
while events.count < 4 && Date() < truncDeadline { pump(0.01) }
watcher.stop()
if Array(events.suffix(2)) != [.roomTransitionStarted, .roomLoaded] {
    fatalError("Log truncation recovery mismatch: \(events)")
}

// Epoch cancellation across targetLifetimeChanged.
let raceDirectory = directory.appendingPathComponent("delivery-race", isDirectory: true)
try fileManager.createDirectory(at: raceDirectory, withIntermediateDirectories: true)
let raceLog = raceDirectory.appendingPathComponent("Hades.log")
try Data("prior lifetime\n".utf8).write(to: raceLog)
let queued = DispatchSemaphore(value: 0)
var raceEvents: [HadesRunLogEvent] = []
let raceWatcher = HadesRunLogWatcher(directoryURL: raceDirectory, deliver: { delivery in
    DispatchQueue.main.async(execute: delivery)
    queued.signal()
}) { raceEvents.append($0) }
raceWatcher.targetLifetimeChanged(running: true)
func raceAppend() throws {
    let handle = try FileHandle(forWritingTo: raceLog)
    try handle.seekToEnd()
    try handle.write(contentsOf: Data("World::Begin()\nend of postLoadTask\n".utf8))
    try handle.synchronize(); try handle.close()
}
try raceAppend()
if queued.wait(timeout: .now() + 2) != .success { fatalError("old log signal did not queue") }
raceWatcher.targetLifetimeChanged(running: true)
pump(0.1)
if !raceEvents.isEmpty { fatalError("old process log event crossed target lifetime") }
try raceAppend()
if queued.wait(timeout: .now() + 2) != .success { fatalError("replacement process did not queue") }
pump(0.1)
if raceEvents != [.roomTransitionStarted, .roomLoaded] { fatalError("replacement process log signal lost") }
raceWatcher.stop()

// An observed absence checkpoints the old log. Boot that completes before
// process discovery is read from that checkpoint when the new target appears.
let lateDirectory = directory.appendingPathComponent("late-discovery", isDirectory: true)
try fileManager.createDirectory(at: lateDirectory, withIntermediateDirectories: true)
let lateLog = lateDirectory.appendingPathComponent("Hades.log")
try Data("Done with boot load (previous process)\n".utf8).write(to: lateLog)
var lateEvents: [HadesRunLogEvent] = []
let lateWatcher = HadesRunLogWatcher(directoryURL: lateDirectory) { lateEvents.append($0) }
lateWatcher.targetLifetimeChanged(running: false)
let lateHandle = try FileHandle(forWritingTo: lateLog)
try lateHandle.seekToEnd()
try lateHandle.write(contentsOf: Data("Lua interface destroyed\nDone with boot load\n".utf8))
try lateHandle.close()
lateWatcher.targetLifetimeChanged(running: true)
pump(0.2)
if lateEvents != [.runtimeReset, .bootReady] {
    fatalError("Late target discovery lost current boot events or replayed a previous launch: \(lateEvents)")
}
lateWatcher.stop()

print("hades_run_log_watcher_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-hades-log-watcher-") as td:
    td_path = Path(td)
    main = td_path / "main.swift"
    binary = td_path / "watcher_test"
    main.write_text(textwrap.dedent(main_source), encoding="utf-8")
    compile_swift_test(games=("hades",), harness_sources=[main], output=binary, flags=(), swiftc=SWIFTC, cwd=ROOT)
    support = td_path / "fake-hades-support"
    proc = launch_fixture([str(binary), str(support)], cwd=ROOT, text=True, capture_output=True, journey="native.hades_run_log_watcher", budgets=JOURNEY_BUDGETS)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
