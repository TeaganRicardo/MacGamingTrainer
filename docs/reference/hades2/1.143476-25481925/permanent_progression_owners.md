# Permanent progression and equipment owners (#427)

Target: Hades II **1.143476 / Steam 25481925**. This investigation read the
installed `Content/Scripts` and bilingual text sources on 2026-10-23 without
launching/attaching the game or reading user saves. The supported identities and
group relationships remain declared once in `save_equipment.py` and
`save_arcana.py`; this note records their native ownership evidence.

## Familiar purchase rank and selection

`FamiliarShopData.lua:1-522` defines the concrete upgrade groups used by the
equipment owner. Each group has an initial purchase and two dependent purchases;
the later records require the preceding `GameState.FamiliarUpgrades` membership.
`RunData.lua:1328-1415` assigns names and resolves inheritance. No concrete or
inherited Familiar purchase record supplies `OnPurchasedFunctionName`, so the
generic callback invocation in the purchase handler adds no unmodeled durable
side effect for this supported set.

The permanent purchase path is:

- `FamiliarShopLogic.lua:292-303`: set `GameState.FamiliarUpgrades[item]`, call
  `AddWorldUpgrade(item)`, then invoke the optional purchase callback.
- `GhostAdminLogic.lua:542-560`: `AddWorldUpgrade` sets current
  `GameState.WorldUpgrades[item]` and ever-added
  `GameState.WorldUpgradesAdded[item]`. It separately records the current-run
  acquisition event in `CurrentRun.WorldUpgradesAdded`.
- `FamiliarShopLogic.lua:445-453`: `GetFamiliarTraitStacks` returns the base stack
  plus the number of purchased matching upgrades. Purchased rank is therefore
  distinct from a mounted trait's runtime stack.
- `FamiliarLogic.lua:158-177`: `EquipFamiliar` stores the selected native Familiar
  in `GameState.EquippedFamiliar`, then mounts runtime effects using those durable
  purchase memberships. `FamiliarLogic.lua:1188-1207` also derives a Familiar's
  upgrade count from the same purchase table.

The supported Save operation sets a **purchased rank** over contiguous native
tiers. It updates `FamiliarUpgrades` and current `WorldUpgrades` together, adds
ever-purchased markers for newly owned tiers, and retains historical markers on
downgrade. Its purchase membership has a distinct native owner from weapon
ownership. A positive rank also unlocks its parent Familiar. Revoking a
Familiar clears known current upgrade memberships and its selected state while
preserving purchase history and unknown records. Missing owners are created;
existing tier gaps and disagreeing current mirrors are normalized to the explicit
desired rank. Native stack counting iterates matching keys, so an observed gap
is displayed by its existing purchase count before the requested repair. Only
an ambiguous key or a parent value that cannot be traversed as a table prevents
this linked child operation; Advanced exposes the actual parent data separately.

Each Familiar entity groups its unlock, purchased ranks and selected observation
around official bilingual identities. Per-entity selection actions mutate the
single native `EquippedFamiliar` selector. The older global enum remains in the
legacy equipment query, but is excluded from entity browsing; review projects
one canonical linked selector effect rather than duplicate actions for the same
owner. Contradictory rank/revocation or selection intents fail the final staged
owner check independently of staging order.

These are deliberate permanent-state operations. They do not emulate spending,
purchase presentation, quest callbacks, runtime trait mounting or current-run
acquisition history. Existing `CurrentRun` bytes and unrelated resources remain
preserved by the temporary-file journey test. A successful disk edit does not
prove that an already running game reloads those owners.

## Weapons, aspects and tools

