"""Two live backend workers keep their identity, requests and tools across selection."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "ContractFixtures/reference_module"
HARNESS = r'''
import AppKit
import SwiftUI

@main struct Test {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        app.finishLaunching()
        let server = URL(fileURLWithPath: CommandLine.arguments[1])
        let python = URL(fileURLWithPath: CommandLine.arguments[2])
        let firstSession = TrainerBackendSession(client: BackendClient(process: BackendProcess(executableURL: python)))
        let secondSession = TrainerBackendSession(client: BackendClient(process: BackendProcess(executableURL: python)))
        let first = FirstFixtureModel(session: firstSession, backendScriptURL: server)
        let second = SecondFixtureModel(session: secondSession, backendScriptURL: server)
        let firstContext = TrainerGameContext<FirstFixtureGameModule>(model: first, session: firstSession)
        let secondContext = TrainerGameContext<SecondFixtureGameModule>(model: second, session: secondSession)
        let application = TrainerApplicationCoordinator(contexts: [
            AnyTrainerGameContext(firstContext), AnyTrainerGameContext(secondContext)
        ])
        func wait(line: UInt = #line, _ condition: () -> Bool) {
            let limit = Date(timeIntervalSinceNow: 30)
            while !condition() && Date() < limit { RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.01)) }
            precondition(condition(), "Live context did not reach expected state at \(line); first=\(first.backendStatus), second=\(second.backendStatus)")
        }
        wait { first.backendAvailable && second.backendAvailable && !first.busy && !second.busy }
        firstContext.toggleConnection()
        secondContext.toggleConnection()
        wait { first.connected && second.connected && !first.busy && !second.busy }
        first.setEnabled(true)
        wait { first.enabled && !first.busy }
        var pids: [String: Int] = [:]
        func recordPID(_ session: TrainerBackendSession, _ key: String) {
            session.send("status", operation: "test", reply: { reply in pids[key] = reply.result?["pid"] as? Int })
        }
        recordPID(firstSession, "first")
        recordPID(secondSession, "second")
        wait { pids.count == 2 }
        precondition(pids["first"] != pids["second"])
        let localization = TrainerLocalizationStore()
        var mayClose = false
        var closes = 0
        let window = firstContext.toolWindows.open(id: "document", title: "First draft", localization: localization, theme: .standard) {
            TrainerToolWindowContent(canClose: { mayClose }, onClose: { closes += 1 }) { Text("retained draft") }
        }
        let document = window.contentView
        let pageWindow = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1400, height: 1000),
                                  styleMask: [.titled, .resizable], backing: .buffered, defer: false)
        pageWindow.isReleasedWhenClosed = false
        pageWindow.contentViewController = NSHostingController(rootView:
            TrainerGamePages(application: application).environmentObject(localization).trainerTheme(.standard))
        pageWindow.makeKeyAndOrderFront(nil)
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.2))
        func fields(_ view: NSView) -> [NSTextField] {
            (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
        }
        guard let draftField = fields(pageWindow.contentView!).first(where: { $0.stringValue == "First draft" }) else {
            preconditionFailure("First game editor was not mounted")
        }
        precondition(pageWindow.makeFirstResponder(draftField))
        let editor = draftField.currentEditor() as! NSTextView
        editor.selectAll(nil)
        editor.insertText("unfinished draft", replacementRange: editor.selectedRange())
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.05))
        application.selectedGameID = "second_fixture"
        precondition(first.connected && second.connected && first.enabled)
        NotificationCenter.default.post(name: NSApplication.didBecomeActiveNotification, object: app)
        precondition(first.activations > 0 && second.activations > 0, "Hidden game lost lifecycle subscription")
        first.setEnabled(false)
        second.setEnabled(true)
        wait { !first.enabled && second.enabled && !first.busy && !second.busy }
        recordPID(firstSession, "firstAfter")
        recordPID(secondSession, "secondAfter")
        wait { pids.count == 4 }
        precondition(pids["first"] == pids["firstAfter"] && pids["second"] == pids["secondAfter"])
        application.selectedGameID = "first_fixture"
        precondition(application.context(id: "first_fixture")?.typed(as: FirstFixtureGameModule.self) === firstContext)
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.1))
        precondition(fields(pageWindow.contentView!).contains { $0 === draftField && $0.stringValue == "unfinished draft" },
                     "Page selection discarded a view-local input draft")
        precondition(window.contentView === document && window.isVisible)
        first.postponeTermination = true
        var terminated: Bool?
        application.prepareForTermination { terminated = true }
        RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.05))
        precondition(terminated == nil && firstSession.isStarted && secondSession.isStarted,
                     "Quit bypassed a tool-window write barrier")
        precondition(application.terminationRequested && !firstContext.toolWindows.interactionEnabled)
        mayClose = true
        first.refreshFromHost()
        wait { first.pendingTermination != nil && !second.busy }
        second.setEnabled(false)
        precondition(second.busy)
        first.finishPostponedTermination()
        precondition(terminated == nil && secondSession.isStarted,
                     "Later context's newly busy operation was interrupted")
        wait { terminated == true && !firstSession.isStarted && !secondSession.isStarted }
        precondition(closes == 1)
        pageWindow.close()
        print("multi_game_contexts_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-multi-context-") as directory:
    project = Path(directory)
    shutil.copytree(ROOT / "Backend/core", project / "Backend/core")
    shutil.copytree(ROOT / "Sources/Core", project / "Sources/Core")
    shutil.copytree(ROOT / "Tools", project / "Tools")
    shutil.copy2(ROOT / "Info.plist", project / "Info.plist")
    modules = []
    frontends = []
    for word, name in (("First", "first_fixture"), ("Second", "second_fixture")):
        destination = project / "Backend/games" / name
        shutil.copytree(FIXTURE / "backend", destination)
        adapter = destination / "adapter.py"
        adapter.write_text("import os, time\n" + adapter.read_text().replace(
            "'enabled': self.enabled}", "'enabled': self.enabled, 'pid': os.getpid()}").replace(
            "if command == 'set_enabled':", "if command == 'set_enabled':\n            time.sleep(0.3)"))
        manifest = json.loads((destination / "module.json").read_text())
        manifest["id"] = name
        manifest["displayName"] = word + " Fixture"
        manifest["backend"]["adapter"] = f"games.{name}.adapter:ReferenceFixtureAdapter"
        manifest["frontend"]["sourceDirectory"] = f"Sources/{word}Fixture"
        manifest["frontend"]["moduleType"] = word + "FixtureGameModule"
        manifest["targetApplication"]["processName"] = word + "InertTarget"
        manifest["targetApplication"]["bundleIdentifier"] = "test." + name
        manifest.pop("app", None)
        (destination / "module.json").write_text(json.dumps(manifest))
        source = project / manifest["frontend"]["sourceDirectory"] / (word + "Module.swift")
        source.parent.mkdir(parents=True)
        source.write_text((FIXTURE / "frontend/ReferenceFixtureModule.swift").read_text().replace(
            "ReferenceFixture", word + "Fixture").replace(
            "    func prepareForTermination(completion: @escaping () -> Void) {",
            "    @Published var postponeTermination = false\n    var pendingTermination: (() -> Void)?\n"
            "    func finishPostponedTermination() {\n        backendSession.stop()\n        let done = pendingTermination\n"
            "        pendingTermination = nil\n        done?()\n    }\n"
            "    func prepareForTermination(completion: @escaping () -> Void) {\n"
            "        if postponeTermination { pendingTermination = completion; return }").replace(
            "    func setEnabled(_ value: Bool)",
            "    @Published var activations = 0\n    func hostDidBecomeActive() { activations += 1 }\n    func setEnabled(_ value: Bool)").replace(
            "    @ObservedObject var model:",
            '    @State private var draft = "' + word + ' draft"\n    @ObservedObject var model:').replace(
            "        VStack(alignment: .leading, spacing: 12) {",
            '        VStack(alignment: .leading, spacing: 12) {\n            TextField("Draft", text: $draft)'))
        frontends.append(source)
        modules.append(name)
    generated = project / "Generated.swift"
    subprocess.run([sys.executable, str(project / "Tools/generate_game_binding.py"),
                    ",".join(modules), str(generated)], check=True, cwd=project)
    main = project / "Harness.swift"
    main.write_text(HARNESS)
    binary = project / "test"
    subprocess.run(["swiftc", "-parse-as-library", *map(str, sorted((project / "Sources/Core").rglob("*.swift"))),
                    *map(str, frontends), str(generated), str(main), "-o", str(binary)], check=True)
    env = {**os.environ, "HOME": str(project / "home"), "PYTHONDONTWRITEBYTECODE": "1"}
    Path(env["HOME"]).mkdir()
    subprocess.run([str(binary), str(project / "Backend/core/server.py"), sys.executable],
                   cwd=project, env=env, check=True, timeout=90)
