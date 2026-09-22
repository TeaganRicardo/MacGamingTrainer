from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "ContractFixtures/reference_module"

# Linux contracts discover every portable test automatically. This integration
# intentionally compiles SwiftUI/AppKit and runs a real Host backend process.
if sys.platform != "darwin":
    print("reference_fixture_session_integration_macos_only")
    raise SystemExit(0)

SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required")

fixture_source = (FIXTURE / "frontend/ReferenceFixtureModule.swift").read_text(encoding="utf-8")
assert "_ = session" not in fixture_source, (
    "reference fixture still discards the Host-owned TrainerBackendSession"
)
assert "ReferenceFixtureModel(session: session)" in fixture_source
assert "model.enabled.toggle()" not in fixture_source, (
    "fixture content still bypasses the backend session with a local-only toggle"
)

harness = r"""
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func waitUntil(_ seconds: TimeInterval, _ predicate: @escaping () -> Bool) -> Bool {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if predicate() { return true }
        RunLoop.current.run(until: Date().addingTimeInterval(0.01))
    }
    return predicate()
}

let args = CommandLine.arguments
if args.count != 2 { fail("expected temporary backend server path") }

let session = TrainerBackendSession()
let model = ReferenceFixtureModel(
    session: session,
    backendScriptURL: URL(fileURLWithPath: args[1])
)

guard waitUntil(3.0, {
    session.isStarted
        && model.backendAvailable
        && model.backendStatus.backendProtocolVersion == 5
        && model.backendStatus.backendModuleProtocolVersion == 1
}) else {
    fail("reference model did not start the injected Host backend session: \(model.backendStatus)")
}

if model.connected { fail("fixture must start disconnected") }
if model.enabled { fail("fixture must start disabled") }

model.toggleConnectionFromHost()
guard waitUntil(2.0, { model.connected && !model.busy }) else {
    fail("connect did not round-trip through the real session")
}

model.setEnabled(true)
guard waitUntil(2.0, { model.enabled && !model.busy }) else {
    fail("set_enabled did not update model from backend reply")
}

// Prove the model observes the same Host-owned session even when the request
// originates outside the model helper.
var directCompletion: Bool? = nil
session.send(
    "set_enabled",
    params: ["value": false],
    operation: "direct session mutation",
    completion: { directCompletion = $0 }
)
guard waitUntil(2.0, { directCompletion != nil && model.enabled == false }) else {
    fail("model is not projecting replies from the injected session")
}
if directCompletion != true { fail("direct session request failed") }

model.setEnabled(true)
guard waitUntil(2.0, { model.enabled && !model.busy }) else {
    fail("fixture could not re-enable through session")
}
model.setEnabled(false)
guard waitUntil(2.0, { !model.enabled && !model.busy }) else {
    fail("explicit fixture disable did not round-trip through session")
}

model.toggleConnectionFromHost()
guard waitUntil(2.0, { !model.connected && !model.busy }) else {
    fail("disconnect did not round-trip through session")
}

model.refreshFromHost()
guard waitUntil(2.0, { !model.connected && !model.enabled && !model.busy }) else {
    fail("status refresh did not preserve backend truth")
}

var canTerminate: Bool? = nil
model.prepareForTermination { canTerminate = $0 }
guard waitUntil(2.0, { canTerminate == true }) else {
    fail("fixture termination did not complete")
}

print("reference_fixture_session_integration_ok")
"""

assert not (ROOT / "Backend/games/reference_fixture").exists()
assert not (ROOT / "Sources/ReferenceFixture").exists()

with tempfile.TemporaryDirectory(prefix="mgt-reference-fixture-session-") as td:
    temp = Path(td)
    project = temp / "project"
    (project / "Backend/games").mkdir(parents=True)
    (project / "Sources").mkdir(parents=True)

    shutil.copytree(ROOT / "Backend/core", project / "Backend/core")
    shutil.copytree(FIXTURE / "backend", project / "Backend/games/reference_fixture")
    shutil.copytree(ROOT / "Sources/Core", project / "Sources/Core")
    shutil.copytree(FIXTURE / "frontend", project / "Sources/ReferenceFixture")
    shutil.copytree(ROOT / "Tools", project / "Tools")

    generated = project / "Generated/ActiveGameModule.swift"
    subprocess.run(
        [PYTHON, str(project / "Tools/generate_game_binding.py"), "reference_fixture", str(generated)],
        cwd=project,
        check=True,
    )

    main_swift = project / "main.swift"
    main_swift.write_text(textwrap.dedent(harness), encoding="utf-8")
    binary = project / "reference_fixture_session_test"

    core_sources = sorted((project / "Sources/Core").rglob("*.swift"))
    subprocess.run(
        [
            SWIFTC,
            *map(str, core_sources),
            str(project / "Sources/ReferenceFixture/ReferenceFixtureModule.swift"),
            str(generated),
            str(main_swift),
            "-o",
            str(binary),
        ],
        cwd=project,
        check=True,
    )

    home = temp / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    proc = subprocess.run(
        [str(binary), str(project / "Backend/core/server.py")],
        cwd=project,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    assert "reference_fixture_session_integration_ok" in proc.stdout

    log_path = home / "Library/Application Support/MacGamingTrainer/reference_fixture/trainer.log"
    assert log_path.is_file(), "backend log escaped the temporary HOME"

assert not (ROOT / "Backend/games/reference_fixture").exists()
assert not (ROOT / "Sources/ReferenceFixture").exists()

print("reference_fixture_session_integration_test_ok")
