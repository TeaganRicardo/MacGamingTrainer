import AppKit
import Foundation
import SwiftUI

private func require(_ value: @autoclosure () -> Bool, _ message: String) { if !value() { fatalError(message) } }
private func pump(_ seconds: TimeInterval = 0.08) { RunLoop.current.run(until: Date().addingTimeInterval(seconds)) }
private func until(_ message: String, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !condition() && Date() < deadline { pump(0.02) }
    require(condition(), message)
}
private func fields(_ view: NSView) -> [NSTextField] { (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields) }

@main struct SaveContainerPlayerJourney {
    @MainActor static func main() throws {
        let base = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MGT_SAVE_JOURNEY_FIXTURE"]!)
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited); app.finishLaunching(); enableNativeAccessibility()
        let defaults = InMemoryDefaults()
        defaults.set(TrainerPresentationLanguage.en.rawValue, forKey: TrainerLocalizationStore.userDefaultsKey)
        let localization = TrainerLocalizationStore(defaults: defaults)
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
            Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        func text(_ key: String) -> String { Hades2GameModule.resolveText(key: key, localization: localization) }
        let session = TrainerBackendSession(client: BackendClient(process: BackendProcess(
            executableURL: URL(fileURLWithPath: CommandLine.arguments[1]), argumentsPrefix: ["-u"])))
        try session.start(descriptor: Hades2GameModule.descriptor,
            backendScriptURL: URL(fileURLWithPath: CommandLine.arguments[2]),
            applyPayload: { _ in }, resetGameState: {}, log: { _ in }, onStatusChange: { _ in })
        let windows = TrainerToolWindowStore()
        func open(_ model: Hades2SaveEditorModel) -> NSWindow {
            windows.open(id: "container-journey", title: "Save container", localization: localization, theme: .standard) {
                TrainerToolWindowContent(canClose: { !model.busy }, onClose: model.close) { Hades2SaveEditorView(model: model) }
            }
        }
        let model = Hades2SaveEditorModel(session: session)
        let window = open(model)
        until("Save open failed") { model.workspaceID != nil && !model.busy && !model.querying && !model.items.isEmpty }
        model.selectTarget("main/Profile2.sav"); until("target selection failed") { !model.busy }
        let root = window.contentView!
        let original = try Data(contentsOf: base.appendingPathComponent("saves/Profile1.sav"))
        let targetBefore = try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav"))
        func edit(_ field: NSTextField, _ value: String) {
            let owner = field.window!
            field.scrollToVisible(field.bounds)
            require(owner.makeFirstResponder(field), "native input focus failed")
            let editor = field.currentEditor() as! NSTextView
            editor.selectAll(nil); editor.insertText(value, replacementRange: editor.selectedRange())
            owner.makeFirstResponder(nil); pump()
        }
        func search(_ value: String) -> Hades2SaveEditorEntry {
            let input = fields(root).first { $0.placeholderString == text("hades2.saveEditor.workbench.search") }!
            edit(input, value)
            until("container search failed: " + value) {
                !model.querying && model.items.count == 1 &&
                (model.items[0].rawID == value || model.items[0].displayName.localizedCaseInsensitiveContains(value))
            }
            return model.items[0]
        }
        func press(_ view: NSView, _ key: String) {
            guard let control = namedNativeControl(view, role: "AXButton", name: text(key)), control.enabled, control.press()
            else { fatalError("native button missing: " + key) }
            pump()
        }
        func browse(_ kind: String, _ title: String) {
            let row = search(title)
            require(row.path == [.saveContainer(kind)], "container namespace decoded as a Lua key")
            press(root, "hades2.saveEditor.workbench.browse")
            until("container browse failed") { !model.querying && model.advancedPath == [.saveContainer(kind)] }
        }
        func scalar(_ key: String, _ value: String) {
            let row = search(key)
            let field = fields(root).first { $0.isEditable && $0.accessibilityLabel() == row.displayName }!
            edit(field, value)
            until("container scalar did not stage") { !model.busy && model.pendingActions.contains { $0.entryID == row.id } }
        }
        func openValue(_ row: Hades2SaveEditorEntry) -> NSView {
            let button = nativeAccessibilityControls(root).first { $0.identifier == "saveEditor.editValue." + row.id }!
            require(button.press(), "typed container editor failed")
            until("container sheet did not open") { window.attachedSheet != nil }
            let sheet = window.attachedSheet!.contentView!
            until("typed container value did not load") {
                fields(sheet).contains { $0.isEditable && $0.accessibilityLabel()?.contains(text("hades2.saveEditor.advanced.typedValue")) == true }
            }
            return sheet
        }
        func typed(_ key: String, _ value: String) {
            let row = search(key), sheet = openValue(row)
            edit(fields(sheet).first { $0.isEditable && $0.accessibilityLabel()?.contains(text("hades2.saveEditor.advanced.typedValue")) == true }!, value)
            until("typed payload did not stage") { !model.busy && model.pendingActions.contains { $0.entryID == row.id } }
            press(sheet, "host.done"); until("container sheet remained open") { window.attachedSheet == nil }
        }
        model.selectDomain(.advanced)
        until("Advanced root failed") { !model.querying && model.items.contains { $0.path == [.saveContainer("header")] } }
        browse("header", "Save container header")
        scalar("timestamp", "18446744073709551614")
        scalar("completed_runs", "4294967295")
        model.leaveAdvanced(); until("header leave failed") { !model.querying && model.advancedPath.isEmpty }
        browse("payload", "Extra Lua payloads")
        scalar("1", "-5.25")
        typed("2", "{\"luaType\":\"table\",\"entries\":[{\"key\":{\"luaType\":\"string\",\"value\":\"Child\"},\"value\":{\"luaType\":\"string\",\"value\":\"container table\"}}]}")
        typed("3", "{\"luaType\":\"number\",\"encoding\":\"nonfinite\",\"value\":\"-inf\"}")
        let infiniteTable = search("4")
        press(root, "hades2.saveEditor.workbench.browse")
        until("infinite-key table browse failed") { !model.querying && model.advancedPath == infiniteTable.path }
        let infinite = search("inf")
        let infiniteKey = Hades2SaveTypedValue(["luaType": "number", "encoding": "nonfinite", "value": "inf"])!
        require(infinite.path.last == .typed(infiniteKey), "infinite key lost its typed path")
        press(root, "hades2.saveEditor.workbench.browse")
        until("infinite-key child browse failed") { !model.querying && model.advancedPath == infinite.path }
        scalar("Nested", "infinite edited")
        model.leaveAdvanced(); until("infinite child leave failed") { !model.querying && model.advancedPath == infiniteTable.path }
        scalar("UniqueSibling", "sibling edited")
        model.leaveAdvanced(); until("infinite table leave failed") { !model.querying && model.advancedPath == [.saveContainer("payload")] }
        model.leaveAdvanced(); until("payload leave failed") { !model.querying && model.advancedPath.isEmpty }
        let main = search("Main Lua root")
        require(main.childCount == nil, "main root duplicated child navigation")
        let sheet = openValue(main)
        edit(fields(sheet).first { $0.placeholderString == text("hades2.saveEditor.advanced.key") }!, "NewRoot")
        edit(fields(sheet).first { $0.placeholderString == text("hades2.saveEditor.advanced.memberValue") }!, "{\"luaType\":\"string\",\"value\":\"created\"}")
        press(sheet, "hades2.saveEditor.advanced.addMember")
        until("root member did not stage") { !model.busy && model.pendingActions.contains { $0.rawID == "NewRoot" } }
        require(model.pendingActions.first { $0.rawID == "NewRoot" }!.entryID.hasPrefix("advanced:"), "root member identity aliased")
        press(sheet, "host.done"); until("root sheet did not close") { window.attachedSheet == nil }
        require(model.pendingCount == 8, "container action count wrong")
        let stagedTarget = try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav"))
        require(stagedTarget == targetBefore, "Stage changed disk bytes")
        press(root, "hades2.saveEditor.apply")
        until("container Apply failed") { !model.busy && !model.querying && model.pendingCount == 0 && model.lastApplyReceipt != nil }
        let installedSource = try Data(contentsOf: base.appendingPathComponent("saves/Profile1.sav"))
        require(installedSource == original, "container edit changed fixed source")
        var active = Data("SGB1".utf8); active.append(contentsOf: [8, 0, 0, 0]); active.append(Data("Profile2".utf8))
        try active.write(to: base.appendingPathComponent("saves/activeProfile"))
        window.performClose(nil); until("container document close failed") { model.workspaceID == nil }
        let reopened = Hades2SaveEditorModel(session: session), reopenedWindow = open(reopened)
        until("container target reopen failed") { !reopened.busy && !reopened.querying && reopened.sourceRelativePath == "Profile2.sav" }
        reopened.selectDomain(.advanced)
        until("reopened Advanced root failed") { !reopened.querying && reopened.items.contains { $0.path == [.saveContainer("header")] } }
        reopened.enterAdvanced(reopened.items.first { $0.path == [.saveContainer("header")] }!)
        until("reopened header failed") { !reopened.querying && reopened.items.contains { $0.rawID == "timestamp" } }
        require(reopened.items.first { $0.rawID == "timestamp" }!.value == AnyHashable("18446744073709551614"), "uint64 precision lost on reopen")
        reopenedWindow.performClose(nil); pump(); session.stop(); pump()
        print("save_container_native_player_journey_ok")
    }
}
