import AppKit
import SwiftUI

/// Structured label with primary text and visually muted secondary suffixes
/// (such as native eligibility warnings or disabled refusal reasons).
package struct TrainerPopupLabel: Equatable {
    package let primary: String
    package let mutedSuffixes: [String]

    package init(primary: String, mutedSuffixes: [String] = []) {
        self.primary = primary
        self.mutedSuffixes = mutedSuffixes.filter { !$0.isEmpty }
    }

    package var plainText: String {
        primary + mutedSuffixes.joined()
    }

    func attributed(font: NSFont, primaryColor: NSColor?, mutedColor: NSColor) -> NSAttributedString {
        let result = NSMutableAttributedString()
        var primaryAttributes: [NSAttributedString.Key: Any] = [.font: font]
        if let primaryColor {
            primaryAttributes[.foregroundColor] = primaryColor
        }
        result.append(NSAttributedString(string: primary, attributes: primaryAttributes))
        for suffix in mutedSuffixes {
            result.append(NSAttributedString(string: suffix, attributes: [
                .font: font,
                .foregroundColor: mutedColor,
            ]))
        }
        return result
    }
}

/// Entry in a hierarchical popup selector menu (`TrainerNestedPopupButton`).
package enum TrainerPopupMenuEntry: Equatable {
    case sectionHeader(String)
    case item(id: String, label: TrainerPopupLabel, enabled: Bool, selected: Bool)
    case submenu(label: TrainerPopupLabel, enabled: Bool, entries: [TrainerPopupMenuEntry])
}

/// Shared AppKit-backed pop-up selector (`NSPopUpButton` with `pullsDown = false`)
/// for selectors that need nested submenus or rich primary/muted item styling
/// while matching every sibling `Picker`'s native double-chevron (`↕`) chrome.
package struct TrainerNestedPopupButton: NSViewRepresentable {
    @Environment(\.isEnabled) private var enabled
    let title: TrainerPopupLabel
    let entries: [TrainerPopupMenuEntry]
    let accessibilityLabel: String
    var accessibilityIdentifier: String? = nil
    let onSelect: (String) -> Void

    package init(
        title: TrainerPopupLabel,
        entries: [TrainerPopupMenuEntry],
        accessibilityLabel: String,
        accessibilityIdentifier: String? = nil,
        onSelect: @escaping (String) -> Void
    ) {
        self.title = title
        self.entries = entries
        self.accessibilityLabel = accessibilityLabel
        self.accessibilityIdentifier = accessibilityIdentifier
        self.onSelect = onSelect
    }

    package final class Coordinator: NSObject {
        var parent: TrainerNestedPopupButton
        var lastEntries: [TrainerPopupMenuEntry]?
        var lastMenuEnabled: Bool?

        init(_ parent: TrainerNestedPopupButton) {
            self.parent = parent
        }

        @MainActor @objc func selectItem(_ sender: NSMenuItem) {
            guard let id = sender.representedObject as? String else { return }
            parent.onSelect(id)
        }
    }

    package func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    package func makeNSView(context: Context) -> NSPopUpButton {
        let button = NSPopUpButton(frame: .zero, pullsDown: false)
        button.controlSize = .regular
        button.font = .systemFont(ofSize: NSFont.systemFontSize)
        button.alignment = .left
        button.lineBreakMode = .byTruncatingTail
        button.autoenablesItems = false
        button.menu?.autoenablesItems = false
        if let cell = button.cell as? NSPopUpButtonCell {
            cell.usesItemFromMenu = false
        }
        button.setContentHuggingPriority(.defaultLow, for: .horizontal)
        button.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return button
    }

    package func updateNSView(_ button: NSPopUpButton, context: Context) {
        context.coordinator.parent = self
        button.isEnabled = enabled
        button.identifier = accessibilityIdentifier.map { NSUserInterfaceItemIdentifier($0) }
        button.setAccessibilityLabel(accessibilityLabel)
        button.setAccessibilityIdentifier(accessibilityIdentifier)
        button.setAccessibilityValue(title.plainText)

        if context.coordinator.lastEntries != entries || context.coordinator.lastMenuEnabled != enabled {
            let menu = NSMenu(title: accessibilityLabel)
            menu.autoenablesItems = false
            populateMenu(menu, with: entries, coordinator: context.coordinator, controlEnabled: enabled)
            button.menu = menu
            context.coordinator.lastEntries = entries
            context.coordinator.lastMenuEnabled = enabled
        }

        let titleFont = button.font ?? .systemFont(ofSize: NSFont.systemFontSize)
        let titleItem = NSMenuItem(title: title.plainText, action: nil, keyEquivalent: "")
        titleItem.isEnabled = enabled
        titleItem.attributedTitle = title.attributed(
            font: titleFont,
            primaryColor: enabled ? .labelColor : .disabledControlTextColor,
            mutedColor: enabled ? .secondaryLabelColor : .tertiaryLabelColor
        )
        if let cell = button.cell as? NSPopUpButtonCell {
            cell.isEnabled = enabled
            cell.menuItem = titleItem
            cell.setAccessibilityLabel(accessibilityLabel)
            cell.setAccessibilityIdentifier(accessibilityIdentifier)
            cell.setAccessibilityValue(title.plainText)
        }
    }

    package func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSPopUpButton, context: Context) -> CGSize? {
        let height = nsView.intrinsicContentSize.height
        let width = proposal.width.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? nsView.intrinsicContentSize.width
        return CGSize(width: width, height: height)
    }

    private func populateMenu(
        _ menu: NSMenu,
        with entries: [TrainerPopupMenuEntry],
        coordinator: Coordinator,
        controlEnabled: Bool
    ) {
        let menuFont = NSFont.menuFont(ofSize: 0)
        for entry in entries {
            switch entry {
            case let .sectionHeader(header):
                if #available(macOS 14.0, *) {
                    menu.addItem(.sectionHeader(title: header))
                } else {
                    let item = NSMenuItem(title: header, action: nil, keyEquivalent: "")
                    item.isEnabled = false
                    menu.addItem(item)
                }
            case let .item(id, label, itemEnabled, selected):
                let effectiveEnabled = controlEnabled && itemEnabled
                let item = NSMenuItem(
                    title: label.plainText,
                    action: #selector(Coordinator.selectItem(_:)),
                    keyEquivalent: ""
                )
                item.target = coordinator
                item.representedObject = id
                item.isEnabled = effectiveEnabled
                item.state = selected ? .on : .off
                item.attributedTitle = label.attributed(
                    font: menuFont,
                    primaryColor: nil,
                    mutedColor: effectiveEnabled ? .secondaryLabelColor : .tertiaryLabelColor
                )
                menu.addItem(item)
            case let .submenu(label, subEnabled, subEntries):
                let effectiveEnabled = controlEnabled && subEnabled
                let item = NSMenuItem(title: label.plainText, action: nil, keyEquivalent: "")
                item.isEnabled = effectiveEnabled
                item.attributedTitle = label.attributed(
                    font: menuFont,
                    primaryColor: nil,
                    mutedColor: effectiveEnabled ? .secondaryLabelColor : .tertiaryLabelColor
                )
                let child = NSMenu(title: label.plainText)
                child.autoenablesItems = false
                populateMenu(child, with: subEntries, coordinator: coordinator, controlEnabled: effectiveEnabled)
                item.submenu = child
                menu.addItem(item)
            }
        }
    }
}
