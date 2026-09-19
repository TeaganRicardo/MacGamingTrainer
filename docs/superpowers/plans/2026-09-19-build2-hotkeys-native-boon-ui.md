# Build 2 Hotkeys and Native Boon UI Implementation Plan

Goal: finish the pre-acceptance Build 2 follow-up without changing debugger lifecycle architecture.

## Completed implementation

- [x] Shortcut v5 derives defaults from `ShortcutAction.uiOrder`, persists only explicit overrides, migrates v3/v4 layouts, and keeps settings order/default order aligned.
- [x] Core/Host generic hotkey feedback: enabled / deferred / disabled.
- [x] Native boon sell through `OpenSellTraitMenu`.
- [x] Direct-add special blessings retained.
- [x] Audited native special three-choice:
  - loot-style: Artemis, Athena, Dionysus, Hades;
  - fixed UpgradeOptions: Arachne, Narcissus, Echo, Medea, Circe, Icarus;
  - Heracles/Moros remain direct-add only.
- [x] No synthetic engine object is created for native choice UI.
- [x] Echo/Arachne/Circe source-specific semantics are retained.
- [x] God Mode uses exact engine-level blocks for `HecatePolymorphStun` and `MiasmaSlow`; no global `ApplyEffect` hook.
- [x] Correctness/Ponytail review completed for the revision-32 follow-up.
- [x] Follow-up PRs were integrated into `feature/post-v0.1-improvements`.
- [x] Revision-32 integrated head passed Linux + macOS Build 2 and produced RC artifact 10578439397.

## Closure audit addition

Interrupted-session review found one real issue: the trainer synthetic source name was assigned before native special-choice eligibility/rarity generation. Hades uses the native source name for `LootData/FieldLootData` and requirement logic.

- [x] RED contract proves native source identity must survive `SetTraitsOnLoot` / `IsGameStateEligible`.
- [x] Runtime fix delays the synthetic bookkeeping name until immediately before opening the native menu.
- [x] Regression became GREEN.
- [x] Runtime revision bumped to 33.
- [x] Revision-dependent tests updated to 33.

## Final integration gate

- [ ] Exact final revision-33 head passes Linux contracts.
- [ ] Exact final revision-33 head passes macOS Build 2.
- [ ] New RC artifact + inner SHA256 recorded.
- [ ] PR #7 / #1 / #11 updated to the new exact artifact.
- [ ] Target-Mac acceptance passes.

The revision-32 RC is superseded for final acceptance. Product remains 0.1 / Build 2 until the manual Phase 0 gate succeeds.
