"""Protect cross-surface UI contracts discovered by the consistency audit."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_UI = ROOT / "Sources/Core/UI"
HADES = ROOT / "Sources/Hades2"

badge = (CORE_UI / "Primitives/TrainerBadge.swift").read_text()
theme = (CORE_UI / "TrainerTheme.swift").read_text()
resource = (CORE_UI / "Components/TrainerResourceControls.swift").read_text()
status = (CORE_UI / "Components/TrainerStatusControls.swift").read_text()
management = (HADES / "Views/Hades2ManagementViews.swift").read_text()
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
assert "static func rarityControlsWidth(compactActionWidth: CGFloat)" in view
assert "static func commonControlsWidth(compactActionWidth: CGFloat)" in view
assert "TraitManagerLayout.commonControlsWidth(compactActionWidth: theme.compactActionWidth)" in view
assert "hasTemporaryContextualControls(for: trait)" in view
assert "hasContextualControls(for: trait)" not in view
assert ".padding(.trailing, TraitManagerLayout.commonControlsWidth + TraitManagerLayout.rowSpacing)" not in view
assert ".minimumScaleFactor(0.65)" not in view
assert ".minimumScaleFactor(0.85)" in view
assert ".frame(width: theme.connectionActionWidth)" not in status
assert "width: theme.connectionActionWidth" in status
assert "struct TrainerSecondaryActionButton" in primary_button
assert "TrainerActionButtonLabel(title: title, systemImage: systemImage, fillsWidth: width != nil)" in primary_button
assert ".frame(maxWidth: fillsWidth ? .infinity : nil)" in primary_button
assert ".frame(width: width)" in primary_button
assert ".frame(width: theme.shortcutCaptureWidth, alignment: .center)" in management
assert ".frame(minWidth: 110)" not in management

# Shared visual controls are adopted by the owning Core controls as well as
# feature views; do not reintroduce a second search or primary-action treatment.
assert "TrainerSearchField(" in resource
assert "TrainerLockButton(" in resource
save_editor = (HADES / "Views/Hades2SaveEditorView.swift").read_text()
assert ".padding(.horizontal, theme.panelPadding)" not in save_editor
assert ".padding(.horizontal, theme.rowHorizontalPadding)" in save_editor
assert 'TrainerShortcutBadgeSlot(text: model.shortcutText(.disableAll))' in view
assert "model.shortcutText(.disableAll))" not in view
assert "hasTemporaryContextualControls(for: trait)" in view
assert "if hasContextualControls(for: trait)" not in view
assert 'localization.localized(locked ? "host.unlock" : "host.lock")' in lock_button
assert '.accessibilityLabel(localization.localized(locked ? "host.unlock" : "host.lock"))' in lock_button
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
assert 'TrainerTextField(title: "—", text: traitLevelInput(trait))' in view
assert '.accessibilityLabel(text("hades2.traits.targetLevel"))' in view
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
visible_ui = "\n".join((view, management_view, gathering, occurrence_setting))
gathering_actions = {
    "generateFlora", "generateMining", "generateDigging", "generateShades", "generateFishing",
}
assert "generateShortcutText: model.shortcutText(family.shortcutAction)" in gathering
assert "var shortcutAction: ShortcutAction" in types
for action in actions:
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
