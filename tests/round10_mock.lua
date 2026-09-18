-- Behaviour-only Round 8 mock. texlua is Lua 5.3; spoof ABI string because
-- the trainer itself intentionally accepts only the game's Lua 5.2 runtime.
_VERSION = "Lua 5.2"
SessionState = {}
GameState = { Resources = { Money = 10, GiftPoints=2, MetaCurrency=3, OreFSilver=4 }, LifetimeResourcesGained = {}, RunHistory = { {}, {} }, WorldUpgrades = {} }
ResourceData = { Money = {}, GiftPoints={}, MetaCurrency={}, OreFSilver={} }
ResourceDisplayOrderData = { "GiftPoints", "MetaCurrency", "OreFSilver" }
ConsumableData = {
  RoomMoneyTinyDrop = {}, RoomMoneySmallDrop = {}, RoomMoneyDrop = {}, RoomMoneyBigDrop = {}, RoomMoneyTripleDrop = {},
  EmptyMaxHealthSmallDrop = {}, MaxHealthDropSmall = {}, MaxHealthDrop = {}, MaxHealthDropBig = {},
  MaxManaDropSmall = {}, MaxManaDrop = {}, MaxManaDropBig = {},
  MinorTalentDrop = {}, TalentDrop = {}, TalentBigDrop = {}, GiftDrop = {},
  MetaCurrencyDrop = {}, MetaCurrencyBigDrop = {}, MetaCardPointsCommonDrop = {}, MetaCardPointsCommonBigDrop = {},
  MemPointsCommonDrop = {}, MemPointsCommonBigDrop = {}, FireBoost = {}, WaterBoost = {}, EarthBoost = {}, AirBoost = {},
  RuntimeFutureReward = {},
}
RewardStoreData = {
  MockRunRewards = {
    { Name = "MaxManaDrop" },
    { Name = "TalentDrop" },
    { Name = "RuntimeFutureReward" },
    { Name = "HermesUpgrade" },
  },
}
LootData = {
  ZeusUpgrade = { GodLoot=true }, HeraUpgrade = {}, PoseidonUpgrade = {}, DemeterUpgrade = {}, ApolloUpgrade = {},
  AphroditeUpgrade = {}, HephaestusUpgrade = {}, HestiaUpgrade = {}, AresUpgrade = {}, HermesUpgrade = {}, TrialUpgrade = {},
  WeaponUpgrade = { RequiredPackages = { "HammerPackage" } },
  StackUpgrade = {}, StackUpgradeBig = {},
  StackUpgradeTriple = { RequiredPackage = "PomTriplePackage" },
  SpellDrop = { RequiredPackage = "SpellPackage", SetupEvents = { { FunctionName = "PregenerateSpells" } } },
}
RewardData = { WeaponUpgrade={}, StackUpgrade={}, Boon={} }
StartRoom = function(run,room)
  if type(run)=='table' then run.CurrentRoom=room end
  return room
end
ChooseRoomReward = function(run,room,rewardStoreName,previouslyChosen,args)
  room.Reward={Name="RoomMoneyDrop"}; return "RoomMoneyDrop"
end
nextRoomPreviewRefreshes=0
CreateDoorRewardPreview = function(door, rewardType, forceLoot, index, args)
  if args and args.ReUseIds then nextRoomPreviewRefreshes=nextRoomPreviewRefreshes+1 end
end
RefreshUseButton = function(id,door) end
ScreenData = {
  UpgradeChoice = { MaxChoices = 3 },
  InventoryScreen = { ItemCategories = {
    { Name="InventoryScreen_ResourcesTab", "MetaCurrency", "OreFSilver" },
    { Name="InventoryScreen_GiftsTab", "GiftPoints" },
  } },
}
CalcNumLootChoices = function(lootData) return ScreenData.UpgradeChoice.MaxChoices end
GetTotalLootChoices = function() return ScreenData.UpgradeChoice.MaxChoices end
TraitData = {
  SupportingFireBoon = {}, InsideCastCritBoon = {}, EchoLastRewardBoon = {}, SpellMockTrait = {},
  NormalRarityBoon = {}, NormalRarityBoon2 = {}, NormalRarityBoon3 = {},
  LegendaryMockBoon = { InheritFrom = { "LegendaryTrait" } }, DuoMockBoon = { InheritFrom = { "SynergyTrait" } },
  NativeMultiCastTrait = { PropertyChanges = {
    { WeaponName="WeaponCast", EffectName="WeaponCastAttackDisable", EffectProperty="Active", ChangeValue=false, ChangeType="Absolute" },
    { WeaponName="WeaponCast", EffectName="WeaponCastSelfSlow", EffectProperty="Active", ChangeValue=false, ChangeType="Absolute" },
    { WeaponName="WeaponCast", EffectName="WeaponCastSelfSlow2", EffectProperty="Active", ChangeValue=false, ChangeType="Absolute" },
  } },
}
TraitElementData = { Fire={BaseElement=true}, Water={BaseElement=true}, Earth={BaseElement=true}, Air={BaseElement=true}, Aether={BaseElement=false} }
CodexOrdering = {
  Order={ "ChthonicGods", "OlympianGods", "OtherDenizens" },
  ChthonicGods={ "SpellDrop" },
  OlympianGods={ "ZeusUpgrade", "HeraUpgrade", "PoseidonUpgrade", "DemeterUpgrade", "ApolloUpgrade", "AphroditeUpgrade", "HephaestusUpgrade", "HestiaUpgrade", "AresUpgrade", "NPC_Athena_01", "NPC_Dionysus_01", "NPC_Artemis_01", "HermesUpgrade" },
  OtherDenizens={ "NPC_Echo_01", "TrialUpgrade" },
}
-- Deliberately wrong legacy fallback: Round 8 must prefer CodexOrdering.
CodexData = { OlympianGods = { "HermesUpgrade", "AresUpgrade", "ZeusUpgrade" } }
UnitSetData = {
  NPC_Artemis = {
    NPC_Artemis_Field_01 = { SpeakerName = "Artemis", Traits = { "SupportingFireBoon", "InsideCastCritBoon" } },
  },
  NPC_Echo = {
    NPC_Echo_01 = { SpeakerName = "Echo", Traits = { { TraitName = "EchoLastRewardBoon" } } },
  },
}
CurrentHubRoom = nil
MapState = { RoomRequiredObjects = {}, EquippedWeapons = { WeaponStaffSwing=true, WeaponSprint=true, WeaponBlink=true } }
ActiveEnemies = {}
WeaponSets = { HeroPrimarySecondaryWeapons = { "WeaponStaffSwing", "WeaponStaffSpecial" } }
WeaponSetLookups = { HeroPrimarySecondaryWeapons = { WeaponStaffSwing=true, WeaponStaffSpecial=true } }
WeaponData = {
  DefaultWeaponValues = { DefaultSpeedPropertyChanges = { { WeaponProperty="ChargeTime" } } },
  WeaponStaffSwing = {}, WeaponStaffSpecial = {},
}
LootObjects = {}
GameData = { MissingPackages = { WeaponUpgrade = { "HammerExtraPackage" } } }
ScreenState = {}
SessionMapState = { LobAmmoInFlight = 0 }

local units = {}
local function hero(id, health, mana, dodge)
  local h = { ObjectId=id, IsDead=false, Health=health, MaxHealth=health, Mana=mana, MaxMana=mana, TimeScale=1,
    Ammo={ WeaponLob=0 }, ActiveEffects={}, Weapons={WeaponStaffSwing=true},
    UnitSpeed=400, WeaponRuntime={
      WeaponSprint={SelfVelocity=500,SelfVelocityCap=600},
      WeaponBlink={SelfVelocity=650,SelfVelocityCap=720},
      WeaponStaffSwing={ChargeTime=1}, WeaponStaffSpecial={ChargeTime=1},
    },
    Traits={{ Slot="Spell", Name="SpellMockTrait", PreEquipWeapons={"WeaponSpell"}, RemainingUses=2 }},
    NaturalDodge=dodge, DodgeChance=dodge,
    ManaRegenSources={ NativeSource={Value=3,ShowManaRegen=true} },
    HealthBuffer=20, MaxHealthBuffer=20, Elements={Fire=1,Water=2,Earth=3,Air=4,Aether=5}, HighestBaseElementCount=4 }
  units[id]=h
  return h
end
CurrentRun = { Hero=hero(101,100,50,0.15), CurrentRoom={}, ResourcesGained={}, ResourcesSpent={}, NumRerolls=0, SpellCharge=0 }
SetupUnit = function(unit,currentRun,args)
  ActiveEnemies[unit.ObjectId]=unit
  units[unit.ObjectId]=unit
  return unit
end
local existingEnemy={ObjectId=501,Health=50,MaxHealth=100,RequiredKill=true,IsDead=false}
SetupUnit(existingEnemy,CurrentRun,{})

local hitCalls, sacrificeCalls, clearCalls, spellFireCalls = 0, 0, 0, 0
local castEffectActive = { WeaponCastAttackDisable=true, WeaponCastSelfSlow=true, WeaponCastSelfSlow2=true }
local castPropertyCalls, weaponEnabled = 0, false
local castWeaponProperties = { IgnoreOwnerAttackDisabled=false, Cooldown=0.25, AllowMultiFireRequest=false, IgnoreForceCooldown=false, ActiveProjectileCap=1 }
local castWeaponPropertyCalls, activeCastCount = 0, 0
local spawnedLoot, spawnedConsumable, grantedTrait
local loadedPackages, timeScale = {}, 1
local giveLootCalls, spellSetupCalls, lastGiveLootArgs = 0, 0, nil
local enemyTimeScale, heroTimeScale, projectileTimeScale = 1, 1, 1
_elapsedTimeMultiplier = 1
local chargeSpeeds, chargeCalls, activatedTraitChecks = {}, {}, 0
local elapsedMultipliers, elapsedCalls = {}, {}
local nextObjectId = 700

UpdateTimers = function(elapsed) return elapsed end
local manaRegenThreadStarts=0
ManaRegen = function() manaRegenThreadStarts=manaRegenThreadStarts+1 end
thread = function(fn, ...) return fn(...) end
SacrificeHealth = function(args)
  sacrificeCalls=sacrificeCalls+1
  if args and args.DeductHealth then CurrentRun.Hero.Health=CurrentRun.Hero.Health-(args.SacrificeHealth or 5) end
