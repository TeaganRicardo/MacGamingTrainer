import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT / path).read_text(encoding='utf-8')

view = read('Sources/Hades2/Hades2View.swift')
types = read('Sources/Hades2/Hades2Types.swift')
model = read('Sources/Hades2/Hades2Model.swift')
store = read('Sources/Hades2/Services/Hades2ShortcutStore.swift')
management = read('Sources/Hades2/Views/Hades2ManagementViews.swift')
gathering = read('Sources/Hades2/Views/Hades2GatheringPanel.swift')
occurrence = read('Sources/Hades2/Views/Hades2OccurrenceSetting.swift')
badge = read('Sources/Core/UI/Primitives/TrainerBadge.swift')
lua = read('Backend/games/hades2/runtime/hades.lua')

# Dynamic spawn lists remain bilingual. Resource rows put the active Host
# language first and suppress a duplicated secondary label when one installed
# game language had to fall back to the other.
assert '"\\(option.name) · \\(option.englishName)"' in view
assert 'let primaryName = localization.language == .en && !resource.englishName.isEmpty' in view
assert 'let secondaryName = localization.language == .en ? resource.name : resource.englishName' in view
assert 'secondaryName.isEmpty || secondaryName == primaryName' in view
assert '"\\(primaryName) · \\(secondaryName)"' in view
# Next-room reward labels resolve through the shipped bilingual table, so the
# view names a key per reward id instead of embedding either language.
for reward in (
    'RoomMoneyDrop',
    'MetaCurrencyDrop',
    'MetaCardPointsCommonDrop',
    'MemPointsCommonDrop',
    'MaxHealthDrop',
    'MaxManaDrop',
    'StackUpgrade',
    'WeaponUpgrade',
    'SpellDrop',
):
    assert f'rewardLabel("{reward}")' in view
for retired in (
    'RoomRewardMoney', 'RoomRewardMetaPoint', 'RoomRewardPsyche',
    'RoomRewardMixerFabric', 'RoomRewardMaxHealth', 'RoomRewardPom',
):
    assert retired not in view, retired
assert 'room.ChosenRewardType = rewardType' in lua
assert 'return "Boon", wanted' in lua

# Selene catalog identity keeps SpellDrop (Hex choice) distinct from TalentDrop
# (Path of Stars points). Runtime spawning semantics are exercised through
# production M.dispatch in test_hades2_store_reward_spawn_semantics.py.
assert '{ id = "TalentDrop", name = "繁星之路", category = "角色奖励", kind = "consumable", group = "special", family = "Selene"' in lua
assert 'sourceId = "Selene", sourceName = "塞勒涅"' in lua

# ShortcutAction declaration order is the sole default-allocation order.
# Expand the actual SwiftUI composition tree and compare its visible shortcut
# affordances with CaseIterable order. This catches missing registrations and
# actions whose default chord is out of top-to-bottom order.
def source_section(source, start, end):
    start_at = source.index(start)
    return source[start_at:source.index(end, start_at + len(start))]

def enum_cases(source, start, end):
    body = source_section(source, start, end).split("var id:", 1)[0]
    declarations = re.findall(r"^\s*case\s+([^\n]+)$", body, re.M)
    return [name for declaration in declarations for name in re.findall(r"[A-Za-z]\w*", declaration)]

def shortcut_references(source):
    pattern = re.compile(
        r"\bshortcut\s*:\s*\.([A-Za-z]\w*)|"
        r"\bshortcutText\(\s*\.([A-Za-z]\w*)\s*\)"
    )
    return [match.group(1) or match.group(2) for match in pattern.finditer(source)]

action_order = enum_cases(
    types,
    "enum ShortcutAction: String, CaseIterable, Identifiable {",
    "struct ElementCount",
)
family_order = enum_cases(
    types,
    "enum Hades2GatheringFamily:",
    "struct Hades2GatheringTarget",
)
assert "static let uiOrder" not in types
assert "ShortcutAction.uiOrder" not in store + model + management
assert "ShortcutAction.allCases" in store
assert "ShortcutAction.allCases" in model
assert "ShortcutAction.allCases" in management
assert 'title: "hades2.op.acquireSelectedReward"' in model
assert 'title: "hades2.op.acquireChaosPair"' in model
assert "family.shortcutAction" in gathering
assert "generateShortcutText: model.shortcutText(family.shortcutAction)" in gathering
assert "TrainerShortcutBadgeSlot(text: generateShortcutText)" in occurrence