The weapon/aspect owner uses native purchase membership and the saved
per-weapon aspect selector. `WeaponUpgradeLogic.lua:478-486` derives a level
from one plus the number of existing known upgrade keys. An observed gap is
therefore displayed by count, while an explicit desired rank writes its native
contiguous tier sequence and repairs the current purchase mirrors.
`WeaponShopLogic.lua:514-520` writes weapon/tool purchase ownership and world
markers; `543-550` writes `GameState.LastWeaponUpgradeName[weapon]` for aspect
selection. `GhostAdminLogic.lua:552-557` distinguishes current ownership from
ever-added history, and `WeaponShopLogic.lua:182` uses the latter to classify
purchased shop items. The shared weapon/tool/aspect mutation therefore removes
only current membership on downgrade or revocation; it retains existing history
and adds history on acquisition. The temporary Save journey first reproduced
Pickaxe rank 2 → 1 erasing `WorldUpgradesAdded.ToolPickaxe2`, then verifies tool
revocation, aspect downgrade/revocation, free-aspect tiers and parent-weapon
teardown with preserved purchase history and unchanged unknown records.
Starter weapon ownership and a default aspect's rank zero are writable; the
latter revokes its actual parent weapon, current aspect tiers and saved selector.
Selecting a locked native aspect grants its missing weapon/aspect prerequisites.
Selecting a native Familiar grants its missing unlock prerequisite. Explicit
contradictory revoke/selection requests fail instead of overriding a requested
choice, and the existing staged basket survives rejection. Review
continues to describe current ranks and dependent selections, without claiming
that existing history was removed. This task does not invent a permanent
selected-weapon scalar from a `CurrentRun` mount.

`WeaponShopData.lua:3157-3427` defines initial tool purchases and their upgrades.
Each tool now has one entity containing purchased rank and an explicit read-only
availability observation. `RoomLogic.lua:5075-5091` proves the supported rule:
access is granted by `GameState.WeaponsUnlocked[tool]` or by the selected
Familiar's `LinkedTool`. The links are declared in
`FamiliarData.lua:268,2197,2466,2784,3150`. There is no independent permanent tool
equipment selector in this path. The UI states that limitation, rather than
offering an unrelated Boolean as an equipment toggle. A Familiar's harvesting
link does not invent an additional purchasable tool progression record.

## Arcana loadout ownership

Each known card entity exposes unlocked state, purchased level and equipped
state. `save_arcana.py` is the single supported-build manifest for the native
5×5 layout, inherited costs and six active automatic requirements; the old
`BonusDodge` automatic requirements are commented out in this installed build.
`MetaUpgradeLogic.lua:97-235` evaluates costs, manual equipped counts and grid
relationships without reading purchased card levels.

`MetaUpgradeCardScreenLogic.lua:992-1060` computes automatic results from one
snapshot before applying them. `1595-1598` deliberately invokes that pass twice.
The Save operation preserves these two snapshot passes, diagonal neighbors and
the current saved layout. A missing layout is created from the native default;
a custom layout is retained. `179-194` derives visible grid size from unlocked
coordinates, with a minimum of three and maximum of five rows/columns. An
already-unlocked card's pure level edit does not require a layout: the native
level does not participate in these equipment predicates.

An explicit automatic-equipment intent can supply required manual selections,
card unlocks and sufficient purchased Grasp. The deterministic solver first
minimizes manual selection changes, then added unlocks, then total equipped
cost, then native manifest order. Existing explicit manual selections and
revocations remain fixed. A conflicting automatic/card request, an impossible
capacity, or mutually unsatisfiable explicit choices produces a conflict while
preserving the earlier staged actions. The temporary-file tests fix this tie
break, including preferring an existing unlocked prerequisite and choosing an
alternative when a user explicitly removed the cheapest candidate.

The operation reconstructs known native unlocked/max-level count and equipped
cost caches. `MetaUpgradeCardScreenLogic.lua:763-772,784-807` owns those
projections; `MetaUpgradeCardUpgradeScreenLogic.lua:104` refreshes count caches
when the upgrade screen closes. `MetaUpgradeData.lua:31` and its tier data set
the native starting Grasp and capacity purchases. The operation raises capacity
only as needed for the final explicit loadout; removing a card does not revoke
previously purchased capacity. Review lists every additional unlock, level
reset, equipped/unequipped card, cache and capacity change before disk Apply.
Scalar cache inconsistencies are repaired rather than treated as a blanket
read-only reason. Duplicate physical cache keys remain ambiguous.

There are no active `AdjacencyBonus` definitions in this build. Native
`MetaUpgradeLogic.lua:237-253` still clears the old
`AdjacencyBonuses.CustomMultiplier` projection during a loadout update. The
operation clears that known stale projection, preserves other unknown bonus
members, and includes the removed value in review. It does not replay purchase
setup, resource spending, runtime mounting or current-run callbacks.