end
Damage = function(victim,args)
  hitCalls=hitCalls+1; victim.Armor=(victim.Armor or 20)-1
  victim.Health=victim.Health-(args.DamageAmount or 10)
  if args.MinHealth~=nil and victim.Health<args.MinHealth then victim.Health=args.MinHealth end
end
ManaDelta = function(delta) CurrentRun.Hero.Mana=CurrentRun.Hero.Mana+delta end
GetHeroMaxAvailableMana = function() return CurrentRun.Hero.MaxMana end
UpdateWeaponMana = function() end
UpdateManaMeterUI = function() end
UpdateHealthUI = function() end
CheckActivatedTraits = function() activatedTraitChecks=activatedTraitChecks+1 end
CalculateDamageMultipliers = function() return 1 end
AddResource = function(id,amount) GameState.Resources[id]=(GameState.Resources[id] or 0)+amount end
SpendResource = function(id,amount) GameState.Resources[id]=(GameState.Resources[id] or 0)-amount end
UpdateRerollUI = function() end
ShowRerollUI = function() end
UpdateMoneyUI = function() end
ClearEffect = function(args) clearCalls=clearCalls+1; CurrentRun.Hero.ActiveEffects[args.Name]=nil end
SetUnitInvulnerable = function(unit,flag) unit.InvulnerableFlags=unit.InvulnerableFlags or {}; unit.InvulnerableFlags[flag or "Generic"]=true end
SetUnitVulnerable = function(unit,flag) if unit.InvulnerableFlags then unit.InvulnerableFlags[flag or "Generic"]=nil end end
GetWeaponData = function(heroUnit, weaponName) return { Name=weaponName } end
GetManaSpendCost = function(data) assert(type(data)=="table" and data.Name=="WeaponSpell","hex cost requires weapon data"); return 100 end
GetEquippedWeapon = function() return "WeaponStaffSwing" end
GetBaseDataValue = function(args)
  assert(type(args)=="table" and type(args.Property)=="string","base data getter shape")
  if args.Type=="Unit" and args.Name=="_PlayerUnit" and args.Property=="Speed" then return 400 end
  if args.Type=="Weapon" and args.Name=="WeaponSprint" and args.Property=="SelfVelocity" then return 500 end
  if args.Type=="Weapon" and args.Name=="WeaponSprint" and args.Property=="SelfVelocityCap" then return 600 end
  if args.Type=="Weapon" and args.Name=="WeaponBlink" and args.Property=="SelfVelocity" then return 650 end
  if args.Type=="Weapon" and args.Name=="WeaponBlink" and args.Property=="SelfVelocityCap" then return 720 end
  return nil
end
GetUnitDataValue = function(args)
  local unit=units[args.Id]; return unit and args.Property=="Speed" and unit.UnitSpeed or nil
end
SetUnitProperty = function(args)
  local unit=units[args.DestinationId]; assert(unit and args.Property=="Speed","unit speed setter shape")
  if args.ValueChangeType=="Multiply" then unit.UnitSpeed=unit.UnitSpeed*args.Value else unit.UnitSpeed=args.Value end
end
GetWeaponDataValue = function(args)
  assert(type(args)=="table" and type(args.WeaponName)=="string" and type(args.Property)=="string","weapon getter shape")
  if args.WeaponName=="WeaponCast" then return castWeaponProperties[args.Property] end
  local unit=units[args.Id]
  local runtime=unit and unit.WeaponRuntime and unit.WeaponRuntime[args.WeaponName]
  return runtime and runtime[args.Property] or nil
end
SetWeaponProperty = function(args)
  assert(type(args)=="table" and type(args.WeaponName)=="string","weapon property call shape")
  if args.WeaponName=="WeaponSpell" and args.Property=="Enabled" then weaponEnabled=not not args.Value end
  if args.WeaponName=="WeaponCast" then
    castWeaponPropertyCalls=castWeaponPropertyCalls+1
    -- Live revision-13 evidence showed the transient DataValue=false write did
    -- not change native Cooldown / IgnoreForceCooldown.  Model that behavior so
    -- this test would fail if the Round 7 calling convention returned.
    if args.DataValue==false and (args.Property=="Cooldown" or args.Property=="IgnoreForceCooldown") then return end
    castWeaponProperties[args.Property]=args.Value
    return
  end
  local unit=units[args.DestinationId]
  if unit then
    unit.WeaponRuntime[args.WeaponName]=unit.WeaponRuntime[args.WeaponName] or {}
    local runtime=unit.WeaponRuntime[args.WeaponName]
    if args.ValueChangeType=="Multiply" then runtime[args.Property]=(runtime[args.Property] or 1)*args.Value
    else runtime[args.Property]=args.Value end
  end
end
GetLuaWeaponSpeedMultiplier = function(weaponName) return 1 end
local function tryCast()
  if activeCastCount > 0 then
    local canRepeat = (not castEffectActive.WeaponCastAttackDisable)
      and castWeaponProperties.IgnoreOwnerAttackDisabled == true
      and castWeaponProperties.AllowMultiFireRequest == true
      and castWeaponProperties.IgnoreForceCooldown == true
      and castWeaponProperties.Cooldown == 0
    if not canRepeat then return false end
    -- Multi-fire request acceptance is separate from the engine's active
    -- projectile cap. A live cast can still occupy the only slot even when all
    -- cooldown/control gates are open.
    if activeCastCount >= (castWeaponProperties.ActiveProjectileCap or 1) then return false end
  end
  activeCastCount=activeCastCount+1
  SessionMapState.LastCastProjectileId=900+activeCastCount
  SessionMapState.CastAttachedProjectiles=SessionMapState.CastAttachedProjectiles or {}
  SessionMapState.CastAttachedProjectiles[900+activeCastCount]={}
  return true
end
ProjectileExists = function(args)
  return type(args)=="table" and type(args.Id)=="number" and SessionMapState.CastAttachedProjectiles and SessionMapState.CastAttachedProjectiles[args.Id] ~= nil
end
UpdateTraitNumber = function() end
ChargeSpell = function(delta) CurrentRun.SpellCharge=math.min((CurrentRun.SpellCharge or 0)-delta,100) end
SpellFire = function()
  spellFireCalls=spellFireCalls+1; CurrentRun.SpellCharge=0; weaponEnabled=false
  local trait=CurrentRun.Hero.Traits[1]
  if trait and trait.RemainingUses then trait.RemainingUses=math.max(0,trait.RemainingUses-1) end
end
SetEffectProperty = function(args)
  castPropertyCalls=castPropertyCalls+1
  assert(args.WeaponName=="WeaponCast" and castEffectActive[args.EffectName]~=nil and args.Property=="Active","unexpected cast effect property")
  castEffectActive[args.EffectName]=not not args.Value
end
HasHeroTraitValue = function() return false end
GetMaxAmmo = function(name) if name=="WeaponLob" then return 4 end return 0 end
UpdateWeaponAmmo = function(name,delta) CurrentRun.Hero.Ammo[name]=(CurrentRun.Hero.Ammo[name] or 0)+delta end

GetMaxMetaUpgradeCost = function() return 30 end
SetLifeProperty = function(args)
  assert(type(args)=="table" and args.Property=="DodgeChance", "unexpected life property")
  -- Match the live game: a DodgeChance write without an explicit target is a
  -- silent no-op rather than a Lua error.  This reproduces the Fix 3 bug.
  if args.DestinationId == nil then return end
  local unit=units[args.DestinationId]
  if not unit then return end
  if args.ValueChangeType=="Add" then unit.DodgeChance=(unit.DodgeChance or 0)+(args.Value or 0)
  else unit.DodgeChance=args.Value end
end
ApplyUnitPropertyChanges = function(unit, changes, applyLuaUpgrades, reverse)
  for _,change in ipairs(changes or {}) do
    local value=change.ChangeValue
    if reverse then
      if change.ChangeType=="Multiply" then value=1/value
      elseif change.ChangeType=="Add" then value=-value end
    end
    if change.LifeProperty=="DodgeChance" then
      if change.ChangeType=="Add" then unit.NaturalDodge=(unit.NaturalDodge or 0)+value
      else unit.NaturalDodge=value end
      SetLifeProperty({Property="DodgeChance",Value=unit.NaturalDodge,DestinationId=unit.ObjectId,DataValue=false})
    elseif change.WeaponName and change.WeaponProperty and MapState.EquippedWeapons[change.WeaponName] then
      SetWeaponProperty({WeaponName=change.WeaponName,DestinationId=unit.ObjectId,Property=change.WeaponProperty,Value=value,ValueChangeType=change.ChangeType})
    end
  end
  return "property-ok"
end
GetTotalHeroTraitValue = function(name,args)
  if name=="DodgeChance" then return CurrentRun.Hero.NaturalDodge end
  if name=="LuckMultiplier" then return 1.25 end
  if name=="OutgoingUnmodifiedCritBonus" then return 0.05 end
  return args and args.IsMultiplier and 1 or 0
end
CalculateCritChance = function(attacker,victim,weaponData,triggerArgs)
  if triggerArgs then triggerArgs.CritChance=0.10 end
  return 0.10
end

SpawnObstacle = function(args) nextObjectId=nextObjectId+1; return nextObjectId end
CreateConsumableItem = function(id,name,cost,args)
  spawnedConsumable=name
  if name=="SpellDrop" then
    assert(args and args.AutoLoadPackages==true,"Selene consumable must auto-load packages")
    loadedPackages.SpellPackage=true
    if PregenerateSpells then PregenerateSpells() end
    spawnedLoot=name
  end
  return { ObjectId=id, Name=name, CanReceiveGift=name=="SpellDrop", OnUsedFunctionName=name=="SpellDrop" and "OpenSpellScreen" or nil }
end
CreateLoot = function(args)
  if args.Name=="WeaponUpgrade" then assert(loadedPackages.HammerPackage and loadedPackages.HammerExtraPackage,"hammer packages were not loaded") end
  if args.Name=="StackUpgradeTriple" then assert(loadedPackages.PomTriplePackage,"triple Pom package was not loaded") end
  nextObjectId=nextObjectId+1; spawnedLoot=args.Name; return { ObjectId=nextObjectId, Name=args.Name }
