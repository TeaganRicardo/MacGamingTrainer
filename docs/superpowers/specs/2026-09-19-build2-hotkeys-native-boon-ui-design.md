# Build 2 Hotkeys and Native Boon UI Design

## Scope

This follow-up keeps product version at 0.1 / Build 2 and adds four related changes without changing the existing debugger lifecycle architecture:

1. Host/Core-owned global-hotkey feedback sounds.
2. Automatic default shortcut reflow when Hades actions are added or reordered.
3. A native Hades II boon-removal entry point.
4. A native Hades II special-blessing three-choice entry point while retaining direct-add behavior.
5. God Mode immunity to audited hostile control/environment effects that bypass normal Damage routing.

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

The second action, 原生三选一, is source-based. The selected catalog row carries stable sourceId and nativeChoice fields; Swift never infers capability from localized names.

Audited native-choice sources in Hades II 1.139672:
- loot-style native choice through SetTraitsOnLoot: Artemis, Athena, Dionysus, Hades;
- fixed UpgradeOptions choice data: Arachne, Narcissus, Echo, Medea, Circe, Icarus;
- Heracles and Moros remain direct-add only because no equivalent native three-choice flow was found.

The trainer shallow-copies current game NPC/choice data and opens OpenUpgradeChoiceMenu on the game's thread scheduler so player input never holds an LLDB boundary. The synthetic source uses a non-engine sentinel ObjectId (-1) only because HandleUpgradeChoiceSelection indexes RoomRequiredObjects[source.ObjectId]; it never creates or destroys an engine object and never takes room-object ownership.

Functional source-specific behavior is preserved where the generic menu alone is insufficient:
- Echo keeps Epic choice rarity and LastReward fallback semantics;
- Arachne runs SetupCostume after the native choice closes;
- Circe preserves DoubleFamiliarTrait preprocessing through SessionMapState.

Trainer-created LootPickups/LootChoiceHistory bookkeeping is restored after the menu closes. The selected trait itself is still applied by native HandleUpgradeChoiceSelection / AddTraitToHero.

Selene SpellDrop and Chaos TrialUpgrade keep their existing native spawn paths instead of being forced through this bridge.

The UI disables 原生三选一 when nativeChoice=false.

## 5. God Mode hostile effect immunity

God Mode already stops the outer Damage path and owns the trainer invulnerability flag. Two audited hostile effects bypass that damage path and alter player control directly:
- HecatePolymorphStun;
- MiasmaSlow.

God Mode uses the game's engine-level AddEffectBlock / RemoveEffectBlock API for exactly those two names and clears an already-active instance when enabled. This catches projectile/terrain application without a broad ApplyEffect hook.

The denylist deliberately excludes:
- ChaosStun, because it is a player-accepted Chaos curse;
- ChronosPolymorphStun, because it appears in scripted presentation/progression paths;
- MedeaPoison, whose damage remains covered by the existing Damage route;
- unrelated buffs, slows and player effects.

## Safety and lifecycle constraints

- No new timer or periodic Lua polling.
- No second debugger attachment.
- Each user action crosses at most one LLDB/Lua boundary.
- Opening a native modal screen is non-idempotent and is never replayed automatically after uncertain transport failure.
- Do not modify original Hades II files.
- No Hades-specific behavior is added to Core beyond generic feedback types/player.
- Product remains 0.1 / Build 2 until Phase 0 manual acceptance passes.
