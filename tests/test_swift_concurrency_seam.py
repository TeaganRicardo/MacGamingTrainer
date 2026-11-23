"""Verify build.sh typecheck strict-concurrency enforcement and the @MainActor module seam."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MGT_PLATFORM = "macos"
MGT_INPUTS = ("build.sh",)

TESTS_DIR = Path(__file__).resolve().parent
ROOT = TESTS_DIR.parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from swift_test_compiler import compile_swift_test  # noqa: E402

if sys.platform != "darwin":
    print("swift_concurrency_seam_macos_only")
    raise SystemExit(0)

# Minimal TrainerCore surface required by build.sh's generated binding/catalog.
MINIMAL_CORE_SWIFT = """
import SwiftUI

package struct GameModuleDescriptor: Sendable {
    package let id: String

    package init(
        id: String,
        displayName: String,
        targetProcessName: String,
        targetBundleIdentifier: String,
        targetExecutablePathSuffix: String,
        expectedHostProtocolVersion: Int,
        expectedModuleProtocolVersion: Int,
        supportsSaveManagement: Bool
    ) {
        self.id = id
    }
}

@MainActor
package protocol TrainerHostModel {}

package struct TrainerWorkbenchSectionItem: Identifiable {
    package let id: String
    package init(id: String) { self.id = id }
}

package struct TrainerWorkbenchSearchCatalog {}
package struct TrainerToolWindowActions {}
package struct TrainerManagementCatalog {}

package protocol TrainerGameModule {
    associatedtype Model: TrainerHostModel

    @MainActor static func workbenchSections(model: Model) -> [TrainerWorkbenchSectionItem]
    @MainActor static func workbenchSearch(model: Model) -> TrainerWorkbenchSearchCatalog?
    @MainActor static func makeManagementCatalog(
        model: Model,
        localization: TrainerLocalizationStore,
        toolWindows: TrainerToolWindowActions
    ) -> TrainerManagementCatalog?
}

package final class TrainerGameContext<M: TrainerGameModule> {
    @MainActor package var model: M.Model { fatalError() }
    @MainActor package init() {}
    package func managementGroups(localization: TrainerLocalizationStore) -> [Any] { [] }
}

package final class AnyTrainerGameContext {
    @MainActor package init<M: TrainerGameModule>(_ context: TrainerGameContext<M>) {}
}

@MainActor
package final class TrainerApplicationCoordinator: ObservableObject {
    package var terminationRequested = false
    package var selectedGameID = ""

    package func context(id: String) -> ContextRef? { nil }

    package struct ContextRef {
        package func typed<M: TrainerGameModule>(as type: M.Type) -> TrainerGameContext<M>? { nil }
    }
}

@MainActor
package final class TrainerLocalizationStore: ObservableObject {
    package func localized(_ key: String) -> String { key }
}

package struct TrainerManagementCommandMenu: Commands {
    package init(title: String, groups: [Any]) {}
    package var body: some Commands { CommandGroup(after: .appInfo) { EmptyView() } }
}
"""

FIXTURE_MODULE_BASE = """
import SwiftUI
import TrainerCore

final class FixtureModel: TrainerHostModel {}

struct FixtureModule: TrainerGameModule {
    static func workbenchSections(model: FixtureModel) -> [TrainerWorkbenchSectionItem] { [] }
    static func workbenchSearch(model: FixtureModel) -> TrainerWorkbenchSearchCatalog? { nil }
    static func makeManagementCatalog(
        model: FixtureModel,
        localization: TrainerLocalizationStore,
        toolWindows: TrainerToolWindowActions
    ) -> TrainerManagementCatalog? {
        nil
    }
}
"""

APP_BASE = """
import TrainerCore

@main
struct FixtureEntry {
    @MainActor static func main() {
        _ = TrainerGameCatalog.descriptors
    }
}
"""

# Triggers a warning only when -strict-concurrency=targeted is active (Sendable
# closure capture in a @MainActor context); turns into an error only when
# warnings are fatal in typecheck mode.
CONCURRENCY_WARNING_SNIPPET = """
final class NonSendableConcurrencyBox {
    var count = 0
}

@MainActor
func runSendableProbe(_ work: @Sendable () -> Void) {
    work()
}

