# Batch A Native Modal Correctness Design

## Goal

Fix the two failed native modal paths from the revision-35 acceptance run without touching game speed, God Mode, notification audio, or connection timing.

The candidate must:
- open the native boon-sell screen from an arbitrary active run room and allow normal Cancel/Exit after zero or more sales;
- expose one `触发原生三选一` item inside each supported special-blessing source group rather than a separate global button;
- open a functioning native three-choice screen for the ten audited sources;
- keep direct-add entries unchanged;
- keep Heracles and Moros without a native-choice action because no audited native three-choice flow exists.

## Root cause: native boon selling

`OpenSellTraitMenu()` deep-copies `ScreenData.SellTraits`. Its Close button calls `CloseStoreScreen`.
`CloseStoreScreen()` assumes `CurrentRun.CurrentRoom.Store.StoreOptions` exists before generic screen cleanup.
That assumption is valid for a store-owned presentation but false when the trainer opens the sell screen in an arbitrary run room.
`HandleSellChoiceSelection()` depends on `CurrentRun.CurrentRoom.SellOptions`, so selling can succeed while Cancel/Exit fails.
The trainer must not fabricate `CurrentRun.CurrentRoom.Store`.

## Root cause: native special choices

Revision 35 looks up both the NPC source and fixed-choice payload in `NPCData`, but the installed game exposes them elsewhere:
- runtime NPC source objects are in `EnemyData`;
- fixed choice payloads are under global `PresetEventArgs` in `NPCData.lua`.

The game's narrative records pass `PresetEventArgs.ArachneCostumeChoices`, `PresetEventArgs.NarcissusBenefitChoices`, and the corresponding Echo/Medea/Circe/Icarus values into their native choice functions.
## Design 1: trainer-owned sell close handler

Keep `OpenSellTraitMenu()` and all native sell option/sale behavior.
For the trainer-opened instance only:
1. Deep-copy `ScreenData.SellTraits`.
2. Replace only the Close button's `OnPressedFunctionName` with a trainer-owned global close function.
3. Temporarily install that copied screen definition while `OpenSellTraitMenu()` runs on its game thread.
4. Restore the original `ScreenData.SellTraits` after the native function returns or errors.

The trainer close function delegates to native `CloseStoreScreen()` only when a real room Store exists. Otherwise it performs the equivalent generic screen cleanup without touching Store state.

## Design 2: correct native special-choice data sources

Retain the existing revision-35 synthetic choice flow and non-blocking game-thread execution. Do not invoke portrait/dialogue narrative functions.
Use `EnemyData[definition.npc]` for source data and `PresetEventArgs[definition.choices]` for fixed-choice data.
Deep-copy the NPC source before choice generation because `SetTraitsOnLoot()` and the choice screen mutate source fields.
Preserve Arachne costume handling, Echo last-reward behavior, Circe familiar preprocessing, dream-run rarity, and temporary loot-history bookkeeping.
Runtime source changes require revision 36.

## Design 3: per-source native-choice entries in Swift

Do not add a backend protocol or schema. Existing `sourceId` and `nativeChoice` catalog fields are sufficient.
Derive one synthetic `BoonOption` per distinct supported special source with id `native-choice:<sourceId>`, kind `native_choice`, and label `触发原生三选一`.
Copy source/section/sort metadata from a representative boon and sort this action before that source's concrete boon entries.
The special picker displays these synthetic entries with normal boons and removes the standalone bottom native-choice button.
One model action routes `native_choice` to `open_special_choice(sourceId)` and normal entries to existing direct `spawn_reward`.
The `spawnSpecial` hotkey uses the same action.
Heracles/Moros get no synthetic action because their catalog rows have `nativeChoice == false`.

## Non-goals
- No game-speed changes.
- No God Mode/debuff changes.
- No notification sound changes.
- No connection timing changes.
- No new Core/Host abstraction.
- No fabricated engine NPC objects or fake room Store state.
