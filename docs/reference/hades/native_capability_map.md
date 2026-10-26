# Hades I native capability map

## Reference identity

This map is grounded in the user-provided original-content snapshot captured on 2026-10-26: Hades Steam App 1145360, Steam Build 10929685, depot 1145364, depot manifest 6896671991921324741, Content buildinfo 38284. The exact source files are preserved in the original-content reference archive. The hashes below match the snapshot's SOURCE-TREE.sha256 manifest.

## Native owners and feature boundaries

| Capability | Native owner and operation | Expected result | Exists in Hades I? | Trainer status |
| --- | --- | --- | --- | --- |
| Permanent resource gain | RoomManager.lua: AddResource(name, amount, source, args) | Updates GameState.Resources and LifetimeResourcesGained, runs ResourceData.OnAddedFunctionName, updates resource UI and native gain presentation. | Yes | Implemented in this branch as a separate additive action. Existing set_resource remains an absolute edit. |
| Fish pool selection | FishingScripts.lua: GetFish(biome, fishingState); FishingData.lua: BiomeFish | Selects from the game's own fish pool for the selected biome and Good/Perfect result. The native pool includes Tartarus, Asphodel, Elysium, Styx, Secrets (Chaos) and Surface. | Yes | Implemented in this branch as an explicit fish-record action. Good and Perfect select native pools; neither guarantees a particular rarity. |
| Fish collection bookkeeping | FishingScripts.lua: RecordFish(fishName) | Increments GameState.TotalCaughtFish, GameState.CaughtFish and CurrentRun.CaughtFish. | Yes | Implemented in this branch. A partial native failure is reported as outcome-unknown so the one-shot is never automatically replayed. |
| Actual fishing interaction | Interactables.lua: FishingPoint use; FishingScripts.lua: StartFishing / WaitForFishingInput | Runs the timed fishing interaction and marks its room-specific fishing lifecycle. | Yes | Not simulated by the record action. The action does not mark the room's fishing point as completed. |
| Fish reward turn-in | FishingScripts.lua: TurnInFish; FishingData.lua: FishValues | Converts held GameState.CaughtFish into its configured resource awards via AddResource, then clears the held-fish table. | Yes | Not invoked automatically. Recorded fish remain available for the native Chef turn-in interaction. |
| Next chamber selection | RunManager.lua: ChooseNextRoomData; RoomData.lua and RoomData*.lua | Chooses a room using the current room set, linked-room rules, native eligibility and forced-room state. | Yes | Not yet exposed. A safe override must respect the active room set and eligibility and update doors that have already been assigned. |
| Current exit-door assignment | RoomManager.lua: AssignRoomToExitDoor; RunManager.lua: CreateRoom; DebugScripts.lua: Force Next Room & Encounter | Creates and assigns room objects to the offered doors. The shipped debug example rewrites existing OfferedExitDoors after setting ForceNextRoom. | Yes | Not yet exposed. Setting ForceNextRoom alone is insufficient once the current exits already have Room objects. |
| Encounter selection | RunManager.lua: SetupEncounter; RoomManager.lua: StartEncounter; EncounterData.lua and EncounterSets.lua | Resolves a legal encounter, sets it up and starts its native lifecycle. ForceNextEncounter is consumed during selection and cleared on room start. | Yes | Not yet exposed. Encounter overrides must remain one-shot and preserve room/session ownership. |
| Room reward selection | RunManager.lua: IsRoomRewardEligible, ChooseRoomReward, SetupRoomReward; StoreData.lua | Applies ForcedReward / ForcedFirstReward, previously chosen rewards, native eligibility, reward-store selection and store refill rules. | Yes | Not yet exposed. A direct reward override must not silently bypass the native eligibility contract. |
| Reward and pickup spawning | EncounterData.lua event functions; RoomManager.lua reward setup; Interactables.lua pickup interactions; LootData.lua | Spawns room-owned rewards/pickups and invokes their native interactions and bookkeeping. | Yes | Not yet exposed. Routing/eligibility and immediate spawn are separate capabilities. |
| Chaos access | RoomDataSecrets.lua (RoomSetData.Secrets), RoomData.lua secret-door rules, Interactables.lua secret-door cost and use logic | Enters the Secrets room set (the native Chaos region), subject to room/door eligibility, cost and run progression. | Yes | Not yet exposed. Chaos access is a special route, not a generic room-reward type. |
| Scripted events and character interactions | RoomEvents.lua, EventPresentation.lua, NPCData.lua, Interactables.lua | Runs room-specific dialogue, NPC interaction, quest and presentation lifecycles. | Yes | No generic event-spawn operation is established. Each supported event needs an explicit native owner and eligibility contract. |

## Exact source hashes

| Source | SHA-256 |
| --- | --- |
| Scripts/RoomManager.lua | ca379fe0708af778007aef929822e4cfe8cf3a47dd2a3d37bf57e582ddb1b924 |
| Scripts/RunManager.lua | 4b2fc24bee7e89f4cb9efedaafd7c35ef4829df6e047d4f37406f0619273895e |
| Scripts/FishingScripts.lua | a0a52b09dea9e974471e6116101357bb30f0cd34c5c70a3903f3698b9c8f6d0d |
| Scripts/FishingData.lua | 7ac70a238bb389308e9b5e67a0f9dace60114dacb3e12572a65fccd8dedc8592 |
| Scripts/Interactables.lua | 2b862c615ae29af2e31e499a7b88b9c996c5c6ee1859683c608e698ffddf6549 |
| Scripts/RoomData.lua | 2998e4109ee5275dcfade2e928d33e8ba386d13cefc196e7d96a9e0ee52ebec6 |
| Scripts/RoomDataSecrets.lua | 045123252aaa5048d9ea8a1bd0473377f70ce40c5ffb8dfe18326969b970000a |
| Scripts/EncounterData.lua | 4fafd05c105cae9e92172813a0dae070599359d2efa4636d19851c9ffe96291e |
| Scripts/StoreData.lua | db7edc1bda6fb69ec3512a44ec1843bfa2e75d9aa9230853c9201abf14b89311 |
| Scripts/AwardMenuScripts.lua | e0bbffc5c6bafc136c1167d75d1adf2bedd9aa47dd93e2612520e46b5498ef0d |
| Scripts/DebugScripts.lua | 2ef3006b85bff7930b32900a5d6f02a013447a7932b0eb2179bf254b5f7375ee |

This is a source inventory for the supported image, not a claim that all listed workflows have been implemented. The resource and fish actions in this branch are the first delivered slice of #572. Rooms, rewards, encounter overrides and Chaos routing remain open work and must retain their native eligibility, transition and recovery semantics.
