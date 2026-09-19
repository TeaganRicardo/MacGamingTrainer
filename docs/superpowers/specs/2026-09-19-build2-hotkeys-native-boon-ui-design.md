# Build 2 Hotkeys and Native Boon UI Design

## Scope

This follow-up keeps product version at 0.1 / Build 2 and adds four related changes without changing the existing debugger lifecycle architecture:

1. Host/Core-owned global-hotkey feedback sounds.
2. Automatic default shortcut reflow when Hades actions are added or reordered.
3. A native Hades II boon-removal entry point.
4. A native Hades II special-blessing three-choice entry point while retaining direct-add behavior.

The already-landed single-boundary preference replay fix remains unchanged.

## 1. Generic hotkey feedback

Core owns a game-agnostic TrainerHotkeyFeedback enum with exactly three success states:
- enabled: requested effect is active now.
- deferred: requested effect was accepted but is waiting for a valid game scene/runtime state.
- disabled: requested effect is now off.

Core also owns TrainerHotkeyFeedbackPlayer, implemented with macOS system sounds only. It accepts the enum and plays three distinct short sounds. No game names or Hades state appear in Core.

A game module decides which feedback state applies only after its command completes. Failed/rejected hotkeys do not play a success-state sound.

Hades II maps toggle completion to:
- target false + successful response -> disabled;
- target true + activeFeatures[key] == true -> enabled;
- target true + successful response but active=false and dormant=true / scene unavailable -> deferred.

Non-toggle shortcut actions do not emit these three toggle sounds in this iteration.

## 2. Automatic shortcut layout

ShortcutAction.uiOrder remains the single semantic ordering source.

Hades2ShortcutStore must stop persisting computed defaults. Persistence stores only explicit user overrides. Therefore:
- a fresh install always maps uiOrder continuously through HotkeyChord.controlOptionDefault(index:);
- adding or moving an action automatically reflows all non-overridden actions;
- explicit user changes remain fixed;
- imported profile shortcuts are explicit overrides and remain fixed;
- collision repair moves only non-overridden/default actions where possible.

Migration from layout v4 detects whether each persisted chord equals the v4 default for that action. Equal values are discarded as derived defaults; differing values become explicit overrides. Layout version increments to 5.

The visible shortcut settings list uses ShortcutAction.uiOrder, so key labels and list order remain aligned.

## 3. Native boon removal

Add a Hades module command open_sell_traits. It is valid only in a live run, outside transitions, with no conflicting active screen.

Runtime implementation calls the game's own OpenSellTraitMenu({}). The game remains authoritative for:
- which traits are sellable;
- the three offered choices and reroll behavior;
- RemoveWeaponTrait cleanup;
- money payout;
- sold-trait counters and presentation.

Trainer does not synthesize a Charon Well / Pool object and does not implement its own trait-removal list.

UI adds one clearly labeled action in build/boon management: 打开祝福出售界面.

## 4. Native special-blessing three-choice

Existing direct-add remains available.

Add a second action mode for special blessings: 原生三选一. The selected special trait provides a stable sourceId; the catalog also publishes nativeChoice so Swift never infers capability from localized labels.

Runtime command open_special_choice receives source and is limited to current-game sources whose normal reward can be reproduced by the generic native choice handler without missing functional preprocessing:
- Narcissus -> NPCData.NarcissusBenefitChoices
- Echo -> NPCData.EchoBenefitChoices (native flow forces Epic before Dream overrides)
- Medea -> NPCData.MedeaCurseChoices
- Icarus -> NPCData.IcarusBenefitChoices

Arachne and Circe remain direct-add only in this iteration:
- Arachne's normal flow requires ArachneArmorApply / SetupCostume after selection.
- Circe's DoubleFamiliarTrait path prepares SessionMapState data before opening the menu.
Calling only the generic menu for either source could show a valid-looking choice whose effect is incomplete.

The trainer shallow-copies the game's current NPC/choice data, filters options through IsGameStateEligible, selects up to three using the game's priority/random rules, and opens OpenUpgradeChoiceMenu. Because the generic native handler requires screen.Source.ObjectId, the trainer creates one built-in InvisibleTarget as a temporary, non-visible source anchor. It is not a reward object and is destroyed/removed from room state after the menu closes.

OpenUpgradeChoiceMenu must run through the game's thread(...) scheduler. The LLDB command only validates/builds the request and schedules the game thread, then returns immediately; player input must never hold the debugger boundary open.

Trainer-specific LootPickups and LootChoiceHistory bookkeeping created by the virtual source is restored after the menu closes. The chosen trait itself remains native: HandleUpgradeChoiceSelection / AddTraitToHero and normal trait side effects are game-owned.

Selene SpellDrop and Chaos TrialUpgrade keep their existing native loot spawn paths rather than being forced through the NPC choice bridge.

The UI disables 原生三选一 when the selected entry/source has nativeChoice=false.

## Safety and lifecycle constraints

- No new timer or periodic Lua polling.
- No second debugger attachment.
- Each user action crosses at most one LLDB/Lua boundary.
- Opening a native modal screen is non-idempotent and is never replayed automatically after uncertain transport failure.
- Do not modify original Hades II files.
- No Hades-specific behavior is added to Core beyond generic feedback types/player.
- Product remains 0.1 / Build 2 until Phase 0 manual acceptance passes.
