"""Exercise real App admission with inert UI/backend and isolated OS processes."""
import json
from pathlib import Path
import re
import select
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
assert SWIFTC, "swiftc is required for Host ownership behavior"

app_source = (ROOT / "Sources/Core/Host/TrainerGameContext.swift").read_text()
start = app_source.index("    convenience init() {") + len("    convenience init() {")
end = start
level = 1
while level:
    if app_source[end] == "{":
        level += 1
    elif app_source[end] == "}":
        level -= 1
    end += 1
app_initializer = app_source[start:end - 1].replace("Module.descriptor", "ActiveGameModule.descriptor").replace(
    "self.init(model: Module.makeModel(session: session), session: session)",
    "self.backendSession = session\n        self._model = StateObject(wrappedValue: ActiveGameModule.makeModel(session: session))")
startup_source = (ROOT / "Sources/Core/Host/TrainerApplicationStartup.swift").read_text().replace("import AppKit\n", "")
strings = {}
for language in ("zh-CN", "en"):
    text = (ROOT / f"Resources/Localization/{language}.lproj/Host.strings").read_text()
    strings[language] = dict(re.findall(r'^"([^"\n]+)" = "([^"\n]*)";', text, re.M))

# Execute both production startup owners and the App initializer. Only native UI,
# localization, and the model/backend are replaced; the model records a synthetic
# attach attempt. No app bundle/debugger/target process or user/game path is used.
harness = r'''
import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif
let directory = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let targetBundle = CommandLine.arguments[2]
let processName = CommandLine.arguments[3]
let uiMode = CommandLine.arguments[4]
let language = CommandLine.arguments[5]
let localizationTables = try! JSONSerialization.jsonObject(with: Data(CommandLine.arguments[6].utf8)) as! [String: [String: String]]
func record(_ event: String) {
    let fd = open(directory.appendingPathComponent("events").path, O_WRONLY | O_CREAT | O_APPEND, 0o600)
    precondition(fd >= 0)
    let data = Data((event + "\n").utf8)
    data.withUnsafeBytes { precondition(write(fd, $0.baseAddress, $0.count) == $0.count) }
    close(fd)
}
// Redirect only the production startup directory lookup into the fixture.
enum FileManager {
    static let `default` = FixtureFiles()
}
final class FixtureFiles {
    func url(for directoryKind: Foundation.FileManager.SearchPathDirectory,
             in domain: Foundation.FileManager.SearchPathDomainMask,
             appropriateFor: URL?, create: Bool) throws -> URL { directory }
    func createDirectory(at url: URL, withIntermediateDirectories: Bool,
                         attributes: [FileAttributeKey: Any]?) throws {
        try Foundation.FileManager.default.createDirectory(at: url,
            withIntermediateDirectories: withIntermediateDirectories, attributes: attributes)
    }
}
enum Bundle { static let main = FixtureBundle() }
struct FixtureBundle { let bundleIdentifier: String? = "test.trainer" }
final class NSRunningApplication {
    let bundleIdentifier: String? = "test.trainer"
    init?(processIdentifier: Int32) { if uiMode == "missing" { return nil } }
    struct ActivationOptions: OptionSet {
        let rawValue: Int
        static let activateAllWindows = Self(rawValue: 1)
    }
    func activate(options: ActivationOptions) -> Bool {
        if uiMode == "activate" { print("activated"); fflush(stdout); return true }
        return false
    }
}
final class FixtureApplication {
    enum Policy { case regular }
    func setActivationPolicy(_ policy: Policy) {}
    func activate(ignoringOtherApps: Bool) {}
}
enum NSApplication { static let shared = FixtureApplication() }
final class NSAlert {
    enum Style { case warning }
    var alertStyle = Style.warning
    var messageText = "", informativeText = ""
    func addButton(withTitle: String) { precondition(!withTitle.hasPrefix("host.")) }
    func runModal() {
        print("alert \(messageText)|\(informativeText.replacingOccurrences(of: "\n", with: " "))")
        fflush(stdout)
    }
}
@MainActor final class TrainerLocalizationStore {
    func localized(_ key: String) -> String { localizationTables[language]?[key] ?? key }
}
struct Descriptor {
    var targetProcessName: String { processName }
    var targetBundleIdentifier: String { targetBundle }
    var targetExecutablePathSuffix: String { "" }
}
struct StateObject<T> { let wrappedValue: T }
final class TrainerBackendSession {}
enum ActiveGameModule {
    static let descriptor = Descriptor()
    static func makeModel(session: TrainerBackendSession) -> Int {
        record("attach \(getpid())")
        return 1
    }
}
''' + startup_source + r'''
@MainActor final class HostHarness {
    let ownership: TrainerTargetOwnership
    let backendSession: TrainerBackendSession
    let _model: StateObject<Int>
    init() {
''' + app_initializer + r'''
    }
}
@main struct FixtureMain {
    @MainActor static func main() {
        _ = readLine() // synchronized concurrent launch admission
        let host = HostHarness()
        print("ready")
        fflush(stdout)
        _ = readLine() // hold ownership until released or killed
        withExtendedLifetime(host) {}
    }
}
'''


