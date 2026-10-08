"""Native Save Editor identities, generated from Hades II 1.143476 / Steam 25481925.

QuestData.lua SHA-256 df9888d6586e0f8644e31db093bf35452bc3ac057d0f144be2f2f1e8d1e64336
ResourceData.lua SHA-256 94b2dc9edc22c34b213ab78dea42f2dc76c80cbcfde14104cbe772b254a29b03
ObjectiveData.lua SHA-256 e635ef5c05ba8a22e4af4ed3d4290ec20d31c0bd95c1aff9e8b1ac828940c816
NPCData*.lua bundle SHA-256 8e632ee4e2f6f1bb5eaa87e8c15154c556dc62e733654bebae9bebf0b0f94ec0
Quest IDs come from QuestOrderData; resources are top-level ResourceData entries
excluding abstract Base* templates. Recheck these IDs on target-build changes.
"""

QUEST_IDS = frozenset((
    "QuestRescueFatesTrue", "QuestHelpOdysseus", "QuestHelpDora", "QuestHelpArachne", "QuestHelpNarcissusAndEcho",
    "QuestWakeHypnos", "QuestFirstSurfaceClear", "QuestFirstUnderworldClear", "QuestUnlockMoros", "QuestBeatHecate",
    "QuestBeatHecateWithoutArcana", "QuestBeatTyphonWithWeapons", "QuestBeatChronosWithArcana", "QuestMeetShrineAltBosses", "QuestClearedWithAllAspects",
    "QuestClearedWithAllFamiliars", "QuestCollectDreamPoints", "QuestDreamClearedWithAllWeapons", "QuestDreamClearedWithShrinePoints", "QuestMeetOlympians",
    "QuestUnlockBountyBoard", "QuestHelpMedea", "QuestHelpCirce", "QuestDeliverAnubisAspect", "QuestDeliverMorriganAspect",
    "QuestDeliverSupayAspect", "QuestDeliverNergalAspect", "QuestDeliverHelAspect", "QuestDeliverShivaAspect", "QuestMeetCyclopsWithOdysseusKeepsake",
    "QuestChaosKeepsakeFullRun", "QuestRandomBountyClearStreak", "QuestGiftNectar", "QuestMemLevel10", "QuestUnlockDagger",
    "QuestUnlockAllWeapons", "QuestUnlockAllWeaponAspects", "QuestMaxWeaponUpgrade", "QuestMaxCardUpgrade", "QuestPetFrog",
    "QuestPurchasePinnedItems", "QuestCauldronSpellsSmall", "QuestClearBountiesSmall", "QuestUnlockAllCards", "QuestSpendCharonPoints",
    "QuestWellShopItems", "QuestRecruitFamiliars", "QuestUpgradeFamiliars", "QuestCatchFish", "QuestCodexSmall",
    "QuestToolsUnlocks", "QuestToolsUpgrades", "QuestCosmeticsSmall", "QuestShadeMercRecruits", "QuestMiniBossKills",
    "QuestMiniBossKillsSurface", "QuestDarkSorceries", "QuestSeleneDuos", "QuestHadesUpgrades", "QuestZeusUpgrades",
    "QuestHeraUpgrades", "QuestPoseidonUpgrades", "QuestDemeterUpgrades", "QuestApolloUpgrades", "QuestAphroditeUpgrades",
    "QuestHephaestusUpgrades", "QuestHestiaUpgrades", "QuestAresUpgrades", "QuestArtemisUpgrades", "QuestHermesUpgrades",
    "QuestAthenaUpgrades", "QuestDionysusUpgrades", "QuestChaosCurses", "QuestChaosBlessings", "QuestLegendaryUpgrades",
    "QuestSynergyUpgrades", "QuestArachneUpgrades", "QuestNarcissusUpgrades", "QuestEchoUpgrades", "QuestMedeaCurses",
    "QuestCirceUpgrades", "QuestIcarusUpgrades", "QuestEliteAttributeKills", "QuestStaffHammerUpgrades", "QuestDaggerHammerUpgrades",
    "QuestTorchHammerUpgrades", "QuestAxeHammerUpgrades", "QuestLobHammerUpgrades", "QuestSuitHammerUpgrades",
))

RESOURCE_IDS = frozenset((
    "MixerFBoss", "MixerGBoss", "MixerHBoss", "MixerIBoss", "MixerNBoss",
    "MixerOBoss", "MixerPBoss", "MixerQBoss", "CosmeticsPoints", "PlantFMoly",
    "PlantGLotus", "PlantHMyrtle", "PlantIShaderot", "PlantNMoss", "PlantODriftwood",
    "PlantPIris", "PlantQFang", "PlantFNightshadeSeed", "PlantFNightshade", "PlantGCattailSeed",
    "PlantGCattail", "PlantHWheatSeed", "PlantHWheat", "PlantIPoppySeed", "PlantIPoppy",
    "PlantNGarlicSeed", "PlantNGarlic", "PlantOMandrakeSeed", "PlantOMandrake", "PlantPOliveSeed",
    "PlantPOlive", "PlantQSnakereedSeed", "PlantQSnakereed", "PlantChaosThalamusSeed", "PlantChaosThalamus",
    "SeedMystery", "OreFSilver", "OreGLime", "OreHGlassrock", "OreIMarble",
    "OreNBronze", "OreOIron", "OrePAdamant", "OreQScales", "OreChaosProtoplasm",
    "MetaCurrency", "MetaCardPointsCommon", "MemPointsCommon", "MetaFabric", "CardUpgradePoints",
    "GiftPoints", "GiftPointsRare", "GiftPointsEpic", "HypnosPoints", "MedeaPoints",
    "IcarusPoints", "HadesSpearPoints", "DeathAreaPoints", "FishFCommon", "FishFRare",
    "FishFLegendary", "FishGCommon", "FishGRare", "FishGLegendary", "FishHCommon",
    "FishHRare", "FishHLegendary", "FishICommon", "FishIRare", "FishILegendary",
    "FishNCommon", "FishNRare", "FishNLegendary", "FishOCommon", "FishORare",
    "FishOLegendary", "FishPCommon", "FishPRare", "FishPLegendary", "FishQCommon",
    "FishQRare", "FishQLegendary", "FishChaosCommon", "FishChaosRare", "FishChaosLegendary",
    "WeaponPointsRare", "Mixer5Common", "Mixer6Common", "MixerShadow", "MixerMythic",
    "FamiliarPoints", "MysteryResource", "SuperGiftPoints", "CharonPoints", "GemPoints",
    "DreamPoints", "TrashPoints",
))

