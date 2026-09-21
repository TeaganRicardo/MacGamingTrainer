from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]
LEGALITY = ROOT / "docs/reference/hades2/1.139672-24556151/catalog_legality.csv"

SPECIAL_TRAITS = {
    "Artemis": {
        "SupportingFireBoon", "CritBonusBoon", "DashOmegaBuffBoon",
        "HighHealthCritBoon", "InsideCastCritBoon", "OmegaCastVolleyBoon",
        "TimedCritVulnerabilityBoon", "FocusCritBoon", "SorceryCritBoon",
    },
    "Athena": {
        "InvulnerabilityDashBoon", "RetaliateInvulnerabilityBoon",
        "FocusLastStandBoon", "DeathDefianceRefillBoon", "AthenaProjectileBoon",
        "InvulnerabilityCastBoon", "ManaSpearBoon", "OlympianSpellCountBoon",
    },
    "Dionysus": {
        "CastLobBoon", "HiddenMaxHealthBoon", "FirstHangoverBoon",
        "CombatEncounterHealBoon", "PowerDrinkBoon", "FogDamageBonusBoon",
        "BankBoon", "RandomBaseDamageBoon",
    },
    "Hades": {
        "HadesLifestealBoon", "HadesCastProjectileBoon", "HadesPreDamageBoon",
        "HadesChronosDebuffBoon", "HadesDashSweepBoon",
        "HadesDeathDefianceDamageBoon", "HadesManaUrnBoon",
        "HadesInvisibilityRetaliateBoon",
    },
    "Arachne": {
        "AgilityCostume", "ManaCostume", "VitalityCostume", "HighArmorCostume",
        "CastDamageCostume", "IncomeCostume", "SpellCostume", "EscalatingCostume",
    },
    "Narcissus": {
        "NarcissusA", "NarcissusB", "NarcissusC", "NarcissusD", "NarcissusE",
        "NarcissusF", "NarcissusG", "NarcissusH", "NarcissusI",
    },
    "Echo": {
        "EchoLastReward", "EchoLastRunBoon", "EchoDeathDefianceRefill",
        "EchoDoubleLevelBoon", "DiminishingDodgeBoon",
        "DiminishingHealthAndManaBoon", "EchoDoubleShop", "EchoRepeatKeepsakeBoon",
    },
    "Medea": {
        "HealingOnDeathCurse", "MoneyOnDeathCurse", "ManaOverTimeCurse",
        "SpawnDamageCurse", "ArmorPenaltyCurse", "SlowProjectileCurse",
        "DeathDefianceRetaliateCurse", "NewStatusDamage",
    },
    "Circe": {
        "CirceShrinkTrait", "CirceEnlargeTrait", "ArcanaRarityTrait",
        "HealAmplifyTrait", "DoubleFamiliarTrait", "RemoveShrineTrait",
        "RandomArcanaTrait", "CirceSorceryDamageBoon", "ExPolymorphBoon",
    },
    "Icarus": {
        "FocusAttackDamageTrait", "FocusSpecialDamageTrait", "OmegaExplodeBoon",
        "CastHazardBoon", "BreakInvincibleArmorBoon", "BreakExplosiveArmorBoon",
        "SupplyDropBoon", "UpgradeHammerBoon",
    },
}

WELL_TRAITS = {
    "ExtendedShopTrait", "FirstHitHealTrait", "TemporaryBoonRarityTrait",
    "TemporaryDiscountTrait", "TemporaryDoorHealTrait",
    "TemporaryEmptySlotDamageTrait", "TemporaryForcedSecretDoorTrait",
    "TemporaryHealExpirationTrait", "TemporaryImprovedCastTrait",
    "TemporaryImprovedDefenseTrait", "TemporaryImprovedExTrait",
    "TemporaryImprovedSecondaryTrait", "TemporaryMoveSpeedTrait",
}

with LEGALITY.open(newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))

trait_rows = {row["id"]: row for row in rows if row["kind"] == "trait"}
special_ids = set().union(*SPECIAL_TRAITS.values())

assert len(special_ids) == 83
assert len(WELL_TRAITS) == 13
assert set(trait_rows) == special_ids | WELL_TRAITS, (
    sorted((special_ids | WELL_TRAITS) - set(trait_rows)),
    sorted(set(trait_rows) - (special_ids | WELL_TRAITS)),
)

SPECIAL_EXACT_TRAITS = {
    *SPECIAL_TRAITS["Arachne"],
    "EchoLastRunBoon",
}

for source, ids in SPECIAL_TRAITS.items():
    for identifier in ids:
        expected = "special" if identifier in SPECIAL_EXACT_TRAITS else "direct"
        assert trait_rows[identifier]["classification"] == expected, (source, identifier)

for identifier in WELL_TRAITS:
    assert trait_rows[identifier]["classification"] == "special", identifier

print("hades2_special_trait_census_ok")