@MainActor
func triggerStrictConcurrencyWarning() {
    let box = NonSendableConcurrencyBox()
    runSendableProbe { _ = box.count }
    box.count += 1
}
"""


def _write_synthetic_build_repo(repo: Path) -> tuple[Path, Path]:
    repo.mkdir()
    shutil.copy2(ROOT / "build.sh", repo / "build.sh")
    (repo / "build.sh").chmod(0o755)
    shutil.copytree(ROOT / "Tools", repo / "Tools")
    shutil.copytree(ROOT / "Backend/core", repo / "Backend/core")
    (repo / "Backend/__init__.py").write_text("", encoding="utf-8")
    shutil.copy2(ROOT / "Info.plist", repo / "Info.plist")
    (repo / "app.json").write_text(
        json.dumps({
            "schemaVersion": 1,
            "app": {
                "bundleIdentifier": "com.example.concurrencyfixture",
                "displayName": "Concurrency Fixture",
            },
            "architectures": ["arm64"],
            "minimumMacOS": "14.0",
            "modules": ["fixture"],
        }),
        encoding="utf-8",
    )
    backend = repo / "Backend/games/fixture"
    backend.mkdir(parents=True)
    (backend / "__init__.py").write_text("", encoding="utf-8")
    (backend / "adapter.py").write_text("", encoding="utf-8")
    (backend / "module.json").write_text(
        json.dumps({
            "schemaVersion": 1,
            "id": "fixture",
            "displayName": "Fixture",
            "protocolVersion": 1,
            "backend": {"adapter": "games.fixture.adapter:Adapter"},
            "frontend": {
                "sourceDirectory": "Sources/Fixture",
                "moduleType": "FixtureModule",
                "architectures": ["arm64"],
                "minimumMacOS": "14.0",
            },
            "targetApplication": {
                "processName": "FixtureGame",
                "bundleIdentifier": "com.example.fixturegame",
            },
        }),
        encoding="utf-8",
    )
    core_dir = repo / "Sources/Core"
    core_dir.mkdir(parents=True)
    (core_dir / "Core.swift").write_text(MINIMAL_CORE_SWIFT, encoding="utf-8")

    fixture_dir = repo / "Sources/Fixture"
    fixture_dir.mkdir(parents=True)
    fixture_swift = fixture_dir / "FixtureModule.swift"
    fixture_swift.write_text(FIXTURE_MODULE_BASE, encoding="utf-8")

    app_swift = repo / "Sources/App.swift"
    app_swift.write_text(APP_BASE, encoding="utf-8")
    return fixture_swift, app_swift


def _run_typecheck(repo: Path) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key != "MGT_GAME_ID"}
    return subprocess.run(
        ["bash", str(repo / "build.sh"), "--typecheck", "--all"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _verify_build_sh_strict_concurrency() -> None:
    with tempfile.TemporaryDirectory(prefix="mgt-concurrency-build-") as tmp:
        repo = Path(tmp) / "repo"
        fixture_swift, app_swift = _write_synthetic_build_repo(repo)

        clean = _run_typecheck(repo)
        assert clean.returncode == 0, clean.stdout + "\n" + clean.stderr

        # Library module strict-concurrency warning must fail typecheck.
        fixture_swift.write_text(FIXTURE_MODULE_BASE + CONCURRENCY_WARNING_SNIPPET, encoding="utf-8")
        library_fail = _run_typecheck(repo)
        assert library_fail.returncode != 0, (
            "build.sh --typecheck passed despite strict-concurrency warning in a library module:\n"
            + library_fail.stdout
            + "\n"
            + library_fail.stderr
        )

        # App module strict-concurrency warning must fail typecheck too.
        fixture_swift.write_text(FIXTURE_MODULE_BASE, encoding="utf-8")
        app_swift.write_text(APP_BASE + CONCURRENCY_WARNING_SNIPPET, encoding="utf-8")
        app_fail = _run_typecheck(repo)
        assert app_fail.returncode != 0, (
            "build.sh --typecheck passed despite strict-concurrency warning in the App module:\n"
            + app_fail.stdout
            + "\n"
            + app_fail.stderr
        )


SEAM_HARNESS_PREFIX = """
import Foundation
import SwiftUI

final class SeamStubModel: TrainerHostModel {
    var connected = false
    var statusTitle = TrainerTextToken(key: "host.disconnected")
    var connectionDetailText = TrainerTextToken(key: "")
    var hostActionsEnabled = true

    func connectFromHost(reason: TrainerHostConnectReason) {}
    func disconnectFromHost() {}
    func refreshFromHost() {}
    func backendPayloadTarget(_ payload: [String: Any]) -> TrainerBackendPayloadTarget { .independent }
}

enum SeamStubModule: TrainerGameModule {
    static let descriptor = GameModuleDescriptor(
        id: "seam_stub",
        displayName: "Seam Stub",
        targetProcessName: "SeamStub",
        targetBundleIdentifier: "com.example.seamstub",
        expectedHostProtocolVersion: 6,
        expectedModuleProtocolVersion: 1,
        supportsSaveManagement: false
    )
    static let presentation = TrainerGamePresentation()

    static func makeModel(services: TrainerModuleServices) -> SeamStubModel { SeamStubModel() }
    static func makeContent(model: SeamStubModel) -> some View { EmptyView() }
    static func presentationText(
        key: String,
        arguments: [String],
        language: TrainerPresentationLanguage
    ) -> String { key }
}

