# Build 2 Hotkeys and Native Boon UI Implementation Plan

Goal: finish the pre-acceptance Build 2 follow-up without changing debugger lifecycle architecture.

Architecture: Core owns generic hotkey feedback only. Hades II owns shortcut semantics and all game-native boon/God Mode behavior. Native modal actions are one-shot and never preference-replayed.

## Completed TDD tasks

- [x] Shortcut v5: derive defaults from ShortcutAction.uiOrder, persist only explicit overrides, migrate v3/v4 layouts, keep settings list and 1–9/A–Z defaults aligned.
- [x] Generic hotkey feedback: Core enabled/deferred/disabled vocabulary and macOS system sounds; Hades maps actual async results after command completion.
- [x] Native boon sell: one-shot open_sell_traits uses thread(OpenSellTraitMenu, {}) and native removal/payout rules.
- [x] Native special choice: direct-add retained; audited 10-source native three-choice path uses sourceId/nativeChoice, OpenUpgradeChoiceMenu, no synthetic engine object, with Echo/Arachne/Circe functional handling.
- [x] God Mode hostile control immunity: exact engine-level effect blocks for HecatePolymorphStun and MiasmaSlow, with symmetric cleanup and no global ApplyEffect hook.

## Final integration gate

- [ ] Exact follow-up head passes Linux contracts.
- [ ] Correctness + Ponytail review finds no Critical/Important issue.
- [ ] Follow-up PR is integrated into feature/post-v0.1-improvements, never main.
- [ ] Exact integrated parent head passes Linux contracts.
- [ ] Exact integrated parent head passes macOS Build 2: host policy harness, Hades log watcher harness, arm64 build, version/module package validation, strict codesign, packaging and artifact upload.
- [ ] Record artifact ID and inner RC SHA256.
- [ ] Update PR #7 and Phase 0 issues with the new manual acceptance checklist.

Constraints: product remains 0.1 / Build 2; no periodic runtime polling; no second debugger attachment; no original game-file modification; no automatic replay of native modal commands.
