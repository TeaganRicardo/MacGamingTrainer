# Hades II 1.143476 special-NPC and Shop routing research (#453)

## Scope and evidence identity

This note records the research phase of #453. It does not authorize a runtime implementation.

Supported target:
- Hades II 1.143476.
- Steam build 25481925.
- arm64 executable UUID recorded by current project status: 35CD2E50-2D78-3A63-835B-3EB1224C6D65.
- Native-source evidence: the 2026-09-30 target-build snapshot `hades2-catalog-evidence-1.143476-steam-25481925`, which contains the complete Content/Scripts tree, non-localization Game SJSON data, English and Simplified Chinese text trees, the Steam app manifest, Info.plist, and SHA-256 manifest.
- Independent archive identity checks: `metadata/Info.plist:23-24` reports 1.143476; `metadata/appmanifest_1145350.acf:12,20` reports build 25481925.
- Trainer baseline inspected: `main@1868b676943314e0e343fb1b03405156bf6822d9`.

All native conclusions below are source inspection of that exact target-build snapshot. No game launch, save mutation, or visual acceptance was performed.

## Executive finding

“Special NPC”, “Shop”, “room reward”, and “direct reward interaction” are separate native owners.

The current Trainer next-room feature operates at the reward-selection layer. It hooks `ChooseRoomReward`, mutates `room.ChosenRewardType`, and intentionally rejects native Story and Shop rewards. By the time that seam runs, each exit door has already been assigned a specific next room. For many special NPCs and Charon shops, the room identity is the capability: the NPC/shop is attached to a Story room, a dedicated Shop room, or a special transition room. Other NPCs are injected later as encounters into an otherwise ordinary combat room.

Therefore, extending the existing reward enum with Story, Shop, or NPC names would target the wrong native seam.

The product needs at least two routing concepts:
1. room routing — choose/offer a native Story or dedicated Shop room;
2. encounter routing — choose a special field encounter inside a selected eligible combat room.

Direct reward interaction is already a third, distinct capability: the current `open_special_choice` command opens the audited native reward/choice flow without making the player meet or route to the NPC.

## Native generation pipeline

The relevant native order is:

1. `ChooseNextRoomData` selects a next-room definition from the biome RoomSet and linked-room rules. `IsRoomEligible` applies route, depth, count, tag, and GameState requirements; `IsRoomForced` handles native force rules. See `Content/Scripts/RunLogic.lua:782-1013`.
2. When exits unlock, `DoUnlockRoomExits` calls `ChooseNextRoomData` for each offered exit, then creates the room with both reward and encounter selection skipped. See `Content/Scripts/RoomLogic.lua:3871-4009`.
3. Reward selection then runs for that already-selected room through `ChooseRoomReward`, and the room is assigned to its door via `AssignRoomToExitDoor`. See `Content/Scripts/RoomLogic.lua:3958-3986,4098-4134`.
4. After the player actually chooses a door and leaves the current room, the game calls `ChooseEncounter` if the selected room does not already own an encounter. `IsEncounterEligible` applies reward compatibility, appearance limits, cooldowns, room tags, and GameState requirements. See `Content/Scripts/RunLogic.lua:1022-1095,1660-1722` and `Content/Scripts/RoomLogic.lua:4376-4394`.
5. `RecordEncounter` marks encounter occurrence only after that selected-door encounter is chosen. See `Content/Scripts/RoomLogic.lua:4453-4462`.
6. Shop objects are materialized after the room becomes current by `RunShopGeneration`, using room-owned store data and chance flags. See `Content/Scripts/StoreLogic.lua:436-451`.

One important asymmetry follows from this pipeline. `CreateRoom` increments room-creation counts when an exit is offered, even when encounter/reward selection was skipped. Encounter occurrence counters, however, are not consumed until the player actually chooses that door and an encounter is selected. This makes an “offer this Story/Shop room once” token materially different from a “next eligible field encounter once” token.

The native debug force seams also confirm the ownership split: `ForceNextRoom` bypasses ordinary room eligibility inside `ChooseNextRoomData`, while `ForceNextEncounter` bypasses ordinary encounter eligibility inside `ChooseEncounter`. They demonstrate technical feasibility, not safe default product semantics.

## Fixed Story-room and transition-room NPCs

The ordinary biome RoomSets contain weighted room candidates; duplicate entries are weights among whatever remains eligible, not fixed encounter probabilities. See `Content/Scripts/RoomSets.lua:18-24,58-66,101,128-134,187-190,252-256,287-292,330,349`.

