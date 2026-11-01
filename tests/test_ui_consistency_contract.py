"""Protect cross-surface UI contracts discovered by the consistency audit."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_UI = ROOT / "Sources/Core/UI"
HADES = ROOT / "Sources/Hades2"
HADES1 = ROOT / "Sources/Hades"

badge = (CORE_UI / "Primitives/TrainerBadge.swift").read_text()
theme = (CORE_UI / "TrainerTheme.swift").read_text()
resource = (CORE_UI / "Components/TrainerResourceControls.swift").read_text()
status = (CORE_UI / "Components/TrainerStatusControls.swift").read_text()
sidebar = (CORE_UI / "TrainerSidebar.swift").read_text()
host = (ROOT / "Sources/Core/Host/TrainerHost.swift").read_text()
management = (HADES / "Views/Hades2ManagementViews.swift").read_text()
hades1_management = (HADES1 / "HadesManagement.swift").read_text()
core_management = (CORE_UI / "Components/TrainerManagementGroups.swift").read_text()
primary_button = (CORE_UI / "Components/TrainerListControls.swift").read_text()
lock_button = (CORE_UI / "Primitives/TrainerToggleControl.swift").read_text()
occurrence = (HADES / "Views/Hades2OccurrenceSetting.swift").read_text()
types = (HADES / "Hades2Types.swift").read_text()
view = (HADES / "Hades2View.swift").read_text()
management_view = (HADES / "Views/Hades2ManagementViews.swift").read_text()

# A shortcut has one width owner. Direct badges and optional slots render the
# same control, rather than giving one presentation path a different minimum.
assert ".frame(minWidth: 52, alignment: .center)" in badge
assert badge.index(".frame(minWidth: 52, alignment: .center)") < badge.index(".background(theme.subtleFill")
slot = badge[badge.index("struct TrainerShortcutBadgeSlot"): ]
assert ".frame(minWidth: 52" not in slot

# The shortcut capture control has a stable width while a chord is being
# captured and after assignment; long labels/chords must not resize the column.
assert "let shortcutCaptureWidth: CGFloat" in theme
assert "shortcutCaptureWidth: 180" in theme
assert "let connectionActionWidth: CGFloat" in theme
assert "connectionActionWidth: 160" in theme
assert "compactActionWidth: 88" in theme
assert "TrainerSecondaryActionButton(" in resource
assert "TrainerSecondaryActionButton(" in occurrence
assert view.count("TrainerSecondaryActionButton(") >= 6
assert "static let removeControlWidth: CGFloat = 132" in view
assert "static let commonControlsWidth: CGFloat = 606" not in view
assert "static let levelControlsWidth: CGFloat = 200" not in view
assert "static let rarityControlsWidth: CGFloat = 250" not in view
assert "static func levelControlsWidth(compactActionWidth: CGFloat)" in view
assert "static func rarityControlsWidth(compactActionWidth: CGFloat, pickerWidth: CGFloat)" in view
assert "static func commonControlsWidth(compactActionWidth: CGFloat, pickerWidth: CGFloat)" in view
assert "42 + 58 + compactActionWidth + 2 * 6" in view
assert "48 + pickerWidth + compactActionWidth + 2 * 6" in view
assert "+ removeControlWidth" in view
assert "TraitManagerLayout.commonControlsWidth(compactActionWidth: theme.compactActionWidth, pickerWidth: theme.pickerCompactWidth)" in view
assert "hasTemporaryContextualControls(for: trait)" not in view
assert "trait.hasTemporaryContextualControls" in view
assert "trait.hasContextualControls" in view
assert "var hasTemporaryContextualControls: Bool" in types
assert "var hasContextualControls: Bool" in types
assert ".padding(.trailing, TraitManagerLayout.commonControlsWidth + TraitManagerLayout.rowSpacing)" not in view
assert ".minimumScaleFactor(0.65)" not in view
assert ".minimumScaleFactor(0.85)" in view
assert ".frame(width: theme.connectionActionWidth)" not in status
assert "widthRole: .connection" in status
assert '"MAC GAMING"' not in sidebar
assert 'host.gameLibrary' not in sidebar
assert 'if targetRunning { return theme.warning }' in sidebar
assert '.accessibilityValue(localization.string(detailToken))' in sidebar
assert 'busy: model.busy' in host
assert 'targetRunning: targetMonitor.isRunning' in host
assert 'Text(localization.string(statusToken))' not in status
assert 'Text(localization.string(detailToken))' not in status
assert 'operationToken: model.operation' not in host[host.index('TrainerConnectionStatusCard('):host.index('Module.makeSidebarActions') ]
assert "struct TrainerSecondaryActionButton" in primary_button
assert ".help(helpText ?? \"\")" in primary_button
assert ".accessibilityLabel(accessibilityLabel ?? title)" in primary_button
assert "helpText: generateHelp" in occurrence
assert 'accessibilityLabel: title + " " + generateLabel' in occurrence
# Core owns the same compact, text-only labeled action geometry for every
# game. Legacy systemImage arguments on old callers cannot change rendering.
assert primary_button.count("TrainerActionButtonLabel(title: title, fillsWidth: widthRole != .sheet && (widthRole != .automatic || inheritedRowWidth != nil))") == 2
label_body = primary_button[primary_button.index("private struct TrainerActionButtonLabel"):
                            primary_button.index("struct TrainerPrimaryActionButton")]
assert "Text(title)" in label_body and "Label(title, systemImage:" not in label_body
assert ".frame(maxWidth: fillsWidth ? .infinity : nil)" in label_body
assert "enum TrainerActionWidthRole" in primary_button
for role in ("case automatic", "case compactRow", "case connection", "case sheet"):
    assert role in primary_button
assert primary_button.count(".modifier(TrainerActionWidthModifier(role: widthRole))") == 2
assert "inheritedRowWidth" in primary_button
row_source = (ROOT / "Sources/Core/UI/Primitives/TrainerRow.swift").read_text()
assert ".environment(\\.trainerActionWidth, theme.compactActionWidth)" in row_source
assert "let width: CGFloat?" not in primary_button
assert "width: CGFloat? = nil" not in primary_button
shortcut_sheet = (CORE_UI / "Components/TrainerShortcutSettingsView.swift").read_text()
capture = (ROOT / "Sources/Core/Input/TrainerShortcutCapture.swift").read_text()
assert ".frame(width: theme.shortcutCaptureWidth, alignment: .center)" in shortcut_sheet
assert ".frame(minWidth: 110)" not in shortcut_sheet

# Both modules supply only game-owned action descriptors and validation. The
# shared Core UI owns the rows, fixed read-only bindings and monitor lifecycle.
hades1_shortcuts = (HADES1 / "HadesTrainerView.swift").read_text()
for source in (hades1_shortcuts, management):
    assert "TrainerShortcutSettingsView(" in source
    assert "isEditable: action != .disableAll" in source
    assert "NSEvent.addLocalMonitorForEvents" not in source
    assert "NSEvent.removeMonitor" not in source
assert "if entry.isEditable {" in shortcut_sheet
assert "shortcutLabel(entry.chordText)" in shortcut_sheet
assert "trainer.shortcut.fixed." in shortcut_sheet
assert ".onDisappear { lifetime.invalidate(); capture.cancel() }" in shortcut_sheet
assert "TrainerGamePageVisibilityObserver" in shortcut_sheet
assert "GlobalHotkeys.beginShortcutCapture()" in capture
assert "GlobalHotkeys.endShortcutCapture(token)" in capture


# Shared visual controls are adopted by the owning Core controls as well as
# feature views; do not reintroduce a second search or primary-action treatment.
assert "TrainerSearchField(" in resource
assert "TrainerLockButton(" in resource
save_editor = (HADES / "Views/Hades2SaveEditorView.swift").read_text()
assert ".padding(.horizontal, theme.panelPadding)" not in save_editor
assert ".padding(.horizontal, theme.rowHorizontalPadding)" in save_editor
assert 'TrainerShortcutBadgeSlot(text: model.shortcutText(.disableAll))' not in management
assert 'TrainerShortcutBadgeSlot(text: model.shortcutText(.disableAll))' not in hades1_management
assert "TrainerManagementGroups(" in management
assert "TrainerManagementGroups(" in hades1_management
assert "TrainerSemanticIcon.Tool.disableAll" in core_management
assert 'model.shortcutText(.disableAll))", systemImage: "power"' not in view
assert "hasTemporaryContextualControls(for: trait)" not in view
assert "if hasContextualControls(for: trait)" not in view
assert 'localization.localized(locked ? "host.unlockValue" : "host.lockValue", arguments: [title])' in lock_button
assert "TrainerPrimaryActionButton(" in status
assert ".buttonStyle(.borderedProminent)" not in status

# Shortcut settings and conflict feedback use action names, not just the name
# of the surrounding section or picker.
shortcut_start = types.index("enum ShortcutAction: String, CaseIterable, Identifiable {")
shortcut_end = types.index("struct ElementCount", shortcut_start)
shortcut_block = types[shortcut_start:shortcut_end]
shortcut_declarations = shortcut_block.split("var id:", 1)[0]
actions = [
    action.strip().lstrip(".")
    for declaration in re.findall(r"^\s*case\s+([^\n]+)$", shortcut_declarations, re.M)
    for action in declaration.split(",")
]
presentation_block = shortcut_block.split("var presentationKey: String", 1)[1]
presentation_cases = dict(re.findall(
    r'case \.([A-Za-z][A-Za-z0-9]*): return "([^"]+)"',
    presentation_block,
))
assert len(actions) == len(set(actions)), "duplicate shortcut action declaration"
assert presentation_cases.get("disableAll") == "host.disableAll"
assert set(presentation_cases) == set(actions), (
    "every registered shortcut action must have one presentation label"
)
action_keys = set(presentation_cases.values())
trait_action_keys = {
    "hades2.traits.applyLevel",
    "hades2.traits.applyRarity",
}
assert 'text("hades2.traits.levelLabel")' in view
# Native trait-input names are covered by test_runtime_text_edit_completion.py;
# the initializer/outer-modifier shape does not prove the AppKit name.
assert '.minimumScaleFactor(0.72)' not in view
assert '.minimumScaleFactor(0.8)' not in view
assert 'text("hades2.traits.applyLevel")' in view
assert 'text("hades2.traits.applyRarity")' in view

for language in ("en", "zh-CN"):
    table = json.loads(
        (HADES / f"Presentation/Localization/hades2.{language}.json").read_text()
    )["entries"]
    module_action_keys = {key for key in action_keys if key.startswith("hades2.")}
    assert module_action_keys <= table.keys()
    assert trait_action_keys <= table.keys()
    assert "hades2.op.acquireExactBoon" not in table
    assert "hades2.shortcut.disableAll" not in table
    trait_labels = [table[key] for key in sorted(trait_action_keys)]
    assert len(trait_labels) == len(set(trait_labels)), f"{language} trait action labels are ambiguous"
    host_strings = (ROOT / "Resources" / "Localization" / f"{language}.lproj" / "Host.strings").read_text()
    host_disable_all = re.search(r'"host.disableAll" = "([^"]+)";', host_strings)
    assert host_disable_all, f"{language} Host-owned Disable All label is missing"
    labels = [table[key] for key in sorted(module_action_keys)] + [host_disable_all.group(1)]
    assert len(labels) == len(set(labels)), f"{language} shortcut action labels are ambiguous"

for key in (
    'case .applyNextRoomReward: return "hades2.shortcut.applyNextRoomReward"',
    'case .spawnOlympian: return "hades2.shortcut.spawnOlympian"',
    'case .spawnPickup: return "hades2.shortcut.spawnPickup"',
    'case .spawnSpecial: return "hades2.shortcut.spawnSpecial"',
):
    assert key in types

# Every registered action must be discoverable at its owning UI seam. The five
# gathering actions share one family-driven row, so their mapping is checked
# through Hades2GatheringFamily rather than five duplicated view literals.
gathering = (HADES / "Views/Hades2GatheringPanel.swift").read_text()
occurrence_setting = (HADES / "Views/Hades2OccurrenceSetting.swift").read_text()
rarity = (HADES / "Views/Hades2BoonRarityPanel.swift").read_text()
visible_ui = "\n".join((view, management_view, gathering, occurrence_setting, rarity))
common_section = view[view.index("private var commonSection: some View {"):view.index("private var boonsSection: some View {")]
assert "Hades2WorkbenchCatalog.shortcutActions(in: .common)" in common_section
assert "action.commonFeatureIcon" in common_section
common_actions = {
    "invincibility", "infiniteHealth", "infiniteMana", "infiniteMoney", "infiniteRerolls",
    "forceEnableRerolls", "instantCastCooldown", "hexAlwaysReady", "infiniteAmmo", "autoMiniGames",
}
gathering_actions = {
    "generateFlora", "generateMining", "generateDigging", "generateShades", "generateFishing",
}
assert "generateShortcutText: model.shortcutText(family.shortcutAction)" in gathering
assert "var shortcutAction: ShortcutAction" in types
for action in actions:
    if action == "disableAll":
        assert "TrainerManagementGroups(" in management_view
        assert "TrainerSemanticIcon.Tool.disableAll" in core_management
        assert "TrainerShortcutBadgeSlot(text: model.shortcutText(.disableAll))" not in management_view
        continue
    if action in common_actions:
        continue
    if action in gathering_actions:
        assert re.search(rf"case \.{re.escape(action)}: \.\w+", types), (
            f"gathering shortcut is not mapped to a family: {action}"
        )
        continue
    patterns = (
        rf"shortcut\s*:\s*\.{re.escape(action)}\b",
        rf"shortcutText\(\s*\.{re.escape(action)}\s*\)",
    )
    assert any(re.search(pattern, visible_ui) for pattern in patterns), (
        f"registered shortcut has no visible badge/affordance: {action}"
    )

print("ui_consistency_contract_ok")


resource_controls = (ROOT / "Sources/Core/UI/Components/TrainerResourceControls.swift").read_text()
occurrence_setting = (HADES / "Views/Hades2OccurrenceSetting.swift").read_text()
assert "TrainerIconLabel(title: title, icon: icon, tint: state.indicatorColor, emphasized: state.isOn)" in resource_controls

# All native Picker instances use the same Core-owned width roles. This prevents
# content-driven widths and per-view frame constants from reappearing.
assert "enum TrainerPickerWidthRole" in theme
assert "pickerCompactWidth: 152" in theme
assert "pickerStandardWidth: 216" in theme
assert "pickerWideWidth: 288" in theme
assert "pickerActionLabelWidth: 200" in theme
for role in ("case compactValue", "case rowValue", "case rowAction", "case form", "case expanding"):
    assert role in theme
assert "idealWidth: theme.pickerWideWidth" in theme
assert "content.frame(minWidth: theme.pickerStandardWidth, maxWidth: .infinity)" in theme
legacy_picker_roles = re.compile(r"\.trainerPickerWidth\(\.(compact|standard|wide|flexible)\)")
picker_exceptions = {Path("Sources/Core/Host/TrainerLocalization.swift")}
for source_root in (ROOT / "Sources/Core", ROOT / "Sources/Hades", ROOT / "Sources/Hades2"):
    for swift_path in source_root.rglob("*.swift"):
        source = swift_path.read_text()
        relative = swift_path.relative_to(ROOT)
        assert not legacy_picker_roles.search(source), f"{relative} still uses a size-named Picker role"
        picker_count = len(re.findall(r"(?<![A-Za-z])Picker\s*\(", source))
        if not picker_count:
            continue
        if relative in picker_exceptions:
            assert "CommandMenu(" in source and ".trainerPickerWidth(" not in source
            continue
        width_count = source.count(".trainerPickerWidth(")
        assert picker_count == width_count, (
            f"{relative} has {picker_count} Pickers but {width_count} semantic width roles"
        )
assert ".trainerPickerWidth(.rowAction)" in (ROOT / "Sources/Hades/HadesRoomsPanel.swift").read_text()
assert ".trainerPickerWidth(.rowAction)" in view
assert ".trainerPickerWidth(inline ? .rowAction : .expanding)" in resource_controls
assert "layout: .pickerAction" in resource_controls
row_primitive = (ROOT / "Sources/Core/UI/Primitives/TrainerRow.swift").read_text()
assert "enum TrainerLabeledControlLayout" in row_primitive
assert "layout == .pickerAction ? theme.pickerActionLabelWidth : nil" in row_primitive

# Raw action widths cannot leak back into game modules. TrainerRow supplies
# the compact action column; standalone controls opt into a semantic role.
for source_root in (ROOT / "Sources/Hades", ROOT / "Sources/Hades2"):
    for swift_path in source_root.rglob("*.swift"):
        source = swift_path.read_text()
        assert "width: theme.compactActionWidth" not in source, swift_path
        assert "width: theme.connectionActionWidth" not in source, swift_path
assert "case .automatic:" in primary_button
assert "if let inheritedRowWidth" in primary_button
assert "widthRole: .connection" in status
for action_surface in (
    ROOT / "Sources/Core/Save/TrainerSaveManagerView.swift",
    ROOT / "Sources/Core/UI/Components/TrainerProfileManagerView.swift",
    ROOT / "Sources/Hades/HadesSaveEditorView.swift",
    ROOT / "Sources/Hades2/Views/Hades2SaveEditorView.swift",
):
    assert "widthRole: .sheet" in action_surface.read_text(), action_surface

# The Hades II material editor has exactly two horizontal rows. The selector,
# amount input and lock stay together on its second row.
resource_editor = resource[
    resource.index("struct TrainerResourceEditor"):
    resource.index("struct TrainerGroupedOptionPicker")
]
assert resource_editor.count("HStack") == 2
control_row_start = resource_editor.index("HStack(spacing: 12)")
control_row_end = resource_editor.index("\n            }\n        }\n    }", control_row_start)
control_row = resource_editor[control_row_start:control_row_end]
assert "Picker(title" in control_row
assert "TrainerNumberField(" in control_row
assert "TrainerLockButton(" in control_row
assert ".trainerPickerWidth(.expanding)" in control_row

assert "tint: hasOverride ? theme.accent : theme.inactive" in occurrence_setting
assert "inline: true" in view
assert "specialSearch" not in view

assert 'let lines = busy' in sidebar
assert 'return lines.joined(separator: "\\n")' in sidebar
