"""Protect cross-surface UI contracts discovered by the consistency audit.

Game modules adopt the shared Core controls checked here; Core's own behaviour
is asserted where it can be observed or compiled (WP1.2, #768):
- action width roles, secondary-action label/help/selected state and the
  shortcut badge lane: `exerciseSharedActionGeometry` (management_ui_harness);
- lock labels, sheet Done/Escape and shortcut capture: the management and sheet
  journeys; picker allocation and the dual picker: the hierarchy journey (all
  run by test_hades_frontend.py and test_hades2_view_state_flow.py);
- card geometry: test_cross_module_geometry_macos.py; the disable-all chord:
  test_shortcut_chord_semantics.py and test_global_hotkey_routing.py.
Only the cross-module lints below stay source-text checks.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HADES = ROOT / "Sources/Hades2"
HADES1 = ROOT / "Sources/Hades"

management = (HADES / "Views/Hades2ManagementViews.swift").read_text()
hades1_management = (HADES1 / "HadesManagement.swift").read_text()
occurrence = (HADES / "Views/Hades2OccurrenceSetting.swift").read_text()
types = (HADES / "Hades2Types.swift").read_text()
view = (HADES / "Hades2View.swift").read_text()
management_view = (HADES / "Views/Hades2ManagementViews.swift").read_text()

# Module rows adopt the shared secondary action and Core trait layout.
assert "TrainerSecondaryActionButton(" in occurrence
assert view.count("TrainerSecondaryActionButton(") >= 6
assert "TrainerTraitManagerLayout.commonControlsWidth(" in view
assert "hasTemporaryContextualControls(for: trait)" not in view
assert "trait.hasTemporaryContextualControls" in view
assert "trait.hasContextualControls" in view
assert "var hasTemporaryContextualControls: Bool" in types
assert "var hasContextualControls: Bool" in types
assert ".padding(.trailing, TrainerTraitManagerLayout.commonControlsWidth + TrainerTraitManagerLayout.rowSpacing)" not in view
assert ".minimumScaleFactor(0.65)" not in view
assert ".minimumScaleFactor(0.85)" in view
assert "helpText: generateHelp" in occurrence
assert 'accessibilityLabel: title + " " + generateLabel' in occurrence

# Both modules supply only game-owned action descriptors and validation. The
# shared Core UI owns the rows, fixed read-only bindings and monitor lifecycle.
hades1_shortcuts = (HADES1 / "HadesTrainerView.swift").read_text()
for source in (hades1_shortcuts, management):
    assert "TrainerShortcutSettingsView(" in source
    assert "isEditable: action != .disableAll" in source
    assert "NSEvent.addLocalMonitorForEvents" not in source
    assert "NSEvent.removeMonitor" not in source

save_editor = (HADES / "Views/Hades2SaveEditorView.swift").read_text()
assert ".padding(.horizontal, theme.panelPadding)" not in save_editor
assert ".padding(.horizontal, theme.rowHorizontalPadding)" in save_editor
assert 'TrainerShortcutBadgeSlot(text: model.shortcutText(.disableAll))' not in management
assert 'TrainerShortcutBadgeSlot(text: model.shortcutText(.disableAll))' not in hades1_management
assert "TrainerManagementGroups(" in management
assert "TrainerManagementGroups(" in hades1_management
assert 'model.shortcutText(.disableAll))", systemImage: "power"' not in view
assert "hasTemporaryContextualControls(for: trait)" not in view
assert "if hasContextualControls(for: trait)" not in view

# Shortcut settings and conflict feedback use action names, not just the name
# of the surrounding section or picker.
shortcut_start = types.index("enum ShortcutAction: String, CaseIterable, Identifiable {")
shortcut_end = types.index("struct ElementCount", shortcut_start)
shortcut_block = types[shortcut_start:shortcut_end]
shortcut_declarations = shortcut_block.split("var id:", 1)[0]
actions = [
    action.strip().lstrip(".").split("=", 1)[0].strip()
    for declaration in re.findall(r"^\s*case\s+([^\n]+)$", shortcut_declarations, re.M)
    for action in declaration.split(",")
]
presentation_block = shortcut_block.split("var presentationKey: String", 1)[1]
presentation_cases = dict(re.findall(
    r'case \.([A-Za-z][A-Za-z0-9]*): return "([^"]+)"',
    presentation_block,
))
assert len(actions) == len(set(actions)), "duplicate shortcut action declaration"
assert 'case applyWorldExit = "applyNextRoomReward"' in shortcut_declarations, (
    "World Exit source identity must retain only the released storage raw value"
)
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
    'case .applyWorldExit: return "hades2.shortcut.applyWorldExit"',
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
chaos_row = (HADES / "Views/Hades2ChaosGatePanel.swift").read_text()
assert "Hades2OccurrenceSetting(" in chaos_row
assert "generateShortcutText: model.shortcutText(.generateChaosGate)" in chaos_row
facility_row = (HADES / "Views/Hades2ChamberFacilityPanel.swift").read_text()
assert "model.shortcutText(.generateChamberFacility)" in facility_row
visible_ui = "\n".join((view, management_view, gathering, occurrence_setting, rarity, chaos_row, facility_row))
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

# Kept (lint): every native Picker passes through the Core presentation owner;
# SwiftUI offers no compile-time hook that forces a modifier onto each Picker.
picker_exceptions = {Path("Sources/Core/Host/TrainerLocalization.swift")}
for source_root in (ROOT / "Sources/Core", ROOT / "Sources/Hades", ROOT / "Sources/Hades2"):
    for swift_path in source_root.rglob("*.swift"):
        source = swift_path.read_text()
        relative = swift_path.relative_to(ROOT)
        picker_count = len(re.findall(r"(?<![A-Za-z])Picker\s*\(", source))
        if not picker_count:
            continue
        if relative in picker_exceptions:
            assert "CommandMenu(" in source and ".trainerPicker(" not in source
            continue
        owner_count = source.count(".trainerPicker(")
        assert picker_count == owner_count, (
            f"{relative} has {picker_count} Pickers but {owner_count} presentation owners"
        )
assert ".trainerPicker(.rowAction" in (ROOT / "Sources/Hades/HadesRoomsPanel.swift").read_text()
world_actions = view[view.index("private var worldExitPanel"):view.index("private var nextOccurrencePanel")]
assert world_actions.count(".trainerPicker(.layoutAllocated") == 2
assert "TrainerDualPickerActionRow(" in world_actions
assert "model.canSelectWorldExitTarget" in world_actions
assert "latched: model.selectedWorldExitLease != nil" in world_actions
assert "subduedLatched: true" in world_actions
assert 'title: text(model.selectedWorldExitLease != nil ? "hades2.worldActions.cancel" : "hades2.worldActions.apply")' in world_actions
assert ".trainerPicker(.layoutAllocated" in (ROOT / "Sources/Hades/HadesRoomsPanel.swift").read_text()
assert "subduedLatched: true" in (ROOT / "Sources/Hades/HadesRoomsPanel.swift").read_text()

# Kept (lint): raw action widths cannot leak back into game modules. TrainerRow
# supplies the compact action column; standalone controls opt into a role.
for source_root in (ROOT / "Sources/Hades", ROOT / "Sources/Hades2"):
    for swift_path in source_root.rglob("*.swift"):
        source = swift_path.read_text()
        assert "width: theme.compactActionWidth" not in source, swift_path
        assert "width: theme.connectionActionWidth" not in source, swift_path
for action_surface in (
    ROOT / "Sources/Hades/HadesSaveEditorView.swift",
    ROOT / "Sources/Hades2/Views/Hades2SaveEditorView.swift",
    ROOT / "Sources/Hades2/Views/Hades2SaveAdvancedValueView.swift",
):
    assert "widthRole: .sheet" in action_surface.read_text(), action_surface

assert "tint: hasOverride ? theme.accent : theme.inactive" in occurrence
assert "inline: true" in view
assert "specialSearch" not in view
assert "TrainerLockSlot()" in occurrence

# Kept (structural): Core management actions declare no key equivalents. The
# global chords belong to the Carbon hotkeys and the shortcut-capture monitor,
# which a SwiftUI menu/button key equivalent would pre-empt.
assert '.keyboardShortcut(' not in (ROOT / "Sources/Core/UI/Components/TrainerManagementGroups.swift").read_text()

# Kept until a sheet-gesture journey reaches them: the Done monitor's guards
# for IME composition, multiline editors, field-editor commit, Return/Enter,
# outside tool-window clicks and nested sheets. Escape and parent-window clicks
# are already asserted by the sheet and Save editor journeys.
sheet_completion = (ROOT / "Sources/Core/UI/Components/TrainerSheetScaffold.swift").read_text()
assert "editor.hasMarkedText()" in sheet_completion
assert "if !editor.isFieldEditor" in sheet_completion
assert "[36, 53, 76].contains(Int(event.keyCode))" in sheet_completion
assert "clickedWindow.styleMask.contains(.titled)" in sheet_completion
assert "window.attachedSheet == nil" in sheet_completion
assert "window.makeFirstResponder(nil)" in sheet_completion
# Same follow-up: Return/Esc and outside-click Done on the Core sheets whose
# gestures no journey drives yet (the shortcut sheet's are driven), the Save
# manager's busy/editing guards, and capture teardown when a sheet disappears.
CORE_UI = ROOT / "Sources/Core/UI"
save_manager_source = (ROOT / "Sources/Core/Save/TrainerSaveManagerView.swift").read_text()
retention_source = (ROOT / "Sources/Core/Save/TrainerSaveRetentionSettings.swift").read_text()
profile_source = (CORE_UI / "Components/TrainerProfileManagerView.swift").read_text()
diagnostics_source = (CORE_UI / "Components/TrainerDiagnosticsView.swift").read_text()
issues_source = (CORE_UI / "TrainerCurrentIssues.swift").read_text()
shortcut_sheet = (CORE_UI / "Components/TrainerShortcutSettingsView.swift").read_text()
assert '.keyboardShortcut(.defaultAction)' in issues_source and '.onExitCommand(perform: onClose)' in issues_source
for source in (profile_source, diagnostics_source, save_manager_source, retention_source):
    assert '.keyboardShortcut(.defaultAction)' in source
    assert '.trainerSheetDoneGestures(' in source
assert "outsideWindowClicks: true" in save_manager_source
assert "guard !model.busy, editingID == nil," in save_manager_source
assert "enabled: !model.busy && editingID == nil" in save_manager_source
restore_confirmation = save_manager_source.split("private struct TrainerSaveRestoreConfirmationView", 1)[1]
assert "trainerSheetDoneGestures(perform: onCancel)" in restore_confirmation
assert ".keyboardShortcut(.defaultAction)" in restore_confirmation
assert '.keyboardShortcut(.defaultAction)' not in restore_confirmation.split(
    'TrainerPrimaryActionButton(title: localization.localized("host.restore")', 1
)[1]
assert ".onDisappear { lifetime.invalidate(); capture.cancel() }" in shortcut_sheet
assert "if entry.isEditable {" in shortcut_sheet and "trainer.shortcut.fixed." in shortcut_sheet

# Kept until a rendered status check exists: the sidebar indicator's colour
# priority, accessibility value and multi-line help.
sidebar = (CORE_UI / "TrainerSidebar.swift").read_text()
assert 'if targetRunning { return theme.warning }' in sidebar
assert '.accessibilityValue(localization.string(detailToken))' in sidebar
assert 'let lines = busy' in sidebar
assert 'return lines.joined(separator: "\\n")' in sidebar

# Top-level module sections share TrainerSection (never bare @ViewBuilder
# siblings in pageSpacing), and both trait-management headers use the same
# TrainerIconLabel badge format.
hades1_view = (HADES1 / "HadesTrainerView.swift").read_text()
hades1_run_data = hades1_view.split("private var runDataSection: some View {", 1)[1].split(
    "private var commonSection: some View {", 1
)[0]
hades2_run_data = view.split("private var statusAndSessionSection: some View {", 1)[1].split(
    "private var commonSection: some View {", 1
)[0]
assert "TrainerSection(" in hades1_run_data and "TrainerSection(" in hades2_run_data
assert "@ViewBuilder\n    private var statusAndSessionSection" not in view

hades1_traits = hades1_view.split("private struct HadesCurrentTraitsPanel:", 1)[1].split(
    "private struct HadesCurrentTraitPlaceholderRow:", 1
)[0]
hades2_traits = view.split("private var currentRunTraitsPanel: some View {", 1)[1].split(
    "private func currentRunTraitContextualControls", 1
)[0]
assert 'TrainerIconLabel(' in hades1_traits and 'Label(text("hades.currentTraits")' not in hades1_traits
assert 'TrainerIconLabel(' in hades2_traits and 'Label(text("hades2.traits.manager")' not in hades2_traits

print("ui_consistency_contract_ok")
