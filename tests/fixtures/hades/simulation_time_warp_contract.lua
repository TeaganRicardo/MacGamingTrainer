local path = assert(arg[1], "Lua module path is required")
local module = dofile(path)
local function contains(source, text)
    return source:find(text, 1, true) ~= nil
end
local ok, err = pcall(module.set, 2)
assert(not ok and contains(tostring(err), "hades.error.runtimeNotReady"))

local calls = {}
AdjustSimulationSpeed = function(args)
    calls[#calls + 1] = args
end
MapState = { SimSpeedChanges = { hit = { Fraction = 0.4 } } }
ok, err = pcall(module.set, 2)
assert(not ok and contains(tostring(err), "hades.error.runtimeNotReady"))
assert(#calls == 0 and contains(module.current(), '"wrapperInstalled":false'))
MapState.SimSpeedChanges = {}
assert(contains(module.set(2), '"multiplier":2'))
assert(calls[#calls].Fraction == 2.0)

local native = { Fraction = 0.25, LerpTime = 0.1, Priority = true }
AdjustSimulationSpeed(native)
assert(calls[#calls].Fraction == 0.5)
assert(calls[#calls].LerpTime == 0.1 and calls[#calls].Priority == true)
assert(native.Fraction == 0.25)
assert(contains(module.set(0.5), '"effectiveFraction":0.125'))
assert(calls[#calls].Fraction == 0.125)
assert(contains(module.set(0), '"effectiveFraction":0'))
assert(calls[#calls].Fraction == 0)
assert(contains(module.set(1), '"multiplier":1'))
assert(calls[#calls].Fraction == 0.25)
AdjustSimulationSpeed({ Fraction = 1, LerpTime = 0.3 })
assert(calls[#calls].Fraction == 1 and calls[#calls].LerpTime == 0.3)
for _, value in ipairs({-0.1, 10.1, math.huge}) do
    ok, err = pcall(module.set, value)
    assert(not ok and contains(tostring(err), "hades.error.invalidValue"))
end

local previous = AdjustSimulationSpeed
local oldCalls = #calls
AdjustSimulationSpeed = function(args)
    calls[#calls + 1] = args
end
ok, err = pcall(module.current)
assert(not ok and contains(tostring(err), "hades.error.restartRequired"))
AdjustSimulationSpeed = previous
assert(contains(module.current(), '"wrapperInstalled":true'))
assert(#calls == oldCalls)
print("hades_simulation_time_warp_lua_contract_ok")
