-- Offline profile of the shipped resident with explicit, inexpensive native
-- stubs. No game/save data is loaded. Native presentations, engine callbacks,
-- optional reroll families are not represented. Trait rows/catalogs are
-- synthetic ordinary God boons; counts select an explicit inventory scale.
local runtimePath = assert(arg[1])
local samples = assert(tonumber(arg[2]))
local traitCount = assert(tonumber(arg[3] or "0"))
local catalogTraitCount = assert(tonumber(arg[4] or "0"))
assert(_VERSION == "Lua 5.2", "profiling requires the supported Lua 5.2 ABI")

SessionState = {}; SessionMapState = {}
GameState = { Resources = { MetaCurrency = 100, Money = 100 },
  LifetimeResourcesGained = {}, RunHistory = {}, LootPickups = {} }
ResourceData = { MetaCurrency = {}, Money = {} }
ResourceDisplayOrderData = { "MetaCurrency" }
ScreenData = { InventoryScreen = { ItemCategories = {} } }
TraitElementData = {}; EnemyData = {}; PresetEventArgs = {}
MapState = { RoomRequiredObjects = {}, EquippedWeapons = {} }
LootObjects = {}; ConsumableData = {}; RewardStoreData = {}
TraitData = {}; LootData = {}; UnitSetData = {}
CodexOrdering = { OlympianGods = {}, Order = {} }
CurrentRun = {
  Hero = { ObjectId = 1, Health = 100, MaxHealth = 100, Mana = 50, MaxMana = 50,
    HealthBuffer = 0, Elements = {}, Traits = {}, TraitDictionary = {},
    BoonData = {}, Ammo = {} },
  CurrentRoom = {}, NumRerolls = 10, SpellCharge = 0,
  PickedTraits = {}, BannedTraits = {}, ResourcesGained = {}, ResourcesSpent = {},
}
ActiveScreens = {}; ScreenState = {}; ScreenAnchors = {}
local noop = function() end
UpdateTimers = noop; Damage = noop; SacrificeHealth = noop; ManaDelta = noop
UpdateHealthUI = noop; UpdateWeaponMana = noop; UpdateManaMeterUI = noop
UpdateRerollUI = noop; UpdateMoneyUI = noop
CalculateDamageMultipliers = function() return 1 end
GetHeroMaxAvailableMana = function() return CurrentRun.Hero.MaxMana end
AddResource = function(id, amount)
  GameState.Resources[id] = (GameState.Resources[id] or 0) + amount
end
SpendResource = function(id, amount)
  GameState.Resources[id] = (GameState.Resources[id] or 0) - amount
end
HeroHasTrait = function() return false end
OpenUpgradeChoiceMenu = noop; CreateBoonLootButtons = noop
AttemptPanelReroll = noop; RerollBoonLoot = noop; DestroyBoonLootButtons = noop

local upgradeQueries = 0
if traitCount > 0 or catalogTraitCount > 0 then
  local pool = {}
  LootData.ZeusUpgrade = { GodLoot = true, Traits = pool }
  for index = 1, math.max(traitCount, catalogTraitCount) do
    local name = string.format("ProfileBoon%04d", index)
    TraitData[name] = { RarityLevels = { Common = 1, Rare = 1.5, Epic = 2, Heroic = 2.5 } }
    if index <= catalogTraitCount then pool[index] = name end
    if index <= traitCount then
      local trait = { Name = name, Id = index, StackNum = 2, Rarity = "Common", SourceId = "ZeusUpgrade" }
      CurrentRun.Hero.Traits[index] = trait
      CurrentRun.Hero.TraitDictionary[name] = { trait }
    end
  end
  IsGodTrait = function(name) return TraitData[name] ~= nil end
  GetAllUpgradeableGodTraits = function()
    upgradeQueries = upgradeQueries + 1
    local eligible = {}
    for _, trait in ipairs(CurrentRun.Hero.Traits) do eligible[trait.Name] = true end
    return eligible
  end
  IncreaseTraitLevel = noop; AddRarityToTraits = noop
  GetTraitTooltipTitle = function(trait) return trait.Name end
end

