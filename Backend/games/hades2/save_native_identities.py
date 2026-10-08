"""Native Save Editor identity registry for Hades II 1.143476 (Steam 25481925).

Source: Content/Scripts/ResourceData.lua (concrete ResourceData entries),
Content/Scripts/QuestData.lua (QuestOrderData); archival evidence is in
Google Drive / MacGamingTrainer / ReferenceEvidence / Hades2. Update when the
supported game build changes; unknown IDs remain read-only in Advanced.
"""

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
    "DreamPoints", "TrashPoints", "Money",
))

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
