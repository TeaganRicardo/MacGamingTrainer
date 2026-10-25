local trainerFlag = "MacGamingTrainer.Hades"
local runtime = {}

function runtime.status()
  local hero = type(CurrentRun) == "table" and CurrentRun.Hero or nil
  local ready = type(hero) == "table" and type(hero.ObjectId) == "number"
  local flags = ready and hero.InvulnerableFlags or nil
  return {
    heroReady = ready,
    invincible = type(flags) == "table" and flags[trainerFlag] == true,
    health = ready and tonumber(hero.Health) or 0,
    maxHealth = ready and tonumber(hero.MaxHealth) or 0,
    money = ready and tonumber(CurrentRun.Money) or 0,
  }
end

function runtime.set_invincibility(enabled)
  assert(type(enabled) == "boolean", "hades.error.invalidValue")
  assert(runtime.status().heroReady, "hades.error.heroNotReady")
  assert(type(CurrentRun.Hero.InvulnerableFlags) == "table"
    and type(CurrentRun.InvulnerableFlags) == "table"
    and type(SetPlayerInvulnerable) == "function"
    and type(SetPlayerVulnerable) == "function", "hades.error.unsupportedRuntime")
  if enabled then
    SetPlayerInvulnerable(trainerFlag)
  else
    SetPlayerVulnerable(trainerFlag)
  end
  return runtime.status()
end

function runtime.json(value)
  return string.format('{"heroReady":%s,"invincible":%s,"health":%.17g,"maxHealth":%.17g,"money":%.17g}',
    tostring(value.heroReady), tostring(value.invincible), value.health or 0,
    value.maxHealth or 0, value.money or 0)
end

return runtime