end
GiveLoot = function(args)
  giveLootCalls=giveLootCalls+1
  lastGiveLootArgs=args
  local name=args.ForceLootName or "ZeusUpgrade"
  if name=="SpellDrop" then
    assert(args.AutoLoadPackages==true,"Selene GiveLoot must auto-load packages")
    loadedPackages.SpellPackage=true
    if PregenerateSpells then PregenerateSpells() end
  end
  nextObjectId=nextObjectId+1
  spawnedLoot=name
  return { ObjectId=nextObjectId, Name=name, CanReceiveGift=name=="SpellDrop", OnUsedFunctionName=name=="SpellDrop" and "OpenSpellScreen" or nil }
end
local spawnRoomRewardCalls, lastSpawnRoomRewardArgs = 0, nil
SpawnRoomReward = function(eventSource,args)
  spawnRoomRewardCalls=spawnRoomRewardCalls+1
  lastSpawnRoomRewardArgs=args
  assert(args.RewardOverride=="SpellDrop" and args.LootName==nil,"Selene room reward shape mismatch")
  local id=SpawnObstacle({Name="SpellDrop",DestinationId=args.SpawnRewardOnId,Group="Standing"})
  return CreateConsumableItem(id,"SpellDrop",0,{AutoLoadPackages=args.AutoLoadPackages})
end
local boonOptionGenerationCalls = 0
local boonNativeSpecials = true
GetRarityChances = function() return { Common=1, Rare=0.20, Epic=0.10, Heroic=0.05 } end
SetTraitsOnLoot = function(loot)
  boonOptionGenerationCalls=boonOptionGenerationCalls+1
  if boonNativeSpecials then
    loot.UpgradeOptions={
      {ItemName="NormalRarityBoon",Type="Trait",Rarity="Common"},
      {ItemName="LegendaryMockBoon",Type="Trait",Rarity="Legendary"},
      {ItemName="DuoMockBoon",Type="Trait",Rarity="Duo"},
    }
  else
    loot.UpgradeOptions={
      {ItemName="NormalRarityBoon",Type="Trait",Rarity="Common"},
      {ItemName="NormalRarityBoon2",Type="Trait",Rarity="Common"},
      {ItemName="NormalRarityBoon3",Type="Trait",Rarity="Common"},
    }
  end
end
GetEligibleUpgrades = function()
  return {
    {ItemName="LegendaryMockBoon",Type="Trait"},
    {ItemName="DuoMockBoon",Type="Trait"},
  }
end
local gardenMultiPlantSeen, gardenHarvestAllSeen = false, false
GardenPlantSeed = function(screen,button,args) gardenMultiPlantSeen = args and args.MultiPlant == true; return "garden-planted" end
UseGardenPlot = function(plot,args,user) gardenHarvestAllSeen = GameState.WorldUpgrades.WorldUpgradeGardenHarvestAll == true; return "garden-used" end
LoadPackages = function(args)
  assert(type(args)=="table" and type(args.Names)=="table","LoadPackages call shape mismatch")
  for _,name in ipairs(args.Names) do loadedPackages[name]=true end
