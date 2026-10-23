# Permanent progression and equipment owners (#427)

Target: Hades II **1.143476 / Steam 25481925**. This investigation read the
installed `Content/Scripts` and bilingual text sources on 2026-10-23 without
launching/attaching the game or reading user saves. The supported identities and
group relationships remain declared once in `save_equipment.py` and
`save_long_term.py`; this note records their native ownership evidence.

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
preserving purchase history and unknown records. Missing, duplicate, malformed,
noncontiguous or disagreeing linked owners are read-only with a visible reason.

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

The existing weapon/aspect owner continues to use native purchase membership,
contiguous aspect ranks and the saved per-weapon aspect selector.
`WeaponShopLogic.lua:514-520` writes weapon/tool purchase ownership and world
markers; `543-550` writes `GameState.LastWeaponUpgradeName[weapon]` for aspect
selection. `GhostAdminLogic.lua:552-557` distinguishes current ownership from
ever-added history, and `WeaponShopLogic.lua:182` uses the latter to classify
purchased shop items. The shared weapon/tool/aspect mutation therefore removes
only current membership on downgrade or revocation; it retains existing history
and adds history on acquisition. The temporary Save journey first reproduced
Pickaxe rank 2 → 1 erasing `WorldUpgradesAdded.ToolPickaxe2`, then verifies tool
revocation, aspect downgrade/revocation, free-aspect tiers and parent-weapon
teardown with preserved purchase history and unchanged unknown records. Review
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

## Arcana disposition

Each card entity contains unlocked state, purchased level and a read-only saved
`Equipped` observation. Independent equipment is a loadout operation:
`MetaUpgradeCardScreenLogic.lua:994-1060,1595-1598` re-evaluates automatic cards
and derived state. `MetaUpgradeLogic.lua:97-235` evaluates costs, equipped counts
and grid relationships, without reading card levels. The six active automatic
cards are declared once in the owner; the old automatic requirements inside
`BonusDodge` are commented out in this installed build. There are no active
`AdjacencyBonus` definitions in its card data, though native adjacency processing
remains in `MetaUpgradeLogic.lua:237-253`.

The supported boundaries are therefore specific to the changed owner:

- Purchased levels remain editable; they cannot change automatic equipment.
- An automatic card's unlocked state is read-only because acquiring it can
  activate it and change automatic neighbors.
- Revoking an equipped manual card is read-only if an unlocked automatic card
  exists, or that automatic unlock owner cannot be uniquely interpreted.
- A manual unequipped card's unlock state remains editable. Revoking an
  equipped manual card also remains supported when no automatic card is
  unlocked. The existing linked equipment and level reset then remains safe.

The owning mutation also maintains **observed** native caches. Native
`MetaUpgradeCardScreenLogic.lua:763-772,784-798` derives equipped cost, unlocked
count and maximum-level count; the upgrade screen refreshes the latter two on
close at `MetaUpgradeCardUpgradeScreenLogic.lua:104`. This task reproduced a
level 2 → 3 write leaving the saved maximum-level cache at zero, then corrected
the known card's count contribution. A safe revocation adjusts all three
observed caches, and review lists those linked effects with bilingual labels.

The implementation applies a known card's before/after contribution as a delta
to existing caches. It retains absent cache fields and opaque cards' existing
contributions instead of synthesizing their unknown native data. Duplicate,
noninteger, negative or contribution-underflowing affected cache owners are
read-only with a specific visible reason. It does not establish the correctness
of an original aggregate that already contains opaque contributions, and does
not claim a complete native grid or historical-cache repair. Native full-cache
recalculation itself dereferences every card's native data in the maximum-level
loop; blindly replaying it against opaque card names would be unsafe.

## Remaining work under the expanded editing contract

The user's latest acceptance requires reliable scalar, Boolean, enum, counter,
membership and selection edits by default. Native linked effects belong to the
implementation; absent whitelist membership or incomplete owner research is
not a final read-only disposition. This implementation snapshot therefore does
**not** complete #427. Automatic Arcana unlock/equipment recomputation, broader
typed/path access to reliable unknown fields, and the existing progression and
equipment whitelist/refusal policies remain development gaps for the next
owner pass. The read-only boundaries described above record current behavior
and source dependencies, not authorization to close those requirements.

## Reproduction and verification boundary

The new temporary-file entity journey first failed on source baseline
`293b6473912991a570729d68fd456e5334977ef1`: searching for the native Familiar
could not find a `familiar:<native-id>` entity, so no grouped purchase/selection
workflow existed. The test now queries bilingual entities, stages linked
progression and equipment changes, inspects the review, applies to temporary
Save bytes, reopens, and verifies native owners and unknown-record preservation.
It covers downgrade/history separation, parent revocation, read-only tool and
Arcana dispositions, missing/malformed/duplicate/gapped/disagreeing Familiar
owners, conflicting intent order, access supplied by a selected Familiar,
observed Arcana cache deltas, absent/opaque cache preservation, invalid cache
owners and the safe manual-card revocation path through reopened Save bytes.

Nearest entity, unique-owner, discovery and staged-action contracts are also
run. Automated file/fixture evidence does not establish rendered app acceptance
or real Hades save-load behavior. Exact-head portable and macOS task gates and
independent final-head review belong to the authorized handoff for this issue.

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
WeaponShopData.lua d7e7f8eec088da86962e8355eb514c4e83188cf1a6fe849c4ad3236a24298e46
RunData.lua 604497cb405551a4364ee9d5bb22ee35731c545ce3cef06a53dc4b6ab6e4b86e
```
