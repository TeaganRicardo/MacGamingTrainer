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

guard CommandLine.arguments.count == 2 else {
    fatalError("temporary log path required")
}

let url = URL(fileURLWithPath: CommandLine.arguments[1])
let tempHome = url.deletingLastPathComponent().appendingPathComponent("home", isDirectory: true)
let expectedScopedURL = tempHome
    .appendingPathComponent("Library/Application Support/MacGamingTrainer", isDirectory: true)
    .appendingPathComponent("hades2", isDirectory: true)
    .appendingPathComponent("trainer.log")
guard TrainerLogSink.moduleLogURL(gameID: "hades2", homeDirectory: tempHome) == expectedScopedURL else {
    fatalError("module log path is not scoped by game id")
}
let scopedSink = TrainerLogSink(gameID: "hades2", homeDirectory: tempHome)
guard scopedSink.url == expectedScopedURL else {
    fatalError("module-owned log sink resolved unexpected path: \(scopedSink.url.path)")
}
scopedSink.append("scoped-one")
scopedSink.flush()
guard (try? String(contentsOf: expectedScopedURL, encoding: .utf8))?.contains("GUI scoped-one") == true else {
    fatalError("module-owned log sink did not write scoped log")
}

try FileManager.default.createDirectory(
    at: url.deletingLastPathComponent(),
    withIntermediateDirectories: true
)
FileManager.default.createFile(atPath: url.path, contents: nil)

let sink = TrainerLogSink(url: url)
sink.append("gui-one")
sink.flush()

let backend = try FileHandle(forWritingTo: url)
try backend.seekToEnd()
try backend.write(contentsOf: Data("backend-one\n".utf8))
try backend.synchronize()
try backend.close()

sink.append("gui-two")
sink.flush()

let content = try String(contentsOf: url, encoding: .utf8)
guard let guiOne = content.range(of: "GUI gui-one\n"),
      let backendOne = content.range(of: "backend-one\n"),
      let guiTwo = content.range(of: "GUI gui-two\n") else {
    fatalError("shared append writers lost or overwrote a log record: \(content)")
}
if !(guiOne.lowerBound < backendOne.lowerBound && backendOne.lowerBound < guiTwo.lowerBound) {
    fatalError("shared log records were reordered or overwritten")
}

for index in 0..<55 {
    let marker = String(format: "rotation-record-%03d", index)
    sink.append(marker + " " + String(repeating: "x", count: 100_000))
}
sink.flush()
let externalWriter = try FileHandle(forWritingTo: url)
try externalWriter.seekToEnd()
try externalWriter.write(contentsOf: Data("backend-after-rotation\n".utf8))
try externalWriter.synchronize()
try externalWriter.close()
sink.append("refresh-after-external-append")
sink.append("oversized-start " + String(repeating: "é", count: 1_200_000) + " oversized-tail")
sink.flush()

let logFiles = try FileManager.default.contentsOfDirectory(at: url.deletingLastPathComponent(), includingPropertiesForKeys: [.fileSizeKey])
    .filter { file in
        let name = file.lastPathComponent
        return name == "trainer.log" || (1...3).contains { name == "trainer.log.\($0)" }
    }
guard logFiles.count <= 4 else {
    fatalError("log rotation retained more than three backups")
}
for file in logFiles {
    let size = try file.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
    guard size <= 1_048_576 else {
        fatalError("rotated log exceeded the 1 MiB bound")
    }
}
let retainedLogs = try logFiles.map { try String(contentsOf: $0, encoding: .utf8) }.joined(separator: "\n")
guard retainedLogs.contains("oversized-tail"), !retainedLogs.contains("rotation-record-000"), retainedLogs.contains("backend-after-rotation") else {
    fatalError("rotation did not preserve the diagnostic tail and discard old history")
}
let oversizedFile = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
guard oversizedFile <= 1_048_576 else {
    fatalError("oversized log entry was not truncated to the file-size bound")
}
guard FileManager.default.fileExists(atPath: url.path + ".1") else {
    fatalError("log rotation did not create the newest backup")
}
print("trainer_log_sink_shared_append_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-log-sink-") as td:
    td = Path(td)
    main = td / "main.swift"
    binary = td / "log_sink_test"
    log = td / "trainer.log"
    main.write_text(textwrap.dedent(main_source), encoding="utf-8")
    subprocess.run([
        SWIFTC,
        str(ROOT / "Sources/Core/Runtime/TrainerLogSink.swift"),
        str(main),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    proc = subprocess.run([str(binary), str(log)], cwd=ROOT, text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
