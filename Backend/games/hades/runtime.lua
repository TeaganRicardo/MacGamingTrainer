local residentRevision = "__MGT_RESIDENT_SOURCE_SHA256__"
local existing = rawget(_G, "MacGamingTrainerHades")
if existing then
  if existing.revision ~= residentRevision then error("hades.error.restartRequired") end
  return existing
end

local trainerFlag = "MacGamingTrainer.Hades"
local defaults = {
  invincibility = false, moneyNoDecrease = false, rerollsNoDecrease = false,
  fullGodGauge = false, fullHealth = false, infiniteAmmo = false, forceRerolls = false,
  boonRarityEnabled = false, moneyMultiplierEnabled = false, resourceMultiplierEnabled = false,
  damageMultiplier = 1, incomingDamageMultiplier = 1, moveSpeedMultiplier = 1,
  attackSpeedMultiplier = 1, dashBonus = 0, moneyMultiplier = 2, resourceMultiplier = 2,
}
local resourceNames = {
  "MetaPoints", "Gems", "SuperGems", "LockKeys", "SuperLockKeys", "GiftPoints", "SuperGiftPoints",
}
local function knownResource(name)
  if type(name) ~= "string" then return false end
  for _, resource in ipairs(resourceNames) do
    if resource == name then return true end
  end
  return false