end
SetPlayerAttackSpecialChargeSpeed = function(name,multiplier)
  assert(type(name)=="string" and type(multiplier)=="number","charge speed call shape mismatch")
  chargeSpeeds[name]=multiplier; chargeCalls[#chargeCalls+1]={Name=name,Value=multiplier,Remove=false}
end
RemovePlayerAttackSpecialChargeSpeed = function(name,multiplier)
  assert(chargeSpeeds[name]==multiplier,"charge speed reverse mismatch")
  chargeSpeeds[name]=nil; chargeCalls[#chargeCalls+1]={Name=name,Value=multiplier,Remove=true}
end
-- Round 6 models the game's native slowdown layer: it selects the minimum
-- multiplier and therefore cannot natively express >1 acceleration.
SessionState.GameplaySlows = {}
SessionState.PlayerGameplaySlows = {}
GetGameplayElapsedTimeMultiplier = function()
  local value=1
  for _,entry in pairs(SessionState.GameplaySlows) do if entry.Amount<value then value=entry.Amount end end
  return value
end
GetPlayerGameplayElapsedTimeMultiplier = function()
  local value=1
  for _,entry in pairs(SessionState.PlayerGameplaySlows) do if entry.Amount<value then value=entry.Amount end end
  return value
end
SetThingProperty = function(args)
  assert(type(args)=="table" and args.Property=="ElapsedTimeMultiplier","unexpected thing property")
  local value=args.Value
  if args.AllProjectiles then
    if args.ValueChangeType=="Multiply" then projectileTimeScale=projectileTimeScale*value else projectileTimeScale=value end
  elseif args.DestinationNames then
    if args.ValueChangeType=="Multiply" then enemyTimeScale=enemyTimeScale*value else enemyTimeScale=value end
  elseif args.DestinationId then
    local unit=units[args.DestinationId]
    if unit then
      if args.ValueChangeType=="Multiply" then unit.TimeScale=(unit.TimeScale or 1)*value else unit.TimeScale=value end
      if unit==CurrentRun.Hero then heroTimeScale=unit.TimeScale end
    end
  end
end
GameplaySetElapsedTimeMultiplier = function(args)
  local starting=GetGameplayElapsedTimeMultiplier()
  local startingPlayer=GetPlayerGameplayElapsedTimeMultiplier()
  local name=args.Name or "Generic"
  elapsedCalls[#elapsedCalls+1]={ Name=name, Value=args.ElapsedTimeMultiplier, Reverse=args.Reverse and true or false }
  if args.ClearAll then
    SessionState.GameplaySlows={};SessionState.PlayerGameplaySlows={}
  elseif args.Reverse then
    SessionState.GameplaySlows[name]=nil
    if args.ApplyToPlayerUnits then SessionState.PlayerGameplaySlows[name]=nil end
  else
    SessionState.GameplaySlows[name]={Amount=args.ElapsedTimeMultiplier}
    if args.ApplyToPlayerUnits then SessionState.PlayerGameplaySlows[name]={Amount=args.ElapsedTimeMultiplier} end
  end
  local current=GetGameplayElapsedTimeMultiplier()
  local currentPlayer=GetPlayerGameplayElapsedTimeMultiplier()
  _elapsedTimeMultiplier=current
  SetThingProperty({Property="ElapsedTimeMultiplier",Value=current,ValueChangeType="Absolute",DataValue=false,AllProjectiles=true})
  SetThingProperty({Property="ElapsedTimeMultiplier",Value=current/starting,ValueChangeType="Multiply",DataValue=false,DestinationNames={"EnemyTeam","RoomWeapon","Summons"}})
  if args.ApplyToPlayerUnits then
    SetThingProperty({Property="ElapsedTimeMultiplier",Value=currentPlayer/startingPlayer,ValueChangeType="Multiply",DataValue=false,DestinationId=CurrentRun.Hero.ObjectId})
  end
  timeScale=current
end
SetTimeScale = nil
PregenerateSpells = function() spellSetupCalls=spellSetupCalls+1 end
SilenceForDreamRun = function() end
AddTraitToHero = function(args) grantedTrait=args.TraitName; return { Name=args.TraitName } end

local fishingOriginalCalls, exorcismOriginalCalls = 0, 0
WaitForFishingInput = function(args) fishingOriginalCalls=fishingOriginalCalls+1 end
ExorcismSequence = function(source,data,args,user) exorcismOriginalCalls=exorcismOriginalCalls+1; return false end
ToggleCombatControl = function() end
FishingReadyForInputPresentation = function() end
SetThreadWait = function() return true end
wait = function() end

local testSource = debug.getinfo(1, 'S').source
local testPath = string.sub(testSource, 1, 1) == '@' and string.sub(testSource, 2) or testSource
local projectRoot = testPath:match('^(.*)/tests/[^/]+$') or '.'
assert(loadfile(projectRoot .. '/Backend/games/hades2/runtime/hades.lua'))()
local M=__MacGamingTrainerV1
local function setFeature(key,value)
  local state=M.dispatch('set_feature',{feature=key,value=value})
  assert(state.desiredFeatures[key]==value,key..' desired mismatch')
  return state
end
local function findReward(state,id)
  for _,item in ipairs(state.rewards or {}) do if item.id==id then return item end end
end

-- Existing Round 3 combat behavior remains intact.
setFeature('godMode',true)
CurrentRun.Hero.Armor=20
Damage(CurrentRun.Hero,{DamageAmount=25})
assert(hitCalls==0 and CurrentRun.Hero.Health==100 and CurrentRun.Hero.Armor==20)
setFeature('godMode',false)
setFeature('infiniteHealth',true)
Damage(CurrentRun.Hero,{DamageAmount=20})
assert(hitCalls==1 and CurrentRun.Hero.Health==100 and CurrentRun.Hero.Armor==19)
setFeature('infiniteHealth',false)

-- Runtime catalog includes ordinary drops, loot, Selene, and dynamically discovered NPC traits.
local state=M.dispatch('status',{})
assert(findReward(state,'RoomMoneyDrop'),'money drop missing')
assert(findReward(state,'MaxManaDrop'),'Soul Tonic missing')
assert(findReward(state,'MaxManaDropSmall'),'small Soul Tonic missing')
assert(findReward(state,'TalentDrop'),'Path of Stars reward missing')
assert(findReward(state,'GiftDrop'),'Nectar reward missing')
assert(findReward(state,'MetaCurrencyDrop'),'Bones reward missing')
assert(findReward(state,'FireBoost'),'element reward missing')
assert(findReward(state,'RuntimeFutureReward'),'runtime RewardStoreData discovery missing')
assert(findReward(state,'WeaponUpgrade'),'hammer missing')
assert(findReward(state,'StackUpgrade'),'pom missing')
assert(findReward(state,'SpellDrop'),'Selene missing')
assert(findReward(state,'trait:SupportingFireBoon'),'Artemis trait missing')
assert(findReward(state,'trait:EchoLastRewardBoon'),'Echo trait missing')
assert(findReward(state,'ZeusUpgrade').group=='olympian','Olympian group missing')
assert(findReward(state,'HermesUpgrade').group=='olympian','RewardStore Olympian must not be duplicated as pickup')
local rewardIdCounts={}
for _,item in ipairs(state.rewards or {}) do rewardIdCounts[item.id]=(rewardIdCounts[item.id] or 0)+1 end
for id,count in pairs(rewardIdCounts) do assert(count==1,'duplicate reward catalog id: '..tostring(id)) end
assert(findReward(state,'RoomMoneyDrop').group=='pickup','pickup group missing')
assert(findReward(state,'SpellDrop').group=='special','special group missing')
assert(findReward(state,'TrialUpgrade').group=='special','Chaos should be in special group')
assert(findReward(state,'trait:SupportingFireBoon').group=='special','NPC special group missing')
local pickupIds={}; local olympianIds={}; local specialIds={}
for _,item in ipairs(state.rewards) do
  if item.group=='pickup' then pickupIds[#pickupIds+1]=item.id
  elseif item.group=='olympian' then olympianIds[#olympianIds+1]=item.id
  elseif item.group=='special' then specialIds[#specialIds+1]=item.id end
end
local function positions(list, wanted)
  local result={}; for i,id in ipairs(list) do result[id]=i end; return result
end
local pp=positions(pickupIds); assert(pp.StackUpgrade and pp.StackUpgradeBig and pp.StackUpgradeTriple and pp.StackUpgradeBig==pp.StackUpgrade+1 and pp.StackUpgradeTriple==pp.StackUpgrade+2,'Pom family not adjacent')
local op=positions(olympianIds); assert(op.ZeusUpgrade<op.HeraUpgrade and op.HeraUpgrade<op.PoseidonUpgrade and op.AresUpgrade<op.HermesUpgrade,'Codex Olympian order not preserved')
local sp=positions(specialIds); assert(sp.SpellDrop<sp.TrialUpgrade and sp['trait:SupportingFireBoon'],'special groups not ordered')
assert(findReward(state,'trait:SupportingFireBoon').sourceName=='阿耳忒弥斯','special source metadata missing')
local resourceIds={}; for _,item in ipairs(state.resources or {}) do resourceIds[#resourceIds+1]=item.id end
assert(table.concat(resourceIds,',')=='MetaCurrency,OreFSilver,GiftPoints','InventoryScreen resource category order was not preserved')
assert(state.resources[1].sectionTitle=='资源' and state.resources[2].sectionTitle=='资源' and state.resources[3].sectionTitle=='赠礼','InventoryScreen resource grouping metadata missing')
assert(state.runCount==3,'run count mismatch')

-- Locked resources now use true no-spend semantics rather than deduct/write-back.
local moneyBefore=GameState.Resources.Money
M.dispatch('lock_resource',{resource='Money',locked=true,requestId='lock-money-r9'})
SpendResource('Money',5,'Shop')
assert(GameState.Resources.Money==moneyBefore,'locked money was consumed')
M.dispatch('lock_resource',{resource='Money',locked=false,requestId='unlock-money-r9'})
SpendResource('Money',2,'Shop')
assert(GameState.Resources.Money==moneyBefore-2,'unlocked money did not spend normally')

-- Enemy damage multiplier affects attributable hostile damage only and preserves self damage.
CurrentRun.Hero.Health=100
state=M.dispatch('set_stat',{stat='enemyDamage',locked=true,value=50})
assert(state.stats.enemyDamage.locked and state.stats.enemyDamage.value==50,'enemy damage stat missing')
Damage(CurrentRun.Hero,{DamageAmount=20,AttackerId=999})
assert(CurrentRun.Hero.Health==90,'50% enemy damage multiplier failed')
Damage(CurrentRun.Hero,{DamageAmount=10,AttackerId=CurrentRun.Hero.ObjectId})
assert(CurrentRun.Hero.Health==80,'self damage should not be scaled as enemy damage')
M.dispatch('set_stat',{stat='enemyDamage',locked=false})
CurrentRun.Hero.Health=100
Damage(CurrentRun.Hero,{DamageAmount=20,AttackerId=999})
assert(CurrentRun.Hero.Health==80,'enemy damage hook leaked after unlock')

-- Round 10 enemy health multiplier rescales current enemies proportionally,
-- applies to future SetupUnit spawns, and restores native max health on unlock.
state=M.dispatch('set_stat',{stat='enemyHealth',locked=true,value=200})
assert(state.stats.enemyHealth.locked and state.stats.enemyHealth.value==200,'enemy health stat missing')
assert(math.abs(existingEnemy.MaxHealth-200)<1e-9 and math.abs(existingEnemy.Health-100)<1e-9,'existing enemy was not scaled to 200%')
state=M.dispatch('set_stat',{stat='enemyHealth',locked=true,value=50})
assert(math.abs(existingEnemy.MaxHealth-50)<1e-9 and math.abs(existingEnemy.Health-25)<1e-9,'enemy health retarget did not preserve health ratio')
local spawnedEnemy={ObjectId=502,Health=80,MaxHealth=80,RequiredKill=true,IsDead=false}
SetupUnit(spawnedEnemy,CurrentRun,{})
assert(math.abs(spawnedEnemy.MaxHealth-40)<1e-9 and math.abs(spawnedEnemy.Health-40)<1e-9,'new enemy did not inherit health multiplier')
M.dispatch('set_stat',{stat='enemyHealth',locked=false})
assert(math.abs(existingEnemy.MaxHealth-100)<1e-9 and math.abs(existingEnemy.Health-50)<1e-9,'existing enemy health did not restore')
assert(math.abs(spawnedEnemy.MaxHealth-80)<1e-9 and math.abs(spawnedEnemy.Health-80)<1e-9,'spawned enemy health did not restore')
CurrentRun.Hero.Health=100
state=M.dispatch('set_counter',{counter='spellCharge',value=73})
assert(CurrentRun.SpellCharge==73 and state.spellCharge==73 and state.spellChargeCost==100,'spell charge edit/state failed')

-- Vital locks cover the full top in-run block, including armor. Edits update the locked target.
state=M.dispatch('lock_vital',{vital='health',locked=true})
state=M.dispatch('lock_vital',{vital='mana',locked=true})
state=M.dispatch('lock_vital',{vital='armor',locked=true})
assert(state.healthLocked and state.manaLocked and state.armorLocked,'vital locks not exposed')
CurrentRun.Hero.Health=31; CurrentRun.Hero.MaxHealth=44
CurrentRun.Hero.Mana=7; CurrentRun.Hero.MaxMana=13
CurrentRun.Hero.HealthBuffer=2; CurrentRun.Hero.MaxHealthBuffer=5
UpdateTimers(0.016)
assert(CurrentRun.Hero.Health==100 and CurrentRun.Hero.MaxHealth==100,'health lock drifted')
assert(CurrentRun.Hero.Mana==50 and CurrentRun.Hero.MaxMana==50,'mana lock drifted')
assert(CurrentRun.Hero.HealthBuffer==20 and CurrentRun.Hero.MaxHealthBuffer==20,'armor lock drifted')
local armorMaxOk=pcall(function() M.dispatch('set_vital',{vital='armor',field='max',value=80}) end)
assert(not armorMaxOk,'armor max edit must be rejected')
M.dispatch('set_vital',{vital='armor',field='current',value=65})
CurrentRun.Hero.HealthBuffer=1; CurrentRun.Hero.MaxHealthBuffer=2; UpdateTimers(0.016)
assert(CurrentRun.Hero.HealthBuffer==65 and CurrentRun.Hero.MaxHealthBuffer==65,'armor current lock did not grow engine capacity')
M.dispatch('lock_vital',{vital='health',locked=false}); M.dispatch('lock_vital',{vital='mana',locked=false}); M.dispatch('lock_vital',{vital='armor',locked=false})

-- Element counters can be edited and locked independently and update elemental activation caches.
state=M.dispatch('set_element',{element='Fire',amount=12})
assert(CurrentRun.Hero.Elements.Fire==12 and CurrentRun.Hero.HighestBaseElementCount==12,'element edit failed')
assert(activatedTraitChecks>0,'element edit did not refresh activated traits')
state=M.dispatch('lock_element',{element='Fire',locked=true})
CurrentRun.Hero.Elements.Fire=1; UpdateTimers(0.016)
assert(CurrentRun.Hero.Elements.Fire==12,'element lock drifted')
local fireRow=nil; for _,row in ipairs(state.elements or {}) do if row.id=='Fire' then fireRow=row end end
assert(fireRow and fireRow.locked,'element lock state missing')
M.dispatch('lock_element',{element='Fire',locked=false})
state=M.dispatch('set_element',{element='Aether',amount=99})
assert(CurrentRun.Hero.Elements.Aether==99,'Aether edit failed')
assert(CurrentRun.Hero.HighestBaseElementCount==12,'Aether incorrectly changed HighestBaseElementCount')
local aetherRow=nil; for _,row in ipairs(state.elements or {}) do if row.id=='Aether' then aetherRow=row end end
assert(aetherRow and aetherRow.name=='以太','Aether row missing or mislabeled')

-- Grasp locks at the function layer and restores original calculation on unlock.
state=M.dispatch('set_stat',{stat='grasp',locked=true,value=77})
assert(state.stats.grasp.locked and GetMaxMetaUpgradeCost()==77,'grasp lock failed')
M.dispatch('set_stat',{stat='grasp',locked=false})
assert(GetMaxMetaUpgradeCost()==30,'grasp unlock did not restore original')

-- Dodge uses the actual life property. Natural changes are preserved while the visible lock remains exact.
state=M.dispatch('set_stat',{stat='dodge',locked=true,value=75})
assert(math.abs(CurrentRun.Hero.DodgeChance-0.75)<1e-9,'dodge lock failed')
assert(math.abs(GetTotalHeroTraitValue('DodgeChance')-0.75)<1e-9,'dodge trait routing did not expose locked target')
local r=ApplyUnitPropertyChanges(CurrentRun.Hero,{{LifeProperty='DodgeChance',ChangeType='Add',ChangeValue=0.05}})
assert(r=='property-ok','property change return value lost')
assert(math.abs(CurrentRun.Hero.DodgeChance-0.75)<1e-9,'dodge drifted while locked')
M.dispatch('set_stat',{stat='dodge',locked=false})
assert(math.abs(CurrentRun.Hero.DodgeChance-0.20)<1e-9,'dodge natural value was not restored')

-- Final crit target neutralizes the unmodified additive term and compensates LuckMultiplier.
state=M.dispatch('set_stat',{stat='crit',locked=true,value=80})
local args={}
local raw=CalculateCritChance(CurrentRun.Hero,nil,nil,args)
local final=raw*GetTotalHeroTraitValue('LuckMultiplier',{IsMultiplier=true})+GetTotalHeroTraitValue('OutgoingUnmodifiedCritBonus')
assert(math.abs(final-0.80)<1e-9,'crit final chance is not exact target')
assert(GetTotalHeroTraitValue('OutgoingUnmodifiedCritBonus')==0,'crit additive term was not neutralized')
-- The shared trait-value router must handle crit without breaking a future dodge lock.
M.dispatch('set_stat',{stat='dodge',locked=true,value=62})
assert(math.abs(GetTotalHeroTraitValue('DodgeChance')-0.62)<1e-9,'shared stat router lost dodge target')
assert(GetTotalHeroTraitValue('OutgoingUnmodifiedCritBonus')==0,'shared stat router lost crit override')
M.dispatch('set_stat',{stat='dodge',locked=false})
M.dispatch('set_stat',{stat='crit',locked=false})
assert(math.abs(CalculateCritChance(CurrentRun.Hero,nil,nil,{})-0.10)<1e-9,'crit function not restored')
assert(math.abs(GetTotalHeroTraitValue('OutgoingUnmodifiedCritBonus')-0.05)<1e-9,'crit bonus hook not restored')

-- Charge speed uses the same named player charge-speed layer used by game systems.
state=M.dispatch('set_stat',{stat='chargeSpeed',locked=true,value=175})
assert(state.stats.chargeSpeed.locked and math.abs(chargeSpeeds.MacGamingTrainerChargeSpeed-1.75)<1e-9,'charge speed lock failed')
state=M.dispatch('set_stat',{stat='chargeSpeed',locked=true,value=80})
assert(math.abs(chargeSpeeds.MacGamingTrainerChargeSpeed-0.8)<1e-9,'charge speed retarget failed')
assert(chargeCalls[#chargeCalls-1].Remove==true and chargeCalls[#chargeCalls].Remove==false,'charge speed did not reverse old layer')
M.dispatch('set_stat',{stat='chargeSpeed',locked=false})
assert(chargeSpeeds.MacGamingTrainerChargeSpeed==nil,'charge speed unlock failed')

-- Movement / sprint / attack speed use reversible native property layers.
state=M.dispatch('set_stat',{stat='moveSpeed',locked=true,value=150})
assert(state.stats.moveSpeed.locked and math.abs(CurrentRun.Hero.UnitSpeed-600)<1e-9,'move speed lock failed')
M.dispatch('set_stat',{stat='moveSpeed',locked=true,value=80})
assert(math.abs(CurrentRun.Hero.UnitSpeed-320)<1e-9,'move speed retarget failed')
M.dispatch('set_stat',{stat='moveSpeed',locked=false})
assert(math.abs(CurrentRun.Hero.UnitSpeed-400)<1e-9,'move speed unlock failed')

state=M.dispatch('set_stat',{stat='sprintSpeed',locked=true,value=160})
assert(state.stats.sprintSpeed.locked and math.abs(CurrentRun.Hero.WeaponRuntime.WeaponSprint.SelfVelocity-800)<1e-9,'sprint velocity lock failed')
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponSprint.SelfVelocityCap-960)<1e-9,'sprint velocity cap lock failed')
M.dispatch('set_stat',{stat='sprintSpeed',locked=false})
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponSprint.SelfVelocity-500)<1e-9 and math.abs(CurrentRun.Hero.WeaponRuntime.WeaponSprint.SelfVelocityCap-600)<1e-9,'sprint speed unlock failed')

state=M.dispatch('set_stat',{stat='dashSpeed',locked=true,value=150})
assert(state.stats.dashSpeed.locked and math.abs(CurrentRun.Hero.WeaponRuntime.WeaponBlink.SelfVelocity-975)<1e-9,'dash velocity lock failed')
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponBlink.SelfVelocityCap-1080)<1e-9,'dash velocity cap lock failed')
M.dispatch('set_stat',{stat='dashSpeed',locked=false})
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponBlink.SelfVelocity-650)<1e-9 and math.abs(CurrentRun.Hero.WeaponRuntime.WeaponBlink.SelfVelocityCap-720)<1e-9,'dash speed unlock failed')

state=M.dispatch('set_stat',{stat='manaRegen',locked=true,value=12})
assert(state.stats.manaRegen.locked and CurrentRun.Hero.ManaRegenSources.MacGamingTrainerManaRegen.Value==12,'mana regen source lock failed')
assert(CurrentRun.Hero.ManaRegenSources.NativeSource.Value==3,'mana regen lock overwrote native source')
assert(manaRegenThreadStarts>0,'mana regen lock did not start native regen loop')
M.dispatch('set_stat',{stat='manaRegen',locked=false})
assert(CurrentRun.Hero.ManaRegenSources.MacGamingTrainerManaRegen==nil and CurrentRun.Hero.ManaRegenSources.NativeSource.Value==3,'mana regen unlock leaked trainer source')

state=M.dispatch('set_stat',{stat='attackSpeed',locked=true,value=200})
assert(state.stats.attackSpeed.locked and math.abs(CurrentRun.Hero.WeaponRuntime.WeaponStaffSwing.ChargeTime-0.5)<1e-9,'attack speed lock failed')
M.dispatch('set_stat',{stat='attackSpeed',locked=true,value=125})
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponStaffSwing.ChargeTime-0.8)<1e-9,'attack speed retarget failed')
M.dispatch('set_stat',{stat='attackSpeed',locked=false})
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponStaffSwing.ChargeTime-1)<1e-9,'attack speed unlock failed')

