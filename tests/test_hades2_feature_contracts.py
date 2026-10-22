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
navigation = read('Sources/Hades2/Services/Hades2WorkbenchNavigation.swift')
management = read('Sources/Hades2/Views/Hades2ManagementViews.swift')
schema = read('Backend/games/hades2/schema.py')
feature_generator = read('Tools/generate_hades2_feature_bindings.py')
feature_bindings = read('Sources/Hades2/Generated/Hades2Feature.generated.swift')
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

# The selected common list owns the first ten defaults. Numeric controls may
# appear above it, and speed owns its explicit minus/plus chords. Every current
# action must still have exactly one visible affordance in its owning section.
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
assert "Hades2WorkbenchCatalog.orderedShortcutActions.filter" in store
assert "defaultShortcutIndex" not in types + store
assert "profileShortcutWarning" in model + management
assert "hades2.error.profileShortcutLayoutUnsupported" in model + management
assert "clearProfileShortcutWarning()" in model + management
assert '.onDisappear { model.clearProfileShortcutWarning() }' in management
assert 'Text(localization.string(warning))' in management
shortcut_settings = management[management.index("struct Hades2ShortcutSettingsView"):management.index("struct Hades2ManagementUtilities")]
assert "ScrollView {" in shortcut_settings
assert ".frame(maxHeight: 560)" in shortcut_settings
assert "ShortcutAction.allCases" in model
assert "Hades2WorkbenchCatalog.orderedShortcutActions" in management
assert 'title: "hades2.op.acquireSelectedReward"' in model
assert 'title: "hades2.op.acquireChaosPair"' in model
assert "family.shortcutAction" in gathering
assert "generateShortcutText: model.shortcutText(family.shortcutAction)" in gathering
assert "TrainerShortcutBadgeSlot(text: generateShortcutText)" in occurrence

common = source_section(view, "private var commonSection: some View {", "private var boonsSection: some View {")
if "Hades2WorkbenchCatalog.shortcutActions(in: .common)" in common:
    assert "action.commonFeatureIcon" in common
    common_order = action_order[:10]
else:
    common_order = shortcut_references(common)
assert common_order == [
    "invincibility", "infiniteHealth", "infiniteMana", "infiniteMoney", "infiniteRerolls",
    "forceEnableRerolls", "instantCastCooldown", "hexAlwaysReady", "infiniteAmmo", "autoMiniGames",
]
assert action_order[:10] == common_order
parts = [
    common,
    source_section(view, "private var gameSpeedPanel: some View {", "private var presentedContent:"),
    source_section(view, "private var damageMetric: some View {", "private var boonRarityPanel:"),
    source_section(view, "private var boonRarityPanel: some View {", "private var nextRoomRewardPanel:"),
    source_section(view, "private var currentRunEffectsPanel: some View {", "private func exactItemLabel("),
    source_section(view, "private var boonAcquisitionPanel: some View {", "private var currentRunEffectsPanel:"),
    source_section(view, "private var resourcePanel: some View {", "private var rewardSpawningPanel:"),
    source_section(view, "private var resourceSection: some View {", "private var roomsSection:"),
    source_section(view, "private var nextRoomRewardPanel: some View {", "private var resourcePanel:"),
    source_section(view, "private var rewardSpawningPanel: some View {", "private var boonAcquisitionPanel:"),
    source_section(view, "private var management: some View {", "private func featureRow("),
]
visible_actions = [action for part in parts for action in shortcut_references(part)]
if "Hades2WorkbenchCatalog.shortcutActions(in: .common)" in common:
    visible_actions.extend(common_order)
visible_actions.extend("generate" + family[:1].upper() + family[1:] for family in family_order)
assert sorted(visible_actions) == sorted(action_order), (visible_actions, action_order)
root = source_section(view, "private var rootContent: some View {", "@ViewBuilder\n    private var statusAndSessionSection")
assert all(section in root for section in ("statusAndSessionSection", "commonSection", "boonsSection", "resourceSection", "roomsSection", "management"))
assert "gardenQoL" not in view
damage = source_section(view, "private var damageMetric: some View {", "private var boonRarityPanel:")
assert "TrainerToggleControl" not in damage
assert ".damageEnabled" not in damage
assert "TrainerShortcutBadgeSlot" not in damage
assert 'placeholder: "1"' in damage
assert "'damageMultiplier': {'default':1.0" in schema
assert "case .damageMultiplier: return 1.0" in feature_bindings
assert 'feature = "damageEnabled"' in feature_generator
assert "value = value ~= 1" in feature_generator
assert 'if feature == "damageEnabled" then value = M.damageMultiplier ~= 1 end' in lua
assert "M.damageMultiplier = 1" in lua[lua.index("local function disable()"):lua.index("local function anyDesired()")]
assert "revision = 119" in lua
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
}
presentation_section = types[types.index("var presentationKey: String"):types.index("\n    }\n}", types.index("var presentationKey: String"))]
presentation_cases = dict(re.findall(r'case \.([A-Za-z]\w*): return "([^"]+)"', presentation_section))
assert set(presentation_cases) == set(action_order), "every shortcut action needs exactly one presentation label"

for language in ("en", "zh-CN"):
    entries = json.loads(read(f"Sources/Hades2/Presentation/Localization/hades2.{language}.json"))["entries"]
    assert required_shortcut_labels <= entries.keys(), f"{language} shortcut labels are incomplete"
    for action, key in presentation_cases.items():
        if action == "disableAll":
            assert key == "host.disableAll"
            host_strings = read(f"Resources/Localization/{language}.lproj/Host.strings")
            assert f'"host.disableAll" =' in host_strings
            continue
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


resource_controls = read('Sources/Core/UI/Components/TrainerResourceControls.swift')
occurrence_setting = read('Sources/Hades2/Views/Hades2OccurrenceSetting.swift')
gathering_panel = read('Sources/Hades2/Views/Hades2GatheringPanel.swift')
chaos_gate_panel = read('Sources/Hades2/Views/Hades2ChaosGatePanel.swift')
host_actions = read('Sources/Hades2/Views/Hades2HostActions.swift')
assert "inline: true" in view
assert "if inline" in resource_controls
assert "actionAvailable ? theme.accent : theme.inactive" in resource_controls
assert "tint: hasOverride ? theme.accent : theme.inactive" in occurrence_setting
assert 'TrainerSection(title: text("hades2.section.elements")' not in view
assert 'TrainerSection(title: text("hades2.gathering.title")' not in gathering_panel
assert 'TrainerSection(title: text("hades2.chaosGate.title")' not in chaos_gate_panel
assert "specialSearch" not in view
assert "resultsPresented" in host_actions
assert ".popover(isPresented: $resultsPresented, arrowEdge: .bottom)" in host_actions


gathering_action_key = "hades2.gathering.generateHelp"
zh_localization = read('Sources/Hades2/Presentation/Localization/hades2.zh-CN.json')
en_localization = read('Sources/Hades2/Presentation/Localization/hades2.en.json')
assert f'"{gathering_action_key}": "生成"' in zh_localization
assert f'"{gathering_action_key}": "Generate"' in en_localization