end
-- Shipped LootData.lua: only normal Olympian and Hermes offer pools.
-- TrialUpgrade/Chaos, Hammer, Pom and forced-Common rooms use other native rules.
local rarityLootNames = {
  ZeusUpgrade = true, PoseidonUpgrade = true, AthenaUpgrade = true, AresUpgrade = true,
  AphroditeUpgrade = true, ArtemisUpgrade = true, DionysusUpgrade = true,
  DemeterUpgrade = true, HermesUpgrade = true,
}
local runtime = {
  version = 1, revision = residentRevision,
  features = {}, hooks = {}, instanceIds = setmetatable({}, { __mode = "k" }),
  nextInstanceId = 0, propertyDepth = 0, rerollLeases = setmetatable({}, { __mode = "k" }),
  movementOwners = setmetatable({}, { __mode = "k" }),
  rerollDoors = setmetatable({}, { __mode = "k" }),
  boonRarityTarget = "Heroic",
  boonForceLegendary = false, boonForceDuo = false,
  fishingChance = nil, chaosGateChance = nil,
  resourceLocks = {},
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
local function enforceResource(name)
  local target = runtime.resourceLocks and runtime.resourceLocks[name]
  if not finite(target) or type(GameState) ~= "table" or type(GameState.Resources) ~= "table" then return end
  GameState.Resources[name] = target
  if type(UpdateResourceUI) == "function" then UpdateResourceUI(name, target) end
end
local function healthLockValid(lock)
  return type(lock) == "table" and finite(lock.current) and finite(lock.max)
    and lock.current >= 1 and lock.max >= 1 and lock.current <= lock.max
end
local function enforceHealthLock(unit)
  local lock = runtime.healthLock
  if not unit or not healthLockValid(lock) then return end
  unit.MaxHealth = lock.max
  unit.Health = math.min(lock.current, lock.max)
end
local function releaseHealthLock(unit)
  runtime.healthLock = nil
  if not unit then return end
  assert(type(ValidateMaxHealth) == "function" and type(UpdateHealthUI) == "function",
    "hades.error.outcomeUnknown")
  ValidateMaxHealth(true)
  unit.Health = math.max(1, math.min(unit.Health, unit.MaxHealth))
  UpdateHealthUI()
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
local function damageModifier(unit, field)
  local modifiers = unit[field] or {}
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
  assert(type(ApplyUnitPropertyChanges) == "function", "hades.error.outcomeUnknown")
  ApplyUnitPropertyChanges(unit, { change }, false)
end
local function attackChanges(factor)
  assert(type(TraitData) == "table" and type(TraitData.HermesWeaponTrait) == "table",
    "hades.error.outcomeUnknown")
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
  assert(type(ApplyUnitPropertyChanges) == "function", "hades.error.outcomeUnknown")
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
      and type(SetPlayerInvulnerable) == "function", "hades.error.outcomeUnknown")
    if not unit.InvulnerableFlags[trainerFlag] then SetPlayerInvulnerable(trainerFlag) end
  elseif type(unit.InvulnerableFlags) == "table" and unit.InvulnerableFlags[trainerFlag] then
    assert(type(SetPlayerVulnerable) == "function", "hades.error.outcomeUnknown")
    SetPlayerVulnerable(trainerFlag)
  end
  mountIncomingDamage(unit)
  refillAmmo(unit)
  if desired.fullHealth and not unit.IsDead then unit.Health = unit.MaxHealth; UpdateHealthUI() end
  if healthLockValid(runtime.healthLock) and not unit.IsDead then
    enforceHealthLock(unit)
    UpdateHealthUI()
  end
  local damage = damageModifier(unit, "OutgoingDamageModifiers")
  if desired.damageMultiplier == 1 then
    if damage then removeDamageModifier(unit) end
  elseif damage then
    damage.GlobalMultiplier = desired.damageMultiplier
  else
    assert(type(AddOutgoingDamageModifier) == "function", "hades.error.outcomeUnknown")
    AddOutgoingDamageModifier(unit, { Name = trainerFlag, GlobalMultiplier = desired.damageMultiplier, Multiplicative = true })
  end
  mounted.damageMultiplier = damageModifier(unit, "OutgoingDamageModifiers")
  mounted.incomingDamageMultiplier = damageModifier(unit, "IncomingDamageModifiers")
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
    assert(type(WeaponSets) == "table" and type(WeaponSets.HeroRushWeapons) == "table", "hades.error.outcomeUnknown")
    nativeChange(unit, { WeaponNames = WeaponSets.HeroRushWeapons, WeaponProperty = "ClipSize",
      ChangeValue = desired.dashBonus - mounted.dash, ChangeType = "Add" })
    mounted.dash = desired.dashBonus
  end
  if finite(runtime.moneyLock) and finite(CurrentRun.Money) then
    CurrentRun.Money = runtime.moneyLock
    if type(UpdateMoneyUI) == "function" then UpdateMoneyUI(runtime.moneyLock) end
  end
  if finite(runtime.rerollsLock) and finite(CurrentRun.NumRerolls) then
    CurrentRun.NumRerolls = runtime.rerollsLock
    if type(UpdateRerollUI) == "function" then UpdateRerollUI(runtime.rerollsLock) end
  end
  for name, _ in pairs(runtime.resourceLocks or {}) do
    enforceResource(name)
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
      local run, unit = CurrentRun, hero()
      if unit and victim == unit and not unit.IsDead
          and (healthLockValid(runtime.healthLock) or runtime.features.fullHealth) then
        -- Preserve native damage bookkeeping while preventing the locked/full
        -- health owner from crossing its requested floor.
        local parameters = {}
        for key, value in pairs(args) do parameters[key] = value end
        parameters.MinHealth = healthLockValid(runtime.healthLock)
          and runtime.healthLock.current or unit.MaxHealth
        local result = table.pack(original(victim, parameters, ...))
        if sameOwner(run, unit) and healthLockValid(runtime.healthLock) then
          enforceHealthLock(unit)
        end
        return table.unpack(result, 1, result.n)
      end
      return original(victim, args, ...)
    end
  end)
  hook("Heal", function(original)
    return function(unit, args, ...)
      local run, owner = CurrentRun, hero()
      local result = table.pack(original(unit, args, ...))
      if owner and unit == owner and sameOwner(run, owner) and healthLockValid(runtime.healthLock) then
        enforceHealthLock(owner)
      end
      return table.unpack(result, 1, result.n)
    end
  end)
  hook("ValidateMaxHealth", function(original)
    return function(blockHealing, ...)
      local run, unit = CurrentRun, hero()
      local locked = unit and healthLockValid(runtime.healthLock)
      local result = table.pack(original(locked and true or blockHealing, ...))
      if locked and sameOwner(run, unit) then enforceHealthLock(unit) end
      return table.unpack(result, 1, result.n)
    end
  end)
  hook("UpdateHealthUI", function(original)
    return function(...)
      local unit = hero()
      if unit and healthLockValid(runtime.healthLock) then enforceHealthLock(unit) end
      return original(...)
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
  local function traitSpecialRarity(traitName)
    local data = type(TraitData) == "table" and TraitData[traitName] or nil
    if type(data) ~= "table" then return nil end
    if data.IsDuoBoon or data.Frame == "Duo" then return "Duo" end
    local inherited = data.InheritFrom
    if type(inherited) == "string" then inherited = { inherited } end
    if type(inherited) == "table" then
      for _, parent in pairs(inherited) do
        if parent == "SynergyTrait" then return "Duo" end
        if parent == "ShopTier3Trait" then return "Legendary" end
      end
    end
    local levels = data.RarityLevels
    if type(levels) == "table" and type(levels.Legendary) == "table"
        and levels.Common == nil and levels.Rare == nil
        and levels.Epic == nil and levels.Heroic == nil then
      return "Legendary"
    end
    return nil
  end
  local function specialOptionKind(option)
    if type(option) ~= "table" then return nil end
    local kind = traitSpecialRarity(option.ItemName)
    if kind ~= nil then return kind end
    if option.Rarity == "Legendary" then return "Legendary" end
    return nil
  end
  local function hasSpecialBoonOption(loot, wanted)
    if type(loot) ~= "table" or type(loot.UpgradeOptions) ~= "table" then return false end
    for _, option in ipairs(loot.UpgradeOptions) do
      if specialOptionKind(option) == wanted then return true end
    end
    return false
  end
  local function forceSpecialBoonOption(loot, args, wanted)
    if wanted == "Legendary" and not runtime.boonForceLegendary then return false end
    if wanted == "Duo" and not runtime.boonForceDuo then return false end
    if type(loot) ~= "table" or type(loot.UpgradeOptions) ~= "table" then return false end
    if not rarityLootNames[loot.Name] or loot.ForceCommon then return false end
    if type(args) == "table" and args.ForceCommon then return false end
    if hasSpecialBoonOption(loot, wanted) then return true end
    if type(GetEligibleUpgrades) ~= "function" then return false end
    local choiceData = type(LootData) == "table" and LootData[loot.Name] or loot
    local ok, eligible = pcall(GetEligibleUpgrades, loot.UpgradeOptions, loot, choiceData)
    if not ok or type(eligible) ~= "table" then return false end
    local selected, excluded = {}, {}
    for _, option in ipairs(loot.UpgradeOptions) do
      if type(option) == "table" and type(option.ItemName) == "string" then selected[option.ItemName] = true end
    end
    if type(args) == "table" and type(args.ExclusionNames) == "table" then
      for _, excludedName in pairs(args.ExclusionNames) do
        if type(excludedName) == "string" then excluded[excludedName] = true end
      end
    end
    local candidate = nil
    for _, option in ipairs(eligible) do
      if type(option) == "table" and type(option.ItemName) == "string"
          and not selected[option.ItemName] and not excluded[option.ItemName]
          and traitSpecialRarity(option.ItemName) == wanted then
        -- In Hades I both Legendary and Duo boons share Rarity = "Legendary";
        -- Duo presentation/frame comes from TraitData[ItemName].IsDuoBoon.
        candidate = { ItemName = option.ItemName, Type = option.Type or "Trait", Rarity = "Legendary" }
        break
      end
    end
    if candidate == nil then return false end
    local replacement = nil
    for index = #loot.UpgradeOptions, 1, -1 do
      if specialOptionKind(loot.UpgradeOptions[index]) == nil then replacement = index; break end
    end
    if replacement ~= nil then
      loot.UpgradeOptions[replacement] = candidate
    elseif #loot.UpgradeOptions < 3 then
      loot.UpgradeOptions[#loot.UpgradeOptions + 1] = candidate
    else
      return false
    end
    return true
  end
  hook("SetTraitsOnLoot", function(original)
    return function(loot, args, ...)
      local active = runtime.features.boonRarityEnabled
        and type(loot) == "table" and rarityLootNames[loot.Name] and not loot.ForceCommon
        and not (type(args) == "table" and args.ForceCommon)
      if active then
        local odds = type(loot.RarityChances) == "table" and loot.RarityChances or nil
        local boosted = nil
        if odds and runtime.boonRarityTarget ~= "Common" then
          -- Native TraitScripts.lua selects the highest legal rarity whose chance
          -- succeeds. Raise only tiers at or below the configured minimum, leaving
          -- higher native odds (especially Legendary) untouched.
          boosted = {}
          for key, value in pairs(odds) do boosted[key] = value end
          boosted.Rare = 1
          if runtime.boonRarityTarget == "Epic" or runtime.boonRarityTarget == "Heroic" then
            boosted.Epic = 1
          end
          if runtime.boonRarityTarget == "Heroic" then boosted.Heroic = 1 end
          loot.RarityChances = boosted
        end
        -- The native selection path is synchronous; restore the exact native
        -- odds on both success and a rejected/failed native offer generation.
        local result = table.pack(pcall(original, loot, args, ...))
        if boosted then loot.RarityChances = odds end
        if not result[1] then error(result[2], 0) end
        forceSpecialBoonOption(loot, args, "Legendary")
        forceSpecialBoonOption(loot, args, "Duo")
        return table.unpack(result, 2, result.n)
      end
      return original(loot, args, ...)
    end
  end)
  hook("AddMoney", function(original)
    return function(amount, source, ...)
      local unit = hero()
      if runtime.features.moneyMultiplierEnabled and unit and source ~= trainerFlag
          and finite(amount) and amount > 0 then
        amount = math.floor(amount * runtime.features.moneyMultiplier + 0.5)
      end
      local result = table.pack(original(amount, source, ...))
      if hero() and finite(runtime.moneyLock) and type(CurrentRun) == "table" and finite(CurrentRun.Money) then
        CurrentRun.Money = runtime.moneyLock
        if type(UpdateMoneyUI) == "function" then UpdateMoneyUI(runtime.moneyLock) end
      end
      return table.unpack(result, 1, result.n)
    end
  end)
  hook("UpdateMoneyUI", function(original)
    return function(value, ...)
      local run, unit = CurrentRun, hero()
      if unit and finite(runtime.moneyLock) and finite(run and run.Money) then
        run.Money = runtime.moneyLock
        value = runtime.moneyLock
      end
      return original(value, ...)
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
  hook("AddResource", function(original)
    return function(name, amount, source, ...)
      if runtime.features.resourceMultiplierEnabled and knownResource(name)
          and source ~= trainerFlag and finite(amount) and amount > 0 then
        amount = math.floor(amount * runtime.features.resourceMultiplier + 0.5)
      end
      local result = table.pack(original(name, amount, source, ...))
      enforceResource(name)
      return table.unpack(result, 1, result.n)
    end
  end)
  hook("SpendResource", function(original)
    return function(name, amount, source, ...)
      if finite(runtime.resourceLocks[name]) and finite(amount) and amount > 0 then
        local result = table.pack(original(name, 0, source, ...))
        enforceResource(name)
        return table.unpack(result, 1, result.n)
      end
      local result = table.pack(original(name, amount, source, ...))
      enforceResource(name)
      return table.unpack(result, 1, result.n)
    end
  end)
  hook("UpdateResourceUI", function(original)
    return function(name, value, ...)
      if finite(runtime.resourceLocks[name]) and type(GameState) == "table"
          and type(GameState.Resources) == "table" then
        GameState.Resources[name] = runtime.resourceLocks[name]
        value = runtime.resourceLocks[name]
      end
      return original(name, value, ...)
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
      local unit = hero()
      if unit and finite(runtime.rerollsLock) and type(CurrentRun) == "table" then
        CurrentRun.NumRerolls = runtime.rerollsLock
        value = runtime.rerollsLock
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

local function sceneName()
  -- CurrentRun.CurrentRoom stays non-nil in the House of Hades and IsDead stays
  -- true there; inspect CurrentDeathAreaRoom before CurrentRun.CurrentRoom.
  if type(CurrentDeathAreaRoom) == "table" then
    return CurrentDeathAreaRoom.Name == "RoomPreRun" and "courtyard" or "house"
  end
  local unit = hero()
  if unit ~= nil then
    if unit.HandlingDeath == true or unit.IsDead == true then return "loading" end
    if type(CurrentRun.CurrentRoom) == "table" then return "run" end
    return "loading"
  end
  if type(CurrentRun) == "table" then return "loading" end
  return "main_menu"
end

function runtime.status()
  installHooks()
  world.install()
  local unit = hero()
  local ready = unit ~= nil
  local resources, traits, features, activeFeatures, dormantFeatures = {}, array(), {}, {}, {}
  local alive = ready and not unit.IsDead
  for name, value in pairs(runtime.features) do
    features[name] = value
    activeFeatures[name] = alive and value ~= defaults[name]
    -- Desired intent waits for its native owner: no hero, or a dead one.
    dormantFeatures[name] = value ~= defaults[name] and not alive
  end
  activeFeatures.invincibility = activeFeatures.invincibility
    and type(unit.InvulnerableFlags) == "table" and unit.InvulnerableFlags[trainerFlag] == true or false
  activeFeatures.fullHealth = activeFeatures.fullHealth and unit.Health == unit.MaxHealth or false
  activeFeatures.infiniteAmmo = activeFeatures.infiniteAmmo and type(unit.Weapons) == "table"
    and (unit.Weapons.RangedWeapon or unit.Weapons.GunWeapon) and true or false
  activeFeatures.fullGodGauge = activeFeatures.fullGodGauge and not unit.SuperActive and type(IsSuperValid) == "function" and IsSuperValid() or false
  activeFeatures.moneyMultiplierEnabled = activeFeatures.moneyMultiplierEnabled and runtime.hooks.AddMoney ~= nil or false
  activeFeatures.resourceMultiplierEnabled = activeFeatures.resourceMultiplierEnabled and runtime.hooks.AddResource ~= nil or false
  local mounted = ready and runtime.mounted
  for feature, field in pairs({ damageMultiplier = "OutgoingDamageModifiers", incomingDamageMultiplier = "IncomingDamageModifiers" }) do
    local modifier = ready and damageModifier(unit, field)
    activeFeatures[feature] = activeFeatures[feature] and mounted and mounted.unit == unit
      and mounted.objectId == unit.ObjectId and modifier ~= nil and mounted[feature] == modifier
      and modifier.GlobalMultiplier == runtime.features[feature] and modifier.Multiplicative == true or false
  end
  for feature, property in pairs({ moveSpeedMultiplier = "move", attackSpeedMultiplier = "attack", dashBonus = "dash" }) do
    activeFeatures[feature] = activeFeatures[feature] and mounted and mounted.unit == unit
      and mounted.objectId == unit.ObjectId and mounted[property] == runtime.features[feature] or false
  end
  local movement = ready and runtime.movementOwners[unit]
  if movement or (ready and CurrentRun.BlockTimerFlags and CurrentRun.BlockTimerFlags.MoveHeroToRoomPosition) then
    activeFeatures.moveSpeedMultiplier = false
    dormantFeatures.moveSpeedMultiplier = runtime.features.moveSpeedMultiplier ~= defaults.moveSpeedMultiplier
  end
  if alive then
    -- These intents also wait for their native environment: an available Aid
    -- that is not in use, and a ranged weapon to refill.
    dormantFeatures.fullGodGauge = runtime.features.fullGodGauge and (unit.SuperActive
      or not (type(IsSuperValid) == "function" and IsSuperValid())) or false
    dormantFeatures.infiniteAmmo = runtime.features.infiniteAmmo and not (type(unit.Weapons) == "table"
      and (unit.Weapons.RangedWeapon or unit.Weapons.GunWeapon)) or false
  end
  for _, name in ipairs(resourceNames) do
    resources[name] = type(GameState) == "table" and type(GameState.Resources) == "table" and tonumber(GameState.Resources[name]) or 0
  end
  local resourceLocks = {}
  for name, target in pairs(runtime.resourceLocks or {}) do
    resourceLocks[name] = target
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
  local scene = sceneName()
  local roomName = type(CurrentDeathAreaRoom) == "table" and CurrentDeathAreaRoom.Name
    or (type(CurrentRun) == "table" and type(CurrentRun.CurrentRoom) == "table" and CurrentRun.CurrentRoom.Name or nil)
  local status = (ready and (scene == "house" or scene == "courtyard" or scene == "run")) and "ready" or "waiting"
  return {
    status = status, scene = scene, roomName = roomName,
    heroReady = ready, heroId = ready and (runtime.generationId .. ":" .. instanceId(CurrentRun) .. ":" .. instanceId(unit) .. ":" .. tostring(unit.ObjectId)) or "",
    invincible = ready and type(unit.InvulnerableFlags) == "table" and unit.InvulnerableFlags[trainerFlag] == true or false,
    health = ready and tonumber(unit.Health) or 0, maxHealth = ready and tonumber(unit.MaxHealth) or 0,
    money = ready and tonumber(CurrentRun.Money) or 0, rerolls = ready and tonumber(CurrentRun.NumRerolls) or 0,
    godGauge = ready and tonumber(unit.SuperMeter) or 0, maxGodGauge = ready and tonumber(unit.SuperMeterLimit) or 0,
    healthLocked = healthLockValid(runtime.healthLock), healthLock = runtime.healthLock,
    moneyLocked = runtime.moneyLock ~= nil, moneyLock = runtime.moneyLock,
    rerollsLocked = runtime.rerollsLock ~= nil, rerollsLock = runtime.rerollsLock,
    resourceLocks = resourceLocks,
    features = features, activeFeatures = activeFeatures, dormantFeatures = dormantFeatures,
    boonRarityTarget = runtime.boonRarityTarget,
    boonForceLegendary = runtime.boonForceLegendary, boonForceDuo = runtime.boonForceDuo,
    fishingChance = runtime.fishingChance, chaosGateChance = runtime.chaosGateChance,
    canOpenSellTraits = world and world.canOpenSellTraits and world.canOpenSellTraits() or false,
    resources = resources, traits = traits, world = world.observation(),
  }
end
local function validateFeature(name, value)
  assert(defaults[name] ~= nil, "hades.error.invalidValue")
  local default = defaults[name]
  if type(default) == "boolean" then
    assert(type(value) == "boolean", "hades.error.invalidValue")
  elseif name == "dashBonus" then
    assert(finite(value) and value == math.floor(value) and value >= 0 and value <= 20, "hades.error.invalidValue")
  elseif name == "moneyMultiplier" or name == "resourceMultiplier" then
    assert(finite(value) and value >= 1 and value <= 100, "hades.error.invalidValue")
  else
    assert(finite(value) and value >= 0.1 and value <= 100, "hades.error.invalidValue")
  end
end
function runtime.configure(features)
  assert(type(features) == "table", "hades.error.invalidValue")
  for name, value in pairs(features) do validateFeature(name, value) end
  installHooks()
  for name, value in pairs(features) do runtime.features[name] = value end
  runtime.boonRarityTarget = "Heroic"
  runtime.boonForceLegendary, runtime.boonForceDuo = false, false
  runtime.fishingChance, runtime.chaosGateChance = nil, nil
  if runtime.features.moneyNoDecrease then runtime.moneyLock = nil end
  if runtime.features.rerollsNoDecrease then runtime.rerollsLock = nil end
  if not runtime.features.forceRerolls then restoreRerollDoors() end
  local unit = hero()
  if unit then mount(unit, false) end
  return runtime.status()
end
function runtime.set_feature(name, value)
  validateFeature(name, value)
  installHooks()
  runtime.features[name] = value
  if name == "moneyNoDecrease" and value then runtime.moneyLock = nil end
  if name == "rerollsNoDecrease" and value then runtime.rerollsLock = nil end
  if name == "forceRerolls" and not value then restoreRerollDoors() end
  local unit = hero()
  if unit then mount(unit, false) end
  return runtime.status()
end
function runtime.set_boon_rarity(target, forceLegendary, forceDuo)
  assert(target == "Common" or target == "Rare" or target == "Epic" or target == "Heroic",
    "hades.error.invalidValue")
  if forceLegendary ~= nil then assert(type(forceLegendary) == "boolean", "hades.error.invalidValue") end
  if forceDuo ~= nil then assert(type(forceDuo) == "boolean", "hades.error.invalidValue") end
  installHooks()
  runtime.boonRarityTarget = target
  runtime.boonForceLegendary = forceLegendary == true
  runtime.boonForceDuo = forceDuo == true
  return runtime.status()
end
local function validateSpawnChance(value)
  if value == nil then return nil end
  assert(finite(value) and value >= 0 and value <= 100, "hades.error.invalidValue")
  return value
end
function runtime.set_fishing_chance(chance)
  chance = validateSpawnChance(chance)
  installHooks()
  world.install()
  runtime.fishingChance = chance
  return runtime.status()
end
function runtime.set_chaos_gate_chance(chance)
  chance = validateSpawnChance(chance)
  installHooks()
  world.install()
  runtime.chaosGateChance = chance
  return runtime.status()
end
function runtime.configure_locks(health, money, rerolls, resourceLocks)
  if health ~= nil then
    assert(healthLockValid(health), "hades.error.invalidValue")
  end
  if money ~= nil then
    assert(finite(money) and money == math.floor(money) and money >= 0 and money <= 1000000000,
      "hades.error.invalidValue")
    assert(not runtime.features.moneyNoDecrease, "hades.error.invalidValue")
  end
  if rerolls ~= nil then
    assert(finite(rerolls) and rerolls == math.floor(rerolls) and rerolls >= 0 and rerolls <= 1000000000,
      "hades.error.invalidValue")
    assert(not runtime.features.rerollsNoDecrease, "hades.error.invalidValue")
  end
  local nextResourceLocks = {}
  if resourceLocks ~= nil then
    assert(type(resourceLocks) == "table", "hades.error.invalidValue")
    for resourceName, resourceValue in pairs(resourceLocks) do
      assert(knownResource(resourceName) and finite(resourceValue)
        and resourceValue == math.floor(resourceValue)
        and resourceValue >= 0 and resourceValue <= 1000000000, "hades.error.invalidValue")
      nextResourceLocks[resourceName] = resourceValue
    end
  end
  installHooks()
  local unit = hero()
  local releasingHealth = health == nil and healthLockValid(runtime.healthLock)
  if releasingHealth then
    releaseHealthLock(unit)
  else
    runtime.healthLock = health and { current = health.current, max = health.max } or nil
  end
  runtime.moneyLock, runtime.rerollsLock = money, rerolls
  runtime.resourceLocks = nextResourceLocks
  if unit then mount(unit, false) end
  return runtime.status()
end
function runtime.lock_vital(name, locked)
  local unit = requireHero()
  assert(name == "health" and type(locked) == "boolean", "hades.error.invalidValue")
  if locked then
    assert(finite(unit.Health) and finite(unit.MaxHealth) and unit.Health >= 1
      and unit.MaxHealth >= 1 and unit.Health <= unit.MaxHealth, "hades.error.invalidValue")
    runtime.healthLock = { current = unit.Health, max = unit.MaxHealth }
    enforceHealthLock(unit)
    UpdateHealthUI()
  else
    -- Restore the game's trait/mirror-owned maximum without retroactively
    -- healing damage that was suppressed while the lock was active.
    releaseHealthLock(unit)
  end
  return runtime.status()
end
function runtime.lock_resource(name, locked)
  local unit = requireHero()
  assert(type(locked) == "boolean", "hades.error.invalidValue")
  if name == "Money" then
    if locked then
      assert(not runtime.features.moneyNoDecrease and finite(CurrentRun.Money),
        "hades.error.invalidValue")
      runtime.moneyLock = CurrentRun.Money
    else
      runtime.moneyLock = nil
    end
  elseif knownResource(name) then
    assert(type(GameState) == "table" and type(GameState.Resources) == "table", "hades.error.unsupportedRuntime")
    if locked then
      local current = tonumber(GameState.Resources[name]) or 0
      assert(finite(current) and current >= 0 and current <= 1000000000, "hades.error.invalidValue")
      runtime.resourceLocks[name] = math.floor(current)
    else
      runtime.resourceLocks[name] = nil
    end
  else
    error("hades.error.invalidValue")
  end
  installHooks()
  mount(unit, false)
  return runtime.status()
end
function runtime.lock_rerolls(locked)
  local unit = requireHero()
  assert(type(locked) == "boolean", "hades.error.invalidValue")
  if locked then
    assert(not runtime.features.rerollsNoDecrease and finite(CurrentRun.NumRerolls),
      "hades.error.invalidValue")
    runtime.rerollsLock = CurrentRun.NumRerolls
  else
    runtime.rerollsLock = nil
  end
  mount(unit, false)
  return runtime.status()
end
function runtime.disable_all()
  world.clearPending()
  for name, value in pairs(defaults) do runtime.features[name] = value end
  runtime.boonRarityTarget = "Heroic"
  runtime.boonForceLegendary, runtime.boonForceDuo = false, false
  runtime.fishingChance, runtime.chaosGateChance = nil, nil
  local unit = hero()
  if healthLockValid(runtime.healthLock) then releaseHealthLock(unit)
  else runtime.healthLock = nil end
  runtime.moneyLock, runtime.rerollsLock = nil, nil
  runtime.resourceLocks = {}
  restoreRerollDoors()
  if unit then mount(unit, false) end
  return runtime.status()
end
function runtime.set_value(field, value)
  local unit = requireHero()
  assert(finite(value) and value == math.floor(value) and value >= 0 and value <= 1000000000, "hades.error.invalidValue")
  if field == "health" then
    assert(value >= 1 and value <= unit.MaxHealth, "hades.error.invalidValue")
    unit.Health = value
    if healthLockValid(runtime.healthLock) then runtime.healthLock.current = value end
    UpdateHealthUI()
  elseif field == "maxHealth" then
    assert(value >= 1, "hades.error.invalidValue")
    local activeLock = healthLockValid(runtime.healthLock) and runtime.healthLock or nil
    if activeLock then
      -- A fixed vital lock owns only its visible current/max pair. Do not
      -- rewrite the native run contribution underneath it: Hearts, Mirror,
      -- curses and trait multipliers keep evolving there and resume on unlock.
      activeLock.max = value
      activeLock.current = math.min(activeLock.current, value)
      enforceHealthLock(unit)
    else
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
      unit.Health = math.max(1, math.min(unit.Health, unit.MaxHealth))
    end
    UpdateHealthUI()
  elseif field == "godGauge" then
    assert(not unit.SuperActive and finite(unit.SuperMeterLimit) and value <= unit.SuperMeterLimit,
      "hades.error.invalidValue")
    BuildSuperMeter(CurrentRun, value - (unit.SuperMeter or 0))
    UpdateSuperMeterUI()
  elseif field == "money" then
    CurrentRun.Money = value
    if runtime.moneyLock ~= nil then runtime.moneyLock = value end
    UpdateMoneyUI(value)
  elseif field == "rerolls" then
    CurrentRun.NumRerolls = value
    if runtime.rerollsLock ~= nil then runtime.rerollsLock = value end
    UpdateRerollUI(value)
  else error("hades.error.invalidValue") end
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
  if runtime.resourceLocks[name] ~= nil then runtime.resourceLocks[name] = value end
  if type(UpdateResourceUI) == "function" then UpdateResourceUI(name, value) end
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
local function beginDeferredMutation(slot)
  local command = runtime[slot]
  if command and command.executionThread == coroutine.running() then command.mutationStarted = true end
end
local function beginTraitMutation()
  beginDeferredMutation("traitCommand")
end
local function beginWorldMutation()
  beginDeferredMutation("worldCommand")
end
local function closeTraitMenu()
  local menu = type(ScreenAnchors) == "table" and ScreenAnchors.TraitTrayScreen
  if not menu then return end
  assert(menu.CanClose and type(CloseAdvancedTooltipScreen) == "function", "hades.error.runtimeNotReady")
  CloseAdvancedTooltipScreen()
  assert(ScreenAnchors.TraitTrayScreen == nil, "hades.error.runtimeNotReady")
  local command = runtime.traitCommand
  if command and command.executionThread == coroutine.running() then command.menu = nil end
  return true
end
local function selectedTrait(unit, id)
  for _, group in ipairs(traitGroups(unit)) do
    if group.instanceId == id then
      return group
    end
  end
  error("hades.error.staleTrait")
end
local function equipOwnedTrait(unit, name, source, rarity, level, expectedId)
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
  if closeTraitMenu() and expectedId then
    local group = selectedTrait(unit, expectedId)
    assert(group.canEdit, "hades.error.unsupportedTrait")
    assert(group.trait == previous, "hades.error.staleTrait")
  end
  beginTraitMutation()
  suspendProperties(unit)
  runtime.propertyDepth = runtime.propertyDepth + 1
  if previous then unequip(unit, previous.Name) end
  if progressOwner then progressOwner[name] = progressValue end
  GameState[ownerKey] = name
  if assist then EquipReferencedWeapons(source) end
  equip(unit, name)
  for _, trait in pairs(unit.Traits or {}) do
    if trait.Name == name then
      if assist then
        AddAssistWeapons(unit, trait)
        if previous and previous.Name == name and finite(previous.RemainingUses) then
          -- AwardMenuScripts UpgradeAssistKeepsake grants one use per added rank.
          trait.RemainingUses = math.max(0, previous.RemainingUses + rank - currentRank)
          UpdateTraitNumber(trait)
        end
      elseif previous and previous.Name == name then
        -- AdvanceKeepsake restores earned effects after native unequip/equip.
        if previous.AccumulatedDodgeBonus then
          trait.AccumulatedDodgeBonus = previous.AccumulatedDodgeBonus
          SetLifeProperty({ Property = "DodgeChance", Value = trait.AccumulatedDodgeBonus,
            ValueChangeType = "Add", DestinationId = unit.ObjectId, DataValue = false })
          SetUnitProperty({ Property = "Speed", Value = 1 + trait.AccumulatedDodgeBonus,
            ValueChangeType = "Multiply", DestinationId = unit.ObjectId })
        end
        trait.AccumulatedDamageBonus, trait.Uses, trait.CurrentRoom =
          previous.AccumulatedDamageBonus, previous.Uses, previous.CurrentRoom
        if name == "ReincarnationTrait" then RecreateLifePips() end
        UpdateTraitNumber(trait)
      end
      break
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
  local patroclus = false
  for _, choice in ipairs(PresetEventArgs.PatroclusBenefitChoices) do
    for _, action in ipairs(choice) do
      if action.PostLineThreadedFunctionName == "PatroclusBuff"
          and action.PostLineFunctionArgs.TraitName == name then patroclus = true end
    end
  end
  assert(not patroclus or level == 1, "hades.error.invalidValue")
  closeTraitMenu()
  beginTraitMutation()
  suspendProperties(unit)
  if patroclus then
    -- PatroclusBuff's synchronous trait owner; its presentation yields first.
    AddTraitToHero({ TraitData = source })
  else addTraits(unit, name, rarity, level) end
  mount(unit, false)
  return runtime.status()
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
  if closeTraitMenu() then
    group = selectedTrait(unit, id)
    assert(group.canRemove, "hades.error.unsupportedTrait")
  end
  beginTraitMutation()
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
    equipOwnedTrait(unit, trait.Name, source, rarity, level, id)
  else
    if closeTraitMenu() then
      group = selectedTrait(unit, id)
      assert(group.canEdit, "hades.error.unsupportedTrait")
      trait = group.trait
    end
    beginTraitMutation()
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
  beginTraitMutation()
  group.trait[group.useField] = uses
  TraitUIUpdateText(group.trait)
  return runtime.status()
end
function runtime.refresh_trait(id)
  local unit = requireHero()
  local group = selectedTrait(unit, id)
  assert(group.canRefresh, "hades.error.unsupportedTrait")
  beginTraitMutation()
  IncrementTraitCooldown(group.trait, group.cooldownLimit)
  TraitUIUpdateText(group.trait)
  return runtime.status()
end
function runtime.expire_trait(id)
  local unit = requireHero()
  local group = selectedTrait(unit, id)
  assert(group.canRemove and group.canExpire, "hades.error.unsupportedTrait")
  local expiration = group.trait.OnExpire
  if expiration and (expiration.Traits or expiration.TraitData) and closeTraitMenu() then
    group = selectedTrait(unit, id)
    assert(group.canRemove and group.canExpire, "hades.error.unsupportedTrait")
  end
  beginTraitMutation()
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
  closeTraitMenu()
  beginTraitMutation()
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
local function deferredCommandResult(slot, id)
  local command = runtime[slot]
  assert(command and command.id == id, "hades.error.staleTarget")
  return { id = id, state = command.state, mutationStarted = command.mutationStarted,
    result = command.result, error = command.error }
end
local function cancelDeferredCommand(slot, id, timeoutMessage)
  local command = runtime[slot]
  assert(command and command.id == id, "hades.error.staleTarget")
  if command.state == "pending" then
    command.state = "cancelled"
  elseif command.state == "running" then
    command.state = "unknown"
    command.error = timeoutMessage
    if command.propertyDepth ~= nil then runtime.propertyDepth = command.propertyDepth end
  end
  return deferredCommandResult(slot, id)
end
local function submitDeferredCommand(slot, id, name, arguments, options)
  local previous = runtime[slot]
  if previous and previous.id == id then return deferredCommandResult(slot, id) end
  assert(not previous or (previous.state ~= "unknown"
    and not (previous.state == "error" and previous.mutationStarted)), "hades.error.restartRequired")
  assert(not previous or (previous.state ~= "pending" and previous.state ~= "running"),
    "hades.error.runtimeNotReady")
  assert(options.allowed(name), "hades.error.invalidValue")
  assert(type(_threads) == "table", "hades.error.runtimeNotReady")
  local command = options.captureContext({ id = id, state = "pending", mutationStarted = false })
  runtime[slot] = command
  local function failOwner()
    command.state = command.state == "running" and "unknown" or "error"
    command.error = "hades.error.staleTarget"
    if command.propertyDepth ~= nil then runtime.propertyDepth = command.propertyDepth end
  end
  local scheduled = coroutine.create(function()
    if command.state ~= "pending" then return end
    if not options.ownsContext(command) then failOwner(); return end
    command.state = "running"
    command.propertyDepth = runtime.propertyDepth
    command.executionThread = coroutine.create(function()
      local ok, value = xpcall(function()
        return runtime[name](table.unpack(arguments, 1, arguments.n))
      end, tostring)
      if ok then
        command.result, command.state = value, "complete"
      else
        command.error, command.state = value, "error"
        runtime.propertyDepth = command.propertyDepth
      end
    end)
    while command.state == "running" do
      if not options.ownsContext(command) then failOwner(); return end
      local ok, waiting = coroutine.resume(command.executionThread)
      if not ok then
        command.error, command.state = tostring(waiting), "error"
        runtime.propertyDepth = command.propertyDepth
        return
      end
      if coroutine.status(command.executionThread) == "dead" then return end
      coroutine.yield(waiting)
    end
  end)
  -- Main.lua update owns the first resume. Calling native thread() here would
  -- run the first native side effects inside the debugger expression again.
  table.insert(_threads, { thread = scheduled, resumeTime = -1 })
  return deferredCommandResult(slot, id)
end
function runtime.trait_command_result(id)
  return deferredCommandResult("traitCommand", id)
end
function runtime.cancel_trait_command(id)
  return cancelDeferredCommand("traitCommand", id, "native trait command did not complete before its deadline")
end
function runtime.submit_trait_command(id, name, arguments)
  return submitDeferredCommand("traitCommand", id, name, arguments, {
    allowed = function(commandName)
      return commandName == "add_trait" or commandName == "update_trait" or commandName == "remove_trait"
        or commandName == "set_trait_uses" or commandName == "expire_trait" or commandName == "refresh_trait"
        or commandName == "add_chaos_pair"
    end,
    captureContext = function(command)
      local unit = requireHero()
      command.run = CurrentRun
      command.unit = unit
      command.objectId = unit.ObjectId
      command.room = CurrentRun.CurrentRoom
      command.menu = type(ScreenAnchors) == "table" and ScreenAnchors.TraitTrayScreen or nil
      return command
    end,
    ownsContext = function(command)
      return CurrentRun == command.run and hero() == command.unit
        and command.unit.ObjectId == command.objectId and CurrentRun.CurrentRoom == command.room
        and (type(ScreenAnchors) == "table" and ScreenAnchors.TraitTrayScreen or nil) == command.menu
    end,
  })
end
function runtime.world_command_result(id)
  return deferredCommandResult("worldCommand", id)
end
function runtime.cancel_world_command(id)
  return cancelDeferredCommand("worldCommand", id, "native world command did not complete before its deadline")
end
function runtime.submit_world_command(id, name, arguments)
  return submitDeferredCommand("worldCommand", id, name, arguments, {
    allowed = function(commandName)
      return commandName == "gain_resource" or commandName == "spawn_reward"
        or commandName == "generate_fishing" or commandName == "generate_chaos_gate"
        or commandName == "generate_chamber_object" or commandName == "apply_world_exit"
        or commandName == "cancel_world_exit"
    end,
    captureContext = function(command)
      local unit = requireHero()
      command.run = CurrentRun
      command.unit = unit
      command.objectId = unit.ObjectId
      command.room = CurrentRun.CurrentRoom
      return command
    end,
    ownsContext = function(command)
      return CurrentRun == command.run and hero() == command.unit
        and command.unit.ObjectId == command.objectId and CurrentRun.CurrentRoom == command.room
    end,
  })
end
world = (function()
  local edits = setmetatable({}, { __mode = "k" })
  local doorEpochs = setmetatable({}, { __mode = "k" })
  local doorObservations = setmetatable({}, { __mode = "k" })
  local occurrenceRequest
  local occurrenceSelection
  local occurrenceGeneration
  local occurrencePendingRoom
  local occurrenceSelectedRooms = setmetatable({}, { __mode = "k" })
  local chaosRooms = setmetatable({}, { __mode = "k" })
  local directBypassQuery = nil
  local occurrenceTargetOrder = {
    "npc:Sisyphus", "npc:Eurydice", "npc:Patroclus", "npc:Thanatos", "shop:Charon",
  }
  local occurrenceTargets = {
    ["npc:Sisyphus"] = { kind = "character", sourceId = "Sisyphus", nativeEncounter = "Story_Sisyphus_01", rooms = { A_Story01 = true } },
    ["npc:Eurydice"] = { kind = "character", sourceId = "Eurydice", nativeEncounter = "Story_Eurydice_01", rooms = { B_Story01 = true } },
    ["npc:Patroclus"] = { kind = "character", sourceId = "Patroclus", nativeEncounter = "Story_Patroclus_01", rooms = { C_Story01 = true } },
    ["npc:Thanatos"] = { kind = "character", sourceId = "Thanatos", encounterSet = "ThanatosEncounters" },
    ["shop:Charon"] = { kind = "shop", sourceId = "Charon", rooms = {
      A_Shop01 = true, B_Shop01 = true, C_Shop01 = true,
      A_PreBoss01 = true, B_PreBoss01 = true, C_PreBoss01 = true, D_Hub = true,
    } },
  }
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
  -- Physical owner and mutable reward fields have separate identities.
  -- A Trainer reward Apply preserves the original observed token; a native
  -- reroll or target-room replacement invalidates that token and its lease.
  local function physicalDoorId(door)
    return table.concat({
      runtime.generationId, instanceId(CurrentRun), instanceId(currentRoom()),
      instanceId(door), tostring(door.ObjectId), instanceId(door.Room),
      tostring(doorEpochs[door] or 0),
    }, ":")
  end
  local function rewardSignature(room)
    local overrides = type(room.RewardOverrides) == "table" and instanceId(room.RewardOverrides) or ""
    local reward = type(room.Reward) == "table" and instanceId(room.Reward) or ""
    return table.concat({
      tostring(room.ChosenRewardType), tostring(room.ForceLootName), overrides, reward,
    }, ":")
  end
  local activeEdit
  local function doorId(door)
    -- Native in-place mutation can return to an earlier reward signature (ABA)
    -- even when no Trainer lease exists. Record every observed identity change,
    -- while keeping a confirmed Trainer Apply/Cancel on its exact original token.
    local edit = activeEdit(door)
    if edit and edit.kind == "reward" then return edit.doorToken end
    local physical = physicalDoorId(door)
    local signature = rewardSignature(door.Room)
    local observed = doorObservations[door]
    if observed and observed.physical == physical and observed.signature ~= signature then
      doorEpochs[door] = (doorEpochs[door] or 0) + 1
      physical = physicalDoorId(door)
    end
    doorObservations[door] = { physical = physical, signature = signature }
    return physical .. ":" .. signature
  end
  local function ordinaryDoor(door)
    return door.Room and door.ReadyToUse and door.Name ~= "SecretDoor" and door.Name ~= "ShrinePointDoor"
  end
  -- A run-scoped occurrence survives a normal room transition, but only a
  -- live room or a room being built by native CreateRoom may select it.
  -- Stale retained Room tables must never consume a future occurrence.
  local function liveEncounterRoom(run, room)
    if run ~= CurrentRun or type(room) ~= "table" then return false end
    if room == currentRoom() then return true end
    local generation = occurrenceGeneration
    if generation and generation.run == run and generation.hero == hero()
        and generation.sourceRoom ~= nil and generation.sourceRoom == currentRoom()
        and generation.roomName == room.Name then return true end
    for _, door in pairs(OfferedExitDoors or {}) do
      if ordinaryDoor(door) and door.Room == room then return true end
    end
    return false
  end
  local function requireDoor(params)
    requireRoom(params)
    local token = params.doorToken or params.doorId
    for _, door in pairs(OfferedExitDoors or {}) do
      if ordinaryDoor(door) and doorId(door) == token then return door end
    end
    error("hades.error.staleDoor")
  end
  local function clearOccurrenceRoomSelections()
    occurrencePendingRoom = nil
    occurrenceSelectedRooms = setmetatable({}, { __mode = "k" })
  end
  local function validOccurrence()
    local request = occurrenceRequest
    if type(request) ~= "table" or request.run ~= CurrentRun or request.hero ~= hero()
        or occurrenceTargets[request.target] == nil then
      occurrenceRequest = nil
      clearOccurrenceRoomSelections()
      return nil
    end
    return request
  end
  local function occurrenceRoomMatches(definition, room)
    if type(definition) ~= "table" or type(definition.rooms) ~= "table"
        or type(room) ~= "table" or definition.rooms[room.Name] ~= true then return false end
    local native = definition.nativeEncounter
    if type(native) == "string" then
      -- Story room eligibility alone does not prove the named NPC's presence.
      local legal = false
      for _, name in pairs(type(room.LegalEncounters) == "table" and room.LegalEncounters or {}) do
        if name == native then legal = true; break end
      end
      if not legal then return false end
      if type(room.Encounter) == "table" and room.Encounter.Name ~= native then return false end
    end
    return true
  end
  local function occurrenceRoomCandidateEligible(definition, room)
    if not occurrenceRoomMatches(definition, room) then return false end
    local name = definition.nativeEncounter
    if type(name) ~= "string" then return true end
    local encounter = type(EncounterData) == "table" and EncounterData[name] or nil
    if type(encounter) ~= "table" or type(IsEncounterEligible) ~= "function" then return false end
    -- Native predicate is given a shallow copy so normalization cannot mutate
    -- its source RoomData owner during this non-destructive selection probe.
    local probe = {}
    for key, value in pairs(room) do probe[key] = value end
    if type(room.LegalEncounters) == "table" then
      probe.LegalEncountersDictionary = {}
      for _, id in pairs(room.LegalEncounters) do probe.LegalEncountersDictionary[id] = true end
    end
    if type(room.IllegalEncounters) == "table" then
      probe.IllegalEncountersDictionary = {}
      for _, id in pairs(room.IllegalEncounters) do probe.IllegalEncountersDictionary[id] = true end
    end
    local ok, eligible = pcall(IsEncounterEligible, CurrentRun, probe, encounter)
    if not ok then error(eligible, 0) end
    return eligible == true
  end
  local function occurrenceEncounterMatches(definition, encounter)
    if type(definition) ~= "table" or type(encounter) ~= "table" then return false end
    if type(definition.encounters) == "table" and definition.encounters[encounter.Name] then return true end
    local set = definition.encounterSet and type(EncounterSets) == "table"
      and EncounterSets[definition.encounterSet] or nil
    for _, name in pairs(set or {}) do if name == encounter.Name then return true end end
    return false
  end
  local function consumeOccurrence(target, token)
    local request = validOccurrence()
    if not request or request.target ~= target or request.leaseToken ~= token then return false end
    occurrenceRequest = nil
    clearOccurrenceRoomSelections()
    return true
  end
  local function occurrenceRoomReserved(request)
    local pending = occurrencePendingRoom
    if pending and (pending.leaseToken ~= request.leaseToken
        or pending.run ~= CurrentRun or pending.hero ~= hero()
        or pending.sourceRoom ~= currentRoom()) then
      occurrencePendingRoom = nil
      pending = nil
    end
    if pending then return true end
    for room, selected in pairs(occurrenceSelectedRooms) do
      if selected.leaseToken ~= request.leaseToken or selected.run ~= CurrentRun
          or selected.hero ~= hero() or selected.sourceRoom ~= currentRoom()
          or (selected.door and selected.door.Room ~= room) then
        occurrenceSelectedRooms[room] = nil
      else
        return true
      end
    end
    return false
  end
  local function occurrenceChoose(kind, original, ...)
    local request = validOccurrence()
    local definition = request and occurrenceTargets[request.target] or nil
    local hasTarget = kind == "room" and type(definition and definition.rooms) == "table"
      or kind == "encounter" and definition ~= nil
        and (type(definition.encounters) == "table" or definition.encounterSet ~= nil)
    if not hasTarget then return original(...) end
    if kind == "room" and (select(1, ...) ~= CurrentRun or occurrenceRoomReserved(request)) then
      return original(...)
    end
    local previous = occurrenceSelection
    occurrenceSelection = {
      kind = kind, target = request.target, leaseToken = request.leaseToken,
      eligible = {}, nativeForced = false,
    }
    local packed = table.pack(pcall(original, ...))
    occurrenceSelection = previous
    if not packed[1] then error(packed[2], 0) end
    return table.unpack(packed, 2, packed.n)
  end
  local function occurrenceObserveForced(kind, original, run, room, candidate, ...)
    local native = original(run, room, candidate, ...)
    local selection = occurrenceSelection
    local request = validOccurrence()
    if selection and request and selection.kind == kind
        and selection.target == request.target and selection.leaseToken == request.leaseToken then
      if native then selection.nativeForced = true end
      if type(candidate) == "table" then selection.eligible[candidate] = true end
    end
    return native
  end
  local function occurrenceRandom(original, pool, ...)
    local selection = occurrenceSelection
    local request = validOccurrence()
    if selection and request and not selection.nativeForced
        and selection.target == request.target and selection.leaseToken == request.leaseToken
        and type(pool) == "table" then
      local definition = occurrenceTargets[selection.target]
      local choices = {}
      for _, candidate in pairs(pool) do
        local data = candidate
        if selection.kind == "room" and type(candidate) == "string" then
          data = type(RoomData) == "table" and RoomData[candidate] or nil
        end
        if selection.eligible[data] then
          local matched = selection.kind == "room" and occurrenceRoomCandidateEligible(definition, data)
            or selection.kind == "encounter" and occurrenceEncounterMatches(definition, data)
          if matched then choices[#choices + 1] = candidate end
        end
      end
      if #choices > 0 then
        local chosen = original(choices, ...)
        if selection.kind == "room" then
          occurrencePendingRoom = {
            run = CurrentRun, hero = hero(), sourceRoom = currentRoom(),
            leaseToken = request.leaseToken, chosen = chosen,
          }
        end
        return chosen
      end
    end
    return original(pool, ...)
  end
  local routeOrder = { "combat", "miniboss", "story", "shop", "reprieve" }
  local function routeKind(name)
    if type(name) ~= "string" then return nil end
    if name:find("_Story", 1, true) then return "story" end
    if name:find("_Shop", 1, true) then return "shop" end
    if name:find("_Reprieve", 1, true) then return "reprieve" end
    if name:find("_MiniBoss", 1, true) then return "miniboss" end
    if name:find("_Combat", 1, true) then return "combat" end
  end
  local function copyTbl(t)
    local c = {}
    if type(t) == "table" then for k, v in pairs(t) do c[k] = v end end
    return c
  end
  local function hasVal(list, w)
    if type(list) ~= "table" then return false end
    for _, v in pairs(list) do if v == w then return true end end
    return false
  end
  local function hasAll(list, req)
    if type(ContainsAll) == "function" then return ContainsAll(list, req) end
    if type(list) ~= "table" or type(req) ~= "table" then return false end
    for _, v in pairs(req) do if not hasVal(list, v) then return false end end
    return true
  end
  local function nativeEligibilityProbe(cb, posForced, ...)
    local rc, rv, ri, rf, src = RandomChance, GetRandomValue, RandomInt, RandomFloat, SessionMapState
    local used = false
    if type(src) == "table" then SessionMapState = copyTbl(src) end
    RandomChance = function(ch) if type(ch) == "number" and ch > 0 then used = true; return posForced end return false end
    GetRandomValue = function(vals) used = true; return type(vals) == "table" and vals[1] or vals end
    if type(ri) == "function" then RandomInt = function(m) used = true; return m end end
    if type(rf) == "function" then RandomFloat = function(m) used = true; return m end end
    local ok, res = pcall(cb, ...)
    SessionMapState, RandomChance, GetRandomValue = src, rc, rv
    if type(ri) == "function" then RandomInt = ri end
    if type(rf) == "function" then RandomFloat = rf end
    if not ok then error(res, 0) end
    return res, used
  end
  local function routeSourceSafe(door)
    local src = currentRoom()
    if type(src) ~= "table" then return false, "source_unavailable" end
    if type(door) ~= "table" then return false, "door_unavailable" end
    local a = type(door.ChooseRoomArgs) == "table" and door.ChooseRoomArgs or {}
    if ForceNextRoom ~= nil then return false, "global_forced_destination" end
    if door.ForceRoomName ~= nil or a.ForceNextRoom ~= nil or src.ForceNextRoom ~= nil then return false, "door_forced_destination" end
    if a.ForceNextRoomSet ~= nil or a.RoomDataSet ~= nil then return false, "door_forced_room_set" end
    if src.ForceNextRoomSet ~= nil then return false, "source_forced_room_set" end
    if src.NextRoomSet or src.NextRoomSetNoGenerate or a.NextRoomSet or a.NextRoomSetNoGenerate or src.NextRoomSetName then
      return false, "source_next_room_set"
    end
    if src.UsePreviousRoomSet or a.UsePreviousRoomSet or door.UsePreviousRoomSet then return false, "source_uses_previous_room_set" end
    if src.LinkedRoom or src.LinkedRooms or src.LinkedRoomByPactLevel then return false, "source_linked_destination" end
    if src.PersistentExitDoorRewards then return false, "source_persistent_door_rooms" end
    if door.ReturnToPreviousRoom or door.ReturnToPreviousRoomName then return false, "door_returns_to_previous_room" end
    return true, "safe"
  end
  local function regionFor(door, src, args)
    if type(args.RoomSetName) == "string" and type(RoomSetData[args.RoomSetName]) == "table" then return args.RoomSetName end
    local own = type(door.Room) == "table" and door.Room.RoomSetName or nil
    if type(own) == "string" and type(RoomSetData[own]) == "table" then return own end
    return src.RoomSetName or "Tartarus"
  end
  local function couldBeForced(data, args)
    if type(IsRoomForced) ~= "function" then return true, false end
    local forced, stoch = nativeEligibilityProbe(IsRoomForced, true, CurrentRun, currentRoom(), data, copyTbl(args))
    return not not forced, stoch
  end
  local function routeCandidatesWithDiagnostics(door, diag)
    diag = diag or {}
    local src = currentRoom()
    if type(src) ~= "table" or type(RoomSetData) ~= "table" then return nil end
    local args = type(door) == "table" and type(door.ChooseRoomArgs) == "table" and door.ChooseRoomArgs or {}
    local _, safety = routeSourceSafe(door)
    diag.sourceSafety = safety
    local roomSet = RoomSetData[regionFor(door, src, args)]
    if type(roomSet) ~= "table" then return nil end
    diag.eligibilityUnavailable = type(IsRoomEligible) ~= "function" or nil
    local res = {}
    for key, data in pairs(roomSet) do
      if type(data) == "table" and not data.DebugOnly then
        local name = type(data.Name) == "string" and data.Name or tostring(key)
        local kind = routeKind(name)
        local probe = copyTbl(data); if probe.Name == nil then probe.Name = name end
        local eligible, failed, forced = false, false, false
        if not diag.eligibilityUnavailable then
          local ok, val, rnd = pcall(nativeEligibilityProbe, IsRoomEligible, false, CurrentRun, src, probe, copyTbl(args))
          if not ok then failed = true
          elseif rnd then diag.randomEligibilityRooms = diag.randomEligibilityRooms or {}; diag.randomEligibilityRooms[name] = true
          else eligible = val and true or false end
        end
        if eligible then
          local fOk, fVal, fRnd = pcall(couldBeForced, probe, args)
          if not fOk then failed = true
          elseif fRnd then diag.randomForceRoom = diag.randomForceRoom or name
          elseif fVal then forced = true; diag.forcedRoom = diag.forcedRoom or name end
        end
        if kind then
          local b = res[kind] or { all = {}, eligible = {}, forced = {}, probeErrors = 0 }; res[kind] = b
          if failed then b.probeErrors = b.probeErrors + 1
          else
            b.all[#b.all + 1] = data
            if eligible then b.eligible[#b.eligible + 1] = data end
            if forced then b.forced[#b.forced + 1] = data end
          end
        end
      end
    end
    local function byName(a, b) return tostring(a.Name) < tostring(b.Name) end
    for _, b in pairs(res) do table.sort(b.all, byName); table.sort(b.eligible, byName); table.sort(b.forced, byName) end
    return res
  end
  local function routeRooms(b)
    if type(b) ~= "table" then return nil end
    return #b.forced > 0 and b.forced or (#b.eligible > 0 and b.eligible or b.all)
  end
  local function roomUnavailableReason(data, door, rDiag)
    rDiag = rDiag or {}
    if type(data) ~= "table" then return "native_ineligible" end
    local name = tostring(data.Name or "")
    if rDiag.randomEligibilityRooms and rDiag.randomEligibilityRooms[name] then return "room_eligibility_requires_rng" end
    local run, src = type(CurrentRun) == "table" and CurrentRun or {}, currentRoom() or {}
    local a = type(door) == "table" and type(door.ChooseRoomArgs) == "table" and door.ChooseRoomArgs or {}
    if (type(a.ExcludedNames) == "table" and a.ExcludedNames[name])
        or (type(a.ExcludedTypes) == "table" and a.ExcludedTypes[data.Type])
        or (type(a.ExcludedRewards) == "table" and type(data.RewardTypes) == "table"
          and #data.RewardTypes > 0 and hasAll(a.ExcludedRewards, data.RewardTypes)) then
      return "room_excluded_by_exit_rules"
    end
    local depth = finite(run.BiomeDepthCache) and run.BiomeDepthCache or 0
    if data.ForceAtBiomeDepth ~= nil and depth ~= data.ForceAtBiomeDepth then
      return depth < data.ForceAtBiomeDepth and "biome_depth_too_low" or "biome_depth_too_high"
    end
    if data.ForceAtBiomeDepthMin ~= nil and depth < data.ForceAtBiomeDepthMin then return "biome_depth_too_low" end
    if src.Name == name then return "room_same_as_source" end
    if data.Starting and not src.AllowNextRoomStarting then return "room_starting_not_allowed" end
    if data.RequiresLinked and src.LinkedRoom ~= name and not hasVal(src.LinkedRooms, name) then return "room_linked_route_required" end
    if src.RequireWingEndMiniBoss and data.WingEndRoom and not data.WingEndMiniBoss and not data.AllowAsAnyWingEnd then return "room_wrong_wing_end" end
    if not src.RequireWingEndMiniBoss and data.WingEndRoom and data.WingEndMiniBoss and not data.AllowAsAnyWingEnd then return "room_miniboss_wing_required" end
    if data.MaxAppearancesThisRun and type(run.RoomCountCache) == "table" and finite(run.RoomCountCache[name]) and run.RoomCountCache[name] >= data.MaxAppearancesThisRun then return "room_max_appearances_this_run" end
    if data.MaxAppearancesThisBiome and type(run.BiomeRoomCountCache) == "table" and finite(run.BiomeRoomCountCache[name]) and run.BiomeRoomCountCache[name] >= data.MaxAppearancesThisBiome then return "max_appearances_this_biome" end
    if data.MaxCreationsThisRun and type(run.RoomCreations) == "table" and finite(run.RoomCreations[name]) and run.RoomCreations[name] >= data.MaxCreationsThisRun then return "max_creations_this_run" end
    if data.GameStateRequirements ~= nil then
      if type(IsGameStateEligible) ~= "function" then return "game_state_requirements" end
      local ok, el, rnd = pcall(nativeEligibilityProbe, IsGameStateEligible, false, CurrentRun, copyTbl(data), data.GameStateRequirements, copyTbl(a))
      if not ok then return "room_eligibility_probe_error" end
      if rnd then return "room_eligibility_requires_rng" end
      if not el then return "game_state_requirements" end
    end
    return "native_ineligible"
  end
  local function routeWarning(b, door, rDiag)
    if rDiag.sourceSafety ~= nil and rDiag.sourceSafety ~= "safe" then return rDiag.sourceSafety end
    if #b.eligible == 0 then return rDiag.eligibilityUnavailable and "room_eligibility_unavailable" or roomUnavailableReason(b.all[1], door, rDiag) end
    if rDiag.forcedRoom ~= nil and #b.forced == 0 then return "native_forced_room_present" end
    return nil
  end
  local function chanceEligible(room, key, callback, bypassQuery)
    local previous = room[key]
    local previousBypass = directBypassQuery
    room[key] = true
    if bypassQuery then directBypassQuery = bypassQuery end
    local ok, result = pcall(callback, CurrentRun, room)
    room[key] = previous
    directBypassQuery = previousBypass
    if not ok then error(result, 0) end
    return result
  end
  local function isHubScene()
    local unit = hero()
    return type(CurrentDeathAreaRoom) == "table" or (unit ~= nil and unit.IsDead == true)
  end
  local function containsValue(list, target)
    if type(list) ~= "table" then return false end
    for _, value in pairs(list) do if value == target then return true end end
    return false
  end
  local function hasEligibleSecretDestination()
    if type(RoomSetData) ~= "table" or type(RoomSetData.Secrets) ~= "table" then return false end
    for _, entry in pairs(RoomSetData.Secrets) do
      if type(entry) == "table" and not entry.DebugOnly then return true end
    end
    return false
  end
  local function inspectFishing(room)
    if type(room) ~= "table" or isHubScene() then return false, "scene" end
    if type(GetInactiveIdsByType) ~= "function" or type(IsFishingEligible) ~= "function"
        or type(Activate) ~= "function" or type(GetRandomValue) ~= "function"
        or type(GetRunDepth) ~= "function" or type(UseHeroTraitsWithValue) ~= "function"
        or type(CheckRoomExitsReady) ~= "function" then
      return false, "native"
    end
    if room.CompletedFishing or room.FishingPointId ~= nil or room.ForceFishing then
      return false, "existing"
    end
    if room.PersistentFishing and type(CurrentRun.RoomCreations) == "table" and CurrentRun.RoomCreations[room.Name] then
      for _, past in pairs(CurrentRun.RoomHistory or {}) do
        if type(past) == "table" and past.Name == room.Name and past.CompletedFishing then
          return false, "existing"
        end
      end
    end
    if #GetInactiveIdsByType({ Name = "FishingPoint" }) == 0 then return false, "placement" end
    if chanceEligible(room, "FishingPointChanceSuccess", IsFishingEligible, "IsFishingEligible") then
      return true, nil
    end
    local req = type(room.FishingPointRequirements) == "table" and room.FishingPointRequirements or nil
    if req then
      if containsValue(req.RequiredCosmetics, "FishingUnlockItem")
          and type(GameState) == "table" and type(GameState.Cosmetics) == "table"
          and not GameState.Cosmetics.FishingUnlockItem then
        return false, "rod"
      end
      if type(req.RequiredMinRoomsSinceFishingPoint) == "number"
          and CurrentRun.LastFishingPointDepth ~= nil and type(CurrentRun.RunDepthCache) == "number"
          and CurrentRun.LastFishingPointDepth ~= CurrentRun.RunDepthCache
          and CurrentRun.RunDepthCache - req.RequiredMinRoomsSinceFishingPoint < CurrentRun.LastFishingPointDepth then
        return false, "spacing"
      end
    end
    return false, "progression"
  end
  local function canFish(room)
    local ok = inspectFishing(room)
    return ok
  end
  local function availableSecretPoints(allPoints)
    local points = allPoints or GetIdsByType({ Name = "SecretPoint" })
    local occupied, available = {}, {}
    for _, door in pairs(OfferedExitDoors or {}) do
      if door.Name == "SecretDoor" or door.Name == "ShrinePointDoor" then
        local point = GetClosest({ Id = door.ObjectId, DestinationIds = points })
        if point then occupied[point] = true end
      end
    end
    for _, point in ipairs(points) do
      if not occupied[point] then available[#available + 1] = point end
    end
    return available
  end
  local function inspectChaos(room, points)
    if type(room) ~= "table" or isHubScene() then return false, "scene" end
    if type(GetIdsByType) ~= "function" or type(IsSecretDoorEligible) ~= "function"
        or type(ChooseNextRoomData) ~= "function" or type(CreateRoom) ~= "function"
        or type(SpawnObstacle) ~= "function" or type(SetupObstacle) ~= "function"
        or type(AssignRoomToExitDoor) ~= "function" or type(GetSecretDoorCost) ~= "function"
        or type(UseHeroTraitsWithValue) ~= "function" or type(GetRunDepth) ~= "function"
        or type(CheckRoomExitsReady) ~= "function"
        or type(ObstacleData) ~= "table" or type(ObstacleData.SecretDoor) ~= "table"
        or type(RoomSetData) ~= "table" or type(RoomSetData.Secrets) ~= "table" then
      return false, "native"
    end
    if room.ForceSecretDoor then return false, "existing" end
    for _, door in pairs(OfferedExitDoors or {}) do
      if door.Name == "SecretDoor" then return false, "existing" end
    end
    if room.RoomSetName == "Secrets" or room.UsePreviousRoomSet or not hasEligibleSecretDestination() then
      return false, "route"
    end
    local allPoints = GetIdsByType({ Name = "SecretPoint" })
    if #allPoints == 0 then return false, "placement" end
    local free = points or availableSecretPoints(allPoints)
    if #free == 0 then return false, "occupied" end
    local forcedByHero = type(HasHeroTraitValue) == "function" and HasHeroTraitValue("ForceSecretDoor")
    if type(room.SecretSpawnChance) == "number" and room.SecretSpawnChance == 0 and not forcedByHero then
      return false, "room"
    end
    if chanceEligible(room, "SecretChanceSuccess", IsSecretDoorEligible, "IsSecretDoorEligible") then
      return true, nil
    end
    local req = type(room.SecretDoorRequirements) == "table" and room.SecretDoorRequirements or nil
    if req and not forcedByHero and type(req.RequiredMinRoomsSinceSecretDoor) == "number"
        and CurrentRun.LastSecretDepth ~= nil and type(CurrentRun.RunDepthCache) == "number"
        and CurrentRun.LastSecretDepth ~= CurrentRun.RunDepthCache
        and CurrentRun.RunDepthCache - req.RequiredMinRoomsSinceSecretDoor < CurrentRun.LastSecretDepth then
      return false, "spacing"
    end
    return false, "progression"
  end
  local function canChaos(room, points)
    local ok = inspectChaos(room, points)
    return ok
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
  local function challengeSwitchAvailable(room)
    if type(EncounterSets) == "table" and type(EncounterSets.ChallengeOptions) == "table" then
      if type(ObstacleData) ~= "table" then return false end
      local eligibleOption = false
      for _, name in pairs(EncounterSets.ChallengeOptions) do
        local data = ObstacleData[name]
        if type(data) == "table" and (data.Requirements == nil
            or (type(IsGameStateEligible) == "function"
              and IsGameStateEligible(CurrentRun, data, data.Requirements))) then
          eligibleOption = true
          break
        end
      end
      if not eligibleOption then return false end
    end
    if type(ChooseChallengeEncounter) == "function" then
      if type(room.ChallengeEncounterName) ~= "string" or type(EncounterData) ~= "table"
          or type(EncounterData[room.ChallengeEncounterName]) ~= "table" then
        return false
      end
    end
    return true
  end
  local function canGenerate(room, kind)
    local owner = objectOwners[kind]
    if room[owner.field] then return false end
    local count = #freePedestals(room, GetIdsByType({ Name = "ChallengeSwitchBase" }))
    if count == 0 then return false end
    local callback = _G[owner.query]
    if kind == "trove" then
      local reserved = ((not room.WellShop and room.ForceWellShop) and 1 or 0)
        + ((not room.SellTraitShop and room.ForceSellTraitShop) and 1 or 0)
      if count <= reserved or not challengeSwitchAvailable(room) then return false end
      return chanceEligible(room, owner.chance, function(run) return callback(run) end)
    end
    return chanceEligible(room, owner.chance, callback)
  end
  local function clearDoorPreview(door)
    local ids, seen = {}, {}
    local function include(id)
      if id and not seen[id] then ids[#ids + 1] = id; seen[id] = true end
    end
    include(door.DoorIconId); include(door.DoorIconFront); include(door.DoorIconBackingId)
    for _, id in pairs(door.AdditionalIcons or {}) do include(id) end
    for _, id in pairs(door.AdditionalAttractIds or {}) do include(id) end
    if #ids > 0 then Destroy({ Ids = ids }) end
    door.AdditionalIcons = {}; door.AdditionalAttractIds = {}
  end
  local function drawDoorPreview(door, room)
    local actual = door.Room
    clearDoorPreview(door)
    door.Room = room
    local ok, result = pcall(CreateDoorRewardPreview, door)
    door.Room = actual
    if not ok then
      clearDoorPreview(door)
      pcall(CreateDoorRewardPreview, door)
      error(result, 0)
    end
  end
  local function refreshDoor(door, room)
    clearDoorPreview(door)
    AssignRoomToExitDoor(door, room)
    CreateDoorRewardPreview(door)
  end
  activeEdit = function(door)
    local edit = edits[door]
    if type(edit) ~= "table" then return nil end
    if edit.run ~= CurrentRun or edit.hero ~= hero()
        or edit.sourceRoom ~= currentRoom() then
      edits[door] = nil
      return nil
    end
    local identityChanged = edit.physicalToken ~= physicalDoorId(door)
    local rewardChanged = edit.signature ~= rewardSignature(door.Room)
    if edit.kind == "route" then
      identityChanged = identityChanged or edit.original ~= door.Room
    elseif edit.kind == "reward" then
      identityChanged = identityChanged or edit.applied ~= door.Room
      rewardChanged = edit.appliedSignature ~= rewardSignature(door.Room)
    else
      identityChanged = true
    end
    if identityChanged or rewardChanged then
      edits[door] = nil
      -- A native mutation can restore the exact old reward fields. Never
      -- allow its previously issued token to become valid again.
      doorEpochs[door] = (doorEpochs[door] or 0) + 1
      return nil
    end
    return edit
  end
  local rewardFields = {
    "Reward", "ChosenRewardType", "ForceLootName", "RewardStoreName",
    "RewardOverrides", "Encounter", "OriginalChosenRewardType", "OriginalForceLootName",
    "DeferReward", "NoReward", "ForcedReward", "ForcedFirstReward",
  }
  local function snapshotReward(door, roomID, target, leaseToken)
    local source = currentRoom()
    local offered = type(source.OfferedRewards) == "table" and source.OfferedRewards or nil
    local room = door.Room
    local edit = {
      kind = "reward", original = room, applied = room, room = roomID, rewardID = target, target = target,
      leaseToken = leaseToken, doorToken = doorId(door),
      physicalToken = physicalDoorId(door),
      originalCanBeRerolled = door.CanBeRerolled,
      originalOfferedRewardsPresent = offered ~= nil,
      originalOfferedReward = offered and offered[door.ObjectId] or nil,
      fields = {}, run = CurrentRun, hero = hero(), sourceRoom = source,
    }
    for _, field in ipairs(rewardFields) do
      edit.fields[field] = { value = room[field] }
    end
    return edit
  end
  local function restoreReward(door, edit)
    local room = door.Room
    for _, field in ipairs(rewardFields) do
      room[field] = edit.fields[field].value
    end
    refreshDoor(door, room)
    door.CanBeRerolled = edit.originalCanBeRerolled
    if type(RefreshUseButton) == "function" then RefreshUseButton(door.ObjectId, door) end
    local source = edit.sourceRoom
    local offered = type(source.OfferedRewards) == "table" and source.OfferedRewards or nil
    if edit.originalOfferedRewardsPresent and not offered then
      offered = {}
      source.OfferedRewards = offered
    end
    if offered then
      offered[door.ObjectId] = edit.originalOfferedReward
      if not edit.originalOfferedRewardsPresent and next(offered) == nil then
        source.OfferedRewards = nil
      end
    end
  end
  -- A reserved category has no concrete room/reward until native door use.
  -- When a specific reward was chosen with the room type, project that reward;
  -- otherwise render a supported generic native preview without drawing RNG.
  local function routePreviewDescriptor(door, route, reward)
    local proxy = DeepCopyTable(door.Room)
    proxy.Reward = nil
    proxy.ChosenRewardType = nil
    proxy.ForceLootName = nil
    proxy.RewardStoreName = nil
    proxy.RewardOverrides = nil
    proxy.RewardPreviewIcon = nil
    proxy.RewardPreviewFx = nil
    proxy.RewardPreviewOverride = nil
    proxy.Encounter = nil
    proxy.OriginalChosenRewardType = nil
    proxy.OriginalForceLootName = nil
    proxy.NextRoomSet = nil
    if type(reward) == "table" then
      proxy.ChosenRewardType = reward.rewardType
      proxy.ForceLootName = reward.forceLoot
      proxy.RewardStoreName = reward.store
      proxy.RewardOverrides = reward.overrides and DeepCopyTable(reward.overrides) or nil
      return proxy
    end
    if route == "shop" then
      proxy.ChosenRewardType = "Shop"
    elseif route ~= "story" then
      -- The native preview treats a truthy NextRoomSet as a neutral ExitPreview.
      -- This is a presentation-only proxy, never written to the exit graph.
      proxy.NextRoomSet = {}
    end
    return proxy
  end
  local function reserveRoute(door, route, reward, leaseToken)
    assert(activeEdit(door) == nil, "hades.error.staleDoor")
    local routes = routeCandidatesWithDiagnostics(door)
    local candidates = routeRooms(routes and routes[route])
    assert(candidates and #candidates > 0, "hades.error.worldUnavailable")
    beginWorldMutation()
    -- Only present the chosen reward or native generic category icon; candidate
    -- selection and room generation are reserved for authorized native departure.
    drawDoorPreview(door, routePreviewDescriptor(door, route, reward))
    edits[door] = {
      kind = "route", route = route, room = route,
      reward = reward, rewardID = reward and reward.id or nil,
      target = route, leaseToken = leaseToken,
      original = door.Room, run = CurrentRun, hero = hero(), sourceRoom = currentRoom(),
      physicalToken = physicalDoorId(door), signature = rewardSignature(door.Room),
    }
  end
  local function clearSourceEdits(source, selectedDoor)
    for door, edit in pairs(edits) do
      if type(edit) == "table" and edit.sourceRoom == source then
        -- Native departure has already accepted the door, sometimes paying
        -- a cost. Revoke each lease before restoring unused sibling previews;
        -- an icon or button callback failure cannot strand the transition.
        local restore = door ~= selectedDoor and activeEdit(door) == edit
        edits[door] = nil
        if restore then
          local ok, err = pcall(function()
            if edit.kind == "reward" then
              restoreReward(door, edit)
            elseif edit.kind == "route" then
              drawDoorPreview(door, door.Room)
            end
          end)
          if not ok then runtime.worldRouteFailure = tostring(err) end
        end
      end
    end
  end
  local function definition(name)
    local data = runtime.worldDefinitions and runtime.worldDefinitions[name]
    assert(data, "hades.error.invalidValue")
    return data
  end
  local function rewardSourceEligible(data)
    if data.kind ~= "loot" then return true end
    if type(LootData) ~= "table" or type(IsGameStateEligible) ~= "function" then return true end
    local ok, eligible, usedRandom = pcall(nativeEligibilityProbe, IsGameStateEligible, false, CurrentRun, LootData[data.id])
    if not ok or usedRandom then return false end
    return eligible == true
  end
  local function rewardDataPresent(data)
    if data.kind == "loot" then
      return type(LootData) == "table" and type(LootData[data.id]) == "table"
    end
    return type(ConsumableData) ~= "table"
      or type(ConsumableData[data.id]) == "table"
      or type(ConsumableData[data.rewardType .. "RunProgress"]) == "table"
  end
  local function rewardCandidatesWithDiagnostics(door, diagnostics)
    diagnostics = diagnostics or {}
    local room = type(door) == "table" and door.Room or nil
    if type(room) ~= "table" then
      diagnostics.reason = "exit_room_unavailable"
      return {}
    end
    local src = currentRoom() or {}
    local locked = room.NoReward and "room_no_reward"
      or ((src.DeferReward or room.DeferReward) and "room_reward_deferred")
      or ((room.ForcedReward ~= nil or room.ForcedFirstReward ~= nil) and "room_has_forced_reward")
      or ((room.ChosenRewardType == "Story" or room.ChosenRewardType == "Shop"
        or room.ChosenRewardType == "Empty" or room.ChosenRewardType == "Devotion")
        and "room_has_fixed_reward_category") or nil
    local sName = room.RewardStoreName
    local live = type(CurrentRun) == "table" and type(CurrentRun.RewardStores) == "table" and CurrentRun.RewardStores or nil
    local curStore = (live and type(sName) == "string" and sName ~= "") and live[sName] or nil
    if locked == nil and live ~= nil then
      if type(sName) ~= "string" or sName == "" then locked = "reward_store_name_missing"
      elseif type(curStore) ~= "table" then locked = "reward_store_unavailable" end
    end
    diagnostics.roomWarning = locked

    local prev, exclGods, sibGods = {}, {}, {}
    if type(src.OfferedRewards) == "table" then
      for objId, off in pairs(src.OfferedRewards) do
        if objId ~= door.ObjectId and type(off) == "table" and type(off.Type) == "string" then
          prev[#prev + 1] = { RewardType = off.Type, ForceLootName = off.ForceLootName }
          if off.Type == "Boon" and type(off.ForceLootName) == "string" then
            exclGods[#exclGods + 1] = off.ForceLootName; sibGods[off.ForceLootName] = true
          end
        end
      end
    end

    local godKnown, godReason, eligGods, godLimit = false, nil, {}, false
    if type(GetEligibleLootNames) == "function" then
      local ok, names, rnd = pcall(nativeEligibilityProbe, GetEligibleLootNames, false, exclGods)
      if ok and type(names) == "table" and not rnd then
        godKnown = true; for _, n in pairs(names) do eligGods[n] = true end
      else godReason = rnd and "god_eligibility_requires_rng" or "god_eligibility_unavailable" end
    end
    if type(ReachedMaxGods) == "function" then
      local ok, lim, rnd = pcall(nativeEligibilityProbe, ReachedMaxGods, false, exclGods)
      godLimit = ok and not rnd and lim == true
    end

    local tiers, seen = {}, {}
    local function addTier(st, n, sk)
      if type(st) == "table" and not seen[st] then seen[st] = true; tiers[#tiers + 1] = { store = st, name = n, sk = sk } end
    end
    if type(curStore) == "table" then addTier(curStore, sName, "current") end
    if type(RewardStoreData) == "table" then
      if type(sName) == "string" and sName ~= "" then addTier(RewardStoreData[sName], sName, "reference") end
      local names = {}
      for n, st in pairs(RewardStoreData) do
        if type(n) == "string" and type(st) == "table" and n ~= "InvalidOverrides" and n ~= sName then names[#names + 1] = n end
      end
      table.sort(names)
      for _, n in ipairs(names) do addTier(RewardStoreData[n], n, "other") end
    end

    local roomProbe, cache = copyTbl(room), {}
    local function probeEntry(e)
      if cache[e] then return cache[e] end
      local r
      if type(IsRoomRewardEligible) ~= "function" then r = { ok = true, eligible = true, usedRandom = false, unavailable = true }
      else
        local ok, el, rnd = pcall(nativeEligibilityProbe, IsRoomRewardEligible, false, CurrentRun, roomProbe, copyTbl(e), prev, { Door = door })
        r = { ok = ok, eligible = el == true, usedRandom = rnd == true }
      end
      cache[e] = r; return r
    end
    local curElig = 0
    if type(curStore) == "table" then
      for _, e in ipairs(curStore) do
        if type(e) == "table" then local p = probeEntry(e); if p.ok and not p.usedRandom and p.eligible then curElig = curElig + 1 end end
      end
    end

    local ids = {}
    for rid, d in pairs(runtime.worldDefinitions or {}) do if d.doorAllowed and rewardDataPresent(d) then ids[#ids + 1] = rid end end
    table.sort(ids)
    local out = {}
    for _, rid in ipairs(ids) do
      local d = runtime.worldDefinitions[rid]
      local upg = d.rewardType .. "RunProgress"
      local prefUpg = type(GameState) == "table" and type(GameState.Cosmetics) == "table" and GameState.Cosmetics[upg] == true
      local best, bestScore, sawErr = nil, 99, false
      for _, t in ipairs(tiers) do
        for _, e in ipairs(t.store) do
          if type(e) == "table" and (e.Name == d.rewardType or e.Name == upg) then
            local p = probeEntry(e)
            if not p.ok then sawErr = true
            else
              local w = nil
              if p.unavailable then w = "reward_eligibility_unavailable"
              elseif p.usedRandom then w = "reward_eligibility_requires_rng"
              elseif not p.eligible then
                if rid == "HermesUpgrade" then w = "god_not_eligible"
                elseif d.rewardType == "Boon" then
                  if sibGods[rid] then w = "reward_not_available"
                  elseif type(GetEligibleLootNames) == "function" then
                    w = not godKnown and (godReason or "god_eligibility_unavailable")
                      or (not eligGods[rid] and (godLimit and "god_limit" or "god_not_eligible") or "reward_not_eligible")
                  else w = not rewardSourceEligible(d) and "god_not_eligible" or "reward_not_eligible" end
                else w = "reward_not_eligible" end
              elseif d.rewardType == "Boon" then
                if sibGods[rid] then w = "reward_not_available"
                elseif type(GetEligibleLootNames) == "function" then
                  if not godKnown then w = godReason or "god_eligibility_unavailable"
                  elseif not eligGods[rid] then w = godLimit and "god_limit" or "god_not_eligible" end
                elseif not rewardSourceEligible(d) then w = "god_not_eligible" end
              elseif rid == "HermesUpgrade" and not rewardSourceEligible(d) then w = "god_not_eligible" end
              if w == nil and ((t.sk == "other" and (type(curStore) == "table" or (type(sName) == "string" and sName ~= "")))
                  or (t.sk == "reference" and curElig > 0)) then w = "reward_not_in_current_store" end
              local pref = (prefUpg and e.Name == upg) or (not prefUpg and e.Name == d.rewardType)
              local score = (w == nil and 0 or 2) + (pref and 0 or 1)
              if score < bestScore then
                bestScore = score
                best = { id = rid, rewardType = e.Name or d.rewardType, forceLoot = d.rewardType == "Boon" and rid or nil,
                  store = t.name, overrides = e.Overrides, reward = e, enabled = true, warning = w }
              end
            end
          end
        end
      end
      if best then out[#out + 1] = best
      elseif sawErr then out[#out + 1] = { id = rid, enabled = false, reason = "reward_eligibility_probe_error" } end
    end
    return out
  end
  local function rewardCandidate(door, target)
    for _, candidate in ipairs(rewardCandidatesWithDiagnostics(door)) do
      if candidate.id == target and candidate.enabled then return candidate end
    end
    return nil
  end
  local function applyRewardEdit(door, roomID, candidate, leaseToken)
    -- Prepare the native reward on a descriptor clone first. Committing the
    -- reward fields in-place preserves the exact physical target-room owner.
    local room = door.Room
    local prepared = DeepCopyTable(room)
    prepared.ChosenRewardType = candidate.rewardType
    prepared.ForceLootName = candidate.forceLoot
    prepared.RewardStoreName = candidate.store
    prepared.RewardOverrides = candidate.overrides and DeepCopyTable(candidate.overrides) or nil
    prepared.Encounter = nil
    prepared.OriginalChosenRewardType = nil; prepared.OriginalForceLootName = nil
    prepared.DeferReward = nil; prepared.NoReward = nil
    prepared.ForcedReward = nil; prepared.ForcedFirstReward = nil
    SetupRoomReward(CurrentRun, prepared, nil, { IgnoreForceLootName = true })
    local edit = snapshotReward(door, roomID, candidate.id, leaseToken)
    beginWorldMutation()
    for _, field in ipairs(rewardFields) do room[field] = prepared[field] end
    edit.appliedSignature = rewardSignature(room)
    edits[door] = edit
    refreshDoor(door, room)
  end
  local function materializeRoute(door, edit)
    assert(edit == activeEdit(door) and edit.kind == "route", "hades.error.staleDoor")
    local routes = routeCandidatesWithDiagnostics(door)
    local candidates = routeRooms(routes and routes[edit.route])
    assert(candidates and #candidates > 0, "hades.error.worldUnavailable")
    local room = CreateRoom(GetRandomValue(candidates), {
      SkipChooseEncounter = true,
      SkipChooseReward = edit.reward ~= nil,
    })
    assert(type(room) == "table", "hades.error.outcomeUnknown")
    if type(edit.reward) == "table" then
      room.ChosenRewardType = edit.reward.rewardType
      room.ForceLootName = edit.reward.forceLoot
      room.RewardStoreName = edit.reward.store
      room.RewardOverrides = edit.reward.overrides and DeepCopyTable(edit.reward.overrides) or nil
      room.DeferReward = nil
      room.NoReward = nil
      room.ForcedReward = nil
      room.ForcedFirstReward = nil
      if type(SetupRoomReward) == "function" then
        SetupRoomReward(CurrentRun, room, nil, { IgnoreForceLootName = true })
      end
    end
    edits[door] = nil
    AssignRoomToExitDoor(door, room)
    return room
  end
  local api = {}
  function api.install()
    for _, name in ipairs({ "IsSecretDoorEligible", "IsShrinePointDoorEligible", "IsChallengeSwitchEligible",
        "IsWellShopEligible", "IsSellTraitShopEligible", "IsFishingEligible" }) do
      local queryName = name
      hook(name, function(original)
        return function(...)
          if spawnContext and queryName ~= spawnContext.query then return false end
          if directBypassQuery ~= queryName and queryName == "IsSecretDoorEligible" then
            local run, room = ...
            local captured = type(room) == "table" and chaosRooms[room] or nil
            if captured and captured.run == CurrentRun and run == CurrentRun
                and room == CurrentRun.CurrentRoom and captured.hero == hero()
                and not room.ForceSecretDoor then
              if captured.probability == 0 then return false end
              if (captured.probability or 0) > 0 then
                if not hasEligibleSecretDestination() or #availableSecretPoints() == 0 then return false end
              end
            end
          end
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
    hook("CreateRoom", function(original)
      return function(data, args, ...)
        local pending = occurrencePendingRoom
        local matching = pending and pending.run == CurrentRun and pending.hero == hero()
          and pending.sourceRoom == currentRoom()
          and (pending.chosen == data or type(pending.chosen) == "string"
            and type(data) == "table" and pending.chosen == data.Name)
        if matching then occurrencePendingRoom = nil end
        local previous = occurrenceGeneration
        occurrenceGeneration = {
          run = CurrentRun, hero = hero(), sourceRoom = currentRoom(),
          roomName = type(data) == "table" and data.Name or nil,
        }
        local fishingPct = type(CurrentRun) == "table" and type(data) == "table" and runtime.fishingChance or nil
        local chaosPct = type(CurrentRun) == "table" and type(data) == "table" and runtime.chaosGateChance or nil
        local overrides = type(args) == "table" and type(args.RoomOverrides) == "table" and args.RoomOverrides or nil
        local baseData = type(RoomData) == "table" and RoomData.BaseRoom or nil
        local origSecret = overrides and overrides.SecretSpawnChance
        if origSecret == nil and type(data) == "table" then origSecret = data.SecretSpawnChance end
        local origFishing = overrides and overrides.FishingPointChance
        if origFishing == nil and type(data) == "table" then origFishing = data.FishingPointChance end
        local baseSecret = origSecret ~= nil and origSecret or (baseData and baseData.SecretSpawnChance)
        local baseFishing = origFishing ~= nil and origFishing or (baseData and baseData.FishingPointChance)
        local applyChaos = chaosPct ~= nil and data.RoomSetName ~= "Secrets" and not data.UsePreviousRoomSet
          and (baseSecret == nil or baseSecret > 0)
        local applyFishing = fishingPct ~= nil and (baseFishing == nil or baseFishing > 0)
        local callArgs = args
        if applyChaos or applyFishing then
          callArgs = type(args) == "table" and copyTbl(args) or {}
          local callOverrides = type(callArgs.RoomOverrides) == "table" and copyTbl(callArgs.RoomOverrides) or {}
          local secretMult, fishingMult = 1, 1
          for _, mutator in pairs(type(GameState) == "table" and GameState.ActiveMutators or {}) do
            if type(mutator) == "table" then
              if finite(mutator.SecretSpawnChanceMultiplier) then secretMult = secretMult * mutator.SecretSpawnChanceMultiplier end
              if finite(mutator.FishingPointChanceMultiplier) then fishingMult = fishingMult * mutator.FishingPointChanceMultiplier end
            end
          end
          local fishingBonus = type(GetTotalHeroTraitValue) == "function" and (GetTotalHeroTraitValue("FishingPointChanceBonus") or 0) or 0
          if applyChaos and secretMult > 0 then
            callOverrides.SecretSpawnChance = (chaosPct == 0 and -1 or (chaosPct / 100)) / secretMult
          end
          if applyFishing and fishingMult > 0 then
            callOverrides.FishingPointChance = ((fishingPct == 0 and -1 or (fishingPct / 100)) - fishingBonus) / fishingMult
          end
          callArgs.RoomOverrides = callOverrides
        end
        local result = table.pack(pcall(original, data, callArgs, ...))
        if type(args) == "table" and type(callArgs) == "table" then
          args.RewardStoreName = callArgs.RewardStoreName
        end
        occurrenceGeneration = previous
        if not result[1] then error(result[2], 0) end
        if type(result[2]) == "table" then
          local created = result[2]
          if applyChaos then
            created.SecretSpawnChance = origSecret
            if chaosPct == 0 then created.SecretChanceSuccess = false end
          end
          if applyFishing then
            created.FishingPointChance = origFishing
            if fishingPct == 0 then created.FishingPointChanceSuccess = false end
          end
          if chaosPct ~= nil then
            chaosRooms[created] = { probability = chaosPct, run = CurrentRun, hero = hero() }
          end
          if matching then
            occurrenceSelectedRooms[created] = {
              run = pending.run, hero = pending.hero, sourceRoom = pending.sourceRoom,
              leaseToken = pending.leaseToken,
            }
          end
        end
        return table.unpack(result, 2, result.n)
      end
    end)
    hook("AssignRoomToExitDoor", function(original)
      return function(door, room, ...)
        local previous = type(door) == "table" and door.Room or nil
        local result = table.pack(original(door, room, ...))
        if type(previous) == "table" and previous ~= room then
          occurrenceSelectedRooms[previous] = nil
        end
        local selected = occurrenceSelectedRooms[room]
        if selected then selected.door = door end
        return table.unpack(result, 1, result.n)
      end
    end)
    hook("ChooseNextRoomData", function(original)
      return function(...)
        return occurrenceChoose("room", original, ...)
      end
    end)
    hook("IsRoomForced", function(original)
      return function(...)
        return occurrenceObserveForced("room", original, ...)
      end
    end)
    hook("ChooseEncounter", function(original)
      return function(run, room, ...)
        if not liveEncounterRoom(run, room) then return original(run, room, ...) end
        return occurrenceChoose("encounter", original, run, room, ...)
      end
    end)
    hook("IsEncounterForced", function(original)
      return function(...)
        return occurrenceObserveForced("encounter", original, ...)
      end
    end)
    hook("GetRandomValue", function(original)
      return function(...)
        return occurrenceRandom(original, ...)
      end
    end)
    hook("RecordEncounter", function(original)
      return function(run, encounter, ...)
        local request = validOccurrence()
        local target = request and request.target
        local token = request and request.leaseToken
        local definition = target and occurrenceTargets[target]
        local result = table.pack(original(run, encounter, ...))
        if run == CurrentRun and token and occurrenceEncounterMatches(definition, encounter) then
          consumeOccurrence(target, token)
        end
        return table.unpack(result, 1, result.n)
      end
    end)
    hook("LeaveRoom", function(original)
      return function(run, door, ...)
        local source = currentRoom()
        local edit = activeEdit(door)
        if edit and edit.kind == "route" then
          -- Native AttemptUseDoor can already have spent money or health. A
          -- failed late CreateRoom/Assign must therefore leave via the original
          -- game-generated destination instead of aborting the transition.
          -- Native RNG/creation counts are deliberately never rewound.
          local originalRoom = door.Room
          local graph = {}
          for _, field in ipairs({ "OfferedRewards", "ExitDoorRooms" }) do
            local map = type(source[field]) == "table" and source[field] or nil
            graph[field] = { existed = map ~= nil, owner = map,
              value = map and map[door.ObjectId] or nil }
          end
          local ok, err = pcall(function()
            assert(run == CurrentRun and edit.run == run and edit.sourceRoom == source,
              "hades.error.staleDoor")
            materializeRoute(door, edit)
          end)
          if not ok then
            door.Room = originalRoom
            for field, snapshot in pairs(graph) do
              local map = type(source[field]) == "table" and source[field] or nil
              if map == nil and snapshot.existed then
                map = snapshot.owner
                source[field] = map
              end
              if map ~= nil then
                map[door.ObjectId] = snapshot.value
                if not snapshot.existed and next(map) == nil then source[field] = nil end
              end
            end
            edits[door] = nil
            runtime.worldRouteFailure = tostring(err)
            if type(DebugPrint) == "function" then
              pcall(DebugPrint, { Text = "MGT Hades route fallback: " .. tostring(err) })
            end
          else
            runtime.worldRouteFailure = nil
          end
        end
        clearSourceEdits(source, door)
        local request = validOccurrence()
        local target = request and request.target
        local token = request and request.leaseToken
        local definition = target and occurrenceTargets[target]
        local result = table.pack(original(run, door, ...))
        if run == CurrentRun and token and occurrenceRoomMatches(definition, door.Room) then
          consumeOccurrence(target, token)
        end
        if occurrencePendingRoom and occurrencePendingRoom.sourceRoom == source then
          occurrencePendingRoom = nil
        end
        for room, selected in pairs(occurrenceSelectedRooms) do
          if selected.sourceRoom == source then occurrenceSelectedRooms[room] = nil end
        end
        return table.unpack(result, 1, result.n)
      end
    end)
  end
  function api.clearPending()
    occurrenceRequest = nil
    occurrenceSelection = nil
    occurrenceGeneration = nil
    clearOccurrenceRoomSelections()
    local source = currentRoom()
    local unit = hero()
    local failure
    for door, edit in pairs(edits) do
      local owned = type(edit) == "table" and edit.run == CurrentRun
        and edit.hero == unit and edit.sourceRoom == source
      local valid = owned and activeEdit(door) == edit
      if valid then
        local ok, err = pcall(function()
          if edit.kind == "reward" then
            restoreReward(door, edit)
          elseif edit.kind == "route" then
            drawDoorPreview(door, door.Room)
          end
        end)
        if not ok and failure == nil then failure = err end
      end
      edits[door] = nil
    end
    if failure ~= nil then error(failure, 0) end
  end
  function api.observation()
    local room = currentRoom()
    if not room then return nil end
    local doors = array()
    for _, door in pairs(OfferedExitDoors or {}) do
      if ordinaryDoor(door) then
        local routeDiagnostics = {}
        local routes = routeCandidatesWithDiagnostics(door, routeDiagnostics)
        local edit = activeEdit(door)
        local targets = array()
        local rewardDiagnostics = {}
        for _, candidate in ipairs(rewardCandidatesWithDiagnostics(door, rewardDiagnostics)) do
          local target = {
            kind = "reward",
            id = candidate.id,
            enabled = candidate.enabled,
          }
          if candidate.reason then target.reason = candidate.reason end
          if candidate.warning then target.warning = candidate.warning end
          targets[#targets + 1] = target
        end
        local currentKind = routeKind(door.Room.Name)
        local currentListed = false
        for _, kind in ipairs(type(routes) == "table" and routeOrder or {}) do
          local bucket = routes[kind]
          if bucket ~= nil then
            local rooms = routeRooms(bucket)
            local enabled = type(rooms) == "table" and #rooms > 0
            local acceptsReward = kind == "combat" or kind == "miniboss"
            local target = {
              kind = "roomCategory",
              id = kind,
              enabled = enabled,
              acceptsReward = acceptsReward,
            }
            if not enabled then
              target.reason = bucket.probeErrors > 0 and "room_eligibility_probe_error" or "no_room_route"
            else
              local warning = routeWarning(bucket, door, routeDiagnostics)
              if warning then target.warning = warning end
            end
            targets[#targets + 1] = target
            if enabled and acceptsReward and (kind == currentKind or kind == door.Room.Name) then
              currentListed = true
            end
          end
        end
        if not currentListed then
          targets[#targets + 1] = {
            kind = "roomCategory",
            id = "current",
            enabled = true,
            acceptsReward = true,
          }
        end
        local lease
        if edit and edit.leaseToken then
          lease = {
            room = edit.room,
            reward = edit.rewardID,
            leaseToken = edit.leaseToken,
          }
        end
        doors[#doors + 1] = {
          id = doorId(door),
          doorToken = doorId(door),
          number = door.ObjectId,
          roomName = door.Room.Name or "",
          roomKind = currentKind or "",
          reward = door.Room.ForceLootName or door.Room.ChosenRewardType or "",
          rewardWarning = rewardDiagnostics.roomWarning,
          targets = targets,
          activeLease = lease,
        }
      end
    end
    table.sort(doors, function(a, b) return a.number < b.number end)
    local objects = array()
    if type(HandleSecretSpawns) == "function" then
      for _, kind in ipairs({ "trove", "well", "purge" }) do
        if canGenerate(room, kind) then objects[#objects + 1] = kind end
      end
    end
    local occurrenceList = array()
    for _, id in ipairs(occurrenceTargetOrder) do
      local definition = occurrenceTargets[id]
      occurrenceList[#occurrenceList + 1] = {
        id = id, kind = definition.kind, sourceId = definition.sourceId,
      }
    end
    local request = validOccurrence()
    local occurrence = request and {
      target = request.target, leaseToken = request.leaseToken,
    } or nil
    local fishOk, fishReason = inspectFishing(room)
    local chaosOk, chaosReason = inspectChaos(room)
    return {
      roomId = roomId(room), doors = doors,
      canFish = fishOk, fishingReason = fishReason,
      canChaos = chaosOk, chaosReason = chaosReason,
      objects = objects, occurrenceTargets = occurrenceList, occurrence = occurrence,
    }
  end
  function runtime.gain_resource(params)
    requireHero()
    assert(finite(params.amount) and params.amount >= 1 and params.amount <= 1000000
      and params.amount == math.floor(params.amount), "hades.error.invalidValue")
    if params.resource == "Money" then
      beginWorldMutation()
      AddMoney(params.amount, trainerFlag)
    else
      local allowed = false
      for _, name in ipairs(resourceNames) do if name == params.resource then allowed = true end end
      assert(allowed, "hades.error.invalidValue")
      beginWorldMutation()
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
      beginWorldMutation()
      if params.reward == "WeaponUpgrade" then
        CreateWeaponLoot({ SpawnPoint = unit.ObjectId, OffsetX = 100 })
      elseif params.reward == "StackUpgrade" then
        CreateStackLoot({ SpawnPoint = unit.ObjectId, OffsetX = 100 })
      else
        GiveLoot({ ForceLootName = params.reward, SpawnPoint = unit.ObjectId, OffsetX = 100 })
      end
    else
      assert(ConsumableData[params.reward], "hades.error.worldUnavailable")
      beginWorldMutation()
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
    beginWorldMutation()
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
    local points = availableSecretPoints()
    assert(canChaos(room, points), "hades.error.worldUnavailable")
    local data = ChooseNextRoomData(CurrentRun, { RoomDataSet = RoomSetData.Secrets })
    assert(data, "hades.error.worldUnavailable")
    local point = GetRandomValue(points)
    beginWorldMutation()
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
    beginWorldMutation()
    room[owner.chance] = true
    spawnContext = { room = room, query = owner.query }
    local ok, result = pcall(HandleSecretSpawns, CurrentRun)
    spawnContext = nil
    room[owner.chance] = previous
    if not ok then error("hades.error.outcomeUnknown: " .. tostring(result), 0) end
    local object = room[owner.field]
    assert(object, "hades.error.outcomeUnknown")
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
  function runtime.apply_world_exit(params)
    local door = requireDoor(params)
    assert(activeEdit(door) == nil and type(params.requestId) == "string",
      "hades.error.staleDoor")
    local roomID, rewardID = params.room, params.reward
    assert(type(roomID) == "string" and roomID ~= "", "hades.error.invalidValue")
    local rewardCandidateObj = nil
    if rewardID ~= nil then
      assert(type(rewardID) == "string" and rewardID ~= "", "hades.error.invalidValue")
      rewardCandidateObj = rewardCandidate(door, rewardID)
      assert(rewardCandidateObj, "hades.error.worldUnavailable")
    end
    local leaseToken = "exit:" .. params.requestId
    if rewardCandidateObj ~= nil and (roomID == "current" or roomID == door.Room.Name
        or roomID == routeKind(door.Room.Name)) then
      applyRewardEdit(door, roomID, rewardCandidateObj, leaseToken)
    else
      assert(roomID ~= "current", "hades.error.invalidValue")
      local routes = routeCandidatesWithDiagnostics(door)
      local candidates = routeRooms(routes and routes[roomID])
      assert(candidates and #candidates > 0, "hades.error.worldUnavailable")
      reserveRoute(door, roomID, rewardCandidateObj, leaseToken)
    end
    return runtime.status()
  end
  function runtime.cancel_world_exit(params)
    local door = requireDoor(params)
    local edit = activeEdit(door)
    assert(edit and edit.leaseToken == params.leaseToken, "hades.error.staleDoor")
    beginWorldMutation()
    if edit.kind == "reward" then
      restoreReward(door, edit)
    elseif edit.kind == "route" then
      drawDoorPreview(door, door.Room)
    end
    edits[door] = nil
    return runtime.status()
  end
  function runtime.apply_world_occurrence(params)
    requireRoom(params)
    assert(type(params.targetID) == "string" and occurrenceTargets[params.targetID],
      "hades.error.invalidValue")
    assert(validOccurrence() == nil and type(params.requestId) == "string",
      "hades.error.worldUnavailable")
    occurrenceRequest = {
      target = params.targetID,
      leaseToken = "occurrence:" .. params.requestId,
      run = CurrentRun,
      hero = requireHero(),
    }
    return runtime.status()
  end
  function runtime.cancel_world_occurrence(params)
    requireRoom(params)
    local request = validOccurrence()
    assert(request and request.leaseToken == params.leaseToken, "hades.error.staleTarget")
    occurrenceRequest = nil
    occurrenceSelection = nil
    clearOccurrenceRoomSelections()
    return runtime.status()
  end

  function api.canOpenSellTraits()
    local unit = hero()
    if unit == nil or unit.IsDead == true or isHubScene() or currentRoom() == nil then
      return false
    end
    if type(OpenSellTraitMenu) ~= "function" or type(thread) ~= "function" then
      return false
    end
    if type(ActiveScreens) == "table" and next(ActiveScreens) ~= nil then
      return false
    end
    if type(IsScreenOpen) == "function" and IsScreenOpen("SellTraitMenu") then
      return false
    end
    return true
  end
  function runtime.open_sell_traits()
    requireHero()
    assert(not isHubScene() and currentRoom() ~= nil, "hades.error.worldUnavailable")
    assert(type(OpenSellTraitMenu) == "function" and type(thread) == "function",
      "hades.error.sellDataUnavailable")
    if (type(ActiveScreens) == "table" and next(ActiveScreens) ~= nil)
        or (type(IsScreenOpen) == "function" and IsScreenOpen("SellTraitMenu")) then
      error("hades.error.sellScreenBusy", 0)
    end
    thread(OpenSellTraitMenu)
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
  assert(kind == "table", "hades.error.outcomeUnknown")
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
