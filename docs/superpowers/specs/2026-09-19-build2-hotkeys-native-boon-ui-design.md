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

Add a second action mode for special blessings: 原生三选一. The selection in Trainer identifies a special source/family, not one exact trait. For a selected special trait, Trainer derives its sourceId and asks runtime to open the native source choice screen.

Runtime command open_special_choice receives source. It supports only source IDs that can be backed by current game data and native choice configuration.

Implementation reuses the game's own source choice definitions and OpenUpgradeChoiceMenu:
- Arachne -> NPCData.ArachneCostumeChoices
- Narcissus -> NPCData.NarcissusBenefitChoices
- Echo -> NPCData.EchoBenefitChoices
- Medea -> NPCData.MedeaCurseChoices
- Circe -> NPCData.CirceBlessingChoices

Where the game exposes a dedicated native choice function with required preprocessing, runtime calls that function rather than duplicating its logic. Sources without a complete native three-choice path in installed game data remain direct-add only.

Selene SpellDrop and Chaos TrialUpgrade already have native loot objects and remain on their existing spawn path rather than being forced through NPC choice data.

The UI disables 原生三选一 when the selected entry/source lacks native-choice capability.

## Safety and lifecycle constraints

- No new timer or periodic Lua polling.
- No second debugger attachment.
- Each user action crosses at most one LLDB/Lua boundary.
- Opening a native modal screen is non-idempotent and is never replayed automatically after uncertain transport failure.
- Do not modify original Hades II files.
- No Hades-specific behavior is added to Core beyond generic feedback types/player.
- Product remains 0.1 / Build 2 until Phase 0 manual acceptance passes.

## 5. God Mode environmental/control immunity

God Mode retains the existing outer Damage hook and unit invulnerability, and additionally blocks only audited hostile Hero effects that bypass damage/invulnerability:
- HecatePolymorphStun (Hecate hostile polymorph pipeline)
- MiasmaSlow (Fields/Mourning miasma terrain slow)

The runtime hooks ApplyEffect only while God Mode is active, only when DestinationId is the current Hero, and only for the explicit denylist above. Enabling God Mode also clears those two effects if already present. Disabling restores the original ApplyEffect function and does not suppress unrelated debuffs, player buffs, TimeSlow, or generic SPEED effects.

The existing Damage hook already covers ordinary enemy and environmental damage entering Damage(); no second damage path is added unless a concrete bypass is proven by tests/logs.
