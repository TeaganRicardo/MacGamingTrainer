local existing = rawget(_G, "MacGamingTrainerHades")
if existing then
  if existing.revision ~= 12 then error("hades.error.restartRequired") end
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
  version = 1, revision = 12,
  features = {}, hooks = {}, instanceIds = setmetatable({}, { __mode = "k" }),
  nextInstanceId = 0, propertyDepth = 0, rerollLeases = setmetatable({}, { __mode = "k" }),
  movementOwners = setmetatable({}, { __mode = "k" }),
  rerollDoors = setmetatable({}, { __mode = "k" }),
  boonRarityTarget = "Heroic",
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
    "hades.error.unsupportedRuntime")
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
    assert(type(AddOutgoingDamageModifier) == "function", "hades.error.unsupportedRuntime")
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
    assert(type(WeaponSets) == "table" and type(WeaponSets.HeroRushWeapons) == "table", "hades.error.unsupportedRuntime")
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
  hook("SetTraitsOnLoot", function(original)
    return function(loot, ...)
      if runtime.features.boonRarityEnabled and runtime.boonRarityTarget ~= "Common"
          and type(loot) == "table" and rarityLootNames[loot.Name] and not loot.ForceCommon
          and type(loot.RarityChances) == "table" then
        -- Native TraitScripts.lua selects the highest legal rarity whose chance
        -- succeeds. Raise only tiers at or below the configured minimum, leaving
        -- higher native odds (especially Legendary) untouched.
        local odds = loot.RarityChances
        local boosted = {}
        for key, value in pairs(odds) do boosted[key] = value end
        boosted.Rare = 1
        if runtime.boonRarityTarget == "Epic" or runtime.boonRarityTarget == "Heroic" then
          boosted.Epic = 1
        end
        if runtime.boonRarityTarget == "Heroic" then boosted.Heroic = 1 end
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
    healthLocked = healthLockValid(runtime.healthLock), healthLock = runtime.healthLock,
    moneyLocked = runtime.moneyLock ~= nil, moneyLock = runtime.moneyLock,
    rerollsLocked = runtime.rerollsLock ~= nil, rerollsLock = runtime.rerollsLock,
    features = features, activeFeatures = activeFeatures, dormantFeatures = dormantFeatures,
    boonRarityTarget = runtime.boonRarityTarget,
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
function runtime.set_boon_rarity(target)
  assert(target == "Common" or target == "Rare" or target == "Epic" or target == "Heroic",
    "hades.error.invalidValue")
  installHooks()
  runtime.boonRarityTarget = target
  return runtime.status()
end
function runtime.configure_locks(health, money, rerolls)
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
  installHooks()
  local unit = hero()
  local releasingHealth = health == nil and healthLockValid(runtime.healthLock)
  if releasingHealth then
    releaseHealthLock(unit)
  else
    runtime.healthLock = health and { current = health.current, max = health.max } or nil
  end
  runtime.moneyLock, runtime.rerollsLock = money, rerolls
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
  assert(name == "Money" and type(locked) == "boolean", "hades.error.invalidValue")
  if locked then
    assert(not runtime.features.moneyNoDecrease and finite(CurrentRun.Money),
      "hades.error.invalidValue")
    runtime.moneyLock = CurrentRun.Money
  else
    runtime.moneyLock = nil
  end
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
  local unit = hero()
  if healthLockValid(runtime.healthLock) then releaseHealthLock(unit)
  else runtime.healthLock = nil end
  runtime.moneyLock, runtime.rerollsLock = nil, nil
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
  suspendProperties(unit)
  if patroclus then
    -- PatroclusBuff's synchronous trait owner; its presentation yields first.
    AddTraitToHero({ TraitData = source })
  else addTraits(unit, name, rarity, level) end
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
  local occurrenceRequest
  local occurrenceSelection
  local occurrenceTargetOrder = {
    "npc:Sisyphus", "npc:Eurydice", "npc:Patroclus", "npc:Thanatos", "shop:Charon",
  }
  local occurrenceTargets = {
    ["npc:Sisyphus"] = { kind = "character", sourceId = "Sisyphus", rooms = { A_Story01 = true } },
    ["npc:Eurydice"] = { kind = "character", sourceId = "Eurydice", rooms = { B_Story01 = true } },
    ["npc:Patroclus"] = { kind = "character", sourceId = "Patroclus", rooms = { C_Story01 = true } },
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
    local token = params.doorToken or params.doorId
    for _, door in pairs(OfferedExitDoors or {}) do
      if ordinaryDoor(door) and doorId(door) == token then return door end
    end
    error("hades.error.staleDoor")
  end
  local function validOccurrence()
    local request = occurrenceRequest
    if type(request) ~= "table" or request.run ~= CurrentRun or request.hero ~= hero()
        or occurrenceTargets[request.target] == nil then
      occurrenceRequest = nil
      return nil
    end
    return request
  end
  local function occurrenceRoomMatches(definition, room)
    return type(definition) == "table" and type(definition.rooms) == "table"
      and type(room) == "table" and definition.rooms[room.Name] == true
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
    return true
  end
  local function occurrenceChoose(kind, original, ...)
    local request = validOccurrence()
    local definition = request and occurrenceTargets[request.target] or nil
    local hasTarget = kind == "room" and type(definition and definition.rooms) == "table"
      or kind == "encounter" and definition ~= nil
        and (type(definition.encounters) == "table" or definition.encounterSet ~= nil)
    if not hasTarget then return original(...) end
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
          local matched = selection.kind == "room" and occurrenceRoomMatches(definition, data)
            or selection.kind == "encounter" and occurrenceEncounterMatches(definition, data)
          if matched then choices[#choices + 1] = candidate end
        end
      end
      if #choices > 0 then return original(choices, ...) end
    end
    return original(pool, ...)
  end
  local function routeKind(name)
    if name:find("_Story", 1, true) then return "story" end
    if name:find("_Shop", 1, true) then return "shop" end
    if name:find("_Reprieve", 1, true) then return "reprieve" end
    if name:find("_MiniBoss", 1, true) then return "miniboss" end
    if name:find("_Combat", 1, true) then return "combat" end
  end
  local function couldBeForced(room, args)
    local randomChance, randomValue = RandomChance, GetRandomValue
    local randomInt, randomFloat = RandomInt, RandomFloat
    local usedRandom = false
    -- A read-only route probe must never advance the game's RNG. A positive
    -- native chance is treated as forced; any other random API use fails closed.
    RandomChance = function(chance)
      if type(chance) == "number" and chance > 0 then
        usedRandom = true
        return true
      end
      return false
    end
    GetRandomValue = function(values, ...)
      usedRandom = true
      if type(values) == "table" then return values[1] end
      return values
    end
    if type(randomInt) == "function" then
      RandomInt = function(minimum) usedRandom = true; return minimum end
    end
    if type(randomFloat) == "function" then
      RandomFloat = function(minimum) usedRandom = true; return minimum end
    end
    local ok, result = pcall(IsRoomForced, CurrentRun, CurrentRun.CurrentRoom, room, args or {})
    RandomChance, GetRandomValue = randomChance, randomValue
    if type(randomInt) == "function" then RandomInt = randomInt end
    if type(randomFloat) == "function" then RandomFloat = randomFloat end
    if not ok then error(result, 0) end
    return usedRandom or result
  end
  local function eligibleWithoutRandom(room, data, args)
    local randomChance, randomValue = RandomChance, GetRandomValue
    local randomInt, randomFloat = RandomInt, RandomFloat
    local usedRandom = false
    RandomChance = function(chance)
      if type(chance) == "number" and chance > 0 then usedRandom = true end
      return false
    end
    GetRandomValue = function(values, ...)
      usedRandom = true
      if type(values) == "table" then return values[1] end
      return values
    end
    if type(randomInt) == "function" then
      RandomInt = function(minimum) usedRandom = true; return minimum end
    end
    if type(randomFloat) == "function" then
      RandomFloat = function(minimum) usedRandom = true; return minimum end
    end
    local ok, result = pcall(IsRoomEligible, CurrentRun, room, data, args or {})
    RandomChance, GetRandomValue = randomChance, randomValue
    if type(randomInt) == "function" then RandomInt = randomInt end
    if type(randomFloat) == "function" then RandomFloat = randomFloat end
    if not ok then error(result, 0) end
    return not usedRandom and result
  end
  local function routeRooms(room, door)
    local result = {}
    local args = type(door) == "table" and door.ChooseRoomArgs or {}
    if type(args) ~= "table" then return end
    if room.NextRoomSet or room.NextRoomSetNoGenerate or room.UsePreviousRoomSet
        or room.LinkedRoom or room.LinkedRooms or room.LinkedRoomByPactLevel
        or room.ForceNextRoom or room.ForceNextRoomSet or room.NextRoomSetName
        or args.RoomDataSet or args.NextRoomSet or args.NextRoomSetNoGenerate
        or args.UsePreviousRoomSet or args.ForceNextRoom or args.ForceNextRoomSet
        or (type(door) == "table" and (door.ForceRoomName or door.ReturnToPreviousRoom
          or door.ReturnToPreviousRoomName or door.UsePreviousRoomSet)) then return end
    local roomSetName = args.RoomSetName or room.RoomSetName or "Tartarus"
    local roomSet = RoomSetData[roomSetName]
    if type(roomSet) ~= "table" then return end
    for name, data in pairs(roomSet) do
      if eligibleWithoutRandom(room, data, args) then
        if couldBeForced(data, args) then return end
        local kind = routeKind(name)
        if kind then
          result[kind] = result[kind] or {}
          table.insert(result[kind], data)
        end
      end
    end
    return result
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
  local function availableSecretPoints()
    local points = GetIdsByType({ Name = "SecretPoint" })
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
  local function canChaos(room, points)
    for _, door in pairs(OfferedExitDoors or {}) do
      if door.Name == "SecretDoor" then return false end
    end
    return #(points or availableSecretPoints()) > 0
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
  local function canModify(room, args)
    return not CurrentRun.CurrentRoom.DeferReward and not room.NoReward and not room.DeferReward
      and not room.ForcedReward and not room.ForcedFirstReward and not couldBeForced(room, args)
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
    door.CanBeRerolled = false
    AssignRoomToExitDoor(door, room)
    CreateDoorRewardPreview(door)
  end
  local function activeEdit(door)
    local edit = edits[door]
    if type(edit) ~= "table" or edit.run ~= CurrentRun or edit.hero ~= hero()
        or edit.sourceRoom ~= currentRoom() then
      edits[door] = nil
      return nil
    end
    if edit.kind == "route" then
      if edit.original ~= door.Room or edit.signature ~= doorId(door) then
        edits[door] = nil
        return nil
      end
    elseif edit.kind == "reward" then
      if edit.applied ~= door.Room or edit.signature ~= doorId(door) then
        edits[door] = nil
        return nil
      end
    else
      edits[door] = nil
      return nil
    end
    return edit
  end
  local function applyDoor(door, room, target, leaseToken)
    local edit = activeEdit(door)
    if not edit or edit.kind ~= "reward" then
      edit = {
        kind = "reward", original = door.Room, run = CurrentRun,
        hero = hero(), sourceRoom = currentRoom(),
      }
    end
    edit.target = target
    edit.leaseToken = leaseToken
    edit.applied = room; edits[door] = edit
    refreshDoor(door, room)
    edit.signature = doorId(door)
  end
  local function routePreviewDescriptor(door, candidates)
    local candidate
    for _, value in ipairs(candidates or {}) do
      if candidate == nil or tostring(value.Name) < tostring(candidate.Name) then candidate = value end
    end
    assert(candidate, "hades.error.worldUnavailable")
    local proxy = DeepCopyTable(door.Room)
    proxy.Name = candidate.Name or proxy.Name
    proxy.Reward = nil
    proxy.ChosenRewardType = candidate.ChosenRewardType or candidate.ForcedReward
    proxy.ForceLootName = candidate.ForceLootName
    proxy.RewardStoreName = candidate.RewardStoreName or candidate.IndividualRewardStore
      or candidate.ForcedRewardStore
    proxy.OriginalChosenRewardType = nil
    proxy.OriginalForceLootName = nil
    proxy.RewardPreviewIcon = candidate.RewardPreviewIcon
    proxy.RewardPreviewFx = candidate.RewardPreviewFx
    proxy.RewardOverrides = type(candidate.RewardOverrides) == "table"
      and DeepCopyTable(candidate.RewardOverrides) or nil
    return proxy
  end
  local function reserveRoute(door, route, leaseToken)
    assert(activeEdit(door) == nil, "hades.error.staleDoor")
    local routes = routeRooms(currentRoom(), door)
    local candidates = routes and routes[route]
    assert(candidates and #candidates > 0, "hades.error.worldUnavailable")
    -- CreateDoorRewardPreview owns the game's real exit presentation. Give it a
    -- read-only eligible RoomData proxy for this call, then restore door.Room.
    drawDoorPreview(door, routePreviewDescriptor(door, candidates))
    edits[door] = {
      kind = "route", route = route, target = route, leaseToken = leaseToken,
      original = door.Room, run = CurrentRun, hero = hero(), sourceRoom = currentRoom(),
      signature = doorId(door),
    }
  end
  local function clearSourceEdits(source)
    for door, edit in pairs(edits) do
      if type(edit) == "table" and edit.sourceRoom == source then edits[door] = nil end
    end
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
  local function applyRewardEdit(door, rewardId, leaseToken)
    local data = definition(rewardId)
    assert(data.doorAllowed and canModify(door.Room, door.ChooseRoomArgs), "hades.error.worldUnavailable")
    local reward, store = doorReward(door.Room, data)
    assert(reward, "hades.error.worldUnavailable")
    local room = DeepCopyTable(door.Room)
    room.ChosenRewardType = data.rewardType
    room.ForceLootName = data.rewardType == "Boon" and rewardId or nil
    room.RewardStoreName = store
    room.RewardOverrides = reward.Overrides and DeepCopyTable(reward.Overrides) or nil
    room.Encounter = nil
    room.OriginalChosenRewardType = nil; room.OriginalForceLootName = nil
    SetupRoomReward(CurrentRun, room, nil, { IgnoreForceLootName = true })
    applyDoor(door, room, rewardId, leaseToken)
  end
  local function materializeRoute(door, edit)
    assert(edit == activeEdit(door) and edit.kind == "route", "hades.error.staleDoor")
    local routes = routeRooms(edit.sourceRoom, door)
    local candidates = routes and routes[edit.route]
    assert(candidates and #candidates > 0, "hades.error.worldUnavailable")
    local room = CreateRoom(GetRandomValue(candidates), { SkipChooseEncounter = true })
    assert(type(room) == "table", "hades.error.unsupportedRuntime")
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
          assert(run == CurrentRun and edit.run == run and edit.sourceRoom == source,
            "hades.error.staleDoor")
          materializeRoute(door, edit)
        end
        local request = validOccurrence()
        local target = request and request.target
        local token = request and request.leaseToken
        local definition = target and occurrenceTargets[target]
        local result = table.pack(original(run, door, ...))
        if run == CurrentRun and token and occurrenceRoomMatches(definition, door.Room) then
          consumeOccurrence(target, token)
        end
        clearSourceEdits(source)
        return table.unpack(result, 1, result.n)
      end
    end)
  end
  function api.clearPending()
    occurrenceRequest = nil
    occurrenceSelection = nil
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
            refreshDoor(door, edit.original)
            if edit.originalCanBeRerolled ~= nil then
              door.CanBeRerolled = edit.originalCanBeRerolled
            end
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
        local routes = routeRooms(room, door)
        local edit = activeEdit(door)
        local targets = array()
        if routes and canModify(door.Room, door.ChooseRoomArgs) then
          local rewardIds = {}
          for rewardId, data in pairs(runtime.worldDefinitions or {}) do
            if data.doorAllowed and canModify(door.Room, door.ChooseRoomArgs)
              and doorReward(door.Room, data) then rewardIds[#rewardIds + 1] = rewardId end
          end
          table.sort(rewardIds)
          for _, rewardId in ipairs(rewardIds) do
            targets[#targets + 1] = { kind = "reward", id = rewardId }
          end
          for _, kind in ipairs({ "combat", "story", "shop", "reprieve", "miniboss" }) do
            if routes[kind] then targets[#targets + 1] = { kind = "roomCategory", id = kind } end
          end
        end
        local lease
        if edit and edit.leaseToken then
          lease = {
            kind = edit.kind == "route" and "roomCategory" or "reward",
            target = edit.target,
            leaseToken = edit.leaseToken,
          }
        end
        doors[#doors + 1] = { id = doorId(door), doorToken = doorId(door), number = door.ObjectId,
          roomName = door.Room.Name or "",
          reward = door.Room.ForceLootName or door.Room.ChosenRewardType or "",
          targets = targets, activeLease = lease }
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
    return {
      roomId = roomId(room), doors = doors, canFish = canFish(room), canChaos = canChaos(room),
      objects = objects, occurrenceTargets = occurrenceList, occurrence = occurrence,
    }
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
    local points = availableSecretPoints()
    assert(canChaos(room, points), "hades.error.worldUnavailable")
    local data = ChooseNextRoomData(CurrentRun, { RoomDataSet = RoomSetData.Secrets })
    assert(data, "hades.error.worldUnavailable")
    local point = GetRandomValue(points)
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
  function runtime.apply_world_exit(params)
    local door = requireDoor(params)
    assert(activeEdit(door) == nil and type(params.requestId) == "string",
      "hades.error.staleDoor")
    local leaseToken = "exit:" .. params.requestId
    if params.kind == "reward" then
      applyRewardEdit(door, params.targetID, leaseToken)
    elseif params.kind == "roomCategory" then
      assert(canModify(door.Room, door.ChooseRoomArgs), "hades.error.worldUnavailable")
      local routes = routeRooms(CurrentRun.CurrentRoom, door)
      local candidates = routes and routes[params.targetID]
      assert(candidates and #candidates > 0, "hades.error.worldUnavailable")
      reserveRoute(door, params.targetID, leaseToken)
    else
      error("hades.error.invalidValue")
    end
    return runtime.status()
  end
  function runtime.cancel_world_exit(params)
    local door = requireDoor(params)
    local edit = activeEdit(door)
    assert(edit and edit.leaseToken == params.leaseToken, "hades.error.staleDoor")
    if edit.kind == "reward" then
      refreshDoor(door, edit.original)
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