-- Re-enable all stats, then verify they remount cleanly on a new Hero/run.
M.dispatch('set_stat',{stat='grasp',locked=true,value=66})
M.dispatch('set_stat',{stat='dodge',locked=true,value=55})
M.dispatch('set_stat',{stat='crit',locked=true,value=40})
M.dispatch('set_stat',{stat='chargeSpeed',locked=true,value=140})
M.dispatch('set_stat',{stat='moveSpeed',locked=true,value=135})
M.dispatch('set_stat',{stat='sprintSpeed',locked=true,value=145})
M.dispatch('set_stat',{stat='dashSpeed',locked=true,value=130})
M.dispatch('set_stat',{stat='manaRegen',locked=true,value=9})
M.dispatch('set_stat',{stat='attackSpeed',locked=true,value=160})
local oldHero=CurrentRun.Hero
CurrentRun={Hero=hero(202,80,40,0.10),CurrentRoom={},ResourcesGained={},ResourcesSpent={},NumRerolls=0,SpellCharge=0}
UpdateTimers(0.016)
state=M.dispatch('status',{})
assert(state.stats.grasp.locked and GetMaxMetaUpgradeCost()==66,'grasp did not remount')
assert(math.abs(CurrentRun.Hero.DodgeChance-0.55)<1e-9,'dodge did not remount')
assert(math.abs(CurrentRun.Hero.DodgeChance-0.55)<1e-9,'old hero dodge state leaked into new hero')
local crit=CalculateCritChance(CurrentRun.Hero,nil,nil,{})*GetTotalHeroTraitValue('LuckMultiplier',{IsMultiplier=true})
assert(math.abs(crit-0.40)<1e-9,'crit did not remount')
assert(math.abs(chargeSpeeds.MacGamingTrainerChargeSpeed-1.4)<1e-9,'charge speed did not remount')
assert(math.abs(CurrentRun.Hero.UnitSpeed-540)<1e-9,'move speed did not remount')
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponSprint.SelfVelocity-725)<1e-9 and math.abs(CurrentRun.Hero.WeaponRuntime.WeaponSprint.SelfVelocityCap-870)<1e-9,'sprint speed did not remount')
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponBlink.SelfVelocity-845)<1e-9 and math.abs(CurrentRun.Hero.WeaponRuntime.WeaponBlink.SelfVelocityCap-936)<1e-9,'dash speed did not remount')
assert(CurrentRun.Hero.ManaRegenSources.MacGamingTrainerManaRegen.Value==9,'mana regen did not remount')
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponStaffSwing.ChargeTime-0.625)<1e-9,'attack speed did not remount')

