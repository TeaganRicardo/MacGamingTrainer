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

/// Completed native choice dispatch shares the actual Picker's production
/// owner. Tracking the SwiftUI Picker's menu remains user-run acceptance.
@MainActor private final class RecordSelection: NSObject {
    let model: Hades2SaveEditorModel
    let entry: Hades2SaveEditorEntry
    init(_ model: Hades2SaveEditorModel, _ entry: Hades2SaveEditorEntry) {
        self.model = model; self.entry = entry
    }
    @objc func changed(_ sender: NSPopUpButton) {
        _ = model.completeTextEdit(entry, text: sender.selectedItem!.representedObject as! String)
    }
}

@main struct SaveRecordPlayerJourney {
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
            windows.open(id: "record-journey", title: "Save record journey", localization: localization, theme: .standard) {
                TrainerToolWindowContent(canClose: { !model.busy }, onClose: model.close) { Hades2SaveEditorView(model: model) }
            }
        }
        let model = Hades2SaveEditorModel(session: session)
        let window = open(model)
        until("record document did not open") { model.workspaceID != nil && !model.busy && !model.querying && !model.items.isEmpty }
        model.selectTarget("main/Profile2.sav")
        until("record target selection did not finish") { !model.busy }
        let root = window.contentView!
        let original = try Data(contentsOf: base.appendingPathComponent("saves/Profile1.sav"))
        let initialTarget = try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav"))

        func edit(_ input: NSTextField, _ value: String, submit: Bool = false) {
            let owner = input.window!
            input.scrollToVisible(input.bounds)
            require(owner.makeFirstResponder(input), "record native input did not focus")
            let editor = input.currentEditor() as! NSTextView
            editor.selectAll(nil); editor.insertText(value, replacementRange: editor.selectedRange())
            if submit { editor.doCommand(by: #selector(NSResponder.insertNewline(_:))) }
            owner.makeFirstResponder(nil); pump()
        }
        func search(_ query: String, _ id: String, in owner: Hades2SaveEditorModel, root content: NSView) -> Hades2SaveEditorEntry {
            let input = fields(content).first { $0.placeholderString == text("hades2.saveEditor.workbench.search") }!
            edit(input, query, submit: true)
            until("record search did not expose \(id)") { !owner.querying && owner.items.contains { $0.id == id } }
            // Backend completion publishes model state before SwiftUI mounts
            // the replacement rows on the following layout pass.
            pump(0.15)
            return owner.items.first { $0.id == id }!
        }
        func row(_ query: String, _ id: String) -> Hades2SaveEditorEntry { search(query, id, in: model, root: root) }
        func scalar(_ query: String, _ id: String, _ value: String) {
            let entry = row(query, id)
            guard let input = fields(root).first(where: { $0.isEditable && $0.accessibilityLabel() == entry.displayName })
            else { fatalError("ordinary scalar has no native control: \(id) name=\(entry.displayName) editable=\(entry.editable) kind=\(entry.valueType) mutations=\(entry.mutationKinds) fields=\(fields(root).map { ($0.accessibilityLabel() ?? "<nil>") + ":" + $0.stringValue })") }
            edit(input, value)
            until("record scalar completion did not stage \(id)") { !model.busy && model.pendingActions.contains { $0.entryID == id } }
            require(String(describing: model.pendingActions.first { $0.entryID == id }!.after!.base) == value,
                    "record scalar completion changed exact submitted data: \(id)")
        }
        func toggle(_ query: String, _ id: String) {
            let entry = row(query, id)
            require(namedNativeControl(root, role: "AXCheckBox", name: entry.displayName)?.press() == true,
                    "ordinary record has no native boolean: \(id)")
            until("record boolean did not stage \(id)") { !model.busy && model.pendingActions.contains { $0.entryID == id } }
        }
        func selectedLabel(_ entry: Hades2SaveEditorEntry, _ token: String, in content: NSView = root) {
            let controls = nativeAccessibilityControls(content).filter { $0.role == "AXPopUpButton" && $0.label == entry.displayName }
            require(!controls.isEmpty && controls.allSatisfy { $0.valueText == entry.choiceNames[token] },
                    "numeric/native enum selected label is missing for \(entry.id): \(controls.map { $0.valueText ?? "<nil>" })")
        }
        func choose(_ entry: Hades2SaveEditorEntry, _ token: String) {
            let target = RecordSelection(model, entry)
            let popup = NSPopUpButton(frame: .zero, pullsDown: false)
            for choice in entry.choices {
                popup.addItem(withTitle: entry.choiceNames[choice] ?? choice)
                popup.lastItem!.representedObject = choice
            }
            popup.target = target; popup.action = #selector(RecordSelection.changed(_:))
            popup.selectItem(at: entry.choices.firstIndex(of: token)!)
            require(popup.sendAction(popup.action, to: target), "native record choice did not dispatch")
            until("completed native record choice did not stage") { !model.busy && model.pendingActions.contains { $0.entryID == entry.id } }
            selectedLabel(entry, token)
        }
        func press(_ key: String) {
            guard let button = namedNativeControl(root, role: "AXButton", name: text(key)), button.enabled, button.press()
            else { fatalError("record native action unavailable: \(key)") }
            pump()
        }
        func assertWarning(_ entry: Hades2SaveEditorEntry, in content: NSView) {
            guard let warning = entry.warning, !warning.isEmpty,
                  namedNativeControl(content, role: "AXStaticText", name: warning) != nil
            else { fatalError("editable record impact warning is absent from its actual native row: \(entry.id)") }
        }

        // Physical navigation uses the document owner; text/boolean controls,
        // correction/revision, acknowledgement and Apply use actual controls.
        scalar("ActiveBounty", "history:run:1:ActiveBounty", "  first  ")
        let result = row("RunResult", "history:run:1:RunResult")
        selectedLabel(result, "2")
        choose(result, "3")
        require(model.pendingActions.first { $0.entryID == result.id }?.after == AnyHashable(3),
                "RunResult acknowledgement converted the stored numeric result to text")
        scalar("EndingRoomName", "history:run:1:EndingRoomName", "")
        scalar("FishingFails", "history:gathering:fishing:FishingFails", "7")
        let quest = row("QuestHelpDora", "quest:QuestHelpDora")
        choose(quest, "Complete")
        require(model.pendingEffectCount == 1, "quest status did not expose its completion-record effect")
        toggle("QuestHelpDora", "questObservation:QuestsViewed:QuestHelpDora")
        toggle("UnverifiedScene", "dialogue:UnverifiedScene")
        scalar("UnverifiedScene", "dialogueChoice:UnverifiedScene", " Choice B ")
        scalar("Unknown_0001", "speech:/VO/Unknown_0001", "12")
        toggle("Legacy_0001", "speech:/VO/Legacy_0001")
        require(model.pendingCount == 10, "ordinary independent requests were merged or lost")
        let stagedTarget = try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav"))
        require(stagedTarget == initialTarget,
                "ordinary record staging wrote before explicit Apply")
        until("ordinary Changes did not load") { !model.busy }
        let bounty = model.pendingActions.first { $0.entryID == "history:run:1:ActiveBounty" }!
        let input = fields(root).first { $0.isEditable && $0.accessibilityLabel() == bounty.name }!
        edit(input, "  revised  ")
        until("Changes exact string revision did not acknowledge") { !model.busy && model.pendingActions.first { $0.entryID == bounty.entryID }?.after == AnyHashable("  revised  ") }
        selectedLabel(result, "3")
        require(nativeAccessibilityControls(root).contains { $0.role == "AXStaticText" && $0.text == result.choiceNames["2"] }
                && nativeAccessibilityControls(root).contains { $0.role == "AXStaticText" && $0.text == result.choiceNames["3"] },
                "Changes before/after numeric enum lost the bilingual choice names")
        press("hades2.saveEditor.apply")
        until("ordinary Apply did not verify and refresh") { !model.busy && !model.querying && model.pendingCount == 0 && model.lastApplyReceipt != nil }
        require(model.lastApplyReceipt!.source == "main/Profile1.sav" && model.lastApplyReceipt!.target == "main/Profile2.sav"
                && !model.lastApplyReceipt!.runtimeReloaded, "ordinary Apply lost fixed source/target or promised runtime reload")
        let sourceAfter = try Data(contentsOf: base.appendingPathComponent("saves/Profile1.sav"))
        require(sourceAfter == original,
                "ordinary record Apply overwrote its fixed source")
        var active = Data("SGB1".utf8); active.append(contentsOf: [8, 0, 0, 0]); active.append(Data("Profile2".utf8))
        try active.write(to: base.appendingPathComponent("saves/activeProfile"))
        window.performClose(nil)
        until("ordinary document did not release workspace") { model.workspaceID == nil }
        let reopened = Hades2SaveEditorModel(session: session)
        let reopenedWindow = open(reopened)
        until("ordinary installed target did not reopen") { !reopened.busy && !reopened.querying && reopened.sourceRelativePath == "Profile2.sav" && !reopened.items.isEmpty }
        let reopenedResult = search("RunResult", result.id, in: reopened, root: reopenedWindow.contentView!)
        require(reopenedResult.value == AnyHashable(3), "reopening disagreed with installed RunResult numeric value")
        selectedLabel(reopenedResult, "3", in: reopenedWindow.contentView!)
        let reopenedBounty = search("ActiveBounty", bounty.entryID, in: reopened, root: reopenedWindow.contentView!)
        require(reopenedBounty.value == AnyHashable("  revised  "), "reopening stripped ordinary text whitespace")
        let installedRoot = reopenedWindow.contentView!
        let searchInput = fields(installedRoot).first { $0.placeholderString == text("hades2.saveEditor.workbench.search") }!
        edit(searchInput, "FutureNPC", submit: true)
        until("unidentified data leaked into ordinary results") { !reopened.querying && reopened.items.isEmpty }
        let gift = search("Hecate", "gift:Hecate:GiftPoints", in: reopened, root: installedRoot)
        assertWarning(gift, in: installedRoot)
        let giftInput = fields(installedRoot).first { $0.isEditable && $0.accessibilityLabel() == gift.displayName }!
        edit(giftInput, "12")
        until("native gift quantity did not acknowledge") { !reopened.busy && reopened.pendingActions.first?.after == AnyHashable(12) }
        let claim = search("QuestUnlockMoros", "questClaim:QuestUnlockMoros", in: reopened, root: installedRoot)
        assertWarning(claim, in: installedRoot)
        require(claim.value == AnyHashable(false) && claim.editable,
                "explicit unclaimed reward is not an editable boolean intent")
        require(namedNativeControl(installedRoot, role: "AXCheckBox", name: claim.displayName)?.press() == true,
                "actual native reward grant control did not dispatch")
        until("native reward intent did not acknowledge") { !reopened.busy && reopened.pendingCount == 2 }
        let beforeRewardApply = try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav"))
        func installedPress(_ key: String, _ arguments: [String] = []) {
            let label = Hades2GameModule.resolveText(key: key, arguments: arguments, localization: localization)
            guard let button = namedNativeControl(installedRoot, role: "AXButton", name: label), button.enabled, button.press()
            else { fatalError("installed record action missing: \(key)") }
            pump()
        }
        until("gift/reward Changes review did not finish") { !reopened.busy }
        let giftInChanges = fields(installedRoot).last { $0.isEditable && $0.accessibilityLabel() == gift.displayName }!
        edit(giftInChanges, "10")
        until("gift Changes revision did not acknowledge") { !reopened.busy && reopened.pendingActions.first?.after == AnyHashable(10) }
        let giftAction = reopened.pendingActions.first { $0.entryID == gift.id }!
        let claimAction = reopened.pendingActions.first { $0.entryID == claim.id }!
        require(giftAction.effects.count == 1 && claimAction.effects.count == 5,
                "gift/reward Changes omitted a proven physical owner")
        for effect in giftAction.effects {
            require(namedNativeControl(installedRoot, role: "AXStaticText", name: effect.name!) != nil,
                    "actual Changes hid gift aggregate effects")
        }
        for effect in claimAction.effects {
            require(namedNativeControl(installedRoot, role: "AXStaticText", name: effect.name!) != nil,
                    "actual Changes hid reward resource/lifetime/CurrentRun effects")
        }
        let afterRewardStaging = try Data(contentsOf: base.appendingPathComponent("saves/Profile2.sav"))
        require(afterRewardStaging == beforeRewardApply, "gift/reward staging wrote before explicit Apply")
        installedPress("hades2.saveEditor.apply")
        until("native gift/reward Apply did not verify") { !reopened.busy && !reopened.querying && reopened.pendingCount == 0 && reopened.lastApplyReceipt != nil }
        require(reopened.lastApplyReceipt!.source == "main/Profile2.sav" && reopened.lastApplyReceipt!.target == "main/Profile2.sav"
                && !reopened.lastApplyReceipt!.runtimeReloaded, "reward receipt lost the reopened fixed source/target")
        reopenedWindow.performClose(nil)
        until("reward document did not release workspace") { reopened.workspaceID == nil }
        let rewardReopened = Hades2SaveEditorModel(session: session)
        let rewardWindow = open(rewardReopened)
        until("reward target did not reopen") { !rewardReopened.busy && !rewardReopened.querying && rewardReopened.sourceRelativePath == "Profile2.sav" && !rewardReopened.items.isEmpty }
        let installedGift = search("Hecate", gift.id, in: rewardReopened, root: rewardWindow.contentView!)
        require(installedGift.value == AnyHashable(10), "reopening lost the acknowledged gift quantity")
        let installedClaim = search("QuestUnlockMoros", claim.id, in: rewardReopened, root: rewardWindow.contentView!)
        require(installedClaim.value == AnyHashable(true) && !installedClaim.editable && installedClaim.mutationKinds.isEmpty,
                "reopened claimed reward permits duplicate grant intent")
        require(namedNativeControl(rewardWindow.contentView!, role: "AXCheckBox", name: installedClaim.displayName) == nil,
                "already-claimed reward exposes an enabled native grant control")
        rewardWindow.performClose(nil); pump(); session.stop(); pump()
        print("save_record_native_player_journey_ok")
    }
}
