import AppKit
import Foundation
import SwiftUI

private func require(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

private func pump(_ seconds: TimeInterval = 0.10) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

private func until(_ message: String, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !condition() && Date() < deadline { pump(0.02) }
    require(condition(), message)
}

private func fields(_ view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
}

/// SwiftUI's popup menu does not track reliably in a prohibited test app.
/// Exercise completed enum selection through a real AppKit selector bound to
/// the same production edit owner; actual SwiftUI menu selection stays manual.
@MainActor private final class EnumSelection: NSObject {
    let model: Hades2SaveEditorModel
    let entry: Hades2SaveEditorEntry
    init(_ model: Hades2SaveEditorModel, _ entry: Hades2SaveEditorEntry) {
        self.model = model; self.entry = entry
    }
    @objc func changed(_ sender: NSPopUpButton) {
        _ = model.completeTextEdit(entry, text: sender.selectedItem!.representedObject as! String)
    }
}

@main struct SaveEditorPlayerJourney {
    @MainActor static func main() throws {
        let python = URL(fileURLWithPath: CommandLine.arguments[1])
        let worker = URL(fileURLWithPath: CommandLine.arguments[2])
        let base = URL(fileURLWithPath: ProcessInfo.processInfo.environment["MGT_SAVE_JOURNEY_FIXTURE"]!)
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited); app.finishLaunching(); enableNativeAccessibility()
        let defaults = InMemoryDefaults()
        defaults.set(TrainerPresentationLanguage.en.rawValue, forKey: TrainerLocalizationStore.userDefaultsKey)
        let localization = TrainerLocalizationStore(defaults: defaults)
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
            Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        func text(_ key: String, _ arguments: [String] = []) -> String {
            Hades2GameModule.resolveText(key: key, arguments: arguments, localization: localization)
        }
        let session = TrainerBackendSession(client: BackendClient(process:
            BackendProcess(executableURL: python, argumentsPrefix: ["-u"])))
        try session.start(descriptor: Hades2GameModule.descriptor, backendScriptURL: worker,
                          applyPayload: { _ in }, resetGameState: {}, log: { _ in }, onStatusChange: { _ in })
        let model = Hades2SaveEditorModel(session: session)
        let windows = TrainerToolWindowStore()
        func open(_ model: Hades2SaveEditorModel) -> NSWindow {
            windows.open(id: "player-journey", title: "Save player journey", localization: localization, theme: .standard) {
                TrainerToolWindowContent(canClose: { !model.busy }, onClose: model.close) {
                    Hades2SaveEditorView(model: model)
                }
            }
        }
        let window = open(model)
        until("real Save source did not open") { model.workspaceID != nil && !model.busy && !model.querying && !model.items.isEmpty }
        let root = window.contentView!
        let originalSHA = model.sourceSHA256
        let originalBytes = try Data(contentsOf: base.appendingPathComponent("saves/Profile1.sav"))
        model.selectTarget("main/Profile2.sav")
        until("explicit physical write target was not selected") { !model.busy && model.selectedTargetID == "main/Profile2.sav" }
        require(model.sourceRelativePath == "Profile1.sav" && model.sourceSHA256 == originalSHA,
                "choosing a write target replaced the originally read source")

        func edit(_ field: NSTextField, _ value: String, submit: Bool = false, finish: Bool = true) {
            field.scrollToVisible(field.bounds)
            require(window.makeFirstResponder(field), "could not focus native Save input")
            guard let editor = field.currentEditor() as? NSTextView else { fatalError("native Save field editor missing") }
            editor.selectAll(nil); editor.insertText(value, replacementRange: editor.selectedRange())
            if submit { editor.doCommand(by: #selector(NSResponder.insertNewline(_:))) }
            if finish { window.makeFirstResponder(nil) }
            pump()
        }
        func search(_ query: String) {
            guard let field = fields(root).first(where: { $0.placeholderString == text("hades2.saveEditor.workbench.search") })
            else { fatalError("native Save search input missing") }
            edit(field, query, submit: true)
            until("native search did not complete: \(query)") { model.search == query && !model.querying && !model.items.isEmpty }
        }
        func entry(_ id: String) -> Hades2SaveEditorEntry {
            guard let entry = model.items.first(where: { $0.id == id }) else { fatalError("searched entity field missing: \(id)") }
            return entry
        }
        func number(_ id: String, _ value: String, basket: Bool = false) {
            let name = basket ? model.pendingActions.first(where: { $0.entryID == id })!.name : entry(id).displayName
            let candidates = fields(root).filter { $0.isEditable && $0.accessibilityLabel() == name }
            let field = basket ? candidates.min(by: {
                $0.convert($0.bounds, to: nil).midY < $1.convert($1.bounds, to: nil).midY
            }) : candidates.first
            guard let field else { fatalError("native numeric Save control missing: \(name)") }
            edit(field, value)
            until("completed numeric edit did not stage: \(id)") {
                !model.busy && model.pendingActions.contains { $0.entryID == id && String(describing: $0.after!.base) == value }
            }
        }
        func press(_ key: String, _ arguments: [String] = []) {
            guard let control = namedNativeControl(root, role: "AXButton", name: text(key, arguments)),
                  control.enabled, control.press() else { fatalError("native Save action unavailable: \(key)") }
            pump()
        }
        func remove(_ id: String, remaining: Int) {
            let identifier = "saveEditor.remove." + id
            guard let control = nativeAccessibilityControls(root).first(where: { $0.identifier == identifier }),
                  control.enabled, control.press() else { fatalError("native per-action remove missing: \(id)") }
            until("native action removal did not finish: \(id)") {
                !model.busy && model.pendingCount == remaining && !model.pendingActions.contains { $0.entryID == id }
            }
        }
        func showChanges() {
            until("Changes review did not expose explicit Apply") {
                namedNativeControl(root, role: "AXButton", name: text("hades2.saveEditor.apply")) != nil
            }
        }

        // Typeahead must complete while the native field editor keeps focus.
        // A combined owner/action query also works across the other locale.
        let searchInput = fields(root).first { $0.placeholderString == text("hades2.saveEditor.workbench.search") }!
        edit(searchInput, "Hecate Salute", finish: false)
        until("owner/action typeahead did not find Hecate") {
            !model.querying && model.search == "Hecate Salute" && model.entityResults.contains { $0.id == "person:Hecate" }
        }
        require(searchInput.currentEditor() != nil, "typeahead stole the active search draft")
        require(namedNativeControl(root, role: "AXStaticText", name: text("hades2.saveEditor.group.characters")) != nil,
                "results have no visible character section heading")
        require(!nativeAccessibilityControls(root).contains {
            $0.role == "AXDisclosureTriangle" || $0.label == text("hades2.saveEditor.investigate.details")
                || $0.label == text("hades2.saveEditor.workbench.technical")
        }, "ordinary Save information still requires an expansion control")
        edit(searchInput, "赫卡忒 致意", finish: false)
        until("cross-language owner/action search failed") {
            !model.querying && model.entityResults.contains { $0.id == "person:Hecate" }
        }
        edit(searchInput, "no-matching-save-field", finish: false)
        until("unmatched typeahead kept stale results") { !model.querying && model.items.isEmpty }
        guard let clear = nativeAccessibilityControls(root).first(where: { $0.identifier == "trainer.search.clear" }), clear.press()
        else { fatalError("native search clear did not dispatch") }
        until("clearing search did not restore browse results") { model.search.isEmpty && !model.querying && !model.items.isEmpty }

        // A simple resource journey crosses the actual search/inline/Changes/
        // Apply controls and the real codec/filesystem transaction exactly once.
        let initialTarget = try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav"))
        search("Ashes"); number("resource:MetaCurrency", "20")
        let stagedTarget = try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav"))
        require(stagedTarget == initialTarget,
                "inline staging wrote the target before explicit Apply")
        showChanges(); press("hades2.saveEditor.apply")
        until("simple real Save Apply did not complete") { !model.busy && !model.querying && model.pendingCount == 0 && model.lastApplyReceipt != nil }
        let firstReceipt = model.lastApplyReceipt!
        require(firstReceipt.source == "main/Profile1.sav" && firstReceipt.target == "main/Profile2.sav" && !firstReceipt.runtimeReloaded,
                "simple Save receipt misrepresented source, target or runtime reload")
        try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav"))
            .write(to: base.appendingPathComponent("after-simple.sav"))

        // Inspect the actual inline enum and exercise native completed choice
        // dispatch through the shared production edit owner, then remove it.
        search("QuestHelpDora")
        let selector = entry("quest:QuestHelpDora")
        require(namedNativeControl(root, role: "AXPopUpButton", name: selector.displayName) != nil,
                "inline enum requires another entity/edit mode before selection")
        let enumTarget = EnumSelection(model, selector)
        let popup = NSPopUpButton(frame: .zero, pullsDown: false)
        for choice in selector.choices {
            popup.addItem(withTitle: selector.choiceNames[choice] ?? choice)
            popup.lastItem!.representedObject = choice
        }
        popup.target = enumTarget; popup.action = #selector(EnumSelection.changed(_:))
        popup.selectItem(at: selector.choices.firstIndex(of: "Complete")!)
        require(popup.sendAction(popup.action, to: enumTarget), "native enum selection did not dispatch")
        until("enum selection did not stage") { !model.busy && model.pendingActions.first?.entryID == selector.id }
        require(model.pendingActions.first?.after == AnyHashable("Complete"), "enum choice lost its semantic value")
        showChanges(); remove(selector.id, remaining: 0)

        // Three independent actions, middle removal and revision through the
        // actual Changes field. The Arcana action carries physical effects.
        search("Sorceress")
        let unlock = entry("card:ChanneledCast:Unlocked")
        require(namedNativeControl(root, role: "AXCheckBox", name: unlock.displayName)?.press() == true,
                "native inline boolean did not dispatch")
        until("inline boolean did not stage linked effects") { !model.busy && model.pendingCount == 1 && model.pendingEffectCount == 7 }
        search("Hecate"); number("interaction:NPC_Hecate_01", "4")
        search("Ashes"); number("resource:MetaCurrency", "50")
        require(model.pendingActions.map(\.entryID) == [unlock.id, "interaction:NPC_Hecate_01", "resource:MetaCurrency"],
                "requested actions lost insertion order or independent ownership")
        showChanges(); remove("interaction:NPC_Hecate_01", remaining: 2)
        number("resource:MetaCurrency", "75", basket: true)

        // A requested level and the unlock action's linked reset share one
        // physical field. Removing the direct action restores its linked owner.
        search("Sorceress"); number("card:ChanneledCast:Level", "1")
        require(model.pendingCount == 3 && model.pendingEffectCount == 6,
                "overlapping direct intent duplicated a linked physical effect")
        remove("card:ChanneledCast:Level", remaining: 2)
        require(model.pendingEffectCount == 7 && model.pendingPhysicalChangeCount == 9,
                "removing direct intent did not recompute the surviving linked projection")
        for effect in model.pendingActions.first!.effects {
            guard let name = effect.name, !name.isEmpty else { fatalError("linked effect has no presentation name") }
            require(nativeAccessibilityControls(root).contains { $0.text == name },
                    "linked physical effect was not directly visible")
        }

        // A later physical target and active-profile change do not rebase the
        // source or revoke the deliberately chosen target.
        try Data(contentsOf: base.appendingPathComponent("target-newer.sav"))
            .write(to: base.appendingPathComponent("saves/Profile2.sav"))
        var active = Data("SGB1".utf8)
        active.append(contentsOf: [8, 0, 0, 0]); active.append(Data("Profile2".utf8))
        try active.write(to: base.appendingPathComponent("saves/activeProfile"))
        require(model.sourceSHA256 == originalSHA && model.sourceRelativePath == "Profile1.sav"
                && model.selectedTargetID == "main/Profile2.sav", "external target changes rebased source/target intent")
        press("hades2.saveEditor.apply")
        until("multi-owner Save Apply did not finish") { !model.busy && !model.querying && model.pendingCount == 0 && model.lastApplyReceipt != nil }
        let lastReceipt = model.lastApplyReceipt!
        require(!lastReceipt.runtimeReloaded && !lastReceipt.hot && lastReceipt.previousSnapshotID != firstReceipt.previousSnapshotID,
                "multi-owner Apply lost its distinct recoverable disk receipt")
        let sourceAfterApply = try Data(contentsOf: base.appendingPathComponent("saves/Profile1.sav"))
        require(sourceAfterApply == originalBytes,
                "explicit-target Apply overwrote its fixed source")
        let originalWorkspace = model.workspaceID!
        window.performClose(nil)
        until("closing the native document did not release its workspace") { model.workspaceID == nil }
        let reopened = Hades2SaveEditorModel(session: session)
        let reopenedWindow = open(reopened)
        until("closed document did not reopen on the current selected source") {
            !reopened.busy && !reopened.querying && reopened.workspaceID != nil
                && reopened.sourceRelativePath == "Profile2.sav" && !reopened.items.isEmpty
        }
        require(reopenedWindow !== window && reopened.workspaceID != originalWorkspace && reopened.pendingCount == 0,
                "reopening retained the closed document's window, workspace or draft batch")
        require(reopened.items.first(where: { $0.id == "resource:MetaCurrency" })?.value == AnyHashable(75),
                "reopened source did not observe installed bytes")
        let report: [String: Any] = [
            "sourceSHA256": originalSHA, "firstSnapshot": firstReceipt.previousSnapshotID,
            "lastSnapshot": lastReceipt.previousSnapshotID, "source": lastReceipt.source,
            "target": lastReceipt.target, "runtimeReloaded": lastReceipt.runtimeReloaded,
            "swiftUIPopupSelectionTested": false,
        ]
        try JSONSerialization.data(withJSONObject: report).write(to: base.appendingPathComponent("journey.json"))
        reopenedWindow.performClose(nil); pump()
        session.stop(); pump()
        print("save_editor_player_journey_native_ok")
    }
}
