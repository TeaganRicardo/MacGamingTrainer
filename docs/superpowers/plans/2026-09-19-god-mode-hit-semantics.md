# God Mode Hit Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Hades II God Mode keep the Hero hit counter exactly unchanged while it blocks hostile hits, without broad effect interception.

**Architecture:** Preserve the existing invulnerability + shared `Damage` router + explicit `AddEffectBlock` design. Capture the bound Hero's exact `Hits` value, restore it immediately on blocked damage and from the already-existing frame guard, and restore it once more on release. No new polling or generic `ApplyEffect` hook is added.

**Tech Stack:** Lua 5.2 resident runtime, Python static contract tests.

**Spec:** `docs/superpowers/specs/2026-09-19-god-mode-hit-semantics-design.md`

## Global Constraints

- Target game build: Hades II 1.139672 / Steam build 24556151.
- Runtime source changes require revision bump 39 → 40.
- No periodic LLDB/Lua polling.
- No broad `ApplyEffect` hook.
- No game-specific semantics in Core/Host.
- Preserve `nil` Hero.Hits baselines as `nil`.
- Tests must never touch real user/game data.

---

### Task 1: Lock the hit-counter contract RED

**Files:**
- Modify: `tests/test_god_mode_hostile_effects.py`

**Interfaces:**
- Consumes: `Backend/games/hades2/runtime/hades.lua` as source text.
- Produces: a static regression contract that requires the hit-baseline lifecycle and revision 40.

- [x] **Step 1: Extend the existing static contract**

Add assertions equivalent to:

```python
assert 'version = 1, revision = 40' in lua
assert 'godModeHitBaseline' in lua
assert 'godModeHitBaselineKnown' in lua

damage_router = lua[lua.index('local function ensureHeroDamageRouter()'):lua.index('local function installGodMode()')]
god_branch = damage_router[damage_router.index('if M.godMode then'):damage_router.index('end', damage_router.index('if M.godMode then')) + 3]
assert 'restoreGodModeHitCount(victim)' in god_branch
assert god_branch.index('restoreGodModeHitCount(victim)') < god_branch.index('return nil')

install = lua[lua.index('local function installGodMode()'):lua.index('local function installHealth()')]
assert 'M.godModeHitBaseline = hero.Hits' in install
assert 'M.godModeHitBaselineKnown = true' in install

release = lua[lua.index('local function releaseGodMode()'):lua.index('local function releaseHealth()')]
assert 'restoreGodModeHitCount' in release
assert 'M.godModeHitBaselineKnown = false' in release

enforce = lua[lua.index('local function enforceLocks()'):lua.index('M.enforceLocksInternal = enforceLocks')]
assert 'restoreGodModeHitCount(CurrentRun.Hero)' in enforce
```

Keep the existing explicit-effect assertions, including the assertion that no `installHook("ApplyEffect"` exists.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
python3 tests/test_god_mode_hostile_effects.py
```

Expected: FAIL because r39 has no hit baseline and revision is still 39.

- [x] **Step 3: Commit the RED contract**

```bash
git add tests/test_god_mode_hostile_effects.py
git commit -m "test: lock god mode hit counter semantics"
```

### Task 2: Implement the minimal nil-preserving hit invariant

**Files:**
- Modify: `Backend/games/hades2/runtime/hades.lua`
- Test: `tests/test_god_mode_hostile_effects.py`

**Interfaces:**
- Consumes: existing `ensureHeroDamageRouter`, `installGodMode`, `releaseGodMode`, and `enforceLocks`.
- Produces: `restoreGodModeHitCount(hero)`, plus resident state `godModeHitHero`, `godModeHitBaseline`, and `godModeHitBaselineKnown`.

- [x] **Step 1: Bump resident runtime revision**

Change both revision checks/state declarations from 39 to 40.

- [x] **Step 2: Add exact baseline state**

Extend `M` with:

```lua
godModeHitHero = nil, godModeHitBaseline = nil, godModeHitBaselineKnown = false,
```

- [x] **Step 3: Add one restoration helper**

Place near the God Mode release helpers:

```lua
local function restoreGodModeHitCount(hero)
  if M.godModeHitBaselineKnown and M.godModeHitHero == hero and type(hero) == "table" then
    hero.Hits = M.godModeHitBaseline
  end
end
```

- [x] **Step 4: Restore immediately at the blocked damage boundary**

In the existing `if M.godMode then` branch of the shared `Damage` hook:

```lua
restoreGodModeHitCount(victim)
return nil
```

Do not call the original `Damage`.

- [x] **Step 5: Capture and release the baseline**

When `installGodMode` binds a new Hero:

```lua
if M.godModeHitHero ~= hero or not M.godModeHitBaselineKnown then
  M.godModeHitHero = hero
  M.godModeHitBaseline = hero.Hits
  M.godModeHitBaselineKnown = true
