# Current-run effect naming governance

Target: Hades II **1.143476** / Steam build **25481925**  
Status: **active implementation — final in-game acceptance pending**

This document governs how concrete runtime traits are named when they can appear in the current-run effect manager. It defines the rules and evidence boundary only; it does not duplicate the row-level naming data.

## Single source of truth

There are two name owners, but only one stored Trainer exception registry:

- Native Game Terms are resolved dynamically from the installed target build through the localization loader, including SJSON `InheritFrom` chains.
- Native Trait Tray title identity comes from `GetTraitTooltipTitle` / `CustomTitle` when the runtime exposes a more appropriate player-facing title than `trait.Name`.
- Trainer-owned substitute labels and Arcana function descriptors live only in `catalog._CURRENT_RUN_DERIVED_NAMES`.
- Family labels are presentation/grouping vocabulary, not a substitute-name registry.

Do not create a second CSV, document table, fixture list, or other hand-maintained copy of `_CURRENT_RUN_DERIVED_NAMES`.

## Resolution order

1. Keep runtime identity (`trait.Name`, owner/source IDs and instance ID) internal.
2. Ask the resident runtime for the same title identity used by the native Trait Tray.
3. Resolve the target game's bilingual `DisplayName`, including SJSON inheritance.
4. If the concrete mounted effect still has no readable/sufficiently specific title, use the bilingual Trainer Product Term in `_CURRENT_RUN_DERIVED_NAMES`.
5. Arcana is one UI section. Its item label is **native card title · Trainer function descriptor**.
6. Generic family labels such as “其他效果 / Other Effect” are forward-compatibility fallbacks only. No known concrete mounted effect in the supported target may rely on a family-only label as its final name.

Trait IDs must never be prettified into user-facing names.

## Current-target census

The census was re-run against the installed **1.143476 / 25481925** target rather than inferred from the retained 1.139672 snapshot.

The active `TraitData` assembly was enumerated from every `OverwriteTableKeys( TraitData, ... )` / `TraitSetData` source, including the non-`TraitData*.lua` additions in `BiomeStateData.lua` and `FamiliarData.lua`. The apparent extra `CastProtectionMetaUpgrade` is inside a Lua block comment and is not installed into `TraitData`.

Result: **670 active unique TraitData IDs**. The identity set matches the retained 1.139672 snapshot, but the installed target remains the authority.

An exact-ID search of all 670 active IDs against the installed target's current text trees establishes the readable native-title set directly:

- **zh-CN:** 604 IDs have a `DisplayName` / `InheritFrom` record; `ElementalEssence` is icon-only, leaving **603 readable native titles**.
- **English:** 608 IDs have a `DisplayName` / `InheritFrom` record; `AirEssence`, `FireEssence`, `EarthEssence`, `WaterEssence`, and `ElementalEssence` are icon-only, likewise leaving **603 readable native titles**.

The shared readable set is therefore **603 IDs in both supported UI languages**, derived from the current target itself rather than inherited from the old snapshot.

The remaining naming boundary is:

- **6** concrete mounted dummy-weapon traits use native `CustomTitle` and therefore resolve to the equipped weapon's official name.
- **22** concrete mounted effects have no readable/sufficiently specific standalone native title and use `_CURRENT_RUN_DERIVED_NAMES`. Familiar rows store only the function descriptor and compose it with the dynamically resolved native Familiar owner; `ElementalEssence` belongs here because its native `DisplayName` is icon-only.
- **39** no-title IDs are base/debug/template scaffolding with no independently mounted user-facing identity.
- **25** Arcana mounted traits are among the 603 native-title IDs. Their native title identifies the card, while the same canonical registry supplies the concise function suffix required to distinguish the mounted effect.

Therefore the stored Trainer registry has **47 entries: 22 substitute names + 25 Arcana function descriptors**. The registry itself is the row-level source of truth; this document records only the accounting and rules.

## Evidence seams

Representative target evidence used to establish the boundary:

- `TraitData*.lua`, `BiomeStateData.lua`, and `FamiliarData.lua` for the active TraitData identity census;
- `TraitText.*.sjson` and the target text tree for bilingual native titles and SJSON inheritance;
- `TraitData.lua` + native weapon text for the six dummy-weapon `CustomTitle` identities;
- `MetaUpgradeData.lua` / `TraitData_MetaUpgrade.lua` + official Arcana descriptions for all 25 Arcana descriptors;
- `FamiliarData.lua` + `FamiliarShopData.lua` for hidden Familiar upgrade effects;
- `ConsumableData.lua` + `TraitData_Essence.lua` for mounted elemental effects;
- `RoomLogic.lua` + `TraitData.lua` for Max Life, Max Magick and Armor state;
- `BiomeStateData.lua` + `BiomeStateLogic.lua` for normal/rain environment effects.

The frozen 1.139672 generated census is useful only as a historical cross-check and candidate seed. It is not current execution authority.

## Change rule

Adding or changing a Trainer-derived current-run name requires, in the same focused change:

- target-build evidence for the mounted effect or Arcana semantics;
- one explicit bilingual Trainer Product Term pair;
- an update to `catalog._CURRENT_RUN_DERIVED_NAMES`, the single stored registry;
- local regression coverage that proves the label is bilingual, recognizable, and not a Trait ID, “未命名效果 / Unnamed Effect”, or a family-only fallback.

If the target build gains a native title for an exception, prefer the native term and remove the redundant Trainer entry instead of preserving both.
