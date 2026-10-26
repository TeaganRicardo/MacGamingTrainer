"""Native Save Editor identities generated for the module-declared supported build.

QuestData.lua SHA-256 df9888d6586e0f8644e31db093bf35452bc3ac057d0f144be2f2f1e8d1e64336
ResourceData.lua SHA-256 94b2dc9edc22c34b213ab78dea42f2dc76c80cbcfde14104cbe772b254a29b03
ObjectiveData.lua SHA-256 e635ef5c05ba8a22e4af4ed3d4290ec20d31c0bd95c1aff9e8b1ac828940c816
NPCData*.lua bundle SHA-256 8e632ee4e2f6f1bb5eaa87e8c15154c556dc62e733654bebae9bebf0b0f94ec0
Quest IDs come from QuestOrderData; resources are top-level ResourceData entries
excluding abstract Base* templates. Recheck these IDs on target-build changes.
"""

QUEST_REWARD_OWNER_SHA256 = {
    "ResourceLogic.lua": "809bdf80b277179d45c420ec3873eebc36e7aca5f3e30d79ad4df01ddf8f82a0",
    "QuestLogLogic.lua": "0dff8cb49c54715ffe13c1c2986553087688e9dbd2aec3fa1fe61943ba91c254",
    "ResourceData.lua": "94b2dc9edc22c34b213ab78dea42f2dc76c80cbcfde14104cbe772b254a29b03",
}

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

