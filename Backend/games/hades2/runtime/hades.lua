-- Loaded before every command. All state is session-local, outside save tables.
-- Reject unsupported runtimes before cleaning up or installing any resident state.
if _VERSION ~= "Lua 5.2" then error("Unsupported Lua ABI: " .. tostring(_VERSION) .. "; Lua 5.2 required") end
for _, name in ipairs({ "SessionState", "GameState" }) do
  if type(_G[name]) ~= "table" then error("Unsupported game runtime: missing table " .. name) end
end
if type(UpdateTimers) ~= "function" then error("Unsupported game runtime: missing UpdateTimers") end
local previousModule = __MacGamingTrainerV1
if previousModule and previousModule.revision ~= 82 then
  local cleanupOk, cleanupMessage = pcall(previousModule.dispatch, "cleanup")
  if not cleanupOk then
    error("MGT_RESIDENT_RESTART_REQUIRED: previous resident cleanup failed: " .. tostring(cleanupMessage))
  end
  __MacGamingTrainerV1 = nil
end
if __MacGamingTrainerV1 == nil then
  local M = {
    version = 1, revision = 82, damageMultiplier = 2, damageEnabled = false,
    invincibility = false, invincibilityHitHero = nil, invincibilityHitBaseline = nil, invincibilityHitBaselineKnown = false, infiniteHealth = false, infiniteMana = false,
    instantCastCooldown = false, hexAlwaysReady = false, infiniteAmmo = false, autoMiniGames = false, gardenQoL = false, boonRarityEnabled = false,
    moneyMultiplier = 2, moneyMultiplierEnabled = false,
    resourceMultiplier = 2, resourceMultiplierEnabled = false,
    -- true means force one currently eligible special boon into the native pool.
    boonRarityTarget = "Epic", boonRarityMultiplier = 1, boonForceLegendary = false, boonForceDuo = false,
    nextRoomReward = nil, nextRoomRewardToken = nil, lastConsumedNextRoomRewardToken = nil,
    nextRoomRewardOriginRoom = nil, nextRoomRewardPatchedDoors = 0, nextRoomRewardPatchedValue = nil, nextRoomRewardPatchRoom = nil,
    desiredFeatures = {
      invincibility = false, infiniteHealth = false, infiniteMana = false, damageEnabled = false,
      instantCastCooldown = false, hexAlwaysReady = false, infiniteAmmo = false, autoMiniGames = false, gardenQoL = false, boonRarityEnabled = false,
      moneyMultiplierEnabled = false, resourceMultiplierEnabled = false,
    },
    resourceLocks = {}, vitalLocks = {}, elementLocks = {}, statTargets = {}, statRuntime = {}, hooks = {}, featureErrors = {}, gatheringProbabilities = {},
    catalogCache = {}, specialChoiceOpens = {}, specialChoiceRun = nil,
    requests = previousModule and previousModule.requests or {},
    requestOrder = previousModule and previousModule.requestOrder or {},
    lastActionReceipt = previousModule and previousModule.terminalActionUnknown and previousModule.lastActionReceipt or nil,
    terminalActionUnknown = previousModule and previousModule.terminalActionUnknown or false,
    -- Ephemeral install identity used only to reject stale UI selections. It is
    -- intentionally neither saved nor carried across a resident replacement.
    traitInventoryGeneration = tostring({}),
  }
  __MacGamingTrainerV1 = M
  local choiceReroll, roomGeneration
  local preferenceReplayDepth = 0

  -- Resource DisplayName values from build 1.139672 Game/Text/zh-CN/HelpText.zh-CN.sjson.
  local names = {
    Money = "金币",
    CosmeticsPoints = "声望",
    DreamPoints = "闪亮星星",
    TrashPoints = "垃圾",
    MetaCardPointsCommon = "尘灰",
    MemPointsCommon = "魂魄",
    MetaCurrency = "骨骸",
    SeedMystery = "神秘种子",
    PlantFMoly = "摩吕草",
    PlantFNightshadeSeed = "颠茄种子",
    PlantFNightshade = "颠茄",
    OreFSilver = "银矿",
    FishFCommon = "怨艾鱼",
    FishFRare = "残像鱼",
    FishFLegendary = "魂腹鱼",
    MetaFabric = "命运丝线",
    GiftPoints = "蜜露",
    GiftPointsRare = "浴盐",
    GiftPointsEpic = "双份鱼饵",
    SuperGiftPoints = "仙酒",
    MixerFBoss = "余烬",
    PlantNMoss = "青苔",
    PlantNGarlicSeed = "蒜瓣",
    PlantNGarlic = "大蒜",
    OreNBronze = "青铜",
    FishNCommon = "肋眼鱼",
    FishNRare = "丧鳗",
    FishNLegendary = "噬颈鲨",
    MixerNBoss = "羊毛",
    PlantGLotus = "莲花",
    PlantGCattailSeed = "香蒲种子",
    PlantGCattail = "香蒲",
    OreGLime = "石灰岩",
    FishGCommon = "石鳖",
    FishGRare = "渠鼻鱼",
    FishGLegendary = "潜鳍鱼",
    MixerGBoss = "珍珠",
    PlantHMyrtle = "香桃木",
    PlantHWheatSeed = "小麦种子",
    PlantHWheat = "小麦",
    OreHGlassrock = "曜石",
    FishHCommon = "抽泣鱼",
    FishHRare = "煎熬鱼",
    FishHLegendary = "泪海马",
    MixerHBoss = "泪珠",
    PlantODriftwood = "浮木",
    PlantOMandrakeSeed = "曼德拉草种子",
    PlantOMandrake = "曼德拉草",
    OreOIron = "铁矿",
    FishOCommon = "虾",
    FishORare = "寄居蟹",
    FishOLegendary = "鱿鱼",
    MixerOBoss = "金苹果",
    PlantPIris = "鸢尾花",
    PlantPOliveSeed = "橄榄枝",
    PlantPOlive = "橄榄",
    OrePAdamant = "精金",
    FishPCommon = "柱头蟹",
    FishPRare = "冠顶龟",
    FishPLegendary = "星航鱼",
    MixerPBoss = "羽毛",
    PlantIShaderot = "糜影草",
    PlantIPoppySeed = "罂粟种子",
    PlantIPoppy = "罂粟",
    OreIMarble = "大理石",
    FishICommon = "瞬息鱼",
    FishIRare = "金鱼",
    FishILegendary = "冥古鱼",
    MixerIBoss = "玄象砂",
    PlantQFang = "尖牙",
    PlantQSnakereedSeed = "浮游植物",
    PlantQSnakereed = "蛇苇",
    OreQScales = "蛇鳞",
    FishQCommon = "七鳃鳗",
    FishQRare = "风暴喉",
    FishQLegendary = "奇美鱼",
    MixerQBoss = "虚空之眼",
    OreChaosProtoplasm = "混沌质",
    PlantChaosThalamusSeed = "原初种子",
    PlantChaosThalamus = "混沌苞蕾",
    FishChaosCommon = "马蒂鱼",
    FishChaosRare = "源祖水母",
    FishChaosLegendary = "虚空鳐",
    CharonPoints = "奥波勒斯信用点",
    FamiliarPoints = "女巫之宝",
    CardUpgradePoints = "月尘",
    Mixer5Common = "星尘",
    Mixer6Common = "黑暗",
    IcarusPoints = "灵质秘药",
    MedeaPoints = "泪珠蒸汽",
    HypnosPoints = "梦雾",
    DeathAreaPoints = "冥府煤灰",
    MixerShadow = "暗影",
    WeaponPointsRare = "梦魇",
    GemPoints = "宝石",
    HadesSpearPoints = "吉加罗斯",
    MixerMythic = "熵",
    MysteryResource = "？？？",
  }
  local arrayMeta = { __trainerJSONArray = true }
  local jsonNull = {}
  local function finite(n)
    return type(n) == "number" and n == n and n ~= math.huge and n ~= -math.huge
  end
  local function number(n) return finite(n) and n or 0 end
  local function quote(s)
    return '"' .. string.gsub(s, '[%z\1-\31\\"]', function(c)
      local escapes = { ['"'] = '\\"', ['\\'] = '\\\\', ['\n'] = '\\n',
        ['\r'] = '\\r', ['\t'] = '\\t', ['\b'] = '\\b', ['\f'] = '\\f' }
      return escapes[c] or string.format('\\u%04x', string.byte(c))
    end) .. '"'
  end
  function M.json(value)
    local seen = {}
    local function encode(v)
      local kind = type(v)
      if kind == "nil" or v == jsonNull then return "null" end
      if kind == "boolean" then return v and "true" or "false" end
      if kind == "number" then
        if not finite(v) then error("Non-finite JSON number") end
        return tostring(v)
      end
      if kind == "string" then return quote(v) end
      if kind ~= "table" then error("Unsupported JSON value") end
      if seen[v] then error("Cyclic JSON table") end
      seen[v] = true
      local out = {}
      if getmetatable(v) == arrayMeta then
        for i = 1, #v do out[#out + 1] = encode(v[i]) end
        seen[v] = nil
        return "[" .. table.concat(out, ",") .. "]"
      end
      local keys = {}
      for key in pairs(v) do
        if type(key) ~= "string" then error("JSON object keys must be strings") end
        keys[#keys + 1] = key
      end
      table.sort(keys)
      for _, key in ipairs(keys) do out[#out + 1] = quote(key) .. ":" .. encode(v[key]) end
      seen[v] = nil
      return "{" .. table.concat(out, ",") .. "}"
    end
    return encode(value)
  end

  -- Catalog order is semantic, not alphabetical.  The numeric sort keys are
  -- protocol data so the UI can preserve game/family order without re-sorting
  -- localized strings.  Within dynamic NPC boon groups, array order from the
  -- game's UnitSetData is kept whenever the game provides one.
  local boonDefinitions = {
    -- Fallback mirrors CodexOrdering.OlympianGods from the current game. Runtime
    -- Codex order takes precedence below when available.
    { id = "ZeusUpgrade", name = "宙斯", order = 10 },
    { id = "HeraUpgrade", name = "赫拉", order = 20 },
    { id = "PoseidonUpgrade", name = "波塞冬", order = 30 },
    { id = "DemeterUpgrade", name = "得墨忒尔", order = 40 },
    { id = "ApolloUpgrade", name = "阿波罗", order = 50 },
    { id = "AphroditeUpgrade", name = "阿弗洛狄忒", order = 60 },
    { id = "HephaestusUpgrade", name = "赫菲斯托斯", order = 70 },
    { id = "HestiaUpgrade", name = "赫斯提亚", order = 80 },
    { id = "AresUpgrade", name = "阿瑞斯", order = 90 },
    { id = "HermesUpgrade", name = "赫尔墨斯", order = 130 },
  }
  local rewardDefinitions = {
    -- Curated ordering for common room rewards.  Runtime discovery below adds
    -- any current/future RewardStoreData entries we do not know about yet.
    { id = "RoomMoneyTinyDrop", name = "少量金币", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "money", familyOrder = 10, itemOrder = 5 },
    { id = "RoomMoneySmallDrop", name = "小份金币", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "money", familyOrder = 10, itemOrder = 8 },
    { id = "RoomMoneyDrop", name = "金币", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "money", familyOrder = 10, itemOrder = 10 },
    { id = "RoomMoneyBigDrop", name = "大量金币", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "money", familyOrder = 10, itemOrder = 20 },
    { id = "RoomMoneyTripleDrop", name = "三份金币", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "money", familyOrder = 10, itemOrder = 30 },
    { id = "MaxHealthDropSmall", name = "小型半人马之心", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "centaurHeart", familyOrder = 20, itemOrder = 10 },
    { id = "MaxHealthDrop", name = "半人马之心", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "centaurHeart", familyOrder = 20, itemOrder = 20 },
    { id = "MaxHealthDropBig", name = "超级半人马之心", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "centaurHeart", familyOrder = 20, itemOrder = 30 },
    { id = "EmptyMaxHealthSmallDrop", name = "小型半人马之魂", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "centaurSoul", familyOrder = 22, itemOrder = 10 },
    { id = "EmptyMaxHealthDrop", name = "半人马之魂", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "centaurSoul", familyOrder = 22, itemOrder = 20 },
    { id = "MaxManaDropSmall", name = "小型灵魂之水", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "soulTonic", familyOrder = 25, itemOrder = 10 },
    { id = "MaxManaDrop", name = "灵魂之水", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "soulTonic", familyOrder = 25, itemOrder = 20 },
    { id = "MaxManaDropBig", name = "超级灵魂之水", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "soulTonic", familyOrder = 25, itemOrder = 30 },
    { id = "RoomRewardHealDrop", name = "新鲜食粮", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "healing", familyOrder = 27, itemOrder = 10 },
    { id = "HealBigDrop", name = "超大份新鲜食粮", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "healing", familyOrder = 27, itemOrder = 20 },
    { id = "HealDropMajor", name = "大型生命恢复", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "healing", familyOrder = 27, itemOrder = 30 },
    { id = "HealDrop", name = "治疗", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "healing", familyOrder = 27, itemOrder = 32 },
    { id = "HealDropMinor", name = "少量治疗", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "healing", familyOrder = 27, itemOrder = 34 },
    { id = "RoomRewardConsolationPrize", name = "红洋葱", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "healing", familyOrder = 27, itemOrder = 40 },
    { id = "ArmorBoost", name = "护盾饰符", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "armor", familyOrder = 28, itemOrder = 10 },
    { id = "ArmorBigBoost", name = "埃癸斯饰符", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "armor", familyOrder = 28, itemOrder = 20 },
    { id = "ChaosWeaponUpgrade", name = "命运铁砧", category = "商店商品", kind = "consumable", group = "pickup", family = "shop", familyOrder = 80, itemOrder = 10 },
    { id = "BlindBoxLoot", name = "神秘祝福", category = "商店商品", kind = "consumable", group = "pickup", family = "shop", familyOrder = 80, itemOrder = 20 },
    { id = "RandomLoot", name = "随机奥林匹斯祝福", category = "商店商品", kind = "consumable", group = "pickup", family = "shop", familyOrder = 80, itemOrder = 30, spawnMode = "random_loot" },
    { id = "BoostedRandomLoot", name = "强化随机祝福", category = "商店商品", kind = "consumable", group = "pickup", family = "shop", familyOrder = 80, itemOrder = 40, spawnMode = "boosted_random_loot" },
    { id = "WeaponUpgradeDrop", name = "狄德勒斯之锤", category = "商店商品", kind = "consumable", group = "pickup", family = "shop", familyOrder = 80, itemOrder = 50, spawnMode = "weapon_loot" },
    { id = "ShopHermesUpgrade", name = "赫尔墨斯的祝福", category = "商店商品", kind = "consumable", group = "pickup", family = "shop", familyOrder = 80, itemOrder = 60, spawnMode = "hermes_loot" },
    { id = "ArmorBoostStore", name = "碎裂之盾", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 10 },
    { id = "DamageSelfDrop", name = "迈达斯的代价", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 20 },
    { id = "EmptyMaxHealthShopItem", name = "半人马之魂", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 30 },
    { id = "HealDropRange", name = "生命的精华", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 40 },
    { id = "LastStandShopItem", name = "冥河之吻", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 50 },
    { id = "LimitedManaRegenDrop", name = "薄雾面纱", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 60 },
    { id = "LimitedSwapTraitDrop", name = "牺牲圣诗", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 70 },
    { id = "MemPointsCommonRange", name = "摇曳的微光", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 80 },
    { id = "MetaCardPointsCommonRange", name = "积灰的袋子", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 90 },
    { id = "MetaCurrencyRange", name = "出土的遗骸", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 100 },
    { id = "RandomStoreItem", name = "命运的作弄", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 110 },
    { id = "SeedMysteryRange", name = "盖亚的礼赠", category = "卡戎之井", kind = "consumable", group = "pickup", family = "well", familyOrder = 85, itemOrder = 120 },
    { id = "trait:ExtendedShopTrait", trait = "ExtendedShopTrait", name = "古老的封印", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 200, storeTrait = true },
    { id = "trait:FirstHitHealTrait", trait = "FirstHitHealTrait", name = "厄洛斯之息", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 210, storeTrait = true },
    { id = "trait:TemporaryBoonRarityTrait", trait = "TemporaryBoonRarityTrait", name = "阿里阿德涅的纱线", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 220, storeTrait = true },
    { id = "trait:TemporaryDiscountTrait", trait = "TemporaryDiscountTrait", name = "渡船优惠券", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 230, storeTrait = true },
    { id = "trait:TemporaryDoorHealTrait", trait = "TemporaryDoorHealTrait", name = "九头蛇轻饮", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 240, storeTrait = true },
    { id = "trait:TemporaryEmptySlotDamageTrait", trait = "TemporaryEmptySlotDamageTrait", name = "达那伊德斯的匕首", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 250, storeTrait = true },
    { id = "trait:TemporaryForcedSecretDoorTrait", trait = "TemporaryForcedSecretDoorTrait", name = "伊克西翁之耀", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 260, storeTrait = true },
    { id = "trait:TemporaryHealExpirationTrait", trait = "TemporaryHealExpirationTrait", name = "善意之瓶", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 270, storeTrait = true },
    { id = "trait:TemporaryImprovedCastTrait", trait = "TemporaryImprovedCastTrait", name = "阿特拉斯的穗带", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 280, storeTrait = true },
    { id = "trait:TemporaryImprovedDefenseTrait", trait = "TemporaryImprovedDefenseTrait", name = "蟒蛇的鳞片", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 290, storeTrait = true },
    { id = "trait:TemporaryImprovedExTrait", trait = "TemporaryImprovedExTrait", name = "女巫的印记", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 300, storeTrait = true },
    { id = "trait:TemporaryImprovedSecondaryTrait", trait = "TemporaryImprovedSecondaryTrait", name = "奇美拉肉干", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 310, storeTrait = true },
    { id = "trait:TemporaryMoveSpeedTrait", trait = "TemporaryMoveSpeedTrait", name = "燃烧的灵液", category = "卡戎之井", kind = "trait", group = "pickup", family = "well", familyOrder = 85, itemOrder = 320, storeTrait = true },
    { id = "WeaponUpgrade", name = "狄德勒斯之锤", category = "资源与常规掉落", kind = "loot", group = "pickup", family = "hammer", familyOrder = 30, itemOrder = 10 },
    { id = "StackUpgrade", name = "力量石榴", category = "资源与常规掉落", kind = "loot", group = "pickup", family = "pom", familyOrder = 40, itemOrder = 10 },
    { id = "StackUpgradeBig", name = "超级力量石榴", category = "资源与常规掉落", kind = "loot", group = "pickup", family = "pom", familyOrder = 40, itemOrder = 20 },
    { id = "StackUpgradeTriple", name = "究极力量石榴", category = "资源与常规掉落", kind = "loot", group = "pickup", family = "pom", familyOrder = 40, itemOrder = 30 },
    { id = "StoreRewardRandomStack", name = "随机祝福强化", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "pom", familyOrder = 40, itemOrder = 40 },
    { id = "RerollDrop", name = "重塑命运", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "utility", familyOrder = 45, itemOrder = 10 },
    { id = "LastStandDrop", name = "冥河之吻", category = "资源与常规掉落", kind = "consumable", group = "pickup", family = "utility", familyOrder = 45, itemOrder = 20 },
    { id = "MinorTalentDrop", name = "黯淡繁星之路", category = "角色奖励", kind = "consumable", group = "special", family = "Selene", familyOrder = 10, itemOrder = 20, sourceId = "Selene", sourceName = "塞勒涅" },
    { id = "TalentDrop", name = "繁星之路", category = "角色奖励", kind = "consumable", group = "special", family = "Selene", familyOrder = 10, itemOrder = 30, sourceId = "Selene", sourceName = "塞勒涅" },
    { id = "TalentBigDrop", name = "闪耀繁星之路", category = "角色奖励", kind = "consumable", group = "special", family = "Selene", familyOrder = 10, itemOrder = 40, sourceId = "Selene", sourceName = "塞勒涅" },
    { id = "GiftDrop", name = "蜜露", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "meta", familyOrder = 60, itemOrder = 10 },
    { id = "MetaCurrencyDrop", name = "骨骸", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "meta", familyOrder = 60, itemOrder = 20 },
    { id = "MetaCurrencyBigDrop", name = "大量骨骸", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "meta", familyOrder = 60, itemOrder = 25 },
    { id = "MetaCardPointsCommonDrop", name = "尘灰", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "meta", familyOrder = 60, itemOrder = 30 },
    { id = "MetaCardPointsCommonBigDrop", name = "大量尘灰", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "meta", familyOrder = 60, itemOrder = 35 },
    { id = "MemPointsCommonDrop", name = "魂魄", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "meta", familyOrder = 60, itemOrder = 40 },
    { id = "MemPointsCommonBigDrop", name = "大量魂魄", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "meta", familyOrder = 60, itemOrder = 45 },
    { id = "OreFSilverDrop", name = "银矿", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaHarvest", familyOrder = 62, itemOrder = 10 },
    { id = "PlantFMolyDrop", name = "摩吕草", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaHarvest", familyOrder = 62, itemOrder = 20 },
    { id = "PlantFNightshadeDrop", name = "颠茄", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaHarvest", familyOrder = 62, itemOrder = 30 },
    { id = "PlantGLotusDrop", name = "莲花", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaHarvest", familyOrder = 62, itemOrder = 40 },
    { id = "MetaFabricDrop", name = "命运丝线", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaHarvest", familyOrder = 62, itemOrder = 50 },
    { id = "TrashPointsDrop", name = "垃圾", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaHarvest", familyOrder = 62, itemOrder = 60 },
    { id = "SeedMysteryDrop", name = "神秘种子", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaHarvest", familyOrder = 62, itemOrder = 70 },
    { id = "MixerFBossDrop", name = "余烬", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaBoss", familyOrder = 64, itemOrder = 10 },
    { id = "MixerGBossDrop", name = "珍珠", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaBoss", familyOrder = 64, itemOrder = 20 },
    { id = "MixerHBossDrop", name = "泪珠", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaBoss", familyOrder = 64, itemOrder = 30 },
    { id = "MixerIBossDrop", name = "玄象砂", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaBoss", familyOrder = 64, itemOrder = 40 },
    { id = "MixerNBossDrop", name = "羊毛", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaBoss", familyOrder = 64, itemOrder = 50 },
    { id = "MixerOBossDrop", name = "金苹果", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaBoss", familyOrder = 64, itemOrder = 60 },
    { id = "MixerPBossDrop", name = "羽毛", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaBoss", familyOrder = 64, itemOrder = 70 },
    { id = "MixerQBossDrop", name = "虚空之眼", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaBoss", familyOrder = 64, itemOrder = 80 },
    { id = "MixerMythicDrop", name = "熵", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaBoss", familyOrder = 64, itemOrder = 85 },
    { id = "Mixer5CommonDrop", name = "星尘", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaBoss", familyOrder = 64, itemOrder = 90 },
    { id = "Mixer6CommonDrop", name = "黑暗", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaBoss", familyOrder = 64, itemOrder = 100 },
    { id = "WeaponPointsRareDrop", name = "梦魇", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaAdvanced", familyOrder = 66, itemOrder = 10 },
    { id = "CardUpgradePointsDrop", name = "月尘", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaAdvanced", familyOrder = 66, itemOrder = 20 },
    { id = "FamiliarPointsDrop", name = "女巫之宝", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaAdvanced", familyOrder = 66, itemOrder = 30 },
    { id = "CharonPointsDrop", name = "奥波勒斯信用点", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaAdvanced", familyOrder = 66, itemOrder = 40 },
    { id = "GemPointsDrop", name = "宝石", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaAdvanced", familyOrder = 66, itemOrder = 50 },
    { id = "GemPointsBigDrop", name = "大量宝石", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaAdvanced", familyOrder = 66, itemOrder = 60 },
    { id = "DreamPointsDrop", name = "闪亮星星", category = "局外资源奖励", kind = "consumable", group = "pickup", family = "metaAdvanced", familyOrder = 66, itemOrder = 70 },
    { id = "FireBoost", name = "火元素精华", category = "元素奖励", kind = "consumable", group = "pickup", family = "element", familyOrder = 70, itemOrder = 10 },
    { id = "WaterBoost", name = "水元素精华", category = "元素奖励", kind = "consumable", group = "pickup", family = "element", familyOrder = 70, itemOrder = 20 },
    { id = "EarthBoost", name = "土元素精华", category = "元素奖励", kind = "consumable", group = "pickup", family = "element", familyOrder = 70, itemOrder = 30 },
    { id = "AirBoost", name = "风元素精华", category = "元素奖励", kind = "consumable", group = "pickup", family = "element", familyOrder = 70, itemOrder = 40 },
    { id = "ElementalBoost", name = "元素精华", category = "元素奖励", kind = "consumable", group = "pickup", family = "element", familyOrder = 70, itemOrder = 50 },
    { id = "SpellDrop", name = "月之礼赠", category = "角色奖励", kind = "loot", group = "special", family = "Selene", familyOrder = 10, itemOrder = 10, sourceId = "Selene", sourceName = "塞勒涅" },
    { id = "TrialUpgrade", name = "卡俄斯的祝福", category = "角色奖励", kind = "loot", group = "special", family = "Chaos", familyOrder = 20, itemOrder = 10, sourceId = "Chaos", sourceName = "卡俄斯" },
  }
  local elementNames = { Fire = "火", Water = "水", Earth = "土", Air = "风", Aether = "以太" }
  local specialSourceDefinitions = {
    { id = "Artemis", name = "阿尔忒弥斯", order = 30 },
    { id = "Athena", name = "雅典娜", order = 40 },
    { id = "Dionysus", name = "迪奥尼索司", order = 50 },
    { id = "Echo", name = "回声", order = 60 },
    { id = "Hades", name = "哈迪斯", order = 70 },
    { id = "Narcissus", name = "纳西索斯", order = 80 },
    { id = "Circe", name = "喀耳刻", order = 90 },
    { id = "Icarus", name = "伊卡洛斯", order = 100 },
    { id = "Medea", name = "美狄亚", order = 110 },
    { id = "Arachne", name = "阿拉克涅", order = 120 },
  }
  local nativeSpecialChoiceDefinitions = {
    Artemis = { npc = "NPC_Artemis_Field_01", mode = "loot" },
    Athena = { npc = "NPC_Athena_01", mode = "loot" },
    Dionysus = { npc = "NPC_Dionysus_01", mode = "loot" },
    Hades = { npc = "NPC_Hades_Field_01", mode = "loot" },
    Arachne = { npc = "NPC_Arachne_01", choices = "ArachneCostumeChoices", post = "costume" },
    Narcissus = { npc = "NPC_Narcissus_01", choices = "NarcissusBenefitChoices" },
    Echo = { npc = "NPC_Echo_01", choices = "EchoBenefitChoices", rarity = "Epic", echoLastReward = true },
    Medea = { npc = "NPC_Medea_01", choices = "MedeaCurseChoices" },
    Circe = { npc = "NPC_Circe_01", choices = "CirceBlessingChoices", circe = true },
    Icarus = { npc = "NPC_Icarus_01", choices = "IcarusBenefitChoices" },
  }
  local nativeSpecialChoiceSources = {}
  for sourceId in pairs(nativeSpecialChoiceDefinitions) do nativeSpecialChoiceSources[sourceId] = true end
  local nativeChoiceOnlyTraits = {
    EchoLastRunBoon = true,
  }

  local specialTraitSources, specialTraitSourceOrder = {}, {}
  for _, source in ipairs(specialSourceDefinitions) do
    specialTraitSources[source.id] = source.name
    specialTraitSourceOrder[source.id] = source.order
  end
  local trainerSource = "MacGamingTrainer"
  local trainerInvincibilityFlag = "MacGamingTrainerInvincibility"
  local invincibilityBlockedEffects = {
    "HecatePolymorphStun",
    "MiasmaSlow",
  }
  local function requireFunctions(label, functions)
    for _, name in ipairs(functions) do
      if type(_G[name]) ~= "function" then error("Unsupported " .. label .. ": missing " .. name) end
    end
  end

  function MacGamingTrainerCloseSellTraitScreen(screen, button)
    if type(CurrentRun) == "table"
        and type(CurrentRun.CurrentRoom) == "table"
        and type(CurrentRun.CurrentRoom.Store) == "table"
        and type(CurrentRun.CurrentRoom.Store.StoreOptions) == "table"
        and type(CloseStoreScreen) == "function" then
      return CloseStoreScreen(screen, button)
    end

    local components = type(screen) == "table" and screen.Components or nil
    if type(components) ~= "table" then return end
    local purchaseIds = {}
    for name, component in pairs(components) do
      if type(name) == "string" and name:match("^PurchaseButton%d+$")
          and type(component) == "table" and component.Id ~= nil then
        purchaseIds[#purchaseIds + 1] = component.Id
      end
    end
    UseableOff({ Ids = purchaseIds })
    AltAspectRatioFramesHide()
    OnScreenCloseStarted(screen)
    if screen.CloseAnimationName and components.ShopBackground then
      SetAnimation({ Name = screen.CloseAnimationName, DestinationId = components.ShopBackground.Id })
    end
    CloseScreen(GetAllIds(screen.Components), 0.15)
    OnScreenCloseFinished(screen)
    ShowCombatUI(screen.Name)
    SetPlayerVulnerable(screen.Name)
  end

  local function sceneName()
    if type(CurrentHubRoom) == "table" then return "crossroads" end
    if type(CurrentRun) == "table" and type(CurrentRun.Hero) == "table"
        and CurrentRun.Hero.ObjectId ~= nil and not CurrentRun.Hero.IsDead then
      if type(CurrentRun.CurrentRoom) == "table" then return "run" end
      return "loading"
    end
    return "main_menu"
  end
  local function ready()
    local room = type(CurrentHubRoom) == "table" and CurrentHubRoom
      or (type(CurrentRun) == "table" and CurrentRun.CurrentRoom or nil)
    return type(CurrentRun) == "table" and type(CurrentRun.Hero) == "table"
      and CurrentRun.Hero.ObjectId ~= nil and not CurrentRun.Hero.IsDead
      and type(room) == "table"
      and finite(CurrentRun.Hero.Health) and finite(CurrentRun.Hero.Mana)
  end
  local function resourceCatalogReady()
    return type(ResourceData) == "table" and type(ResourceDisplayOrderData) == "table"
      and type(GameState) == "table" and type(GameState.Resources) == "table"
      and type(GameState.LifetimeResourcesGained) == "table"
  end
  local function resourceRunAccountingReady()
    -- Native AddResource and SpendResource update separate per-run ledgers.
    -- Only use those native paths when both ledgers exist; otherwise a hub
    -- resource decrease can fault while indexing CurrentRun.ResourcesSpent.
    return type(CurrentRun) == "table" and type(CurrentRun.ResourcesGained) == "table"
      and type(CurrentRun.ResourcesSpent) == "table"
  end
  local function resourceReady()
    -- Inventory resources live in GameState rather than on the combat Hero.
    -- In the Crossroads they can therefore be edited directly even when there
    -- is no live run object to receive AddResource/SpendResource accounting.
    return resourceCatalogReady() and (resourceRunAccountingReady() or sceneName() == "crossroads")
  end
  local function economyReady()
    -- Multiplier/lock hooks are global function hooks and can be installed in
    -- the hub before a run exists. The native functions will receive a valid
    -- CurrentRun whenever the game actually awards/spends a resource.
    return resourceCatalogReady() and type(AddResource) == "function" and type(SpendResource) == "function"
  end
  local function requireResources()
    if not resourceCatalogReady() then
      error("Unsupported resource editing: resource tables unavailable")
    end
  end
  local function restoreFlag(record)
    if record and record.owner[record.key] == true then record.owner[record.key] = record.previous end
  end
  local function acquireFlag(key)
    local record = { owner = SessionState, key = key, previous = SessionState[key] }
    SessionState[key] = true
    return record
  end
  local function owns(name)
    local hook = M.hooks[name]
    return hook ~= nil and _G[name] == hook.wrapper and hook.ownerSession == SessionState
  end
  local function releaseHook(name)
    local hook = M.hooks[name]
    if hook and _G[name] == hook.wrapper then _G[name] = hook.original end
    M.hooks[name] = nil
  end
  local function installHook(name, body, scope)
    if owns(name) then return end
    local original = _G[name]
    local hook = { original = original }
    local ownerRun = CurrentRun
    local ownerHero = type(ownerRun) == "table" and ownerRun.Hero or nil
    local ownerSession = SessionState
    hook.ownerSession = ownerSession
    -- Most combat hooks intentionally die with their Hero/run. Global-safe
    -- hooks installed while no Hero exists (Crossroads) are session-scoped;
    -- an explicit scope can opt into the same behavior. synchronize() still
    -- releases/reconciles them on scene transitions, so no stale state crosses
    -- sessions.
    local sessionScoped = scope == "session" or type(ownerHero) ~= "table"
    hook.scope = sessionScoped and "session" or "run"
    hook.wrapper = function(...)
      local active = M.hooks[name] == hook and SessionState == ownerSession
      if active and not sessionScoped then
        active = CurrentRun == ownerRun and type(CurrentRun) == "table"
          and CurrentRun.Hero == ownerHero and not ownerHero.IsDead
      end
      if active then return body(original, ...) end
      return original(...)
    end
    M.hooks[name] = hook
    _G[name] = hook.wrapper
  end
  local function refreshHealth()
    if type(UpdateHealthUI) == "function" then pcall(UpdateHealthUI)
    elseif type(FrameState) == "table" then FrameState.RequestUpdateHealthUI = true end
  end
  local function refreshMana()
    UpdateWeaponMana(0, { ForceCheck = true })
    UpdateManaMeterUI()
  end
  local function refreshMoney()
    if type(UpdateMoneyUI) == "function" then UpdateMoneyUI(true) end
  end
  local function releaseHeroDamageRouterIfUnused()
    if not M.invincibility and not M.infiniteHealth and M.statTargets.enemyDamage == nil then releaseHook("Damage") end
  end
  local function restoreInvincibilityHitCount(hero)
    if M.invincibilityHitBaselineKnown and M.invincibilityHitHero == hero and type(hero) == "table" then
      hero.Hits = M.invincibilityHitBaseline
    end
  end
  local function releaseInvincibility()
    restoreInvincibilityHitCount(M.invincibilityHitHero)
    M.invincibilityHitHero = nil
    M.invincibilityHitBaseline = nil
    M.invincibilityHitBaselineKnown = false
    M.invincibility = false
    local effectHero = M.invincibilityEffectBlockHero
    if effectHero and effectHero.ObjectId ~= nil and type(RemoveEffectBlock) == "function" then
      for _, effectName in ipairs(invincibilityBlockedEffects) do
        pcall(RemoveEffectBlock, { Id = effectHero.ObjectId, Name = effectName })
      end
    end
    M.invincibilityEffectBlockHero = nil
    local hero = M.invincibilityHero
    if hero and type(hero.InvulnerableFlags) == "table" and hero.InvulnerableFlags[trainerInvincibilityFlag] then
      if type(SetUnitVulnerable) == "function" then
        pcall(SetUnitVulnerable, hero, trainerInvincibilityFlag)
      else
        hero.InvulnerableFlags[trainerInvincibilityFlag] = nil
      end
    end
    M.invincibilityHero = nil
    releaseHeroDamageRouterIfUnused()
  end
  local function releaseHealth()
    M.infiniteHealth = false
    restoreFlag(M.deathFlag)
    M.deathFlag = nil
    releaseHook("SacrificeHealth")
    releaseHeroDamageRouterIfUnused()
  end
  local function releaseMana()
    M.infiniteMana = false
    restoreFlag(M.manaFlag)
    M.manaFlag = nil
    releaseHook("ManaDelta")
  end
  local function releaseDamage()
    M.damageEnabled = false
    releaseHook("CalculateDamageMultipliers")
  end
  -- The cast gate is engine-level, not just an ActiveEffect flag.  Current
  -- game traits that turn the normal cast into a repeatable projected cast
  -- disable three cast-control effects and combine that with a small set of
  -- cast-weapon properties (notably AllowMultiFireRequest and
  -- IgnoreOwnerAttackDisabled).  Mirror only those control/cooldown properties
  -- and leave projectile/animation data untouched so ordinary casts keep their
  -- native presentation and boon interactions.
  --
  -- Cast delivery is a family, not one weapon.  The base cast is WeaponCast, but
  -- a cast-shape boon swaps the weapon that is actually fired and binds the cast
  -- control to the swapped name (PowersLogic.Setup*Cast -> SwapWeapon, then
  -- WeaponLogic.CheckSpinControl -> AddWeaponControl(castOverridden)):
  --   CastProjectileBoon (Hestia)     -> WeaponCastProjectile
  --   HadesCastProjectileBoon (Hades) -> WeaponCastProjectileHades
  --   CastAnywhereBoon (Zeus)         -> WeaponAnywhereCast
  --   CastLobBoon (Dionysus)          -> WeaponCastLob
  -- Evidence: the target build's TraitData_*.lua PreEquipWeapons /
  -- OverrideWeaponFireNames pairs and its own OnWeaponFiredFunctions.ValidWeapons
  -- list in TraitData_MetaUpgrade.lua.  The recast gate is a per-weapon engine
  -- property, so overriding only WeaponCast leaves the fired variant's own gate
  -- in force and the recast stays blocked for those shapes.
  local castModel = {
    baseWeapon = "WeaponCast",
    variantWeapons = setmetatable({
      "WeaponCastProjectile", "WeaponCastProjectileHades", "WeaponAnywhereCast", "WeaponCastLob",
    }, arrayMeta),
    variantSet = {},
    overrides = {
      IgnoreOwnerAttackDisabled = true,
      Cooldown = 0,
      AllowMultiFireRequest = true,
      IgnoreForceCooldown = true,
      -- A cast weapon also has an engine-level active-projectile cap.  Removing
      -- the cooldown/control effects alone still leaves a live cast occupying
      -- that slot, so a second fire request can be rejected until the first cast
      -- dies.  Keep a generous finite cap instead of touching projectile
      -- lifetime or expiring the player's current cast; overlapping casts
      -- therefore retain their native boon/damage behavior.
      ActiveProjectileCap = 32,
    },
    propertyOrder = {
      "IgnoreOwnerAttackDisabled", "Cooldown", "AllowMultiFireRequest", "IgnoreForceCooldown", "ActiveProjectileCap",
    },
  }
  for _, weaponName in ipairs(castModel.variantWeapons) do castModel.variantSet[weaponName] = true end
  function castModel.isWeapon(weaponName)
    return weaponName == castModel.baseWeapon or castModel.variantSet[weaponName] == true
  end
  -- Resolve the weapons that currently deliver the cast.  This mirrors
  -- WeaponLogic.CheckSpinControl and is re-evaluated on every apply, so acquiring
  -- or removing a supported Cast modifier re-targets the gate without toggling
  -- the feature.  Only the bounded cast-shape family is admitted; a Spell/Hex
  -- PreEquipWeapons entry is not a cast delivery weapon.
  function castModel.effectiveWeapons(hero)
    hero = hero or (type(CurrentRun) == "table" and CurrentRun.Hero or nil)
    local active = { [castModel.baseWeapon] = true }
    if type(hero) == "table" and type(hero.Traits) == "table" then
      for _, trait in ipairs(hero.Traits) do
        if type(trait) == "table" and type(trait.PreEquipWeapons) == "table" then
          for _, equipped in ipairs(trait.PreEquipWeapons) do
            if castModel.variantSet[equipped] then active[equipped] = true end
          end
        end
      end
    end
    local resolved = setmetatable({ castModel.baseWeapon }, arrayMeta)
    for _, weaponName in ipairs(castModel.variantWeapons) do
      if active[weaponName] then resolved[#resolved + 1] = weaponName end
    end
    return resolved
  end
  -- The gate belongs to the weapon that actually fires.  A cast-family weapon
  -- that is not the current delivery shape must keep native behavior, so the
  -- property hook only protects a weapon while it is effective.
  function castModel.protects(weaponName)
    if not castModel.isWeapon(weaponName) then return false end
    for _, effectiveName in ipairs(castModel.effectiveWeapons()) do
      if effectiveName == weaponName then return true end
    end
    return false
  end
  -- The current game's projected-cast traits disable this entire trio.  Treat
  -- them as one reversible group rather than declaring success after changing
  -- only WeaponCastAttackDisable.  Every cast-shape boon in the target build
  -- declares these effects under WeaponName = "WeaponCast" (the effect stays
  -- owned by the base cast weapon even after the fired weapon is swapped), so
  -- the effect group does not follow the delivery weapon.
  local castEffectOverrides = {
    WeaponCastAttackDisable = false,
    WeaponCastSelfSlow = false,
    WeaponCastSelfSlow2 = false,
  }
  local castEffectOrder = { "WeaponCastAttackDisable", "WeaponCastSelfSlow", "WeaponCastSelfSlow2" }
  local function castEffectNaturallyActive(effectName)
    local function containsOverride(value, seen, depth)
      if type(value) ~= "table" or depth > 8 then return false end
      seen = seen or {}
      if seen[value] then return false end
      seen[value] = true
      if value.WeaponName == "WeaponCast" and value.EffectName == effectName
          and value.EffectProperty == "Active" and value.ChangeValue == false then return true end
      for _, child in pairs(value) do
        if containsOverride(child, seen, depth + 1) then return true end
      end
      return false
    end
    local hero = type(CurrentRun) == "table" and CurrentRun.Hero or nil
    if type(hero) == "table" and type(hero.Traits) == "table" then
      for _, trait in ipairs(hero.Traits) do
        if containsOverride(trait, nil, 0) then return false end
        if type(TraitData) == "table" and type(trait) == "table" and type(trait.Name) == "string"
            and containsOverride(TraitData[trait.Name], nil, 0) then return false end
      end
    end
    return true
  end
  local function readCastWeaponProperty(property, hero, weaponName)
    weaponName = weaponName or castModel.baseWeapon
    hero = hero or (type(CurrentRun) == "table" and CurrentRun.Hero or nil)
    if type(hero) ~= "table" or hero.ObjectId == nil then return nil, false end
    if type(GetWeaponDataValue) == "function" then
      local ok, value = pcall(GetWeaponDataValue, { Id = hero.ObjectId, WeaponName = weaponName, Property = property })
      if ok and value ~= nil then return value, true end
    end
    -- Some engine builds do not surface every inherited Weapon property through
    -- GetWeaponDataValue until it has been overridden once. Use the canonical
    -- base weapon value as the restoration fallback instead of leaking the
    -- trainer's override after the feature is disabled.
    if type(GetBaseDataValue) == "function" then
      local ok, value = pcall(GetBaseDataValue, { Type = "Weapon", Name = weaponName, Property = property })
      if ok and value ~= nil then return value, true end
    end
    return nil, false
  end
  local function writeCastWeaponProperty(property, value, setter, hero, weaponName)
    weaponName = weaponName or castModel.baseWeapon
    setter = setter or SetWeaponProperty
    hero = hero or (type(CurrentRun) == "table" and CurrentRun.Hero or nil)
    if type(hero) ~= "table" or hero.ObjectId == nil or type(setter) ~= "function" then return false end
    -- Match ApplyWeaponPropertyChange: ordinary WeaponProperty mutations omit
    -- DataValue entirely.  Round 7 forced DataValue=false, which only touched
    -- the transient instance layer; the live build then continued reporting
    -- native Cooldown/IgnoreForceCooldown through GetWeaponDataValue.
    return pcall(setter, {
      WeaponName = weaponName, DestinationId = hero.ObjectId, Property = property,
      Value = value, ValueChangeType = "Absolute",
    })
  end
  local function writeCastEffectActive(effectName, active, setter, hero)
    setter = setter or SetEffectProperty
    hero = hero or (type(CurrentRun) == "table" and CurrentRun.Hero or nil)
    if type(hero) ~= "table" or hero.ObjectId == nil or type(setter) ~= "function" then return false end
    local ok = pcall(setter, {
      WeaponName = "WeaponCast", EffectName = effectName,
      DestinationId = hero.ObjectId, Property = "Active",
      Value = not not active, ValueChangeType = "Absolute",
    })
    return ok
  end
  function castModel.ensureWeaponRuntime(runtime, weaponName, hero)
    local weapon = runtime.weapons[weaponName]
    if weapon ~= nil then return weapon end
    weapon = { nativeProperties = {}, nativePropertyKnown = {}, applied = false }
    for _, property in ipairs(castModel.propertyOrder) do
      local value, ok = readCastWeaponProperty(property, hero, weaponName)
      if ok and value ~= nil then
        weapon.nativeProperties[property] = value
        weapon.nativePropertyKnown[property] = true
      end
    end
    runtime.weapons[weaponName] = weapon
    return weapon
  end
  local function ensureCastRuntime()
    if not ready() then return nil end
    local hero = CurrentRun.Hero
    if type(M.castRuntime) == "table" and M.castRuntime.hero == hero then return M.castRuntime end
    local runtime = {
      hero = hero, weapons = {}, appliedWeapons = {},
      nativeEffects = {}, nativeEffectKnown = {}, applied = false,
    }
    for _, effectName in ipairs(castEffectOrder) do
      runtime.nativeEffects[effectName] = castEffectNaturallyActive(effectName)
      runtime.nativeEffectKnown[effectName] = true
    end
    for _, weaponName in ipairs(castModel.effectiveWeapons(hero)) do
      castModel.ensureWeaponRuntime(runtime, weaponName, hero)
    end
    M.castRuntime = runtime
    return runtime
  end
  local function applyCastAvailability()
    if not M.instantCastCooldown or not ready() then return false end
    local runtime = ensureCastRuntime()
    if runtime == nil then return false end
    local weaponHook = M.hooks["SetWeaponProperty"]
    local effectHook = M.hooks["SetEffectProperty"]
    local weaponSetter = weaponHook and weaponHook.original or SetWeaponProperty
    local effectSetter = effectHook and effectHook.original or SetEffectProperty
    local applied = true
    -- Re-resolve on every apply: a Cast modifier acquired or removed since the
    -- last tick changes which weapon is fired, and the gate has to follow it.
    local effective = castModel.effectiveWeapons(runtime.hero)
    local active = {}
    for _, weaponName in ipairs(effective) do active[weaponName] = true end
    -- A delivery weapon that was replaced or removed must not keep the
    -- trainer's gate; restore the latest native value the game exposed for it.
    for weaponName in pairs(runtime.appliedWeapons) do
      if not active[weaponName] then
        local weapon = runtime.weapons[weaponName]
        if weapon ~= nil then
          for _, property in ipairs(castModel.propertyOrder) do
            if weapon.nativePropertyKnown[property] then
              if not writeCastWeaponProperty(property, weapon.nativeProperties[property], weaponSetter, runtime.hero, weaponName) then
                applied = false
              end
            end
          end
        end
      end
    end
    for _, weaponName in ipairs(effective) do
      castModel.ensureWeaponRuntime(runtime, weaponName, runtime.hero)
      for _, property in ipairs(castModel.propertyOrder) do
        if not writeCastWeaponProperty(property, castModel.overrides[property], weaponSetter, runtime.hero, weaponName) then
          applied = false
        end
      end
    end
    runtime.appliedWeapons = active
    for _, effectName in ipairs(castEffectOrder) do
      if not writeCastEffectActive(effectName, castEffectOverrides[effectName], effectSetter, runtime.hero) then
        applied = false
      end
    end
    runtime.applied = applied
    return applied
  end
  local function releaseInstantCastCooldown()
    local runtime = M.castRuntime
    local weaponHook = M.hooks["SetWeaponProperty"]
    local effectHook = M.hooks["SetEffectProperty"]
    local weaponSetter = weaponHook and weaponHook.original or SetWeaponProperty
    local effectSetter = effectHook and effectHook.original or SetEffectProperty
    M.instantCastCooldown = false
    releaseHook("SetWeaponProperty")
    releaseHook("SetEffectProperty")
    -- Do not replay old-Hero properties into a freshly-created run.  When the
    -- user toggles the feature off in-place, however, restore the latest values
    -- the game attempted to set while the trainer was active.
    local currentHero = type(CurrentRun) == "table" and CurrentRun.Hero or nil
    if type(runtime) == "table" and runtime.hero == currentHero then
      local nativeKeepsCastOpen = not castEffectNaturallyActive("WeaponCastAttackDisable")
      -- Restore every patched cast weapon to the latest value the game exposed or
      -- attempted while the trainer was active. This is important for
      -- ActiveProjectileCap: leaving the trainer's expanded cap behind would leak
      -- behavior after the toggle is disabled, including when a native
      -- projected-cast boon is owned. Restoring per weapon also undoes a variant
      -- that was gated while a Cast modifier was equipped.
      if type(weaponSetter) == "function" then
        for weaponName, weapon in pairs(runtime.weapons or {}) do
          for _, property in ipairs(castModel.propertyOrder) do
            if weapon.nativePropertyKnown[property] then
              pcall(writeCastWeaponProperty, property, weapon.nativeProperties[property], weaponSetter, runtime.hero, weaponName)
            end
          end
        end
      end
      if type(effectSetter) == "function" then
        for _, effectName in ipairs(castEffectOrder) do
          local natural = runtime.nativeEffects[effectName]
          if nativeKeepsCastOpen and castEffectOverrides[effectName] == false then natural = false end
          if type(natural) ~= "boolean" then natural = castEffectNaturallyActive(effectName) end
          pcall(writeCastEffectActive, effectName, natural, effectSetter, runtime.hero)
        end
      end
    end
    M.castRuntime = nil
  end
  local function releaseHex()
    M.hexAlwaysReady = false
    M.hexRuntime = nil
    releaseHook("SpellFire")
  end
  local function releaseAmmo()
    M.infiniteAmmo = false
    releaseHook("UpdateWeaponAmmo")
  end
  local function releaseMiniGames()
    M.autoMiniGames = false
    releaseHook("WaitForFishingInput")
    releaseHook("ExorcismSequence")
  end
  local function releaseGardenQoL()
    M.gardenQoL = false
    releaseHook("GardenPlantSeed")
    releaseHook("UseGardenPlot")
  end
  local function releaseBoonRarity()
    M.boonRarityEnabled = false
    releaseHook("GetRarityChances")
    releaseHook("SetTraitsOnLoot")
  end
  local function releaseNextRoomReward()
    releaseHook("ChooseRoomReward")
    releaseHook("StartRoom")
    M.nextRoomRewardOriginRoom = nil
    M.nextRoomRewardPatchedDoors = 0
    M.nextRoomRewardPatchedValue = nil
    M.nextRoomRewardPatchRoom = nil
  end
  local function releaseEconomyRuntime()
    M.moneyMultiplierEnabled, M.resourceMultiplierEnabled = false, false
    releaseHook("AddResource")
    releaseHook("SpendResource")
  end
  local function releaseRerollsRuntime()
    releaseHook("UpdateRerollUI")
  end
  -- DodgeChance is an engine LifeProperty.  Current game scripts always target
  -- the hero explicitly when writing it; omitting DestinationId is accepted by
  -- Lua but is a no-op in the live build.
  local function originalHeroTraitValue(valueName, args)
    local getter = GetTotalHeroTraitValue
    local hook = M.hooks["GetTotalHeroTraitValue"]
    if hook and GetTotalHeroTraitValue == hook.wrapper then getter = hook.original end
    if type(getter) ~= "function" then return nil end
    local ok, value = pcall(getter, valueName, args)
    return ok and finite(value) and value or nil
  end
  local function getDodgeRaw(hero)
    if type(hero) ~= "table" or hero.ObjectId == nil then return nil end
    return originalHeroTraitValue("DodgeChance")
  end
  local function setDodgeRaw(hero, value)
    if type(hero) ~= "table" or hero.ObjectId == nil or not finite(value) or type(SetLifeProperty) ~= "function" then return false end
    M.dodgeInternalWrite = true
    local ok = pcall(SetLifeProperty, {
      DestinationId = hero.ObjectId, Property = "DodgeChance", Value = value, DataValue = false,
    })
    M.dodgeInternalWrite = false
    return ok
  end
  local function ensureStatTraitValueRouter()
    requireFunctions("stat trait value routing", { "GetTotalHeroTraitValue" })
    if owns("GetTotalHeroTraitValue") then return end
    installHook("GetTotalHeroTraitValue", function(original, valueName, args, ...)
      if M.statTargets.dodge ~= nil and valueName == "DodgeChance" then
        return math.max(0, math.min(1, M.statTargets.dodge / 100))
      end
      if M.statTargets.crit ~= nil and valueName == "OutgoingUnmodifiedCritBonus" then return 0 end
      return original(valueName, args, ...)
    end)
  end
  local function releaseStatTraitValueRouterIfUnused(force)
    if force or (M.statTargets.dodge == nil and M.statTargets.crit == nil) then
      releaseHook("GetTotalHeroTraitValue")
    end
  end
  local function releaseGraspLock()
    local wasActive = M.statRuntime.grasp
    M.statRuntime.grasp = false
    releaseHook("GetMaxMetaUpgradeCost")
    if wasActive and type(GetMaxMetaUpgradeCost) == "function" then pcall(GetMaxMetaUpgradeCost) end
  end
  local function releaseCritLock()
    M.statRuntime.crit = false
    releaseHook("CalculateCritChance")
    releaseStatTraitValueRouterIfUnused(false)
  end
  local function releaseDodgeLock()
    local runtime = M.statRuntime.dodge
    M.statRuntime.dodge = nil
    releaseHook("SetLifeProperty")
    if type(runtime) == "table" and runtime.hero and runtime.hero == (CurrentRun and CurrentRun.Hero) then
      local natural = getDodgeRaw(runtime.hero)
      if not finite(natural) then natural = runtime.natural end
      if finite(natural) then setDodgeRaw(runtime.hero, natural) end
    end
    releaseStatTraitValueRouterIfUnused(false)
  end

  local function releaseEnemyDamageLock()
    M.statRuntime.enemyDamage = false
    releaseHeroDamageRouterIfUnused()
  end
  local function enemyHealthRuntime()
    local runtime = M.statRuntime.enemyHealth
    if type(runtime) ~= "table" then
      runtime = { factor = 1, records = {} }
      M.statRuntime.enemyHealth = runtime
    end
    return runtime
  end
  local function enemyUnitEligible(unit)
    if type(unit) ~= "table" or unit == (CurrentRun and CurrentRun.Hero) or unit.ObjectId == nil or unit.IsDead then return false end
    if type(ActiveEnemies) == "table" and ActiveEnemies[unit.ObjectId] ~= nil then return true end
    return unit.IsBoss == true or unit.RequiredKill == true
  end
  local function rescaleEnemyHealthUnit(unit, newFactor)
    if not enemyUnitEligible(unit) or not finite(newFactor) or newFactor <= 0 then return false end
    local runtime = enemyHealthRuntime()
    local id = unit.ObjectId
    local record = runtime.records[id]
    local oldFactor = type(record) == "table" and record.factor or 1
    if not finite(oldFactor) or oldFactor <= 0 then oldFactor = 1 end
    if math.abs(oldFactor - newFactor) < 0.000001 then
      runtime.records[id] = { unit = unit, factor = newFactor }
      return true
    end
    local oldMax = unit.MaxHealth
    if not finite(oldMax) or oldMax <= 0 then return false end
    local health = finite(unit.Health) and unit.Health or oldMax
    local ratio = math.max(0, math.min(1, health / oldMax))
    local baseMax = oldMax / oldFactor
    local newMax = math.max(1, baseMax * newFactor)
    unit.MaxHealth = newMax
    unit.Health = math.max(0, math.min(newMax, newMax * ratio))
    if math.abs(newFactor - 1) < 0.000001 then runtime.records[id] = nil
    else runtime.records[id] = { unit = unit, factor = newFactor } end
    return true
  end
  local function applyEnemyHealthToActive(factor)
    if type(ActiveEnemies) ~= "table" then return end
    for _, unit in pairs(ActiveEnemies) do if type(unit) == "table" then rescaleEnemyHealthUnit(unit, factor) end end
  end
  local function releaseEnemyHealthLock()
    local runtime = M.statRuntime.enemyHealth
    if type(runtime) == "table" and type(runtime.records) == "table" then
      local records = {}
      for id, record in pairs(runtime.records) do records[id] = record end
      for _, record in pairs(records) do
        if type(record) == "table" and type(record.unit) == "table" and not record.unit.IsDead then rescaleEnemyHealthUnit(record.unit, 1) end
      end
    end
    M.statRuntime.enemyHealth = nil
    releaseHook("SetupUnit")
  end
  local function installEnemyHealthLock()
    requireFunctions("enemy health multiplier", { "SetupUnit" })
    local target = M.statTargets.enemyHealth
    if not finite(target) then return end
    local factor = target / 100
    local runtime = enemyHealthRuntime()
    if not owns("SetupUnit") then
      installHook("SetupUnit", function(original, unit, currentRun, args, ...)
        local result = original(unit, currentRun, args, ...)
        if M.statTargets.enemyHealth ~= nil and enemyUnitEligible(unit) then rescaleEnemyHealthUnit(unit, M.statTargets.enemyHealth / 100) end
        return result
      end)
    end
    applyEnemyHealthToActive(factor)
    runtime.factor = factor
  end

  local trainerChargeSpeedName = "MacGamingTrainerChargeSpeed"
  local function releaseChargeSpeedLock()
    local applied = M.statRuntime.chargeSpeed
    M.statRuntime.chargeSpeed = nil
    if finite(applied) and type(RemovePlayerAttackSpecialChargeSpeed) == "function" then
      pcall(RemovePlayerAttackSpecialChargeSpeed, trainerChargeSpeedName, applied)
    end
  end
  local function installChargeSpeedLock()
    requireFunctions("charge speed lock", { "SetPlayerAttackSpecialChargeSpeed", "RemovePlayerAttackSpecialChargeSpeed" })
    local target = M.statTargets.chargeSpeed
    if not finite(target) then return end
    local multiplier = target / 100
    if M.statRuntime.chargeSpeed == multiplier then return end
    releaseChargeSpeedLock()
    SetPlayerAttackSpecialChargeSpeed(trainerChargeSpeedName, multiplier)
    M.statRuntime.chargeSpeed = multiplier
  end

  -- Speed controls deliberately reuse the same property families as the game:
  -- Unit.Speed for ordinary movement, WeaponSprint SelfVelocity/Cap for sprint,
  -- and each weapon's native SpeedPropertyChanges for attack cadence.  The
  -- trainer applies a reversible multiplier layer instead of overwriting data
  -- tables, so ordinary boons/aspects can continue to stack underneath it.
  local function currentMoveSpeedPercent(hero)
    if type(hero) ~= "table" or hero.ObjectId == nil or type(GetBaseDataValue) ~= "function" or type(GetUnitDataValue) ~= "function" then return nil end
    local okBase, base = pcall(GetBaseDataValue, { Type = "Unit", Name = "_PlayerUnit", Property = "Speed" })
    local okCurrent, current = pcall(GetUnitDataValue, { Id = hero.ObjectId, Property = "Speed" })
    if okBase and okCurrent and finite(base) and base ~= 0 and finite(current) then return current / base * 100 end
    return nil
  end
  local function currentWeaponVelocityPercent(hero, weaponName)
    if type(hero) ~= "table" or hero.ObjectId == nil or type(GetBaseDataValue) ~= "function" or type(GetWeaponDataValue) ~= "function" then return nil end
    local okBase, base = pcall(GetBaseDataValue, { Type = "Weapon", Name = weaponName, Property = "SelfVelocity" })
    local okCurrent, current = pcall(GetWeaponDataValue, { Id = hero.ObjectId, WeaponName = weaponName, Property = "SelfVelocity" })
    if okBase and okCurrent and finite(base) and base ~= 0 and finite(current) then return current / base * 100 end
    return nil
  end
  local function currentSprintSpeedPercent(hero) return currentWeaponVelocityPercent(hero, "WeaponSprint") end
  local function currentDashSpeedPercent(hero) return currentWeaponVelocityPercent(hero, "WeaponBlink") end
  local function firstPrimarySecondaryWeapon(hero)
    if type(hero) ~= "table" or type(hero.Weapons) ~= "table" then return nil end
    if type(GetEquippedWeapon) == "function" then
      local ok, name = pcall(GetEquippedWeapon)
      if ok and type(name) == "string" then return name end
    end
    local lookup = type(WeaponSetLookups) == "table" and WeaponSetLookups.HeroPrimarySecondaryWeapons or nil
    for name in pairs(hero.Weapons) do
      if type(name) == "string" and (type(lookup) ~= "table" or lookup[name]) then return name end
    end
    return nil
  end
  local function currentAttackSpeedPercent(hero)
    if type(GetLuaWeaponSpeedMultiplier) ~= "function" then return nil end
    local weaponName = firstPrimarySecondaryWeapon(hero)
    if not weaponName then return nil end
    local ok, timeMultiplier = pcall(GetLuaWeaponSpeedMultiplier, weaponName)
    if ok and finite(timeMultiplier) and timeMultiplier > 0 then return 100 / timeMultiplier end
    return nil
  end
  local function releaseMoveSpeedLock()
    local runtime = M.statRuntime.moveSpeed
    M.statRuntime.moveSpeed = nil
    if type(runtime) == "table" and runtime.hero == (CurrentRun and CurrentRun.Hero)
        and finite(runtime.factor) and runtime.factor > 0 and type(SetUnitProperty) == "function" then
      pcall(SetUnitProperty, { DestinationId = runtime.hero.ObjectId, Property = "Speed", Value = 1 / runtime.factor, ValueChangeType = "Multiply" })
    end
  end
  local function installMoveSpeedLock()
    requireFunctions("move speed lock", { "SetUnitProperty" })
    local target = M.statTargets.moveSpeed
    if not finite(target) then return end
    local hero = CurrentRun.Hero
    local factor = target / 100
    local runtime = M.statRuntime.moveSpeed
    if type(runtime) == "table" and runtime.hero == hero and math.abs((runtime.factor or 0) - factor) < 0.000001 then return end
    releaseMoveSpeedLock()
    SetUnitProperty({ DestinationId = hero.ObjectId, Property = "Speed", Value = factor, ValueChangeType = "Multiply" })
    M.statRuntime.moveSpeed = { hero = hero, factor = factor }
  end
  local function releaseWeaponVelocityLock(stat, weaponName)
    local runtime = M.statRuntime[stat]
    M.statRuntime[stat] = nil
    if type(runtime) == "table" and runtime.hero == (CurrentRun and CurrentRun.Hero)
        and finite(runtime.factor) and runtime.factor > 0 and type(SetWeaponProperty) == "function" then
      for _, property in ipairs({ "SelfVelocity", "SelfVelocityCap" }) do
        pcall(SetWeaponProperty, { WeaponName = weaponName, DestinationId = runtime.hero.ObjectId,
          Property = property, Value = 1 / runtime.factor, ValueChangeType = "Multiply" })
      end
    end
  end
  local function installWeaponVelocityLock(stat, weaponName, label)
    requireFunctions(label .. " lock", { "SetWeaponProperty" })
    local target = M.statTargets[stat]
    if not finite(target) then return end
    local hero = CurrentRun.Hero
    local factor = target / 100
    local runtime = M.statRuntime[stat]
    if type(runtime) == "table" and runtime.hero == hero and math.abs((runtime.factor or 0) - factor) < 0.000001 then return end
    releaseWeaponVelocityLock(stat, weaponName)
    for _, property in ipairs({ "SelfVelocity", "SelfVelocityCap" }) do
      SetWeaponProperty({ WeaponName = weaponName, DestinationId = hero.ObjectId,
        Property = property, Value = factor, ValueChangeType = "Multiply" })
    end
    M.statRuntime[stat] = { hero = hero, factor = factor }
  end
  local function releaseSprintSpeedLock() releaseWeaponVelocityLock("sprintSpeed", "WeaponSprint") end
  local function installSprintSpeedLock() installWeaponVelocityLock("sprintSpeed", "WeaponSprint", "sprint speed") end
  local function releaseDashSpeedLock() releaseWeaponVelocityLock("dashSpeed", "WeaponBlink") end
  local function installDashSpeedLock() installWeaponVelocityLock("dashSpeed", "WeaponBlink", "dash speed") end
  local function shallowCopy(source)
    local copy = {}
    if type(source) == "table" then for key, value in pairs(source) do copy[key] = value end end
    return copy
  end
  local function buildAttackSpeedChanges(timeFactor)
    local changes = setmetatable({}, arrayMeta)
    local weaponNames = type(WeaponSets) == "table" and WeaponSets.HeroPrimarySecondaryWeapons or nil
    local defaultChanges = type(WeaponData) == "table" and type(WeaponData.DefaultWeaponValues) == "table"
      and WeaponData.DefaultWeaponValues.DefaultSpeedPropertyChanges or nil
    if type(weaponNames) ~= "table" or type(defaultChanges) ~= "table" then return changes end
    for _, weaponName in pairs(weaponNames) do
      if type(weaponName) == "string" then
        local definitions = type(WeaponData[weaponName]) == "table" and WeaponData[weaponName].SpeedPropertyChanges or nil
        if type(definitions) ~= "table" then definitions = defaultChanges end
        for _, definition in pairs(definitions) do
          if type(definition) == "table" then
            local change = shallowCopy(definition)
            change.WeaponNames = nil
            change.WeaponName = weaponName
            change.ChangeType = "Multiply"
            change.ChangeValue = timeFactor
            if change.InvertSource then change.ChangeValue = 1 / change.ChangeValue end
            change.SpeedPropertyChanges = nil
            changes[#changes + 1] = change
          end
        end
      end
    end
    return changes
  end
  local function releaseAttackSpeedLock()
    local runtime = M.statRuntime.attackSpeed
    M.statRuntime.attackSpeed = nil
    if type(runtime) == "table" and runtime.hero == (CurrentRun and CurrentRun.Hero)
        and type(runtime.changes) == "table" and type(ApplyUnitPropertyChanges) == "function" then
      pcall(ApplyUnitPropertyChanges, runtime.hero, runtime.changes, true, true)
    end
  end
  local function installAttackSpeedLock()
    requireFunctions("attack speed lock", { "ApplyUnitPropertyChanges" })
    local target = M.statTargets.attackSpeed
    if not finite(target) then return end
    if type(WeaponData) ~= "table" or type(WeaponSets) ~= "table" or type(WeaponSets.HeroPrimarySecondaryWeapons) ~= "table" then
      error("Unsupported attack speed lock: weapon speed tables unavailable")
    end
    local hero = CurrentRun.Hero
    local timeFactor = 100 / target
    local runtime = M.statRuntime.attackSpeed
    if type(runtime) == "table" and runtime.hero == hero and math.abs((runtime.timeFactor or 0) - timeFactor) < 0.000001 then return end
    releaseAttackSpeedLock()
    local changes = buildAttackSpeedChanges(timeFactor)
    if #changes == 0 then error("Unsupported attack speed lock: no speed property changes") end
    ApplyUnitPropertyChanges(hero, changes, true, false)
    M.statRuntime.attackSpeed = { hero = hero, timeFactor = timeFactor, changes = changes }
  end
  local trainerManaRegenSource = "MacGamingTrainerManaRegen"
  local function currentTrainerManaRegen(hero)
    if type(hero) ~= "table" or type(hero.ManaRegenSources) ~= "table" then return nil end
    local source = hero.ManaRegenSources[trainerManaRegenSource]
    return type(source) == "table" and finite(source.Value) and source.Value or 0
  end
  local function releaseManaRegenLock()
    local runtime = M.statRuntime.manaRegen
    M.statRuntime.manaRegen = nil
    if type(runtime) == "table" and type(runtime.hero) == "table" and type(runtime.hero.ManaRegenSources) == "table" then
      if runtime.previous ~= nil then runtime.hero.ManaRegenSources[trainerManaRegenSource] = runtime.previous
      else runtime.hero.ManaRegenSources[trainerManaRegenSource] = nil end
    end
  end
  local function installManaRegenLock()
    local target = M.statTargets.manaRegen
    if not finite(target) then return end
    local hero = CurrentRun.Hero
    if type(hero.ManaRegenSources) ~= "table" then error("Unsupported mana regen lock: ManaRegenSources unavailable") end
    local runtime = M.statRuntime.manaRegen
    if type(runtime) == "table" and runtime.hero == hero and runtime.value == target then return end
    releaseManaRegenLock()
    local previous = hero.ManaRegenSources[trainerManaRegenSource]
    hero.ManaRegenSources[trainerManaRegenSource] = { Value = target, ShowManaRegen = true }
    M.statRuntime.manaRegen = { hero = hero, previous = previous, value = target }
    if type(ManaRegen) == "function" and type(thread) == "function" then pcall(thread, ManaRegen) end
  end

  local function releaseStatsRuntime()
    releaseGraspLock()
    releaseCritLock()
    releaseDodgeLock()
    releaseChargeSpeedLock()
    releaseMoveSpeedLock()
    releaseSprintSpeedLock()
    releaseDashSpeedLock()
    releaseAttackSpeedLock()
    releaseManaRegenLock()
    releaseEnemyDamageLock()
    releaseEnemyHealthLock()
    releaseStatTraitValueRouterIfUnused(true)
  end
  local function releaseGuard()
    if M.guardWrapper and UpdateTimers == M.guardWrapper then UpdateTimers = M.originalUpdateTimers end
    M.guardWrapper, M.originalUpdateTimers = nil, nil
  end
  local function deactivateRuntime()
    if roomGeneration ~= nil then roomGeneration.release() end
    releaseInvincibility()
    releaseHealth()
    releaseMana()
    releaseDamage()
    releaseInstantCastCooldown()
    releaseHex()
    releaseAmmo()
    releaseMiniGames()
    releaseGardenQoL()
    releaseBoonRarity()
    releaseNextRoomReward()
    releaseEconomyRuntime()
    releaseRerollsRuntime()
    releaseStatsRuntime()
  end
  local function clearDesired()
    M.gatheringProbabilities = {}
    M.chaosGateProbability = nil
    for key in pairs(M.desiredFeatures) do M.desiredFeatures[key] = false end
    M.resourceLocks = {}
    M.vitalLocks = {}
    M.elementLocks = {}
    M.rerollsLock = nil
    M.statTargets = {}
    M.nextRoomReward = nil
    M.nextRoomRewardToken = nil
  end
  local function disable()
    if choiceReroll ~= nil then choiceReroll.cleanup() end
    clearDesired()
    deactivateRuntime()
    releaseGuard()
  end
  local function anyDesired()
    for _, value in pairs(M.desiredFeatures) do if value then return true end end
    return next(M.resourceLocks) ~= nil or next(M.vitalLocks) ~= nil or next(M.elementLocks) ~= nil or M.rerollsLock ~= nil
      or next(M.statTargets) ~= nil or M.nextRoomReward ~= nil or next(M.gatheringProbabilities) ~= nil or M.chaosGateProbability ~= nil
  end
  local function anyRuntimeActive()
    return M.invincibility or M.infiniteHealth or M.infiniteMana or M.damageEnabled
      or M.instantCastCooldown or M.hexAlwaysReady or M.infiniteAmmo or M.autoMiniGames or M.gardenQoL or M.boonRarityEnabled
      or M.moneyMultiplierEnabled or M.resourceMultiplierEnabled
      or owns("AddResource") or owns("SpendResource") or owns("UpdateRerollUI")
      or owns("CreateRoom") or owns("GetHarvestPointSpawnChance") or owns("IsSecretDoorEligible")
      or owns("GetMaxMetaUpgradeCost") or owns("CalculateCritChance")
      or owns("GetTotalHeroTraitValue") or M.statRuntime.dodge ~= nil or M.statRuntime.chargeSpeed ~= nil
      or M.statRuntime.moveSpeed ~= nil or M.statRuntime.sprintSpeed ~= nil or M.statRuntime.dashSpeed ~= nil or M.statRuntime.attackSpeed ~= nil or M.statRuntime.manaRegen ~= nil or M.statRuntime.enemyDamage or M.statRuntime.enemyHealth ~= nil
  end
  local reconcileDesired
  local forceCastAvailable, refillHex, currentSpellRuntime, actionLedger
  local function synchronize()
    -- Keep already owned hooks on their captured owner. An uncertain native
    -- coroutine must never adopt a new owner or reinstall a replaced hook.
    if M.terminalActionUnknown then return end
    local hero = type(CurrentRun) == "table" and CurrentRun.Hero or nil
    if M.session ~= SessionState or M.run ~= CurrentRun or M.hero ~= hero then
      deactivateRuntime()
      M.session, M.run, M.hero = SessionState, CurrentRun, hero
      M.featureErrors = {}
    end
    local invincibilityFlagActive = M.invincibilityHero == hero and type(hero) == "table"
      and type(hero.InvulnerableFlags) == "table" and hero.InvulnerableFlags[trainerInvincibilityFlag]
    if M.invincibility and (not owns("Damage") or not invincibilityFlagActive) then releaseInvincibility() end
    if M.infiniteHealth and (not owns("Damage") or not owns("SacrificeHealth")) then releaseHealth() end
    if M.infiniteMana and not owns("ManaDelta") then releaseMana() end
    if M.damageEnabled and not owns("CalculateDamageMultipliers") then releaseDamage() end
    if M.instantCastCooldown and (not owns("SetEffectProperty") or not owns("SetWeaponProperty")) then releaseInstantCastCooldown() end
    if M.hexAlwaysReady and not owns("SpellFire") then releaseHex() end
    if M.infiniteAmmo and not owns("UpdateWeaponAmmo") then releaseAmmo() end
    if M.autoMiniGames and type(WaitForFishingInput) == "function" and not owns("WaitForFishingInput")
        and type(ExorcismSequence) == "function" and not owns("ExorcismSequence") then releaseMiniGames() end
    if M.gardenQoL and (not owns("GardenPlantSeed") or not owns("UseGardenPlot")) then releaseGardenQoL() end
    if M.boonRarityEnabled and (not owns("GetRarityChances") or not owns("SetTraitsOnLoot")) then releaseBoonRarity() end
    if (M.moneyMultiplierEnabled or M.resourceMultiplierEnabled or next(M.resourceLocks))
        and (not owns("AddResource") or not owns("SpendResource")) then releaseEconomyRuntime() end
    if M.rerollsLock ~= nil and not owns("UpdateRerollUI") then releaseRerollsRuntime() end
    if M.statTargets.grasp ~= nil and M.statRuntime.grasp and not owns("GetMaxMetaUpgradeCost") then releaseGraspLock() end
    if M.statTargets.crit ~= nil and M.statRuntime.crit
        and (not owns("CalculateCritChance") or not owns("GetTotalHeroTraitValue")) then releaseCritLock() end
    if M.statTargets.dodge ~= nil and type(M.statRuntime.dodge) == "table" then
      local runtime = M.statRuntime.dodge
      if runtime.hero ~= hero or not owns("SetLifeProperty") or not owns("GetTotalHeroTraitValue") then releaseDodgeLock() end
    end
    if M.guardWrapper and UpdateTimers ~= M.guardWrapper then
      M.guardWrapper, M.originalUpdateTimers = nil, nil
    end
    if reconcileDesired then reconcileDesired(false) end
    if anyDesired() and not M.guardWrapper then
      local ok, message = pcall(function()
        requireFunctions("scene observer", { "UpdateTimers" })
        local original = UpdateTimers
        local wrapper
        wrapper = function(elapsed)
          if M.guardWrapper == wrapper then synchronize() end
          local result = original(elapsed)
          if M.guardWrapper == wrapper and M.enforceLocksInternal then M.enforceLocksInternal() end
          return result
        end
        M.originalUpdateTimers, M.guardWrapper = original, wrapper
        UpdateTimers = wrapper
      end)
      if not ok then M.reconcileError = tostring(message) end
    elseif not anyDesired() and not anyRuntimeActive() then
      releaseGuard()
    end
  end
  local function enforceResource(id)
    local target = M.resourceLocks[id]
    if target ~= nil and GameState.Resources[id] ~= target then
      GameState.Resources[id] = target
      if id == "Money" then refreshMoney() end
    end
  end
  local function enforceVital(vital)
    local lock = M.vitalLocks[vital]
    if type(lock) ~= "table" then return end
    local hero = CurrentRun.Hero
    if vital == "health" then
      if finite(lock.max) and hero.MaxHealth ~= lock.max then hero.MaxHealth = lock.max end
      if finite(lock.current) and hero.Health ~= lock.current then hero.Health = math.min(lock.current, number(hero.MaxHealth)) end
      refreshHealth()
    elseif vital == "mana" then
      if finite(lock.max) and hero.MaxMana ~= lock.max then hero.MaxMana = lock.max end
      local available = number(hero.MaxMana)
      if type(GetHeroMaxAvailableMana) == "function" then
        local ok, value = pcall(GetHeroMaxAvailableMana)
        if ok and finite(value) then available = value end
      end
      if finite(lock.current) and hero.Mana ~= lock.current then hero.Mana = math.min(lock.current, math.max(0, available)) end
      refreshMana()
    elseif vital == "armor" then
      if finite(lock.current) then
        -- Armor has no user-facing maximum.  MaxHealthBuffer is only an engine
        -- capacity field; grow it when needed so the requested current armor
        -- can survive a room/system refresh, but never lock or shrink it.
        if number(hero.MaxHealthBuffer) < lock.current then hero.MaxHealthBuffer = lock.current end
        if hero.HealthBuffer ~= lock.current then hero.HealthBuffer = lock.current end
      end
      refreshHealth()
    end
  end
  local function refreshHighestElementCount()
    if type(CurrentRun) ~= "table" or type(CurrentRun.Hero) ~= "table" or type(CurrentRun.Hero.Elements) ~= "table" then return end
    local highest = 0
    -- Follow the game's own TraitElementData.BaseElement flag. Aether is a
    -- canonical element but BaseElement=false, so it must not inflate infusion
    -- requirements based on HighestBaseElementCount.
    for element, count in pairs(CurrentRun.Hero.Elements) do
      local data = type(TraitElementData) == "table" and TraitElementData[element] or nil
      if type(data) == "table" and data.BaseElement then highest = math.max(highest, number(count)) end
    end
    CurrentRun.Hero.HighestBaseElementCount = highest
  end
  local function enforceElements()
    local changed = false
    if type(CurrentRun.Hero.Elements) ~= "table" then return end
    for element, target in pairs(M.elementLocks) do
      if finite(target) and CurrentRun.Hero.Elements[element] ~= target then
        CurrentRun.Hero.Elements[element] = target
        changed = true
      end
    end
    if changed then
      refreshHighestElementCount()
      if type(CheckActivatedTraits) == "function" then pcall(CheckActivatedTraits, CurrentRun.Hero, { SkipPresentation = true }) end
    end
  end
  local function enforceLocks()
    if M.terminalActionUnknown and (M.session ~= SessionState or M.run ~= CurrentRun
        or M.hero ~= (type(CurrentRun) == "table" and CurrentRun.Hero or nil)) then return end
    -- Save-backed inventory locks are meaningful in the Crossroads too; keep
    -- those invariants before applying Hero-only combat locks.
    if type(GameState) == "table" and type(GameState.Resources) == "table" then
      for id in pairs(M.resourceLocks) do enforceResource(id) end
    end
    if not ready() then return end
    if M.invincibility then restoreInvincibilityHitCount(CurrentRun.Hero) end
    for vital in pairs(M.vitalLocks) do enforceVital(vital) end
    enforceElements()
    if M.instantCastCooldown then
      if not forceCastAvailable() then
        M.featureErrors.instantCastCooldown = "Unable to keep the cast delivery weapon available"
      end
    end
    if M.hexAlwaysReady then
      if refillHex() then M.featureErrors.hexAlwaysReady = nil end
    end
    if M.rerollsLock ~= nil and finite(CurrentRun.NumRerolls)
        and (not M.terminalActionUnknown or owns("UpdateRerollUI"))
        and CurrentRun.NumRerolls ~= M.rerollsLock and type(UpdateRerollUI) == "function" then
      CurrentRun.NumRerolls = M.rerollsLock
      UpdateRerollUI(M.rerollsLock)
    end
    if M.statTargets.dodge ~= nil and type(M.statRuntime.dodge) == "table" then
      -- There is no reliable public getter for the live LifeProperty in this
      -- build, so reapply the exact target after the game's timer update.
      setDodgeRaw(CurrentRun.Hero, M.statTargets.dodge / 100)
    end
  end
  M.enforceLocksInternal = enforceLocks
  local function installGuard()
    if M.guardWrapper then return end
    requireFunctions("scene observer", { "UpdateTimers" })
    local original = UpdateTimers
    local wrapper
    wrapper = function(elapsed)
      if M.guardWrapper == wrapper then synchronize() end
      local result = original(elapsed)
      if M.guardWrapper == wrapper then enforceLocks() end
      return result
    end
    M.originalUpdateTimers, M.guardWrapper = original, wrapper
    UpdateTimers = wrapper
  end
  local function resourceSectionTitle(id)
    if string.find(id, "Gift", 1, true) then return "赠礼资源" end
    if string.find(id, "Plant", 1, true) or string.find(id, "Seed", 1, true) then return "植物与种子" end
    if string.find(id, "Ore", 1, true) then return "矿物" end
    if string.find(id, "Fish", 1, true) then return "鱼类" end
    if string.find(id, "Boss", 1, true) then return "首领素材" end
    return "通用与制作资源"
  end
  local resourceInventorySectionTitles = {
    InventoryScreen_ResourcesTab = "资源",
    InventoryScreen_GardenTab = "植物与种子",
    InventoryScreen_GiftsTab = "赠礼",
    InventoryScreen_FishTab = "鱼类",
  }
  local function inventoryResourceLayout()
    local order, metadata, seen = {}, {}, {}
    local categories = type(ScreenData) == "table" and type(ScreenData.InventoryScreen) == "table"
      and ScreenData.InventoryScreen.ItemCategories or nil
    if type(categories) == "table" then
      for categoryIndex, category in ipairs(categories) do
        local sectionTitle = type(category) == "table" and resourceInventorySectionTitles[category.Name] or nil
        if sectionTitle ~= nil then
          local itemOrder = 0
          for _, id in ipairs(category) do
            if type(id) == "string" and id ~= "Money" and not seen[id]
                and type(ResourceData) == "table" and type(ResourceData[id]) == "table" then
              itemOrder = itemOrder + 1
              seen[id] = true
              order[#order + 1] = id
              metadata[id] = { sectionTitle = sectionTitle, sectionOrder = categoryIndex, itemOrder = itemOrder }
            end
          end
        end
      end
    end
    -- Fallback/forward compatibility: append game resources that are not part
    -- of the Inventory screen categories in ResourceDisplayOrderData order.
    if type(ResourceDisplayOrderData) == "table" and type(ResourceData) == "table" then
      for _, id in ipairs(ResourceDisplayOrderData) do
        if type(id) == "string" and id ~= "Money" and not seen[id] and type(ResourceData[id]) == "table" then
          seen[id] = true
          order[#order + 1] = id
          metadata[id] = { sectionTitle = resourceSectionTitle(id), sectionOrder = 999, itemOrder = #order }
        end
      end
    end
    return order, metadata
  end
  local function resourceCatalog()
    local cached = M.catalogCache.resources
    if type(cached) == "table" then return cached.order, cached.metadata, cached.allowed end
    if type(ResourceDisplayOrderData) ~= "table" or type(ResourceData) ~= "table" then return {}, {}, {} end
    -- Prefer the Inventory screen's own category arrays: they are the game's
    -- source of truth for both grouping and per-category presentation order.
    -- ResourceDisplayOrderData remains the fallback for uncategorized/future
    -- resources so the catalog never silently drops a real ResourceData item.
    local order, metadata = inventoryResourceLayout()
    local allowed = {}
    for _, id in ipairs(order) do
      if type(id) == "string" and id ~= "Money" and type(ResourceData[id]) == "table" then allowed[id] = true end
    end
    -- Do not freeze the fallback-only layout if InventoryScreen has not been
    -- initialized yet; the next state call can still discover official groups.
    local categories = type(ScreenData) == "table" and type(ScreenData.InventoryScreen) == "table"
      and ScreenData.InventoryScreen.ItemCategories or nil
    if type(categories) == "table" then
      cached = { order = order, metadata = metadata, allowed = allowed }
      M.catalogCache.resources = cached
    end
    return order, metadata, allowed
  end
  local function resources()
    local result = setmetatable({}, arrayMeta)
    local order, metadata, allowed = resourceCatalog()
    for index, id in ipairs(order) do
      if allowed[id] then
        local presentation = metadata[id] or {}
        result[#result + 1] = {
          id = id, name = names[id] or id,
          count = number(GameState.Resources and GameState.Resources[id]),
          locked = M.resourceLocks[id] ~= nil, sortOrder = index,
          sectionTitle = presentation.sectionTitle or resourceSectionTitle(id),
        }
      end
    end
    return result, allowed
  end
  local function officialOlympianOrder()
    local order = {}
    local list = type(CodexOrdering) == "table" and CodexOrdering.OlympianGods or nil
    if type(list) ~= "table" and type(CodexData) == "table" then list = CodexData.OlympianGods end
    if type(list) == "table" then
      for index, id in ipairs(list) do
        if type(id) == "string" then order[id] = index * 10 end
      end
    end
    return order
  end
  local function boons()
    local cached = M.catalogCache.boons
    if type(cached) == "table" then return cached.list, cached.allowed end
    local result, allowed = setmetatable({}, arrayMeta), {}
    local officialOrder = officialOlympianOrder()
    for _, entry in ipairs(boonDefinitions) do
      if type(LootData) == "table" and type(LootData[entry.id]) == "table" then
        allowed[entry.id] = true
        result[#result + 1] = { id = entry.id, name = entry.name, sortSection = 20, sortGroup = officialOrder[entry.id] or entry.order, sortOrder = 0 }
      end
    end
    table.sort(result, function(a,b) return (a.sortGroup or 999) < (b.sortGroup or 999) end)
    if type(LootData) == "table" and (type(CodexOrdering) == "table" or type(CodexData) == "table") then
      M.catalogCache.boons = { list = result, allowed = allowed }
    end
    return result, allowed
  end
  local specialSourceCodexIds = {
    Selene = "SpellDrop", Chaos = "TrialUpgrade",
    Artemis = "NPC_Artemis_01", Athena = "NPC_Athena_01", Dionysus = "NPC_Dionysus_01",
    Echo = "NPC_Echo_01", Hades = "NPC_Hades_Field_01", Narcissus = "NPC_Narcissus_01",
    Circe = "NPC_Circe_01", Icarus = "NPC_Icarus_01", Medea = "NPC_Medea_01",
    Arachne = "NPC_Arachne_01",
  }
  local function officialSpecialSourceOrder()
    local order, codexRank = {}, {}
    if type(CodexOrdering) == "table" then
      local chapters = CodexOrdering.Order
      if type(chapters) ~= "table" then chapters = { "ChthonicGods", "OlympianGods", "OtherDenizens" } end
      for chapterIndex, chapterName in ipairs(chapters) do
        local entries = CodexOrdering[chapterName]
        if type(entries) == "table" then
          for itemIndex, id in ipairs(entries) do
            if type(id) == "string" then codexRank[id] = chapterIndex * 1000 + itemIndex end
          end
        end
      end
    end
    for sourceId, codexId in pairs(specialSourceCodexIds) do
      if codexRank[codexId] then order[sourceId] = codexRank[codexId] end
    end
    return order
  end
  local function orderedTraitIds(traits)
    local result, found = {}, {}
    if type(traits) ~= "table" or type(TraitData) ~= "table" then return result end
    local function add(name)
      if type(name) == "string" and type(TraitData[name]) == "table" and not found[name] then
        found[name] = true; result[#result + 1] = name
      end
    end
    -- Array order is the closest thing to an official presentation order for
    -- in-person boon pools. Preserve it before considering keyed fallbacks.
    for _, value in ipairs(traits) do
      if type(value) == "string" then add(value)
      elseif type(value) == "table" then add(value.TraitName or value.Name) end
    end
    local fallback = {}
    for key, value in pairs(traits) do
      local name
      if type(value) == "string" then name = value
      elseif type(value) == "table" then name = value.TraitName or value.Name
      elseif type(key) == "string" and (value == true or finite(value)) then name = key end
      if type(name) == "string" and not found[name] then fallback[#fallback + 1] = name end
    end
    table.sort(fallback)
    for _, name in ipairs(fallback) do add(name) end
    return result
  end
  local seleneModel = (function()
    local function currentSpell()
      local hero = type(CurrentRun) == "table" and CurrentRun.Hero or nil
      local slotted = type(hero) == "table" and hero.SlottedSpell or nil
      return type(slotted) == "table" and slotted or nil
    end

    local function talentNodes(traitName, invested)
      local result = setmetatable({}, arrayMeta)
      local slotted = currentSpell()
      local talents = slotted and slotted.Talents or nil
      if type(traitName) ~= "string" or type(talents) ~= "table" then return result end
      for depth, column in ipairs(talents) do
        if type(column) == "table" then
          for slot, node in pairs(column) do
            if type(node) == "table" and node.Name == traitName
                and (invested == nil or not not node.Invested == invested) then
              result[#result + 1] = { depth = depth, slot = slot, node = node }
            end
          end
        end
      end
      table.sort(result, function(a, b)
        if a.depth ~= b.depth then return a.depth < b.depth end
        return tostring(a.slot) < tostring(b.slot)
      end)
      return result
    end

    local function catalogSignature()
      local slotted = currentSpell()
      if type(slotted) ~= "table" then return "none" end
      local parts = { tostring(slotted.Name or ""), tostring(slotted.TraitName or "") }
      for depth, column in ipairs(slotted.Talents or {}) do
        local keys = {}
        for slot in pairs(type(column) == "table" and column or {}) do keys[#keys + 1] = slot end
        table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
        for _, slot in ipairs(keys) do
          local node = column[slot]
          if type(node) == "table" and type(node.Name) == "string" then
            parts[#parts + 1] = table.concat({
              tostring(depth), tostring(slot), node.Name,
              node.Invested and "1" or "0", tostring(node.Rarity or ""),
            }, ":")
          end
        end
      end
      return table.concat(parts, "|")
    end

    local function investedTalentNames(slotted)
      local names = {}
      for _, column in ipairs(type(slotted) == "table" and slotted.Talents or {}) do
        for _, node in pairs(type(column) == "table" and column or {}) do
          if type(node) == "table" and node.Invested and type(node.Name) == "string" then
            names[node.Name] = true
          end
        end
      end
      return names
    end

    local function teardown()
      local slotted = currentSpell()
      if type(slotted) ~= "table" then return nil end
      requireFunctions("Selene spell teardown", {
        "HeroHasTrait", "RemoveTrait", "UnequipWeapon", "UpdateTalentPointInvestedCache",
      })
      local hero = CurrentRun.Hero
      for traitName in pairs(investedTalentNames(slotted)) do
        while HeroHasTrait(traitName) do
          RemoveTrait(hero, traitName, { Silent = true, SkipExpire = true })
        end
      end
      local mainTraitName = slotted.TraitName
      local mainTrait = nil
      for _, trait in ipairs(hero.Traits or {}) do
        if type(trait) == "table" and trait.Name == mainTraitName then
          mainTrait = trait
          break
        end
      end
      if type(mainTrait) ~= "table" and type(mainTraitName) == "string"
          and type(TraitData) == "table" then
        mainTrait = TraitData[mainTraitName]
      end
      if type(mainTrait) == "table" and type(SpellUnreadyPresentation) == "function" then
        pcall(SpellUnreadyPresentation, mainTrait)
      elseif type(SessionMapState) == "table" then
        SessionMapState.SpellWorldReadyFx = nil
      end
      if type(MapState) == "table" then MapState.ActiveSpellPresentation = nil end
      for _, weaponName in pairs(type(mainTrait) == "table" and mainTrait.PreEquipWeapons or {}) do
        UnequipWeapon({
          DestinationId = hero.ObjectId, Name = weaponName, UnloadPackages = false,
        })
        if type(MapState) == "table" and type(MapState.EquippedWeapons) == "table" then
          MapState.EquippedWeapons[weaponName] = nil
        end
      end
      if type(mainTraitName) == "string" then
        while HeroHasTrait(mainTraitName) do
          RemoveTrait(hero, mainTraitName, { Silent = true, SkipExpire = true })
        end
      end
      hero.SlottedSpell = nil
      CurrentRun.SpellCharge = 0
      CurrentRun.AllSpellInvestedCache = false
      CurrentRun.AllUniqueSpellInvestedCache = false
      if type(SessionMapState) == "table" then SessionMapState.PendingSpellChanges = nil end
      UpdateTalentPointInvestedCache()
      return mainTraitName
    end

    local function applySpell(spellName)
      requireFunctions("Selene spell acquisition", {
        "DeepCopyTable", "CreateTalentTree", "AddTraitToHero", "UpdateTalentPointInvestedCache",
      })
      local spellData = type(SpellData) == "table" and SpellData[spellName] or nil
      if type(spellData) ~= "table" or spellData.Skip
          or (type(spellData.GameStateRequirements) == "table" and spellData.GameStateRequirements.Skip)
          or type(spellData.TraitName) ~= "string" then
        error("Selene spell target is unavailable")
      end
      local slotted = DeepCopyTable(spellData)
      slotted.Name = spellName
      slotted.Talents = DeepCopyTable(CreateTalentTree(spellData))
      slotted.HasDuoTalent = false
      for _, column in ipairs(slotted.Talents or {}) do
        for _, node in pairs(type(column) == "table" and column or {}) do
          local talentData = type(node) == "table" and type(TraitData) == "table"
            and TraitData[node.Name] or nil
          if type(talentData) == "table" and talentData.IsDuoBoon then
            slotted.HasDuoTalent = true
            break
          end
        end
        if slotted.HasDuoTalent then break end
      end

      teardown()
      requireFunctions("Selene spell acquisition", { "HeroHasTrait" })
      local ok, added = pcall(AddTraitToHero, {
        TraitName = spellData.TraitName, SkipNewTraitHighlight = true,
      })
      if not ok then
        if HeroHasTrait(spellData.TraitName) then
          CurrentRun.Hero.SlottedSpell = slotted
          CurrentRun.SpellCharge = 0
        end
        UpdateTalentPointInvestedCache()
        error(added)
      end
      if type(added) ~= "table" then
        if HeroHasTrait(spellData.TraitName) then
          CurrentRun.Hero.SlottedSpell = slotted
          CurrentRun.SpellCharge = 0
        end
        UpdateTalentPointInvestedCache()
        error("Selene spell acquisition failed")
      end
      CurrentRun.Hero.SlottedSpell = slotted
      CurrentRun.SpellCharge = 0

      if slotted.CheckSpellReadyOnAcquire then
        if type(added.CheckChargeFunctionName) == "string" then
          requireFunctions("Selene spell ready check", { "thread", "CallFunctionName" })
          thread(CallFunctionName, added.CheckChargeFunctionName, CurrentRun.Hero)
        end
      else
        requireFunctions("Selene spell ready presentation", { "thread", "SpellReadyPresentation" })
        thread(SpellReadyPresentation, added, 1.5)
      end
      UpdateTalentPointInvestedCache()
      return added
    end

    local function applyTalent(traitName)
      local available = talentNodes(traitName, false)
      if #available == 0 then error("Selene talent is no longer available in the current Path of Stars") end
      requireFunctions("Selene talent acquisition", {
        "HeroHasTrait", "GetHeroTrait", "AddTraitToHero", "IncreaseTraitLevel",
        "UpdateTalentPointInvestedCache",
      })
      local selected = available[1].node
      selected.Invested = true
      selected.QueuedInvested = nil
      local runtimeTrait
      if HeroHasTrait(traitName) then
        runtimeTrait = GetHeroTrait(traitName)
        if type(runtimeTrait) ~= "table" then error("Mounted Selene talent is unavailable") end
        local beforeLevel = tonumber(runtimeTrait.StackNum) or 1
        local ok, upgraded = pcall(IncreaseTraitLevel, runtimeTrait)
        local liveLevel = tonumber(runtimeTrait.StackNum) or 1
        if not ok then
          if liveLevel == beforeLevel then
            selected.Invested = false
            selected.QueuedInvested = nil
          end
          UpdateTalentPointInvestedCache()
          error(upgraded)
        end
        if type(upgraded) ~= "table" or (tonumber(upgraded.StackNum) or liveLevel) <= beforeLevel then
          if liveLevel == beforeLevel then
            selected.Invested = false
            selected.QueuedInvested = nil
          end
          UpdateTalentPointInvestedCache()
          error("Selene talent acquisition failed")
        end
        runtimeTrait = upgraded
        local base = type(TraitData) == "table" and TraitData[traitName] or nil
        if type(base) == "table" and type(base.AcquireFunctionName) == "string" then
          requireFunctions("Selene talent acquire callback", { "CallFunctionName" })
          CallFunctionName(base.AcquireFunctionName, base.AcquireFunctionArgs, runtimeTrait)
        end
      else
        local ok, added = pcall(AddTraitToHero, {
          TraitName = traitName, Rarity = selected.Rarity, FromLoot = true,
        })
        if not ok then
          if not HeroHasTrait(traitName) then
            selected.Invested = false
            selected.QueuedInvested = nil
          end
          UpdateTalentPointInvestedCache()
          error(added)
        end
        runtimeTrait = added
      end
      if type(runtimeTrait) ~= "table" then
        if not HeroHasTrait(traitName) then
          selected.Invested = false
          selected.QueuedInvested = nil
        end
        UpdateTalentPointInvestedCache()
        error("Selene talent acquisition failed")
      end
      local base = type(TraitData) == "table" and TraitData[traitName] or nil
      if type(base) == "table" and base.IsDuoBoon then
        CurrentRun.Hero.SlottedSpell.ObtainedDuoTalent = true
      end
      UpdateTalentPointInvestedCache()
      return runtimeTrait
    end

    return {
      currentSpell = currentSpell,
      talentNodes = talentNodes,
      catalogSignature = catalogSignature,
      teardown = teardown,
      applySpell = applySpell,
      applyTalent = applyTalent,
    }
  end)()

  local hammerModel = (function()
    local parentWeapons = {
      StaffHammerTrait = "WeaponStaffSwing",
      DaggerHammerTrait = "WeaponDagger",
      AxeHammerTrait = "WeaponAxe",
      TorchHammerTrait = "WeaponTorch",
      LobHammerTrait = "WeaponLob",
      SuitHammerTrait = "WeaponSuit",
    }

    local function source()
      local value = type(LootData) == "table" and LootData.WeaponUpgrade or nil
      return type(value) == "table" and value or nil
    end

    local function sourceTraitNames()
      local result, seen = setmetatable({}, arrayMeta), {}
      local value = source()
      if value == nil then return result end
      for _, pool in ipairs({ value.PriorityUpgrades, value.WeaponUpgrades, value.Traits }) do
        for _, name in ipairs(orderedTraitIds(pool)) do
          if not seen[name] then
            seen[name] = true
            result[#result + 1] = name
          end
        end
      end
      return result
    end

    local function sourceContains(name)
      if type(name) ~= "string" then return false end
      for _, candidate in ipairs(sourceTraitNames()) do
        if candidate == name then return true end
      end
      return false
    end

    local function ownerWeaponForDefinition(definition)
      if type(definition) ~= "table" then return nil end
      if type(definition.CodexWeapon) == "string" and definition.CodexWeapon ~= "" then
        return definition.CodexWeapon
      end
      for _, parent in ipairs(type(definition.InheritFrom) == "table" and definition.InheritFrom or {}) do
        if parentWeapons[parent] ~= nil then return parentWeapons[parent] end
      end
      return nil
    end

    local function ownerWeapon(name, runtimeTrait)
      local runtimeOwner = ownerWeaponForDefinition(runtimeTrait)
      if runtimeOwner ~= nil then return runtimeOwner end
      local definition = type(TraitData) == "table" and TraitData[name] or nil
      return ownerWeaponForDefinition(definition)
    end

    local function currentWeapon()
      if type(GetEquippedWeapon) == "function" then
        local ok, value = pcall(GetEquippedWeapon)
        if ok and type(value) == "string" and value ~= "" then return value end
      end
      local hero = type(CurrentRun) == "table" and CurrentRun.Hero or nil
      local weapons = type(hero) == "table" and hero.Weapons or nil
      if type(weapons) ~= "table" then return nil end
      local candidates = {}
      for _, name in ipairs(sourceTraitNames()) do
        local weapon = ownerWeapon(name)
        if type(weapon) == "string" then candidates[weapon] = true end
      end
      local ordered = {}
      for weapon in pairs(candidates) do ordered[#ordered + 1] = weapon end
      table.sort(ordered)
      for _, weapon in ipairs(ordered) do
        if weapons[weapon] then return weapon end
      end
      return nil
    end

    local function currentAspect()
      local weapon = currentWeapon()
      local selected = type(GameState) == "table" and GameState.LastWeaponUpgradeName or nil
      return type(selected) == "table" and type(selected[weapon]) == "string" and selected[weapon] or ""
    end

    local function isHammerTrait(trait)
      if type(trait) ~= "table" then return false end
      if trait.IsHammerTrait then return true end
      return type(trait.Name) == "string" and sourceContains(trait.Name)
    end

    local function isRuntimeAspect(trait)
      if type(trait) ~= "table" then return false end
      if trait.IsWeaponEnchantment then return true end
      if trait.Slot ~= "Aspect" or type(trait.RequiredWeapon) ~= "string" then return false end
      if type(trait.InheritFrom) == "table" then
        for _, parent in ipairs(trait.InheritFrom) do
          if parent == "WeaponEnchantmentTrait" then return true end
        end
      end
      return false
    end

    local function ownerMatchesCurrent(name, runtimeTrait)
      local current = currentWeapon()
      if current == nil then return false end
      local owner = ownerWeapon(name, runtimeTrait)
      return owner ~= nil and owner == current
    end

    local function nativeEligible()
      local names, lookup = setmetatable({}, arrayMeta), {}
      local value = source()
      if value == nil or currentWeapon() == nil or type(GetEligibleUpgrades) ~= "function" then
        return names, lookup
      end
      local ok, options = pcall(GetEligibleUpgrades, {}, value, value)
      if not ok or type(options) ~= "table" then return names, lookup end
      local sourceLookup = {}
      for _, name in ipairs(sourceTraitNames()) do sourceLookup[name] = true end
      for _, option in pairs(options) do
        local name = type(option) == "table" and (option.ItemName or option.TraitName or option.Name) or option
        if type(name) == "string" and sourceLookup[name] and not lookup[name] then
          lookup[name] = true
          names[#names + 1] = name
        end
      end
      table.sort(names)
      return names, lookup
    end

    local function mountedCurrent(name)
      local hero = type(CurrentRun) == "table" and CurrentRun.Hero or nil
      if type(hero) ~= "table" or type(hero.Traits) ~= "table" then return false end
      for _, trait in ipairs(hero.Traits) do
        if type(trait) == "table" and trait.Name == name and isHammerTrait(trait)
            and ownerMatchesCurrent(name, trait) then
          return true
        end
      end
      return false
    end

    local function catalogNames()
      local visible, eligibleLookup = nativeEligible()
      local allowed = setmetatable({}, arrayMeta)
      for _, name in ipairs(sourceTraitNames()) do
        if ownerMatchesCurrent(name)
            and (eligibleLookup[name] or mountedCurrent(name)) then
          allowed[#allowed + 1] = name
        end
      end
      return visible, allowed
    end

    local function catalogSignature()
      local parts = { tostring(currentWeapon() or ""), currentAspect() }
      local eligible = nativeEligible()
      for _, name in ipairs(eligible) do parts[#parts + 1] = "eligible:" .. name end
      local hero = type(CurrentRun) == "table" and CurrentRun.Hero or nil
      if type(hero) == "table" then
        for _, trait in ipairs(type(hero.Traits) == "table" and hero.Traits or {}) do
          if isHammerTrait(trait) then
            parts[#parts + 1] = table.concat({
              "mounted", tostring(trait.Name or ""), tostring(trait.Id or ""),
              tostring(trait.Rarity or ""), tostring(ownerWeapon(trait.Name, trait) or ""),
            }, ":")
          elseif isRuntimeAspect(trait) then
            parts[#parts + 1] = table.concat({
              "aspect", tostring(trait.Name or ""), tostring(trait.Id or ""),
              tostring(trait.Rarity or ""), tostring(trait.RequiredWeapon or ""),
            }, ":")
          end
        end
      end
      return table.concat(parts, "|")
    end

    local function applyExact(name)
      local value = source()
      if value == nil or not sourceContains(name) then
        error("Selected boon is not currently eligible")
      end
      requireFunctions("exact Hammer acquisition", {
        "GetEligibleUpgrades", "GetProcessedTraitData", "AddTraitToHero",
      })
      local _, eligible = nativeEligible()
      if not eligible[name] then error("Selected boon is not currently eligible") end
      local processed = GetProcessedTraitData({
        Unit = CurrentRun.Hero, TraitName = name, Rarity = "Common",
      })
      if type(processed) ~= "table" then error("Exact boon processing failed") end
      local added = AddTraitToHero({
        TraitData = processed,
        PreProcessedForDisplay = true,
        FromLoot = true,
      })
      if type(added) ~= "table" then error("Exact boon acquisition did not return a trait") end
      if type(CurrentRun.PickedTraits) == "table" then CurrentRun.PickedTraits[name] = true end
      if type(SessionMapState) == "table" then SessionMapState.LastUpgradeChoice = name end
      return added
    end

    local function needsUnequip(trait)
      return type(trait) == "table" and type(trait.PreEquipWeapons) == "table"
        and next(trait.PreEquipWeapons) ~= nil
    end

    local function removalReady(trait)
      if type(RemoveTraitData) ~= "function" then return false end
      return not needsUnequip(trait) or type(UnequipWeapon) == "function"
    end

    local function removeMounted(trait)
      if type(trait) ~= "table" or not isHammerTrait(trait) then
        error("Trait removal is unavailable for the selected target")
      end
      requireFunctions("Hammer trait removal", { "RemoveTraitData" })
      local helperWeapons = {}
      for _, weaponName in pairs(type(trait.PreEquipWeapons) == "table" and trait.PreEquipWeapons or {}) do
        if type(weaponName) == "string" then helperWeapons[#helperWeapons + 1] = weaponName end
      end
      if #helperWeapons > 0 then requireFunctions("Hammer helper weapon removal", { "UnequipWeapon" }) end
      local instanceId = trait.Id ~= nil and tostring(trait.Id) or ""
      RemoveTraitData(CurrentRun.Hero, trait, { Silent = true, SkipExpire = true })
      for _, candidate in ipairs(CurrentRun.Hero.Traits or {}) do
        if type(candidate) == "table" and candidate.Id ~= nil
            and tostring(candidate.Id) == instanceId then
          error("Direct trait removal left the selected instance mounted")
        end
      end
      for _, weaponName in ipairs(helperWeapons) do
        local owned = false
        for _, candidate in ipairs(CurrentRun.Hero.Traits or {}) do
          for _, referenced in pairs(type(candidate) == "table"
              and type(candidate.PreEquipWeapons) == "table" and candidate.PreEquipWeapons or {}) do
            if referenced == weaponName then owned = true; break end
          end
          if owned then break end
        end
        if not owned then
          UnequipWeapon({
            DestinationId = CurrentRun.Hero.ObjectId,
            Name = weaponName,
            UnloadPackages = false,
          })
          if type(MapState) == "table" and type(MapState.EquippedWeapons) == "table" then
            MapState.EquippedWeapons[weaponName] = nil
          end
        end
      end
    end

    return {
      catalogNames = catalogNames,
      catalogSignature = catalogSignature,
      isHammerTrait = isHammerTrait,
      isRuntimeAspect = isRuntimeAspect,
      removalReady = removalReady,
      applyExact = applyExact,
      removeMounted = removeMounted,
    }
  end)()

  local echoModel = (function()
    local prefix = "echo:lastRun:"

    local function previousRun()
      local history = type(GameState) == "table" and GameState.RunHistory or nil
      if type(history) ~= "table" or #history == 0 then return nil end
      local value = history[#history]
      return type(value) == "table" and value or nil
    end

    local function sourceRarity(name)
      local previous = previousRun()
      if type(previous) ~= "table" then return nil end
      if type(previous.SpecialInteractRecord) == "table" and previous.SpecialInteractRecord.Shrine then
        return nil
      end
      local cache = previous.TraitRarityCache
      if type(cache) ~= "table" or cache[name] == nil then return nil end
      local definition = type(TraitData) == "table" and TraitData[name] or nil
      if type(definition) ~= "table" or definition.ExcludeTraitFromLastRunBoonPool then return nil end
      if type(IsGodTrait) ~= "function" then return nil end
      local ok, isGod = pcall(IsGodTrait, name, { ForShop = true, ForLastRunBoon = true })
      if not ok or not isGod then return nil end
      local rarity = cache[name]
      return type(rarity) == "string" and rarity or "Common"
    end

    local function catalogTargets()
      local result = setmetatable({}, arrayMeta)
      local previous = previousRun()
      local cache = type(previous) == "table" and previous.TraitRarityCache or nil
      if type(cache) ~= "table" then return result end
      local names = {}
      for name in pairs(cache) do
        if type(name) == "string" and sourceRarity(name) ~= nil then names[#names + 1] = name end
      end
      table.sort(names)
      for _, name in ipairs(names) do
        result[#result + 1] = { name = name, rarity = sourceRarity(name) }
      end
      return result
    end

    local function catalogSignature()
      local previous = previousRun()
      if type(previous) ~= "table" then return "none" end
      local parts = {
        type(previous.SpecialInteractRecord) == "table" and previous.SpecialInteractRecord.Shrine
          and "shrine" or "ordinary",
      }
      local cache = previous.TraitRarityCache
      if type(cache) ~= "table" then return table.concat(parts, "|") end
      local names = {}
      for name in pairs(cache) do if type(name) == "string" then names[#names + 1] = name end end
      table.sort(names)
      for _, name in ipairs(names) do
        parts[#parts + 1] = tostring(name) .. ":" .. tostring(cache[name] or "")
      end
      return table.concat(parts, "|")
    end

    local function eligibleRarity(name)
      local rarity = sourceRarity(name)
      if rarity == nil then return false, nil end
      local definition = type(TraitData) == "table" and TraitData[name] or nil
      if type(definition) ~= "table" then return false, nil end
      if type(HeroHasTrait) ~= "function" or HeroHasTrait(name) then return false, nil end
      if type(IsTraitEligible) ~= "function" or not IsTraitEligible(definition) then return false, nil end
      if definition.Slot ~= nil then
        if type(HeroSlotFilled) ~= "function" or HeroSlotFilled(definition.Slot) then return false, nil end
      end
      if type(GetHeroTrait) == "function" then
        local floor = GetHeroTrait("ElementalRarityUpgradeBoon")
        if type(floor) == "table" and floor.Activated
            and (rarity == "" or rarity == "Common") then
          rarity = "Rare"
        end
      end
      return true, rarity ~= "" and rarity or "Common"
    end

    local function hiddenEntry(rewardId)
      if type(rewardId) ~= "string" or string.sub(rewardId, 1, #prefix) ~= prefix then return nil end
      local name = string.sub(rewardId, #prefix + 1)
      if name == "" or type(TraitData) ~= "table" or type(TraitData[name]) ~= "table" then return nil end
      return {
        id = rewardId, name = name, category = "角色奖励", group = "exact", kind = "trait",
        trait = name, family = "Echo", sourceId = "Echo", sourceName = "回声",
        sectionTitle = "上局祝福", acquisitionMode = "echoLastRunExact",
      }
    end

    local function applyPreviousRunExact(name, rarity)
      requireFunctions("Echo previous-run exact acquisition", {
        "GetProcessedTraitData", "AddTraitToHero",
      })
      local processed = GetProcessedTraitData({
        Unit = CurrentRun.Hero, TraitName = name, Rarity = rarity,
      })
      if type(processed) ~= "table" then error("Echo previous-run boon acquisition failed") end

      local lootSource = GetLootSourceName(name, {
        CheckEnemyData = true, GetPackageName = true,
      })
      if lootSource ~= nil then
        requireFunctions("Echo previous-run package preparation", {
          "LoadPackages", "IncrementTableValue",
        })
        if type(CurrentRun.LootTypeHistory) ~= "table" then
          error("Echo previous-run boon acquisition failed")
        end
        LoadPackages({ Name = lootSource, IgnoreAssert = true })
        IncrementTableValue(CurrentRun.LootTypeHistory, lootSource)
        if type(processed.AcquireFunctionArgs) == "table"
            and processed.AcquireFunctionArgs.GlobalVoiceLines ~= nil then
          requireFunctions("Echo previous-run voice preparation", { "LoadVoiceBanks" })
          LoadVoiceBanks(lootSource, nil, true)
        end
      end

      local added = AddTraitToHero({
        FromLoot = true,
        TraitData = processed,
        OverwriteArgs = {
          OffsetX = -50, OffsetY = -50,
          AngleMin = 90, AngleMax = 180,
          ForceMin = 80, ForceMax = 180,
          UpwardForceMin = 300, UpwardForceMax = 700,
          ReRandomizeForcePerItem = true,
          ForceToValidLocation = false,
          KeepCollision = false,
        },
      })
      if type(added) ~= "table" then error("Echo previous-run boon acquisition failed") end
      if type(SessionMapState) == "table" then SessionMapState.LastUpgradeChoice = name end
      return added
    end

    return {
      catalogTargets = catalogTargets,
      catalogSignature = catalogSignature,
      eligibleRarity = eligibleRarity,
      hiddenEntry = hiddenEntry,
      applyExact = applyPreviousRunExact,
    }
  end)()

  local function rewards()
    local cached = M.catalogCache.rewards
    local seleneSignature = seleneModel.catalogSignature()
    local hammerSignature = hammerModel.catalogSignature()
    local echoSignature = echoModel.catalogSignature()
    if type(cached) == "table"
        and cached.seleneSignature == seleneSignature
        and cached.hammerSignature == hammerSignature
        and cached.echoSignature == echoSignature then
      return cached.list, cached.allowed
    end
    local result, allowed = setmetatable({}, arrayMeta), {}
    local officialSourceOrder = officialSpecialSourceOrder()
    local familyTitles = {
      money = "金币", centaurHeart = "半人马之心", centaurSoul = "半人马之魂", soulTonic = "灵魂之水",
      healing = "恢复", armor = "护甲", hammer = "狄德勒斯之锤", pom = "力量石榴",
      utility = "其他局内奖励", meta = "局外资源奖励",
      metaHarvest = "采集与杂项资源", metaBoss = "首领资源", metaAdvanced = "高阶资源", element = "元素奖励", shop = "商店商品", well = "卡戎之井",
    }
    local knownBoonIds = {}
    for _, entry in ipairs(boonDefinitions) do knownBoonIds[entry.id] = true end
    local function addDefinition(entry)
      if allowed[entry.id] then return end
      local traitId = entry.trait
      if traitId == nil and entry.kind == "trait" then traitId = string.match(entry.id, "^trait:(.+)$") end
      local exists = (entry.kind == "loot" and type(LootData) == "table" and type(LootData[entry.id]) == "table")
        or (entry.kind == "consumable" and type(ConsumableData) == "table" and type(ConsumableData[entry.id]) == "table")
        or (entry.kind == "trait" and type(TraitData) == "table" and type(TraitData[traitId]) == "table")
      if exists then
        local section = entry.group == "pickup" and 10 or (entry.group == "exact" and 25 or 30)
        allowed[entry.id] = {
          id = entry.id, name = entry.name, category = entry.category, group = entry.group or "pickup", kind = entry.kind,
          family = entry.family, trait = traitId, storeTrait = entry.storeTrait, spawnMode = entry.spawnMode,
          acquisitionMode = entry.acquisitionMode, spellName = entry.spellName, sortSection = section,
          sortGroup = (entry.group == "special" or entry.group == "exact")
            and (officialSourceOrder[entry.sourceId] or entry.familyOrder or 999) or (entry.familyOrder or 0),
          sortOrder = entry.itemOrder or 0, sourceId = entry.sourceId, sourceName = entry.sourceName,
          sectionTitle = (entry.group == "special" or entry.group == "exact") and entry.sourceName or familyTitles[entry.family],
        }
        result[#result + 1] = allowed[entry.id]
      end
    end
    for _, entry in ipairs(rewardDefinitions) do addDefinition(entry) end

    -- RewardStoreData is the game's authoritative list of room reward pools.
    -- Add any direct LootData/ConsumableData entries that are not yet in our
    -- curated catalog. This prevents the trainer catalog from silently going
    -- stale when Supergiant adds or rearranges rewards.
    if type(RewardStoreData) == "table" then
      local storeNames = {}
      for storeName, store in pairs(RewardStoreData) do
        if storeName ~= "InvalidOverrides" and type(store) == "table" then storeNames[#storeNames + 1] = storeName end
      end
      table.sort(storeNames)
      local discovered, seenDiscovered = {}, {}
      for _, storeName in ipairs(storeNames) do
        local store = RewardStoreData[storeName]
        for _, definition in ipairs(store) do
          local id = type(definition) == "table" and definition.Name or nil
          if type(id) == "string" and not seenDiscovered[id] then
            seenDiscovered[id] = true
            local kind = type(ConsumableData) == "table" and type(ConsumableData[id]) == "table" and "consumable" or nil
            if kind == nil and type(LootData) == "table" and type(LootData[id]) == "table" then kind = "loot" end
            if kind ~= nil and not allowed[id] and not knownBoonIds[id] then
              discovered[#discovered + 1] = { id = id, kind = kind, store = storeName }
            end
          end
        end
      end
      table.sort(discovered, function(a, b) return a.id < b.id end)
      for index, entry in ipairs(discovered) do
        addDefinition({
          id = entry.id, name = entry.id, category = "其他房间奖励", kind = entry.kind,
          group = "pickup", family = "runtimeReward", familyOrder = 90, itemOrder = index,
        })
        if allowed[entry.id] then allowed[entry.id].sectionTitle = "其他房间奖励" end
      end
    end

    local officialGodOrder = officialOlympianOrder()
    for _, entry in ipairs(boonDefinitions) do
      local item = { id = entry.id, name = entry.name, category = "奥林匹斯的祝福", group = "olympian", kind = "loot", sortSection = 20, sortGroup = officialGodOrder[entry.id] or entry.order, sortOrder = 0, sectionTitle = "奥林匹斯诸神" }
      if type(LootData) == "table" and type(LootData[entry.id]) == "table" then allowed[entry.id] = item; result[#result + 1] = item end
    end
    -- Exact ordinary acquisition is projected from the same native GodLoot
    -- sources that own eligibility/replacement. These rows are catalog targets,
    -- not authorization to bypass the source's operation-time rules.
    for _, entry in ipairs(boonDefinitions) do
      local source = type(LootData) == "table" and LootData[entry.id] or nil
      if type(source) == "table" then
        local seen, ordered = {}, {}
        local function collectExact(pool)
          for _, traitName in ipairs(orderedTraitIds(pool)) do
            if not seen[traitName] then
              seen[traitName] = true
              ordered[#ordered + 1] = traitName
            end
          end
        end
        collectExact(source.PriorityUpgrades)
        collectExact(source.WeaponUpgrades)
        collectExact(source.Traits)
        for index, traitName in ipairs(ordered) do
          local id = "exact:" .. entry.id .. ":" .. traitName
          if not allowed[id] then
            local item = {
              id = id, name = traitName, category = "奥林匹斯的祝福", group = "exact", kind = "trait",
              trait = traitName, family = "olympianHermes", sourceId = entry.id, sourceName = entry.name,
              sectionTitle = entry.name, acquisitionMode = "ordinaryNative",
              sortSection = 25, sortGroup = officialGodOrder[entry.id] or entry.order or 999, sortOrder = index,
            }
            allowed[id] = item
            result[#result + 1] = item
          end
        end
      end
    end

    -- Chaos exact targets remain paired lifecycle choices. Selecting one
    -- exact phase narrows only that side of TrialUpgrade; the counterpart is
    -- still chosen from the target build's eligible native pool at operation time.
    local chaosSource = type(LootData) == "table" and LootData.TrialUpgrade or nil
    if type(chaosSource) == "table" and chaosSource.TransformingTraits then
      local chaosOrder = officialSourceOrder.Chaos or 20
      local function addChaosExactRows(pool, prefix, mode, sectionTitle, orderOffset)
        for index, traitName in ipairs(orderedTraitIds(pool)) do
          local id = "chaos:" .. prefix .. ":" .. traitName
          if not allowed[id] then
            local item = {
              id = id, name = traitName, category = "卡俄斯的祝福", group = "exact", kind = "trait",
              trait = traitName, family = "chaos", sourceId = "Chaos", sourceName = "卡俄斯",
              sectionTitle = sectionTitle, acquisitionMode = mode,
              sortSection = 25, sortGroup = chaosOrder + orderOffset, sortOrder = index,
            }
            allowed[id] = item
            result[#result + 1] = item
          end
        end
      end
      addChaosExactRows(chaosSource.PermanentTraits, "blessing", "chaosBlessing", "卡俄斯的祝福", 0)
      addChaosExactRows(chaosSource.TemporaryTraits, "curse", "chaosCurse", "卡俄斯的祝福", 1)
    end

    -- Selene exact targets are projected from the native spell owner. Main
    -- Hexes come from SpellData; talents come only from the current generated
    -- Path of Stars rather than the global TraitData talent universe.
    if type(SpellData) == "table" and type(TraitData) == "table" then
      local seleneOrder = officialSourceOrder.Selene or 10
      local spellNames = {}
      for spellName, spellData in pairs(SpellData) do
        if type(spellName) == "string" and type(spellData) == "table"
            and not spellData.Skip
            and not (type(spellData.GameStateRequirements) == "table"
              and spellData.GameStateRequirements.Skip)
            and type(spellData.TraitName) == "string"
            and type(TraitData[spellData.TraitName]) == "table" then
          spellNames[#spellNames + 1] = spellName
        end
      end
      table.sort(spellNames)
      for index, spellName in ipairs(spellNames) do
        local spellData = SpellData[spellName]
        local id = "selene:spell:" .. spellName
        local item = {
          id = id, name = spellData.TraitName, category = "角色奖励", group = "exact", kind = "trait",
          trait = spellData.TraitName, family = "hex", sourceId = "Selene", sourceName = "塞勒涅",
          sectionTitle = "塞勒涅", acquisitionMode = "seleneSpell", spellName = spellName,
          sortSection = 25, sortGroup = seleneOrder, sortOrder = index,
        }
        allowed[id] = item
        result[#result + 1] = item
      end

      local slotted = seleneModel.currentSpell()
      if type(slotted) == "table" and type(slotted.Name) == "string"
          and type(slotted.Talents) == "table" then
        local talentNames, seenTalents, availableTalents = {}, {}, {}
        for _, column in ipairs(slotted.Talents) do
          for _, node in pairs(type(column) == "table" and column or {}) do
            if type(node) == "table" and type(node.Name) == "string"
                and type(TraitData[node.Name]) == "table" then
              if not seenTalents[node.Name] then
                seenTalents[node.Name] = true
                talentNames[#talentNames + 1] = node.Name
              end
              if not node.Invested then availableTalents[node.Name] = true end
            end
          end
        end
        table.sort(talentNames)
        for index, traitName in ipairs(talentNames) do
          local id = "selene:talent:" .. slotted.Name .. ":" .. traitName
          local item = {
            id = id, name = traitName, category = "角色奖励", group = "exact", kind = "trait",
            trait = traitName, family = "hexTalent", sourceId = "Selene", sourceName = "塞勒涅",
            sectionTitle = "繁星之路", acquisitionMode = "seleneTalent", spellName = slotted.Name,
            sortSection = 25, sortGroup = seleneOrder + 1, sortOrder = index,
          }
          allowed[id] = item
          if availableTalents[traitName] then result[#result + 1] = item end
        end
      end
    end

    -- Echo's previous-run blessing is an owner action, not a trait target.
    -- Project the concrete God boons from the latest run history directly so
    -- exact acquisition never opens/waits on Echo's random three-choice menu.
    do
      local echoOrder = officialSourceOrder.Echo or 60
      for index, target in ipairs(echoModel.catalogTargets()) do
        local id = "echo:lastRun:" .. target.name
        local item = {
          id = id, name = target.name, category = "角色奖励", group = "exact", kind = "trait",
          trait = target.name, family = "Echo", sourceId = "Echo", sourceName = "回声",
          sectionTitle = "上局祝福", acquisitionMode = "echoLastRunExact",
          sortSection = 25, sortGroup = echoOrder, sortOrder = index,
        }
        allowed[id] = item
        result[#result + 1] = item
      end
    end


    -- Daedalus Hammer exact targets are the game's current native eligibility
    -- for the equipped weapon/aspect.  Mounted targets remain in the internal
    -- allowed map only so an identical completed request can return its receipt
    -- after the game removes that target from the visible eligible pool.
    do
      local visibleNames, allowedNames = hammerModel.catalogNames()
      local visible = {}
      for _, name in ipairs(visibleNames) do visible[name] = true end
      local hammerOrder = 850
      for index, traitName in ipairs(allowedNames) do
        local id = "hammer:" .. traitName
        local item = {
          id = id, name = traitName, category = "角色奖励", group = "exact", kind = "trait",
          trait = traitName, family = "hammer", sourceId = "WeaponUpgrade",
          sourceName = "狄德勒斯之锤", sectionTitle = "狄德勒斯之锤",
          acquisitionMode = "hammerNative",
          sortSection = 25, sortGroup = hammerOrder, sortOrder = index,
        }
        allowed[id] = item
        if visible[traitName] then result[#result + 1] = item end
      end
    end

    local buckets = {}
    for _, source in ipairs(specialSourceDefinitions) do buckets[source.id] = { seen = {}, traits = {} } end
    local function collect(sourceId, traits)
      local bucket = buckets[sourceId]
      if not bucket then return end
      for _, traitName in ipairs(orderedTraitIds(traits)) do
        if not bucket.seen[traitName] then bucket.seen[traitName] = true; bucket.traits[#bucket.traits + 1] = traitName end
      end
    end
    if type(UnitSetData) == "table" then
      for setKey, unitSet in pairs(UnitSetData) do
        if type(unitSet) == "table" then
          for unitKey, unit in pairs(unitSet) do
            if type(unit) == "table" then
              local speaker = type(unit.SpeakerName) == "string" and unit.SpeakerName or ""
              local sourceId = specialTraitSources[speaker] and speaker or nil
              if sourceId == nil and type(unitKey) == "string" then
                for _, source in ipairs(specialSourceDefinitions) do
                  if string.find(unitKey, source.id, 1, true) then sourceId = source.id; break end
                end
              end
              if sourceId == nil and type(setKey) == "string" then
                for _, source in ipairs(specialSourceDefinitions) do
                  if string.find(setKey, source.id, 1, true) then sourceId = source.id; break end
                end
              end
              if sourceId then collect(sourceId, unit.Traits) end
            end
          end
        end
      end
    end
    for _, source in ipairs(specialSourceDefinitions) do
      local bucket = buckets[source.id]
      for index, traitName in ipairs(bucket and bucket.traits or {}) do
        local id = "trait:" .. traitName
        if not allowed[id] and not nativeChoiceOnlyTraits[traitName] then
          local item = {
            id = id, name = traitName, category = "角色奖励", group = "exact", kind = "trait", trait = traitName,
            family = source.id, sourceId = source.id, sourceName = source.name, sectionTitle = source.name,
            nativeChoice = nativeSpecialChoiceSources[source.id] == true,
            acquisitionMode = source.id == "Arachne" and "costume" or "direct",
            sortSection = 25, sortGroup = officialSourceOrder[source.id] or specialTraitSourceOrder[source.id] or 999, sortOrder = index,
          }
          allowed[id] = item; result[#result + 1] = item
        end
      end
    end
    table.sort(result, function(a, b)
      local sa, sb = a.sortSection or 999, b.sortSection or 999
      if sa ~= sb then return sa < sb end
      local ga, gb = a.sortGroup or 999, b.sortGroup or 999
      if ga ~= gb then return ga < gb end
      local oa, ob = a.sortOrder or 999, b.sortOrder or 999
      if oa ~= ob then return oa < ob end
      return a.id < b.id
    end)
    if type(LootData) == "table" and type(ConsumableData) == "table"
        and type(RewardStoreData) == "table" and type(UnitSetData) == "table" and type(TraitData) == "table" then
      M.catalogCache.rewards = {
        list = result, allowed = allowed, seleneSignature = seleneSignature,
        hammerSignature = hammerSignature, echoSignature = echoSignature,
      }
    end
    return result, allowed
  end
  local statOrder, statRegistry
  local function statSupport()
    local result = {}
    for _, stat in ipairs(statOrder or {}) do
      local entry = statRegistry and statRegistry[stat] or nil
      local supported = false
      if entry ~= nil then
        if entry.support == nil then supported = true
        else
          local ok, value = pcall(entry.support)
          supported = ok and not not value
        end
      end
      result[stat] = supported
    end
    return result
  end
  local function statState(stat, hero, support)
    local entry = statRegistry and statRegistry[stat] or nil
    local value = nil
    if entry and entry.value then
      local ok, result = pcall(entry.value, hero, support)
      if ok and finite(result) then value = result end
    end
    return { value = value, target = M.statTargets[stat], locked = M.statTargets[stat] ~= nil }
  end
  local function statAvailableMap(support)
    local result = {}
    for _, stat in ipairs(statOrder or {}) do
      local entry = statRegistry and statRegistry[stat] or nil
      local available = false
      if support[stat] and entry ~= nil then
        if entry.available == nil then available = ready()
        else
          local ok, value = pcall(entry.available)
          available = ok and not not value
        end
      end
      result[stat] = available
    end
    return result
  end
  local function anyAvailableStat(available)
    for _, stat in ipairs(statOrder or {}) do if available[stat] then return true end end
    return false
  end
  local function featureAvailable(entry)
    if entry == nil then return false end
    if entry.available == nil then return ready() end
    local ok, value = pcall(entry.available)
    return ok and not not value
  end
  local function castWeaponGateVerified(runtime)
    if type(runtime) ~= "table" or not ready() or runtime.hero ~= CurrentRun.Hero then return false end
    for _, weaponName in ipairs(castModel.effectiveWeapons(runtime.hero)) do
      for _, property in ipairs(castModel.propertyOrder) do
        local value, ok = readCastWeaponProperty(property, runtime.hero, weaponName)
        if not ok or value ~= castModel.overrides[property] then return false end
      end
    end
    return true
  end
  local function castDiagnostics()
    local runtime = M.castRuntime
    local diagnostics = {
      method = "nativeMultiCastControlSet",
      effectHook = owns("SetEffectProperty"), weaponHook = owns("SetWeaponProperty"),
      effectOverrides = { WeaponCastAttackDisable = false, WeaponCastSelfSlow = false, WeaponCastSelfSlow2 = false },
      castVariantWeapons = castModel.variantWeapons,
    }
    if type(runtime) ~= "table" then return diagnostics end
    diagnostics.heroBound = ready() and runtime.hero == CurrentRun.Hero or false
    diagnostics.applied = not not runtime.applied
    if not diagnostics.heroBound then
      diagnostics.weaponGateVerified = false
      return diagnostics
    end
    -- The recast decision belongs to whichever weapon actually fires, so report
    -- the resolved delivery set and each weapon's own gate instead of only the
    -- base WeaponCast.  This is the runtime evidence surface for a modified Cast
    -- shape (for example Hestia's thrown cast or Hades' attached cast).
    local effective = castModel.effectiveWeapons(runtime.hero)
    diagnostics.effectiveWeapons = effective
    local actual = {}
    for _, weaponName in ipairs(effective) do
      local values = {}
      for _, property in ipairs(castModel.propertyOrder) do
        local value, ok = readCastWeaponProperty(property, runtime.hero, weaponName)
        if ok and value ~= nil then values[property] = value end
      end
      actual[weaponName] = values
    end
    diagnostics.weaponProperties = actual
    diagnostics.weaponGateVerified = castWeaponGateVerified(runtime)
    if type(SessionMapState) == "table" then
      diagnostics.lastProjectileId = SessionMapState.LastCastProjectileId
      local tracked = 0
      local seen = {}
      if type(SessionMapState.CastAttachedProjectiles) == "table" then
        for projectileId in pairs(SessionMapState.CastAttachedProjectiles) do
          local exists = true
          if type(ProjectileExists) == "function" then
            local ok, value = pcall(ProjectileExists, { Id = projectileId })
            exists = ok and not not value
          end
          if exists then tracked = tracked + 1; seen[projectileId] = true end
        end
      end
      local lastId = SessionMapState.LastCastProjectileId
      if lastId ~= nil and not seen[lastId] and type(ProjectileExists) == "function" then
        local ok, exists = pcall(ProjectileExists, { Id = lastId })
        if ok and exists then tracked = tracked + 1 end
        diagnostics.lastProjectileExists = ok and not not exists or false
      end
      diagnostics.activeTrackedCasts = tracked
    end
    return diagnostics
  end
  local featureOrder, featureRegistry
  local function featureRuntimeMaps(hero)
    local supportMap, activeMap, dormantMap = {}, {}, {}
    for _, key in ipairs(featureOrder or {}) do
      local entry = featureRegistry and featureRegistry[key] or nil
      local function evaluate(callback, default)
        if callback == nil then return default end
        local ok, value = pcall(callback, hero)
        return ok and not not value or false
      end
      supportMap[key] = entry ~= nil and evaluate(entry.support, true) or false
      activeMap[key] = entry ~= nil and evaluate(entry.active, false) or false
      local desired = entry and (entry.desired and evaluate(entry.desired, false) or not not M.desiredFeatures[key]) or false
      local waitingForEnvironment = desired and supportMap[key] and not activeMap[key] and not featureAvailable(entry)
      if entry and (evaluate(entry.dormant, false) or waitingForEnvironment) then dormantMap[key] = true end
    end
    return supportMap, activeMap, dormantMap
  end
  -- Current-run trait/buff inventory and management capability projection.
  --
  -- The inventory remains live runtime observation. The ids below are only a
  -- target snapshot: resident generation + CurrentRun table identity + trait.Id.
  -- None is persisted, and every mutation re-resolves the selection immediately
  -- before it calls a game-owned operation.
  local traitManagement = (function()
    local deferredTraitIssues = {
      other = 221,
    }
    local rarityOrder = { "Common", "Rare", "Epic", "Heroic" }
    local function isArachneCostumeChoice(name)
      if type(name) ~= "string" or type(PresetEventArgs) ~= "table" then return false end
      local choiceData = PresetEventArgs.ArachneCostumeChoices
      if type(choiceData) ~= "table" or type(choiceData.UpgradeOptions) ~= "table" then return false end
      for _, option in pairs(choiceData.UpgradeOptions) do
        if type(option) == "table" and option.ItemName == name then return true end
      end
      return false
    end

    local function isArachneCostumeTrait(name)
      if type(name) ~= "string" or type(TraitData) ~= "table" then return false end
      local definition = TraitData[name]
      if type(definition) ~= "table" or type(definition.InheritFrom) ~= "table" then return false end
      local costume = false
      for _, parent in ipairs(definition.InheritFrom) do
        if parent == "CostumeTrait" then
          costume = true
          break
        end
      end
      if not costume then return false end
      if isArachneCostumeChoice(name) then return true end
      local npc = type(EnemyData) == "table" and EnemyData.NPC_Arachne_01 or nil
      for _, traitName in pairs(type(npc) == "table" and npc.Traits or {}) do
        if traitName == name then return true end
      end
      return false
    end

    local function applyCostume(name)
      if not isArachneCostumeChoice(name) then error("Exact costume target is unavailable") end
      requireFunctions("Arachne costume acquisition", { "AddTraitToHero", "SetupCostume" })

      local previous = {}
      for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
        if type(trait) == "table" and trait.Name ~= name and isArachneCostumeTrait(trait.Name) then
          previous[#previous + 1] = trait
        end
      end
      if #previous > 0 then
        requireFunctions("Arachne costume replacement", { "RemoveTraitData" })
      end

      for _, trait in ipairs(previous) do
        local ok, message = pcall(
          RemoveTraitData, CurrentRun.Hero, trait, { Silent = true, SkipExpire = true }
        )
        local stillMounted = false
        for _, candidate in ipairs(CurrentRun.Hero.Traits or {}) do
          if candidate == trait then
            stillMounted = true
            break
          end
        end
        if not ok or stillMounted then
          pcall(SetupCostume)
          if not ok then error(message) end
          error("Arachne costume replacement left previous owner mounted")
        end
      end

      local ok, added = pcall(AddTraitToHero, { TraitName = name, FromLoot = true })
      local setupOk, setupMessage = pcall(SetupCostume)
      if not ok then error(added) end
      if type(added) ~= "table" then error("Arachne costume acquisition failed") end
      if not setupOk then error(setupMessage) end

      for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
        if trait ~= added and type(trait) == "table" and isArachneCostumeTrait(trait.Name) then
          error("Arachne costume replacement left previous owner mounted")
        end
      end
      return added
    end

    local function removeCostume(trait)
      if type(trait) ~= "table" or not isArachneCostumeTrait(trait.Name) then
        error("Trait removal is unavailable for the selected target")
      end
      requireFunctions("Arachne costume removal", { "RemoveTraitData", "SetupCostume" })
      local instanceId = trait.Id ~= nil and tostring(trait.Id) or ""
      local ok, message = pcall(
        RemoveTraitData, CurrentRun.Hero, trait, { Silent = true, SkipExpire = true }
      )
      local stillMounted = false
      for _, candidate in ipairs(CurrentRun.Hero.Traits or {}) do
        if candidate == trait or (type(candidate) == "table" and candidate.Id ~= nil
            and instanceId ~= "" and tostring(candidate.Id) == instanceId) then
          stillMounted = true
          break
        end
      end
      if not stillMounted then
        local setupOk, setupMessage = pcall(SetupCostume)
        if not setupOk then error(setupMessage) end
      end
      if not ok then error(message) end
      if stillMounted then error("Arachne costume removal left owner state mounted") end
    end

    local function traitLevel(trait)
      if type(trait) ~= "table" then return 1 end
      local value = trait.StackNum
      if not finite(value) or value < 1 then return 1 end
      return math.floor(value)
    end

    local function traitRarity(trait)
      return type(trait) == "table" and type(trait.Rarity) == "string" and trait.Rarity or ""
    end

    local function sameNameCount(name)
      local count = 0
      if type(CurrentRun) == "table" and type(CurrentRun.Hero) == "table"
          and type(CurrentRun.Hero.Traits) == "table" then
        for _, trait in ipairs(CurrentRun.Hero.Traits) do
          if type(trait) == "table" and trait.Name == name then count = count + 1 end
        end
      end
      return count
    end

    local function specialTraitSourceId(name)
      if type(name) ~= "string" or name == "" then return "" end
      for sourceId, definition in pairs(nativeSpecialChoiceDefinitions) do
        local npcData = type(EnemyData) == "table" and EnemyData[definition.npc] or nil
        if type(npcData) == "table" and type(npcData.Traits) == "table" then
          for _, traitName in pairs(npcData.Traits) do
            if traitName == name then return sourceId end
          end
        end
        local choiceData = definition.choices ~= nil and type(PresetEventArgs) == "table"
          and PresetEventArgs[definition.choices] or nil
        if type(choiceData) == "table" and type(choiceData.UpgradeOptions) == "table" then
          for _, option in pairs(choiceData.UpgradeOptions) do
            if type(option) == "table" and option.ItemName == name then return sourceId end
          end
        end
      end
      return ""
    end

    local function directSpecialEditLifecycleSafe(trait)
      if type(trait) ~= "table" or type(trait.Name) ~= "string" then return false end
      local definition = type(TraitData) == "table" and TraitData[trait.Name] or nil
      if type(definition) ~= "table" then return false end

      -- Acquisition callbacks grant state outside the mounted row. Rebuilding
      -- or levelling that row cannot undo/recompute those one-shot rewards.
      for _, key in ipairs({ "AcquireFunctionName", "AcquireFunction" }) do
        if trait[key] ~= nil or definition[key] ~= nil then return false end
      end

      -- IncreaseTraitLevel/AddRarityToTraits both rebuild with SkipSetup. A
      -- setup/counter owner is editable only when the game provides its own
      -- explicit level/rarity reconciliation callback.
      local hasReconcile = type(definition.OnLevelOrRarityChangeFunctionName) == "string"
          and definition.OnLevelOrRarityChangeFunctionName ~= ""
      for _, key in ipairs({
        "CurrentRoom", "RoomsPerUpgrade", "Uses", "RemainingUses",
        "OnExpire", "OnExpireFunctionName", "SetupFunction", "SetupFunctions",
        "PreEquipWeapons", "UseFunctionName", "UseFunctionNames",
      }) do
        if (trait[key] ~= nil or definition[key] ~= nil) and not hasReconcile then
          return false
        end
      end
      return true
    end

    local function directSpecialLevelMeaningful(trait)
      if type(trait) ~= "table" or type(trait.Name) ~= "string"
          or type(IncreaseTraitLevel) ~= "function"
          or type(GetProcessedTraitData) ~= "function"
          or type(ExtractValues) ~= "function"
          or not directSpecialEditLifecycleSafe(trait) then
        return false
      end
      local definition = type(TraitData) == "table" and TraitData[trait.Name] or nil
      if trait.BlockStacking or (type(definition) == "table" and definition.BlockStacking) then
        return false
      end
      local function signature(stackNum)
        local ok, processed = pcall(GetProcessedTraitData, {
          Unit = CurrentRun.Hero,
          TraitName = trait.Name,
          StackNum = stackNum,
          RarityMultiplier = trait.RarityMultiplier,
        })
        if not ok or type(processed) ~= "table" then return nil end
        processed.Rarity = trait.Rarity or processed.Rarity
        local extracted = pcall(ExtractValues, CurrentRun.Hero, processed, processed)
        if not extracted or type(processed.ExtractData) ~= "table" then return nil end
        local encoded, value = pcall(M.json, processed.ExtractData)
        return encoded and value or nil
      end
      local current = traitLevel(trait)
      local before = signature(current)
      local after = signature(current + 1)
      return before ~= nil and after ~= nil and before ~= after
    end

    local function directSpecialRarityMeaningful(trait)
      if type(trait) ~= "table" or type(trait.Name) ~= "string"
          or type(AddRarityToTraits) ~= "function" then
        return false
      end
      local definition = type(TraitData) == "table" and TraitData[trait.Name] or nil
      if type(definition) ~= "table" or type(definition.RarityLevels) ~= "table"
          or trait.BlockInRunRarify or definition.BlockInRunRarify
          or not directSpecialEditLifecycleSafe(trait) then
        return false
      end
      return true
    end

    local function directSpecialRemovalSafe(trait)
      if type(trait) ~= "table" or type(trait.Name) ~= "string"
          or type(RemoveTraitData) ~= "function" then
        return false
      end
      local definition = type(TraitData) == "table" and TraitData[trait.Name] or nil
      if type(definition) ~= "table" then return false end
      -- RemoveTraitData is authoritative for trait-local callbacks/properties.
      -- These markers instead indicate acquisition/setup/counter/weapon state
      -- that lives outside the row and therefore needs an owner-specific path.
      for _, key in ipairs({
        "AcquireFunctionName", "AcquireFunction", "SetupFunction", "SetupFunctions",
        "OnExpire", "OnExpireFunctionName", "Uses", "RemainingUses",
        "CurrentRoom", "RoomsPerUpgrade", "PreEquipWeapons",
        "UseFunctionName", "UseFunctionNames", "AddMetaUpgradeLastStands",
      }) do
        if trait[key] ~= nil or definition[key] ~= nil then return false end
      end
      return true
    end

    local function directSpecialCostumeArmor(trait)
      if type(trait) ~= "table" or type(trait.Name) ~= "string" then return false end
      local definition = type(TraitData) == "table" and TraitData[trait.Name] or nil
      if type(definition) ~= "table" then return false end

      local function inheritsCostume(value)
        if type(value) ~= "table" then return false end
        if value.CostumeTrait == true then return true end
        for _, parent in pairs(type(value.InheritFrom) == "table" and value.InheritFrom or {}) do
          if parent == "CostumeTrait" then return true end
        end
        return false
      end
      if not inheritsCostume(trait) and not inheritsCostume(definition) then return false end

      local function hasCostumeArmor(value)
        if type(value) ~= "table" then return false end
        if type(value.SetupFunction) == "table" and value.SetupFunction.Name == "CostumeArmor" then
          return true
        end
        for _, setup in pairs(type(value.SetupFunctions) == "table" and value.SetupFunctions or {}) do
          if type(setup) == "table" and setup.Name == "CostumeArmor" then return true end
        end
        return false
      end
      return hasCostumeArmor(trait) or hasCostumeArmor(definition)
    end

    local function removeDirectSpecial(trait)
      if type(trait) ~= "table" or trait.Id == nil then
        error("Trait removal is unavailable for the selected target")
      end
      local refreshCostume = directSpecialCostumeArmor(trait)
      if refreshCostume and type(SetupCostume) ~= "function" then
        error("Direct costume armor removal is unavailable")
      end
      local instanceId = tostring(trait.Id)
      local ok, message = pcall(
        RemoveTraitData, CurrentRun.Hero, trait, { Silent = true, SkipExpire = true }
      )
      local stillMounted = false
      for _, candidate in ipairs(CurrentRun.Hero.Traits or {}) do
        if type(candidate) == "table" and candidate.Id ~= nil
            and tostring(candidate.Id) == instanceId then
          stillMounted = true
          break
        end
      end

      -- Native RemoveTraitData already owns armor-source teardown. Costume
      -- refresh is the remaining owner state and must run even when removal
      -- acknowledged late, before the request is surfaced outcome-unknown.
      if not stillMounted and refreshCostume then
        local setupOk, setupMessage = pcall(SetupCostume)
        if not setupOk then error(setupMessage) end
      end
      if not ok then error(message) end
      if stillMounted then error("Direct trait removal left the selected instance mounted") end
    end

    local function traitSourceId(trait)
      if type(trait) ~= "table" then return "" end
      if hammerModel.isHammerTrait(trait) or hammerModel.isRuntimeAspect(trait) then
        return "WeaponUpgrade"
      end
      local specialSource = specialTraitSourceId(trait.Name)
      if specialSource ~= "" then return specialSource end
      if type(trait.LootDataName) == "string" and trait.LootDataName ~= "" then return trait.LootDataName end
      if type(trait.SourceId) == "string" and trait.SourceId ~= "" then return trait.SourceId end
      if type(GetLootSourceName) == "function" and type(trait.Name) == "string" then
        local ok, source = pcall(GetLootSourceName, trait.Name, { ForBoonInfo = true, CheckEnemyData = true })
        if ok and type(source) == "string" then return source end
      end
      return ""
    end

    local function sellScreenEligible(trait)
      if type(trait) ~= "table" then return false, "missingTarget" end
      if type(trait.Name) ~= "string" or trait.Name == "" then return false, "noTraitName" end
      if trait.Rarity == nil then return false, "noRarity" end
      if type(IsGodTrait) ~= "function" then return false, "predicateUnavailable" end
      local ok, isGod = pcall(IsGodTrait, trait.Name, { ForShop = true })
      if not ok then return false, "predicateFailed" end
      if not isGod then return false, "notShopGodOwned" end
      return true, ""
    end

    local function listHasTraitName(list, name)
      if type(list) ~= "table" or type(name) ~= "string" then return false end
      for _, value in pairs(list) do
        local candidate = type(value) == "table" and (value.ItemName or value.TraitName or value.Name) or value
        if candidate == name then return true end
      end
      return false
    end

    local function chaosLifecycleState(trait)
      if type(trait) ~= "table" or type(trait.Name) ~= "string" then return "" end
      local source = type(LootData) == "table" and LootData.TrialUpgrade or nil
      if type(source) ~= "table" then return "" end
      if listHasTraitName(source.TemporaryTraits, trait.Name) then return "curse" end
      if listHasTraitName(source.PermanentTraits, trait.Name) then return "blessing" end
      return ""
    end

    local function chaosLinkedTraitName(trait)
      if chaosLifecycleState(trait) ~= "curse" then return "" end
      local onExpire = trait.OnExpire
      local linked = type(onExpire) == "table" and onExpire.TraitData or nil
      return type(linked) == "table" and type(linked.Name) == "string" and linked.Name or ""
    end

    local keepsakeModel = (function()
      local function ownerName()
        if type(GameState) ~= "table" or type(GameState.LastAwardTrait) ~= "string"
            or GameState.LastAwardTrait == "" then
          return ""
        end
        local name = GameState.LastAwardTrait
        if type(TraitData) ~= "table" or type(TraitData[name]) ~= "table" then return "" end
        return name
      end

      local function isMounted(trait)
        local name = ownerName()
        return name ~= "" and type(trait) == "table" and trait.Name == name
      end

      local function mountedTrait(name)
        for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
          if type(trait) == "table" and trait.Name == name then return trait end
        end
        return nil
      end

      local function removalReady()
        return ownerName() ~= "" and type(UnequipKeepsake) == "function"
      end

      local function rankReady(trait)
        if not isMounted(trait) or type(trait.Rarity) ~= "string"
            or type(UnequipKeepsake) ~= "function" or type(EquipKeepsake) ~= "function"
            or type(PersistentKeepsakeKeys) ~= "table" or type(UpdateTraitNumber) ~= "function" then
          return false
        end
        local definition = type(TraitData) == "table" and TraitData[trait.Name] or nil
        return type(definition) == "table" and type(definition.RarityLevels) == "table"
      end

      local function targetRankAvailable(trait, rarity)
        if not rankReady(trait) or type(rarity) ~= "string" then return false end
        local definition = TraitData[trait.Name]
        return definition.RarityLevels[rarity] ~= nil
      end

      local function teardownOwner()
        if not removalReady() then error("Keepsake owner removal is unavailable") end
        local name = ownerName()
        UnequipKeepsake(CurrentRun.Hero, name, { AdvanceKeepsakeMoment = true })
        for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
          if type(trait) == "table" and trait.Name == name then
            error("Keepsake owner removal left the selected trait mounted")
          end
        end
      end

      local function rebuildRarity(trait, targetRarity)
        if not targetRankAvailable(trait, targetRarity) then
          error("Trait rarity editing is unavailable for the selected target")
        end
        local name = ownerName()
        local persistentValues = {}
        for _, key in pairs(PersistentKeepsakeKeys) do
          local value = trait[key]
          if key == "DoorHealReserve" and value ~= nil and type(round) == "function" then
            value = round(value)
          end
          persistentValues[key] = value
        end

        local firstError = nil
        local function attempt(work)
          local ok, value = pcall(work)
          if not ok then
            if firstError == nil then firstError = tostring(value) end
            return nil
          end
          return value
        end

        -- This mirrors the game's AdvanceKeepsake(fromTrait=true) rebuild
        -- shape, with ForceRarity as the only semantic difference. No durable
        -- chamber progress or selected Keepsake identity is touched.
        attempt(function()
          UnequipKeepsake(CurrentRun.Hero, name, {
            SkipValidateHealth = true,
            AdvanceKeepsakeMoment = true,
          })
        end)
        if mountedTrait(name) ~= nil then
          if firstError ~= nil then error(firstError) end
          error("Trait rarity recompute did not reach the requested rarity")
        end

        attempt(function()
          return EquipKeepsake(CurrentRun.Hero, name, {
            SkipSetup = true,
            ForceRarity = targetRarity,
          })
        end)
        local rebuilt = mountedTrait(name)
        if type(rebuilt) ~= "table" then
          if firstError ~= nil then error(firstError) end
          error("Trait rarity recompute did not reach the requested rarity")
        end

        -- Even if EquipKeepsake acknowledged late after mounting the owner,
        -- restore the same runtime-owned fields that native AdvanceKeepsake
        -- preserves before surfacing outcome-unknown.
        for key, value in pairs(persistentValues) do rebuilt[key] = value end

        if rebuilt.CostumeTrait and type(rebuilt.SetupFunction) == "table"
            and rebuilt.SetupFunction.Name == "CostumeArmor"
            and finite(rebuilt.CurrentArmor) and rebuilt.CurrentArmor ~= 0
            and type(AddHealthBuffer) == "function" then
          attempt(function()
            AddHealthBuffer(rebuilt.CurrentArmor, rebuilt.Name)
            if type(FrameState) == "table" then FrameState.RequestUpdateHealthUI = true end
          end)
        end
        if name == "LowHealthCritKeepsake" then
          if type(IsTraitActive) == "function" and not IsTraitActive(rebuilt)
              and type(rebuilt.PropertyChanges) == "table"
              and type(rebuilt.PropertyChanges[1]) == "table" then
            rebuilt.PropertyChanges[1].ChangeValue = 1
          end
          if type(ValidateMaxHealth) == "function" then
            attempt(function() ValidateMaxHealth(true) end)
          end
          if type(FrameState) == "table" then FrameState.RequestUpdateHealthUI = true end
        end
        if name == "ReincarnationKeepsake" then rebuilt.CustomTrayText = nil end
        if name == "DecayingBoostKeepsake" then
          rebuilt.CurrentKeepsakeDamageBonus = rebuilt.InitialKeepsakeDamageBonus
        end
        if name == "ManaOverTimeRefundKeepsake" and type(ValidateMaxMana) == "function" then
          attempt(function() ValidateMaxMana() end)
        end
        attempt(function() UpdateTraitNumber(rebuilt) end)

        if rebuilt.Rarity ~= targetRarity then
          error("Trait rarity recompute did not reach the requested rarity")
        end
        if firstError ~= nil then error(firstError) end
        return rebuilt
      end

      return {
        ownerName = ownerName,
        isMounted = isMounted,
        removalReady = removalReady,
        rankReady = rankReady,
        targetRankAvailable = targetRankAvailable,
        rebuildRarity = rebuildRarity,
        teardown = teardownOwner,
      }
    end)()

    local arcanaModel = (function()
      local unsafeTraitKeys = {
        "AcquireFunctionName", "AcquireFunction", "SetupFunction", "SetupFunctions",
        "OnExpire", "OnExpireFunctionName", "Uses", "RemainingUses", "CurrentRoom",
        "RerollCount", "BonusMoney", "AddMetaUpgradeLastStands", "MetaConversionUses",
        "BossEncounterShieldHits",
      }

      local function ownerName(trait)
        if type(trait) ~= "table" or type(trait.Name) ~= "string" or trait.Name == ""
            or type(GameState) ~= "table" or type(GameState.MetaUpgradeState) ~= "table"
            or type(MetaUpgradeCardData) ~= "table" then
          return ""
        end
        local found = ""
        for cardName, state in pairs(GameState.MetaUpgradeState) do
          local card = MetaUpgradeCardData[cardName]
          if type(state) == "table" and state.Equipped
              and type(card) == "table" and card.TraitName == trait.Name then
            if found ~= "" and found ~= cardName then return "" end
            found = cardName
          end
        end
        return found
      end

      local function ownerState(trait)
        local name = ownerName(trait)
        if name == "" then return "", nil, nil end
        return name, GameState.MetaUpgradeState[name], MetaUpgradeCardData[name]
      end

      local function mountedTrait(name)
        local found = nil
        for _, mounted in ipairs(CurrentRun.Hero.Traits or {}) do
          if type(mounted) == "table" and mounted.Name == name then
            if found ~= nil then return nil end
            found = mounted
          end
        end
        return found
      end

      local function definitionSafe(trait, card)
        if type(trait) ~= "table" or type(card) ~= "table" then return false end
        if card.OnGrantedFunctionName ~= nil or card.OnUpgradedFunctionName ~= nil then
          return false
        end
        local definition = type(TraitData) == "table" and TraitData[trait.Name] or nil
        if type(definition) ~= "table" or type(definition.RarityLevels) ~= "table" then
          return false
        end
        for _, key in ipairs(unsafeTraitKeys) do
          if trait[key] ~= nil or definition[key] ~= nil then return false end
        end
        return true
      end

      local function rarityInNativeOrder(rarity)
        local order = type(TraitRarityData) == "table" and TraitRarityData.RarityUpgradeOrder or nil
        if type(order) ~= "table" then return false end
        for _, value in ipairs(order) do
          if value == rarity then return true end
        end
        return false
      end

      local function adjacencyMultiplier(state)
        local bonuses = type(state) == "table" and state.AdjacencyBonuses or nil
        local custom = type(bonuses) == "table" and bonuses.CustomMultiplier or nil
        if custom == nil then return 1 end
        if not finite(custom) then return nil end
        return 1 + custom
      end

      local function rankReady(trait)
        local _, state, card = ownerState(trait)
        if type(state) ~= "table" or type(card) ~= "table"
            or type(trait.Rarity) ~= "string"
            or type(RemoveWeaponTrait) ~= "function" or type(AddTraitToHero) ~= "function"
            or type(ValidateMaxHealth) ~= "function" or type(ValidateMaxMana) ~= "function"
            or type(HandleWeaponAnimSwaps) ~= "function"
            or adjacencyMultiplier(state) == nil then
          return false
        end
        return definitionSafe(trait, card)
      end

      local function targetRankAvailable(trait, rarity)
        if not rankReady(trait) or type(rarity) ~= "string" or not rarityInNativeOrder(rarity) then
          return false
        end
        return TraitData[trait.Name].RarityLevels[rarity] ~= nil
      end

      local function durableSnapshot(state)
        local adjacency = type(state.AdjacencyBonuses) == "table" and state.AdjacencyBonuses or nil
        return {
          state = state,
          unlocked = state.Unlocked,
          equipped = state.Equipped,
          level = state.Level,
          adjacency = adjacency,
          adjacencyMultiplier = adjacency and adjacency.CustomMultiplier or nil,
        }
      end

      local function durableUnchanged(owner, before)
        local state = type(GameState) == "table" and type(GameState.MetaUpgradeState) == "table"
          and GameState.MetaUpgradeState[owner] or nil
        if state ~= before.state or state.Unlocked ~= before.unlocked
            or state.Equipped ~= before.equipped or state.Level ~= before.level
            or state.AdjacencyBonuses ~= before.adjacency then
          return false
        end
        local currentMultiplier = type(state.AdjacencyBonuses) == "table"
          and state.AdjacencyBonuses.CustomMultiplier or nil
        return currentMultiplier == before.adjacencyMultiplier
      end

      local function rebuildRarity(trait, targetRarity)
        if not targetRankAvailable(trait, targetRarity) then
          error("Trait rarity editing is unavailable for the selected target")
        end
        local owner, state = ownerState(trait)
        local name = trait.Name
        local multiplier = adjacencyMultiplier(state)
        local before = durableSnapshot(state)
        local firstError = nil

        local function attempt(work)
          local ok, value = pcall(work)
          if not ok then
            if firstError == nil then firstError = tostring(value) end
            return nil
          end
          return value
        end

        -- Mirror the native pre-run Arcana owner path while keeping
        -- MetaUpgradeState read-only. A forced rarity changes only this
        -- mounted run effect and carries the owner's current adjacency state.
        attempt(function() RemoveWeaponTrait(name, { Silent = true }) end)
        if mountedTrait(name) ~= nil then
          if firstError ~= nil then error(firstError) end
          error("Trait rarity recompute did not reach the requested rarity")
        end

        attempt(function()
          return AddTraitToHero({
            SkipNewTraitHighlight = true,
            TraitName = name,
            Rarity = targetRarity,
            CustomMultiplier = multiplier,
            SourceName = owner,
          })
        end)
        local rebuilt = mountedTrait(name)
        if type(rebuilt) ~= "table" then
          if firstError ~= nil then error(firstError) end
          error("Trait rarity recompute did not reach the requested rarity")
        end

        -- These are the native pre-run derived refreshes that are safe to
        -- replay for the declarative subset. Cards with one-shot grant/upgrade
        -- callbacks or mutable setup state never receive this capability.
        attempt(function() ValidateMaxHealth() end)
        attempt(function() ValidateMaxMana() end)
        attempt(function() HandleWeaponAnimSwaps() end)

        if rebuilt.Rarity ~= targetRarity or ownerName(rebuilt) ~= owner then
          error("Trait rarity recompute did not reach the requested rarity")
        end
        if not durableUnchanged(owner, before) then
          error("Arcana runtime edit changed durable card progression")
        end
        if firstError ~= nil then error(firstError) end
        return rebuilt
      end

      return {
        ownerName = ownerName,
        isMounted = function(trait) return ownerName(trait) ~= "" end,
        rankReady = rankReady,
        targetRankAvailable = targetRankAvailable,
        rebuildRarity = rebuildRarity,
      }
    end)()

    local familiarModel = (function()
      local function ownerName()
        if type(GameState) ~= "table" or type(GameState.EquippedFamiliar) ~= "string"
            or GameState.EquippedFamiliar == "" then
          return ""
        end
        local name = GameState.EquippedFamiliar
        if type(FamiliarData) ~= "table" or type(FamiliarData[name]) ~= "table" then
          return ""
        end
        return name
      end

      local function ownerData()
        local name = ownerName()
        return name ~= "" and FamiliarData[name] or nil
      end

      local function mountedName(name)
        if type(name) ~= "string" or name == "" then return false end
        local data = ownerData()
        if type(data) ~= "table" or type(data.TraitNames) ~= "table" then return false end
        for _, traitName in ipairs(data.TraitNames) do
          if traitName == name then return true end
        end
        if name ~= "RestedFamiliarResourceBonus" then return false end
        for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
          if type(trait) == "table" and trait.Name == name then return true end
        end
        return false
      end

      local function isMounted(trait)
        return type(trait) == "table" and mountedName(trait.Name)
      end

      local function canLevel(trait)
        if not isMounted(trait) or type(IncreaseTraitLevel) ~= "function" then return false end
        -- Toula's primary stack also owns a live Last Stand record, and the
        -- damage-modifier helper traits are copied onto the live Familiar unit
        -- at spawn time. Do not expose a half-applied runtime level edit.
        if trait.Name == "LastStandFamiliar"
            or trait.Name == "RestedFamiliarResourceBonus" then return false end
        local definition = type(TraitData) == "table" and TraitData[trait.Name] or nil
        local model = type(definition) == "table" and definition or trait
        if type(model.FamiliarDataModifiers) == "table" then return false end
        return not trait.BlockStacking
      end

      local function removalReady()
        local data = ownerData()
        if type(data) ~= "table" or type(data.TraitNames) ~= "table"
            or type(RemoveTrait) ~= "function" then
          return false
        end
        if data.TraitNames[1] == "LastStandFamiliar"
            and (type(RemoveLastStand) ~= "function" or type(UpdateLifePips) ~= "function") then
          return false
        end
        local unit = type(MapState) == "table" and MapState.FamiliarUnit or nil
        if type(unit) == "table" and unit.ObjectId ~= nil and type(Destroy) ~= "function" then
          return false
        end
        return true
      end

      local function teardownOwner()
        if not removalReady() then error("Familiar owner removal is unavailable") end
        local name = ownerName()
        local data = ownerData()
        local names = {}
        for _, traitName in ipairs(data.TraitNames) do names[#names + 1] = traitName end
        if mountedName("RestedFamiliarResourceBonus") then
          names[#names + 1] = "RestedFamiliarResourceBonus"
        end

        -- Each owner step is attempted at most once. If an engine callback
        -- acknowledges late or throws after mutating, finish the other distinct
        -- cleanup steps so the runtime owner is not left half-mounted, then
        -- surface outcome-unknown through the action ledger. Never retry the
        -- uncertain callback.
        local firstError = nil
        local function attempt(work)
          local ok, message = pcall(work)
          if not ok and firstError == nil then firstError = tostring(message) end
        end

        for _, traitName in ipairs(names) do
          attempt(function() RemoveTrait(CurrentRun.Hero, traitName) end)
        end

        if data.TraitNames[1] == "LastStandFamiliar" then
          attempt(function() RemoveLastStand(CurrentRun.Hero, "LastStandFamiliar") end)
          if finite(CurrentRun.Hero.MaxLastStands) and CurrentRun.Hero.MaxLastStands > 0 then
            CurrentRun.Hero.MaxLastStands = CurrentRun.Hero.MaxLastStands - 1
          end
          attempt(function() UpdateLifePips(CurrentRun.Hero) end)
        end

        local unit = type(MapState) == "table" and MapState.FamiliarUnit or nil
        if type(unit) == "table" and unit.ObjectId ~= nil then
          attempt(function() Destroy({ Id = unit.ObjectId }) end)
        end
        if type(GameState) == "table" and GameState.EquippedFamiliar == name then
          GameState.EquippedFamiliar = nil
        end
        if type(MapState) == "table" and MapState.FamiliarUnit == unit then
          MapState.FamiliarUnit = nil
        end

        for _, traitName in ipairs(names) do
          for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
            if type(trait) == "table" and trait.Name == traitName then
              error("Familiar owner removal left a mounted trait")
            end
          end
        end
        if type(GameState) == "table" and GameState.EquippedFamiliar == name then
          error("Familiar owner removal left the owner equipped")
        end
        if firstError ~= nil then error(firstError) end
      end

      return {
        ownerName = ownerName,
        isMounted = isMounted,
        canLevel = canLevel,
        removalReady = removalReady,
        teardown = teardownOwner,
      }
    end)()

    local temporaryModel = (function()
      local function hasParent(value, parent)
        if type(value) ~= "table" then return false end
        for _, name in ipairs(type(value.InheritFrom) == "table" and value.InheritFrom or {}) do
          if name == parent then return true end
        end
        return false
      end

      local function isWellOwner(trait)
        if type(trait) ~= "table" or type(trait.Name) ~= "string" then return false end
        if hasParent(trait, "ShopTrait") then return true end
        local definition = type(TraitData) == "table" and TraitData[trait.Name] or nil
        return hasParent(definition, "ShopTrait")
      end

      local function counterKind(trait)
        if not isWellOwner(trait) then return nil end
        if finite(trait.RemainingUses) then return "remainingUses" end
        if finite(trait.Uses) then return "uses" end
        return nil
      end

      local function counterValue(trait)
        local kind = counterKind(trait)
        if kind == "remainingUses" then return trait.RemainingUses end
        if kind == "uses" then return trait.Uses end
        return nil
      end

      local function refreshCounter(trait)
        requireFunctions("temporary effect counter editing", { "UpdateTraitNumber" })
        UpdateTraitNumber(trait)
        if type(TraitUIUpdateText) == "function" then TraitUIUpdateText(trait) end
      end

      local function setCounter(trait, value)
        local kind = counterKind(trait)
        if kind == "remainingUses" then
          trait.RemainingUses = value
        elseif kind == "uses" then
          trait.Uses = value
        else
          error("Temporary effect duration editing is unavailable for the selected target")
        end
        refreshCounter(trait)
        if counterValue(trait) ~= value then
          error("Temporary effect duration did not reach the requested remaining uses")
        end
      end

      local function canSetCounter(trait)
        return counterKind(trait) ~= nil and type(UpdateTraitNumber) == "function"
      end

      local function canExpire(trait)
        local value = counterValue(trait)
        if not finite(value) or value <= 0 then return false end
        local kind = counterKind(trait)
        if kind == "remainingUses" then
          return type(RemoveTraitData) == "function"
        end
        return kind == "uses"
          and type(UpdateTraitNumber) == "function"
          and type(RemoveTraitData) == "function"
      end

      local function instanceStillMounted(trait)
        if type(trait) ~= "table" or trait.Id == nil then return false end
        for _, mounted in ipairs(CurrentRun.Hero.Traits or {}) do
          if type(mounted) == "table" and mounted.Id ~= nil
              and tostring(mounted.Id) == tostring(trait.Id) then
            return true
          end
        end
        return false
      end

      local function expire(trait)
        local kind = counterKind(trait)
        local value = counterValue(trait)
        if not finite(value) or value <= 0 then
          error("Temporary effect expiry is unavailable for the selected target")
        end
        if kind == "remainingUses" then
          requireFunctions("temporary effect expiry", { "RemoveTraitData" })
          trait.RemainingUses = 0
          RemoveTraitData(CurrentRun.Hero, trait, { Silent = true })
          if instanceStillMounted(trait) then
            error("Temporary effect expiry left the selected instance mounted")
          end
          return
        end
        if kind == "uses" then
          trait.Uses = 0
          refreshCounter(trait)
          if trait.Uses ~= 0 then
            error("Temporary effect duration did not reach the requested remaining uses")
          end
          requireFunctions("temporary effect expiry", { "RemoveTraitData" })
          RemoveTraitData(CurrentRun.Hero, trait, { Silent = true })
          if instanceStillMounted(trait) then
            error("Temporary effect expiry left the selected instance mounted")
          end
          return
        end
        error("Temporary effect expiry is unavailable for the selected target")
      end

      local function cancel(trait)
        -- Well ownership is the cancellation authority. Some persistent Well
        -- effects have no duration counter, but still require explicit owner
        -- teardown; duration/expiry controls remain gated separately.
        requireFunctions("temporary effect cancellation", { "RemoveTraitData" })
        RemoveTraitData(CurrentRun.Hero, trait, { Silent = true, SkipExpire = true })
        if instanceStillMounted(trait) then
          error("Temporary effect cancellation left the selected instance mounted")
        end
      end

      return {
        isManaged = isWellOwner,
        value = counterValue,
        canSet = canSetCounter,
        canExpire = canExpire,
        set = setCounter,
        expire = expire,
        cancel = cancel,
      }
    end)()

    local function traitFamily(trait, sellEligible)
      if type(trait) ~= "table" then return "other" end
      local name = trait.Name or ""
      if trait.BiomeStateTrait then return "biomeState" end
      if chaosLifecycleState(trait) ~= "" then return "chaos" end
      local slotted = seleneModel.currentSpell()
      if type(slotted) == "table" and slotted.TraitName == name then return "hex" end
      if #seleneModel.talentNodes(name, true) > 0 then return "hexTalent" end
      if trait.Slot == "Spell" or string.find(name, "Spell", 1, true) ~= nil
          or string.find(name, "Hex", 1, true) ~= nil then return "hex" end
      if hammerModel.isRuntimeAspect(trait) then return "weaponAspect" end
      if hammerModel.isHammerTrait(trait) then return "hammer" end
      if arcanaModel.isMounted(trait) then return "arcana" end
      if keepsakeModel.isMounted(trait) then return "keepsake" end
      if familiarModel.isMounted(trait) then return "familiar" end
      if temporaryModel.isManaged(trait) then return "temporary" end
      -- Arachne's outfit is an actual owner lifecycle. Other game-owned boons
      -- may inherit CostumeTrait only to participate in armor/appearance
      -- mechanics, so inheritance alone must not steal their stronger owner.
      if isArachneCostumeTrait(name) then return "costume" end

      -- TreatAsGodLootByShops makes several field/special NPC rewards sellable,
      -- but that does not make their lifecycle an ordinary Olympian/Hermes one.
      -- Special-NPC source ownership therefore still wins over shop eligibility.
      local source = traitSourceId(trait)
      if type(source) == "string" and source ~= "" then
        if string.find(source, "NPC_", 1, true) == 1
            or nativeSpecialChoiceDefinitions[source] ~= nil then
          return "directSpecial"
        end
      end
      if sellEligible then return "olympianHermes" end
      if type(trait.InheritFrom) == "table" then
        for _, parent in ipairs(trait.InheritFrom) do
          if parent == "CostumeTrait" then return "costume" end
        end
      end
      return "other"
    end

    local function availableRarities(trait)
      local result = setmetatable({}, arrayMeta)
      if type(trait) ~= "table" then return result end
      local definition = type(TraitData) == "table" and TraitData[trait.Name] or nil
      local levels = type(definition) == "table" and definition.RarityLevels or trait.RarityLevels
      if type(levels) ~= "table" and chaosLifecycleState(trait) == "curse" then
        local linkedName = chaosLinkedTraitName(trait)
        local linked = type(TraitData) == "table" and TraitData[linkedName] or nil
        levels = type(linked) == "table" and linked.RarityLevels
          or (type(trait.OnExpire) == "table" and type(trait.OnExpire.TraitData) == "table"
            and trait.OnExpire.TraitData.RarityLevels or nil)
      end
      if type(levels) ~= "table" then return result end
      for _, rarity in ipairs(rarityOrder) do
        if levels[rarity] ~= nil then result[#result + 1] = rarity end
      end
      if hammerModel.isHammerTrait(trait) and levels.Legendary ~= nil then
        result[#result + 1] = "Legendary"
      end
      return result
    end

    local function nativeLevelEligible(trait)
      if type(trait) ~= "table" or type(GetAllUpgradeableGodTraits) ~= "function" then return false end
      local ok, eligible = pcall(GetAllUpgradeableGodTraits, 1)
      return ok and type(eligible) == "table" and eligible[trait.Name] == true
    end

    local function operationCapabilities(trait, family, sellEligible, sameCount)
      local levelCapability, levelReason = "none", "ownerSpecificLifecycle"
      local rarityCapability, rarityReason = "none", "ownerSpecificLifecycle"
      local removalCapability, removalReason = "none", "ownerSpecificLifecycle"
      local hasIdentity = trait.Id ~= nil

      if not hasIdentity then
        levelReason, rarityReason, removalReason = "missingInstanceIdentity", "missingInstanceIdentity", "missingInstanceIdentity"
      else
        if sameCount > 1 then
          levelReason = "multipleMatchingInstances"
        elseif family == "hexTalent" and #seleneModel.talentNodes(trait.Name, false) > 0
            and type(IncreaseTraitLevel) == "function"
            and type(UpdateTalentPointInvestedCache) == "function"
            and (type(TraitData) ~= "table" or type(TraitData[trait.Name]) ~= "table"
              or type(TraitData[trait.Name].AcquireFunctionName) ~= "string"
              or type(CallFunctionName) == "function") then
          levelCapability, levelReason = "increaseOne", ""
        elseif family == "chaos"
            and type(GetProcessedTraitData) == "function"
            and type(RemoveTraitData) == "function"
            and type(AddTraitToHero) == "function" then
          levelCapability, levelReason = "increaseOne", ""
        elseif family == "familiar" and familiarModel.canLevel(trait) then
          levelCapability, levelReason = "increaseOne", ""
        elseif family == "hammer" or family == "weaponAspect" or family == "costume"
            or family == "temporary" then
          levelReason = "notMeaningful"
        elseif family == "familiar" then
          levelReason = "ownerSpecificLifecycle"
        elseif family == "keepsake" or family == "arcana" then
          levelReason = "notMeaningful"
        elseif type(IncreaseTraitLevel) ~= "function" then
          levelReason = "nativePathUnavailable"
        elseif family == "directSpecial" and directSpecialLevelMeaningful(trait) then
          levelCapability, levelReason = "increaseOne", ""
        elseif family == "directSpecial" then
          levelReason = "notMeaningful"
        elseif family == "olympianHermes" and nativeLevelEligible(trait) then
          levelCapability, levelReason = "increaseOne", ""
        else
          levelReason = family == "olympianHermes" and "notMeaningful" or "ownerSpecificLifecycle"
        end

        local rarities = availableRarities(trait)
        if sameCount > 1 then
          rarityReason = "multipleMatchingInstances"
        elseif trait.Rarity == nil or #rarities < 2 then
          rarityReason = "notMeaningful"
        elseif family == "hexTalent" and type(AddRarityToTraits) == "function" then
          rarityCapability, rarityReason = "setExact", ""
        elseif family == "chaos"
            and type(GetProcessedTraitData) == "function"
            and type(RemoveTraitData) == "function"
            and type(AddTraitToHero) == "function" then
          rarityCapability, rarityReason = "setExact", ""
        elseif family == "hammer" and type(AddRarityToTraits) == "function"
            and type(TraitData) == "table" and type(TraitData[trait.Name]) == "table"
            and type(TraitData[trait.Name].RarityLevels) == "table"
            and TraitData[trait.Name].RarityLevels.Legendary ~= nil then
          rarityCapability, rarityReason = "setExact", ""
        elseif family == "weaponAspect" then
          rarityReason = "permanentProgressionOwned"
        elseif family == "costume" or family == "temporary" or family == "familiar" then
          rarityReason = "notMeaningful"
        elseif family == "keepsake" and keepsakeModel.rankReady(trait) then
          rarityCapability, rarityReason = "setExact", ""
        elseif family == "keepsake" then
          rarityReason = "nativePathUnavailable"
        elseif family == "arcana" and arcanaModel.rankReady(trait) then
          rarityCapability, rarityReason = "setExact", ""
        elseif family == "arcana" then
          rarityReason = "ownerSpecificLifecycle"
        elseif type(AddRarityToTraits) ~= "function" then
          rarityReason = "nativePathUnavailable"
        elseif family == "directSpecial" and directSpecialRarityMeaningful(trait) then
          rarityCapability, rarityReason = "setExact", ""
        elseif family == "directSpecial" then
          rarityReason = "notMeaningful"
        elseif family == "olympianHermes" and sellEligible then
          rarityCapability, rarityReason = "setExact", ""
        else
          rarityReason = "ownerSpecificLifecycle"
        end

        local slotted = seleneModel.currentSpell()
        if sameCount > 1 and (family == "hex" or family == "hexTalent" or family == "costume") then
          removalReason = "multipleMatchingInstances"
        elseif family == "hex" and type(slotted) == "table" and slotted.TraitName == trait.Name
            and type(HeroHasTrait) == "function" and type(RemoveTrait) == "function"
            and type(UnequipWeapon) == "function" and type(UpdateTalentPointInvestedCache) == "function" then
          removalCapability, removalReason = "singleInstanceForce", ""
        elseif family == "hexTalent" and #seleneModel.talentNodes(trait.Name, true) > 0
            and type(RemoveTraitData) == "function"
            and type(UpdateTalentPointInvestedCache) == "function" then
          removalCapability, removalReason = "singleInstanceForce", ""
        elseif family == "chaos" and type(RemoveTraitData) == "function" then
          removalCapability, removalReason = "singleInstanceForce", ""
        elseif family == "hammer" and hammerModel.removalReady(trait) then
          removalCapability, removalReason = "singleInstanceForce", ""
        elseif family == "costume" and isArachneCostumeTrait(trait.Name)
            and type(RemoveTraitData) == "function" and type(SetupCostume) == "function" then
          removalCapability, removalReason = "singleInstanceForce", ""
        elseif family == "temporary" and type(RemoveTraitData) == "function" then
          removalCapability, removalReason = "singleInstanceForce", ""
        elseif family == "familiar" and familiarModel.removalReady() then
          removalCapability, removalReason = "singleInstanceForce", ""
        elseif family == "keepsake" and keepsakeModel.removalReady() then
          removalCapability, removalReason = "singleInstanceForce", ""
        elseif family == "arcana" then
          removalReason = "permanentProgressionOwned"
        elseif family == "weaponAspect" then
          removalReason = "permanentProgressionOwned"
        elseif family == "directSpecial" and directSpecialCostumeArmor(trait)
            and type(RemoveTraitData) == "function" and type(SetupCostume) == "function" then
          removalCapability, removalReason = "singleInstanceForce", ""
        elseif family == "directSpecial" and directSpecialRemovalSafe(trait) then
          removalCapability, removalReason = "singleInstanceForce", ""
        elseif family == "directSpecial" then
          removalReason = "ownerSpecificLifecycle"
        elseif family == "olympianHermes" and sellEligible then
          removalCapability, removalReason = "nameLevelAllMatching", ""
        end
      end

      return levelCapability, levelReason, rarityCapability, rarityReason,
        removalCapability, removalReason
    end

    local currentRunTraits = function()
      local result = setmetatable({}, arrayMeta)
      if not ready() or sceneName() ~= "run" or type(CurrentRun) ~= "table"
          or type(CurrentRun.Hero) ~= "table" or type(CurrentRun.Hero.Traits) ~= "table" then
        return result, "noActiveRun"
      end
      local runId = tostring(CurrentRun)
      for index, trait in ipairs(CurrentRun.Hero.Traits) do
        if type(trait) == "table" and type(trait.Name) == "string" and trait.Name ~= "" then
          local sellEligible, sellReason = sellScreenEligible(trait)
          local family = traitFamily(trait, sellEligible)
          local count = sameNameCount(trait.Name)
          local displayId = trait.Name
          if type(GetTraitTooltipTitle) == "function" then
            local titleOk, title = pcall(GetTraitTooltipTitle, trait)
            if titleOk and type(title) == "string" and title ~= "" then displayId = title end
          elseif type(trait.CustomTitle) == "string" and trait.CustomTitle ~= "" then
            displayId = trait.CustomTitle
          end
          local levelCapability, levelReason, rarityCapability, rarityReason,
            removalCapability, removalReason = operationCapabilities(trait, family, sellEligible, count)
          if removalCapability == "none" and removalReason == "ownerSpecificLifecycle"
              and sellReason ~= "" and family == "olympianHermes" then
            removalReason = sellReason
          end
          result[#result + 1] = {
            generationId = M.traitInventoryGeneration,
            runId = runId,
            -- A row without the game-owned Id remains observable but cannot mutate.
            instanceId = trait.Id ~= nil and tostring(trait.Id) or ("missing:" .. tostring(index)),
            name = trait.Name,
            displayId = displayId,
            family = family,
            sourceId = family == "chaos" and "Chaos"
              or ((family == "hex" or family == "hexTalent") and "Selene"
              or (family == "hammer" and "WeaponUpgrade"
              or (family == "familiar" and familiarModel.ownerName()
              or (family == "keepsake" and keepsakeModel.ownerName()
              or (family == "arcana" and arcanaModel.ownerName(trait)
              or (family == "weaponAspect" and "" or traitSourceId(trait))))))),
            owner = family == "chaos" and "Chaos"
              or ((family == "hex" or family == "hexTalent") and "Selene"
              or (family == "hammer" and "WeaponUpgrade"
              or (family == "familiar" and familiarModel.ownerName()
              or (family == "keepsake" and keepsakeModel.ownerName()
              or (family == "arcana" and arcanaModel.ownerName(trait)
              or (family == "weaponAspect" and "WeaponAspect" or traitSourceId(trait))))))),
            level = traitLevel(trait),
            rarity = traitRarity(trait),
            hasRarity = trait.Rarity ~= nil,
            availableRarities = availableRarities(trait),
            sameNameCount = count,
            remainingUses = family == "temporary" and temporaryModel.value(trait)
              or (finite(trait.RemainingUses) and trait.RemainingUses or nil),
            lifecycleState = family == "chaos" and chaosLifecycleState(trait) or "",
            linkedTrait = family == "chaos" and chaosLinkedTraitName(trait) or "",
            canAdvanceLifecycle = family == "chaos" and chaosLifecycleState(trait) == "curse"
              and chaosLinkedTraitName(trait) ~= "" and type(RemoveTraitData) == "function",
            canSetRemainingUses = family == "temporary" and temporaryModel.canSet(trait),
            canExpire = family == "temporary" and temporaryModel.canExpire(trait),
            levelCapability = levelCapability,
            levelReason = levelReason,
            rarityCapability = rarityCapability,
            rarityReason = rarityReason,
            removalCapability = removalCapability,
            removalReason = removalReason,
            removalScopeAllMatching = (removalCapability == "nameLevelAllMatching"),
            deferredIssue = deferredTraitIssues[family],
          }
        end
      end
      return result, nil
    end

    local function resolveTraitTarget(params)
      if not ready() or sceneName() ~= "run" then error("Trait mutation requires an active run room") end
      if params.generationId ~= M.traitInventoryGeneration then
        error("Trait selection belongs to a stale runtime generation")
      end
      if params.runId ~= tostring(CurrentRun) then error("Trait selection belongs to a stale run") end
      if type(params.instanceId) ~= "string" or params.instanceId == ""
          or string.find(params.instanceId, "missing:", 1, true) == 1 then
        error("Trait instance is no longer present")
      end
      local target = nil
      for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
        if type(trait) == "table" and trait.Id ~= nil and tostring(trait.Id) == params.instanceId then
          target = trait
          break
        end
      end
      if target == nil then error("Trait instance is no longer present") end
      local sellEligible = sellScreenEligible(target)
      local family = traitFamily(target, sellEligible)
      local count = sameNameCount(target.Name)
      local expectedRarity = type(params.expectedRarity) == "string" and params.expectedRarity or ""
      local expectedRemainingUses = params.expectedRemainingUses
      local observedRemainingUses = family == "temporary" and temporaryModel.value(target)
        or (finite(target.RemainingUses) and target.RemainingUses or nil)
      if target.Name ~= params.trait or family ~= params.family
          or traitLevel(target) ~= params.expectedLevel or traitRarity(target) ~= expectedRarity
          or count ~= params.expectedSameNameCount
          or (expectedRemainingUses ~= nil and observedRemainingUses ~= expectedRemainingUses) then
        error("Trait target changed since selection")
      end
      return target, family, sellEligible, count
    end

    local function targetHasRarity(rarities, rarity)
      for _, value in ipairs(rarities) do if value == rarity then return true end end
      return false
    end

    local function rebuildChaosTarget(target, targetLevel, targetRarity)
      if chaosLifecycleState(target) == "" then error("Chaos trait editing is unavailable") end
      requireFunctions("Chaos trait editing", { "GetProcessedTraitData", "RemoveTraitData", "AddTraitToHero", "DeepCopyTable" })
      local level = targetLevel or traitLevel(target)
      local rarity = targetRarity or traitRarity(target)
      local rebuilt = GetProcessedTraitData({
        Unit = CurrentRun.Hero, TraitName = target.Name, StackNum = level, Rarity = rarity,
      })
      if type(rebuilt) ~= "table" then error("Chaos trait edit failed") end
      rebuilt.Id = target.Id
      rebuilt.StackNum = level
      rebuilt.Rarity = rarity

      for _, key in ipairs({ "RemainingUses", "Uses", "CurrentRoom", "TraitTitle" }) do
        if target[key] ~= nil then rebuilt[key] = DeepCopyTable(target[key]) end
      end

      if chaosLifecycleState(target) == "curse" then
        local linkedName = chaosLinkedTraitName(target)
        if linkedName == "" then error("Chaos trait editing is unavailable") end
        local queued = GetProcessedTraitData({
          Unit = CurrentRun.Hero, TraitName = linkedName, StackNum = level, Rarity = rarity,
        })
        if type(queued) ~= "table" then error("Chaos trait edit failed") end
        queued.StackNum = level
        queued.Rarity = rarity
        rebuilt.OnExpire = type(target.OnExpire) == "table" and DeepCopyTable(target.OnExpire) or {}
        rebuilt.OnExpire.TraitData = queued
        rebuilt.TraitTitle = target.TraitTitle or rebuilt.TraitTitle
          or ("ChaosCombo_" .. target.Name .. "_" .. linkedName)
      end

      RemoveTraitData(CurrentRun.Hero, target, {
        Silent = true, SkipExpire = true, SkipActivatedTraitUpdate = true,
      })
      local added = AddTraitToHero({
        TraitData = rebuilt,
        SkipNewTraitHighlight = true,
        SkipActivatedTraitUpdate = true,
        SkipSetup = true,
        SkipQuestStatusCheck = true,
      })
      if type(added) ~= "table" or tostring(added.Id) ~= tostring(target.Id) then
        error("Chaos trait edit failed")
      end
      return added
    end

    local function mutate(command, params)
      if command == "set_trait_level" or command == "set_trait_rarity"
        or command == "set_trait_remaining_uses" or command == "expire_trait"
        or command == "remove_trait" or command == "advance_trait_lifecycle" then
      return traitManagement.mutate(command, params)
    end
    if command == "open_sell_traits" then
      if not ready() or sceneName() ~= "run" then error("Boon selling requires an active run room") end
      requireFunctions("native boon sell screen", {
        "OpenSellTraitMenu", "AreScreensActive", "thread", "DeepCopyTable",
        "AltAspectRatioFramesHide", "OnScreenCloseStarted", "SetAnimation", "UseableOff",
        "CloseScreen", "GetAllIds", "OnScreenCloseFinished", "ShowCombatUI", "SetPlayerVulnerable",
      })
      if type(ScreenData) ~= "table" or type(ScreenData.SellTraits) ~= "table" then
        error("Native boon sell screen data is unavailable")
      end
      if AreScreensActive() then error("Cannot open boon sell screen while another screen is active") end
      return actionLedger.run(command, params, function(record)
        local function runSell()
          local originalScreen = ScreenData.SellTraits
          local trainerScreen = nil
          local ok, message = pcall(function()
            trainerScreen = DeepCopyTable(ScreenData.SellTraits)
            local closeButton = trainerScreen.ComponentData
              and trainerScreen.ComponentData.ActionBar
              and trainerScreen.ComponentData.ActionBar.Children
              and trainerScreen.ComponentData.ActionBar.Children.CloseButton
            if type(closeButton) ~= "table" or type(closeButton.Data) ~= "table" then
              error("Native boon sell screen missing close button data")
            end
            closeButton.Data.OnPressedFunctionName = "MacGamingTrainerCloseSellTraitScreen"
            ScreenData.SellTraits = trainerScreen
            local menuArgs = {}
            OpenSellTraitMenu(menuArgs)
          end)
          if trainerScreen ~= nil and ScreenData.SellTraits == trainerScreen then ScreenData.SellTraits = originalScreen end
          if ok then
            record.status = "opened"
            record.error = nil
          else
            record.status = "failed"
            record.error = tostring(message)
            if type(DebugPrint) == "function" then
              DebugPrint({ Text = "MacGamingTrainer native sell screen failed: " .. record.error })
            end
          end
          actionLedger.publish(record)
        end
        thread(runSell)
        return nil, "accepted"
      end)
    end
    if command == "open_special_choice" then
      if not ready() or sceneName() ~= "run" then error("Special blessing choice requires an active run room") end
      if type(ScreenState) == "table" and ScreenState.InTransition then error("Cannot open special blessing choice during a transition") end
      requireFunctions("native special blessing choice", {
        "AreScreensActive", "OpenUpgradeChoiceMenu", "ShallowCopyTable", "DeepCopyTable",
        "IsGameStateEligible", "RemoveRandomValue", "RandomSynchronize", "thread",
      })
      if AreScreensActive() then error("Cannot open special blessing choice while another screen is active") end
      local definition = nativeSpecialChoiceDefinitions[params.source]
      if type(definition) ~= "table" then error("Special blessing source has no audited native choice flow") end
      if type(EnemyData) ~= "table" or type(PresetEventArgs) ~= "table" or type(TraitData) ~= "table" then
        error("Special blessing source data is unavailable")
      end
      local npcData = EnemyData[definition.npc]
      if type(npcData) ~= "table" then error("Special blessing source data is unavailable") end
      local choiceData = definition.choices ~= nil and PresetEventArgs[definition.choices] or nil
      if definition.mode ~= "loot"
          and (type(choiceData) ~= "table" or type(choiceData.UpgradeOptions) ~= "table") then
        error("Special blessing choice data is unavailable")
      end
      if definition.mode == "loot" then
        requireFunctions("native special blessing loot choice", { "SetTraitsOnLoot" })
      else
        requireFunctions("native special blessing fixed choice", { "PassRarityCheck", "HeroHasTrait" })
      end
      if definition.post == "costume" then
        requireFunctions("Arachne costume application", { "SetupCostume" })
      end
      if definition.circe then
        requireFunctions("Circe familiar choice", { "GetProcessedTraitData", "SetTraitTextData" })
      end

      return actionLedger.run(command, params, function(record)
        local source = DeepCopyTable(npcData)
        local syntheticName = "MacGamingTrainerSpecial_" .. params.source
        source.ObjectId = -1
        source.CanDuplicate = false
        source.DestroyOnPickup = false
        source.LastRewardEligible = false
        source.BanUnpickedBoonsEligible = false
        source.UpgradeScreenOpenFunctionName = nil
        source.UpgradeMenuOpenVoiceLines = nil
        source.UseNarrativeContextArt = false
        source.LightingColor = source.LightingColor or source.LootColor or { 255, 255, 255, 255 }
        source.LootColor = source.LootColor or source.LightingColor
        source.BoonGetColor = source.BoonGetColor or source.LootColor

        local args = {}
        if M.specialChoiceRun ~= CurrentRun then
          M.specialChoiceRun = CurrentRun
          M.specialChoiceOpens = {}
        end
        M.specialChoiceOpens[params.source] = (M.specialChoiceOpens[params.source] or 0) + 1
        RandomSynchronize(8 + M.specialChoiceOpens[params.source])
        if definition.mode == "loot" then
          source.UpgradeOptions = nil
          SetTraitsOnLoot(source)
          if type(source.UpgradeOptions) ~= "table" or #source.UpgradeOptions == 0 then
            error("No eligible special blessings are available")
          end
        else
          source.BlockReroll = true
          args = ShallowCopyTable(choiceData)
          args.PortraitShift = nil

          local preview
          source.UpgradeOptions, preview = choiceReroll.fixedPlan(source, definition)
          if preview ~= nil then
            SessionMapState.OldFamiliarTrait, SessionMapState.NewFamiliarTrait, SessionMapState.StatLine = preview.old, preview.new, preview.statLine
          end
        end

        source.Name = syntheticName
        if type(GameState.LootPickups) ~= "table" then
          error("Special blessing choice requires loot pickup state")
        end
        local lootPickups = GameState.LootPickups
        local previousPickup = lootPickups[source.Name]
        local hadLootChoiceHistory = type(CurrentRun.LootChoiceHistory) == "table"
        local history = hadLootChoiceHistory and CurrentRun.LootChoiceHistory or nil
        local historyCount = history and #history or 0
        local ownerRun = CurrentRun

        local function runChoice()
          local previousLastReward = ownerRun.LastReward
          local injectedLastReward = definition.echoLastReward and previousLastReward == nil
          if injectedLastReward then
            ownerRun.LastReward = { Type = "Consumable", Name = "MaxHealthDrop", DisplayName = "MaxHealthDrop" }
          end
          local ok, message = pcall(OpenUpgradeChoiceMenu, source, args)
          if ok and definition.post == "costume" then pcall(SetupCostume) end
          local cleanupOk, cleanupMessage = pcall(function()
            if injectedLastReward then ownerRun.LastReward = previousLastReward end
            lootPickups[source.Name] = previousPickup
            if hadLootChoiceHistory then
              while #history > historyCount do table.remove(history) end
            elseif ownerRun == CurrentRun and type(CurrentRun.LootChoiceHistory) == "table" then
              CurrentRun.LootChoiceHistory = nil
            end
          end)
          if not cleanupOk then ok, message = false, cleanupMessage end
          if ok then
            record.status = "opened"
            record.error = nil
          else
            record.status = "failed"
            record.error = tostring(message)
            if type(DebugPrint) == "function" then
              DebugPrint({ Text = "MacGamingTrainer native special choice failed: " .. record.error })
            end
          end
          actionLedger.publish(record)
        end
        thread(runChoice)
        return nil, "accepted"
      end)
    end
    if command == "acquire_chaos_pair" then
      local pairSource = nil
      local function containsName(list, wanted)
        if type(list) ~= "table" then return false end
        for _, value in pairs(list) do
          local name = type(value) == "table" and (value.ItemName or value.TraitName or value.Name) or value
          if name == wanted then return true end
        end
        return false
      end
      return actionLedger.run(command, params, function()
        local source = pairSource
        if type(source) ~= "table" then error("Chaos exact acquisition is unavailable") end
        SetTraitsOnLoot(source)
        local option = nil
        for _, candidate in pairs(source.UpgradeOptions or {}) do
          if type(candidate) == "table"
              and candidate.ItemName == params.blessing
              and candidate.SecondaryItemName == params.curse then
            option = candidate
            break
          end
        end
        if type(option) ~= "table" then error("Chaos exact acquisition is unavailable") end
        local rarity = option.Rarity or "Common"
        local blessing = GetProcessedTraitData({
          Unit = CurrentRun.Hero, TraitName = params.blessing, Rarity = rarity,
        })
        local curse = GetProcessedTraitData({
          Unit = CurrentRun.Hero, TraitName = params.curse, Rarity = rarity,
        })
        if type(blessing) ~= "table" or type(curse) ~= "table" then
          error("Chaos exact acquisition failed")
        end
        curse.OnExpire = curse.OnExpire or {}
        curse.OnExpire.TraitData = blessing
        curse.TraitTitle = "ChaosCombo_" .. curse.Name .. "_" .. blessing.Name
        local added = AddTraitToHero({
          TraitData = curse,
          PreProcessedForDisplay = true,
          FromLoot = true,
        })
        if type(added) ~= "table" then error("Chaos exact acquisition failed") end
        if type(CurrentRun.PickedTraits) == "table" then CurrentRun.PickedTraits[curse.Name] = true end
        if type(SessionMapState) == "table" then SessionMapState.LastUpgradeChoice = curse.Name end
        return nil
      end, function()
        if not ready() or sceneName() ~= "run" then error("Chaos exact acquisition is unavailable") end
        if type(ScreenState) == "table" and ScreenState.InTransition then
          error("Chaos exact acquisition is unavailable")
        end
        if type(params.blessing) ~= "string" or params.blessing == ""
            or type(params.curse) ~= "string" or params.curse == "" then
          error("Chaos exact acquisition is unavailable")
        end
        requireFunctions("exact Chaos pair acquisition", {
          "DeepCopyTable", "GetEligibleTransformingTrait", "SetTraitsOnLoot",
          "GetProcessedTraitData", "AddTraitToHero",
        })
        local source = type(LootData) == "table" and LootData.TrialUpgrade or nil
        if type(source) ~= "table" or not source.TransformingTraits
            or type(TraitData) ~= "table"
            or type(TraitData[params.blessing]) ~= "table"
            or type(TraitData[params.curse]) ~= "table"
            or not containsName(source.PermanentTraits, params.blessing)
            or not containsName(source.TemporaryTraits, params.curse) then
          error("Chaos exact acquisition is unavailable")
        end
        local eligibleBlessings = GetEligibleTransformingTrait({ params.blessing })
        local eligibleCurses = GetEligibleTransformingTrait({ params.curse })
        if not containsName(eligibleBlessings, params.blessing)
            or not containsName(eligibleCurses, params.curse) then
          error("Chaos exact acquisition is unavailable")
        end
        pairSource = DeepCopyTable(source)
        pairSource.PermanentTraits = { params.blessing }
        pairSource.TemporaryTraits = { params.curse }
        pairSource.UpgradeOptions = nil
        pairSource.Rarity = nil
      end)
    end
    if command == "spawn_reward" then
      if not ready() or sceneName() ~= "run" then error("Reward spawning requires an active run room") end
      local _, allowed = rewards()
      local rewardId = params.reward
      local entry = type(rewardId) == "string" and allowed[rewardId] or nil
      if not entry then entry = echoModel.hiddenEntry(rewardId) end
      if not entry then error("Unknown or unsupported reward") end
      if type(ScreenState) == "table" and ScreenState.InTransition then error("Cannot spawn a reward during a transition") end

      local exactPlan = nil
      local function listContains(list, wanted)
        if type(list) ~= "table" then return false end
        for _, value in pairs(list) do
          local name = type(value) == "table" and (value.ItemName or value.TraitName or value.Name) or value
          if name == wanted then return true end
        end
        return false
      end
      local function singleTargetList(list, wanted)
        return listContains(list, wanted) and { wanted } or {}
      end
      local function findTargetOption(options, wanted)
        if type(options) ~= "table" then return nil end
        for _, option in pairs(options) do
          if type(option) == "table" and option.ItemName == wanted then return option end
        end
        return nil
      end
      local function prepareExactReward()
        if entry.kind ~= "trait" or entry.group ~= "exact" then return end
        if type(entry.trait) ~= "string" or type(TraitData) ~= "table" or type(TraitData[entry.trait]) ~= "table" then
          error("Exact boon target is unavailable")
        end
        requireFunctions("exact boon ownership", { "HeroHasTrait" })
        if entry.acquisitionMode ~= "seleneTalent" and HeroHasTrait(entry.trait) then
          error("Selected boon is already owned")
        end

        if entry.acquisitionMode == "chaosBlessing" or entry.acquisitionMode == "chaosCurse" then
          requireFunctions("exact Chaos acquisition", {
            "DeepCopyTable", "GetEligibleTransformingTrait", "SetTraitsOnLoot",
            "GetProcessedTraitData", "AddTraitToHero",
          })
          local source = type(LootData) == "table" and LootData.TrialUpgrade or nil
          if type(source) ~= "table" or not source.TransformingTraits then
            error("Chaos exact acquisition is unavailable")
          end
          local selectedPool = entry.acquisitionMode == "chaosBlessing"
            and source.PermanentTraits or source.TemporaryTraits
          if not listContains(selectedPool, entry.trait) then
            error("Chaos exact acquisition is unavailable")
          end
          local eligibleSelected = GetEligibleTransformingTrait({ entry.trait })
          if not listContains(eligibleSelected, entry.trait) then
            error("Chaos exact acquisition is unavailable")
          end
          local counterpartPool = entry.acquisitionMode == "chaosBlessing"
            and source.TemporaryTraits or source.PermanentTraits
          local eligibleCounterparts = GetEligibleTransformingTrait(counterpartPool)
          if type(eligibleCounterparts) ~= "table" or next(eligibleCounterparts) == nil then
            error("Chaos exact acquisition is unavailable")
          end
          source = DeepCopyTable(source)
          if entry.acquisitionMode == "chaosBlessing" then
            source.PermanentTraits = { entry.trait }
          else
            source.TemporaryTraits = { entry.trait }
          end
          source.UpgradeOptions = nil
          source.Rarity = nil
          exactPlan = { mode = entry.acquisitionMode, source = source }
          return
        end
        if entry.acquisitionMode == "seleneSpell" then
          local spellData = type(SpellData) == "table" and SpellData[entry.spellName] or nil
          if type(spellData) ~= "table" or spellData.TraitName ~= entry.trait
              or spellData.Skip
              or (type(spellData.GameStateRequirements) == "table"
                and spellData.GameStateRequirements.Skip) then
            error("Selene spell target is unavailable")
          end
          local spellRequirements = {
            "DeepCopyTable", "CreateTalentTree", "AddTraitToHero", "RemoveTrait",
            "UnequipWeapon", "UpdateTalentPointInvestedCache", "thread",
          }
          if spellData.CheckSpellReadyOnAcquire then
            spellRequirements[#spellRequirements + 1] = "CallFunctionName"
          else
            spellRequirements[#spellRequirements + 1] = "SpellReadyPresentation"
          end
          requireFunctions("exact Selene spell acquisition", spellRequirements)
          exactPlan = { mode = "seleneSpell", spellName = entry.spellName }
          return
        end
        if entry.acquisitionMode == "hammerNative" then
          requireFunctions("exact Hammer acquisition", {
            "GetEligibleUpgrades", "GetProcessedTraitData", "AddTraitToHero",
          })
          local source = type(LootData) == "table" and LootData.WeaponUpgrade or nil
          if type(source) ~= "table" then error("Selected boon is not currently eligible") end
          local eligible = GetEligibleUpgrades({}, source, source)
          if findTargetOption(eligible, entry.trait) == nil then
            error("Selected boon is not currently eligible")
          end
          exactPlan = { mode = "hammerNative" }
          return
        end
        if entry.acquisitionMode == "seleneTalent" then
          local slotted = seleneModel.currentSpell()
          if type(slotted) ~= "table" or slotted.Name ~= entry.spellName
              or #seleneModel.talentNodes(entry.trait, false) == 0 then
            error("Selene talent is unavailable for the current Path of Stars")
          end
          local talentRequirements = {
            "HeroHasTrait", "GetHeroTrait", "AddTraitToHero", "IncreaseTraitLevel",
            "UpdateTalentPointInvestedCache",
          }
          local base = type(TraitData) == "table" and TraitData[entry.trait] or nil
          if HeroHasTrait(entry.trait) and type(base) == "table"
              and type(base.AcquireFunctionName) == "string" then
            talentRequirements[#talentRequirements + 1] = "CallFunctionName"
          end
          requireFunctions("exact Selene talent acquisition", talentRequirements)
          exactPlan = { mode = "seleneTalent", spellName = entry.spellName }
          return
        end
        if entry.acquisitionMode == "echoLastRunExact" then
          requireFunctions("Echo previous-run exact eligibility", {
            "HeroHasTrait", "GetHeroTrait", "IsGodTrait", "IsTraitEligible", "HeroSlotFilled",
            "GetProcessedTraitData", "AddTraitToHero", "GetLootSourceName",
          })
          local eligible, rarity = echoModel.eligibleRarity(entry.trait)
          if not eligible then error("Echo previous-run boon is no longer eligible") end
          exactPlan = { mode = "echoLastRunExact", rarity = rarity }
          return
        end
        if entry.acquisitionMode == "direct" or entry.acquisitionMode == "costume" then
          requireFunctions("exact special boon acquisition", { "AddTraitToHero" })
          if entry.acquisitionMode == "costume" then
            if entry.sourceId ~= "Arachne" or not traitManagement.isArachneCostumeChoice(entry.trait) then
              error("Exact costume target is unavailable")
            end
            requireFunctions("exact costume acquisition", { "SetupCostume" })
          end
          exactPlan = { mode = entry.acquisitionMode }
          return
        end
        if entry.acquisitionMode ~= "ordinaryNative" then
          error("Exact boon acquisition strategy is unavailable")
        end

        requireFunctions("exact Olympian boon acquisition", {
          "DeepCopyTable", "GetReplacementTraits", "GetEligibleUpgrades",
          "GetProcessedTraitData", "GetTraitCount", "GetTotalHeroTraitValue",
          "RemoveWeaponTrait", "AddTraitToHero", "SetTraitsOnLoot",
        })
        local source = type(LootData) == "table" and LootData[entry.sourceId] or nil
        if type(source) ~= "table" then error("Exact boon source is unavailable") end
        source = DeepCopyTable(source)
        source.PriorityUpgrades = singleTargetList(source.PriorityUpgrades, entry.trait)
        source.WeaponUpgrades = singleTargetList(source.WeaponUpgrades, entry.trait)
        source.Traits = singleTargetList(source.Traits, entry.trait)
        source.UpgradeOptions = nil
        source.Rarity = nil

        local replacement = findTargetOption(GetReplacementTraits({ entry.trait }), entry.trait)
        if replacement and replacement.TraitToReplace then
          exactPlan = { mode = "ordinaryReplacement", source = source, option = replacement }
          return
        end

        local eligible = GetEligibleUpgrades({}, source, source)
        if findTargetOption(eligible, entry.trait) == nil then
          error("Selected boon is not currently eligible")
        end
        exactPlan = { mode = "ordinaryNative", source = source }
      end
      local function addChaosExact()
        local source = exactPlan.source
        SetTraitsOnLoot(source)
        local option = nil
        for _, candidate in pairs(source.UpgradeOptions or {}) do
          if type(candidate) == "table" then
            if exactPlan.mode == "chaosBlessing" and candidate.ItemName == entry.trait then
              option = candidate
              break
            elseif exactPlan.mode == "chaosCurse" and candidate.SecondaryItemName == entry.trait then
              option = candidate
              break
            end
          end
        end
        if type(option) ~= "table" then
          error("Chaos exact acquisition is unavailable")
        end
        if type(option.ItemName) ~= "string" or type(option.SecondaryItemName) ~= "string" then
          error("Chaos exact acquisition failed")
        end
        local rarity = option.Rarity or "Common"
        local blessing = GetProcessedTraitData({
          Unit = CurrentRun.Hero, TraitName = option.ItemName, Rarity = rarity,
        })
        local curse = GetProcessedTraitData({
          Unit = CurrentRun.Hero, TraitName = option.SecondaryItemName, Rarity = rarity,
        })
        if type(blessing) ~= "table" or type(curse) ~= "table" then
          error("Chaos exact acquisition failed")
        end
        curse.OnExpire = curse.OnExpire or {}
        curse.OnExpire.TraitData = blessing
        curse.TraitTitle = "ChaosCombo_" .. curse.Name .. "_" .. blessing.Name
        local added = AddTraitToHero({
          TraitData = curse,
          PreProcessedForDisplay = true,
          FromLoot = true,
        })
        if type(added) ~= "table" then error("Chaos exact acquisition failed") end
        if type(CurrentRun.PickedTraits) == "table" then CurrentRun.PickedTraits[curse.Name] = true end
        if type(SessionMapState) == "table" then SessionMapState.LastUpgradeChoice = curse.Name end
        return nil
      end

      local function addOrdinaryExact()
        local source = exactPlan.source
        local option
        if exactPlan.mode == "ordinaryReplacement" then
          option = exactPlan.option
        else
          SetTraitsOnLoot(source)
          option = findTargetOption(source.UpgradeOptions, entry.trait)
          if option == nil then error("Selected boon became unavailable before acquisition") end
        end

        local rarity = option.Rarity or "Common"
        local stackNum = nil
        if option.TraitToReplace then
          local existingNum = GetTraitCount(CurrentRun.Hero, { Name = option.TraitToReplace })
          stackNum = existingNum + GetTotalHeroTraitValue("ExchangeLevelBonus")
        end
        local processed = GetProcessedTraitData({
          Unit = CurrentRun.Hero, TraitName = entry.trait, Rarity = rarity, StackNum = stackNum,
        })
        if type(processed) ~= "table" then error("Exact boon processing failed") end
        if option.TraitToReplace then
          processed.TraitToReplace = option.TraitToReplace
          processed.OldRarity = option.OldRarity
          RemoveWeaponTrait(option.TraitToReplace)
        end
        local added = AddTraitToHero({
          TraitData = processed,
          PreProcessedForDisplay = option.TraitToReplace == nil,
          FromLoot = true,
        })
        if type(added) ~= "table" then error("Exact boon acquisition did not return a trait") end
        if type(CurrentRun.PickedTraits) == "table" then CurrentRun.PickedTraits[entry.trait] = true end
        if type(SessionMapState) == "table" then SessionMapState.LastUpgradeChoice = entry.trait end
        if type(CheckNewTraitManaReserveShrineUpgrade) == "function" then
          CheckNewTraitManaReserveShrineUpgrade(added, { IsGodLoot = true })
        end
        if type(CheckAndAddOlympianDuo) == "function" then CheckAndAddOlympianDuo(source) end
        return nil
      end

      return actionLedger.run(command, params, function()
        if entry.spawnMode == "weapon_loot" then
          requireFunctions("shop hammer spawning", { "CreateWeaponLoot" })
          local loot = CreateWeaponLoot({
            SpawnPoint = CurrentRun.Hero.ObjectId, OffsetX = 100,
            DoesNotBlockExit = true, SuppressSpawnSounds = true,
          })
          if type(loot) ~= "table" or not finite(loot.ObjectId) then error("Daedalus Hammer shop spawn did not return an object ID") end
          return loot.ObjectId
        end
        if entry.spawnMode == "hermes_loot" then
          requireFunctions("shop Hermes spawning", { "CreateHermesLoot" })
          local loot = CreateHermesLoot({
            SpawnPoint = CurrentRun.Hero.ObjectId, OffsetX = 100,
            DoesNotBlockExit = true, SuppressSpawnSounds = true, BoughtFromShop = true,
          })
          if type(loot) ~= "table" or not finite(loot.ObjectId) then error("Hermes shop spawn did not return an object ID") end
          loot.CanReceiveGift = false
          return loot.ObjectId
        end
        if entry.spawnMode == "random_loot" or entry.spawnMode == "boosted_random_loot" then
          requireFunctions("random shop boon spawning", { "GetEligibleInteractedGod", "GiveLoot" })
          local forceLootName = GetEligibleInteractedGod()
          if type(forceLootName) ~= "string" or forceLootName == "" then error("No eligible Olympian boon is available") end
          local lootArgs = {
            ForceLootName = forceLootName, SpawnPoint = CurrentRun.Hero.ObjectId, OffsetX = 100,
            BoughtFromShop = true, DoesNotBlockExit = true, AutoLoadPackages = true,
          }
          if entry.spawnMode == "boosted_random_loot" then
            lootArgs.AddBoostedAnimation = true
            lootArgs.BoonRaritiesOverride = { Legendary = 0.1, Epic = 0.25, Rare = 0.90 }
          end
          local loot = GiveLoot(lootArgs)
          if type(loot) ~= "table" or not finite(loot.ObjectId) then error("Random shop boon spawn did not return an object ID") end
          loot.CanReceiveGift = false
          if lootArgs.BoonRaritiesOverride ~= nil then loot.BoonRaritiesOverride = lootArgs.BoonRaritiesOverride end
          return loot.ObjectId
        end
        if entry.kind == "trait" then
          if type(TraitData) ~= "table" or type(TraitData[entry.trait]) ~= "table" then error("Trait reward is unavailable") end
          if exactPlan and (exactPlan.mode == "chaosBlessing" or exactPlan.mode == "chaosCurse") then
            return addChaosExact()
          end
          if exactPlan and exactPlan.mode == "seleneSpell" then
            seleneModel.applySpell(exactPlan.spellName)
            return nil
          end
          if exactPlan and exactPlan.mode == "seleneTalent" then
            seleneModel.applyTalent(entry.trait)
            return nil
          end
          if exactPlan and exactPlan.mode == "hammerNative" then
            hammerModel.applyExact(entry.trait)
            return nil
          end
          if exactPlan and exactPlan.mode == "echoLastRunExact" then
            echoModel.applyExact(entry.trait, exactPlan.rarity)
            return nil
          end
          if exactPlan and exactPlan.mode == "costume" then
            traitManagement.applyCostume(entry.trait)
            return nil
          end
          if exactPlan and (exactPlan.mode == "ordinaryNative" or exactPlan.mode == "ordinaryReplacement") then
            return addOrdinaryExact()
          end
          if entry.storeTrait then
            requireFunctions("store trait spawning", { "GetProcessedTraitData", "AddTraitToHero" })
            local traitData = GetProcessedTraitData({ Unit = CurrentRun.Hero, TraitName = entry.trait })
            if type(traitData) ~= "table" then error("Store trait processing failed") end
            if type(RecalculateStoreTraitDurations) == "function" then RecalculateStoreTraitDurations(traitData) end
            local extension = nil
            if type(HeroHasTrait) == "function" and HeroHasTrait("ExtendedShopTrait") then
              requireFunctions("extended store trait eligibility", { "GetHeroTrait", "IsTraitActive" })
              extension = GetHeroTrait("ExtendedShopTrait")
              if type(extension) == "table"
                  and type(extension.ValidPermanentItemsLookup) == "table"
                  and extension.ValidPermanentItemsLookup[entry.trait]
                  and IsTraitActive(extension) then
                traitData.MakePermanent = true
              end
            end
            if traitData.MakePermanent and type(extension) == "table" and finite(extension.BossExtension) then
              requireFunctions("extended store trait", { "UseHeroTraitsWithValue" })
              traitData.UsesAsEncounters = false
              traitData.UsesAsRooms = false
              traitData.UsesAsBosses = true
              traitData.RemainingUses = extension.BossExtension
              traitData.StatLines = { "ExtendedStoreUsesRemainingDisplay1" }
              if traitData.CustomStatLinesWithShrineUpgrade ~= nil then
                requireFunctions("extended store trait shrine display", { "GetNumShrineUpgrades" })
                if GetNumShrineUpgrades(traitData.CustomStatLinesWithShrineUpgrade.ShrineUpgradeName) > 0 then
                  traitData.CustomStatLinesWithShrineUpgrade.StatLines[1] = "ExtendedStoreUsesRemainingDisplay1"
                end
              end
              UseHeroTraitsWithValue("BossExtension", true)
            end
            if traitData.IncreaseUsesOnStack and type(HeroHasTrait) == "function" and HeroHasTrait(entry.trait) then
              requireFunctions("store trait stacking", { "GetHeroTrait", "UpdateTraitNumber" })
              local currentTrait = GetHeroTrait(entry.trait)
              if type(currentTrait) ~= "table" then error("Existing store trait is unavailable") end
              currentTrait.RemainingUses = number(currentTrait.RemainingUses) + number(traitData.RemainingUses)
              UpdateTraitNumber(currentTrait)
            else
              AddTraitToHero({ TraitData = traitData, SkipQuestStatusCheck = true, SkipAddToHUD = true })
            end
            if traitData.StoreCostMultiplier
                and type(CurrentRun.CurrentRoom) == "table"
                and type(CurrentRun.CurrentRoom.Store) == "table"
                and type(CurrentRun.CurrentRoom.Store.StoreOptions) == "table" then
              requireFunctions("store cost refresh", { "ShallowCopyTable" })
              for _, currentUpgradeData in pairs(CurrentRun.CurrentRoom.Store.StoreOptions) do
                if type(currentUpgradeData) == "table" then
                  currentUpgradeData.Processed = nil
                  currentUpgradeData.DataOverrides = ShallowCopyTable(currentUpgradeData)
                  currentUpgradeData.DataOverrides.ResourceCosts = nil
                end
              end
            end
          else
            requireFunctions("special blessing", { "AddTraitToHero" })
            AddTraitToHero({ TraitName = entry.trait, FromLoot = true })
            if entry.sourceId == "Arachne" then
              requireFunctions("Arachne costume spawning", { "SetupCostume" })
              SetupCostume()
            end
          end
          return nil
        end
        if entry.kind == "consumable" then
          requireFunctions("consumable spawning", { "SpawnObstacle", "CreateConsumableItem" })
          local objectId = SpawnObstacle({ Name = rewardId, DestinationId = CurrentRun.Hero.ObjectId, Group = "Standing", OffsetX = 100 })
          if not finite(objectId) then error("Consumable spawn did not return an object ID") end
          local item = CreateConsumableItem(objectId, rewardId, 0, {
            IgnoreSounds = true, RunProgressUpgradeEligible = true, AutoLoadPackages = true, IgnoreAssert = true,
          })
          if item == nil then error("Consumable initialization failed") end
          if type(item) == "table" then
            item.DoesNotBlockExit = true
            item.IgnorePurchase = true
            item.PurchaseRequirements = nil
          end
          return objectId
        end
        if rewardId == "SpellDrop" then
          -- SpellDrop is itself a native room-reward type. SpawnRoomReward's
          -- generic reward branch creates it through CreateConsumableItem,
          -- which intentionally accepts LootData entries, runs SetupEvents
          -- (PregenerateSpells), and preserves OpenSpellScreen/gift behavior.
          -- Do not coerce it into a generic Boon/GiveLoot object.
          requireFunctions("Selene room reward spawning", { "SpawnRoomReward" })
          local loot = SpawnRoomReward(CurrentRun.CurrentRoom, {
            RewardOverride = "SpellDrop",
            SpawnRewardOnId = CurrentRun.Hero.ObjectId, AutoLoadPackages = true,
          })
          if type(loot) ~= "table" or not finite(loot.ObjectId) then error("Selene loot spawn did not return an object ID") end
          return loot.ObjectId
        end
        requireFunctions("loot spawning", { "CreateLoot" })
        if type(MapState) ~= "table" or type(MapState.RoomRequiredObjects) ~= "table"
            or type(LootObjects) ~= "table" then error("Unsupported loot spawning: scene loot tables unavailable") end
        local lootData = LootData[rewardId]
        local packages, packageSeen = {}, {}
        local function addPackage(value)
          if type(value) == "string" and value ~= "" then
            if not packageSeen[value] then packageSeen[value] = true; packages[#packages + 1] = value end
          elseif type(value) == "table" then
            if type(value.Name) == "string" then addPackage(value.Name) end
            if type(value.Names) == "table" then addPackage(value.Names) end
            for key, item in pairs(value) do
              if key ~= "Name" and key ~= "Names" then
                if type(item) == "string" or type(item) == "table" then addPackage(item) end
              end
            end
          end
        end
        addPackage(lootData.RequiredPackage)
        addPackage(lootData.RequiredPackages)
        if type(GameData) == "table" and type(GameData.MissingPackages) == "table" then
          addPackage(GameData.MissingPackages[rewardId])
        end
        if #packages > 0 then
          requireFunctions("loot package loading", { "LoadPackages" })
          local ok, message = pcall(LoadPackages, { Names = packages })
          if not ok then error("Loot package loading failed: " .. tostring(message)) end
        end
        local setup = lootData.SetupEvents
        if setup ~= nil then
          if type(setup) ~= "table" then error("Unsupported loot setup events") end
          for _, event in ipairs(setup) do
            local fn = event.FunctionName
            if fn ~= "SilenceForDreamRun" and fn ~= "PregenerateSpells" then
              error("Unsupported loot setup event: " .. tostring(fn))
            end
            requireFunctions("loot setup", { fn })
            if event.Args and (event.Args.BlockInteract or event.Args.ForceTextLines) then
              error("Unsupported loot setup arguments")
            end
          end
        end
        local loot = CreateLoot({ Name = rewardId, SpawnPoint = CurrentRun.Hero.ObjectId,
          OffsetX = 100, AutoLoadPackages = true, DoesNotBlockExit = true })
        if type(loot) ~= "table" or not finite(loot.ObjectId) then error("Loot spawn did not return an object ID") end
        return loot.ObjectId
      end, prepareExactReward)
    end
    error("Unknown command")
  end

  local preferenceReplayCommands = {
    set_feature = true,
    set_boon_rarity = true,
    set_gathering_probabilities = true,
    set_chaos_gate_probability = true,
    set_stat = true,
    set_vital = true,
    lock_vital = true,
    set_resource = true,
    lock_resource = true,
    set_rerolls = true,
    lock_rerolls = true,
    set_element = true,
    lock_element = true,
    set_next_room_reward = true,
  }
  function M.dispatchBatch(calls)
    if type(calls) ~= "table" then error("Preference replay batch must be a table") end
    if preferenceReplayDepth ~= 0 then error("Nested preference replay is unsupported") end
    if M.terminalActionUnknown then
      error("MGT_OUTCOME_UNKNOWN: Previous action outcome is unknown; do not retry")
    end
    synchronize()
    preferenceReplayDepth = 1
    local ok, message = pcall(function()
      for index = 1, #calls do
        local call = calls[index]
        if type(call) ~= "table" or not preferenceReplayCommands[call.command] then
          error("Unsupported preference replay command at index " .. tostring(index))
        end
        local params = call.params or {}
        if type(params) ~= "table" then error("Preference replay params must be a table") end
        M.dispatch(call.command, params)
      end
    end)
    preferenceReplayDepth = 0
    if not ok then error(message) end
    synchronize()
    return state(false)
  end
end
