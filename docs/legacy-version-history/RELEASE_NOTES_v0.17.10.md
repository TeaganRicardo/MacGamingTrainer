# v0.17.10

App version: **0.17.10**  
Build: **33**  
Hades II Lua revision: **21**

## Critical regression fixes

- Removed v0.17.9's automatic 4-second Lua `status` polling. Each status request crosses the LLDB boundary and can pause Hades II; the live log showed repeated 0.2–1.3 s calls and an eventual boundary timeout. Runtime presentation now refreshes only on user-driven backend interactions or explicit refresh.
- Save Manager no longer enters its blocking loading state while the staged-restore watcher performs its background `scan`. Actual backup/restore/delete/rename operations still block their own controls.
- Reworked **next room reward** around the current game's exit-door flow. Hades II chooses rewards separately for every offered door; the trainer now keeps the override armed for all eligible exit doors and consumes it only when `StartRoom` confirms that the player entered the next room.
- If exit rewards already exist when the user selects an override, all ordinary offered doors are patched immediately, `CurrentRun.CurrentRoom.OfferedRewards` is synchronized, and existing preview objects are refreshed in-place rather than duplicated.
- Boss/story/shop/devotion/empty/no-reward paths remain native and are not replaced.

## Compatibility

Host protocol remains v5 and Hades module protocol remains v4. Lua revision is 21 because next-room runtime hook behavior changed.