# Native StoryResetData.TextLines from the module-declared source snapshot.
# StoryResetData.lua SHA-256 58509042a27542f96d666071da2fa58ca3c3b227002e4ae628501b7d7738ef8e
# A native-authored reset target is necessary, not sufficient, to authorize an
# individual edit: companion narrative/gift/run owners are validated separately.
STORY_RESET_TEXT_IDS = frozenset("""
AchillesTrueEnding01 AphroditeAboutChronosBossW01 AphroditeAboutTyphonDeath01 AphroditeAboutTyphonW01 AphroditePostEpilogue01 AphroditePostTrueEnding01 AphroditePostTrueEnding02 AphroditeUnderworldRunCleared02
ApolloAboutChronosBossW01 ApolloAboutChronosBossW02 ApolloAboutPalace01 ApolloAboutTyphonDeath01 ApolloAboutTyphonDeath02 ApolloAboutTyphonW01 ApolloAboutTyphonW02 ApolloAboutTyphonW03
ApolloPalaceAboutTyphonDeath01 ApolloPalaceFirstMeeting ApolloPalaceMeeting02 ApolloPalaceMeeting03 ApolloPalaceMeeting04 ApolloPalaceMeeting04_B ApolloPalacePostTrueEnding01 ApolloPostEpilogue01
ApolloPostTrueEnding01 ApolloUnderworldRunCleared03 ArachneAboutUltimateProgress01 ArachnePostEpilogue01 ArachnePostEpilogue02 ArachnePostTrueEnding01 ArachnePostTrueEnding02 AresAboutTyphonDeath01
AresPostEpilogue01 AresPostTrueEnding01 AresPostTrueEnding02 AresPostTrueEndingAboutChronos01 AresPostTrueEndingAboutChronos02 AresPostTrueEndingAboutTyphon01 AresUnderworldRunCleared01 AresUnderworldRunCleared02
AresUnderworldRunCleared03 ArtemisAboutChronosBossW01 ArtemisAboutChronosBossW02 ArtemisAboutTyphon02 ArtemisPostEpilogue01 ArtemisPostTrueEnding01 AthenaAboutChronosBossW01 AthenaAboutTyphonDeath01
AthenaAboutTyphonW01 AthenaPostEpilogue01 AthenaPostEpilogue02 AthenaPostTrueEnding01 AthenaPostTrueEnding02 CerberusTrueEnding01 ChaosAboutTyphonDeath01 ChaosPostEpilogue01
ChaosPostTrueEnding01 ChaosPostTrueEnding02 ChaosPostTrueEndingAboutNyx01 ChaosPostTrueEndingRunCleared01 ChaosUnderworldSurfaceCleared01 ChaosUnderworldSurfaceCleared02 ChaosWithNyx01 CharonAboutChronosBossW01
CharonAboutTyphon02 CharonPostEpilogue01 CharonPostTrueEnding01 CharonPostTrueEnding02 ChronosBossAboutFamily01 ChronosBossAboutFamily02 ChronosBossAboutFamily03 ChronosBossAboutFamily04
ChronosBossAboutFamily05 ChronosBossAboutHecateKidnapped01 ChronosBossAboutHecateKidnapped02 ChronosBossAboutTyphon02 ChronosBossAboutTyphonDeath01 ChronosBossOutro01 ChronosBossOutroAfterHecateKidnapped01 ChronosBossOutroPostTrueEnding01
ChronosBossOutroPreTrueEnding01 ChronosBossOutroPreTrueEnding01_B ChronosBossOutroUltimateProgress01 ChronosBossOutroUltimateProgress02 ChronosBossOutroUltimateProgress03 ChronosBossOutroUltimateProgress04 ChronosBossOutroUltimateProgress05 ChronosBossPostTrueEnding01
ChronosBossPostTrueEnding02 ChronosMeetingAboutTyphon02 ChronosMeetingAboutTyphonW01 ChronosPostBattleMeeting01 CirceAboutTyphonW01 CircePostEpilogue01 CircePostTrueEnding01 CircePostTrueEnding02
CircePostTrueEnding03 DemeterAboutChronosBossW01 DemeterAboutChronosBossW02 DemeterAboutTyphonDeath01 DemeterAboutTyphonDeath02 DemeterAboutTyphonW01 DemeterAboutTyphonW02 DemeterPalaceAboutTyphonDeath01
DemeterPalaceFirstMeeting DemeterPalacePostTrueEnding01_B DemeterPostEpilogue01 DemeterPostEpilogue02 DemeterPostTrueEnding01 DemeterPostTrueEnding03 DionysusPostEpilogue01 DionysusPostTrueEnding01
DionysusPostTrueEnding02 DionysusPostTrueEnding03 DoraAboutChronosBossW01 DoraAboutChronosBossW02 DoraPostEpilogue01 DoraPostTrueEnding01 DoraPostTrueEnding02 EchoPostTrueEnding01
ErisAboutChronos01 ErisAboutRunCleared01 ErisAboutSurfaceRunCleared01 ErisAboutUltimateProgress01 ErisBossAboutTyphon03 ErisBossAboutTyphonDeath01 ErisBossPostTrueEnding01 ErisPostEpilogue01
ErisPostEpilogue02 ErisPostTrueEnding01 ErisPostTrueEnding02 ErisPostTrueEnding03 ErisPostTrueEnding04 FatesEpilogue01 HadesAboutChronosBossW01 HadesAboutChronosBossW01_B
HadesAboutTyphon02 HadesAboutUltimateProgress01 HadesAboutUltimateProgress02 HadesAboutUltimateProgress03 HadesHideAndSeek01 HadesTrueEnding01 HadesWithPersephone01 HadesWithPersephonePostEpilogue01
HadesWithPersephonePostEpilogue02 HadesWithPersephonePostEpilogue03 HecateAboutChronosBossW01 HecateAboutChronosBossW01Cont1 HecateAboutChronosBossW02 HecateAboutChronosBossW03 HecateAboutChronosBossW04_A HecateAboutChronosBossW04_B
HecateAboutStormStopNotCast01 HecateAboutTimeStop01 HecateAboutTyphonDeath01 HecateAboutTyphonFight03 HecateAboutTyphonW02 HecateAboutUltimateProgress02 HecateAboutUltimateProgress03 HecateAboutUltimateProgress03_A
HecateAboutUltimateProgress04 HecateBathHouseEpilogue01 HecateBossAboutChronosBossW02 HecateBossAboutEndingPath00 HecateBossAboutEndingPath01 HecateBossAboutEndingPath02 HecateBossAboutEndingPath03 HecateBossAboutEndingPath04
HecateBossKidnapped01 HecateBossPostEpilogue01 HecateBossPostEpilogue02 HecateBossPostTrueEnding01 HecateBossPostTrueEnding02 HecatePostEpilogue01 HecatePostEpilogue02 HecatePostTrueEnding01
HecatePostTrueEnding02 HecatePostTrueEnding03 HecatePostTrueEnding04 HephaestusAboutChronosBossW01 HephaestusAboutTyphonDeath01 HephaestusAboutTyphonDeath02 HephaestusPostEpilogue01 HephaestusPostEpilogue02
HephaestusPostTrueEnding01 HephaestusPostTrueEnding02 HephaestusPostTrueEnding03 HephaestusUnderworldRunCleared02 HeraAboutPalace01 HeraAboutPalace02 HeraAboutTyphonDeath01 HeraAboutTyphonDeath02
HeraAboutTyphonW01 HeraPostEpilogue01 HeraPostEpilogue02 HeraPostTrueEnding01 HeraPostTrueEndingAboutSurface01 HeraclesFieldAboutEpilogue01 HeraclesFieldAboutTrueEnding01 HeraclesFieldAboutTrueEnding02
HeraclesFieldAboutTyphon02 HeraclesPreEncounterAboutTrueEnding01 HermesAboutFatesQuest01 HermesAboutTyphonDeath01 HermesAboutUltimateProgress01 HermesFieldAboutTyphon03 HermesFieldAboutTyphonDeath01 HermesPostEpilogue01
HermesPostEpilogue02 HermesPostEpilogue03 HermesPostTrueEnding01 HermesPostTrueEnding02 HermesPostTrueEnding03 HermesSurfaceRunCleared02 HermesUnderworldRunCleared01 HestiaAboutChronosBossW01
HestiaAboutChronosBossW02 HestiaAboutTyphonDeath01 HestiaAboutWinStreak01 HestiaPostEpilogue01 HestiaPostTrueEnding01 HestiaPostTrueEnding02 HestiaSurfaceRunCleared01 HestiaSurfaceRunCleared03
HestiaUnderworldRunCleared01 HestiaUnderworldRunCleared02 HestiaUnderworldRunCleared03 HypnosAboutStoryReset01 HypnosAboutUltimateProgress01 HypnosAboutUltimateProgress02 HypnosDreamAboutStoryReset01 HypnosDreamMeeting03
HypnosDreamMeeting03_B HypnosFinalDreamMeeting01 HypnosPostTrueEnding01 HypnosPostTrueEnding02 HypnosWakeUp03 HypnosWakeUp03_B HypnosWakeUp03_C IcarusHomeAboutTyphonDeath01
IcarusHomePostEpilogue01 IcarusHomePostEpilogue02 IcarusHomePostTrueEnding01 IcarusHomePostTrueEnding02 IcarusPostTrueEnding01 IcarusPostTrueEnding01_B IcarusPostTrueEnding02 IcarusPostTrueEnding03
Inspect_I_Boss01TrueEnding_01 MedeaPostTrueEnding01 MelinoeHideAndSeek01 MorosAboutChronosBossW01 MorosAboutChronosBossW02 MorosAboutEpilogueProgress01 MorosAboutHecateKidnapped01 MorosAboutPostEndingChronosBossW01
MorosAboutPostEndingTyphonW01 MorosAboutTyphonDeath01 MorosAboutTyphonW01 MorosPostEpilogue01 MorosPostEpilogue02 MorosPostEpilogue03 MorosPostTrueEnding01 MorosPostTrueEnding02
NemesisAboutChronosBossFights01 NemesisAboutChronosBossW01 NemesisAboutHecateKidnapped01 NemesisAboutNyx01 NemesisAboutNyxRescue01 NemesisAboutTyphonDeath01 NemesisAboutTyphonW01 NemesisAboutTyphonW02
NemesisAboutUltimateProgress01 NemesisPostEpilogue01 NemesisPostTrueEnding01 NemesisPostTrueEnding02 NemesisPostTrueEnding03 NemesisWithHecate02 NeoChronosAboutErebus01 NeoChronosAboutOlympus01
NeoChronosAboutOlympus01_B NeoChronosAboutOlympus02 NeoChronosAboutTartarus01 NeoChronosAboutTartarus01_B NeoChronosAboutTartarus02 NeoChronosPostEpilogue01 NyxInChaos01 NyxInChaosPostEpilogue01
NyxWithNemesis01 OdysseusAboutChronosBossW01 OdysseusAboutHecateKidnapped01 OdysseusAboutTyphonDeath01 OdysseusAboutTyphonW01 OdysseusAboutTyphonW02 OdysseusAboutUltimateProgress01 OdysseusPostEpilogue01
OdysseusPostEpilogue02 OdysseusPostTrueEnding01 OdysseusPostTrueEnding02 OdysseusPostTrueEndingAboutHouse01 OdysseusPostTrueEndingAboutTyphon01 PalaceBoonExit01 PalaceBoonExit02 PalaceBoonExitPostTrueEnding01
PalaceBoonExitTyphonDestroyed01 PersephoneTrueEnding01 PolyphemusPostTrueEnding01 PolyphemusPostTrueEnding02 PolyphemusPostTrueEnding03 PoseidonAboutPalace01 PoseidonAboutTyphonDeath01 PoseidonPostEpilogue01
PoseidonPostEpilogue02 PoseidonPostTrueEnding01 PoseidonPostTrueEnding02 PoseidonSurfaceRunCleared01 PoseidonSurfaceRunCleared02 PoseidonUnderworldRunCleared02 PoseidonUnderworldRunCleared03 PreTrueEnding01
PrometheusAboutEpilogue01 PrometheusAboutEpilogue02 PrometheusAboutEpilogue03 PrometheusAboutEpilogue04 PrometheusAboutTyphon03 PrometheusAboutUltimateProgress01 PrometheusAboutUltimateProgress02 PrometheusPostTrueEnding01
PrometheusPostTrueEnding02 PrometheusPostTrueEnding03 ScyllaAboutGrandeur01 ScyllaPostTrueEnding01 ScyllaPostTrueEnding02 SeleneAboutTyphonW01 SeleneAboutTyphonW02 SelenePostEpilogue01
SelenePostTrueEnding01 SelenePostTrueEnding02 SelenePostTrueEndingRunCleared01 SelenePostTrueEndingRunCleared02 SeleneRunCleared02 SeleneRunCleared03 SeleneTrueEnding01 SkellyAboutChronosBossW01
SkellyAboutChronosBossW03 SkellyAboutTyphonW01 SkellyAboutTyphonW02 SkellyAboutUltimateProgress01 SkellyAboutZagreusFight01 SkellyPostEpilogue01 SkellyPostTrueEnding01 SkellyPostTrueEnding02
TrueEnding01 TrueEnding02 TrueEndingFinale01 TrueEndingFinaleResponse01 ZagreusBossFirstMeeting ZagreusBossOutro01 ZagreusPastFirstMeeting ZagreusPastMeeting02
ZagreusPastMeeting02_2 ZagreusPastMeeting03 ZagreusPastMeeting04 ZagreusPastMeeting04_2 ZagreusPastMeeting04_3 ZagreusPastMeeting05 ZagreusPastMeeting06 ZagreusPastMeeting06_B
ZagreusPastMeeting07 ZagreusPastMeeting08 ZagreusTrueEnding01 ZeusAboutTyphonW01 ZeusAboutTyphonW02 ZeusAboutTyphonW03 ZeusAboutTyphonW04 ZeusPalaceAboutTyphonDeath01
ZeusPalaceFirstMeeting ZeusPalaceFirstMeetingAlt ZeusPalaceMeeting02 ZeusPalaceMeeting03 ZeusPalaceMeeting03_A ZeusPalaceMeeting03_B ZeusPalaceMeeting04 ZeusPalaceMeeting04_B
ZeusPalacePostTrueEnding01 ZeusPostEpilogue01 ZeusPostEpilogue02 ZeusPostTrueEnding01 ZeusPostTrueEnding02 ZeusPostTrueEnding03 ZeusUnderworldRunCleared02 ZeusUnderworldRunCleared03
ZeusUnderworldRunCleared04
""".split())

