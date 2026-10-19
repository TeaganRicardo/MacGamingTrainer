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
assert "static let commonControlsWidth: CGFloat = 606" in view
assert "private var managedTraitHasContextualControls: Bool" in view
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
assert 'localization.localized(locked ? "host.unlock" : "host.lock")' in lock_button
assert '.accessibilityLabel(localization.localized(locked ? "host.unlock" : "host.lock"))' in lock_button
assert "TrainerPrimaryActionButton(" in status
assert ".buttonStyle(.borderedProminent)" not in status

# Shortcut settings and conflict feedback use action names, not just the name
# of the surrounding section or picker.
action_keys = {
    "hades2.shortcut.applyNextRoomReward",
    "hades2.shortcut.spawnOlympian",
    "hades2.shortcut.spawnPickup",
    "hades2.shortcut.spawnSpecial",
}
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
    assert action_keys <= table.keys()
    assert trait_action_keys <= table.keys()
    trait_labels = [table[key] for key in sorted(trait_action_keys)]
    assert len(trait_labels) == len(set(trait_labels)), f"{language} trait action labels are ambiguous"
    labels = [table[key] for key in sorted(action_keys)]
    assert len(labels) == len(set(labels)), f"{language} shortcut action labels are ambiguous"

for key in (
    'case .applyNextRoomReward: return "hades2.shortcut.applyNextRoomReward"',
    'case .spawnOlympian: return "hades2.shortcut.spawnOlympian"',
    'case .spawnPickup: return "hades2.shortcut.spawnPickup"',
    'case .spawnSpecial: return "hades2.shortcut.spawnSpecial"',
):
    assert key in types

# Every registered shortcut action must have a visible affordance in its
# owning panel or management UI. A settings entry alone is insufficient.
ui_order = types.split("static let uiOrder:", 1)[1].split("static let legacyDigitActions:", 1)[0]
actions = re.findall(r"\.([A-Za-z][A-Za-z0-9]*)", ui_order)
assert len(actions) == 20, f"unexpected shortcut inventory size: {len(actions)}"
visible_ui = view + "\n" + management_view
for action in actions:
    patterns = (
        rf"shortcut\s*:\s*\.{re.escape(action)}\b",
        rf"shortcutText\(\s*\.{re.escape(action)}\s*\)",
    )
    assert any(re.search(pattern, visible_ui) for pattern in patterns), (
        f"registered shortcut has no visible badge/affordance: {action}"
    )

print("ui_consistency_contract_ok")