NPC_INTERACTION_IDS = frozenset((
    "NPC_Achilles_01", "NPC_Apollo_Story_01", "NPC_Arachne_01", "NPC_Arachne_Home_01", "NPC_Artemis_01",
    "NPC_Artemis_Field_01", "NPC_Athena_01", "NPC_Bouldy_01", "NPC_Cerberus_Field_01", "NPC_Cerberus_Story_01",
    "NPC_Charon_01", "NPC_Chronos_01", "NPC_Chronos_02", "NPC_Chronos_Story_01", "NPC_Circe_01",
    "NPC_Demeter_Story_01", "NPC_Dionysus_01", "NPC_Dora_01", "NPC_Echo_01", "NPC_Eris_01",
    "NPC_Hades_02", "NPC_Hades_Field_01", "NPC_Hades_Story_01", "NPC_Hecate_01", "NPC_Hecate_Story_01",
    "NPC_Hera_Story_01", "NPC_Heracles_01", "NPC_Hermes_01", "NPC_HorseAndChariot_01", "NPC_Hypnos_01",
    "NPC_Hypnos_02", "NPC_Hypnos_03", "NPC_Hypnos_04", "NPC_Hypnos_DreamRun", "NPC_Icarus_01",
    "NPC_LeopardGuest", "NPC_Medea_01", "NPC_Melinoe_Story_01", "NPC_Moros_01", "NPC_Narcissus_01",
    "NPC_Narcissus_Field_01", "NPC_Nemesis_01", "NPC_Nyx_01", "NPC_Nyx_Story_01", "NPC_Odysseus_01",
    "NPC_Persephone_01", "NPC_Selene_01", "NPC_Skelly_01", "NPC_Zagreus_01", "NPC_Zagreus_Past_01",
    "NPC_Zeus_01", "NPC_Zeus_Story_01",
))

OBJECTIVE_IDS = frozenset((
    "ActivateCatFamiliar", "AdvancedTooltipPrompt", "AnomalyStart", "BiomeNPylons", "BountyAdvancedTooltip",
    "BountyPrompt", "CapturePointProgress", "CardPrompt", "ChallengeReward", "CheckFamiliarInfoPrompt",
    "CheckFamiliarUpgradeInfoPrompt", "DoraDecorationIntroPrompt", "EliteChallenge", "ExorcismPrompt", "FamiliarPrompt",
    "FamiliarUpgradePrompt", "Flashback02Prompt", "GiftMedeaPoints", "GiftPrompt", "HeraclesMoney",
    "HitSkelly", "KeepsakePrompt", "KillChronos", "KillSkelly", "KillTyphon",
    "NemesisBet", "NemesisDamageContest", "NemesisKills", "OpenInventory", "OpenInventorySkelly",
    "PerfectClear", "PerfectClearCleanup", "PlayerKills", "PlayerMoney", "PostCreditsStartNewRun",
    "SkyEntranceInput", "SpellLaserPrompt", "SpellLeapPrompt", "SpellMeteorPrompt", "SpellPolymorphPrompt",
    "SpellPotionPrompt", "SpellSummonPrompt", "SpellTimeSlowPrompt", "SpellTransformPrompt", "TimeChallenge",
    "TimeChallengeValue", "UseDreamRunDoor", "UseShrinePrompt", "UseSurfaceDoor", "WeaponAxe",
    "WeaponAxeDash", "WeaponAxeSpecial", "WeaponAxeSpecialSwing", "WeaponAxeSpin", "WeaponBlink",
    "WeaponCast", "WeaponCastArm", "WeaponDagger", "WeaponDagger5", "WeaponDaggerDash",
    "WeaponDaggerThrow", "WeaponDaggerThrowCharged", "WeaponDaggerWombo", "WeaponLob", "WeaponLobCharged",
    "WeaponLobCharged_Hel", "WeaponLobPickup", "WeaponLobSpecial", "WeaponLobSpecialCharged", "WeaponLobSpecial_Hel",
    "WeaponLob_Hel", "WeaponStaffBall", "WeaponStaffBall2", "WeaponStaffBall_Anubis", "WeaponStaffDash",
    "WeaponStaffSwing", "WeaponStaffSwing5", "WeaponStaffSwing_Anubis", "WeaponSuit", "WeaponSuitCharged",
    "WeaponSuitDash", "WeaponSuitRanged", "WeaponSuitRangedCharged", "WeaponSuitRangedCharged_Shiva", "WeaponTorch",
    "WeaponTorchCharged", "WeaponTorchCharged_Supay", "WeaponTorchSpecial", "WeaponTorchSpecialCharged",
))