# Native handler/description references; display text stays in official localization.

SAVE_FIELD_SOURCE_SHA256 = {'DeathLoopData.lua': '682be85f426507ad3bba35772fba285b3397fd05544c6bd7caedc3f5fc4aec87',
 'FamiliarData.lua': '5a8e079c729ddf2d4f756fd4a5f1938466265174a33968c3a9d80f7f512d37b3',
 'LootData_Chaos.lua': '63d8ea3839d5e585ade60ed2dd8aba2eae42d4c2a48743e69495906d83773fe4',
 'LootData_Hermes.lua': '52f9847a0f394b5b465cd22d7c774fd6917fef4295e90733332efd430c602484',
 'LootData_Selene.lua': '93735c4f3eb41c0d5159a71354287c3dfe575308f55e68145d52a1953cf2a276',
 'NPCData.lua': '494a278163e4b55e95d3479747a339c94c79fa9b098bc43e05167857f990db33',
 'NPCData_Arachne.lua': '97877939610096bd9e816ae28ca2667fd172519f1124cd8df9345aba937136f7',
 'NPCData_Artemis.lua': '3a1cb7a56dad875c9959244d9d73439073515dce6884e871341bfd5c6b2793c6',
 'NPCData_Athena.lua': '3ab70afea115bb62bb7f839fe5f6d4f5a5c1760b227b5aa94817df9073fca3f5',
 'NPCData_Charon.lua': '8f47f4215fc0e9ea10c77893bad3b5dd7c5f7fc5acf075f7fd1adebcded9023d',
 'NPCData_Chronos.lua': '24e771a8eb50059ec1adff03e1126f715125c989277b1f825d0f8093dba5e258',
 'NPCData_Circe.lua': '955b0ba52ac200d65a9765a97e90d174bdbc8178d7757d898aee78081272376b',
 'NPCData_Dionysus.lua': '6a275033c9b6db090d7645d39eff957c256eb5b19d78596a7c5e7b64225f17fc',
 'NPCData_Dora.lua': 'ee8b9bc242a0b2c2982727d15139847881ba81197a043c4ecb4e0b882379938e',
 'NPCData_Echo.lua': '8ebfd6a9cd2c12d43dee33898941ce83ddbb24475d69d9efbb6c2be752dca243',
 'NPCData_Eris.lua': '2cbb1cb203d5613c2ff0165ea10da13224b7258adfed18c27a371132c117609d',
 'NPCData_Hades.lua': 'c9ad56dc42c5286e247e100b6e1d25b0ea75ab02ece7ef590acf86fb3e32bf9d',
 'NPCData_Hecate.lua': '622d51643a23af55414820bd9614dfb80dbb79fb8aa073f5229a078efbe73d84',
 'NPCData_Heracles.lua': '443279d16c758eba38d306785ace68004cb28cbe1e164aea1b236a0cff1c8947',
 'NPCData_Hermes.lua': 'beb33319a4a1c317960efe727f8439fb5f29627f912c004740dd7e0070c0f1fa',
 'NPCData_Hypnos.lua': 'dfb4754411e152f3815140be449aa848aa11368f4b6b159768ac70885bfad786',
 'NPCData_Icarus.lua': '87afe931de71d79ddef07a4574cb8e31731a86b28350f009f903bf18fbbdeeb0',
 'NPCData_Medea.lua': '2985cc7531e2ebe6c0aa067d418b18ff74946c285a68a5703f3805f88cf84978',
 'NPCData_Moros.lua': 'c03f240ddd569b9215c51a10a9702f93963ab9cb6298a206088a7c069f4f380d',
 'NPCData_Narcissus.lua': '55587025a285307f4b04071bd28a9d5a42aaa1133c1764ea0580a997d8c01019',
 'NPCData_Nemesis.lua': 'c3b2469529d278073adbd75fcbcec67db851f72491cb61cc97adab470dc0ee60',
 'NPCData_Odysseus.lua': '73db48d00a8f1baf79d0013adfc28798a1953a8168af3e08419d6df74a7eccbf',
 'NPCData_Selene.lua': '2d3e934a9e51cf3038f74b0022b47e2b6008e02cc7022421c31784a8a64066e8',
 'NPCData_Skelly.lua': 'd0d7418ba6fe540e28657dac6289e8eb1a938a3ba580401910b834fc85668c0a',
 'ObjectiveData.lua': 'e635ef5c05ba8a22e4af4ed3d4290ec20d31c0bd95c1aff9e8b1ac828940c816',
 'ObstacleData.lua': 'b2c6641e1c0072960807c1e9fa1d718f61b5b77d25c015f8e8d392706e5dc5e3',
 'ObstacleDataH.lua': '8332612a0815eaab27e18289293dbb6099eac54aaf02ee4c92eece195d2cfafc',
 'RoomDataF.lua': '4d23b89616376dfa78060031abb5fe41dcaac39c113f546886ca4c476148e8b1',
 'RoomDataH.lua': '115b9864166eabffb4e83c54b174a649fd91b3eaa3068dbdf9fc8263d37eeaf1',
 'RoomDataO.lua': '3791ca84e6ac660170dfd8d9ed108f8abea31f3577e9cdc7de3036c258fbd036',
 'RoomDataP.lua': '5002765b58bcdd64b52d417547f6b8c81c3f7a4214bf76e3642853337c683e3c'}