-- Cast availability now mirrors the engine-level multi-fire control properties
-- used by native projected-cast traits, not just WeaponCastAttackDisable.Active.
castEffectActive.WeaponCastAttackDisable=true; castEffectActive.WeaponCastSelfSlow=true; castEffectActive.WeaponCastSelfSlow2=true; activeCastCount=0
castWeaponProperties.IgnoreOwnerAttackDisabled=false
castWeaponProperties.Cooldown=0.25
castWeaponProperties.AllowMultiFireRequest=false
castWeaponProperties.IgnoreForceCooldown=false
castWeaponProperties.ActiveProjectileCap=1
assert(tryCast() and not tryCast(),'mock baseline unexpectedly allowed a second live cast')
activeCastCount=0; SessionMapState.CastAttachedProjectiles={}; SessionMapState.LastCastProjectileId=nil
state=setFeature('instantCastCooldown',true)
assert(not castEffectActive.WeaponCastAttackDisable and not castEffectActive.WeaponCastSelfSlow and not castEffectActive.WeaponCastSelfSlow2 and state.activeFeatures.instantCastCooldown,'cast availability did not arm full native effect group')
assert(castWeaponProperties.IgnoreOwnerAttackDisabled and castWeaponProperties.AllowMultiFireRequest and castWeaponProperties.IgnoreForceCooldown and castWeaponProperties.Cooldown==0 and castWeaponProperties.ActiveProjectileCap==32,'cast multi-fire properties/projectile cap not applied')
assert(tryCast() and tryCast(),'cast availability still blocked the second live cast')
state=M.dispatch('status',{})
assert(state.runtimeDiagnostics.castRuntime.method=='nativeMultiCastControlSet','cast diagnostics method missing')
assert(state.runtimeDiagnostics.castRuntime.weaponGateVerified,'cast diagnostics did not verify engine weapon gate')
assert(state.runtimeDiagnostics.castRuntime.activeTrackedCasts==2,'cast diagnostics did not observe two live casts')
-- Later game writes are forced while enabled but remembered for restoration.
SetWeaponProperty({WeaponName='WeaponCast',DestinationId=CurrentRun.Hero.ObjectId,Property='Cooldown',Value=0.5})
SetEffectProperty({WeaponName='WeaponCast',EffectName='WeaponCastAttackDisable',DestinationId=CurrentRun.Hero.ObjectId,Property='Active',Value=true,ValueChangeType='Absolute'})
SetEffectProperty({WeaponName='WeaponCast',EffectName='WeaponCastSelfSlow',DestinationId=CurrentRun.Hero.ObjectId,Property='Active',Value=true,ValueChangeType='Absolute'})
assert(castWeaponProperties.Cooldown==0 and not castEffectActive.WeaponCastAttackDisable and not castEffectActive.WeaponCastSelfSlow,'cast hooks failed to keep native effect group open')
setFeature('instantCastCooldown',false)
assert(castEffectActive.WeaponCastAttackDisable and castEffectActive.WeaponCastSelfSlow and castEffectActive.WeaponCastSelfSlow2 and castWeaponProperties.Cooldown==0.5,'cast natural properties/effects were not restored')
assert(castWeaponProperties.IgnoreOwnerAttackDisabled==false and castWeaponProperties.AllowMultiFireRequest==false and castWeaponProperties.IgnoreForceCooldown==false and castWeaponProperties.ActiveProjectileCap==1,'cast boolean properties/projectile cap were not restored')
-- A native boon that disables the same gate must remain authoritative when the
-- trainer turns off; never reactivate or undo its multi-fire path.
table.insert(CurrentRun.Hero.Traits,{Name='NativeMultiCastTrait'})
castEffectActive.WeaponCastAttackDisable=false; castEffectActive.WeaponCastSelfSlow=false; castEffectActive.WeaponCastSelfSlow2=false
castWeaponProperties.IgnoreOwnerAttackDisabled=true; castWeaponProperties.AllowMultiFireRequest=true; castWeaponProperties.IgnoreForceCooldown=true; castWeaponProperties.Cooldown=0; castWeaponProperties.ActiveProjectileCap=2
setFeature('instantCastCooldown',true)
setFeature('instantCastCooldown',false)
assert(not castEffectActive.WeaponCastAttackDisable and not castEffectActive.WeaponCastSelfSlow and not castEffectActive.WeaponCastSelfSlow2 and castWeaponProperties.AllowMultiFireRequest and castWeaponProperties.ActiveProjectileCap==2,'cast release overwrote a native multi-cast boon/cap')
table.remove(CurrentRun.Hero.Traits,#CurrentRun.Hero.Traits)

-- Hex readiness uses the equipped Spell trait's actual weapon data/cost and
-- restores both charge and weapon Enabled state after SpellFire.
CurrentRun.SpellCharge=0; weaponEnabled=false; CurrentRun.Hero.Traits[1].RemainingUses=0
state=setFeature('hexAlwaysReady',true)
assert(CurrentRun.SpellCharge==100 and weaponEnabled and CurrentRun.Hero.Traits[1].RemainingUses==1,'hex did not become ready immediately')
SpellFire()
assert(spellFireCalls>0 and CurrentRun.SpellCharge==100 and weaponEnabled and CurrentRun.Hero.Traits[1].RemainingUses==1,'hex did not recover after firing')
UpdateTimers(0.016)
assert(state.desiredFeatures.hexAlwaysReady,'hex desired state lost')
setFeature('hexAlwaysReady',false)

-- A run transition can expose the new Hero before its Spell trait is mounted.
-- Keep the user's desired toggle pending and arm it automatically once the
-- trait arrives; this is the exact reconnect/run-boundary race from live play.
setFeature('hexAlwaysReady',true)
CurrentRun={Hero=hero(250,85,42,0.11),CurrentRoom={},ResourcesGained={},ResourcesSpent={},NumRerolls=0,SpellCharge=0}
CurrentRun.Hero.Traits={}
weaponEnabled=false
UpdateTimers(0.016)
state=M.dispatch('status',{})
assert(state.desiredFeatures.hexAlwaysReady and not state.activeFeatures.hexAlwaysReady,'hex desired state was dropped while Spell trait was pending')
assert(state.runtimeDiagnostics.hexRuntime and state.runtimeDiagnostics.hexRuntime.reason=='noSpell','pending hex state was not diagnosed')
table.insert(CurrentRun.Hero.Traits,{Slot='Spell',Name='SpellMockTrait',PreEquipWeapons={'WeaponSpell'},RemainingUses=0})
UpdateTimers(0.016)
state=M.dispatch('status',{})
assert(state.desiredFeatures.hexAlwaysReady and state.activeFeatures.hexAlwaysReady,'pending hex did not arm after Spell trait appeared')
assert(CurrentRun.SpellCharge==100 and weaponEnabled and CurrentRun.Hero.Traits[1].RemainingUses==1,'pending hex did not restore full readiness')
setFeature('hexAlwaysReady',false)

-- Hex with no Spell is a dormant/deferred state, not a feature error.
CurrentRun.Hero.Traits={}
state=setFeature('hexAlwaysReady',true)
assert(state.desiredFeatures.hexAlwaysReady and state.dormantFeatures.hexAlwaysReady and not state.activeFeatures.hexAlwaysReady,'hex noSpell should be dormant')
assert(state.featureErrors.hexAlwaysReady==nil,'hex noSpell was incorrectly reported as a feature error')
setFeature('hexAlwaysReady',false)
CurrentRun.Hero.Traits={{Slot='Spell',Name='SpellMockTrait',PreEquipWeapons={'WeaponSpell'},RemainingUses=1}}

-- Auto minigames keeps native reward settlement and only forces the success
-- decision/input path for fishing and exorcism.
state=setFeature('autoMiniGames',true)
assert(state.activeFeatures.autoMiniGames and state.runtimeDiagnostics.miniGameHooks.fishing and state.runtimeDiagnostics.miniGameHooks.exorcism,'minigame hooks did not arm')
CurrentRun.Hero.FishingInput=false; CurrentRun.Hero.FishingState='Success'
WaitForFishingInput({FishingAnimationPointId=123})
assert(CurrentRun.Hero.FishingInput==true and fishingOriginalCalls==0,'fishing auto-success did not submit native success input')
assert(ExorcismSequence({}, {}, {}, CurrentRun.Hero)==true and exorcismOriginalCalls==0,'exorcism auto-success failed')
setFeature('autoMiniGames',false)
CurrentRun.Hero.FishingInput=false
WaitForFishingInput({})
assert(fishingOriginalCalls==1,'fishing original path was not restored')
assert(ExorcismSequence({}, {}, {}, CurrentRun.Hero)==false and exorcismOriginalCalls==1,'exorcism original path was not restored')

-- Next-room reward is consumed only when an ordinary reward is being chosen.
state=M.dispatch('set_next_room_reward',{reward='WeaponUpgrade'})
assert(state.nextRoomReward=='WeaponUpgrade' and state.runtimeDiagnostics.nextRoomRewardHook,'next-room reward hook did not arm')
local forcedRoom={Encounter={Name='Encounter'}}
local chosen=ChooseRoomReward(CurrentRun,forcedRoom,'RunProgress',nil,{Door={ObjectId=9001}})
assert(chosen=='WeaponUpgrade' and forcedRoom.Reward.Name=='WeaponUpgrade','next-room ordinary reward override failed')
state=M.dispatch('status',{})
assert(state.nextRoomReward=='WeaponUpgrade' and state.runtimeDiagnostics.nextRoomRewardHook,'next-room reward was consumed before the player entered a door')
local enteredRoom=forcedRoom
StartRoom(CurrentRun,enteredRoom)
state=M.dispatch('status',{})
assert(state.nextRoomReward==nil and not state.runtimeDiagnostics.nextRoomRewardHook,'next-room reward was not consumed after entering the selected room')
state=M.dispatch('set_next_room_reward',{reward='ZeusUpgrade'})
forcedRoom={Encounter={Name='Encounter'}}
chosen=ChooseRoomReward(CurrentRun,forcedRoom,'RunProgress',nil,{Door={ObjectId=9001}})
assert(chosen=='Boon' and forcedRoom.ForceLootName=='ZeusUpgrade','next-room god reward override failed')
M.dispatch('set_next_room_reward',{reward=nil})
M.dispatch('set_next_room_reward',{reward='MetaCurrencyDrop'})
forcedRoom={Encounter={Name='Encounter'}}
chosen=ChooseRoomReward(CurrentRun,forcedRoom,'RunProgress',nil,{Door={ObjectId=9001}})
assert(chosen=='MetaCurrencyDrop' and forcedRoom.Reward.Name=='MetaCurrencyDrop','next-room meta currency reward override failed')
M.dispatch('set_next_room_reward',{reward=nil})

-- If exit rewards were already materialized before the trainer command,
-- every ordinary offered door must be patched immediately and the one-shot
-- still remains armed until the selected room is actually entered.
local originRoom=CurrentRun.CurrentRoom
local offeredA={ChosenRewardType='RoomMoneyDrop',Reward={Name='RoomMoneyDrop'},Encounter={Name='Encounter'}}
local offeredB={ChosenRewardType='MaxManaDrop',Reward={Name='MaxManaDrop'},Encounter={Name='Encounter'}}
MapState.OfferedExitDoors={
  [9101]={ObjectId=9101,Room=offeredA,RewardPreviewIconIds={101}},
  [9102]={ObjectId=9102,Room=offeredB,RewardPreviewIconIds={102}},
}
CurrentRun.CurrentRoom=originRoom
CurrentRun.CurrentRoom.OfferedRewards={}
nextRoomPreviewRefreshes=0
state=M.dispatch('set_next_room_reward',{reward='MaxHealthDrop'})
assert(offeredA.ChosenRewardType=='MaxHealthDrop' and offeredB.ChosenRewardType=='MaxHealthDrop','existing offered doors were not all patched')
assert(CurrentRun.CurrentRoom.OfferedRewards[9101].Type=='MaxHealthDrop' and CurrentRun.CurrentRoom.OfferedRewards[9102].Type=='MaxHealthDrop','offered reward cache was not synchronized')
assert(state.nextRoomReward=='MaxHealthDrop' and state.runtimeDiagnostics.nextRoomRewardPatchedDoors==2,'existing door patch diagnostics are wrong')
assert(nextRoomPreviewRefreshes==2,'existing reward previews were not refreshed in place')
StartRoom(CurrentRun,offeredB)
state=M.dispatch('status',{})
assert(state.nextRoomReward==nil and not state.runtimeDiagnostics.nextRoomRewardHook,'patched next-room reward did not consume on room entry')
MapState.OfferedExitDoors={}

-- Garden QoL uses the game's own multi-plant and harvest-all paths without
-- permanently unlocking the WorldUpgradeGardenHarvestAll upgrade.
state=setFeature('gardenQoL',true)
assert(state.activeFeatures.gardenQoL and state.runtimeDiagnostics.gardenHooks.plant and state.runtimeDiagnostics.gardenHooks.harvest,'garden hooks did not arm')
GardenPlantSeed({}, {}, {})
assert(gardenMultiPlantSeen,'garden QoL did not force native MultiPlant')
GameState.WorldUpgrades.WorldUpgradeGardenHarvestAll=nil
UseGardenPlot({ReadyForHarvest=true}, {}, CurrentRun.Hero)
assert(gardenHarvestAllSeen,'garden QoL did not enable native harvest-all for the call')
assert(GameState.WorldUpgrades.WorldUpgradeGardenHarvestAll==nil,'garden QoL leaked the harvest-all upgrade flag')
setFeature('gardenQoL',false)

-- Persistent boon rarity control multiplies native rarity chances and applies a
-- minimum rarity. Special controls are neutral when off and force a currently
-- eligible Legendary/Duo into the native three-choice pool when on.
state=M.dispatch('set_boon_rarity',{target='Epic',multiplier=200,forceLegendary=false,forceDuo=false})
state=setFeature('boonRarityEnabled',true)
assert(state.activeFeatures.boonRarityEnabled and state.runtimeDiagnostics.boonRarityHooks.chances and state.runtimeDiagnostics.boonRarityHooks.options,'boon rarity hooks did not arm')
local rarity=GetRarityChances({Name='ZeusUpgrade'})
assert(math.abs(rarity.Rare-0.40)<1e-9 and math.abs(rarity.Epic-0.20)<1e-9 and math.abs(rarity.Heroic-0.10)<1e-9,'rarity multiplier did not compose with native chances')
local rarityLoot={Name='ZeusUpgrade',GodLoot=true}
local callsBefore=boonOptionGenerationCalls
SetTraitsOnLoot(rarityLoot,{})
assert(#rarityLoot.UpgradeOptions==3 and rarityLoot.UpgradeOptions[1].Rarity=='Epic' and rarityLoot.UpgradeOptions[2].Rarity=='Legendary' and rarityLoot.UpgradeOptions[3].Rarity=='Duo','special controls off must preserve native Legendary/Duo choices')
assert(boonOptionGenerationCalls==callsBefore+1,'special controls off must not reroll native boon generation')
boonNativeSpecials=false
M.dispatch('set_boon_rarity',{target='Epic',multiplier=200,forceLegendary=true,forceDuo=false})
rarityLoot={Name='ZeusUpgrade',GodLoot=true}; SetTraitsOnLoot(rarityLoot,{})
assert(rarityLoot.UpgradeOptions[3].ItemName=='LegendaryMockBoon' and rarityLoot.UpgradeOptions[3].Rarity=='Legendary','eligible Legendary boon was not forced')
M.dispatch('set_boon_rarity',{target='Epic',multiplier=200,forceLegendary=true,forceDuo=true})
rarityLoot={Name='ZeusUpgrade',GodLoot=true}; SetTraitsOnLoot(rarityLoot,{})
local forcedKinds={}; for _,option in ipairs(rarityLoot.UpgradeOptions) do forcedKinds[option.Rarity]=true end
assert(forcedKinds.Legendary and forcedKinds.Duo and #rarityLoot.UpgradeOptions==3,'eligible Legendary + Duo were not forced into the native three choices')
boonNativeSpecials=true
setFeature('boonRarityEnabled',false)

-- The product no longer exposes boon choice count: the native screen itself is
-- fixed to MaxChoices=3. Compatibility state remains disabled/unsupported.
state=M.dispatch('status',{})
assert(state.featureSupport.boonChoiceEnabled==nil and state.boonChoiceEnabled==nil and state.boonChoiceCount==nil and CalcNumLootChoices({Name='ZeusUpgrade'})==3 and GetTotalLootChoices()==3,'retired boon choice feature still leaks into runtime state')

-- Game speed is now an independent factor layered on top of the game's native
-- minimum-only slowdown system, so acceleration and slowdown both work.
state=M.dispatch('status',{})
assert(state.featureSupport.gameSpeed==true,'direct elapsed game speed capability missing')
state=M.dispatch('set_feature',{feature='gameSpeed',value=2})
assert(state.gameSpeed==2 and state.activeFeatures.gameSpeed,'game speed did not report verified active')
assert(math.abs(_elapsedTimeMultiplier-2)<1e-9 and math.abs(enemyTimeScale-2)<1e-9 and math.abs(heroTimeScale-2)<1e-9 and math.abs(projectileTimeScale-2)<1e-9,'2x game speed did not apply to effective layers')
assert(state.runtimeDiagnostics.gameSpeedMethod=='directElapsedFactor','wrong game speed backend selected')
assert(state.runtimeDiagnostics.gameSpeedHeroBound==true,'game speed did not verify the current Hero binding')
GameplaySetElapsedTimeMultiplier({ElapsedTimeMultiplier=0.5,Name='NativeSlow',ApplyToPlayerUnits=true})
state=M.dispatch('status',{})
assert(math.abs(GetGameplayElapsedTimeMultiplier()-0.5)<1e-9,'native slowdown mock failed')
assert(math.abs(_elapsedTimeMultiplier-1)<1e-9 and math.abs(enemyTimeScale-1)<1e-9 and math.abs(heroTimeScale-1)<1e-9 and math.abs(projectileTimeScale-1)<1e-9,'trainer factor did not compose with native slowdown')
GameplaySetElapsedTimeMultiplier({ElapsedTimeMultiplier=0.5,Reverse=true,Name='NativeSlow',ApplyToPlayerUnits=true})
assert(math.abs(_elapsedTimeMultiplier-2)<1e-9 and math.abs(enemyTimeScale-2)<1e-9 and math.abs(heroTimeScale-2)<1e-9,'native slowdown reversal lost trainer factor')
state=M.dispatch('set_feature',{feature='gameSpeed',value=0.5})
assert(state.activeFeatures.gameSpeed and math.abs(_elapsedTimeMultiplier-0.5)<1e-9 and math.abs(enemyTimeScale-0.5)<1e-9 and math.abs(heroTimeScale-0.5)<1e-9,'0.5x speed did not replace 2x factor')
state=M.dispatch('set_feature',{feature='gameSpeed',value=1})
assert(state.gameSpeed==1 and not state.activeFeatures.gameSpeed and math.abs(_elapsedTimeMultiplier-1)<1e-9 and math.abs(enemyTimeScale-1)<1e-9 and math.abs(heroTimeScale-1)<1e-9,'game speed did not restore')

-- Desired features, ordinary toggles and locks survive a run/hero replacement
-- and remount on the new hero without requiring another UI toggle.
setFeature('instantCastCooldown',true); setFeature('hexAlwaysReady',true); setFeature('infiniteHealth',true)
M.dispatch('set_element',{element='Aether',amount=77})
M.dispatch('lock_element',{element='Aether',locked=true})
M.dispatch('set_resource',{resource='Money',amount=321,requestId='persist-money'})
M.dispatch('lock_resource',{resource='Money',locked=true})
M.dispatch('set_feature',{feature='gameSpeed',value=1.5})

-- The backend prepends hades.lua on every command. Re-loading the same
-- revision must be a no-op, exactly as a debugger detach/reconnect or backend
-- restart in the same Hades process would do.
local residentModule=M
assert(loadfile(projectRoot .. '/Backend/games/hades2/runtime/hades.lua'))()
assert(__MacGamingTrainerV1==residentModule,'same-revision bootstrap replaced resident state')
M=__MacGamingTrainerV1
state=M.dispatch('status',{})
assert(state.desiredFeatures.instantCastCooldown and state.desiredFeatures.hexAlwaysReady and state.desiredFeatures.infiniteHealth,'same-revision bootstrap lost desired toggles')
assert(state.moneyLocked and state.gameSpeed==1.5,'same-revision bootstrap lost locks or speed target')

local persistentOldHero=CurrentRun.Hero
CurrentRun={Hero=hero(303,90,45,0.12),CurrentRoom={},ResourcesGained={},ResourcesSpent={},NumRerolls=0,SpellCharge=0}
-- New room units inherit the process/global elapsed multiplier, while the
-- newly-created Hero starts at its own neutral unit multiplier. This catches
-- accidental reversal of the old run's trainer factor against the new Hero.
enemyTimeScale=_elapsedTimeMultiplier; projectileTimeScale=_elapsedTimeMultiplier; heroTimeScale=CurrentRun.Hero.TimeScale
GameState.Resources.Money=0
castEffectActive.WeaponCastAttackDisable=true; castEffectActive.WeaponCastSelfSlow=true; castEffectActive.WeaponCastSelfSlow2=true; weaponEnabled=false
UpdateTimers(0.016)
state=M.dispatch('status',{})
assert(state.desiredFeatures.instantCastCooldown and state.activeFeatures.instantCastCooldown and not castEffectActive.WeaponCastAttackDisable,'cast feature did not remount across run')
assert(state.desiredFeatures.hexAlwaysReady and state.activeFeatures.hexAlwaysReady and CurrentRun.SpellCharge==100 and weaponEnabled,'hex feature did not remount across run')
assert(state.desiredFeatures.infiniteHealth and state.activeFeatures.infiniteHealth,'ordinary feature did not remount across run')
local aetherAfterRun=nil; for _,row in ipairs(state.elements or {}) do if row.id=='Aether' then aetherAfterRun=row end end
assert(aetherAfterRun and aetherAfterRun.count==77 and aetherAfterRun.locked,'element lock did not persist across run')
assert(state.moneyLocked and GameState.Resources.Money==321,'resource lock did not persist across run')
assert(state.gameSpeed==1.5 and state.activeFeatures.gameSpeed and math.abs(_elapsedTimeMultiplier-1.5)<1e-9,'speed feature did not remount across run')
assert(math.abs(CurrentRun.Hero.TimeScale-1.5)<1e-9 and math.abs(enemyTimeScale-1.5)<1e-9,'speed factor was not rebound exactly once to the new run')
setFeature('instantCastCooldown',false); setFeature('hexAlwaysReady',false); setFeature('infiniteHealth',false)
M.dispatch('lock_element',{element='Aether',locked=false}); M.dispatch('lock_resource',{resource='Money',locked=false})
M.dispatch('set_feature',{feature='gameSpeed',value=1})

-- Next-room override uses current full-release reward identifiers. Direct
-- consumables stay direct, while Selene/god loot goes through Boon+ForceLootName
-- so the native SpawnRoomReward path calls GiveLoot.
state=M.dispatch('set_next_room_reward',{reward='MaxHealthDrop'})
local overrideRoom={Encounter={Name='Combat'}}
local chosen=ChooseRoomReward(CurrentRun,overrideRoom,'RoomRewardStore',nil,{Door={ObjectId=9002}})
assert(chosen=='MaxHealthDrop' and overrideRoom.ChosenRewardType=='MaxHealthDrop' and overrideRoom.Reward.Name=='MaxHealthDrop','current direct next-room override failed')
state=M.dispatch('set_next_room_reward',{reward='SpellDrop'})
overrideRoom={Encounter={Name='Combat'}}
chosen=ChooseRoomReward(CurrentRun,overrideRoom,'RoomRewardStore',nil,{Door={ObjectId=9002}})
assert(chosen=='Boon' and overrideRoom.ChosenRewardType=='Boon' and overrideRoom.ForceLootName=='SpellDrop' and overrideRoom.Reward.ForceLootName=='SpellDrop','Selene next-room override did not use native Boon path')

-- Spawn each supported kind without invoking NPC narrative state.
state=M.dispatch('spawn_reward',{reward='RoomMoneyDrop',requestId='r-money'})
assert(spawnedConsumable=='RoomMoneyDrop' and state.applied,'consumable spawn failed')
state=M.dispatch('spawn_reward',{reward='WeaponUpgrade',requestId='r-hammer'})
assert(spawnedLoot=='WeaponUpgrade' and state.lootObjectId,'loot spawn failed')
state=M.dispatch('spawn_reward',{reward='StackUpgradeTriple',requestId='r-triple-pom'})
assert(spawnedLoot=='StackUpgradeTriple' and loadedPackages.PomTriplePackage,'triple Pom spawn/package load failed')
state=M.dispatch('spawn_reward',{reward='SpellDrop',requestId='r-selene'})
assert(spawnedLoot=='SpellDrop' and loadedPackages.SpellPackage,'Selene spawn/package load failed')
assert(spawnRoomRewardCalls==1 and spellSetupCalls==1 and lastSpawnRoomRewardArgs.RewardOverride=='SpellDrop' and lastSpawnRoomRewardArgs.LootName==nil,'Selene spawn bypassed native room reward/setup path')
state=M.dispatch('spawn_reward',{reward='trait:SupportingFireBoon',requestId='r-artemis'})
assert(grantedTrait=='SupportingFireBoon','special trait grant failed')
local duplicate=M.dispatch('spawn_reward',{reward='WeaponUpgrade',requestId='r-hammer'})
assert(duplicate.duplicate==true,'spawn idempotency failed')

M.dispatch('disable_all',{})
assert(GetMaxMetaUpgradeCost()==30,'grasp hook leaked after disable_all')
assert(math.abs(CurrentRun.Hero.DodgeChance-0.12)<1e-9,'dodge not restored after disable_all')
assert(math.abs(CalculateCritChance(CurrentRun.Hero,nil,nil,{})-0.10)<1e-9,'crit hook leaked after disable_all')
assert(chargeSpeeds.MacGamingTrainerChargeSpeed==nil,'charge speed leaked after disable_all')
assert(math.abs(CurrentRun.Hero.UnitSpeed-400)<1e-9,'move speed leaked after disable_all')
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponSprint.SelfVelocity-500)<1e-9 and math.abs(CurrentRun.Hero.WeaponRuntime.WeaponSprint.SelfVelocityCap-600)<1e-9,'sprint speed leaked after disable_all')
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponBlink.SelfVelocity-650)<1e-9 and math.abs(CurrentRun.Hero.WeaponRuntime.WeaponBlink.SelfVelocityCap-720)<1e-9,'dash speed leaked after disable_all')
assert(CurrentRun.Hero.ManaRegenSources.MacGamingTrainerManaRegen==nil,'mana regen leaked after disable_all')
assert(math.abs(CurrentRun.Hero.WeaponRuntime.WeaponStaffSwing.ChargeTime-1)<1e-9,'attack speed leaked after disable_all')
assert(CalcNumLootChoices({Name='ZeusUpgrade'})==3,'boon choice hook leaked after disable_all')
assert(math.abs(existingEnemy.MaxHealth-100)<1e-9,'enemy health multiplier leaked after disable_all')
state=M.dispatch('status',{})
assert(not state.healthLocked and not state.manaLocked and not state.armorLocked,'vital locks leaked after disable_all')
for _,row in ipairs(state.elements or {}) do assert(not row.locked,'element lock leaked after disable_all') end

