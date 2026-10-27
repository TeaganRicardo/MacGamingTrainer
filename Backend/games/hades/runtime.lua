local existing = rawget(_G, "MacGamingTrainerHades")
if existing then
  if existing.revision ~= 4 then error("hades.error.restartRequired") end
  return existing
end

local trainerFlag = "MacGamingTrainer.Hades"
local defaults = {
  invincibility = false, moneyNoDecrease = false, rerollsNoDecrease = false,
  fullGodGauge = false, fullHealth = false, infiniteAmmo = false, forceRerolls = false,
  boonRarityEnabled = false, damageMultiplier = 1, incomingDamageMultiplier = 1, moveSpeedMultiplier = 1,
  attackSpeedMultiplier = 1, dashBonus = 0,
}
local resourceNames = {
  "MetaPoints", "Gems", "SuperGems", "LockKeys", "SuperLockKeys", "GiftPoints", "SuperGiftPoints",
}
-- Shipped LootData.lua: only normal Olympian and Hermes offer pools.
-- TrialUpgrade/Chaos, Hammer, Pom and forced-Common rooms use other native rules.
local rarityLootNames = {
  ZeusUpgrade = true, PoseidonUpgrade = true, AthenaUpgrade = true, AresUpgrade = true,
  AphroditeUpgrade = true, ArtemisUpgrade = true, DionysusUpgrade = true,
  DemeterUpgrade = true, HermesUpgrade = true,
}
local runtime = {
  version = 1, revision = 4,
  features = {}, hooks = {}, instanceIds = setmetatable({}, { __mode = "k" }),
  nextInstanceId = 0, propertyDepth = 0, rerollLeases = setmetatable({}, { __mode = "k" }),
  movementOwners = setmetatable({}, { __mode = "k" }),
  rerollDoors = setmetatable({}, { __mode = "k" }),
}
runtime.generationId = tostring(runtime)
for name, value in pairs(defaults) do runtime.features[name] = value end
local arrayType = {}
local mainThread = {}
local function array() return setmetatable({}, arrayType) end
local function finite(value)
  return type(value) == "number" and value == value and value ~= math.huge and value ~= -math.huge
end
local function hero()
  local value = type(CurrentRun) == "table" and CurrentRun.Hero or nil
  if type(value) == "table" and type(value.ObjectId) == "number" then return value end
end
local function requireHero()
  local value = hero()
  assert(value, "hades.error.heroNotReady")
  return value
end
local function sameOwner(run, unit)
  return CurrentRun == run and hero() == unit
end
local function instanceId(trait)
  if not runtime.instanceIds[trait] then
    runtime.nextInstanceId = runtime.nextInstanceId + 1
    runtime.instanceIds[trait] = tostring(runtime.nextInstanceId)
  end
  return runtime.instanceIds[trait]
