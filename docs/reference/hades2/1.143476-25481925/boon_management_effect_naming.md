# Boon Management effect naming governance

Target: Hades II **1.143476** / Steam build **25481925**  
Status: **proposed — pending user review**

This document owns the presentation rules for concrete runtime traits that can appear in Boon Management but do not have a sufficiently specific standalone native title. The row-level review ledger is `boon_management_effect_names.csv`.

## Resolution order

1. Keep runtime identity (`trait.Name`, owner/source IDs and instance ID) internal.
2. Ask the resident runtime for the same title identity used by the native Trait Tray (`GetTraitTooltipTitle`).
3. Resolve the target game's bilingual `DisplayName`, including SJSON `InheritFrom` chains. An inherited native title is still a Native Game Term.
4. Only if the resulting title is insufficient to identify the function, use the derived bilingual descriptor in the CSV.
5. Arcana is one UI section. Its final item label is **native card title · derived function descriptor**. The exact card remains owner/source metadata, not a separate section.
6. Family labels such as “其他效果 / Other Effect” are emergency compatibility fallbacks only. No row in the supported-target census is allowed to rely on one as its final label.

## Provenance

- `native-owner+trainer-derived-effect`: the owner/card/familiar/weapon name is an official target-build localization term; the short function descriptor is Trainer-owned and derived from target Lua fields or the official Description.
- `trainer-derived-effect`: no standalone target-build title exists; both language labels are neutral Trainer Product Terms derived from the target effect semantics.
- Ordinary boons, Hexes, Chaos traits, Hammers, Keepsakes and other rows with a concrete native title are **not duplicated in this ledger**. They stay dynamically sourced from installed target localization.
- Text records that merely omit `DisplayName` but use `InheritFrom` are **not** treated as unnamed. The localization parser resolves their native parent title.

## Census boundary

The retained 1.139672 generated TraitData inventory was used only to find historical missing-title candidates. Every row admitted to this ledger was then revalidated against the installed 1.143476 target's Lua/text files. Debug/base/template traits are excluded unless target code proves they are concretely mounted in `CurrentRun.Hero.Traits`.

### Census accounting

The supported target has **670 unique TraitData IDs**. The naming census closes over all 670:

- **603** resolve to a readable target-build title through direct or inherited SJSON `DisplayName`. Ordinary native rows stay dynamic rather than being copied into the Trainer registry.
- **25 of those 603** are Arcana mounted traits whose native title identifies the card but not its function; they therefore receive the functional suffixes recorded in the CSV.
- **6** additional concrete mounted weapon placeholder traits have no standalone text title but resolve through the native Trait Tray `CustomTitle` seam:
  - `DummyWeaponStaff` → 女巫之杖 / Witch's Staff
  - `DummyWeaponDagger` → 姊妹双刃 / Sister Blades
  - `DummyWeaponAxe` → 月石之斧 / Moonstone Axe
  - `DummyWeaponTorch` → 暗影之炬 / Umbral Flames
  - `DummyWeaponLob` → 银白之颅 / Argent Skull
  - `DummyWeaponSuit` → 漆黑战衣 / Black Coat
- **22** additional concrete mounted effects have no sufficiently specific native title and therefore require the Trainer-derived bilingual labels in the CSV.
- **39** IDs are base/debug/template scaffolding with no independently proven mounted identity and are intentionally excluded from Boon Management presentation:
  `AxeHammerTrait`, `BaseBoonUpgradeKeepsake`, `BaseCirce`, `BaseCurse`, `BaseDummyWeapon`, `BaseEcho`, `BaseIcarus`, `BaseTrait`, `BiomeState`, `ChaosBlessing`, `ChaosBlessingTrait`, `ChaosCurse`, `ChaosCurseRemainingEncounters`, `ChaosCurseTrait`, `ChaosLegacyTrait`, `CostumeTrait`, `DaggerHammerTrait`, `FamiliarTrait`, `ForceCommonAppearanceTrait`, `ForceDuoAppearanceTrait`, `GiftTrait`, `InPersonOlympianTrait`, `LegacyTrait`, `LegendaryTalent`, `LegendaryTrait`, `LobHammerTrait`, `ManaOverTimeSource`, `MetaUpgradeTrait`, `MoonBeamTalentTrait`, `ShopTrait`, `SpellTalentTrait`, `SpellTrait`, `StaffHammerTrait`, `SuitHammerTrait`, `SynergyTrait`, `TorchHammerTrait`, `UnityTrait`, `WeaponEnchantmentTrait`, `WeaponTrait`.

Accounting: **603 + 6 + 22 + 39 = 670**. The CSV has **47 rows** because it contains the 22 otherwise unnamed concrete effects plus the 25 Arcana function descriptors.

Concrete target seams used in this review include:

- `MetaUpgradeData.lua` + `TraitText.*.sjson` for all 25 Arcana cards;
- `FamiliarData.lua` + `FamiliarShopData.lua` for hidden Familiar upgrade traits;
- `ConsumableData.lua` + `TraitData_Essence.lua` for elemental essence traits;
- `RoomLogic.lua` + `TraitData.lua` for Max Life, Max Magick and Armor state;
- `WeaponLogic.lua` + `TraitData.lua` + native `WeaponSuit` text for the Black Coat sprint trait;
- `BiomeStateData.lua` + `BiomeStateLogic.lua` for normal/rain environment-state traits; these are grouped as the product family `biomeState` rather than leaking into `other`.

## Governance rule

Adding a new current-run derived label requires all of the following in the same focused change:

- target-build evidence proving the trait can be mounted;
- a bilingual label pair;
- provenance classification;
- an entry in the CSV;
- a matching code entry in `catalog._CURRENT_RUN_DERIVED_NAMES`;
- local regression coverage proving the target census does not fall through to “未命名效果 / Unnamed Effect” or a family-only label.

Do not infer a display name by prettifying Trait IDs.