-- Crossroads/global-scope regression: save-backed/meta controls and global
-- hooks should work without fabricating a combat Hero. Hero-bound combat
-- features remain desired+dormant and remount when a run returns.
local crossroadsReturnRun=CurrentRun
CurrentHubRoom={Name='Hub_Main'}
CurrentRun=nil
state=M.dispatch('status',{})
assert(state.scene=='crossroads' and state.status=='waiting','crossroads scene was not detected without CurrentRun')
assert(state.capabilities.setFeature and state.capabilities.setStats and state.capabilities.setResource,'crossroads did not expose global-safe capabilities')
assert(state.statAvailable.grasp and not state.statAvailable.dodge and not state.statAvailable.enemyHealth,'crossroads stat availability leaked Hero-only stats')
state=M.dispatch('set_stat',{stat='grasp',locked=true,value=88})
assert(state.stats.grasp.locked and GetMaxMetaUpgradeCost()==88 and GameState.MaxMetaUpgradeCostCache==88,'grasp was not genuinely editable in crossroads')
state=setFeature('gardenQoL',true)
assert(state.activeFeatures.gardenQoL,'garden QoL did not install immediately in crossroads')
state=M.dispatch('set_resource',{resource='GiftPoints',amount=42,requestId='crossroads-gift'})
assert(GameState.Resources.GiftPoints==42,'save-backed resource edit failed in crossroads')
local crossroadsSpentBefore=(GameState.LifetimeResourcesSpent and GameState.LifetimeResourcesSpent.GiftPoints) or 0
state=M.dispatch('set_resource',{resource='GiftPoints',amount=40,requestId='crossroads-gift-spend'})
assert(GameState.Resources.GiftPoints==40 and GameState.LifetimeResourcesSpent.GiftPoints==crossroadsSpentBefore+2,'crossroads resource decrease did not preserve lifetime spend accounting')
state=M.dispatch('lock_resource',{resource='GiftPoints',locked=true})
local giftRow=nil; for _,row in ipairs(state.resources or {}) do if row.id=='GiftPoints' then giftRow=row; break end end
assert(state.capabilities.setResource and giftRow and giftRow.locked,'resource lock did not arm in crossroads')
state=setFeature('moneyMultiplierEnabled',true)
assert(state.activeFeatures.moneyMultiplierEnabled,'economy hook did not install in crossroads')
state=M.dispatch('set_feature',{feature='gameSpeed',value=1.25})
assert(state.activeFeatures.gameSpeed and math.abs(_elapsedTimeMultiplier-1.25)<1e-9,'game speed did not install in crossroads')
state=setFeature('infiniteHealth',true)
assert(state.desiredFeatures.infiniteHealth and state.dormantFeatures.infiniteHealth and not state.activeFeatures.infiniteHealth,'Hero-only feature was not dormant in crossroads')
state=M.dispatch('set_next_room_reward',{reward='WeaponUpgrade'})
assert(state.nextRoomReward=='WeaponUpgrade' and state.runtimeDiagnostics.nextRoomRewardHook,'next-room reward did not arm in crossroads')

CurrentRun=crossroadsReturnRun
CurrentHubRoom=nil
UpdateTimers(0.016)
state=M.dispatch('status',{})
assert(state.activeFeatures.infiniteHealth,'dormant combat feature did not remount when a run returned')
assert(state.activeFeatures.gameSpeed and math.abs(_elapsedTimeMultiplier-1.25)<1e-9,'session-scoped game speed did not survive crossroads-to-run transition')
assert(state.nextRoomReward=='WeaponUpgrade' and state.runtimeDiagnostics.nextRoomRewardHook,'pending next-room reward was lost on crossroads-to-run transition')
local crossroadsForcedRoom={Encounter={Name='Encounter'}}
assert(ChooseRoomReward(CurrentRun,crossroadsForcedRoom,'RunProgress',nil,{Door={ObjectId=9003}})=='WeaponUpgrade' and crossroadsForcedRoom.Reward.Name=='WeaponUpgrade','crossroads next-room reward did not survive into the run')
M.dispatch('disable_all',{})
assert(GetMaxMetaUpgradeCost()==30 and math.abs(_elapsedTimeMultiplier-1)<1e-9,'crossroads global state leaked after disable_all')
print('round10_mock_ok')
