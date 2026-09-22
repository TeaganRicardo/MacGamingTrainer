from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return (ROOT / path).read_text(encoding='utf-8')

view = read('Sources/Hades2/Hades2View.swift')
types = read('Sources/Hades2/Hades2Types.swift')
management = read('Sources/Hades2/Views/Hades2ManagementViews.swift')
badge = read('Sources/Core/UI/Primitives/TrainerBadge.swift')
lua = read('Backend/games/hades2/runtime/hades.lua')

# Dynamic spawn/resource lists render a bilingual item label whenever English is
# available, and the static next-room choices use the same Chinese · English form.
assert '"\\(option.name) · \\(option.englishName)"' in view
assert '"\\(resource.name) · \\(resource.englishName)"' in view
for label in (
    '金币 · Gold Crowns',
    '半人马之心 · Centaur Heart',
    '灵魂之水 · Soul Tonic',
    '力量石榴 · Pom of Power',
    '狄德勒斯之锤 · Daedalus Hammer',
    '月之礼赠 · Gift of the Moon',
):
    assert label in view

# Selene has two distinct native reward paths. SpellDrop chooses a Hex; TalentDrop
# is the official Path of Stars consumable used to add points to the current Hex.
assert '{ id = "TalentDrop", name = "繁星之路", category = "特殊祝福", kind = "consumable", group = "special", family = "Selene"' in lua
assert 'sourceId = "Selene", sourceName = "塞勒涅"' in lua
spawn = lua[lua.index('if command == "spawn_reward" then'):lua.index('requireFunctions("loot spawning"', lua.index('if command == "spawn_reward" then'))]
assert spawn.index('if entry.kind == "consumable" then') < spawn.index('if rewardId == "SpellDrop" then')
assert 'CreateConsumableItem(objectId, rewardId, 0' in spawn
assert 'if rewardId == "TalentDrop"' not in spawn

# Shortcut defaults follow the visible action order: 1...9, then A...J. All
# static toggle/apply/spawn actions are represented, and nil slots do not reserve
# a phantom column.
order = types[types.index('static let uiOrder'):types.index('static let legacyDigitActions')]
for token in (
    '.godMode', '.infiniteHealth', '.infiniteMana', '.instantCastCooldown',
    '.hexAlwaysReady', '.infiniteAmmo', '.damageEnabled', '.autoMiniGames',
    '.gardenQoL', '.boonRarityEnabled', '.forceLegendary', '.forceDuo',
    '.moneyMultiplierEnabled', '.resourceMultiplierEnabled',
    '.spawnOlympian', '.spawnPickup', '.spawnSpecial', '.applyNextRoomReward',
    '.disableAll',
):
    assert token in order
assert order.index('.spawnOlympian') < order.index('.applyNextRoomReward')
assert 'Color.clear' not in badge
assert 'if let text, !text.isEmpty' in badge
assert 'NSEvent.addLocalMonitorForEvents(matching: .keyDown)' in management
assert 'HotkeyChord.capture(event)' in management

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