| NPC / scene | Native route owner | Principal eligibility / forcing | Interaction owner |
| --- | --- | --- | --- |
| Arachne | `F_Story01` | Story reward, no reroll, max one creation/run, force if unseen 3 runs; biome depth 4-8; historical F boss entered; Artemis first meeting must exist historically but not have occurred in current run; blocked by Standard Package bounty. `RoomDataF.lua:3140-3172` | `Story_Arachne_01`; native Arachne costume choice |
| Narcissus | `G_Story01` | Story reward, no reroll, max one creation/run, force if unseen 6 runs; biome depth 3-6; historical G boss entered; bounty restriction. `RoomDataG.lua:2536-2562` | `Story_Narcissus_01`; native benefit choices |
| Echo | `H_Bridge01`, not a standalone Story room | Bridge is always forced after two and before three ordinary H rooms, max one creation/run. Its reward becomes Story only after historical H boss and while normal story conditions apply; otherwise Shop. `RoomDataH.lua:787-862` | `Story_Echo_01` competes in the bridge encounter pool with `BridgeShop` and `BridgeNemesisRandomEvent`. Echo is weighted four times, BridgeShop twice, Nemesis event once. |
| Hades | `I_Story01` | Story reward, max one creation/run, force-if-unseen 6, force depth 2-4; requires >1 I_Intro entry, no conflicting special room already created from the current room, and valid route/offered-door conditions. After Chronos completion, an unseen first Hades room can become always-forced when exactly one exit exists. Blocked by bounty/HecateMissing/post-ending gate. `RoomDataI.lua:3026-3183` | `Story_Hades_01` |
| Medea | `N_Story01` | Story reward, max one creation/run, force-if-unseen 3; Ephyra spoke/return route; requires historical Heracles first meeting and current N route having reached N_PreHub or Chaos; bounty restriction. `RoomDataN.lua:3609-3730` | `Story_Medea_01` |
| Circe | `O_Story01` | Story reward, max one creation/run; requires historical O boss, >1 O biome visit, no Icarus first meeting this run, encounter depth >3, biome depth <=5, bounty restriction. At biome depth 5, Story or Shop is forced if neither has been entered. `RoomDataO.lua:2738-2886` | `Story_Circe_01` |
| Dionysus | `P_Story01` | Story reward, max one creation/run; requires historical P boss, no Athena first meeting this run, encounter depth >2, biome depth <=7, bounty restriction. `RoomDataP.lua:2240-2354` | `Story_Dionysus_01` |

Two nearby scene families should not be silently grouped into the same product target:
- `Q_Story01` is a linked, no-reward palace narrative route using `Story_Palace_01`; it is not an ordinary special-reward encounter. See `RoomDataQ.lua:2866-2905`.
- Post-boss/narrative Story scenes such as the F Chronos scene likewise are story progression, not a reward-giver routing feature.

### Fields bridge is structurally special

`H_Bridge01` proves why “NPC probability” cannot be one universal control. The room itself is mandatory at a narrow route point. Echo versus Charon versus Nemesis is decided later by encounter eligibility and weighted selection inside that one room. For this family, forcing the room does not force Echo, and forcing Story as a reward still leaves Echo and Bridge Nemesis as separate eligible Story encounters.

## Field-encounter NPCs

Several NPC appearances are encounter injections into otherwise ordinary combat rooms. Their owner is `ChooseEncounter`, not `ChooseNextRoomData`.

The shared `NoRecentFieldNPCEncounter` requirement blocks another field-NPC encounter for six prior rooms across Artemis, Nemesis, Heracles, Icarus, and Athena. See `Content/Scripts/RequirementsData.lua:1495-1538`.

| NPC | Regions / encounter family | Key native gates |
| --- | --- | --- |
| Artemis | F, G, N; `ArtemisCombat*` | Intro completion for normal encounters, unused NPC this run, biome depth >=4, shared field-NPC cooldown, bounty/surface-route restrictions, and rejection of Boon/Spell/Devotion/Hermes/Hammer rewards. Intro and fallback variants add history and prior-run spawn conditions. `EncounterData_Artemis.lua` |
| Athena | P; `AthenaCombat*` | Similar encounter-level gating, shared field-NPC cooldown, Athena-specific history/keepsake rules, incompatible reward filtering; intro plus fallback P variants. `EncounterData_Athena.lua` |
| Icarus | O and P; `IcarusCombat*` | NPC unused this run, biome depth >=3, shared cooldown, bounty restriction, incompatible reward filtering, region/history/tag rules. O intro and later P appearances have distinct progression gates. `EncounterData_Icarus.lua` |
| Heracles | N, O, P; `HeraclesCombat*` | No Heracles field encounter already completed this run, intro history, shared field-NPC cooldown plus a Heracles-specific 20-room/3-run shopping/story cooldown, bounty restriction. Later O/P variants require additional history. `EncounterData_Heracles.lua`; `RequirementsData.lua:1460-1483` |
| Nemesis | F, G, H, I plus random-event variants | Intro/free-item history, no Nemesis combat in current run, depth gates, shared cooldown plus a much stronger Nemesis-specific prior-room/biome cooldown, bounty/Hecate restrictions, incompatible reward filtering. H also has the bridge random event. `EncounterData_Nemesis.lua`; `RequirementsData.lua:1434-1459` |