Unknown observed card metadata is preserved. Its existing scalar physical
fields remain writable with their actual Lua types and the shared Advanced
unknown-impact warning; absent fields are not invented. The module does not
infer unlocks, costs or runtime effects for unknown metadata. Native full-cache
code itself dereferences native card data, so known cache reconstruction is
explicitly limited to the supported manifest rather than claiming unknown
cards' contributions. Structured unknown data, raw layout edits and fields
outside the semantic card actions remain the Advanced typed/path owner's
responsibility.

## Verification and remaining acceptance

The initial temporary-file entity journey reproduced missing Familiar grouping
on baseline `293b6473912991a570729d68fd456e5334977ef1`. Subsequent RED fixtures
reproduced an equipped Arcana Boolean being read-only, an automatic activation
being refused without implementing its prerequisites, locked native selectors
being omitted/refused, and Pickaxe rank 2 → 1 erasing ever-purchased history.
The expanded typed-card RED also caught synthetic absent fields and incorrect
assumed value types on unknown metadata.

`test_hades2_save_arcana_equipment.py` exercises actual temporary Core Save
query → Stage → review → Apply → reopen journeys: all six automatic rules,
two-pass automatic dependencies, custom layouts, deterministic prerequisites,
capacity, explicit-intent conflicts and retained baskets, missing table
creation, native tier/mirror repair, starter/default-aspect revocation, native
selection prerequisites, unknown values, adjacency projections and current-run
preservation. Existing equipment/progression/entity/discovery/staged-action
and unique-owner tests cover the neighboring workflows and successful paths.
Tests never read or mutate the user's save tree.

A local source oracle additionally executed the installed unmodified native
automatic requirement, coordinate, zoom and snapshot functions. It verified the
manifest's inherited costs/rules and compared 120 seeded default/custom-layout
states against the Python implementation, with matching automatic results.
The oracle log and extraction script are retained locally under
`/tmp/mgt-427-native-arcana-oracle.{log,lua}`; native game source is not copied
into the repository. This is native Lua function evidence, without a game
process, runtime mounting or real-save acceptance.

Advanced typed/path integration and Swift warning presentation are developed
by their separate owners. The workspace must run this module's finalizer when
building both the final semantic candidate and the semantic candidate used to
detect Advanced overlap. Exact-head portable/macOS gates, independent review,
rendered UI acceptance and real Hades save loading remain distinct completion
evidence for the integrated issue. This scoped implementation does not close
#427 or the wider Save Editor acceptance on its own.

## Source hashes

SHA-256 of the inspected native source files:

```text
FamiliarShopLogic.lua 7669f18a5906f156aeab2d6206d7716fa58d29a98d4d3beb8c7f872b55212eff
FamiliarShopData.lua 6f2bd1c0b219adc8b336d4a788b090adcd6000af4c0235d498d3c2a2e36177b0
FamiliarLogic.lua 97f62d6815c55c89aa55129f582c07855d3821768c2534853cdc1b182fff25ae
FamiliarData.lua 5a8e079c729ddf2d4f756fd4a5f1938466265174a33968c3a9d80f7f512d37b3
GhostAdminLogic.lua c0344bbdacfae2eb5e8711b9da36cd70869415da209124e39fa7813dab6a5cf3
RoomLogic.lua affb8ee3dc2806e1b9a1a5f8f8c3616f9d2010f267e58f175095f5c16e072d5b
MetaUpgradeLogic.lua baef38ab67722b48d54422f551e54fb5fefb861e5a1ce7b39c98852015f4ea27
MetaUpgradeData.lua 9023e35c8f74e466aeba8287f618bb439000ca93e9d8a5eded7abe0f1a2882b5
MetaUpgradeCardScreenLogic.lua 228ad33a9ef71af6142109afd6105c3b599759ee600df12dd638ba2b33f41752
MetaUpgradeCardUpgradeScreenLogic.lua d65be170cf0dcc4c2010139895b877dd2b21a01e21b05251ebf2b791e8ea1eaa
WeaponShopLogic.lua 3a0b47260e29e8f10fd3abe6b683047687448081dadd704a8ca5a9495bd6c9a9
WeaponUpgradeLogic.lua 023271aab24f3f12dd76f5ccbece3175be7ae9e22fd72c07c4e38d4aaaf1f8d9
WeaponShopData.lua d7e7f8eec088da86962e8355eb514c4e83188cf1a6fe849c4ad3236a24298e46
RunData.lua 604497cb405551a4364ee9d5bb22ee35731c545ce3cef06a53dc4b6ab6e4b86e
```