def launch(binary, directory, bundle="test.game", name="Synthetic Target", mode="activate", language="en"):
    process = subprocess.Popen([str(binary), str(directory), bundle, name, mode, language,
                                json.dumps(strings, ensure_ascii=False)], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return process


def start(process):
    process.stdin.write("go\n")
    process.stdin.flush()
    return read_reply(process)


def read_reply(process):
    readable, _, _ = select.select([process.stdout], [], [], 10)
    assert readable, "synthetic Host did not complete startup admission within 10 seconds"
    return process.stdout.readline().strip()


def finish(process, expected=0):
    if process.poll() is None:
        try:
            process.stdin.write("stop\n")
            process.stdin.flush()
        except BrokenPipeError:
            pass
    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == expected, (process.returncode, stdout, stderr)
    return stdout.strip()


def attempts(directory):
    events = directory / "events"
    return events.read_text().splitlines() if events.exists() else []


with tempfile.TemporaryDirectory(prefix="mgt-host-ownership-") as temporary:
    temporary = Path(temporary)
    source = temporary / "main.swift"
    binary = temporary / "host"
    source.write_text(harness)
    subprocess.run([SWIFTC, "-parse-as-library", str(ROOT / "Sources/Core/Host/TrainerTargetOwnership.swift"),
                    str(source), "-o", str(binary)], check=True, cwd=ROOT)
    directory = temporary / "ownership"
    directory.mkdir()
    processes = [launch(binary, directory) for _ in range(2)]
    try:
        for process in processes:
            process.stdin.write("go\n")
            process.stdin.flush()
        replies = [read_reply(process) for process in processes]
        assert len(attempts(directory)) == 1, f"concurrent App launches attempted duplicate attach: {attempts(directory)}; {replies}"
        assert replies.count("ready") == 1, replies
        refusal = next(reply for reply in replies if reply != "ready")
        assert refusal == "activated" or "Another Trainer instance" in refusal, replies
        owner = processes[replies.index("ready")]
        lock = next(directory.rglob("*.lock"))
        original_inode = lock.stat().st_ino
        assert int(lock.read_text()) == owner.pid

        # An active owner blocks even a different executable copy/name. Both
        # activation failure and owner lookup failure have actionable fallback.
        for mode, language, title, step in [
            ("reject", "en", "Another Trainer instance", "Use the existing Trainer window"),
            ("missing", "zh-CN", "另一个修改器实例", "请使用已打开的修改器窗口"),
        ]:
            contender = launch(binary, directory, name="Another Executable", mode=mode, language=language)
            reply = start(contender)
            assert title in reply and step in reply, reply
            assert not reply.startswith("ready"), reply
            finish(contender)
            assert len(attempts(directory)) == 1
            assert lock.stat().st_ino == original_inode and int(lock.read_text()) == owner.pid

        # A genuinely different module target can run concurrently.
        independent = launch(binary, directory, bundle="test.othergame")
        assert start(independent) == "ready"
        finish(independent)
        assert len(attempts(directory)) == 2
    finally:
        for process in processes:
            finish(process)

    # Clean shutdown releases the kernel lease while retaining the same inode.
    replacement = launch(binary, directory)
    assert start(replacement) == "ready"
    assert lock.stat().st_ino == original_inode
    assert int(lock.read_text()) == replacement.pid
    # Force-quit leaves a stale PID/file but must not permanently block launch.
    replacement.kill()
    replacement.communicate(timeout=10)
    recovered = launch(binary, directory)
    assert start(recovered) == "ready"
    assert lock.stat().st_ino == original_inode
    assert int(lock.read_text()) == recovered.pid
    finish(recovered)

    # Targets without bundle identity coordinate by declared process name.
    unnamed = launch(binary, directory, bundle="")
    assert start(unnamed) == "ready"
    contender = launch(binary, directory, bundle="")
    assert start(contender) == "activated"
    finish(contender)
    finish(unnamed)

    # An inaccessible ownership directory fails before session/model creation.
    blocked = temporary / "blocked"
    blocked.mkdir()
    (blocked / "MacGamingTrainer").write_text("not a directory")
    failure = launch(binary, blocked)
    reply = start(failure)
    assert "Unable to establish Trainer ownership" in reply, reply
    assert "file access error" in reply, reply
    finish(failure, expected=1)
    assert not attempts(blocked)

print("host_target_ownership_ok: concurrent launch, active owner, focus/fallback, clean release, crash recovery, target isolation, fail-closed startup")


# A synthetic executable exercises the Hades I path probe without starting the game.
clang = shutil.which("clang")
assert clang, "clang is required for the synthetic process identity fixture"

with tempfile.TemporaryDirectory(prefix="mgt-target-process-") as temporary:
    temporary = Path(temporary)
    fixture_source = temporary / "fixture.c"
    fixture_source.write_text("#include <unistd.h>\nint main(void) { for (;;) sleep(1); }\n")
    target_executable = temporary / "Hades/Game.macOS.app/Contents/MacOS/Game.macOS"
    unrelated_executable = temporary / "Other/Game.macOS"
    for executable in (target_executable, unrelated_executable):
        executable.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([clang, str(fixture_source), "-o", str(executable)], check=True)

    harness = r'''
import AppKit
import Foundation

@main struct FixtureMain {
    static func main() {
        let expectedPID = pid_t(Int32(CommandLine.arguments[1])!)
        let expectedRunning = CommandLine.arguments[2] == "true"
        let monitor = TrainerTargetProcessMonitor(
            processName: "Game.macOS",
            bundleIdentifier: "",
            executablePathSuffix: "Hades/Game.macOS.app/Contents/MacOS/Game.macOS"
        )
        precondition(monitor.isRunning == expectedRunning, "unexpected target presence")
        if expectedRunning {
            precondition(monitor.targetObservation.processIdentifier == expectedPID,
                         "monitor returned the wrong process identifier")
        }
    }
}
'''
    swift_source = temporary / "monitor.swift"
    swift_binary = temporary / "monitor"
    swift_source.write_text(harness)
    subprocess.run(
        [
            SWIFTC,
            "-parse-as-library",
            str(ROOT / "Sources/Core/Runtime/TrainerTargetProcessMonitor.swift"),
            str(swift_source),
            "-o",
            str(swift_binary),
        ],
        check=True,
        cwd=ROOT,
    )

    for executable, expected in (
        (target_executable, "true"),
        (unrelated_executable, "false"),
    ):
        process = subprocess.Popen([str(executable)])
        try:
            subprocess.run(
                [str(swift_binary), str(process.pid), expected],
                check=True,
                timeout=15,
                cwd=ROOT,
            )
        finally:
            process.terminate()
            process.wait(timeout=5)

print("host_target_process_monitor_ok: kernel path discovery and same-name rejection")