local function verifyInventory(state)
  assert(#state.currentRunTraits == traitCount, "mounted inventory count did not match the workload")
  for index, row in ipairs(state.currentRunTraits) do
    assert(row.instanceId == tostring(index) and row.sameNameCount == 1
      and row.family == "olympianHermes" and row.levelCapability == "increaseOne",
      "mounted inventory identity/eligibility was not observed")
  end
end

local function emit(name, duration)
  print(name .. "\t" .. string.format("%.9f", duration))
end
local function measure(name, work, iterations)
  iterations = iterations or 1
  for _ = 1, 3 do work() end
  for _ = 1, samples do
    local started = os.clock()
    for _ = 1, iterations do work() end
    emit(name, (os.clock() - started) / iterations)
  end
end
local started = os.clock()
dofile(runtimePath)
local M = assert(__MacGamingTrainerV1)
emit("resident_load", os.clock() - started)
started = os.clock()
local first = M.dispatch("status", { includeCatalogs = true })
assert(first.boons and first.rewards, "cold status omitted catalogs")
M.json(first)
emit("cold_catalog_status_json", os.clock() - started)
verifyInventory(first)
local exactCount = 0
for _, row in ipairs(first.rewards) do
  if row.acquisitionMode == "ordinaryNative" then exactCount = exactCount + 1 end
end
assert(exactCount == catalogTraitCount, "exact catalog count did not match the workload")
measure("warm_catalog_status_json", function()
  M.json(M.dispatch("status", { includeCatalogs = true }))
end)

local observation
measure("status_dispatch", function()
  observation = M.dispatch("status", { includeCatalogs = false })
  assert(observation.boons == nil and observation.rewards == nil)
end)
verifyInventory(observation)
measure("status_json", function() M.json(observation) end)
measure("status_dispatch_json", function()
  M.json(M.dispatch("status", { includeCatalogs = false }))
end)
measure("frame_without_desired", function() UpdateTimers(1 / 60) end, 100)

local enabled = { "infiniteHealth", "infiniteMana", "damageEnabled",
  "moneyMultiplierEnabled", "resourceMultiplierEnabled", "forceEnableRerolls" }
local calls = {
  { command = "set_feature", params = { feature = "damageMultiplier", value = 3 } },
  { command = "set_feature", params = { feature = "moneyMultiplier", value = 3 } },
  { command = "set_feature", params = { feature = "resourceMultiplier", value = 3 } },
  { command = "lock_resource", params = { resource = "MetaCurrency", locked = true } },
  { command = "lock_rerolls", params = { locked = true } },
  { command = "lock_vital", params = { vital = "health", locked = true } },
}
for _, feature in ipairs(enabled) do
  calls[#calls + 1] = { command = "set_feature", params = { feature = feature, value = true } }
end
local function verify(state)
  verifyInventory(state)
  assert(state.healthLocked and state.rerollsLocked, "requested locks did not mount")
  assert(next(state.featureErrors) == nil, "fixture feature installation failed")
  for _, feature in ipairs(enabled) do
    assert(state.activeFeatures[feature], feature .. " is not active in the measured fixture")
  end
  M.json(state)
end
verify(M.dispatchBatch(calls))
print("features\t" .. M.json(M.dispatch("status", { includeCatalogs = false }).activeFeatures))
measure("frame_with_desired", function() UpdateTimers(1 / 60) end, 100)
verify(M.dispatch("status", { includeCatalogs = false }))
measure("active_status_dispatch_json", function()
  M.json(M.dispatch("status", { includeCatalogs = false }))
end)

-- Existing durable features are torn down before every timed replay. The
-- cleanup itself is outside the sample; batch installs and observation are in it.
for _ = 1, samples do
  M.dispatch("cleanup", { includeCatalogs = false })
  local started = os.clock()
  local result = M.dispatchBatch(calls)
  local encoded = M.json(result)
  emit("preference_replay_json", os.clock() - started)
  assert(#encoded > 0)
  verify(result)
end

M.dispatch("cleanup", { includeCatalogs = false })
-- Each edit is a distinct one-shot intent. Its returned observation and the
-- underlying resource must agree; measurement never repeats an unknown action.
for index = 1, samples do
  local amount = 100 + index
  local started = os.clock()
  local result = M.dispatch("set_resource", {
    resource = "MetaCurrency", amount = amount,
    requestId = "profile-resource-" .. index, includeCatalogs = false,
  })
  M.json(result)
  emit("resource_edit_json", os.clock() - started)
  assert(GameState.Resources.MetaCurrency == amount, "resource edit did not converge")
  local observed
  for _, resource in ipairs(result.resources) do
    if resource.id == "MetaCurrency" then observed = resource.count end
  end
  assert(observed == amount, "resource observation did not match the completed edit")
  assert(result.lastAction.requestId == "profile-resource-" .. index
    and result.lastAction.outcome == "completed" and not result.lastAction.duplicate,
    "resource edit lost its one-shot receipt")
end

local beforeQueries = upgradeQueries
local final = M.dispatch("status", { includeCatalogs = false })
verifyInventory(final)
print("fixture\t" .. M.json({ mounted_traits = traitCount, catalog_traits = catalogTraitCount,
  native_upgrade_queries_per_status = upgradeQueries - beforeQueries }))