SPECIAL_INTERACTION_FUNCTIONS = {'BartenderShade01': ('SpecialInteractSaluteBroker',),
 'CatFamiliar': ('CatFamiliarSpecialInteractLockedInRun', 'CatFamiliarSpecialInteractUnlockedInHub'),
 'CrossroadsFountainWall01': ('UseHadesFountain',),
 'DieHardFanShade': ('SpecialInteractDieHardFanShade', 'SpecialInteractDieHardFanShadeSendToElysium'),
 'FrogFamiliar': ('FrogFamiliarSpecialInteractUnlockedInHub', 'PetFamiliarFrog'),
 'GameStatsScreen': ('SpecialInteractSaluteBroker',),
 'GhostInspectPoint': ('UseExorcisedGhostsPreRun', 'UseGhostEavesdropper', 'UseGhostInspectPoint'),
 'HermesUpgrade': ('SpecialInteractSalute',),
 'HoundFamiliar': ('HoundFamiliarSpecialInteractLockedInRun', 'HoundFamiliarSpecialInteractUnlockedInHub'),
 'HubGardenPlot': ('PlantAdmirePresentation',),
 'Market': ('SpecialInteractSaluteBroker',),
 'MusicPlayerScreen': ('SpecialInteractSaluteBroker',),
 'NPC_Achilles_01': ('SpecialInteractSalute',),
 'NPC_Arachne_01': ('SpecialInteractSalute',),
 'NPC_Arachne_Home_01': ('SpecialInteractSalute',),
 'NPC_Artemis_01': ('SpecialInteractSalute', 'UseArtemisJoinSong'),
 'NPC_Artemis_Field_01': ('SpecialInteractSalute', 'UseArtemisJoinSong'),
 'NPC_Athena_01': ('SpecialInteractSalute',),
 'NPC_Cerberus_Field_01': ('AttemptPetCerberusThread',),
 'NPC_Cerberus_Story_01': ('AttemptPetCerberusThread',),
 'NPC_Charon_01': ('SpecialInteractSalute',),
 'NPC_Chronos_02': ('SpecialInteractSalute',),
 'NPC_Chronos_Story_01': ('SpecialInteractThreatenChronos',),
 'NPC_Circe_01': ('SpecialInteractSalute',),
 'NPC_Demeter_Story_01': ('SpecialInteractSalute',),
 'NPC_Dionysus_01': ('SpecialInteractSalute',),
 'NPC_Dora_01': ('SpecialInteractSalute', 'UseCosmeticsShop'),
 'NPC_Echo_01': ('SpecialInteractSalute',),
 'NPC_Eris_01': ('SpecialInteractSalute',),
 'NPC_Hades_02': ('SpecialInteractSalute',),
 'NPC_Hades_Field_01': ('SpecialInteractSalute',),
 'NPC_Hecate_01': ('SpecialInteractSalute',),
 'NPC_Hecate_Story_01': ('SpecialInteractSalute',),
 'NPC_Hera_Story_01': ('SpecialInteractSalute',),
 'NPC_Heracles_01': ('SpecialInteractSalute',),
 'NPC_Hermes_01': ('SpecialInteractSalute',),
 'NPC_Hypnos_01': ('SpecialInteractSalute',),
 'NPC_Hypnos_02': ('SpecialInteractSalute',),
 'NPC_Hypnos_03': ('SpecialInteractSalute',),
 'NPC_Hypnos_04': ('SpecialInteractSalute',),
 'NPC_Hypnos_DreamRun': ('SpecialInteractSalute',),
 'NPC_Icarus_01': ('SpecialInteractSalute',),
 'NPC_Medea_01': ('SpecialInteractSalute',),
 'NPC_Moros_01': ('SpecialInteractSaluteInterrupt',),
 'NPC_Narcissus_01': ('SpecialInteractSalute',),
 'NPC_Narcissus_Field_01': ('SpecialInteractSalute',),
 'NPC_Nemesis_01': ('SpecialInteractSalute',),
 'NPC_Nyx_Story_01': ('SpecialInteractSalute',),
 'NPC_Odysseus_01': ('SpecialInteractSaluteInterrupt',),
 'NPC_Persephone_01': ('HugPersephone',),
 'NPC_Selene_01': ('SpecialInteractSalute',),
 'NPC_Skelly_01': ('SpecialInteractSalute',),
 'NPC_Zagreus_01': ('HugZagreus',),
 'NPC_Zeus_Story_01': ('SpecialInteractSalute',),
 'PolecatFamiliar': ('PolecatFamiliarSpecialInteractLockedInRun',
                     'PolecatFamiliarSpecialInteractUnlockedInHub'),
 'RavenFamiliar': ('RavenFamiliarSpecialInteractLockedInRun', 'RavenFamiliarSpecialInteractUnlockedInHub'),
 'RunHistoryScreen': ('SpecialInteractSaluteBroker',),
 'Shrine': ('SpecialInteractChangeNextRunRNG',),
 'SpellDrop': ('SpecialInteractSalute',),
 'TrialUpgrade': ('SpecialInteractSalute',)}

