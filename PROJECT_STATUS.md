# MacGamingTrainer Project Status

## Current baseline

- Product version: 0.1
- Development build: 2
- Latest release: v0.1 / Build 1
- Stable branch: main
- Active development branch: feature/post-v0.1-improvements
- Host protocol: 5
- Hades II module protocol: 5
- Desired-state schema: 3
- Profile schema: 4
- Hades II Lua source revision: 25
- Target game build last verified: Hades II 1.139672 / Steam build 24556151

## Verified on target Mac

- Native arm64 build succeeds.
- App bundle passes codesign --verify --deep --strict.
- com.apple.security.cs.debugger=true entitlement is present.
- Hades process discovery works without attaching.
- Runtime diagnostics revision 26 is verified on target Mac; a valid Hero object was confirmed both in Crossroads and in a real run.
- Main-menu waiting quit regression is fixed: quit persists desired-off state, disconnects best-effort, and does not block app termination.
- Save backup 修改器测试 was restored successfully; a pre-restore backup was created automatically.
- Real-run acceptance reached status=ready / scene=run with Hero object 40000, 97 resources, 129 rewards, 11 stats and 5 elements.
- All 83 NPC trait entries in the observed catalog resolved official Chinese names; none required fallback naming.
- forceLegendary and forceDuo OFF/ON/both state transitions were exercised in a real run; boon rarity hooks engaged and returned to fully disabled state after cleanup.
- Selene SpellDrop first-Hex spawn path is confirmed operational in-game.

## Verified in Build 2

- Full Python regression suite passes on the target Mac; Swift parse and native arm64 build pass; strict codesign verification passes.
- Hades resident Lua revision 26 reloads correctly from the Build 2 bundle.
- Live run catalog: 129 rewards and 97 resources; no list entry has an empty English label or an internal identifier standing in for English.
- SpellDrop and TalentDrop both resolve to the Selene special-reward section. TalentDrop uses the official 繁星之路 · Path of Stars label.
- Native TalentDrop interaction was verified without OCR: after pickup, ActiveScreens["TalentScreen"] was present, source was TalentDrop, current Hex was Leap, and 6 Talent points were available.
- Profile schema 4 shortcut chords pass Linux Foundation-level semantic tests and the full target-Mac regression suite.
- macOS synthetic key-event validation captured and registered a non-default Control+Shift+K chord as ⌃⇧K.
- Shortcut rows with no badge collapse instead of reserving the former 52pt empty slot.
- Fire/Water/Earth/Air/Aether compile with distinct SF Symbols and semantic colors.

## In progress

1. Passive waiting -> ready transition: bounded two-shot status probe per connection lifetime at 15s / 30s; no repeating timer. Full main-menu-to-run passive acceptance remains open.
2. Manual visual acceptance only:
   - confirm the 19-row shortcut settings sheet interaction/spacing in the actual UI;
   - confirm the five element icons/colors at normal display scale.

## Deferred until correctness is stable

- LLDB attach latency profiling and optimization.

## Non-regression constraints

- No periodic LLDB/Lua polling.
- No unsafe replay of outcome-unknown non-idempotent mutations.
- No legacy Profile compatibility layer.
- No 4+ boon-choice UI/hack.
- Hades-specific semantics remain outside Core.
- Exit must never be permanently blocked by cleanup failure.