end
local function traitGroups(unit)
  local groups, names = {}, {}
  for _, trait in pairs(unit.Traits or {}) do
    local group
    for _, candidate in ipairs(groups) do
      if candidate.name == trait.Name and AreTraitsIdentical(candidate.trait, trait) then
        group = candidate
        break
      end
    end
    if not group then
      group = { name = trait.Name, trait = trait, members = {} }
      groups[#groups + 1] = group
      names[trait.Name] = (names[trait.Name] or 0) + 1
    end
    group.members[#group.members + 1] = trait
    if trait.Rarity then
      if group.rarity and group.rarity ~= trait.Rarity then group.mixedRarity = true end
      group.rarity = group.rarity or trait.Rarity
      if not group.trait.Rarity then group.trait = trait end
    end
  end
  for _, group in ipairs(groups) do
    local ids = {}
    for _, trait in ipairs(group.members) do ids[#ids + 1] = instanceId(trait) end
    table.sort(ids)
    group.instanceId = "trait:" .. group.name .. ":" .. table.concat(ids, ",")
    group.rarity = group.rarity or "Common"
    local source = type(TraitData) == "table" and TraitData[group.name]
    group.canEdit, group.canRemove = true, true
    if group.mixedRarity or (names[group.name] > 1 and source and
        (source.Slot or group.trait.AddIncomingDamageModifiers or group.trait.AddOutgoingDamageModifiers
          or group.trait.AddOutgoingLifestealModifiers or group.trait.WeaponDataOverride)) then
      group.limitation = "duplicateName"
      group.canEdit, group.canRemove = false, false
    elseif not source then
      group.limitation = "unknownTrait"
      group.canEdit, group.canRemove = false, false
    elseif source.Slot == "Keepsake" or source.Slot == "Assist" then
      group.canEdit = true
    elseif group.trait.OnExpire or group.trait.SetupFunction or group.trait.IsWeaponEnchantment then
      group.limitation = "specialLifecycle"
      group.canEdit = false
    end
    group.useField = finite(group.trait.RemainingUses) and "RemainingUses" or "Uses"
    group.remainingUses = group.trait[group.useField]
    group.canExpire = group.trait.OnExpire ~= nil or (finite(group.trait.RemainingUses) and not group.trait.AddAssist)
    group.canSetUses = finite(group.remainingUses) and #group.members == 1
    group.cooldownLimit = group.trait.RoomCooldown or group.trait.TimeCooldown
    group.canRefresh = finite(group.trait.CurrentCooldown) and finite(group.cooldownLimit) and #group.members == 1
    if group.limitation == "duplicateName" or group.limitation == "unknownTrait" then
      group.canExpire, group.canSetUses, group.canRefresh = false, false, false
    end

  end
  return groups
end
local function damageModifier(unit)
  local modifiers = unit.OutgoingDamageModifiers or {}
  for _, modifier in pairs(modifiers) do
    if modifier.Name == trainerFlag then return modifier end
  end
end
local function removeDamageModifier(unit)
  local modifiers = unit.OutgoingDamageModifiers or {}
  for index, modifier in pairs(modifiers) do
    if modifier.Name == trainerFlag then modifiers[index] = nil; return end
  end
end
local function mountIncomingDamage(unit)
  local found
  for index, modifier in pairs(unit.IncomingDamageModifiers or {}) do
    if modifier.Name == trainerFlag then
      found = modifier
      if runtime.features.incomingDamageMultiplier == 1 then
        unit.IncomingDamageModifiers[index] = nil
      else modifier.GlobalMultiplier = runtime.features.incomingDamageMultiplier end
      break
    end
  end
  if not found and runtime.features.incomingDamageMultiplier ~= 1 then
    AddIncomingDamageModifier(unit, { Name = trainerFlag,
      GlobalMultiplier = runtime.features.incomingDamageMultiplier, Multiplicative = true })
  end
end
local function refillAmmo(unit)
  if not runtime.features.infiniteAmmo or unit.IsDead then return end
  for _, name in ipairs({ "RangedWeapon", "GunWeapon" }) do
    if unit.Weapons and unit.Weapons[name] then
      RunWeaponMethod({ Id = unit.ObjectId, Weapon = name, Method = "RefillAmmo" })
    end
  end
end
local suspendProperties
local function nativeChange(unit, change)
  assert(type(ApplyUnitPropertyChanges) == "function", "hades.error.unsupportedRuntime")
  ApplyUnitPropertyChanges(unit, { change }, false)
end
local function attackChanges(factor)
  assert(type(TraitData) == "table" and type(TraitData.HermesWeaponTrait) == "table",
    "hades.error.unsupportedRuntime")
  local changes = {}
  for _, source in ipairs(TraitData.HermesWeaponTrait.PropertyChanges or {}) do
    if source.ChangeType == "Multiply" then
      local change = {}
      for key, value in pairs(source) do change[key] = value end
      change.ChangeValue = factor
      changes[#changes + 1] = change
    end
  end
  return changes
end
local function applyAttack(unit, factor)
  if factor == 1 then return end
  assert(type(ApplyUnitPropertyChanges) == "function", "hades.error.unsupportedRuntime")
  ApplyUnitPropertyChanges(unit, attackChanges(factor), false)
end
local function fillGauge(unit)
  if runtime.features.fullGodGauge and not runtime.fillingGauge and not unit.IsDead and not unit.SuperActive
      and type(IsSuperValid) == "function" and IsSuperValid()
      and finite(unit.SuperMeterLimit) and type(BuildSuperMeter) == "function" then
    runtime.fillingGauge = true
    BuildSuperMeter(CurrentRun, math.max(0, unit.SuperMeterLimit - (unit.SuperMeter or 0)))
    runtime.fillingGauge = false
  end
end
local function mount(unit, rebuilt)
  local mounted = runtime.mounted
  if rebuilt or not mounted or mounted.unit ~= unit or mounted.objectId ~= unit.ObjectId then
    mounted = { unit = unit, objectId = unit.ObjectId, move = 1, attack = 1, dash = 0 }
    runtime.mounted = mounted
  end
  local desired = runtime.features
  if desired.invincibility then
    assert(type(unit.InvulnerableFlags) == "table" and type(CurrentRun.InvulnerableFlags) == "table"
      and type(SetPlayerInvulnerable) == "function", "hades.error.unsupportedRuntime")
    if not unit.InvulnerableFlags[trainerFlag] then SetPlayerInvulnerable(trainerFlag) end
  elseif type(unit.InvulnerableFlags) == "table" and unit.InvulnerableFlags[trainerFlag] then
    assert(type(SetPlayerVulnerable) == "function", "hades.error.unsupportedRuntime")
    SetPlayerVulnerable(trainerFlag)
  end
  mountIncomingDamage(unit)
  refillAmmo(unit)
  if desired.fullHealth and not unit.IsDead then unit.Health = unit.MaxHealth; UpdateHealthUI() end
  local damage = damageModifier(unit)
  if desired.damageMultiplier == 1 then
    if damage then removeDamageModifier(unit) end
  elseif damage then
    damage.GlobalMultiplier = desired.damageMultiplier
  else
    assert(type(AddOutgoingDamageModifier) == "function", "hades.error.unsupportedRuntime")
    AddOutgoingDamageModifier(unit, { Name = trainerFlag, GlobalMultiplier = desired.damageMultiplier, Multiplicative = true })
  end
  local movement = runtime.movementOwners[unit]
  local scriptedMovement = movement and movement.run == CurrentRun and movement.objectId == unit.ObjectId
  scriptedMovement = scriptedMovement or (CurrentRun.BlockTimerFlags and CurrentRun.BlockTimerFlags.MoveHeroToRoomPosition)
  if not scriptedMovement and mounted.move ~= desired.moveSpeedMultiplier then
    nativeChange(unit, { UnitProperty = "Speed", ChangeValue = desired.moveSpeedMultiplier / mounted.move, ChangeType = "Multiply" })
    mounted.move = desired.moveSpeedMultiplier
  end
  if mounted.attack ~= desired.attackSpeedMultiplier then
    applyAttack(unit, mounted.attack / desired.attackSpeedMultiplier)
    mounted.attack = desired.attackSpeedMultiplier
  end
  if mounted.dash ~= desired.dashBonus then
    assert(type(WeaponSets) == "table" and type(WeaponSets.HeroRushWeapons) == "table", "hades.error.unsupportedRuntime")
    nativeChange(unit, { WeaponNames = WeaponSets.HeroRushWeapons, WeaponProperty = "ClipSize",
      ChangeValue = desired.dashBonus - mounted.dash, ChangeType = "Add" })
    mounted.dash = desired.dashBonus
  end
  fillGauge(unit)
end
suspendProperties = function(unit)
  local mounted = runtime.mounted
  if not mounted or mounted.unit ~= unit or mounted.objectId ~= unit.ObjectId then return end
  if mounted.move ~= 1 then
    nativeChange(unit, { UnitProperty = "Speed", ChangeValue = 1 / mounted.move, ChangeType = "Multiply" })
    mounted.move = 1
  end
  if mounted.attack ~= 1 then
    applyAttack(unit, mounted.attack)
    mounted.attack = 1
  end
  if mounted.dash ~= 0 then
    nativeChange(unit, { WeaponNames = WeaponSets.HeroRushWeapons, WeaponProperty = "ClipSize",
      ChangeValue = -mounted.dash, ChangeType = "Add" })
    mounted.dash = 0
  end
end
local function beginMovement(unit)
  local owner = runtime.movementOwners[unit]
  if not owner or owner.run ~= CurrentRun or owner.objectId ~= unit.ObjectId then
    local mounted = runtime.mounted
    if mounted and mounted.unit == unit and mounted.objectId == unit.ObjectId and mounted.move ~= 1 then
      nativeChange(unit, { UnitProperty = "Speed", ChangeValue = 1 / mounted.move, ChangeType = "Multiply" })
      mounted.move = 1
    end
    owner = { run = CurrentRun, unit = unit, objectId = unit.ObjectId, depth = 0 }
    runtime.movementOwners[unit] = owner
  end
  owner.depth = owner.depth + 1
  return owner
end
local function finishMovement(owner)
  if runtime.movementOwners[owner.unit] ~= owner then return end
  owner.depth = owner.depth - 1
  if owner.depth == 0 then
    runtime.movementOwners[owner.unit] = nil
    if sameOwner(owner.run, owner.unit) and owner.unit.ObjectId == owner.objectId then
      mount(owner.unit, false)
    end
  end
end
local nativeMovementFunctions = {}
local adoptedMovement = setmetatable({}, { __mode = "k" })
local movementAdoptionPending = false
local function movementFrame(thread, original)
  local level = 1
  while true do
    local info = debug.getinfo(thread, level, "f")
    if not info then return end
    if info.func == original then return level end
    level = level + 1
  end
end
local function adoptScheduledMovement()
  local unit = hero()
  if not movementAdoptionPending or not unit then return end
  movementAdoptionPending = false
  local seen = {}
  local function adopt(thread)
    if seen[thread] then return end
    seen[thread] = true
    for original, name in pairs(nativeMovementFunctions) do
      local level = movementFrame(thread, original)
      if level and not movementFrame(thread, runtime.hooks[name]) then
        -- Bedroom's native body always addresses CurrentRun.Hero; the other
        -- owners retain their run or object id in the suspended Lua frame.
        local matches = name == "BedroomIntermissionApproach"
        local index = 1
        while not matches do
          local key, value = debug.getlocal(thread, level, index)
          if not key then break end
          matches = ((name == "MoveHeroToRoomPosition" or name == "DropHeroToRoomPosition")
              and key == "heroId" and value == unit.ObjectId)
            or (key == "currentRun" and value == CurrentRun)
          index = index + 1
        end
        if matches then
          local owner = beginMovement(unit)
          if name == "RoomEntranceE_Intro" or name == "RoomEntranceSurface" then owner.held = true end
          adoptedMovement[thread] = { original = original, name = name, owner = owner }
          return
        end
      end
    end
  end
  -- Main.lua registers timed waits with .thread and event waits with .Thread.
  for _, queue in ipairs({ _threads or {}, _workingThreads or {} }) do
    for _, record in pairs(queue) do adopt(record.thread) end
  end
  for _, listeners in pairs(_eventListeners or {}) do
    for _, record in pairs(listeners) do adopt(record.Thread) end
  end
end
local function hook(name, wrap)
  local current = rawget(_G, name)
  if type(current) == "function" and not runtime.hooks[name] then
    local replacement = wrap(current)
    runtime.hooks[name] = replacement
    _G[name] = replacement
  end
end
local function restoreRerollDoors()
  for door, lease in pairs(runtime.rerollDoors) do
    if CurrentRun == lease.run and CurrentRun.CurrentRoom == lease.room and door.Room == lease.targetRoom and door.CanBeRerolled
        and not runtime.nativeMetaSelected("RerollMetaUpgrade") then
      door.CanBeRerolled = lease.native
      RefreshUseButton(door.ObjectId, door)
    end
    runtime.rerollDoors[door] = nil
  end
end
local function installHooks()
  if type(SaveIgnores) == "table" then SaveIgnores.MacGamingTrainerHades = true end
  hook("Save", function(original)
    return function(...)
      SaveIgnores.MacGamingTrainerHades = true
      local removed = {}
      local function removeField(owner, key)
        if owner and owner[key] ~= nil then
          removed[#removed + 1] = { owner = owner, key = key, value = owner[key] }
          owner[key] = nil
        end
      end
      local function strip(run)
        if type(run) ~= "table" then return end
        removeField(run.InvulnerableFlags, trainerFlag)
        local unit = run.Hero
        if type(unit) ~= "table" then return end
        removeField(unit.InvulnerableFlags, trainerFlag)
        for _, key in ipairs({ "OutgoingDamageModifiers", "IncomingDamageModifiers" }) do
          for index, modifier in pairs(unit[key] or {}) do
            if modifier.Name == trainerFlag then removeField(unit[key], index) end
          end
        end
      end
      strip(CurrentRun)
      for door, lease in pairs(runtime.rerollDoors) do
        if CurrentRun == lease.run and CurrentRun.CurrentRoom == lease.room and door.Room == lease.targetRoom then
          removeField(door, "CanBeRerolled")
          door.CanBeRerolled = lease.native
        end
      end
      for _, run in pairs(type(GameState) == "table" and GameState.RunHistory or {}) do strip(run) end
      -- Main.lua Save is synchronous; restore projections even when luabins.save raises.
      local result = table.pack(pcall(original, ...))
      for _, field in ipairs(removed) do field.owner[field.key] = field.value end
      if not result[1] then error(result[2], 0) end
      return table.unpack(result, 2, result.n)
    end
  end)
  hook("SetupHeroObject", function(original)
    return function(...)
      local unit = hero()
      if unit then runtime.movementOwners[unit] = nil end
      runtime.propertyDepth = runtime.propertyDepth + 1
      local result = table.pack(original(...))
      runtime.propertyDepth = runtime.propertyDepth - 1
      unit = hero()
      if unit then mount(unit, true) end
      return table.unpack(result, 1, result.n)
    end
  end)
  hook("RemoveTimerBlock", function(original)
    return function(run, flag, ...)
      local unit = hero()
      local result = table.pack(original(run, flag, ...))
      if flag == "MoveHeroToRoomPosition" and unit and sameOwner(run, unit) then mount(unit, false) end
      return table.unpack(result, 1, result.n)
    end
  end)
  hook("resume", function(original)
    return function(thread, ...)
      local result = table.pack(original(thread, ...))
      local adopted = adoptedMovement[thread]
      if adopted and not movementFrame(thread, adopted.original) then
        adoptedMovement[thread] = nil
        local owner = adopted.owner
        if adopted.name == "RoomEntranceSurface" then
          if not owner.resetPending then owner.held = nil; finishMovement(owner) end
        elseif adopted.name ~= "RoomEntranceE_Intro" then
          finishMovement(owner)
        end
      end
      return table.unpack(result, 1, result.n)
    end
  end)
  for _, name in ipairs({ "DropHeroToRoomPosition", "MoveHeroToRoomPosition", "RoomEntranceHades",
      "StartDeathLoopPresentation", "BedroomIntermissionApproach" }) do
    hook(name, function(original)
      nativeMovementFunctions[original] = name
      movementAdoptionPending = true
      return function(...)
        local unit = hero()
        local first = ...
        if name == "DropHeroToRoomPosition" and unit and first ~= unit.ObjectId then unit = nil end
        if (name == "RoomEntranceHades" or name == "StartDeathLoopPresentation")
            and first ~= CurrentRun then unit = nil end
        local owner = unit and beginMovement(unit)
        local result = table.pack(original(...))
        if owner then finishMovement(owner) end
        return table.unpack(result, 1, result.n)
      end
    end)
  end
  -- Scripted walks can outlive their entry function until a native reset or
  -- SetupHeroObject. Surface's post-meeting branch has no deferred reset.
  for _, name in ipairs({ "RoomEntranceE_Intro", "RoomEntranceSurface", "ExitToHadesPresentation",
      "GardenScenePan", "SetupPlayerUnitInFlashback" }) do
    hook(name, function(original)
      if name == "RoomEntranceE_Intro" or name == "RoomEntranceSurface" then
        nativeMovementFunctions[original] = name
        movementAdoptionPending = true
      end
      return function(...)
        local unit = hero()
        local first = ...
        if (name == "RoomEntranceE_Intro" or name == "RoomEntranceSurface" or name == "ExitToHadesPresentation")
            and first ~= CurrentRun then unit = nil end
        local owner, acquired
        if unit then
          owner = runtime.movementOwners[unit]
          if not owner or owner.run ~= CurrentRun or owner.objectId ~= unit.ObjectId or not owner.held then
            owner = beginMovement(unit)
            owner.held = true
            acquired = true
          end
        end
        local result = table.pack(original(...))
        if name == "RoomEntranceSurface" and acquired and not owner.resetPending then
          owner.held = nil
          finishMovement(owner)
        end
        return table.unpack(result, 1, result.n)
      end
    end)
  end
  for _, name in ipairs({ "ResetPlayerMoveData", "RestorePlayerUnitAfterFlashback" }) do
    hook(name, function(original)
      if name == "ResetPlayerMoveData" then
        nativeMovementFunctions[original] = name
        movementAdoptionPending = true
      end
      return function(...)
        local unit = hero()
        local first = ...
        if name == "ResetPlayerMoveData" and first ~= CurrentRun then unit = nil end
        local owner = unit and runtime.movementOwners[unit]
        if owner and (owner.run ~= CurrentRun or owner.objectId ~= unit.ObjectId) then owner = nil end
        if owner and name == "ResetPlayerMoveData" then owner.resetPending = true end
        local result = table.pack(original(...))
        if owner and name == "ResetPlayerMoveData" then owner.resetPending = nil end
        if owner and owner.held then owner.held = nil; finishMovement(owner) end
        return table.unpack(result, 1, result.n)
      end
    end)
  end
  for _, name in ipairs({ "AddTraitToHero", "RemoveWeaponTrait", "EquipPlayerWeapon" }) do
    hook(name, function(original)
      return function(...)
        local run, unit = CurrentRun, hero()
        if runtime.propertyDepth == 0 and unit then suspendProperties(unit) end
        runtime.propertyDepth = runtime.propertyDepth + 1
        local result = table.pack(original(...))
        runtime.propertyDepth = runtime.propertyDepth - 1
        if runtime.propertyDepth == 0 and unit and sameOwner(run, unit) then mount(unit, false) end
        return table.unpack(result, 1, result.n)
      end
    end)
  end
  hook("Damage", function(original)
    return function(victim, args, ...)
      local unit = hero()
      if runtime.features.fullHealth and unit and victim == unit and not unit.IsDead then
        -- Combat.lua clamps to MinHealth before checking Death Defiance/death.
        -- Only this hero's damage call receives the temporary life floor.
        local parameters = {}
        for key, value in pairs(args) do parameters[key] = value end
        parameters.MinHealth = unit.MaxHealth
        return original(victim, parameters, ...)
      end
      return original(victim, args, ...)
    end
  end)
  for _, name in ipairs({ "UpdateAmmoUI", "UpdateGunUI" }) do
    hook(name, function(original)
      return function(args, ...)
        local unit = hero()
        if unit and runtime.features.infiniteAmmo then
          refillAmmo(unit)
          local observed = {}
          for key, value in pairs(args or {}) do observed[key] = value end
          observed.Ammo = nil
          return original(observed, ...)
        end
        return original(args, ...)
      end
    end)
  end
  hook("IsMetaUpgradeSelected", function(original)
    runtime.nativeMetaSelected = original
    return function(name, ...)
      if runtime.features.forceRerolls and hero()
          and (name == "RerollPanelMetaUpgrade" or name == "RerollMetaUpgrade") then
        local caller = debug.getinfo(2, "f").func
        -- Query-local permission: Mirror selection, ranks and saved state are
        -- untouched, and native blocked/cost/door eligibility remains in force.
        if caller == CreateBoonLootButtons or caller == CreateStoreButtons
            or caller == CreateSellButtons or caller == runtime.nativeAssignRoom
            or caller == SpawnStoreItemInWorld then return true end
      end
      return original(name, ...)
    end
  end)
  hook("AssignRoomToExitDoor", function(original)
    runtime.nativeAssignRoom = original
    return function(door, room, ...)
      local lease = runtime.rerollDoors[door]
      if lease then
        if lease.run == CurrentRun and lease.room == CurrentRun.CurrentRoom and lease.targetRoom == room then
          door.CanBeRerolled = lease.native
        end
        runtime.rerollDoors[door] = nil
      end
      local native = door.CanBeRerolled
      local result = table.pack(original(door, room, ...))
      if runtime.features.forceRerolls and door.CanBeRerolled and not native
          and not runtime.nativeMetaSelected("RerollMetaUpgrade") then
        runtime.rerollDoors[door] = { run = CurrentRun, room = CurrentRun.CurrentRoom, targetRoom = room, native = native }
      end
      return table.unpack(result, 1, result.n)
    end
  end)
  hook("SetTraitsOnLoot", function(original)
    return function(loot, ...)
      if runtime.features.boonRarityEnabled and type(loot) == "table"
          and rarityLootNames[loot.Name] and not loot.ForceCommon
          and type(loot.RarityChances) == "table" then
        -- Native TraitScripts.lua selects a Legendary only when eligible; the
        -- Heroic roll uses the Epic-capable trait pool. Keep the Legendary
        -- chance and source/slot legality, while preferring Heroic (or Rare
        -- for a Rare-only trait). Original odds are never changed in-place.
        local odds = loot.RarityChances
        local boosted = {}
        for key, value in pairs(odds) do boosted[key] = value end
        boosted.Heroic, boosted.Epic, boosted.Rare = 1, 1, 1
        loot.RarityChances = boosted
        -- The native selection path is synchronous; restore the exact native
        -- odds on both success and a rejected/failed native offer generation.
        local result = table.pack(pcall(original, loot, ...))
        loot.RarityChances = odds
        if not result[1] then error(result[2], 0) end
        return table.unpack(result, 2, result.n)
      end
      return original(loot, ...)
    end
  end)
  hook("SpendMoney", function(original)
    return function(amount, ...)
      local run, unit = CurrentRun, hero()
      local protect = runtime.features.moneyNoDecrease and unit and finite(amount) and amount > 0
      local result = table.pack(original(amount, ...))
      if protect and sameOwner(run, unit) then
        run.Money = run.Money + amount
        UpdateMoneyUI(run.Money)
      end
      return table.unpack(result, 1, result.n)
    end
  end)
  local function rerollHook(name, getRun, getCost)
    hook(name, function(original)
      return function(...)
        local args = table.pack(...)
        if not runtime.features.forceRerolls
            and (name == "AttemptBoonLootReroll" or name == "AttemptPanelReroll")
            and not runtime.nativeMetaSelected("RerollPanelMetaUpgrade") then return end
        local run, unit = getRun(args), hero()
        local key = coroutine.running() or mainThread
        local previous = runtime.rerollLeases[key]
        local cost = getCost(args)
        if runtime.features.rerollsNoDecrease and run and unit and finite(cost) and cost > 0 then
          runtime.rerollLeases[key] = { run = run, unit = unit, before = run.NumRerolls or 0, cost = cost }
        end
        local result = table.pack(original(table.unpack(args, 1, args.n)))
        runtime.rerollLeases[key] = previous
        return table.unpack(result, 1, result.n)
      end
    end)
  end
  rerollHook("AttemptBoonLootReroll", function() return CurrentRun end, function() return 1 end)
  rerollHook("AttemptPanelReroll", function() return CurrentRun end, function(args) return args[2] and args[2].Cost end)
  rerollHook("AttemptReroll", function(args) return args[1] end, function() return 1 end)
  hook("UpdateRerollUI", function(original)
    return function(value, ...)
      local lease = runtime.rerollLeases[coroutine.running() or mainThread]
      if lease and not lease.restored and sameOwner(lease.run, lease.unit)
          and lease.run.NumRerolls == lease.before - lease.cost then
        lease.run.NumRerolls = lease.run.NumRerolls + lease.cost
        value = lease.run.NumRerolls
        lease.restored = true
      end
      return original(value, ...)
    end
  end)
  hook("BuildSuperMeter", function(original)
    return function(run, amount, ...)
      local unit = hero()
      if runtime.features.fullGodGauge and unit and run == CurrentRun and not unit.SuperActive
          and finite(unit.SuperMeterLimit) then amount = math.max(amount or 0, unit.SuperMeterLimit - (unit.SuperMeter or 0)) end
      return original(run, amount, ...)
    end
  end)
  hook("UpdateSuperMeterUI", function(original)
    return function(...)
      local unit = hero()
      if unit then fillGauge(unit) end
      return original(...)
    end
  end)
  hook("StopSuper", function(original)
    return function(...)
      local run, unit = CurrentRun, hero()
      local result = table.pack(original(...))
      if unit and sameOwner(run, unit) then fillGauge(unit) end
      return table.unpack(result, 1, result.n)
    end
  end)
  hook("PostEncounterDrainSuper", function(original)
    return function(...)
      if runtime.features.fullGodGauge then return end
      return original(...)
    end
  end)
  adoptScheduledMovement()
end

local world

function runtime.status()
  installHooks()
  world.install()
  local unit = hero()
  local ready = unit ~= nil
  local resources, traits, features, activeFeatures = {}, array(), {}, {}
  for name, value in pairs(runtime.features) do
    features[name] = value
    activeFeatures[name] = ready and not unit.IsDead and value ~= defaults[name]
  end
  activeFeatures.invincibility = activeFeatures.invincibility
    and type(unit.InvulnerableFlags) == "table" and unit.InvulnerableFlags[trainerFlag] == true or false
  activeFeatures.fullHealth = activeFeatures.fullHealth and unit.Health == unit.MaxHealth or false
  activeFeatures.infiniteAmmo = activeFeatures.infiniteAmmo and type(unit.Weapons) == "table"
    and (unit.Weapons.RangedWeapon or unit.Weapons.GunWeapon) and true or false
  activeFeatures.fullGodGauge = activeFeatures.fullGodGauge and not unit.SuperActive and type(IsSuperValid) == "function" and IsSuperValid() or false
  local mounted = ready and runtime.mounted
  for feature, property in pairs({ moveSpeedMultiplier = "move", attackSpeedMultiplier = "attack", dashBonus = "dash" }) do
    activeFeatures[feature] = activeFeatures[feature] and mounted and mounted.unit == unit
      and mounted.objectId == unit.ObjectId and mounted[property] == runtime.features[feature] or false
  end
  local movement = ready and runtime.movementOwners[unit]
  if movement or (ready and CurrentRun.BlockTimerFlags and CurrentRun.BlockTimerFlags.MoveHeroToRoomPosition) then
    activeFeatures.moveSpeedMultiplier = false
  end
  for _, name in ipairs(resourceNames) do
    resources[name] = type(GameState) == "table" and type(GameState.Resources) == "table" and tonumber(GameState.Resources[name]) or 0
  end
  if ready then
    for _, group in ipairs(traitGroups(unit)) do
      local limitation = group.limitation
      traits[#traits + 1] = {
        instanceId = group.instanceId, name = group.name, rarity = group.rarity,
        level = #group.members, canEdit = group.canEdit, canRemove = group.canRemove,
        remainingUses = group.remainingUses, canSetUses = group.canSetUses,
        canExpire = group.canExpire, canRefresh = group.canRefresh,
        cooldown = group.trait.CurrentCooldown, cooldownLimit = group.cooldownLimit,
        blessing = group.trait.LastBlessingName,
        curse = group.trait.LastCurseName, limitation = limitation or "",
      }
    end
  end
  return {
    heroReady = ready, heroId = ready and (runtime.generationId .. ":" .. instanceId(CurrentRun) .. ":" .. instanceId(unit) .. ":" .. tostring(unit.ObjectId)) or "",
    invincible = ready and type(unit.InvulnerableFlags) == "table" and unit.InvulnerableFlags[trainerFlag] == true or false,
    health = ready and tonumber(unit.Health) or 0, maxHealth = ready and tonumber(unit.MaxHealth) or 0,
    money = ready and tonumber(CurrentRun.Money) or 0, rerolls = ready and tonumber(CurrentRun.NumRerolls) or 0,
    godGauge = ready and tonumber(unit.SuperMeter) or 0, maxGodGauge = ready and tonumber(unit.SuperMeterLimit) or 0,
    features = features, activeFeatures = activeFeatures, resources = resources, traits = traits, world = world.observation(),
  }
end
local function validateFeature(name, value)
  assert(defaults[name] ~= nil, "hades.error.invalidValue")
  local default = defaults[name]
  if type(default) == "boolean" then
    assert(type(value) == "boolean", "hades.error.invalidValue")
  elseif name == "dashBonus" then
    assert(finite(value) and value == math.floor(value) and value >= 0 and value <= 20, "hades.error.invalidValue")
  else
    assert(finite(value) and value >= 0.1 and value <= 100, "hades.error.invalidValue")
  end
end
function runtime.configure(features)
  assert(type(features) == "table", "hades.error.invalidValue")
  for name, value in pairs(features) do validateFeature(name, value) end
  installHooks()
  for name, value in pairs(features) do runtime.features[name] = value end
  if not runtime.features.forceRerolls then restoreRerollDoors() end
  local unit = hero()
  if unit then mount(unit, false) end
  return runtime.status()
end
function runtime.set_feature(name, value)
  validateFeature(name, value)
  installHooks()
  runtime.features[name] = value
  if name == "forceRerolls" and not value then restoreRerollDoors() end
  local unit = hero()
  if unit then mount(unit, false) end
  return runtime.status()
end
function runtime.set_invincibility(enabled)
  requireHero()
  return runtime.set_feature("invincibility", enabled)
end
function runtime.disable_all()
  world.clearPending()
  for name, value in pairs(defaults) do runtime.features[name] = value end
  restoreRerollDoors()
  local unit = hero()
  if unit then mount(unit, false) end
  return runtime.status()
end
function runtime.set_value(field, value)
  local unit = requireHero()
  assert(finite(value) and value == math.floor(value) and value >= 0 and value <= 1000000000, "hades.error.invalidValue")
  if field == "health" then
    assert(value >= 1 and value <= unit.MaxHealth, "hades.error.invalidValue")
    unit.Health = value
    UpdateHealthUI()
  elseif field == "maxHealth" then
    assert(value >= 1, "hades.error.invalidValue")
    local multiplier = GetTotalHeroTraitValue("MaxHealthMultiplier", { IsMultiplier = true })
    assert(finite(multiplier) and multiplier > 0, "hades.error.unsupportedRuntime")
    local change = (value - unit.MaxHealth - GetMaxHealthUpgradeIncrement(0)) / multiplier
    if change ~= 0 then
      local trait = GetProcessedTraitData({ Unit = unit, TraitName = "RoomRewardEmptyMaxHealthTrait" })
      trait.PropertyChanges[1].ChangeValue = change
      -- ApplyUnitPropertyChange clamps health before its multiplier-aware
      -- validation. Keep that intermediate maximum positive on large decreases.
      unit.MaxHealth = math.max(unit.MaxHealth, value - change)
      AddTraitToHero({ TraitData = trait })
    else
      ValidateMaxHealth(true)
    end
    unit.Health = math.max(0, math.min(unit.Health, unit.MaxHealth))
    UpdateHealthUI()
  elseif field == "godGauge" then
    assert(not unit.SuperActive and finite(unit.SuperMeterLimit) and value <= unit.SuperMeterLimit,
      "hades.error.invalidValue")
    BuildSuperMeter(CurrentRun, value - (unit.SuperMeter or 0))
    UpdateSuperMeterUI()
  elseif field == "money" then
    CurrentRun.Money = value
    UpdateMoneyUI(value)
  elseif field == "rerolls" then
    CurrentRun.NumRerolls = value
    UpdateRerollUI(value)
  else error("hades.error.invalidValue") end
  return runtime.status()
end
function runtime.heal()
  local unit = requireHero()
  Heal(unit, { HealAmount = math.max(0, unit.MaxHealth - unit.Health), Silent = true,
    AttackerName = trainerFlag })
  UpdateHealthUI()
  return runtime.status()
end
function runtime.set_resource(name, value)
  requireHero()
  local known = false
  for _, resource in ipairs(resourceNames) do if name == resource then known = true end end
  assert(known and finite(value) and value == math.floor(value) and value >= 0 and value <= 1000000000,
    "hades.error.invalidValue")
  assert(type(GameState) == "table" and type(GameState.Resources) == "table", "hades.error.unsupportedRuntime")
  GameState.Resources[name] = value
  UpdateResourceUI(name, value)
  return runtime.status()
end
local function validateTrait(unit, name, rarity, level)
  assert(type(name) == "string" and type(TraitData) == "table" and type(TraitData[name]) == "table",
    "hades.error.invalidValue")
  local source = TraitData[name]
  assert(type(rarity) == "string" and ((source.RarityLevels and source.RarityLevels[rarity])
    or (not source.RarityLevels and rarity == "Common")), "hades.error.invalidValue")
  assert(finite(level) and level == math.floor(level) and level >= 1 and level <= 100, "hades.error.invalidValue")
  if source.RequiredWeapon then
    assert(unit.Weapons and unit.Weapons[source.RequiredWeapon], "hades.error.traitWeaponRequired")
  end
  if source.RequiredWeapons then
    local equipped = false
    for _, name in ipairs(source.RequiredWeapons) do if unit.Weapons and unit.Weapons[name] then equipped = true end end
    assert(equipped, "hades.error.traitWeaponRequired")
  end
  return source
end
local function addTraits(unit, name, rarity, level, preserved)
  local processed = GetProcessedTraitData({ Unit = unit, TraitName = name, Rarity = rarity })
  if preserved then
    for _, key in ipairs({ "AccumulatedFountainDamageBonus", "RemainingUses", "Uses", "CurrentCooldown", "LastCurseName", "LastBlessingName", "TraitTitle" }) do
      if preserved[key] ~= nil then processed[key] = preserved[key] end
    end
  end
  AddTraitToHero({ TraitData = processed })
  for _ = 2, level do AddTraitToHero({ TraitName = name }) end
end
local function equipOwnedTrait(unit, name, source, rarity, level)
  assert(level == 1, "hades.error.invalidValue")
  local assist = source.Slot == "Assist"
  local ownerKey = assist and "LastAssistTrait" or "LastAwardTrait"
  local equip = assist and EquipAssist or EquipKeepsake
  local unequip = assist and UnequipAssist or UnequipKeepsake
  assert(type(equip) == "function" and type(unequip) == "function", "hades.error.unsupportedRuntime")
  local previous
  for _, trait in pairs(unit.Traits or {}) do
    if trait.Slot == source.Slot then
      assert(not previous, "hades.error.unsupportedTrait")
      previous = trait
    end
  end
  local rank = GetRarityValue(rarity)
  local currentRank = GetKeepsakeLevel(name)
  local progressOwner, progressValue
  if source.KeepsakeRarityGameStateRequirements then
    local requirements = source.KeepsakeRarityGameStateRequirements[rank]
    local requirement = requirements and requirements.AssistUpgradeLevel
    if assist and requirement and requirement.Name == name then
      for key in pairs(requirements) do assert(key == "AssistUpgradeLevel", "hades.error.unsupportedTrait") end
      progressOwner, progressValue = GameState.AssistUnlocks, requirement.Level
    else
      assert(rank == currentRank, "hades.error.unsupportedTrait")
    end
  elseif rank ~= currentRank then
    assert(source.ChamberThresholds, "hades.error.unsupportedTrait")
    progressOwner, progressValue = GameState.KeepsakeChambers, 0
    for index = 1, rank - 1 do
      assert(finite(source.ChamberThresholds[index]), "hades.error.unsupportedTrait")
      progressValue = progressValue + source.ChamberThresholds[index]
    end
  end
  if previous and previous.Name == name and previous.Rarity == rarity
      and GameState[ownerKey] == name and rank == currentRank then return end
  suspendProperties(unit)
  runtime.propertyDepth = runtime.propertyDepth + 1
  if previous then unequip(unit, previous.Name) end
  if progressOwner then progressOwner[name] = progressValue end
  GameState[ownerKey] = name
  if assist then EquipReferencedWeapons(source) end
  equip(unit, name)
  if assist then
    for _, trait in pairs(unit.Traits or {}) do
      if trait.Name == name then AddAssistWeapons(unit, trait); break end
    end
  end
  runtime.propertyDepth = runtime.propertyDepth - 1
  mount(unit, false)
end
function runtime.add_trait(name, rarity, level)
  local unit = requireHero()
  local source = validateTrait(unit, name, rarity, level)
  if source.Slot == "Keepsake" or source.Slot == "Assist" then
    equipOwnedTrait(unit, name, source, rarity, level)
    return runtime.status()
  end
  if source.Slot then
    for _, trait in pairs(unit.Traits or {}) do
      assert(trait.Slot ~= source.Slot or trait.Name == name, "hades.error.traitSlotOccupied")
    end
  end
  suspendProperties(unit)
  addTraits(unit, name, rarity, level)
  mount(unit, false)
  return runtime.status()
end
local function selectedTrait(unit, id)
  for _, group in ipairs(traitGroups(unit)) do
    if group.instanceId == id then
      return group
    end
  end
  error("hades.error.staleTrait")
end
local function cancelGroup(unit, group, expire)
  if group.trait.Slot == "Keepsake" or group.trait.Slot == "Assist" then
    local assist = group.trait.Slot == "Assist"
    local owner = assist and "LastAssistTrait" or "LastAwardTrait"
    if assist then UnequipAssist(unit, group.name) else UnequipKeepsake(unit, group.name) end
    if GameState[owner] == group.name then GameState[owner] = nil end
  elseif #group.members == GetTraitNameCount(unit, group.name) and not group.trait.OnExpire
      and not group.trait.RemainingUses and not group.trait.LastCurseName then
    RemoveWeaponTrait(group.name)
  else
    for _, trait in ipairs(group.members) do
      if not expire then trait.OnExpire = nil end
      RemoveTraitData(unit, trait)
    end
  end
end
function runtime.remove_trait(id)
  local unit = requireHero()
  local group = selectedTrait(unit, id)
  assert(group.canRemove, "hades.error.unsupportedTrait")
  suspendProperties(unit)
  cancelGroup(unit, group, false)
  mount(unit, false)
  return runtime.status()
end
function runtime.update_trait(id, rarity, level)
  local unit = requireHero()
  local group = selectedTrait(unit, id)
  assert(group.canEdit, "hades.error.unsupportedTrait")
  local trait = group.trait
  local source = validateTrait(unit, trait.Name, rarity, level)
  if source.Slot == "Keepsake" or source.Slot == "Assist" then
    equipOwnedTrait(unit, trait.Name, source, rarity, level)
  else
    suspendProperties(unit)
    cancelGroup(unit, group, false)
    addTraits(unit, trait.Name, rarity, level, trait)
    mount(unit, false)
  end
  return runtime.status()
end
function runtime.set_trait_uses(id, uses)
  local unit = requireHero()
  local group = selectedTrait(unit, id)
  assert(group.canSetUses and finite(uses) and uses == math.floor(uses) and uses >= 0 and uses <= 1000,
    "hades.error.invalidValue")
  if uses == 0 and group.useField == "RemainingUses" and group.canExpire then return runtime.expire_trait(id) end
  group.trait[group.useField] = uses
  TraitUIUpdateText(group.trait)
  return runtime.status()
end
function runtime.refresh_trait(id)
  local unit = requireHero()
  local group = selectedTrait(unit, id)
  assert(group.canRefresh, "hades.error.unsupportedTrait")
  IncrementTraitCooldown(group.trait, group.cooldownLimit)
  TraitUIUpdateText(group.trait)
  return runtime.status()
end
function runtime.expire_trait(id)
  local unit = requireHero()
  local group = selectedTrait(unit, id)
  assert(group.canRemove and group.canExpire, "hades.error.unsupportedTrait")
  suspendProperties(unit)
  cancelGroup(unit, group, true)
  mount(unit, false)
  return runtime.status()
end
function runtime.add_chaos_pair(blessingName, curseName, rarity, encounters)
  local unit = requireHero()
  local function includes(values, name)
    for _, value in ipairs(values or {}) do if value == name then return true end end
    return false
  end
  local trial = type(LootData) == "table" and LootData.TrialUpgrade
  assert(trial and includes(trial.PermanentTraits, blessingName) and includes(trial.TemporaryTraits, curseName),
    "hades.error.invalidValue")
  validateTrait(unit, blessingName, rarity, 1)
  assert(finite(encounters) and encounters == math.floor(encounters) and encounters >= 1 and encounters <= 100,
    "hades.error.invalidValue")
  local blessing = GetProcessedTraitData({ Unit = unit, TraitName = blessingName, Rarity = rarity })
  local curse = GetProcessedTraitData({ Unit = unit, TraitName = curseName, Rarity = rarity })
  local title = "ChaosCombo_" .. curseName .. "_" .. blessingName
  blessing.LastCurseName, blessing.LastBlessingName = curseName, blessingName
  blessing.TraitTitle = "Blank"
  curse.OnExpire = { TraitData = blessing }
  curse.CurseName, curse.LastCurseName = curseName, curseName
  curse.BlessingName, curse.LastBlessingName = blessingName, blessingName
  curse.TraitTitle, curse.RemainingUses = title, encounters
  suspendProperties(unit)
  AddTraitToHero({ TraitData = curse })
  mount(unit, false)
  return runtime.status()
end
world = (function()
  local edits = setmetatable({}, { __mode = "k" })
  local encounters = setmetatable({}, { __mode = "k" })
  local spawnContext
  local objectOwners = {
    trove = { field = "ChallengeSwitch", chance = "ChallengeChanceSuccess", query = "IsChallengeSwitchEligible" },
    well = { field = "WellShop", chance = "WellShopChanceSuccess", query = "IsWellShopEligible" },
    purge = { field = "SellTraitShop", chance = "SellTraitShopChanceSuccess", query = "IsSellTraitShopEligible" },
  }
  local function roomId(room)
    return runtime.generationId .. ":" .. instanceId(CurrentRun) .. ":room:" .. instanceId(room)
  end
  local function currentRoom()
    local unit = hero()
    local room = unit and CurrentRun.CurrentRoom
    if type(room) == "table" and type(room.Name) == "string" and type(RoomSetData) == "table" then return room end
  end
  local function requireRoom(params)
    requireHero()
    local room = currentRoom()
    assert(room and roomId(room) == params.roomId, "hades.error.staleRoom")
    return room
  end
  local function doorId(door)
    local room = door.Room
    local overrides = type(room.RewardOverrides) == "table" and instanceId(room.RewardOverrides) or ""
    return instanceId(door) .. ":" .. instanceId(room) .. ":" .. tostring(room.ChosenRewardType)
      .. ":" .. tostring(room.ForceLootName) .. ":" .. overrides
  end
  local function ordinaryDoor(door)
    return door.Room and door.ReadyToUse and door.Name ~= "SecretDoor" and door.Name ~= "ShrinePointDoor"
  end
  local function requireDoor(params)
    requireRoom(params)
    for _, door in pairs(OfferedExitDoors or {}) do
      if ordinaryDoor(door) and doorId(door) == params.doorId then return door end
    end
    error("hades.error.staleDoor")
  end
  local function routeKind(name)
    if name:find("_Story", 1, true) then return "story" end
    if name:find("_Shop", 1, true) then return "shop" end
    if name:find("_Reprieve", 1, true) then return "reprieve" end
    if name:find("_MiniBoss", 1, true) then return "miniboss" end
    if name:find("_Combat", 1, true) then return "combat" end
  end
  local function routeRooms(room)
    local result = {}
    if room.NextRoomSet or room.NextRoomSetNoGenerate or room.UsePreviousRoomSet
        or room.LinkedRoom or room.LinkedRooms or room.LinkedRoomByPactLevel then return result end
    for name, data in pairs(RoomSetData[room.RoomSetName or "Tartarus"] or {}) do
      local kind = routeKind(name)
      if kind and IsRoomEligible(CurrentRun, room, data) then
        result[kind] = result[kind] or {}
        table.insert(result[kind], data)
      end
    end
    return result
  end
  local function thanatos(room)
    for _, name in ipairs(EncounterSets.ThanatosEncounters or {}) do
      local data = EncounterData[name]
      if data and IsEncounterEligible(CurrentRun, room, data) then return data end
    end
  end
  local function chanceEligible(room, key, callback)
    local previous = room[key]
    room[key] = true
    local ok, result = pcall(callback, CurrentRun, room)
    room[key] = previous
    if not ok then error(result, 0) end
    return result
  end
  local function canFish(room)
    return not room.CompletedFishing and not room.FishingPointId
      and #GetInactiveIdsByType({ Name = "FishingPoint" }) > 0
      and chanceEligible(room, "FishingPointChanceSuccess", IsFishingEligible)
  end
  local function canChaos(room)
    for _, door in pairs(OfferedExitDoors or {}) do
      if door.Name == "SecretDoor" then return false end
    end
    return #GetIdsByType({ Name = "SecretPoint" }) > 0
      and chanceEligible(room, "SecretChanceSuccess", IsSecretDoorEligible)
  end
  local function freePedestals(room, ids)
    local free = {}
    for _, id in ipairs(ids) do
      local used = false
      for _, owner in pairs(objectOwners) do
        if room[owner.field] and room[owner.field].ObjectId == id then used = true end
      end
      if not used then free[#free + 1] = id end
    end
    return free
  end
  local function canGenerate(room, kind)
    local owner = objectOwners[kind]
    if room[owner.field] then return false end
    local count = #freePedestals(room, GetIdsByType({ Name = "ChallengeSwitchBase" }))
    if count == 0 then return false end
    local callback = _G[owner.query]
    if kind == "trove" then
      return chanceEligible(room, owner.chance, function(run) return callback(run) end)
    end
    return chanceEligible(room, owner.chance, callback)
  end
  local function canModify(room)
    return not CurrentRun.CurrentRoom.DeferReward and not room.NoReward and not room.DeferReward and not room.ForcedReward
  end
  local function refreshDoor(door, room)
    local ids, seen = {}, {}
    local function include(id)
      if id and not seen[id] then ids[#ids + 1] = id; seen[id] = true end
    end
    include(door.DoorIconId); include(door.DoorIconFront); include(door.DoorIconBackingId)
    for _, id in pairs(door.AdditionalIcons or {}) do include(id) end
    for _, id in pairs(door.AdditionalAttractIds or {}) do include(id) end
    if #ids > 0 then Destroy({ Ids = ids }) end
    door.AdditionalIcons = {}; door.AdditionalAttractIds = {}
    door.CanBeRerolled = false
    AssignRoomToExitDoor(door, room)
    CreateDoorRewardPreview(door)
  end
  local function applyDoor(door, room)
    local edit = edits[door]
    if not edit or edit.applied ~= door.Room or edit.signature ~= doorId(door) then edit = { original = door.Room } end
    encounters[door.Room] = nil
    edit.applied = room; edits[door] = edit
    refreshDoor(door, room)
    edit.signature = doorId(door)
  end
  local function definition(name)
    local data = runtime.worldDefinitions and runtime.worldDefinitions[name]
    assert(data, "hades.error.invalidValue")
    return data
  end
  local function rewardSourceEligible(data)
    return data.kind ~= "loot" or IsGameStateEligible(CurrentRun, LootData[data.id])
  end
  local function doorReward(room, data)
    if not rewardSourceEligible(data) then return end
    for name, store in pairs(RewardStoreData) do
      for _, reward in ipairs(store) do
        if type(reward) == "table" and reward.Name == data.rewardType
            and IsRoomRewardEligible(CurrentRun, room, reward, nil, {}) then return reward, name end
      end
    end
  end
  local api = {}
  function api.install()
    for _, name in ipairs({ "IsSecretDoorEligible", "IsShrinePointDoorEligible", "IsChallengeSwitchEligible",
        "IsWellShopEligible", "IsSellTraitShopEligible", "IsFishingEligible" }) do
      local queryName = name
      hook(name, function(original)
        return function(...)
          if spawnContext and queryName ~= spawnContext.query then return false end
          if spawnContext and queryName == "IsChallengeSwitchEligible" then
            local run = ...
            return original(run)
          end
          return original(...)
        end
      end)
    end
    hook("GetIdsByType", function(original)
      return function(args, ...)
        local ids = original(args, ...)
        if spawnContext and args.Name == "ChallengeSwitchBase" then
          return freePedestals(spawnContext.room, ids)
        end
        return ids
      end
    end)
    hook("ChooseEncounter", function(original)
      return function(run, room, ...)
        local intent = encounters[room]
        encounters[room] = nil
        if intent and run == intent.run and hero() == intent.hero and run.CurrentRoom == intent.sourceRoom
            and IsEncounterEligible(run, room, EncounterData[intent.name]) then
          return SetupEncounter(EncounterData[intent.name], room)
        end
        return original(run, room, ...)
      end
    end)
  end
  function api.clearPending() encounters = setmetatable({}, { __mode = "k" }) end
  function api.observation()
    local room = currentRoom()
    if not room then return nil end
    for target, intent in pairs(encounters) do
      if intent.run ~= CurrentRun or intent.hero ~= hero() or intent.sourceRoom ~= room then encounters[target] = nil end
    end
    local routes, doors = routeRooms(room), array()
    for _, door in pairs(OfferedExitDoors or {}) do
      if ordinaryDoor(door) then
        local options = array()
        if canModify(door.Room) then
          for _, kind in ipairs({ "combat", "story", "shop", "reprieve", "miniboss" }) do
            if routes[kind] then options[#options + 1] = kind end
          end
          if thanatos(door.Room) then options[#options + 1] = "thanatos" end
        end
        local edit, encounter = edits[door], encounters[door.Room]
        doors[#doors + 1] = { id = doorId(door), number = door.ObjectId,
          reward = door.Room.ForceLootName or door.Room.ChosenRewardType or "",
          canReward = canModify(door.Room),
          routes = options, canRestore = edit ~= nil and edit.applied == door.Room and edit.signature == doorId(door),
          pendingEncounter = encounter ~= nil }
      end
    end
    table.sort(doors, function(a, b) return a.number < b.number end)
    local objects = array()
    if type(HandleSecretSpawns) == "function" then
      for _, kind in ipairs({ "trove", "well", "purge" }) do
        if canGenerate(room, kind) then objects[#objects + 1] = kind end
      end
    end
    return { roomId = roomId(room), doors = doors, canFish = canFish(room), canChaos = canChaos(room), objects = objects }
  end
  function runtime.gain_resource(params)
    requireHero()
    assert(finite(params.amount) and params.amount >= 1 and params.amount <= 1000000
      and params.amount == math.floor(params.amount), "hades.error.invalidValue")
    if params.resource == "Money" then
      AddMoney(params.amount, trainerFlag)
    else
      local allowed = false
      for _, name in ipairs(resourceNames) do if name == params.resource then allowed = true end end
      assert(allowed, "hades.error.invalidValue")
      AddResource(params.resource, params.amount, trainerFlag)
    end
    return runtime.status()
  end
  function runtime.spawn_reward(params)
    requireRoom(params)
    local data = definition(params.reward)
    assert(rewardSourceEligible(data), "hades.error.worldUnavailable")
    local unit = requireHero()
    if data.kind == "loot" then
      if params.reward == "WeaponUpgrade" then
        CreateWeaponLoot({ SpawnPoint = unit.ObjectId, OffsetX = 100 })
      elseif params.reward == "StackUpgrade" then
        CreateStackLoot({ SpawnPoint = unit.ObjectId, OffsetX = 100 })
      else
        GiveLoot({ ForceLootName = params.reward, SpawnPoint = unit.ObjectId, OffsetX = 100 })
      end
    else
      assert(ConsumableData[params.reward], "hades.error.worldUnavailable")
      local id = SpawnObstacle({ Name = params.reward, DestinationId = unit.ObjectId, Group = "Standing", OffsetX = 100 })
      local reward = CreateConsumableItem(id, params.reward, 0)
      ApplyConsumableItemResourceMultiplier(CurrentRun.CurrentRoom, reward)
      ExtractValues(unit, reward, reward)
      ActivatedObjects[id] = reward
    end
    return runtime.status()
  end
  function runtime.generate_fishing(params)
    local room = requireRoom(params)
    assert(canFish(room), "hades.error.worldUnavailable")
    local points = GetInactiveIdsByType({ Name = "FishingPoint" })
    room.ForceFishing = true
    UseHeroTraitsWithValue("ForceFishingPoint", true)
    room.FishingPointId = GetRandomValue(points)
    Activate({ Id = room.FishingPointId })
    CurrentRun.LastFishingPointDepth = GetRunDepth(CurrentRun)
    if CheckRoomExitsReady(room) then thread(FishingPointAvailablePresentation, room) end
    return runtime.status()
  end
  function runtime.generate_chaos_gate(params)
    local room = requireRoom(params)
    assert(canChaos(room), "hades.error.worldUnavailable")
    local data = ChooseNextRoomData(CurrentRun, { RoomDataSet = RoomSetData.Secrets })
    assert(data, "hades.error.worldUnavailable")
    local point = GetRandomValue(GetIdsByType({ Name = "SecretPoint" }))
    local door = DeepCopyTable(ObstacleData.SecretDoor)
    door.ObjectId = SpawnObstacle({ Name = "SecretDoor", Group = "FX_Terrain", DestinationId = point, AttachedTable = door })
    SetupObstacle(door)
    door.HealthCost = GetSecretDoorCost()
    local target = CreateRoom(data)
    AssignRoomToExitDoor(door, target)
    door.OnUsedPresentationFunctionName = "SecretDoorUsedPresentation"
    room.ForceSecretDoor = true
    UseHeroTraitsWithValue("ForceSecretDoor", true)
    CurrentRun.LastSecretDepth = GetRunDepth(CurrentRun)
    if CheckRoomExitsReady(room) then
      CreateDoorRewardPreview(door)
      thread(ExitDoorUnlockedPresentation, door)
      door.ReadyToUse = true
    end
    return runtime.status()
  end
  function runtime.generate_chamber_object(params)
    local room = requireRoom(params)
    local owner = objectOwners[params.object]
    assert(owner and canGenerate(room, params.object), "hades.error.worldUnavailable")
    local previous = room[owner.chance]
    room[owner.chance] = true
    spawnContext = { room = room, query = owner.query }
    local ok, result = pcall(HandleSecretSpawns, CurrentRun)
    spawnContext = nil
    room[owner.chance] = previous
    if not ok then error(result, 0) end
    local object = room[owner.field]
    assert(object, "hades.error.unsupportedRuntime")
    if CheckRoomExitsReady(room) then
      object.ReadyToUse = true
      object.UseText = object.ChallengeAvailableUseText or object.AvailableUseText
      RefreshUseButton(object.ObjectId, object)
      local animation = object.UnlockedAnimationName
        or (params.object == "well" and "WellShopUnlocked" or "SellTraitShopUnlocked")
      SetAnimation({ Name = animation, DestinationId = object.ObjectId })
    end
    return runtime.status()
  end
  function runtime.set_door_reward(params)
    local door = requireDoor(params)
    local data = definition(params.reward)
    assert(data.doorAllowed and canModify(door.Room), "hades.error.worldUnavailable")
    local reward, store = doorReward(door.Room, data)
    assert(reward, "hades.error.worldUnavailable")
    local room = DeepCopyTable(door.Room)
    local encounter = encounters[door.Room]
    room.ChosenRewardType = data.rewardType
    room.ForceLootName = data.rewardType == "Boon" and params.reward or nil
    room.RewardStoreName = store
    room.RewardOverrides = reward.Overrides and DeepCopyTable(reward.Overrides) or nil
    room.Encounter = nil
    room.OriginalChosenRewardType = nil; room.OriginalForceLootName = nil
    SetupRoomReward(CurrentRun, room, nil, { IgnoreForceLootName = true })
    encounters[room] = encounter
    applyDoor(door, room)
    return runtime.status()
  end
  function runtime.set_door_route(params)
    local door = requireDoor(params)
    assert(canModify(door.Room), "hades.error.worldUnavailable")
    if params.route == "thanatos" then
      local data = thanatos(door.Room)
      assert(data, "hades.error.worldUnavailable")
      local room = DeepCopyTable(door.Room)
      room.Encounter = nil
      encounters[room] = { run = CurrentRun, hero = hero(), sourceRoom = CurrentRun.CurrentRoom, name = data.Name }
      applyDoor(door, room)
    else
      local candidates = routeRooms(CurrentRun.CurrentRoom)[params.route]
      assert(candidates and #candidates > 0, "hades.error.worldUnavailable")
      local room = CreateRoom(GetRandomValue(candidates), { SkipChooseEncounter = true })
      applyDoor(door, room)
    end
    return runtime.status()
  end
  function runtime.restore_door(params)
    local door = requireDoor(params)
    local edit = edits[door]
    assert(edit and edit.applied == door.Room and edit.signature == doorId(door), "hades.error.staleDoor")
    encounters[door.Room] = nil
    refreshDoor(door, edit.original)
    edits[door] = nil
    return runtime.status()
  end
  return api
end)()

local function escape(value)
  return '"' .. value:gsub('[%z\1-\31\\"]', function(character)
    if character == '"' then return '\\"' end
    if character == '\\' then return '\\\\' end
    return string.format('\\u%04x', string.byte(character))
  end) .. '"'
end
function runtime.json(value)
  local kind = type(value)
  if kind == "string" then return escape(value) end
  if kind == "boolean" then return tostring(value) end
  if kind == "number" then return finite(value) and string.format("%.17g", value) or "null" end
  if kind == "nil" then return "null" end
  assert(kind == "table", "hades.error.unsupportedRuntime")
  local values = {}
  if getmetatable(value) == arrayType then
    for _, item in ipairs(value) do values[#values + 1] = runtime.json(item) end
    return "[" .. table.concat(values, ",") .. "]"
  end
  for key, item in pairs(value) do values[#values + 1] = escape(tostring(key)) .. ":" .. runtime.json(item) end
  table.sort(values)
  return "{" .. table.concat(values, ",") .. "}"
end
_G.MacGamingTrainerHades = runtime
installHooks()
return runtime