Arachne also has `ArachneCombatF/G` cocoon encounters with a five-room cooldown. Those encounters use Arachne presentation/options but are not equivalent to routing to `F_Story01` to meet the reward-giver NPC. See `EncounterData_Arachne.lua` and `RequirementsData.lua:1484-1493`.

The normal EncounterSets contain repeated variants for weighting and fallback behavior. A generic “set special-NPC chance to X%” would have to replace multiple eligibility-conditioned weighted pools and would not map cleanly to the native model.

## Shop taxonomy

“Shop” also has multiple native forms.

### Dedicated/random Charon route rooms

These are proper room-routing targets and own a Shop encounter/reward plus a WorldShop:
- `F_Shop01`: max one creation/run, native force depth 4-6, requires at least two exits, biome depth <=6. `RoomDataF.lua:2881-2906`.
- `G_Shop01`: max one, force depth 3-6, at least two exits, biome depth <=5. `RoomDataG.lua:1797-1824`.
- `N_Shop01`: Ephyra spoke/return route; requires the surface-penalty cure and N route having reached N_PreHub or Chaos. `RoomDataN.lua:1981-2020`.
- `O_Shop01`: max one, encounter depth >3, biome depth <=5; at depth 5 it participates in the native Shop-versus-Story force rule. `RoomDataO.lua:739-787`.
- `P_Shop01`: max one, encounter depth >4, biome depth <=7. `RoomDataP.lua:668-701`.

`I_Shop01` exists in RoomSets but is `DebugOnly=true`, so ordinary room eligibility rejects it. See `RoomDataI.lua:2308-2320`.

There is no ordinary `H_Shop01`; the Fields shop case is `H_Bridge01 + BridgeShop`.

### Mandatory/pre-boss shop-bearing rooms

F/G/H/N/O/P pre-boss routes include fixed Shop behavior. Q uses `TyphonShop`, `ForcedFirstReward="Shop"`, and `Q_WorldShop`. See `RoomDataQ.lua:1217-1225`. These are progression rooms, not equivalent to a random dedicated Charon-room occurrence.

Tartarus `I_PreBoss01` is another important exception: it owns `I_WorldShop` and Shop room events but its legal encounter is `Empty`, not Shop. See `RoomDataI.lua:795-900`.

### In-room Well / Surface stores

The game can also roll WellShop/SurfaceShop availability while creating an ordinary room, and later materialize those stores when the room becomes current. These are not route destinations and should not be controlled by a “next Shop room” feature. See `RunLogic.lua:630-636`, `StoreLogic.lua:436-451`, and `RoomLogic.lua:5155-5180`.

## Current Trainer capability versus the routing gap

Current Trainer capabilities already cover parts of the user intent, but at different layers:

- Direct special reward UI: `nativeSpecialChoiceDefinitions` contains Artemis, Athena, Dionysus, Hades, Arachne, Narcissus, Echo, Medea, Circe, and Icarus. `open_special_choice` synthesizes an audited source and calls the native `OpenUpgradeChoiceMenu`; it does not route to or spawn the NPC. Current source: `Backend/games/hades2/runtime/hades.lua:330-341,8809-8917`.
- Ordinary next-room reward: hooks `ChooseRoomReward` and patches normal reward doors. It explicitly rejects Story and Shop and does not change `door.Room.Name`. Current source: `Backend/games/hades2/runtime/hades.lua:7309-7406`.
- Exact reward spawning/trait operations are likewise distinct from meeting an NPC or entering a Shop room.

The missing capability is native occurrence routing, not reward acquisition.

## One-shot ownership and consumption implications

A future route control should remain a one-shot intent with an identity token/receipt, but room and encounter tokens cannot use identical consumption rules.

### Room target

A Story/dedicated-Shop room is selected while exit doors are generated. Native `RoomCreations` is incremented for that offered room immediately. Many target rooms have `MaxCreationsThisRun=1`.

If a Trainer forces/offers such a room on one exit and the player chooses a different exit:
- consuming the token on offer matches the native room counter but may surprise the player because they missed it;
- retaining the token until entry requires owning the reservation/counter semantics or another route-safe mechanism, otherwise the native max-creation rule can prevent the room from being offered again;
- replacing the actually chosen route later is more invasive and can violate linked-room/progression assumptions.

This is why existing next-room-reward behavior cannot simply be copied.

### Encounter target