func makeSnapshot() -> TrainerSaveSnapshot {
    TrainerSaveSnapshot(row: [
        "id": "s1",
        "name": "s1",
        "createdAt": "2026-01-01T00:00:00Z",
        "sizeBytes": 1,
        "protected": false,
        "automatic": false,
    ])!
}
"""

VALID_SEAM_CALLER = SEAM_HARNESS_PREFIX + """
@MainActor
func exerciseSeam<Module: TrainerGameModule>(_ type: Module.Type) {
    let services = TrainerModuleServices(
        descriptor: Module.descriptor,
        session: TrainerBackendSession(),
        logSink: TrainerLogSink(gameID: Module.descriptor.id),
        targetObservation: TrainerTargetObservation(isRunning: false, launchGeneration: 0, processIdentifier: nil)
    )
    let model = Module.makeModel(services: services)
    _ = Module.makeContent(model: model)
    _ = Module.workbenchSections(model: model)
    _ = Module.workbenchSearch(model: model)
    let localization = TrainerLocalizationStore()
    _ = Module.makeManagementCatalog(model: model, localization: localization, toolWindows: .none)
    _ = Module.managedBackupEditor
    model.connectFromHost(reason: .manual)
    model.launchActionFromHost?()
}

// Non-isolated callers verify the parameter closures themselves carry @MainActor:
// removing @MainActor from either closure parameter makes model.refreshFromHost() invalid here.
func exerciseHotkeyCallbacks(services: TrainerModuleServices, model: SeamStubModel) async {
    _ = await services.makeHotkeys(
        registrationChanged: { _ in model.refreshFromHost() },
        action: { _ in model.refreshFromHost() }
    )
}

@main
struct SeamValidMain {
    @MainActor static func main() {
        exerciseSeam(SeamStubModule.self)
    }
}
"""

OFF_ACTOR_PROBES: dict[str, str] = {
    "makeModel": """
func offActor<Module: TrainerGameModule>(_ type: Module.Type, services: TrainerModuleServices) {
    _ = Module.makeModel(services: services)
}
""",
    "makeContent": """
func offActor<Module: TrainerGameModule>(_ type: Module.Type, model: Module.Model) {
    _ = Module.makeContent(model: model)
}
""",
    "workbenchSections": """
func offActor<Module: TrainerGameModule>(_ type: Module.Type, model: Module.Model) {
    _ = Module.workbenchSections(model: model)
}
""",
    "workbenchSearch": """
func offActor<Module: TrainerGameModule>(_ type: Module.Type, model: Module.Model) {
    _ = Module.workbenchSearch(model: model)
}
""",
    "makeManagementCatalog": """
func offActor<Module: TrainerGameModule>(
    _ type: Module.Type,
    model: Module.Model,
    localization: TrainerLocalizationStore
) {
    _ = Module.makeManagementCatalog(model: model, localization: localization, toolWindows: .none)
}
""",
    "managedBackupEditor": """
func offActor<Module: TrainerGameModule>(_ type: Module.Type) {
    _ = Module.managedBackupEditor
}
""",
    "managedBackupEditorClosure": """
@MainActor
func offActorCall<Module: TrainerGameModule>(
    _ type: Module.Type,
    createModel: @MainActor @Sendable @escaping () -> Module.Model
) {
    if let editor = Module.managedBackupEditor {
        Task.detached {
            let model = await createModel()
            let snapshot = makeSnapshot()
            _ = editor(model, snapshot)
        }
    }
}
""",
    "hostModelMethod": """
func offActor<Model: TrainerHostModel>(_ model: Model) {
    model.connectFromHost(reason: .manual)
}
""",
    "launchActionFromHost": """
@MainActor
func offActorCall<Model: TrainerHostModel>(_ model: Model) {
    if let action = model.launchActionFromHost {
        Task.detached {
            action()
        }
    }
}
""",
    "moduleServices": """
func offActor(services: TrainerModuleServices) {
    _ = services.backendStatus
}
""",
}


def _verify_main_actor_seam() -> None:
    flags = ("-parse-as-library", "-strict-concurrency=targeted", "-warnings-as-errors")
    with tempfile.TemporaryDirectory(prefix="mgt-mainactor-seam-") as tmp:
        directory = Path(tmp)
        valid_source = directory / "ValidSeamCaller.swift"
        valid_source.write_text(VALID_SEAM_CALLER, encoding="utf-8")
        compile_swift_test(
            harness_sources=[valid_source],
            output=directory / "valid_seam",
            games=(),
            flags=flags,
        )

        for name, probe in OFF_ACTOR_PROBES.items():
            probe_source = directory / f"probe_{name}.swift"
            probe_source.write_text(
                SEAM_HARNESS_PREFIX + probe + "\n@main struct ProbeMain { @MainActor static func main() {} }\n",
                encoding="utf-8",
            )
            try:
                compile_swift_test(
                    harness_sources=[probe_source],
                    output=directory / f"probe_{name}",
                    games=(),
                    flags=flags,
                )
            except subprocess.CalledProcessError:
                continue
            raise AssertionError(f"Off-actor seam probe {name!r} unexpectedly compiled")


_verify_build_sh_strict_concurrency()
_verify_main_actor_seam()
print("swift_concurrency_seam_ok")