end
```

At the start of `releaseGodMode`, restore the bound Hero once, then clear:

```lua
restoreGodModeHitCount(M.godModeHitHero)
M.godModeHitHero = nil
M.godModeHitBaseline = nil
M.godModeHitBaselineKnown = false
```

- [x] **Step 6: Enforce from the existing frame guard**

Inside `enforceLocks()`, after confirming the current Hero is available:

```lua
if M.godMode then restoreGodModeHitCount(CurrentRun.Hero) end
```

Do not add another timer, thread, or hook.

- [x] **Step 7: Run the focused contract and verify GREEN**

Run:

```bash
python3 tests/test_god_mode_hostile_effects.py
```

Expected: `god_mode_hostile_effects_ok`.

- [x] **Step 8: Run Linux contracts**

Run:

```bash
bash Tools/run_linux_checks.sh
```

Expected: `linux_checks_ok`.

- [x] **Step 9: Commit the implementation**

```bash
git add Backend/games/hades2/runtime/hades.lua tests/test_god_mode_hostile_effects.py
git commit -m "fix: keep god mode hits out of run state"
```

### Task 3: Review the God Mode slice before widening effect coverage

**Files:**
- Modify only if review finds a demonstrated defect: `Backend/games/hades2/runtime/hades.lua`, `tests/test_god_mode_hostile_effects.py`

**Interfaces:**
- Consumes: Task 2 implementation and the 1.139672 source audit.
- Produces: a reviewed r40 God Mode hit-semantics candidate.

- [x] **Step 1: Verify no forbidden broad interception**

Run:

```bash
grep -n 'installHook("ApplyEffect"' Backend/games/hades2/runtime/hades.lua && exit 1 || true
```

Expected: no match.

- [x] **Step 2: Verify only the existing guard enforces the baseline**

Run:

```bash
grep -n 'godModeHit\|restoreGodModeHitCount' Backend/games/hades2/runtime/hades.lua
```

Expected: state declaration, one helper, install/release, Damage branch, and existing `enforceLocks`; no new polling loop.

- [x] **Step 3: Re-run focused + full Linux contracts**

```bash
python3 tests/test_god_mode_hostile_effects.py
bash Tools/run_linux_checks.sh
```

Expected: both PASS.

- [x] **Step 4: Record manual acceptance target**

Manual r40 acceptance must establish the current Hero hit counter for the test interval, exercise ordinary hostile hits while r40 God Mode is active, and verify the save-backed counter remains unchanged. Per owner instruction on 2026-09-20, a deliberate post-disable hit/increment check is not required.


## Execution checkpoint — 2026-09-19

- Isolated branch: `fix/batch-b-runtime-semantics-r40`.
- RED contract commit: `5c59a2dcc26931cd8a0fb72c7b974a6048dea1e7`.
- r40 implementation commit: `864ff8fcbf96c616564756d658d3535c1f570f94`.
- RED was reproduced against the exact r39 God Mode/revision structure in the available container; the new contract fails first on revision 39 and then on the absent hit-baseline lifecycle.
- The updated r40 snippets satisfy the new source contract, including nil-preserving baseline state and restoration before the God Mode Damage early-return.
- Review confirms there is still no `installHook("ApplyEffect"` and no new timer/thread/polling path.
- The original execution checkpoint above has now been superseded by the 2026-09-20 verification below.

## Verification checkpoint — 2026-09-20

- Verified code/test head: `39c66b702d66c650eeb992f7016d5e9cb7c3f64c`.
- Installed Hades II 1.139672 scripts prove `CurrentRun.Hero.Hits` is part of the save-backed `CurrentRun` and remains on the latest completed run.
- Focused God Mode contract: PASS / `god_mode_hostile_effects_ok`.
- First full Linux run exposed only three stale revision-39 assertions. Root cause was incomplete propagation of the intentional resident revision bump; test-only commit `39c66b7` advances those contracts to 40.
- Final full Linux suite: PASS / `linux_checks_ok`.
- Full macOS suite: PASS / `macos_checks_ok`.
- Real Hades II save-tree before/after sentinel: `REAL_SAVE_TREE_UNCHANGED`.
- Clean package gate: PASS for runtime 40, arm64, debugger entitlement, strict codesign, one packaged Hades II module and clean git diff.
- Tester ZIP: `MacGamingTrainer-0.1-build2-rc-r40.zip`, 1,976,217 bytes, SHA256 `45b623fcb70986af6ad604b69f62192925b7fb9e97854573f7d7daab30acc0c0`.
- Focused real-game HeroHit acceptance: PASS. Hot backups `saves-20260920-011751-3qk9q5zy` and `saves-20260920-012157-js8mys43` were extracted read-only with `TheNormalnij/Hades-SavesExtractor` commit `0ad8d26968a5cc8fb6bd0548af39f455dff2e8c7`. `LUA_DATA.CurrentRun.Hero.Hits` is `182` in both, current Hero health is `157` in both, and the after snapshot carries `MacGamingTrainerGodMode = true`. Historical latest-run `Hero.Hits = 248` is distinct and unchanged.
- Per owner instruction, the deliberate post-disable hit/increment check is omitted from acceptance.
- Hecate polymorph and Mourning Fields miasma blocks are unchanged by r40 and are not claimed as newly manually retested here.
- r40 is accepted for integration.