A field encounter is not selected or recorded until the player has chosen a door. A “next eligible selected combat encounter” token can therefore stay armed through ineligible offered rooms and be consumed only when `ChooseEncounter` selects the requested family. This fits the native lifecycle more naturally.

### Failure and replay

The project-wide non-idempotent rule still applies: outcome-unknown mutations must not be blindly replayed. A future durable one-shot route token needs an explicit consumption receipt, just as the existing next-room reward does.

## Product options for user selection

The investigation supports three coherent behavior levels.

### Option A — native-eligible routing (recommended)

- Fixed Story NPC / dedicated Shop: make the target appear in the next native-eligible batch of exits; consume the room-routing token when the game has actually reserved/offered the room.
- Field NPC: use the next selected combat room in which the requested encounter is natively eligible; consume only when the encounter is selected.
- Preserve all normal history, depth, biome, route, cooldown, reward-compatibility, and mutual-exclusion rules.
- If there is currently no eligible target, keep a pending status rather than claiming execution.

Advantages: closest to native behavior, least progression risk, clean ownership split. Cost: a player can ignore an offered Story/Shop door and lose that one-shot room request.

### Option B — native-eligible guarantee-until-entered

- Same native eligibility as A.
- For fixed Story/Shop targets, keep the request pending until the player actually enters the target, even if an offered target door was skipped.

Advantages: user intent feels stronger. Cost: implementation must deliberately own room reservation/creation-count semantics so a skipped offer does not strand the request. This is meaningfully more stateful than current reward forcing.

### Option C — expert force with explicit eligibility bypass

- Permit forcing the selected room/encounter even when ordinary native GameState eligibility would reject it, while still enforcing hard route-integrity limits such as correct biome/family, linked/final-route constraints, boss/progression room safety, and valid host room shape.

Advantages: strongest debugging/control capability. Cost: native scenes can reference history or route state the player has not established. It must be labeled as a bypass, not presented as normal occurrence probability.

The native `ForceNextRoom` and `ForceNextEncounter` paths show that bypass is technically possible, but they should not be the default Trainer contract.

## Decisions still required before implementation

1. Choose routing strength: A (recommended), B, or C.
2. Define “Shop” scope. Recommended: route only to dedicated/random Charon room forms plus the Fields bridge shop; exclude mandatory pre-boss shops and in-room Well/Surface stores from this occurrence control.
3. Define visible NPC scope. Recommended: expose both reward-giver routing targets and field-character encounters (Artemis, Athena, Icarus, Nemesis, Heracles), while keeping ambient Arachne cocoon combat and pure narrative/final-route scenes out of the primary selector.

After those choices, publish a focused implementation issue. Room routing and encounter routing should have separate native owners internally even if the UI presents them under one occurrence-control section.

## Source index

Target-build native source:
- `Content/Scripts/RunLogic.lua:592-745,782-1013,1022-1095,1660-1722`
- `Content/Scripts/RoomLogic.lua:3871-4009,4098-4134,4376-4394,4453-4462,5155-5180`
- `Content/Scripts/StoreLogic.lua:436-451`
- `Content/Scripts/RoomSets.lua:18-24,58-66,101,128-134,187-190,252-256,287-292,330,349`
- `Content/Scripts/RoomDataF.lua:2881-2906,3140-3172`
- `Content/Scripts/RoomDataG.lua:1797-1824,2536-2562`
- `Content/Scripts/RoomDataH.lua:787-862`
- `Content/Scripts/RoomDataI.lua:795-900,2308-2320,3026-3183`
- `Content/Scripts/RoomDataN.lua:1981-2020,3609-3730`
- `Content/Scripts/RoomDataO.lua:739-787,2738-2886`
- `Content/Scripts/RoomDataP.lua:668-701,2240-2354`
- `Content/Scripts/RoomDataQ.lua:1217-1225,2866-2905`
- `Content/Scripts/EncounterData_Story.lua:843+,2048+`
- `Content/Scripts/EncounterData_Unique.lua:297+`
- `Content/Scripts/EncounterData_Artemis.lua`
- `Content/Scripts/EncounterData_Athena.lua`
- `Content/Scripts/EncounterData_Icarus.lua`
- `Content/Scripts/EncounterData_Heracles.lua`
- `Content/Scripts/EncounterData_Nemesis.lua`
- `Content/Scripts/EncounterData_Arachne.lua`
- `Content/Scripts/RequirementsData.lua:1434-1538`
- `metadata/Info.plist:23-24`
- `metadata/appmanifest_1145350.acf:12,20`

Current Trainer source:
- `Backend/games/hades2/runtime/hades.lua@1868b676943314e0e343fb1b03405156bf6822d9:330-341,7309-7406,8809-8917`.