combat = source_section(view, "private var combatSection: some View {", "private var buildSection: some View {")
build = source_section(view, "private var buildSection: some View {", "private func text(_ key: String, arguments: [String]) -> String {")
boon_rarity = source_section(view, "private var boonRarityPanel: some View {", "private var nextRoomRewardPanel: some View {")
build = build.replace("            boonRarityPanel\n", boon_rarity)
resource = source_section(view, "private var resourcePanel: some View {", "private var boonPanel: some View {")
boon = source_section(view, "private var boonPanel: some View {", "private func exactItemLabel(")
next_room = source_section(view, "private var nextRoomRewardPanel: some View {", "private var nextOccurrencePanel: some View {")
next_occurrence = source_section(view, "private var nextOccurrencePanel: some View {", "private var resourcePanel: some View {")
spawn = source_section(view, "private var spawnSection: some View {", "private var gameSpeedMapping:")
spawn = spawn.replace("                boonPanel\n", boon)
spawn = spawn.replace("                nextRoomRewardPanel\n", next_room)
spawn = spawn.replace("                nextOccurrencePanel\n", next_occurrence)
management_controls = source_section(view, "private var management: some View {", "private func featureRow(")
root = source_section(view, "private var rootContent: some View {", "@ViewBuilder\n    private var statusAndSessionSection")
root_order = re.findall(
    r"(combatSection|buildSection|resourceSection|Hades2GatheringPanel\(model: model\)|"
    r"Hades2ChaosGatePanel\(model: model\)|spawnSection|management)",
    root,
)
expanded = {
    "combatSection": combat,
    "buildSection": build,
    "resourceSection": resource,
    "Hades2GatheringPanel(model: model)": None,
    "Hades2ChaosGatePanel(model: model)": "",
    "spawnSection": spawn,
    "management": management_controls,
}
visible_order = []
for item in root_order:
    if item == "Hades2GatheringPanel(model: model)":
        visible_order.extend(["generate" + family[:1].upper() + family[1:] for family in family_order])
    else:
        visible_order.extend(shortcut_references(expanded[item]))
assert visible_order == action_order, (
    "ShortcutAction declaration order must follow the rendered top-to-bottom control order; "
    f"UI={visible_order}, registry={action_order}"
)
assert len(set(action_order)) == len(action_order)
assert "Color.clear" not in badge
assert "if let text, !text.isEmpty" in badge
assert 'NSEvent.addLocalMonitorForEvents(matching: .keyDown)' in management
assert 'HotkeyChord.capture(event)' in management

required_shortcut_labels = {
    "hades2.shortcut.generateFlora",
    "hades2.shortcut.generateMining",
    "hades2.shortcut.generateDigging",
    "hades2.shortcut.generateShades",
    "hades2.shortcut.generateFishing",
    "hades2.shortcut.acquireChaosPair",
    "hades2.shortcut.acquireExactBoon",
    "hades2.shortcut.openPurgingPool",
    "hades2.shortcut.applyNextOccurrence",
    "hades2.shortcut.disableAll",
}
presentation_section = types[types.index("var presentationKey: String"):types.index("\n    }\n}", types.index("var presentationKey: String"))]
presentation_cases = dict(re.findall(r'case \.([A-Za-z]\w*): return "([^"]+)"', presentation_section))
assert set(presentation_cases) == set(action_order), "every shortcut action needs exactly one presentation label"

for language in ("en", "zh-CN"):
    entries = json.loads(read(f"Sources/Hades2/Presentation/Localization/hades2.{language}.json"))["entries"]
    assert required_shortcut_labels <= entries.keys(), f"{language} shortcut labels are incomplete"
    assert entries["hades2.shortcut.disableAll"] == ("Disable All" if language == "en" else "关闭全部修改器")
    for action, key in presentation_cases.items():
        assert key.startswith("hades2."), f"{action} bypasses the Hades presentation catalogue: {key}"
        assert key in entries, f"{language} lacks shortcut label for {action}: {key}"
    assert "hades2.op.acquireSelectedReward" in entries
    assert "hades2.op.acquireChaosPair" in entries

# Elements have distinct symbols and colors rather than sharing the atom icon.
for line in (
    'case "Fire": return ("flame.fill", .orange)',
    'case "Water": return ("drop.fill", .blue)',
    'case "Earth": return ("mountain.2.fill", .brown)',
    'case "Air": return ("wind", .cyan)',
    'case "Aether": return ("sparkles", .purple)',
):
    assert line in view

print('hades2_feature_contracts_ok')
