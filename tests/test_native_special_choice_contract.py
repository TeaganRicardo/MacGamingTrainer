from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / 'Sources/Hades2/Hades2API.swift').read_text()
types = (ROOT / 'Sources/Hades2/Hades2Types.swift').read_text()
state = (ROOT / 'Sources/Hades2/Hades2BackendState.swift').read_text()
model = (ROOT / 'Sources/Hades2/Hades2Model.swift').read_text()
view = (ROOT / 'Sources/Hades2/Hades2View.swift').read_text()
router = (ROOT / 'Backend/games/hades2/command_router.py').read_text()
adapter = (ROOT / 'Backend/games/hades2/adapter.py').read_text()
lua = (ROOT / 'Backend/games/hades2/runtime/hades.lua').read_text()

for token in ('openSpecialChoice = "open_special_choice"', 'case openSpecialChoice(source: String)', 'case .openSpecialChoice: return .openSpecialChoice'):
    assert token in api, token
assert 'return ["source": source]' in api

assert "'open_special_choice'" in router
assert "command=='open_special_choice'" in router or "command == 'open_special_choice'" in router
assert "params.get('source')" in router
replay = adapter[adapter.index('def _replay_preferences'):adapter.index('def scan(', adapter.index('def _replay_preferences'))]
assert 'open_special_choice' not in replay

assert 'let sourceId: String' in types
assert 'let nativeChoice: Bool' in types
assert 'sourceId: row["sourceId"] as? String ?? ""' in state
assert 'nativeChoice: row["nativeChoice"] as? Bool ?? false' in state

assert 'func openSpecialChoice' in model
assert '.openSpecialChoice(source:' in model
assert 'nativeChoice' in model
assert '原生三选一' in view
assert '直接添加' in view

definitions = lua[lua.index('local nativeSpecialChoiceDefinitions'):lua.index('local nativeSpecialChoiceSources')]
for source in (
    'Artemis', 'Athena', 'Dionysus', 'Hades',
    'Arachne', 'Narcissus', 'Echo', 'Medea', 'Circe', 'Icarus',
):
    assert source in definitions, source
for source in ('Heracles', 'Moros'):
    assert source not in definitions, source
for source in ('Artemis', 'Athena', 'Dionysus', 'Hades'):
    assert source + ' = { npc = ' in definitions and 'mode = "loot"' in definitions
for source in ('Arachne', 'Narcissus', 'Echo', 'Medea', 'Circe', 'Icarus'):
    assert source + ' = { npc = ' in definitions and 'choices = ' in definitions

block = lua[lua.index('if command == "open_special_choice" then'):lua.index('if command == "spawn_reward" then')]
assert 'local definition = nativeSpecialChoiceDefinitions[params.source]' in block
assert 'allowedNativeSources' not in block, "native choice capability must have one source of truth"
assert 'OpenUpgradeChoiceMenu' in block
assert 'thread(runChoice)' in block, "native menu must run on a game thread, never hold the LLDB boundary for player input"
assert 'SpawnObstacle({' not in block, "native choice must not create an in-world anchor"
assert 'Destroy({' not in block and 'pcall(Destroy' not in block, "native choice must not own a synthetic engine object"
assert 'RoomRequiredObjects' not in block, "native choice must not mutate room object ownership"
assert 'source.ObjectId = -1' in block, "native selection cleanup needs only a non-nil sentinel ObjectId"
assert 'SetupCostume' in block, "Arachne choice must preserve costume application"
assert 'DoubleFamiliarTrait' in block and 'SessionMapState.OldFamiliarTrait' in block, "Circe choice must preserve native familiar preprocessing"
assert 'CurrentRun.LastReward' in block, "Echo choice must preserve last-reward semantics"
assert 'IsGameStateEligible' in block
assert 'UpgradeOptions' in block
assert 'AddTraitToHero' not in block
assert 'hadLootChoiceHistory' in block
assert 'CurrentRun.LootChoiceHistory = nil' in block

spawn = lua[lua.index('if command == "spawn_reward" then'):]
assert 'entry.kind == "trait"' in spawn
assert 'AddTraitToHero' in spawn

# Catalog advertises the capability instead of making Swift infer it from localized names.
assert 'nativeChoice = nativeSpecialChoiceSources[source.id] == true' in lua

print('native_special_choice_contract_ok')
