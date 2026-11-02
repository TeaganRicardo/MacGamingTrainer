"""Native width/column alignment for the five Hades II Rooms & Rewards pickers.

Two direct room/encounter controls and three shared inline spawn controls use the
actual production row and Picker primitives; no game process or saves required.
"""

ROOM_PICKER_ALIGNMENT_JOURNEY = r'''
private struct RoomPickerChoice: Identifiable {
    let id: String
    let name: String
}

private struct RoomPickerAlignmentFixture: View {
    let language: TrainerPresentationLanguage
    private let choice = RoomPickerChoice(id: "reward", name: "少量金币 · Small Gold Crowns")

    private func title(_ english: String, _ chinese: String) -> String {
        language == .en ? english : chinese
    }

    @ViewBuilder
    private func directPicker(_ english: String, _ chinese: String, _ key: String) -> some View {
        let label = title(english, chinese)
        TrainerLabeledControlRow(title: label, icon: "door.left.hand.open",
                                 tint: TrainerTheme.standard.accent, emphasized: true,
                                 layout: .pickerAction) {
            Picker(label, selection: .constant("reward")) {
                Text(choice.name).tag("reward")
                Text(title("Original", "原生")).tag("original")
            }
            .labelsHidden()
            .trainerPickerWidth(.rowAction)
            TrainerShortcutBadgeSlot(text: key)
            TrainerSecondaryActionButton(title: title("Apply", "应用"), enabled: true) {}
        }
    }

    private var choices: [TrainerPickerSection<RoomPickerChoice>] {
        [TrainerPickerSection(id: 0, title: title("Rewards", "奖励"), items: [choice])]
    }

    @ViewBuilder
    private func spawnPicker(_ english: String, _ chinese: String, _ key: String) -> some View {
        let label = title(english, chinese)
        TrainerGroupedOptionPicker(
            title: label, icon: "sparkles", pickerLabel: label,
            selection: .constant("reward"), sections: choices,
            enabled: true, actionEnabled: true, inline: true,
            emptyLabel: title("None", "无"),
            actionTitle: title("Generate", "生成"), shortcutText: key,
            itemLabel: { $0.name }, onAction: { _ in }
        )
    }

    var body: some View {
        VStack(spacing: 1) {
            directPicker("Next room reward", "下一房奖励", "⌃⌥G")
            directPicker("Next qualified encounter", "下一次合资格遭遇", "⌃⌥H")
            spawnPicker("Olympian blessing", "奥林匹斯的祝福", "⌃⌥J")
            spawnPicker("Resources and pickups", "资源与常规掉落", "⌃⌥K")
            spawnPicker("Character reward", "角色奖励", "⌃⌥L")
        }
        .trainerGroupedRows()
        .frame(maxWidth: .infinity)
    }
}

@MainActor
private func exerciseRoomPickerAlignment() {
    let theme = TrainerTheme.standard
    let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
    for language in [TrainerPresentationLanguage.en, .zhCN] {
        localization.language = language
        for width in [theme.contentMinWidth, CGFloat(1050)] {
            let host = NSHostingView(rootView:
                RoomPickerAlignmentFixture(language: language)
                    .frame(width: width, height: 600, alignment: .topLeading)
                    .preferredColorScheme(.dark)
                    .trainerTheme(theme)
                    .environmentObject(localization)
            )
            let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: width, height: 600),
                styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
            window.isReleasedWhenClosed = false
            window.appearance = NSAppearance(named: .darkAqua)
            window.contentView = host
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            hierarchyWait(host) {
                window.isKeyWindow && nativeAccessibilityControls(host)
                    .filter { $0.role == "AXPopUpButton" }.count == 5
            }
            let pickers = nativeAccessibilityControls(host)
                .filter { $0.role == "AXPopUpButton" }
                .sorted { $0.frame.minY < $1.frame.minY }
            hierarchyCheck(pickers.count == 5, "five real Rooms & Rewards popups not mounted")
            let first = pickers[0].frame
            hierarchyCheck(first.width > 180 && first.width <= theme.pickerWideWidth + 1,
                           "the native popup did not occupy its shared row-action allocation")
            for (index, control) in pickers.enumerated() {
                let frame = control.frame
                hierarchyCheck(frame.width > 0 && frame.height > 0,
                               "room popup #\(index) collapsed")
                hierarchyCheck(abs(frame.minX - first.minX) <= 1 && abs(frame.width - first.width) <= 1,
                               "room popups have unequal columns: language=\(language.rawValue) window=\(width) first=\(first) #\(index)=\(frame)")
            }
            window.contentView = nil
            window.close()
        }
    }
    print("room_picker_native_alignment_ok")
}
'''
