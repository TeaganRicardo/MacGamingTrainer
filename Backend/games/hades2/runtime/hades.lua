-- Loaded before every command. All state is session-local, outside save tables.
-- Reject unsupported runtimes before cleaning up or installing any resident state.
if _VERSION ~= "Lua 5.2" then error("Unsupported Lua ABI: " .. tostring(_VERSION) .. "; Lua 5.2 required") end
for _, name in ipairs({ "SessionState", "GameState" }) do
  if type(_G[name]) ~= "table" then error("Unsupported game runtime: missing table " .. name) end
end
if type(UpdateTimers) ~= "function" then error("Unsupported game runtime: missing UpdateTimers") end
local previousModule = __MacGamingTrainerV1
if previousModule and previousModule.revision ~= 64 then
  local cleanupOk, cleanupMessage = pcall(previousModule.dispatch, "cleanup")
  if not cleanupOk then
    error("MGT_RESIDENT_RESTART_REQUIRED: previous resident cleanup failed: " .. tostring(cleanupMessage))
  end
  __MacGamingTrainerV1 = nil
end
if __MacGamingTrainerV1 == nil then
  local M = {
    version = 1, revision = 64, damageMultiplier = 2, damageEnabled = false,
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
    resourceLocks = {}, vitalLocks = {}, elementLocks = {}, statTargets = {}, statRuntime = {}, hooks = {}, featureErrors = {},
    catalogCache = {}, specialChoiceOpens = {}, specialChoiceRun = nil,
    requests = previousModule and previousModule.requests or {},
    requestOrder = previousModule and previousModule.requestOrder or {},
    lastActionReceipt = nil,
    -- Ephemeral install identity used only to reject stale UI selections. It is
    -- intentionally neither saved nor carried across a resident replacement.
    traitInventoryGeneration = tostring({}),
  }
  __MacGamingTrainerV1 = M

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
      if kind == "nil" then return "null" end
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
    clearDesired()
    deactivateRuntime()
    releaseGuard()
  end
  local function anyDesired()
    for _, value in pairs(M.desiredFeatures) do if value then return true end end
    return next(M.resourceLocks) ~= nil or next(M.vitalLocks) ~= nil or next(M.elementLocks) ~= nil or M.rerollsLock ~= nil
      or next(M.statTargets) ~= nil or M.nextRoomReward ~= nil
  end
  local function anyRuntimeActive()
    return M.invincibility or M.infiniteHealth or M.infiniteMana or M.damageEnabled
      or M.instantCastCooldown or M.hexAlwaysReady or M.infiniteAmmo or M.autoMiniGames or M.gardenQoL or M.boonRarityEnabled
      or M.moneyMultiplierEnabled or M.resourceMultiplierEnabled
      or owns("AddResource") or owns("SpendResource") or owns("UpdateRerollUI")
      or owns("GetMaxMetaUpgradeCost") or owns("CalculateCritChance")
      or owns("GetTotalHeroTraitValue") or M.statRuntime.dodge ~= nil or M.statRuntime.chargeSpeed ~= nil
      or M.statRuntime.moveSpeed ~= nil or M.statRuntime.sprintSpeed ~= nil or M.statRuntime.dashSpeed ~= nil or M.statRuntime.attackSpeed ~= nil or M.statRuntime.manaRegen ~= nil or M.statRuntime.enemyDamage or M.statRuntime.enemyHealth ~= nil
  end
  local reconcileDesired
  local forceCastAvailable, refillHex, currentSpellRuntime, actionLedger
  local function synchronize()
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
      return owner == nil or owner == current
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
      local allowed, allowedLookup = setmetatable({}, arrayMeta), {}
      for _, name in ipairs(sourceTraitNames()) do
        if ownerMatchesCurrent(name)
            and (eligibleLookup[name] or mountedCurrent(name)) then
          allowedLookup[name] = true
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
      currentWeapon = currentWeapon,
      isHammerTrait = isHammerTrait,
      isRuntimeAspect = isRuntimeAspect,
      removalReady = removalReady,
      applyExact = applyExact,
      removeMounted = removeMounted,
    }
  end)()

  local function rewards()
    local cached = M.catalogCache.rewards
    local seleneSignature = seleneModel.catalogSignature()
    local hammerSignature = hammerModel.catalogSignature()
    if type(cached) == "table"
        and cached.seleneSignature == seleneSignature
        and cached.hammerSignature == hammerSignature then
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
        hammerSignature = hammerSignature,
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
    local directTraitStrategies = {
      -- Artemis is shop-owned but not normal Pom eligibility. This ordinary-effect
      -- boon proves an intentional direct level path without replaying acquisition.
      CritBonusBoon = { sourceId = "Artemis", level = "increaseOne" },
      -- Icarus' OmegaExplodeBoon is not native SellTraits / rarity-menu eligible.
      -- Its mounted state is declarative (mana modifier + damage callback), with no
      -- acquire/setup/expire reward lifecycle, so it is the bounded direct example
      -- for exact rarity recompute and single-instance teardown in #227.
      OmegaExplodeBoon = { sourceId = "Icarus", rarity = "setExact", removal = "singleInstanceForce" },
    }
    local deferredTraitIssues = {
      costume = 239,
      temporary = 239,
      directSpecial = 239,
      familiar = 240,
      other = 221,
    }
    local rarityOrder = { "Common", "Rare", "Epic", "Heroic" }
    local directUnsafeLifecycleKeys = {
      "AcquireFunctionName", "AcquireFunction", "SetupFunction", "SetupFunctions",
      "OnExpire", "OnExpireFunctionName", "Uses", "ExpireAfterRooms",
    }

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

    local function directStrategySafe(trait)
      if type(trait) ~= "table" or directTraitStrategies[trait.Name] == nil then return false end
      for _, key in ipairs(directUnsafeLifecycleKeys) do
        if trait[key] ~= nil then return false end
      end
      if trait.RemainingUses ~= nil then return false end
      return true
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

    local function traitSourceId(trait)
      if type(trait) ~= "table" then return "" end
      local strategy = directTraitStrategies[trait.Name]
      if strategy then return strategy.sourceId end
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

    local function traitFamily(trait, sellEligible)
      if type(trait) ~= "table" then return "other" end
      local name = trait.Name or ""
      if directTraitStrategies[name] ~= nil then return "directSpecial" end
      if chaosLifecycleState(trait) ~= "" then return "chaos" end
      local slotted = seleneModel.currentSpell()
      if type(slotted) == "table" and slotted.TraitName == name then return "hex" end
      if #seleneModel.talentNodes(name, true) > 0 then return "hexTalent" end
      if trait.Slot == "Spell" or string.find(name, "Spell", 1, true) ~= nil
          or string.find(name, "Hex", 1, true) ~= nil then return "hex" end
      if hammerModel.isRuntimeAspect(trait) then return "weaponAspect" end
      if hammerModel.isHammerTrait(trait) then return "hammer" end
      if string.find(name, "Familiar", 1, true) ~= nil then return "familiar" end
      if trait.RemainingUses ~= nil then return "temporary" end
      if type(trait.InheritFrom) == "table" then
        for _, parent in ipairs(trait.InheritFrom) do
          if parent == "CostumeTrait" then return "costume" end
        end
      end

      -- TreatAsGodLootByShops makes several field/special NPC rewards sellable,
      -- but that does not make their lifecycle an ordinary Olympian/Hermes one.
      -- Ownership wins over menu eligibility; #239 handles those families unless
      -- an explicit direct strategy above opts in one audited operation.
      local source = traitSourceId(trait)
      if type(source) == "string" and source ~= "" then
        if string.find(source, "NPC_", 1, true) == 1
            or nativeSpecialChoiceDefinitions[source] ~= nil then
          return "directSpecial"
        end
      end
      if sellEligible then return "olympianHermes" end
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
      local strategy = directTraitStrategies[trait.Name]
      local directSafe = strategy ~= nil and directStrategySafe(trait)
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
        elseif family == "hammer" or family == "weaponAspect" then
          levelReason = "notMeaningful"
        elseif type(IncreaseTraitLevel) ~= "function" then
          levelReason = "nativePathUnavailable"
        elseif strategy and strategy.level == "increaseOne" and directSafe and not trait.BlockStacking then
          levelCapability, levelReason = "increaseOne", ""
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
        elseif type(AddRarityToTraits) ~= "function" then
          rarityReason = "nativePathUnavailable"
        elseif strategy and strategy.rarity == "setExact" and directSafe then
          rarityCapability, rarityReason = "setExact", ""
        elseif family == "olympianHermes" and sellEligible then
          rarityCapability, rarityReason = "setExact", ""
        else
          rarityReason = "ownerSpecificLifecycle"
        end

        local slotted = seleneModel.currentSpell()
        if sameCount > 1 and (family == "hex" or family == "hexTalent") then
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
        elseif family == "weaponAspect" then
          removalReason = "permanentProgressionOwned"
        elseif strategy and strategy.removal == "singleInstanceForce" and directSafe
            and type(RemoveTraitData) == "function" then
          removalCapability, removalReason = "singleInstanceForce", ""
        elseif family == "olympianHermes" and sellEligible then
          removalCapability, removalReason = "nameLevelAllMatching", ""
        elseif strategy and not directSafe then
          removalReason = "directSafetyFailed"
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
            family = family,
            sourceId = family == "chaos" and "Chaos"
              or ((family == "hex" or family == "hexTalent") and "Selene"
              or ((family == "hammer" or family == "weaponAspect") and "WeaponUpgrade"
              or traitSourceId(trait))),
            owner = family == "chaos" and "Chaos"
              or ((family == "hex" or family == "hexTalent") and "Selene"
              or ((family == "hammer" or family == "weaponAspect") and "WeaponUpgrade"
              or traitSourceId(trait))),
            level = traitLevel(trait),
            rarity = traitRarity(trait),
            hasRarity = trait.Rarity ~= nil,
            availableRarities = availableRarities(trait),
            sameNameCount = count,
            remainingUses = finite(trait.RemainingUses) and trait.RemainingUses or nil,
            lifecycleState = family == "chaos" and chaosLifecycleState(trait) or "",
            linkedTrait = family == "chaos" and chaosLinkedTraitName(trait) or "",
            canAdvanceLifecycle = family == "chaos" and chaosLifecycleState(trait) == "curse"
              and chaosLinkedTraitName(trait) ~= "" and type(RemoveTraitData) == "function",
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
      if target.Name ~= params.trait or family ~= params.family
          or traitLevel(target) ~= params.expectedLevel or traitRarity(target) ~= expectedRarity
          or count ~= params.expectedSameNameCount then
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

    return {
      currentRunTraits = currentRunTraits,
      resolveTarget = resolveTraitTarget,
      capabilities = operationCapabilities,
      availableRarities = availableRarities,
      targetHasRarity = targetHasRarity,
      level = traitLevel,
      rarity = traitRarity,
      chaosLifecycleState = chaosLifecycleState,
      chaosLinkedTraitName = chaosLinkedTraitName,
      rebuildChaosTarget = rebuildChaosTarget,
      seleneTalentNodes = seleneModel.talentNodes,
      teardownSlottedSpell = seleneModel.teardown,
      hasDirectStrategy = function(name) return directTraitStrategies[name] ~= nil end,
    }
  end)()

  local function state(includeCatalogs)
    local hero = CurrentRun and CurrentRun.Hero or {}
    local list = resources()
    local boonList, rewardList = nil, nil
    if includeCatalogs ~= false then boonList, rewardList = boons(), rewards() end
    local support = statSupport()
    local statAvailable = statAvailableMap(support)
    local currentScene = sceneName()
    local availableMana = number(hero.MaxMana)
    if CurrentRun and CurrentRun.Hero and type(GetHeroMaxAvailableMana) == "function" then
      local ok, value = pcall(GetHeroMaxAvailableMana)
      if ok and finite(value) then availableMana = value end
    end
    local featureSupportMap, activeFeatureMap, dormantFeatureMap = featureRuntimeMaps(hero)
    local spellChargeCost = nil
    if ready() and type(currentSpellRuntime) == "function" then
      local ok, _, _, _, cost = pcall(currentSpellRuntime)
      if ok and finite(cost) then spellChargeCost = cost end
    end
    local economySupported = type(AddResource) == "function" and type(SpendResource) == "function" and resourceCatalogReady()
    local activeMoney = not not (M.moneyMultiplierEnabled and owns("AddResource") and owns("SpendResource"))
    local activeResources = not not (M.resourceMultiplierEnabled and owns("AddResource") and owns("SpendResource"))
    featureSupportMap.moneyMultiplierEnabled = economySupported
    featureSupportMap.resourceMultiplierEnabled = economySupported
    activeFeatureMap.moneyMultiplierEnabled = activeMoney
    activeFeatureMap.resourceMultiplierEnabled = activeResources
    if M.desiredFeatures.moneyMultiplierEnabled and economySupported and not activeMoney then dormantFeatureMap.moneyMultiplierEnabled = true end
    if M.desiredFeatures.resourceMultiplierEnabled and economySupported and not activeResources then dormantFeatureMap.resourceMultiplierEnabled = true end
    local canSpawn = ready() and currentScene == "run" and type(MapState) == "table"
      and type(MapState.RoomRequiredObjects) == "table" and type(LootObjects) == "table"
    -- Current-run trait/buff inventory: live runtime truth, never the catalog
    -- and never desired state.
    local traitList, traitListReason = traitManagement.currentRunTraits()
    local elementList = setmetatable({}, arrayMeta)
    local heroElements = type(hero.Elements) == "table" and hero.Elements or {}
    local orderedElements = { "Fire", "Water", "Earth", "Air", "Aether" }
    for _, element in ipairs(orderedElements) do
      if heroElements[element] ~= nil or (type(TraitElementData) == "table" and TraitElementData[element] ~= nil) then
        elementList[#elementList + 1] = { id = element, name = elementNames[element] or element, count = number(heroElements[element]), locked = M.elementLocks[element] ~= nil }
      end
    end
    local runCount = 0
    if type(GameState.RunHistory) == "table" then runCount = #GameState.RunHistory + (type(CurrentRun) == "table" and 1 or 0) end
    local statsState = {}
    for _, stat in ipairs(statOrder or {}) do statsState[stat] = statState(stat, hero, support) end
    return {
      status = ready() and "ready" or "waiting", scene = currentScene,
      capabilities = {
        -- Desired feature state can be accepted as soon as the Lua runtime is
        -- loaded. Individual run-only features report dormant until their
        -- environment exists; hub-safe hooks can arm immediately.
        setFeature = true, setVitals = ready(), setResource = resourceReady(),
        spawnReward = canSpawn, setStats = anyAvailableStat(statAvailable),
        setElements = ready() and type(hero.Elements) == "table", hotBackup = true, hotRestore = false,
      },
      featureSupport = featureSupportMap,
      desiredFeatures = {
        invincibility = M.desiredFeatures.invincibility, infiniteHealth = M.desiredFeatures.infiniteHealth,
        infiniteMana = M.desiredFeatures.infiniteMana, damageEnabled = M.desiredFeatures.damageEnabled,
        instantCastCooldown = M.desiredFeatures.instantCastCooldown,
        hexAlwaysReady = M.desiredFeatures.hexAlwaysReady, infiniteAmmo = M.desiredFeatures.infiniteAmmo,
        autoMiniGames = M.desiredFeatures.autoMiniGames, gardenQoL = M.desiredFeatures.gardenQoL,
        boonRarityEnabled = M.desiredFeatures.boonRarityEnabled,
        moneyMultiplierEnabled = M.desiredFeatures.moneyMultiplierEnabled,
        resourceMultiplierEnabled = M.desiredFeatures.resourceMultiplierEnabled,
      },
      activeFeatures = activeFeatureMap,
      dormantFeatures = dormantFeatureMap,
      invincibility = M.desiredFeatures.invincibility, infiniteHealth = M.desiredFeatures.infiniteHealth,
      infiniteMana = M.desiredFeatures.infiniteMana, damageEnabled = M.desiredFeatures.damageEnabled,
      instantCastCooldown = M.desiredFeatures.instantCastCooldown,
      hexAlwaysReady = M.desiredFeatures.hexAlwaysReady, infiniteAmmo = M.desiredFeatures.infiniteAmmo,
      autoMiniGames = M.desiredFeatures.autoMiniGames, gardenQoL = M.desiredFeatures.gardenQoL,
      boonRarityEnabled = M.desiredFeatures.boonRarityEnabled,
      boonRarity = { target = M.boonRarityTarget, multiplier = M.boonRarityMultiplier * 100,
        forceLegendary = M.boonForceLegendary, forceDuo = M.boonForceDuo },
      -- Identity is current-run only. D00 proved `trait.Id` is assigned by
      -- GetTraitUniqueId and is NOT stable across run reload or restart, so the
      -- payload says so rather than implying a durable identifier.
      currentRunTraits = traitList,
      currentRunTraitIdentityScope = "currentRunInstance",
      currentRunTraitIdentityPersistent = false,
      currentRunTraitsReason = traitListReason,
      nextRoomReward = M.nextRoomReward,
      damageMultiplier = M.damageMultiplier,
      moneyMultiplier = M.moneyMultiplier, moneyMultiplierEnabled = M.desiredFeatures.moneyMultiplierEnabled,
      resourceMultiplier = M.resourceMultiplier, resourceMultiplierEnabled = M.desiredFeatures.resourceMultiplierEnabled,
      health = number(hero.Health), maxHealth = number(hero.MaxHealth), healthLocked = M.vitalLocks.health ~= nil,
      mana = number(hero.Mana), maxMana = number(hero.MaxMana), manaLocked = M.vitalLocks.mana ~= nil,
      availableMana = availableMana, totalMaxMana = number(hero.MaxMana),
      armor = number(hero.HealthBuffer), armorLocked = M.vitalLocks.armor ~= nil,
      spellCharge = number(CurrentRun and CurrentRun.SpellCharge), spellChargeCost = spellChargeCost,
      money = number(GameState.Resources and GameState.Resources.Money), moneyLocked = M.resourceLocks.Money ~= nil,
      rerolls = number(CurrentRun and CurrentRun.NumRerolls), rerollsLocked = M.rerollsLock ~= nil,
      runCount = runCount, elements = elementList,
      statSupport = support, statAvailable = statAvailable, stats = statsState,
      resources = list, boons = boonList, rewards = rewardList,
      lastAction = actionLedger.latestReceipt(),
      featureErrors = M.featureErrors,
      runtimeDiagnostics = {
        revision = M.revision, heroObjectId = hero.ObjectId, runCount = runCount,
        guardInstalled = not not (M.guardWrapper and UpdateTimers == M.guardWrapper),
        castHook = owns("SetEffectProperty") and owns("SetWeaponProperty"), castRuntime = castDiagnostics(),
        hexRuntime = M.hexRuntime,
        miniGameHooks = { fishing = owns("WaitForFishingInput"), exorcism = owns("ExorcismSequence") },
        boonRarityHooks = { chances = owns("GetRarityChances"), options = owns("SetTraitsOnLoot") },
        gardenHooks = { plant = owns("GardenPlantSeed"), harvest = owns("UseGardenPlot") },
        nextRoomRewardHook = owns("ChooseRoomReward") and owns("StartRoom"),
        nextRoomRewardPatchedDoors = M.nextRoomRewardPatchedDoors,
        nextRoomRewardToken = M.nextRoomRewardToken,
        lastConsumedNextRoomRewardToken = M.lastConsumedNextRoomRewardToken,
      },
    }
  end
  local function ensureHeroDamageRouter()
    requireFunctions("hero damage routing", { "Damage" })
    if owns("Damage") then return end
    installHook("Damage", function(original, victim, triggerArgs)
      if victim == CurrentRun.Hero then
        if M.invincibility then
          -- OnHit increments Hero.Hits before it reaches Damage(). Restore the
          -- pre-Invincibility baseline before skipping the vanilla damage pipeline.
          restoreInvincibilityHitCount(victim)
          -- Stop at the outer Lua damage entry. This skips armor loss, hit-stun,
          -- knockback and normal hostile on-hit processing inside Damage().
          return nil
        end
        local routedArgs = triggerArgs
        if M.statTargets.enemyDamage ~= nil and type(triggerArgs) == "table" and finite(triggerArgs.DamageAmount) then
          local attackerId = triggerArgs.AttackerId
          if attackerId == nil and type(triggerArgs.AttackerTable) == "table" then attackerId = triggerArgs.AttackerTable.ObjectId end
          -- Only scale damage that can be attributed to something other than
          -- the hero. Self-damage / sacrifices retain their native semantics.
          if attackerId ~= nil and attackerId ~= CurrentRun.Hero.ObjectId then
            routedArgs = {}
            for key, value in pairs(triggerArgs) do routedArgs[key] = value end
            routedArgs.DamageAmount = math.max(0, triggerArgs.DamageAmount * M.statTargets.enemyDamage / 100)
          end
        end
        if M.infiniteHealth and type(routedArgs) == "table" and finite(victim.Health) then
          -- Preserve the normal hit pipeline while preventing the final health
          -- value from dropping below the pre-hit value. Health buffers/armor
          -- and hit presentations remain owned by the game.
          local previousMin = routedArgs.MinHealth
          local floor = victim.Health
          if previousMin == nil or (finite(previousMin) and previousMin < floor) then routedArgs.MinHealth = floor end
          local result = original(victim, routedArgs)
          routedArgs.MinHealth = previousMin
          return result
        end
        return original(victim, routedArgs)
      end
      return original(victim, triggerArgs)
    end)
  end
  local function installInvincibility()
    requireFunctions("invincibility", {
      "Damage", "SetUnitInvulnerable", "SetUnitVulnerable",
      "AddEffectBlock", "RemoveEffectBlock", "ClearEffect",
    })
    ensureHeroDamageRouter()
    local hero = CurrentRun.Hero
    if M.invincibilityHitHero ~= hero or not M.invincibilityHitBaselineKnown then
      M.invincibilityHitHero = hero
      M.invincibilityHitBaseline = hero.Hits
      M.invincibilityHitBaselineKnown = true
    end
    if M.invincibilityEffectBlockHero ~= hero then
      for _, effectName in ipairs(invincibilityBlockedEffects) do
        AddEffectBlock({ Id = hero.ObjectId, Name = effectName })
        ClearEffect({ Id = hero.ObjectId, Name = effectName })
      end
      M.invincibilityEffectBlockHero = hero
    end
    if M.invincibilityHero ~= hero or not (type(hero.InvulnerableFlags) == "table" and hero.InvulnerableFlags[trainerInvincibilityFlag]) then
      SetUnitInvulnerable(hero, trainerInvincibilityFlag, { Silent = true })
      M.invincibilityHero = hero
    end
    M.invincibility = true
  end
  local function installHealth()
    requireFunctions("infinite health", { "SacrificeHealth", "Damage" })
    ensureHeroDamageRouter()
    if not owns("SacrificeHealth") then
      installHook("SacrificeHealth", function(original, args)
        if M.infiniteHealth and args and args.DeductHealth then
          local protected = {}
          for key, value in pairs(args) do protected[key] = value end
          protected.DeductHealth = false
          return original(protected)
        end
        return original(args)
      end)
    end
    if not M.deathFlag then M.deathFlag = acquireFlag("BlockHeroDeath") end
    M.infiniteHealth = true
  end
  local function installEnemyDamageLock()
    requireFunctions("enemy damage multiplier", { "Damage" })
    if not finite(M.statTargets.enemyDamage) then return end
    ensureHeroDamageRouter()
    M.statRuntime.enemyDamage = true
  end
  forceCastAvailable = function()
    if not M.instantCastCooldown then return false end
    return applyCastAvailability()
  end
  local function installInstantCastCooldown()
    requireFunctions("cast always available", { "SetEffectProperty", "SetWeaponProperty", "GetWeaponDataValue" })
    M.instantCastCooldown = true
    local runtime = ensureCastRuntime()
    if runtime == nil then error("Unable to initialize cast delivery runtime") end
    if not owns("SetWeaponProperty") then
      installHook("SetWeaponProperty", function(original, args, ...)
        if M.instantCastCooldown and type(args) == "table" and castModel.protects(args.WeaponName)
            and castModel.overrides[args.Property] ~= nil
            and (args.DestinationId == nil or args.DestinationId == CurrentRun.Hero.ObjectId) then
          local current = ensureCastRuntime()
          if current then
            local weapon = castModel.ensureWeaponRuntime(current, args.WeaponName, CurrentRun.Hero)
            weapon.nativeProperties[args.Property] = args.Value
            weapon.nativePropertyKnown[args.Property] = args.Value ~= nil
          end
          local protected = {}
          for key, value in pairs(args) do protected[key] = value end
          protected.DestinationId = CurrentRun.Hero.ObjectId
          protected.Value = castModel.overrides[args.Property]
          protected.ValueChangeType = "Absolute"
          -- Preserve the caller's DataValue mode.  Native trait property
          -- changes omit it; injecting false here prevented the engine-level
          -- cast gate from actually changing in revision 13.
          return original(protected, ...)
        end
        return original(args, ...)
      end)
    end
    if not owns("SetEffectProperty") then
      installHook("SetEffectProperty", function(original, args, ...)
        if M.instantCastCooldown and type(args) == "table"
            and args.WeaponName == "WeaponCast" and castEffectOverrides[args.EffectName] ~= nil
            and args.Property == "Active"
            and (args.DestinationId == nil or args.DestinationId == CurrentRun.Hero.ObjectId) then
          local current = ensureCastRuntime()
          if current and type(args.Value) == "boolean" then
            current.nativeEffects[args.EffectName] = args.Value
            current.nativeEffectKnown[args.EffectName] = true
          end
          local protected = {}
          for key, value in pairs(args) do protected[key] = value end
          protected.DestinationId = CurrentRun.Hero.ObjectId
          protected.Value = castEffectOverrides[args.EffectName]
          protected.ValueChangeType = "Absolute"
          return original(protected, ...)
        end
        return original(args, ...)
      end)
    end
    if not forceCastAvailable() then error("Unable to arm cast delivery multi-fire path") end
  end
  currentSpellRuntime = function()
    if not ready() or type(CurrentRun.Hero.Traits) ~= "table"
        or type(GetWeaponData) ~= "function" or type(GetManaSpendCost) ~= "function" then return nil end
    for _, trait in ipairs(CurrentRun.Hero.Traits) do
      if type(trait) == "table" and trait.Slot == "Spell" and type(trait.PreEquipWeapons) == "table"
          and type(trait.PreEquipWeapons[1]) == "string" then
        local weaponName = trait.PreEquipWeapons[1]
        local okData, data = pcall(GetWeaponData, CurrentRun.Hero, weaponName)
        if okData and type(data) == "table" then
          local okCost, cost = pcall(GetManaSpendCost, data)
          if okCost and finite(cost) and cost > 0 then return trait, weaponName, data, cost end
        end
      end
    end
    return nil
  end
  refillHex = function()
    if not M.hexAlwaysReady then return false end
    local trait, weaponName, _, cost = currentSpellRuntime()
    if trait == nil then M.hexRuntime = { ready = false, reason = "noSpell" }; return false end
    if finite(trait.RemainingUses) and trait.RemainingUses <= 0 then
      trait.RemainingUses = 1
      if type(UpdateTraitNumber) == "function" then pcall(UpdateTraitNumber, trait) end
    end
    local charge = finite(CurrentRun.SpellCharge) and CurrentRun.SpellCharge or 0
    if charge < cost and type(ChargeSpell) == "function" then
      -- Prefer the game's own charging path so the Hex HUD/cooldown overlay is
      -- refreshed naturally. Force bypasses encounter proximity restrictions.
      pcall(ChargeSpell, -(cost - charge), { Force = true })
      charge = finite(CurrentRun.SpellCharge) and CurrentRun.SpellCharge or charge
    end
    if charge < cost then CurrentRun.SpellCharge = cost end
    local ok = pcall(SetWeaponProperty, {
      WeaponName = weaponName, DestinationId = CurrentRun.Hero.ObjectId, Property = "Enabled", Value = true,
    })
    M.hexRuntime = { ready = ok and number(CurrentRun.SpellCharge) >= cost, weapon = weaponName, cost = cost, charge = number(CurrentRun.SpellCharge) }
    return M.hexRuntime.ready
  end
  local function installHex()
    requireFunctions("hex always ready", { "SpellFire", "GetWeaponData", "GetManaSpendCost", "SetWeaponProperty" })
    if not owns("SpellFire") then
      installHook("SpellFire", function(original, ...)
        local result = original(...)
        if M.hexAlwaysReady then refillHex() end
        return result
      end)
    end
    M.hexAlwaysReady = true
    -- A run transition can temporarily expose Hero before the Spell trait is
    -- mounted. Keep the desired hook resident and let the frame guard arm it
    -- as soon as a usable hex appears instead of turning the user's toggle off.
    refillHex()
  end
  local function refillAmmo()
    local hero = CurrentRun.Hero
    if type(hero.Ammo) ~= "table" then return end
    for weaponName, current in pairs(hero.Ammo) do
      if type(weaponName) == "string" and finite(current) then
        local ok, maximum = pcall(GetMaxAmmo, weaponName)
        if ok and finite(maximum) and maximum > current then
          UpdateWeaponAmmo(weaponName, maximum - current)
        end
      end
    end
  end
  local function installAmmo()
    requireFunctions("infinite ammo", { "UpdateWeaponAmmo", "GetMaxAmmo" })
    if not owns("UpdateWeaponAmmo") then
      installHook("UpdateWeaponAmmo", function(original, weaponName, delta, args)
        if M.infiniteAmmo and finite(delta) and delta < 0 then delta = 0 end
        return original(weaponName, delta, args)
      end)
    end
    M.infiniteAmmo = true
    refillAmmo()
  end
  local function installMiniGames()
    if type(WaitForFishingInput) ~= "function" and type(ExorcismSequence) ~= "function" then
      error("Unsupported auto minigames: fishing/exorcism entry points unavailable")
    end
    if type(WaitForFishingInput) == "function" and not owns("WaitForFishingInput") then
      installHook("WaitForFishingInput", function(original, args, ...)
        if not M.autoMiniGames then return original(args, ...) end
        args = args or {}
        if type(ToggleCombatControl) == "function" then
          pcall(ToggleCombatControl, { "Use" }, true, "Fishing")
        end
        if type(FishingReadyForInputPresentation) == "function" and args.FishingAnimationPointId ~= nil then
          pcall(FishingReadyForInputPresentation, args.FishingAnimationPointId)
        end
        -- Do not fabricate the fish/reward. Wait for the game's own genuine
        -- success window, then submit the same state transition as a valid Use
        -- press. This keeps rarity selection and FishingEndPresentation native.
        while M.autoMiniGames and ready() and type(CurrentRun.Hero) == "table"
            and not CurrentRun.Hero.FishingInput do
          if CurrentRun.Hero.FishingState == "Success" then
            CurrentRun.Hero.FishingInput = true
            if type(SetThreadWait) == "function" then pcall(SetThreadWait, "Fishing", 0.01) end
            return
          end
          wait(0.01)
        end
        if not M.autoMiniGames and ready() then return original(args, ...) end
      end)
    end
    if type(ExorcismSequence) == "function" and not owns("ExorcismSequence") then
      installHook("ExorcismSequence", function(original, source, exorcismData, args, user, ...)
        if M.autoMiniGames then return true end
        return original(source, exorcismData, args, user, ...)
      end)
    end
    M.autoMiniGames = true
  end
  local function installGardenQoL()
    requireFunctions("garden quality-of-life", { "GardenPlantSeed", "UseGardenPlot" })
    if not owns("GardenPlantSeed") then
      installHook("GardenPlantSeed", function(original, screen, button, args, ...)
        if not M.gardenQoL then return original(screen, button, args, ...) end
        local protected = {}
        if type(args) == "table" then for key, value in pairs(args) do protected[key] = value end end
        protected.MultiPlant = true
        return original(screen, button, protected, ...)
      end)
    end
    if not owns("UseGardenPlot") then
      installHook("UseGardenPlot", function(original, plot, args, user, ...)
        if not M.gardenQoL or type(plot) ~= "table" or not plot.ReadyForHarvest then
          return original(plot, args, user, ...)
        end
        local upgrades = type(GameState) == "table" and GameState.WorldUpgrades or nil
        if type(upgrades) ~= "table" then return original(plot, args, user, ...) end
        local previous = upgrades.WorldUpgradeGardenHarvestAll
        upgrades.WorldUpgradeGardenHarvestAll = true
        local packed = table.pack(pcall(original, plot, args, user, ...))
        upgrades.WorldUpgradeGardenHarvestAll = previous
        if not packed[1] then error(packed[2]) end
        return table.unpack(packed, 2, packed.n)
      end)
    end
    M.gardenQoL = true
  end

  local rarityRank = { Common = 1, Rare = 2, Epic = 3, Heroic = 4 }
  local function traitSpecialRarity(traitName)
    local data = type(TraitData) == "table" and TraitData[traitName] or nil
    if type(data) ~= "table" then return nil end
    if data.IsDuoBoon then return "Duo" end
    local inherited = type(data) == "table" and data.InheritFrom or nil
    if type(inherited) == "string" then inherited = { inherited } end
    if type(inherited) == "table" then
      for _, parent in pairs(inherited) do
        if parent == "SynergyTrait" then return "Duo" end
        if parent == "LegendaryTrait" then return "Legendary" end
      end
    end
    local levels = data.RarityLevels
    if type(levels) == "table" then
      if type(levels.Duo) == "table" then return "Duo" end
      if type(levels.Legendary) == "table" and levels.Common == nil and levels.Rare == nil
          and levels.Epic == nil and levels.Heroic == nil then return "Legendary" end
    end
    return nil
  end
  local function specialOptionKind(option)
    if type(option) ~= "table" then return nil end
    if option.Rarity == "Legendary" or option.Rarity == "Duo" then return option.Rarity end
    return traitSpecialRarity(option.ItemName)
  end
  local function applyMinimumBoonRarity(lootData)
    if type(lootData) ~= "table" or type(lootData.UpgradeOptions) ~= "table" then return end
    local targetRank = rarityRank[M.boonRarityTarget] or 1
    for _, option in ipairs(lootData.UpgradeOptions) do
      if type(option) == "table" then
        local special = specialOptionKind(option)
        if not special then
          local currentRank = rarityRank[option.Rarity or "Common"] or 1
          if currentRank < targetRank then option.Rarity = M.boonRarityTarget end
        end
      end
    end
  end
  local function hasSpecialBoonOption(lootData, wanted)
    if type(lootData) ~= "table" or type(lootData.UpgradeOptions) ~= "table" then return false end
    for _, option in ipairs(lootData.UpgradeOptions) do
      if specialOptionKind(option) == wanted then return true end
    end
    return false
  end
  local function forceSpecialBoonOption(lootData, args, wanted)
    if wanted == "Legendary" and not M.boonForceLegendary then return false end
    if wanted == "Duo" and not M.boonForceDuo then return false end
    if type(lootData) ~= "table" or type(lootData.UpgradeOptions) ~= "table" then return false end
    if not lootData.GodLoot and not lootData.TreatAsGodLootByShops then return false end
    if lootData.ForceCommon or (type(args) == "table" and args.ForceCommon) then return false end
    if type(args) == "table" and type(args.BlockRarities) == "table" and args.BlockRarities[wanted] then return false end
    if hasSpecialBoonOption(lootData, wanted) then return true end

    -- Ask the game's own eligibility pipeline for the current pool so trait
    -- prerequisites, ownership, bans and room restrictions remain native.
    local ok, eligible = pcall(GetEligibleUpgrades, lootData.UpgradeOptions, lootData, lootData)
    if not ok or type(eligible) ~= "table" then return false end
    local selected = {}
    for _, option in ipairs(lootData.UpgradeOptions) do
      if type(option) == "table" and type(option.ItemName) == "string" then selected[option.ItemName] = true end
    end
    local candidate = nil
    for _, option in ipairs(eligible) do
      if type(option) == "table" and type(option.ItemName) == "string"
          and not selected[option.ItemName] and traitSpecialRarity(option.ItemName) == wanted then
        candidate = { ItemName = option.ItemName, Type = option.Type or "Trait", Rarity = wanted }
        break
      end
    end
    if candidate == nil then return false end

    -- Preserve the native number of visible choices. Replace the last normal
    -- option; only append when the game produced fewer choices on its own.
    local replacement = nil
    for index = #lootData.UpgradeOptions, 1, -1 do
      if specialOptionKind(lootData.UpgradeOptions[index]) == nil then replacement = index; break end
    end
    if replacement ~= nil then
      lootData.UpgradeOptions[replacement] = candidate
    elseif #lootData.UpgradeOptions < 3 then
      lootData.UpgradeOptions[#lootData.UpgradeOptions + 1] = candidate
    else
      return false
    end
    return true
  end
  local function installBoonRarity()
    requireFunctions("boon rarity control", { "GetRarityChances", "SetTraitsOnLoot", "GetEligibleUpgrades" })
    if not owns("GetRarityChances") then
      installHook("GetRarityChances", function(original, loot, ...)
        local chances = original(loot, ...)
        if M.boonRarityEnabled and type(chances) == "table" and finite(M.boonRarityMultiplier) then
          local multiplier = math.max(0, M.boonRarityMultiplier)
          for _, rarity in ipairs({ "Rare", "Epic", "Heroic" }) do
            if finite(chances[rarity]) then chances[rarity] = math.max(0, math.min(1, chances[rarity] * multiplier)) end
          end
        end
        return chances
      end)
    end
    if not owns("SetTraitsOnLoot") then
      installHook("SetTraitsOnLoot", function(original, lootData, args, ...)
        local packed = table.pack(original(lootData, args, ...))
        if M.boonRarityEnabled and type(lootData) == "table" then
          applyMinimumBoonRarity(lootData)
          forceSpecialBoonOption(lootData, args, "Legendary")
          forceSpecialBoonOption(lootData, args, "Duo")
        end
        return table.unpack(packed, 1, packed.n)
      end)
    end
    M.boonRarityEnabled = true
  end

  local nextRoomDirectRewards = {
    RoomMoneyDrop=true, MetaCurrencyDrop=true, MetaCardPointsCommonDrop=true, MemPointsCommonDrop=true,
    MaxHealthDrop=true, MaxManaDrop=true, StackUpgrade=true, WeaponUpgrade=true, HermesUpgrade=true,
  }

  local function nextRoomRewardSpec(wanted)
    if type(wanted) ~= "string" then return nil, nil end
    if nextRoomDirectRewards[wanted] then return wanted, nil end
    if type(LootData) == "table" and type(LootData[wanted]) == "table" then return "Boon", wanted end
    return nil, nil
  end

  local function ordinaryDoorReward(room, native)
    if type(room) ~= "table" or type(native) ~= "string" then return false end
    if room.NoReward or room.DeferReward then return false end
    if native == "Story" or native == "Shop" or native == "Empty" or native == "Devotion" then return false end
    if type(room.Encounter) == "table" and type(room.Encounter.Name) == "string"
        and string.find(room.Encounter.Name, "Boss", 1, true) then return false end
    return native == "Boon" or nextRoomDirectRewards[native] == true
      or (type(ConsumableData) == "table" and type(ConsumableData[native]) == "table")
      or (type(LootData) == "table" and type(LootData[native]) == "table")
  end

  local function forceNextRoomReward(room, wanted)
    local rewardType, forceLoot = nextRoomRewardSpec(wanted)
    if rewardType == nil or type(room) ~= "table" then return nil, nil end
    room.Reward = { Name = rewardType }
    room.ChosenRewardType = rewardType
    if forceLoot ~= nil then
      room.Reward.ForceLootName = forceLoot
      room.ForceLootName = forceLoot
    else
      room.ForceLootName = nil
    end
    return rewardType, forceLoot
  end

  local function patchOfferedNextRoomDoors()
    local wanted = M.nextRoomReward
    if wanted == nil or type(MapState) ~= "table" or type(MapState.OfferedExitDoors) ~= "table" then
      M.nextRoomRewardPatchedDoors = 0
      return 0
    end
    local patched = 0
    for doorId, door in pairs(MapState.OfferedExitDoors) do
      local room = type(door) == "table" and door.Room or nil
      local native = type(room) == "table" and room.ChosenRewardType or nil
      if ordinaryDoorReward(room, native) then
        local rewardType, forceLoot = forceNextRoomReward(room, wanted)
        if rewardType ~= nil then
          patched = patched + 1
          if type(CurrentRun) == "table" and type(CurrentRun.CurrentRoom) == "table" then
            CurrentRun.CurrentRoom.OfferedRewards = CurrentRun.CurrentRoom.OfferedRewards or {}
            CurrentRun.CurrentRoom.OfferedRewards[doorId] = { Type = rewardType, ForceLootName = forceLoot }
          end
          -- Existing previews were already materialized before the trainer command.
          -- Reuse those world-UI objects instead of spawning duplicate icons.
          if type(CreateDoorRewardPreview) == "function" and type(door.RewardPreviewIconIds) == "table"
              and next(door.RewardPreviewIconIds) ~= nil then
            pcall(CreateDoorRewardPreview, door, rewardType, forceLoot, nil, { ReUseIds = true })
          end
          if type(RefreshUseButton) == "function" and door.ObjectId ~= nil then
            pcall(RefreshUseButton, door.ObjectId, door)
          end
        end
      end
    end
    M.nextRoomRewardPatchedDoors = patched
    return patched
  end

  local function installNextRoomReward()
    requireFunctions("next room reward", { "ChooseRoomReward", "StartRoom" })
    if M.nextRoomRewardOriginRoom == nil and type(CurrentRun) == "table" then
      M.nextRoomRewardOriginRoom = CurrentRun.CurrentRoom
    end
    if not owns("ChooseRoomReward") then
      installHook("ChooseRoomReward", function(original, run, room, rewardStoreName, previouslyChosenRewards, args, ...)
        local native = original(run, room, rewardStoreName, previouslyChosenRewards, args, ...)
        local wanted = M.nextRoomReward
        -- The game chooses each offered exit independently. Keep the one-shot
        -- armed across every door so the player's actual selection is forced.
        if wanted == nil or type(args) ~= "table" or type(args.Door) ~= "table"
            or not ordinaryDoorReward(room, native) then return native end
        local rewardType = forceNextRoomReward(room, wanted)
        return rewardType or native
      end)
    end
    if not owns("StartRoom") then
      installHook("StartRoom", function(original, currentRun, currentRoom, ...)
        local result = original(currentRun, currentRoom, ...)
        if M.nextRoomReward ~= nil then
          local origin = M.nextRoomRewardOriginRoom
          if origin == nil or currentRoom ~= origin then
            M.lastConsumedNextRoomRewardToken = M.nextRoomRewardToken
            M.nextRoomReward = nil
            M.nextRoomRewardToken = nil
            releaseNextRoomReward()
          end
        end
        return result
      end)
    end
    local patchRoom = type(CurrentRun) == "table" and CurrentRun.CurrentRoom or nil
    if M.nextRoomRewardPatchedValue ~= M.nextRoomReward or M.nextRoomRewardPatchRoom ~= patchRoom then
      patchOfferedNextRoomDoors()
      M.nextRoomRewardPatchedValue = M.nextRoomReward
      M.nextRoomRewardPatchRoom = patchRoom
    end
  end

  local function installMana()
    requireFunctions("infinite mana", { "ManaDelta", "GetHeroMaxAvailableMana", "UpdateWeaponMana", "UpdateManaMeterUI" })
    if M.infiniteMana then return end
    installHook("ManaDelta", function(original, delta, args)
      local result = original(delta, args)
      if M.infiniteMana then CurrentRun.Hero.Mana = GetHeroMaxAvailableMana(); refreshMana() end
      return result
    end)
    M.manaFlag = acquireFlag("UnlimitedMana")
    M.infiniteMana = true
    CurrentRun.Hero.Mana = GetHeroMaxAvailableMana()
    refreshMana()
  end
  local function installDamage()
    requireFunctions("damage multiplier", { "CalculateDamageMultipliers" })
    if M.damageEnabled then return end
    installHook("CalculateDamageMultipliers", function(original, attacker, victim, weaponData, triggerArgs)
      local result = original(attacker, victim, weaponData, triggerArgs)
      if M.damageEnabled and attacker == CurrentRun.Hero then return result * M.damageMultiplier end
      return result
    end)
    M.damageEnabled = true
  end
  local function installEconomy()
    requireResources()
    requireFunctions("resource modifiers", { "AddResource", "SpendResource" })
    installHook("AddResource", function(original, id, amount, source, args)
      if finite(amount) and amount > 0 and source ~= trainerSource then
        if id == "Money" and M.moneyMultiplierEnabled then amount = amount * M.moneyMultiplier
        elseif id ~= "Money" and M.resourceMultiplierEnabled then
          local _, _, allowed = resourceCatalog()
          if allowed[id] then amount = amount * M.resourceMultiplier end
        end
      end
      local result = original(id, amount, source, args)
      enforceResource(id)
      return result
    end)
    installHook("SpendResource", function(original, id, amount, source, args)
      if M.resourceLocks[id] ~= nil and finite(amount) and amount > 0 then
        -- Preserve the game's spend path/presentations without consuming the
        -- locked currency.  Passing zero is safer than spending then writing
        -- the save-backed resource table back after the fact.
        local result = original(id, 0, source, args)
        enforceResource(id)
        return result
      end
      local result = original(id, amount, source, args)
      enforceResource(id)
      return result
    end)
  end
  local function installRerolls()
    requireFunctions("reroll lock", { "UpdateRerollUI" })
    installHook("UpdateRerollUI", function(original, value)
      if M.rerollsLock ~= nil then
        CurrentRun.NumRerolls = M.rerollsLock
        value = M.rerollsLock
      end
      return original(value)
    end)
  end
  local function containsDodgeChange(value, seen, depth)
    if type(value) ~= "table" or depth > 5 then return false end
    seen = seen or {}; if seen[value] then return false end; seen[value] = true
    if value.LifeProperty == "DodgeChance" then return true end
    for _, child in pairs(value) do if containsDodgeChange(child, seen, depth + 1) then return true end end
    return false
  end
  local function installGraspLock()
    requireFunctions("grasp lock", { "GetMaxMetaUpgradeCost" })
    if type(GameState) == "table" and M.statTargets.grasp ~= nil then
      GameState.MaxMetaUpgradeCostCache = M.statTargets.grasp
    end
    if not owns("GetMaxMetaUpgradeCost") then
      installHook("GetMaxMetaUpgradeCost", function(original, ...)
        if M.statTargets.grasp ~= nil then
          if type(GameState) == "table" then GameState.MaxMetaUpgradeCostCache = M.statTargets.grasp end
          return M.statTargets.grasp
        end
        return original(...)
      end)
    end
    M.statRuntime.grasp = true
  end
  local function installCritLock()
    requireFunctions("critical chance lock", { "CalculateCritChance", "GetTotalHeroTraitValue" })
    ensureStatTraitValueRouter()
    if not owns("CalculateCritChance") then
      installHook("CalculateCritChance", function(original, attacker, victim, weaponData, triggerArgs, ...)
        if M.statTargets.crit ~= nil and attacker == CurrentRun.Hero then
          local luck = GetTotalHeroTraitValue("LuckMultiplier", { IsMultiplier = true })
          if not finite(luck) or luck <= 0 then luck = 1 end
          local chance = math.max(0, math.min(1, M.statTargets.crit / 100)) / luck
          if type(triggerArgs) == "table" then triggerArgs.CritChance = chance end
          return chance
        end
        return original(attacker, victim, weaponData, triggerArgs, ...)
      end)
    end
    M.statRuntime.crit = true
  end
  local function installDodgeLock()
    requireFunctions("dodge lock", { "GetTotalHeroTraitValue", "SetLifeProperty" })
    local hero = CurrentRun.Hero
    if type(M.statRuntime.dodge) ~= "table" or M.statRuntime.dodge.hero ~= hero then
      releaseDodgeLock()
      local natural = getDodgeRaw(hero)
      if not finite(natural) then error("Unsupported dodge lock: trait DodgeChance unavailable") end
      M.statRuntime.dodge = { hero = hero, natural = natural }
    end
    ensureStatTraitValueRouter()
    if not owns("SetLifeProperty") then
      installHook("SetLifeProperty", function(original, args, ...)
        if M.statTargets.dodge ~= nil and type(args) == "table" and args.Property == "DodgeChance" then
          local destination = args.DestinationId
          if destination == nil or destination == CurrentRun.Hero.ObjectId then
            local protected = {}
            for key, item in pairs(args) do protected[key] = item end
            protected.DestinationId = CurrentRun.Hero.ObjectId
            protected.DataValue = false
            protected.Value = M.statTargets.dodge / 100
            protected.ValueChangeType = nil
            return original(protected, ...)
          end
        end
        return original(args, ...)
      end)
    end
    if not setDodgeRaw(hero, M.statTargets.dodge / 100) then
      error("Unsupported dodge lock: SetLifeProperty failed")
    end
  end
  featureOrder = {
    "invincibility", "infiniteHealth", "infiniteMana", "damageEnabled", "instantCastCooldown",
    "hexAlwaysReady", "infiniteAmmo", "autoMiniGames", "gardenQoL", "boonRarityEnabled",
  }
  featureRegistry = {
    invincibility = {
      install = installInvincibility, release = releaseInvincibility,
      support = function() return type(Damage) == "function" and type(SetUnitInvulnerable) == "function" and type(SetUnitVulnerable) == "function" end,
      active = function(hero) return M.invincibility and owns("Damage") and M.invincibilityHero == hero and type(hero.InvulnerableFlags) == "table" and hero.InvulnerableFlags[trainerInvincibilityFlag] end,
    },
    infiniteHealth = {
      install = installHealth, release = releaseHealth,
      support = function() return type(Damage) == "function" and type(SacrificeHealth) == "function" end,
      active = function() return M.infiniteHealth and owns("Damage") and owns("SacrificeHealth") and SessionState.BlockHeroDeath end,
    },
    infiniteMana = {
      install = installMana, release = releaseMana,
      support = function() return type(ManaDelta) == "function" end,
      active = function() return M.infiniteMana and owns("ManaDelta") and SessionState.UnlimitedMana end,
    },
    damageEnabled = {
      install = installDamage, release = releaseDamage,
      support = function() return type(CalculateDamageMultipliers) == "function" end,
      active = function() return M.damageEnabled and owns("CalculateDamageMultipliers") end,
    },
    instantCastCooldown = {
      install = installInstantCastCooldown, release = releaseInstantCastCooldown,
      support = function() return type(SetEffectProperty) == "function" and type(SetWeaponProperty) == "function" and type(GetWeaponDataValue) == "function" end,
      active = function(hero) return M.instantCastCooldown and owns("SetEffectProperty") and owns("SetWeaponProperty") and type(M.castRuntime) == "table" and M.castRuntime.hero == hero and M.castRuntime.applied and castWeaponGateVerified(M.castRuntime) end,
    },
    hexAlwaysReady = {
      install = installHex, release = releaseHex,
      support = function() return type(SpellFire) == "function" and type(GetWeaponData) == "function" and type(GetManaSpendCost) == "function" and type(SetWeaponProperty) == "function" end,
      active = function() return M.hexAlwaysReady and owns("SpellFire") and type(M.hexRuntime) == "table" and M.hexRuntime.ready end,
      dormant = function() return M.desiredFeatures.hexAlwaysReady and owns("SpellFire") and type(M.hexRuntime) == "table" and M.hexRuntime.reason == "noSpell" end,
    },
    infiniteAmmo = {
      install = installAmmo, release = releaseAmmo,
      support = function() return type(UpdateWeaponAmmo) == "function" and type(GetMaxAmmo) == "function" end,
      active = function() return M.infiniteAmmo and owns("UpdateWeaponAmmo") end,
    },
    autoMiniGames = {
      install = installMiniGames, release = releaseMiniGames, available = function() return true end,
      support = function() return type(WaitForFishingInput) == "function" or type(ExorcismSequence) == "function" end,
      active = function() return M.autoMiniGames and (owns("WaitForFishingInput") or owns("ExorcismSequence")) end,
    },
    gardenQoL = {
      install = installGardenQoL, release = releaseGardenQoL, available = function() return true end,
      support = function() return type(GardenPlantSeed) == "function" and type(UseGardenPlot) == "function" end,
      active = function() return M.gardenQoL and owns("GardenPlantSeed") and owns("UseGardenPlot") end,
    },
    boonRarityEnabled = {
      install = installBoonRarity, release = releaseBoonRarity, available = function() return true end,
      support = function() return type(GetRarityChances) == "function" and type(SetTraitsOnLoot) == "function" and type(GetEligibleUpgrades) == "function" end,
      active = function() return M.boonRarityEnabled and owns("GetRarityChances") and owns("SetTraitsOnLoot") end,
    },
  }
  statOrder = { "grasp", "dodge", "crit", "chargeSpeed", "moveSpeed", "sprintSpeed", "dashSpeed", "attackSpeed", "manaRegen", "enemyDamage", "enemyHealth" }
  statRegistry = {
    grasp = {
      install = installGraspLock, release = releaseGraspLock, min = 0, max = 999, integer = true, available = function() return true end,
      support = function() return type(GetMaxMetaUpgradeCost) == "function" end,
      value = function(_, support) if support.grasp then local ok,v=pcall(GetMaxMetaUpgradeCost); if ok and finite(v) then return v end end end,
    },
    dodge = {
      install = installDodgeLock, release = releaseDodgeLock, min = 0, max = 100,
      support = function() return type(GetTotalHeroTraitValue) == "function" and type(SetLifeProperty) == "function" end,
      value = function(hero) if M.statTargets.dodge ~= nil then return M.statTargets.dodge end local v=getDodgeRaw(hero); return finite(v) and v * 100 or nil end,
    },
    crit = {
      install = installCritLock, release = releaseCritLock, min = 0, max = 100,
      support = function() return type(CalculateCritChance) == "function" and type(GetTotalHeroTraitValue) == "function" end,
      value = function() return M.statTargets.crit end,
    },
    chargeSpeed = {
      install = installChargeSpeedLock, release = releaseChargeSpeedLock, min = 10, max = 1000,
      support = function() return type(SetPlayerAttackSpecialChargeSpeed) == "function" and type(RemovePlayerAttackSpecialChargeSpeed) == "function" end,
      value = function() return M.statTargets.chargeSpeed or 100 end,
    },
    moveSpeed = {
      install = installMoveSpeedLock, release = releaseMoveSpeedLock, min = 10, max = 1000,
      support = function() return type(SetUnitProperty) == "function" end,
      value = function(hero) return M.statTargets.moveSpeed or currentMoveSpeedPercent(hero) or 100 end,
    },
    sprintSpeed = {
      install = installSprintSpeedLock, release = releaseSprintSpeedLock, min = 10, max = 1000,
      support = function() return type(SetWeaponProperty) == "function" end,
      value = function(hero) return M.statTargets.sprintSpeed or currentSprintSpeedPercent(hero) or 100 end,
    },
    dashSpeed = {
      install = installDashSpeedLock, release = releaseDashSpeedLock, min = 10, max = 1000,
      support = function() return type(SetWeaponProperty) == "function" and type(GetBaseDataValue) == "function" and type(GetWeaponDataValue) == "function" end,
      value = function(hero) return M.statTargets.dashSpeed or currentDashSpeedPercent(hero) or 100 end,
    },
    attackSpeed = {
      install = installAttackSpeedLock, release = releaseAttackSpeedLock, min = 10, max = 1000,
      support = function() return type(ApplyUnitPropertyChanges) == "function" and type(WeaponData) == "table" and type(WeaponSets) == "table" and type(WeaponSets.HeroPrimarySecondaryWeapons) == "table" end,
      value = function(hero) return M.statTargets.attackSpeed or currentAttackSpeedPercent(hero) or 100 end,
    },
    manaRegen = {
      install = installManaRegenLock, release = releaseManaRegenLock, min = 0, max = 1000,
      support = function() return ready() and type(CurrentRun.Hero.ManaRegenSources) == "table" end,
      value = function(hero) return M.statTargets.manaRegen or currentTrainerManaRegen(hero) or 0 end,
    },
    enemyDamage = {
      install = installEnemyDamageLock, release = releaseEnemyDamageLock, min = 0, max = 1000,
      support = function() return type(Damage) == "function" end,
      value = function() return M.statTargets.enemyDamage or 100 end,
    },
    enemyHealth = {
      install = installEnemyHealthLock, release = releaseEnemyHealthLock, min = 10, max = 1000,
      support = function() return type(SetupUnit) == "function" and type(ActiveEnemies) == "table" end,
      value = function() return M.statTargets.enemyHealth or 100 end,
    },
  }

  local function featureAttempt(key, desired, install, release, raiseOnError)
    if not desired then
      release()
      M.featureErrors[key] = nil
      return true
    end
    if M.featureErrors[key] ~= nil and not raiseOnError then return false end
    local ok, message = pcall(install)
    if ok then
      M.featureErrors[key] = nil
      return true
    end
    pcall(release)
    M.featureErrors[key] = tostring(message)
    if raiseOnError then error(message) end
    return false
  end
  local function reconcileEconomy(raiseOnError)
    local desired = M.desiredFeatures.moneyMultiplierEnabled or M.desiredFeatures.resourceMultiplierEnabled
      or next(M.resourceLocks) ~= nil
    if not desired then
      releaseEconomyRuntime()
      M.featureErrors.economy = nil
      return true
    end
    if M.featureErrors.economy ~= nil and not raiseOnError then return false end
    local ok, message = pcall(function()
      installEconomy()
      M.moneyMultiplierEnabled = M.desiredFeatures.moneyMultiplierEnabled
      M.resourceMultiplierEnabled = M.desiredFeatures.resourceMultiplierEnabled
    end)
    if ok then M.featureErrors.economy = nil; return true end
    releaseEconomyRuntime()
    M.featureErrors.economy = tostring(message)
    if raiseOnError then error(message) end
    return false
  end
  local function reconcileStat(stat, raiseOnError)
    local entry = statRegistry[stat]
    if entry == nil then error("Unknown stat") end
    return featureAttempt("stat:" .. stat, M.statTargets[stat] ~= nil, entry.install, entry.release, raiseOnError)
  end
  reconcileDesired = function(raiseOnError, onlyKey)
    local allOk = true
    local function run(key, desired, entry)
      if onlyKey == nil or onlyKey == key then
        if desired and not featureAvailable(entry) then
          -- Desired state stays set, but the resident implementation is not
          -- mounted until its scene/Hero dependency becomes available.
          entry.release()
          M.featureErrors[key] = nil
        elseif not featureAttempt(key, desired, entry.install, entry.release, raiseOnError) then
          allOk = false
        end
      end
    end
    for _, key in ipairs(featureOrder) do
      local entry = featureRegistry[key]
      local desired = entry.desired and entry.desired() or M.desiredFeatures[key]
      run(key, desired, entry)
    end
    if onlyKey == nil or onlyKey == "moneyMultiplierEnabled" or onlyKey == "resourceMultiplierEnabled" or onlyKey == "economy" then
      if (M.desiredFeatures.moneyMultiplierEnabled or M.desiredFeatures.resourceMultiplierEnabled or next(M.resourceLocks) ~= nil) and not economyReady() then
        releaseEconomyRuntime(); M.featureErrors.economy = nil
      elseif not reconcileEconomy(raiseOnError) then allOk = false end
    end
    if onlyKey == nil or onlyKey == "rerolls" then
      if M.rerollsLock ~= nil and ready() then
        if not featureAttempt("rerolls", true, installRerolls, releaseRerollsRuntime, raiseOnError) then allOk = false end
      elseif M.rerollsLock ~= nil then
        releaseRerollsRuntime(); M.featureErrors.rerolls = nil
      else
        releaseRerollsRuntime(); M.featureErrors.rerolls = nil
      end
    end
    if onlyKey == nil or onlyKey == "nextRoomReward" then
      if M.nextRoomReward ~= nil then
        if not featureAttempt("nextRoomReward", true, installNextRoomReward, releaseNextRoomReward, raiseOnError) then allOk = false end
      else
        releaseNextRoomReward(); M.featureErrors.nextRoomReward = nil
      end
    end
    local availableStats = statAvailableMap(statSupport())
    for _, stat in ipairs(statOrder) do
      if onlyKey == nil or onlyKey == "stat:" .. stat then
        local entry = statRegistry[stat]
        if M.statTargets[stat] ~= nil and not availableStats[stat] then
          entry.release()
          M.featureErrors["stat:" .. stat] = nil
        elseif not reconcileStat(stat, raiseOnError) then allOk = false end
      end
    end
    if anyDesired() then
      local ok, message = pcall(installGuard)
      if ok then M.featureErrors.guard = nil
      else
        M.featureErrors.guard = tostring(message)
        allOk = false
        if raiseOnError then error(message) end
      end
    else
      M.featureErrors.guard = nil
    end
    return allOk
  end
  local function validateResource(id)
    requireResources()
    local _, _, allowed = resourceCatalog()
    if type(id) ~= "string" or not (allowed[id] or id == "Money") or type(ResourceData[id]) ~= "table" then
      error("Unknown or unsupported resource")
    end
  end
  local function integer(value, minimum)
    if not finite(value) or value % 1 ~= 0 or value < minimum or value > 999999 then
      error("Amount must be an integer " .. minimum .. "..999999")
    end
  end
  actionLedger = (function()
    local actionSemanticKeys = {
      set_resource = { "resource", "amount" },
      set_rerolls = { "amount" },
      open_sell_traits = {},
      set_trait_level = { "generationId", "runId", "instanceId", "trait", "family", "expectedLevel", "expectedRarity", "expectedSameNameCount", "targetLevel" },
      set_trait_rarity = { "generationId", "runId", "instanceId", "trait", "family", "expectedLevel", "expectedRarity", "expectedSameNameCount", "rarity" },
      remove_trait = { "generationId", "runId", "instanceId", "trait", "family", "expectedLevel", "expectedRarity", "expectedSameNameCount" },
      advance_trait_lifecycle = { "generationId", "runId", "instanceId", "trait", "family", "expectedLevel", "expectedRarity", "expectedSameNameCount" },
      open_special_choice = { "source" },
      spawn_reward = { "reward" },
    }
    local knownActionStatuses = { completed = true, accepted = true, opened = true, failed = true }
    local function actionFingerprint(command, params)
      local keys = actionSemanticKeys[command]
      if type(keys) ~= "table" then error("Action fingerprint is undefined for " .. tostring(command)) end
      local fingerprint = { command = command }
      for _, key in ipairs(keys) do fingerprint[key] = params[key] end
      return fingerprint
    end
    local function sameActionFingerprint(left, right)
      if type(left) ~= "table" or type(right) ~= "table" then return false end
      for key, value in pairs(left) do if right[key] ~= value then return false end end
      for key, value in pairs(right) do if left[key] ~= value then return false end end
      return true
    end
    local function actionReceipt(record, requestId, duplicate)
      return {
        requestId = requestId,
        command = record.command,
        outcome = record.status,
        duplicate = not not duplicate,
        error = record.error,
      }
    end
    local function publishActionReceipt(record)
      M.lastActionReceipt = actionReceipt(record, record.requestId, false)
    end
    local function action(command, params, work, preflight)
      local requestId = params.requestId
      if type(requestId) ~= "string" or #requestId == 0 or #requestId > 128 then
        error("Action requires a requestId of 1..128 characters")
      end
      local fingerprint = actionFingerprint(command, params)
      local prior = M.requests[requestId]
      if prior then
        if not sameActionFingerprint(prior.fingerprint, fingerprint) then
          error("requestId reused for a different action")
        end
        if not knownActionStatuses[prior.status] then
          error("MGT_OUTCOME_UNKNOWN: Previous action outcome is unknown; do not retry")
        end
        local result = state(params.includeCatalogs)
        local receipt = actionReceipt(prior, requestId, true)
        result.requestId, result.duplicate = requestId, true
        result.actionOutcome = receipt.outcome
        result.applied = receipt.outcome == "completed" or receipt.outcome == "opened"
        if receipt.error then result.actionError = receipt.error end
        if prior.lootObjectId then result.lootObjectId = prior.lootObjectId end
        return result
      end
      -- Deterministic validation belongs after request-id deduplication. A
      -- duplicate successful mutation must return its prior receipt even though
      -- the live target has since changed or disappeared.
      if preflight ~= nil then preflight() end
      local record = { requestId = requestId, command = command, fingerprint = fingerprint, status = "outcome_unknown" }
      M.requests[requestId] = record
      M.requestOrder[#M.requestOrder + 1] = requestId
      if #M.requestOrder > 128 then M.requests[table.remove(M.requestOrder, 1)] = nil end
      local ok, value, outcome = pcall(work, record)
      if not ok then
        record.status = "outcome_unknown"
        record.error = tostring(value)
        publishActionReceipt(record)
        error("MGT_OUTCOME_UNKNOWN: " .. record.error)
      end
      if record.status == "outcome_unknown" then record.status = outcome or "completed" end
      record.lootObjectId = value
      publishActionReceipt(record)
      local result = state(params.includeCatalogs)
      local receipt = actionReceipt(record, requestId, false)
      result.requestId, result.duplicate = requestId, false
      result.actionOutcome = receipt.outcome
      result.applied = receipt.outcome == "completed" or receipt.outcome == "opened"
      if receipt.error then result.actionError = receipt.error end
      if record.lootObjectId then result.lootObjectId = record.lootObjectId end
      return result
    end
    return {
      run = action,
      publish = publishActionReceipt,
      latestReceipt = function() return M.lastActionReceipt end,
    }
  end)()

  local function editResource(id, target)
    local current = number(GameState.Resources[id])
    if M.resourceLocks[id] ~= nil then M.resourceLocks[id] = target end
    local delta = target - current
    if delta == 0 then return end
    if resourceRunAccountingReady() and type(AddResource) == "function" and type(SpendResource) == "function" then
      local args = { Silent = true, SkipVoiceLines = true, SkipInventoryObjective = true,
        IgnoreAsLastResourceGained = true, SkipQuestStatusCheck = true, SkipResourceSpendPresentation = true }
      if delta > 0 then AddResource(id, delta, trainerSource, args)
      else SpendResource(id, -delta, trainerSource, args) end
    else
      -- The Crossroads can exist without CurrentRun.ResourcesGained/Spent.
      -- Native AddResource indexes those tables unconditionally, so use the
      -- save-backed resource fields directly and keep lifetime accounting
      -- coherent rather than fabricating a fake run.
      GameState.Resources[id] = target
      if delta > 0 then
        GameState.LifetimeResourcesGained[id] = number(GameState.LifetimeResourcesGained[id]) + delta
      else
        GameState.LifetimeResourcesSpent = GameState.LifetimeResourcesSpent or {}
        GameState.LifetimeResourcesSpent[id] = number(GameState.LifetimeResourcesSpent[id]) - delta
      end
    end
    if number(GameState.Resources[id]) ~= target then error("Resource setter did not reach the requested amount") end
    if id == "Money" then refreshMoney() end
  end
  local function editVital(vital, field, value)
    if not ready() then error("Game scene does not expose vital editing") end
    if not finite(value) or value < 0 or value > 999999 then error("Vital value must be 0..999999") end
    if vital ~= "health" and vital ~= "mana" and vital ~= "armor" then error("Unknown vital") end
    if field ~= "current" and field ~= "max" then error("Unknown vital field") end
    local hero = CurrentRun.Hero
    if vital == "health" then
      requireFunctions("health editing", { "UpdateHealthUI" })
      if field == "max" then
        if value < 1 then error("Maximum health must be at least 1") end
        hero.MaxHealth = value
        if number(hero.Health) > value then hero.Health = value end
        if number(hero.Health) < 1 then hero.Health = 1 end
      else
        if value < 1 then error("Current health must be at least 1") end
        hero.Health = math.min(value, number(hero.MaxHealth))
      end
      if type(M.vitalLocks.health) == "table" then M.vitalLocks.health[field] = field == "current" and hero.Health or hero.MaxHealth end
      refreshHealth()
      return
    end
    if vital == "mana" then
      requireFunctions("mana editing", { "UpdateWeaponMana", "UpdateManaMeterUI" })
      if field == "max" then
        hero.MaxMana = value
        local available = value
        if type(GetHeroMaxAvailableMana) == "function" then
          local ok, result = pcall(GetHeroMaxAvailableMana)
          if ok and finite(result) then available = result end
        end
        if number(hero.Mana) > available then hero.Mana = math.max(0, available) end
      else
        local available = number(hero.MaxMana)
        if type(GetHeroMaxAvailableMana) == "function" then
          local ok, result = pcall(GetHeroMaxAvailableMana)
          if ok and finite(result) then available = result end
        end
        hero.Mana = math.min(value, math.max(0, available))
      end
      if type(M.vitalLocks.mana) == "table" then M.vitalLocks.mana[field] = field == "current" and hero.Mana or hero.MaxMana end
      refreshMana()
      return
    end
    -- Armor/HealthBuffer is a temporary pool, not a user-facing current/max
    -- pair. Keep only its current amount in the trainer. MaxHealthBuffer may be
    -- raised internally so the engine can hold a requested larger buffer, but
    -- it is neither displayed nor locked as an independent stat.
    if field ~= "current" then error("Armor exposes only a current value") end
    local maximum = number(hero.MaxHealthBuffer)
    if value > maximum then hero.MaxHealthBuffer = value; maximum = value end
    hero.HealthBuffer = math.min(value, maximum)
    if type(M.vitalLocks.armor) == "table" then M.vitalLocks.armor.current = number(hero.HealthBuffer) end
    refreshHealth()
  end
  function M.dispatch(command, params)
    synchronize()
    params = params or {}
    if type(params) ~= "table" then error("Parameters must be a table") end
    if command == "status" then return state(params.includeCatalogs) end
    if command == "cleanup" or command == "disable_all" then
      local hadMana = M.infiniteMana
      disable()
      if hadMana and ready() and type(UpdateWeaponMana) == "function" and type(UpdateManaMeterUI) == "function" then refreshMana() end
      return state(params.includeCatalogs)
    end
    if command == "set_vital" then
      editVital(params.vital, params.field, params.value)
      return state(params.includeCatalogs)
    end
    if command == "set_counter" then
      if not ready() then error("Game scene does not expose counter editing") end
      if params.counter ~= "spellCharge" then error("Unknown counter") end
      if not finite(params.value) or params.value < 0 or params.value > 999999 then error("Counter value must be 0..999999") end
      CurrentRun.SpellCharge = params.value
      if type(UpdateSpellActiveStatus) == "function" then pcall(UpdateSpellActiveStatus) end
      -- If the always-ready feature is desired, its invariant wins on the next
      -- guard pass; setting a lower value while it is enabled is therefore
      -- intentionally temporary.
      return state(params.includeCatalogs)
    end
    if command == "lock_vital" then
      if not ready() then error("Game scene does not expose vital locking") end
      if params.vital ~= "health" and params.vital ~= "mana" and params.vital ~= "armor" then error("Unknown vital") end
      if type(params.locked) ~= "boolean" then error("locked must be boolean") end
      if params.locked then
        local hero = CurrentRun.Hero
        if params.vital == "health" then M.vitalLocks.health = { current = number(hero.Health), max = number(hero.MaxHealth) }
        elseif params.vital == "mana" then M.vitalLocks.mana = { current = number(hero.Mana), max = number(hero.MaxMana) }
        else M.vitalLocks.armor = { current = number(hero.HealthBuffer) } end
        installGuard()
      else M.vitalLocks[params.vital] = nil end
      if not anyDesired() and not anyRuntimeActive() then releaseGuard() end
      return state(params.includeCatalogs)
    end
    if command == "set_element" or command == "lock_element" then
      if not ready() or type(CurrentRun.Hero.Elements) ~= "table" then error("Elements are unavailable") end
      local element = params.element
      if type(element) ~= "string" or (type(TraitElementData) == "table" and TraitElementData[element] == nil) then error("Unknown element") end
      if command == "set_element" then
        integer(params.amount, 0)
        CurrentRun.Hero.Elements[element] = params.amount
        if M.elementLocks[element] ~= nil then M.elementLocks[element] = params.amount end
        refreshHighestElementCount()
        if type(CheckActivatedTraits) == "function" then pcall(CheckActivatedTraits, CurrentRun.Hero, { SkipPresentation = true }) end
      else
        if type(params.locked) ~= "boolean" then error("locked must be boolean") end
        if params.locked then M.elementLocks[element] = number(CurrentRun.Hero.Elements[element]); installGuard()
        else M.elementLocks[element] = nil end
      end
      if not anyDesired() and not anyRuntimeActive() then releaseGuard() end
      return state(params.includeCatalogs)
    end
    if command == "set_stat" then
      local stat, locked, value = params.stat, params.locked, params.value
      local entry = statRegistry[stat]
      if entry == nil then error("Unknown stat") end
      if type(locked) ~= "boolean" then error("locked must be boolean") end
      if locked then
        if not finite(value) then error("Stat value must be finite") end
        if entry.integer and value % 1 ~= 0 then error("Stat value must be an integer") end
        if value < entry.min or value > entry.max then error("Stat value is outside the supported range") end
        local support = statSupport()
        if not support[stat] then error("Stat is unavailable in this game build") end
        local available = statAvailableMap(support)
        if not available[stat] then error("Stat is unavailable in the current scene") end
        M.statTargets[stat] = value
      else
        M.statTargets[stat] = nil
        entry.release()
      end
      M.featureErrors["stat:" .. stat] = nil
      reconcileDesired(true, "stat:" .. stat)
      if anyDesired() then installGuard() elseif not anyRuntimeActive() then releaseGuard() end
      return state(params.includeCatalogs)
    end
    if command == "set_next_room_reward" then
      local reward, token = params.reward, params.token
      if reward ~= nil and type(reward) ~= "string" then error("Next room reward must be a string or nil") end
      if reward == "" then reward = nil end
      if reward ~= nil then
        if type(token) ~= "string" or #token == 0 or #token > 128 then error("Next room reward token is invalid") end
        local validDirect = reward == "RoomMoneyDrop" or reward == "MetaCurrencyDrop" or reward == "MetaCardPointsCommonDrop"
          or reward == "MemPointsCommonDrop" or reward == "MaxHealthDrop" or reward == "MaxManaDrop"
          or reward == "StackUpgrade" or reward == "WeaponUpgrade" or reward == "HermesUpgrade"
        local validLoot = type(LootData) == "table" and type(LootData[reward]) == "table"
        if not validDirect and not validLoot then error("Unsupported next room reward") end
        M.nextRoomReward = reward
        M.nextRoomRewardToken = token
      else
        M.nextRoomReward = nil
        M.nextRoomRewardToken = nil
      end
      M.featureErrors.nextRoomReward = nil
      reconcileDesired(true, "nextRoomReward")
      if anyDesired() then installGuard() elseif not anyRuntimeActive() then releaseGuard() end
      return state(params.includeCatalogs)
    end
    if command == "set_boon_rarity" then
      local target = params.target or M.boonRarityTarget
      local multiplier = params.multiplier or (M.boonRarityMultiplier * 100)
      if target ~= "Common" and target ~= "Rare" and target ~= "Epic" and target ~= "Heroic" then error("Unknown boon rarity target") end
      if not finite(multiplier) or multiplier < 0 or multiplier > 1000 then error("Rarity multiplier must be 0..1000 percent") end
      if params.forceLegendary ~= nil and type(params.forceLegendary) ~= "boolean" then error("forceLegendary must be boolean") end
      if params.forceDuo ~= nil and type(params.forceDuo) ~= "boolean" then error("forceDuo must be boolean") end
      M.boonRarityTarget = target
      M.boonRarityMultiplier = multiplier / 100
      if params.forceLegendary ~= nil then M.boonForceLegendary = params.forceLegendary end
      if params.forceDuo ~= nil then M.boonForceDuo = params.forceDuo end
      if M.desiredFeatures.boonRarityEnabled and ready() then reconcileDesired(true, "boonRarityEnabled") end
      return state(params.includeCatalogs)
    end
    if command == "set_feature" then
      local feature, value = params.feature, params.value
      if feature == "damageMultiplier" or feature == "moneyMultiplier" or feature == "resourceMultiplier" then
        if not finite(value) or value < 1 or value > 100 then error("Multiplier must be 1..100") end
        M[feature] = value
        return state(params.includeCatalogs)
      end
      if type(value) ~= "boolean" then error("Feature value must be boolean") end
      if M.desiredFeatures[feature] == nil then error("Unknown feature") end
      local previous = M.desiredFeatures[feature]
      M.desiredFeatures[feature] = value
      M.featureErrors[feature] = nil
      if feature == "moneyMultiplierEnabled" or feature == "resourceMultiplierEnabled" then M.featureErrors.economy = nil end
      if not value then
        local entry = featureRegistry[feature]
        if entry ~= nil then entry.release()
        elseif feature == "moneyMultiplierEnabled" then M.moneyMultiplierEnabled = false
        elseif feature == "resourceMultiplierEnabled" then M.resourceMultiplierEnabled = false end
        if feature == "infiniteMana" and ready() then refreshMana() end
      end
      local ok, message = pcall(function() reconcileDesired(true, feature) end)
      if not ok then
        M.desiredFeatures[feature] = previous
        M.featureErrors[feature] = nil
        if feature == "moneyMultiplierEnabled" or feature == "resourceMultiplierEnabled" then M.featureErrors.economy = nil end
        reconcileDesired(false, feature)
        error("Feature unavailable: " .. tostring(message))
      end
      if anyDesired() then installGuard()
      elseif not anyRuntimeActive() then releaseGuard() end
      return state(params.includeCatalogs)
    end
    if command == "lock_resource" then
      if not resourceReady() then error("Game scene does not expose resource editing") end
      validateResource(params.resource)
      if type(params.locked) ~= "boolean" then error("locked must be boolean") end
      if params.locked then
        if params.resource == "Money" then requireFunctions("money lock", { "UpdateMoneyUI" }) end
        M.resourceLocks[params.resource] = number(GameState.Resources[params.resource])
        installEconomy()
        M.moneyMultiplierEnabled = M.desiredFeatures.moneyMultiplierEnabled
        M.resourceMultiplierEnabled = M.desiredFeatures.resourceMultiplierEnabled
        installGuard()
      else
        M.resourceLocks[params.resource] = nil
        if not M.desiredFeatures.moneyMultiplierEnabled and not M.desiredFeatures.resourceMultiplierEnabled and not next(M.resourceLocks) then
          releaseEconomyRuntime()
        end
      end
      if not anyDesired() and not anyRuntimeActive() then releaseGuard() end
      return state(params.includeCatalogs)
    end
    if command == "lock_rerolls" then
      if not ready() then error("Game scene does not expose rerolls") end
      if type(params.locked) ~= "boolean" then error("locked must be boolean") end
      if params.locked then
        if not finite(CurrentRun.NumRerolls) then error("Unsupported rerolls: counter unavailable") end
        installRerolls()
        M.rerollsLock = CurrentRun.NumRerolls
        installGuard()
      else M.rerollsLock = nil; releaseRerollsRuntime() end
      if not anyDesired() and not anyRuntimeActive() then releaseGuard() end
      return state(params.includeCatalogs)
    end
    if command == "set_resource" then
      if not resourceReady() then error("Game scene does not expose resource editing") end
      validateResource(params.resource)
      integer(params.amount, 0)
      if params.resource == "Money" and type(UpdateMoneyUI) ~= "function" then error("Unsupported money editing: missing UpdateMoneyUI") end
      return actionLedger.run(command, params, function() editResource(params.resource, params.amount) end)
    end
    if command == "set_rerolls" then
      if not ready() then error("Game scene does not expose rerolls") end
      integer(params.amount, 0)
      requireFunctions("reroll editing", { "UpdateRerollUI", "ShowRerollUI" })
      if not finite(CurrentRun.NumRerolls) then error("Unsupported rerolls: counter unavailable") end
      return actionLedger.run(command, params, function()
        if M.rerollsLock ~= nil then M.rerollsLock = params.amount end
        CurrentRun.NumRerolls = params.amount
        ShowRerollUI()
        UpdateRerollUI(params.amount)
      end)
    end
    if command == "set_trait_level" then
      local function validateLevelTarget()
        local target, family, sellEligible, count = traitManagement.resolveTarget(params)
        integer(params.targetLevel, 1)
        if params.targetLevel <= traitManagement.level(target) then
          error("Trait target level must be higher than the current level")
        end
        local levelCapability = traitManagement.capabilities(target, family, sellEligible, count)
        if levelCapability ~= "increaseOne" then
          error("Trait level editing is unavailable for the selected target")
        end
        if family == "chaos" then
          requireFunctions("Chaos trait level editing", { "GetProcessedTraitData", "RemoveTraitData", "AddTraitToHero", "DeepCopyTable" })
        elseif family == "hexTalent" then
          local delta = params.targetLevel - traitManagement.level(target)
          if #traitManagement.seleneTalentNodes(target.Name, false) < delta then
            error("Not enough uninvested Path of Stars nodes remain for the requested level")
          end
          requireFunctions("Selene talent level editing", {
            "IncreaseTraitLevel", "UpdateTalentPointInvestedCache",
          })
          local base = type(TraitData) == "table" and TraitData[target.Name] or nil
          if type(base) == "table" and type(base.AcquireFunctionName) == "string" then
            requireFunctions("Selene talent acquire callback", { "CallFunctionName" })
          end
        -- Ordinary God boons are re-checked against the game's real Pom
        -- eligibility. The explicit direct strategy is the only bypass.
        elseif not traitManagement.hasDirectStrategy(target.Name) then
          requireFunctions("trait level editing", { "GetAllUpgradeableGodTraits", "IncreaseTraitLevel" })
          local ok, eligible = pcall(GetAllUpgradeableGodTraits, 1)
          if not ok or type(eligible) ~= "table" or not eligible[target.Name] then
            error("Trait is no longer eligible for a meaningful level increase")
          end
        else
          requireFunctions("trait level editing", { "IncreaseTraitLevel" })
        end
        return target, family
      end
      return actionLedger.run(command, params, function()
        -- Resolve again immediately before the mutation, after the deterministic
        -- preflight and after action() has ruled out a duplicate request.
        local live, family = validateLevelTarget()
        local upgraded
        if family == "chaos" then
          upgraded = traitManagement.rebuildChaosTarget(live, params.targetLevel, nil)
        elseif family == "hexTalent" then
          local before = traitManagement.level(live)
          local delta = params.targetLevel - before
          local nodes = traitManagement.seleneTalentNodes(live.Name, false)
          local base = type(TraitData) == "table" and TraitData[live.Name] or nil
          upgraded = live
          for index = 1, delta do
            local selected = nodes[index] and nodes[index].node or nil
            if type(selected) ~= "table" then
              error("Selene talent tree changed before the requested level was applied")
            end
            selected.Invested = true
            selected.QueuedInvested = nil
            local beforeStep = traitManagement.level(upgraded)
            local ok, nextTrait = pcall(IncreaseTraitLevel, upgraded)
            local liveStep = traitManagement.level(upgraded)
            if not ok then
              if liveStep == beforeStep then
                selected.Invested = false
                selected.QueuedInvested = nil
              end
              UpdateTalentPointInvestedCache()
              error(nextTrait)
            end
            if type(nextTrait) ~= "table" or traitManagement.level(nextTrait) <= beforeStep then
              if liveStep == beforeStep then
                selected.Invested = false
                selected.QueuedInvested = nil
              end
              UpdateTalentPointInvestedCache()
              error("Trait level increase did not reach the requested target level")
            end
            upgraded = nextTrait
            if type(base) == "table" and type(base.AcquireFunctionName) == "string" then
              CallFunctionName(base.AcquireFunctionName, base.AcquireFunctionArgs, upgraded)
            end
          end
          UpdateTalentPointInvestedCache()
        else
          local before = traitManagement.level(live)
          local delta = params.targetLevel - before
          upgraded = IncreaseTraitLevel(live, delta)
        end
        if type(upgraded) ~= "table" or traitManagement.level(upgraded) ~= params.targetLevel then
          error("Trait level increase did not reach the requested target level")
        end
      end, validateLevelTarget)
    end
    if command == "set_trait_rarity" then
      local function validateRarityTarget()
        local target, family, sellEligible, count = traitManagement.resolveTarget(params)
        local _, _, rarityCapability = traitManagement.capabilities(target, family, sellEligible, count)
        local rarities = traitManagement.availableRarities(target)
        if rarityCapability ~= "setExact" or not traitManagement.targetHasRarity(rarities, params.rarity)
            or params.rarity == traitManagement.rarity(target) then
          error("Trait rarity editing is unavailable for the selected target")
        end
        if family == "chaos" then
          requireFunctions("Chaos trait rarity editing", { "GetProcessedTraitData", "RemoveTraitData", "AddTraitToHero", "DeepCopyTable" })
        elseif family == "hexTalent" then
          requireFunctions("Selene talent rarity editing", { "AddRarityToTraits" })
        else
          requireFunctions("trait rarity editing", { "AddRarityToTraits" })
        end
        return target, family
      end
      return actionLedger.run(command, params, function()
        local live, family = validateRarityTarget()
        local upgraded
        if family == "chaos" then
          upgraded = traitManagement.rebuildChaosTarget(live, nil, params.rarity)
        else
          upgraded = AddRarityToTraits({}, {
            NumTraits = 1,
            ForceUpgrade = { live },
            TargetRarityName = params.rarity,
            Silent = true,
          })
        end
        if type(upgraded) ~= "table" or upgraded.Rarity ~= params.rarity then
          error("Trait rarity recompute did not reach the requested rarity")
        end
      end, validateRarityTarget)
    end
    if command == "remove_trait" then
      local function validateRemovalTarget()
        local target, family, sellEligible, count = traitManagement.resolveTarget(params)
        local _, _, _, _, removalCapability = traitManagement.capabilities(target, family, sellEligible, count)
        if removalCapability == "none" then
          error("Trait removal is unavailable for the selected target")
        end
        if removalCapability == "nameLevelAllMatching" then
          requireFunctions("native trait removal", { "RemoveWeaponTrait" })
        elseif removalCapability == "singleInstanceForce" and family == "hex" then
          requireFunctions("Selene spell removal", {
            "HeroHasTrait", "RemoveTrait", "UnequipWeapon", "UpdateTalentPointInvestedCache",
          })
        elseif removalCapability == "singleInstanceForce" and family == "hexTalent" then
          requireFunctions("Selene talent removal", {
            "RemoveTraitData", "UpdateTalentPointInvestedCache",
          })
        elseif removalCapability == "singleInstanceForce" and family == "hammer" then
          requireFunctions("Hammer trait removal", { "RemoveTraitData" })
          if type(live) == "table" and type(live.PreEquipWeapons) == "table"
              and next(live.PreEquipWeapons) ~= nil then
            requireFunctions("Hammer helper weapon removal", { "UnequipWeapon" })
          end
        elseif removalCapability == "singleInstanceForce" then
          requireFunctions("direct trait removal", { "RemoveTraitData" })
        else
          error("Trait removal capability is unknown")
        end
        return target, removalCapability, family
      end
      return actionLedger.run(command, params, function()
        local live, removalCapability, family = validateRemovalTarget()
        if removalCapability == "nameLevelAllMatching" then
          -- Native SellTraits teardown: deliberately name-level/all-matching.
          RemoveWeaponTrait(live.Name, { Silent = true })
          for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
            if type(trait) == "table" and trait.Name == live.Name then
              error("Native trait removal left a matching instance mounted")
            end
          end
        elseif family == "hex" then
          traitManagement.teardownSlottedSpell()
          local slotted = seleneModel.currentSpell()
          if type(slotted) == "table" or HeroHasTrait(live.Name) then
            error("Selene spell removal left owner state mounted")
          end
        elseif family == "hammer" then
          hammerModel.removeMounted(live)
        elseif family == "hexTalent" then
          local ok, removalError = pcall(
            RemoveTraitData, CurrentRun.Hero, live, { Silent = true, SkipExpire = true }
          )
          local stillMounted = false
          for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
            if type(trait) == "table" and trait.Name == live.Name then
              stillMounted = true
              break
            end
          end
          if not stillMounted then
            for _, nodeEntry in ipairs(traitManagement.seleneTalentNodes(live.Name, true)) do
              nodeEntry.node.Invested = false
              nodeEntry.node.QueuedInvested = nil
            end
            UpdateTalentPointInvestedCache()
          end
          if not ok then error(removalError) end
          if stillMounted then error("Selene talent removal left the mounted effect present") end
        else
          -- Bounded object-level force removal for an audited declarative trait.
          -- SkipExpire prevents a one-shot/reward expiration path from firing;
          -- directStrategySafe() refuses traits with such a lifecycle anyway.
          RemoveTraitData(CurrentRun.Hero, live, { Silent = true, SkipExpire = true })
          for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
            if type(trait) == "table" and trait.Id ~= nil and tostring(trait.Id) == params.instanceId then
              error("Direct trait removal left the selected instance mounted")
            end
          end
        end
      end, validateRemovalTarget)
    end
    if command == "advance_trait_lifecycle" then
      local function validateChaosAdvance()
        local target, family = traitManagement.resolveTarget(params)
        if family ~= "chaos" or traitManagement.chaosLifecycleState(target) ~= "curse"
            or traitManagement.chaosLinkedTraitName(target) == "" then
          error("Chaos lifecycle transition is unavailable")
        end
        requireFunctions("Chaos lifecycle transition", { "RemoveTraitData" })
        return target, traitManagement.chaosLinkedTraitName(target)
      end
      return actionLedger.run(command, params, function()
        local live, linkedName = validateChaosAdvance()
        RemoveTraitData(CurrentRun.Hero, live, { Silent = true })
        local replacement = nil
        for _, trait in ipairs(CurrentRun.Hero.Traits or {}) do
          if type(trait) == "table" and trait.Id ~= nil
              and tostring(trait.Id) == params.instanceId then
            replacement = trait
            break
          end
        end
        if type(replacement) ~= "table" or replacement.Name ~= linkedName
            or traitManagement.chaosLifecycleState(replacement) ~= "blessing" then
          error("Chaos lifecycle transition failed")
        end
      end, validateChaosAdvance)
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

          local priorityOptions, eligibleOptions = {}, {}
          for _, option in pairs(choiceData.UpgradeOptions) do
            local traitAvailable = type(option) == "table" and
              (option.Type ~= "Trait" or
                (type(option.ItemName) == "string"
                  and type(TraitData[option.ItemName]) == "table"
                  and not HeroHasTrait(option.ItemName)
                  and (type(CurrentRun.PickedTraits) ~= "table" or not CurrentRun.PickedTraits[option.ItemName])))
            if type(option) == "table" and traitAvailable
                and (option.GameStateRequirements == nil or IsGameStateEligible(source, option.GameStateRequirements)) then
              local candidate = ShallowCopyTable(option)
              if definition.rarity ~= nil then candidate.Rarity = definition.rarity end
              if candidate.PriorityRequirements ~= nil and IsGameStateEligible(source, candidate.PriorityRequirements) then
                priorityOptions[#priorityOptions + 1] = candidate
              else
                eligibleOptions[#eligibleOptions + 1] = candidate
              end
            end
          end
          if #priorityOptions + #eligibleOptions == 0 then error("No eligible special blessings are available") end

          source.UpgradeOptions = {}
          for _ = 1, 3 do
            local option = nil
            if #priorityOptions > 0 then
              option = RemoveRandomValue(priorityOptions)
              if option ~= nil then option.SlotEntranceAnimation = option.PrioritySlotEntranceAnimation end
            elseif #eligibleOptions > 0 then
              option = RemoveRandomValue(eligibleOptions)
              if option ~= nil and definition.rarity == nil and option.Rarity
                  and #eligibleOptions > 0 and not PassRarityCheck(option.Rarity) then
                option = RemoveRandomValue(eligibleOptions)
              end
            end
            if option ~= nil then source.UpgradeOptions[#source.UpgradeOptions + 1] = option end
          end

          if CurrentRun.IsDreamRun and type(TraitRarityData) == "table"
              and type(TraitRarityData.RarityUpgradeOrder) == "table" then
            for _, option in ipairs(source.UpgradeOptions) do
              option.Rarity = TraitRarityData.RarityUpgradeOrder[CurrentRun.EnteredBiomes] or option.Rarity
            end
          end

          if definition.circe then
            for _, option in ipairs(source.UpgradeOptions) do
              if option.ItemName == "DoubleFamiliarTrait" then
                local familiarTrait = nil
                for _, traitData in ipairs(CurrentRun.Hero.Traits or {}) do
                  if traitData.FamiliarTrait then familiarTrait = traitData; break end
                end
                if familiarTrait == nil then error("Circe familiar choice requires an active familiar trait") end
                local rarity = option.Rarity or "Common"
                local rarityLevels = type(TraitData.DoubleFamiliarTrait) == "table"
                  and TraitData.DoubleFamiliarTrait.RarityLevels or nil
                local rarityData = type(rarityLevels) == "table" and rarityLevels[rarity] or nil
                if type(rarityData) ~= "table" or not finite(rarityData.Multiplier) then
                  error("Circe familiar choice rarity data is unavailable")
                end
                SetTraitTextData(familiarTrait)
                SessionMapState.OldFamiliarTrait = familiarTrait
                local multiplier = rarityData.Multiplier + 1
                local bonusStacks = type(TraitData[familiarTrait.Name]) == "table"
                  and (TraitData[familiarTrait.Name].CirceBonusStacks or 0) or 0
                local newFamiliarTrait = GetProcessedTraitData({
                  Unit = CurrentRun.Hero, TraitName = familiarTrait.Name,
                  StackNum = (familiarTrait.StackNum or 1) * multiplier + bonusStacks * (multiplier - 1),
                })
                SetTraitTextData(newFamiliarTrait)
                SessionMapState.NewFamiliarTrait = newFamiliarTrait
                if familiarTrait.FamiliarLastStandHealAmount ~= nil then
                  SessionMapState.OldFamiliarTrait.ExtractData.TooltipLastStandAmount = 1
                  SessionMapState.NewFamiliarTrait.ExtractData.TooltipLastStandAmount = multiplier
                end
                if type(TraitData[familiarTrait.Name]) == "table"
                    and TraitData[familiarTrait.Name].CirceStatLine then
                  SessionMapState.StatLine = TraitData[familiarTrait.Name].CirceStatLine
                end
              end
            end
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
    if command == "spawn_reward" then
      if not ready() or sceneName() ~= "run" then error("Reward spawning requires an active run room") end
      local _, allowed = rewards()
      local rewardId = params.reward
      local entry = type(rewardId) == "string" and allowed[rewardId] or nil
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
        if entry.acquisitionMode == "direct" or entry.acquisitionMode == "costume" then
          requireFunctions("exact special boon acquisition", { "AddTraitToHero" })
          if entry.acquisitionMode == "costume" then
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
end