OBJECTIVE_LOCALIZATION_IDS = {'ActivateCatFamiliar': 'Objective_ActivateCatFamiliar',
 'AdvancedTooltipPrompt': 'Objective_AdvancedTooltip',
 'AnomalyStart': 'Objective_AnomalyStart',
 'BiomeNPylons': 'Objective_BiomeNPylons',
 'BountyAdvancedTooltip': 'Objective_BountyAdvancedTooltip',
 'BountyPrompt': 'Objective_BountyPrompt',
 'CapturePointProgress': 'Objective_CapturePointProgress',
 'CardPrompt': 'Objective_CardPrompt',
 'ChallengeReward': 'Objective_ChallengeReward',
 'CheckFamiliarInfoPrompt': 'Objective_CheckFamiliarInfoPrompt',
 'CheckFamiliarUpgradeInfoPrompt': 'Objective_CheckFamiliarUpgradeInfoPrompt',
 'DoraDecorationIntroPrompt': 'Objective_SaluteDora',
 'EliteChallenge': 'Objective_EliteChallenge',
 'ExorcismPrompt': 'Objective_Exorcism',
 'FamiliarPrompt': 'Objective_FamiliarPrompt',
 'FamiliarUpgradePrompt': 'Objective_FamiliarUpgradePrompt',
 'Flashback02Prompt': 'Objective_AnomalyStart',
 'GiftMedeaPoints': 'Objective_GiftMedeaPoints',
 'GiftPrompt': 'Objective_GiveGift',
 'HeraclesMoney': 'Objective_HeraclesMoney',
 'HitSkelly': 'Objective_HitSkelly',
 'KeepsakePrompt': 'Objective_UseKeepsakeRack',
 'KillChronos': 'Objective_KillChronos',
 'KillSkelly': 'Objective_KillSkelly',
 'KillTyphon': 'Objective_KillTyphon',
 'NemesisBet': 'Objective_NemesisBet',
 'NemesisDamageContest': 'Objective_NemesisDamageContest',
 'NemesisKills': 'Objective_NemesisKills',
 'OpenInventory': 'Objective_OpenInventory',
 'OpenInventorySkelly': 'Objective_OpenInventorySkelly',
 'PerfectClear': 'Objective_PerfectClear',
 'PerfectClearCleanup': 'Objective_PerfectClearCleanup',
 'PlayerKills': 'Objective_PlayerKills',
 'PlayerMoney': 'Objective_PlayerMoney',
 'PostCreditsStartNewRun': 'Objective_PostCreditsStartNewRun',
 'SkyEntranceInput': 'Objective_SkyEntranceInput',
 'SpellLaserPrompt': 'Objective_UseSpellLaser',
 'SpellLeapPrompt': 'Objective_UseSpellLeap',
 'SpellMeteorPrompt': 'Objective_UseSpellMeteor',
 'SpellPolymorphPrompt': 'Objective_UseSpellPolymorph',
 'SpellPotionPrompt': 'Objective_UseSpellPotion',
 'SpellSummonPrompt': 'Objective_UseSpellSummon',
 'SpellTimeSlowPrompt': 'Objective_UseSpellTimeSlow',
 'SpellTransformPrompt': 'Objective_UseSpellTransform',
 'TimeChallenge': 'Objective_TimeChallenge',
 'TimeChallengeValue': 'ChallengeSwitch_Value',
 'UseDreamRunDoor': 'Objective_UseDreamRunDoor',
 'UseShrinePrompt': 'Objective_UseShrine',
 'UseSurfaceDoor': 'Objective_UseSurfaceDoor',
 'WeaponAxeSpecialSwing': 'Objective_WeaponAxeSpecialSwing',
 'WeaponDaggerThrowCharged': 'Objective_WeaponDaggerThrowCharged',
 'WeaponDaggerWombo': 'Objective_WeaponDaggerWombo',
 'WeaponLobCharged': 'Objective_WeaponLobCharged',
 'WeaponLobCharged_Hel': 'Objective_WeaponLobCharged_Hel',
 'WeaponLobPickup': 'Objective_WeaponLobPickup',
 'WeaponLobSpecialCharged': 'Objective_WeaponLobSpecialCharged',
 'WeaponLobSpecial_Hel': 'Objective_WeaponLobSpecial_Hel',
 'WeaponLob_Hel': 'Objective_WeaponLob_Hel',
 'WeaponStaffBall_Anubis': 'Objective_WeaponStaffBall_Anubis',
 'WeaponStaffSwing_Anubis': 'Objective_WeaponStaffSwing_Anubis',
 'WeaponSuitRangedCharged': 'Objective_WeaponSuitRangedCharged',
 'WeaponSuitRangedCharged_Shiva': 'Objective_WeaponSuitRangedCharged_Shiva',
 'WeaponTorchCharged': 'Objective_WeaponTorchCharged',
 'WeaponTorchCharged_Supay': 'Objective_WeaponTorchCharged_Supay',
 'WeaponTorchSpecialCharged': 'Objective_WeaponTorchSpecialCharged'}
