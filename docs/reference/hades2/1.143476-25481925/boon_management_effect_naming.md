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

Concrete target seams used in this review include:

- `MetaUpgradeData.lua` + `TraitText.*.sjson` for all 25 Arcana cards;
- `FamiliarData.lua` + `FamiliarShopData.lua` for hidden Familiar upgrade traits;
- `ConsumableData.lua` + `TraitData_Essence.lua` for elemental essence traits;
- `RoomLogic.lua` + `TraitData.lua` for Max Life, Max Magick and Armor state;
- `WeaponLogic.lua` + `TraitData.lua` + native `WeaponSuit` text for the Black Coat sprint trait;
- `BiomeStateData.lua` + `BiomeStateLogic.lua` for normal/rain environment-state traits.

## Governance rule

Adding a new current-run derived label requires all of the following in the same focused change:

- target-build evidence proving the trait can be mounted;
- a bilingual label pair;
- provenance classification;
- an entry in the CSV;
- a matching code entry in `catalog._CURRENT_RUN_DERIVED_NAMES`;
- local regression coverage proving the target census does not fall through to “未命名效果 / Unnamed Effect” or a family-only label.

Do not infer a display name by prettifying Trait IDs.
