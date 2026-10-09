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

# Native StoryResetData.TextLines from target 1.143476 / Steam 25481925.
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
