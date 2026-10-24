import AppKit
import Foundation
import SwiftUI

private func require(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}
private func pump(_ seconds: TimeInterval = 0.08) { RunLoop.current.run(until: Date().addingTimeInterval(seconds)) }
private func until(_ message: String, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !condition() && Date() < deadline { pump(0.02) }
    require(condition(), message)
}
private func fields(_ view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
}

@main struct SaveAdvancedPlayerJourney {
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
            windows.open(id: "advanced-journey", title: "Advanced Save journey", localization: localization, theme: .standard) {
                TrainerToolWindowContent(canClose: { !model.busy }, onClose: model.close) { Hades2SaveEditorView(model: model) }
            }
        }
        let model = Hades2SaveEditorModel(session: session)
        let window = open(model)
        until("Save document did not open") { model.workspaceID != nil && !model.busy && !model.querying && !model.items.isEmpty }
        model.selectTarget("main/Profile2.sav")
        until("target selection did not finish") { !model.busy }
        let root = window.contentView!
        let original = try Data(contentsOf: base.appendingPathComponent("saves/Profile1.sav"))
        let targetBefore = try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav"))

        func enter(_ name: String, in model: Hades2SaveEditorModel) {
            guard let row = model.items.first(where: { $0.rawID == name }) else { fatalError("Advanced table missing: \(name)") }
            model.enterAdvanced(row)
            until("Advanced navigation did not finish: \(name)") { !model.querying && !model.items.isEmpty }
        }
        // Picker navigation remains separately user-run. All edits below use
        // the actual mounted controls, completion, Changes and Apply owners.
        model.selectDomain(.advanced)
        until("Advanced root did not open") { !model.querying && model.items.contains { $0.rawID == "GameState" } }
        enter("GameState", in: model); enter("AdvancedFixture", in: model)

        func edit(_ field: NSTextField, _ value: String) {
            guard let owner = field.window else { fatalError("native input has no window") }
            field.scrollToVisible(field.bounds)
            require(owner.makeFirstResponder(field), "native input could not focus")
            guard let editor = field.currentEditor() as? NSTextView else { fatalError("native field editor missing") }
            editor.selectAll(nil); editor.insertText(value, replacementRange: editor.selectedRange())
            owner.makeFirstResponder(nil); pump()
        }
        func search(_ value: String) -> Hades2SaveEditorEntry {
            guard let input = fields(root).first(where: { $0.placeholderString == text("hades2.saveEditor.workbench.search") })
            else { fatalError("native search field missing") }
            edit(input, value)
            until("Advanced search did not complete") { !model.querying && model.items.contains { $0.rawID == value } }
            return model.items.first { $0.rawID == value }!
        }
        func press(_ owner: NSView, _ key: String) {
            guard let button = namedNativeControl(owner, role: "AXButton", name: text(key)), button.enabled, button.press()
            else { fatalError("actual Save button missing: \(key)") }
            pump()
        }
        func numericOrText(_ name: String, _ value: String) {
            let row = search(name)
            guard let input = fields(root).first(where: { $0.isEditable && $0.accessibilityLabel() == row.displayName })
            else { fatalError("editable Advanced scalar has no actual inline control: \(name)") }
            edit(input, value)
            until("Advanced completed scalar did not stage") { !model.busy && model.pendingActions.contains { $0.entryID == row.id } }
        }
        func openValue(_ row: Hades2SaveEditorEntry) -> NSView {
            let identifier = "saveEditor.editValue." + row.id
            guard let button = nativeAccessibilityControls(root).first(where: { $0.identifier == identifier }),
                  button.enabled, button.press() else { fatalError("Advanced type/structure editor missing: \(row.rawID)") }
            until("Advanced structure sheet did not open") { window.attachedSheet != nil }
            let sheet = window.attachedSheet!.contentView!
            until("Advanced typed value did not load") {
                fields(sheet).contains { $0.isEditable && $0.accessibilityLabel()?.contains(text("hades2.saveEditor.advanced.typedValue")) == true }
            }
            return sheet
        }
        func typed(_ row: Hades2SaveEditorEntry, _ value: String, probeLanguage: Bool = false, probeBackend: Bool = false) {
            var sheet = openValue(row)
            var input = fields(sheet).first { $0.isEditable && $0.accessibilityLabel()?.contains(text("hades2.saveEditor.advanced.typedValue")) == true }!
            if probeLanguage {
                require(input.window!.makeFirstResponder(input), "typed value did not focus")
                let editor = input.currentEditor() as! NSTextView
                editor.selectAll(nil); editor.insertText("unfinished draft", replacementRange: editor.selectedRange())
                localization.language = .zhCN; pump(0.30)
                require(input.stringValue == "unfinished draft", "Advanced language/detail refresh replaced focused draft")
                localization.language = .en; pump(0.30)
                require(input.stringValue == "unfinished draft", "Advanced bilingual refresh discarded unfinished text")
                edit(input, "invalid tagged value")
                require(model.editFailures[row.id] != nil, "invalid typed input lost its scoped correction")
                press(sheet, "host.done")
                until("invalid typed editor did not dismiss") { window.attachedSheet == nil }
                sheet = openValue(row)
                input = fields(sheet).first { $0.isEditable && $0.accessibilityLabel()?.contains(text("hades2.saveEditor.advanced.typedValue")) == true }!
                require(input.stringValue == "invalid tagged value", "reopening the same Advanced field lost its retained invalid draft")
            }
            if probeBackend {
                // Structurally tagged JSON reaches the real backend, where
                // the codec owner rejects inconsistent allocation hints.
                let rejected = "{\"luaType\":\"table\",\"arraySize\":1,\"hashSize\":0,\"entries\":[]}"
                let count = model.pendingCount
                edit(input, rejected)
                until("backend refusal did not retain its field correction") { !model.busy && model.editFailures[row.id] != nil }
                require(model.pendingCount == count && !model.pendingActions.contains { $0.entryID == row.id },
                        "refused typed value joined the acknowledged Changes batch")
                press(sheet, "host.done")
                until("refused value editor did not dismiss") { window.attachedSheet == nil }
                sheet = openValue(row)
                input = fields(sheet).first { $0.isEditable && $0.accessibilityLabel()?.contains(text("hades2.saveEditor.advanced.typedValue")) == true }!
                require(input.stringValue == rejected, "reopening lost the backend-refused typed draft needed for correction")
                require(model.editFailures[row.id] != nil, "reopening discarded the backend-refused field correction")
            }
            edit(input, value)
            until("Advanced typed edit did not stage") { !model.busy && model.pendingActions.contains { $0.entryID == row.id } }
            require(model.editFailures[row.id] == nil && model.typedDrafts[row.id] == nil,
                    "acknowledged typed correction retained its rejected draft or error")
            press(sheet, "host.done")
            until("Advanced sheet did not close") { window.attachedSheet == nil }
        }
        func membership(_ operation: String, key: String, value: String? = nil) {
            let row = search("Members")
            let sheet = openValue(row)
            guard let keyInput = fields(sheet).first(where: { $0.placeholderString == text("hades2.saveEditor.advanced.key") })
            else { fatalError("native membership key input missing") }
            edit(keyInput, key)
            if let value {
                let input = fields(sheet).first { $0.placeholderString == text("hades2.saveEditor.advanced.memberValue") }!
                edit(input, value)
            }
            press(sheet, operation)
            until("membership completion did not finish") { !model.busy }
            press(sheet, "host.done")
            until("membership sheet did not close") { window.attachedSheet == nil }
        }
        func apply(_ expected: Int) {
            require(model.pendingCount == expected, "unexpected independently removable Advanced action count")
            press(root, "hades2.saveEditor.apply")
            until("Advanced Apply did not verify and refresh") { !model.busy && !model.querying && model.pendingCount == 0 && model.lastApplyReceipt != nil }
            require(model.lastApplyReceipt!.source == "main/Profile1.sav" && model.lastApplyReceipt!.target == "main/Profile2.sav"
                    && !model.lastApplyReceipt!.runtimeReloaded, "Advanced receipt lost source/target or promised runtime reload")
        }

        numericOrText("Number", "8.25")
        let boolean = search("Boolean")
        require(namedNativeControl(root, role: "AXCheckBox", name: boolean.displayName)?.press() == true, "Advanced boolean is not a native inline control")
        until("Advanced boolean did not stage") { !model.busy && model.pendingActions.contains { $0.entryID == boolean.id } }
        numericOrText("Text", "  exact  "); numericOrText("Empty", "")
        typed(search("Binary"), "{\"luaType\":\"string\",\"encoding\":\"base64\",\"value\":\"AP4=\"}", probeLanguage: true)
        typed(search("Nil"), "{\"luaType\":\"number\",\"value\":3}", probeBackend: true)
        typed(search("Members"), "{\"luaType\":\"table\",\"entries\":[{\"key\":{\"luaType\":\"boolean\",\"value\":true},\"value\":{\"luaType\":\"string\",\"value\":\"boolean changed\"}},{\"key\":{\"luaType\":\"number\",\"value\":1},\"value\":{\"luaType\":\"string\",\"value\":\"number changed\"}},{\"key\":{\"luaType\":\"string\",\"value\":\"1\"},\"value\":{\"luaType\":\"string\",\"value\":\"string changed\"}},{\"key\":{\"luaType\":\"string\",\"encoding\":\"base64\",\"value\":\"/w==\"},\"value\":{\"luaType\":\"string\",\"value\":\"binary changed\"}}]}")
        let removed = search("Removed")
        guard let remove = nativeAccessibilityControls(root).first(where: { $0.identifier == "saveEditor.unset." + removed.id })
        else { fatalError("Advanced field removal control missing") }
        require(remove.press(), "Advanced field removal did not dispatch")
        until("Advanced unset did not stage") { !model.busy && model.pendingActions.contains { $0.entryID == removed.id } }
        let untouched = try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav"))
        require(untouched == targetBefore, "Advanced staging wrote before explicit Apply")
        apply(8)
        try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav")).write(to: base.appendingPathComponent("after-advanced-first.sav"))

        let membershipRow = search("Members")
        var membershipSheet = openValue(membershipRow)
        edit(fields(membershipSheet).first { $0.placeholderString == text("hades2.saveEditor.advanced.key") }!, "  unfinished key  ")
        edit(fields(membershipSheet).first { $0.placeholderString == text("hades2.saveEditor.advanced.memberValue") }!, "invalid member value")
        press(membershipSheet, "hades2.saveEditor.advanced.addMember")
        require(namedNativeControl(membershipSheet, role: "AXStaticText", name: text("hades2.saveEditor.invalidDraft")) != nil,
                "invalid membership did not expose its correction")
        press(membershipSheet, "host.done")
        until("invalid membership editor did not dismiss") { window.attachedSheet == nil }
        membershipSheet = openValue(membershipRow)
        require(fields(membershipSheet).first { $0.placeholderString == text("hades2.saveEditor.advanced.key") }?.stringValue == "  unfinished key  ",
                "reopening the table lost its unfinished membership key")
        require(fields(membershipSheet).first { $0.placeholderString == text("hades2.saveEditor.advanced.memberValue") }?.stringValue == "invalid member value",
                "reopening the table lost its unfinished membership value")
        require(namedNativeControl(membershipSheet, role: "AXStaticText", name: text("hades2.saveEditor.invalidDraft")) != nil,
                "reopening the table lost its membership correction")
        press(membershipSheet, "host.done")
        until("membership draft editor did not dismiss") { window.attachedSheet == nil }

        membership("hades2.saveEditor.advanced.addMember", key: "Added", value: "{\"luaType\":\"number\",\"value\":42}")
        let initialAdded = model.pendingActions.first!
        guard let removeAdded = nativeAccessibilityControls(root).first(where: { $0.identifier == "saveEditor.remove." + initialAdded.entryID }),
              removeAdded.press() else { fatalError("new member action has no native per-action removal") }
        until("new member action removal did not finish") { !model.busy && model.pendingCount == 0 }
        membership("hades2.saveEditor.advanced.addMember", key: "Added", value: "{\"luaType\":\"number\",\"value\":42}")
        let added = model.pendingActions.first!
        typed(added.editorEntry, "{\"luaType\":\"boolean\",\"value\":false}")
        membership("hades2.saveEditor.advanced.removeMember", key: "1")
        typed(search("Nil"), "{\"luaType\":\"nil\",\"value\":null}")
        apply(3)
        let installedSource = try Data(contentsOf: base.appendingPathComponent("saves/Profile1.sav"))
        require(installedSource == original, "Advanced explicit-target Apply overwrote its fixed source")
        var active = Data("SGB1".utf8); active.append(contentsOf: [8, 0, 0, 0]); active.append(Data("Profile2".utf8))
        try active.write(to: base.appendingPathComponent("saves/activeProfile"))
        window.performClose(nil)
        until("Advanced document did not close") { model.workspaceID == nil }
        let reopened = Hades2SaveEditorModel(session: session)
        let reopenedWindow = open(reopened)
        until("Advanced installed target did not reopen") { !reopened.busy && !reopened.querying && reopened.sourceRelativePath == "Profile2.sav" && !reopened.items.isEmpty }
        reopened.selectDomain(.advanced)
        until("reopened Advanced root missing") { !reopened.querying && !reopened.items.isEmpty }
        enter("GameState", in: reopened); enter("AdvancedFixture", in: reopened)
        require(reopened.items.first { $0.rawID == "Number" }?.value == AnyHashable(8.25), "reopened numeric value disagrees with acknowledged Apply")
        require(reopened.items.first { $0.rawID == "Text" }?.value == AnyHashable("  exact  "), "Advanced text whitespace was normalized away")
        require(reopened.items.first { $0.rawID == "Empty" }?.value == AnyHashable(""), "Advanced empty string was refused")
        require(!reopened.items.contains { $0.rawID == "Removed" } && reopened.items.contains { $0.rawID == "Nil" }, "nil and field absence were conflated")
        enter("Members", in: reopened)
        require(reopened.items.contains { $0.rawID == "base64:/w==" } && reopened.items.contains { $0.rawID == "Added" && $0.value == AnyHashable(false) },
                "binary key navigation or new member revision did not survive reopening")
        reopenedWindow.performClose(nil); pump(); session.stop(); pump()
        print("save_advanced_native_player_journey_ok")
    }
}
