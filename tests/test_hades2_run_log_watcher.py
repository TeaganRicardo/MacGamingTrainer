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

let fileManager = FileManager.default
let directory = fileManager.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/Supergiant Games/Hades II", isDirectory: true)
let logURL = directory.appendingPathComponent("Hades II.log")

try? fileManager.removeItem(at: directory)
try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
try Data("seed\n".utf8).write(to: logURL)

var fired = false
let watcher = Hades2RunLogWatcher {
    fired = true
}
watcher.start()

let setupDeadline = Date().addingTimeInterval(0.35)
while Date() < setupDeadline {
    RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.01))
}

let handle = try FileHandle(forWritingTo: logURL)
try handle.seekToEnd()
try handle.write(contentsOf: Data("2026-09-19 [MainThread] World.cpp INFO| World::Begin()  -> Hub_PreRun\n".utf8))
try handle.synchronize()
try handle.close()

let deadline = Date().addingTimeInterval(2.0)
while !fired && Date() < deadline {
    RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.01))
}

watcher.stop()
if !fired {
    fatalError("appending a World::Begin line did not trigger the watcher")
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
        str(ROOT / "Sources/Hades2/Services/Hades2RunLogWatcher.swift"),
        str(main),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    proc = subprocess.run([str(binary)], cwd=ROOT, text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
