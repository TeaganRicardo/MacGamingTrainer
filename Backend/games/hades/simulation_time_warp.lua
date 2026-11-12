-- Hades I exposes AdjustSimulationSpeed to Lua as the engine's global
-- simulation-time owner. Keep the Trainer multiplier separate from the
-- game's own SimSpeedChanges so native slow/fast effects compose.
local STATE_KEY = "__MGT_SIMULATION_TIME_WARP_V1"

local function copyArguments(arguments)
    local copy = {}
    if type(arguments) == "table" then
        for key, value in pairs(arguments) do
            copy[key] = value
        end
    end
    return copy
end

local function numberJSON(value)
    return (string.format("%.17g", value):gsub(",", "."))
end

local function response(state, installed)
    local multiplier = state and state.multiplier or 1.0
    local nativeFraction = state and state.nativeFraction or 1.0
    local effectiveFraction = nativeFraction * multiplier
    return "{\"wrapperInstalled\":" .. tostring(installed)
        .. ",\"multiplier\":" .. numberJSON(multiplier)
        .. ",\"nativeFraction\":" .. numberJSON(nativeFraction)
        .. ",\"effectiveFraction\":" .. numberJSON(effectiveFraction) .. "}"
end

local function makeWrapper(state)
    return function(arguments)
        if state.applying then
            return state.original(arguments)
        end
        if type(arguments) ~= "table" or type(arguments.Fraction) ~= "number"
            or arguments.Fraction ~= arguments.Fraction then
            return state.original(arguments)
        end

        local nativeArguments = copyArguments(arguments)
        state.nativeFraction = nativeArguments.Fraction
        state.nativeArguments = nativeArguments
        nativeArguments.Fraction = state.nativeFraction * state.multiplier
        state.effectiveFraction = nativeArguments.Fraction
        return state.original(nativeArguments)
    end
end

local function current()
    local state = rawget(_G, STATE_KEY)
    if state == nil then
        return response(nil, false)
    end
    assert(type(state) == "table" and state.version == 1
        and type(state.wrapper) == "function" and type(state.original) == "function",
        "hades.error.restartRequired")
    assert(rawget(_G, "AdjustSimulationSpeed") == state.wrapper,
        "hades.error.restartRequired")
    return response(state, true)
end

local function set(multiplier)
    assert(type(multiplier) == "number" and multiplier == multiplier
        and multiplier >= 0 and multiplier <= 10, "hades.error.invalidValue")

    local state = rawget(_G, STATE_KEY)
    if state == nil then
        local original = rawget(_G, "AdjustSimulationSpeed")
        assert(type(original) == "function", "hades.error.runtimeNotReady")
        state = {
            version = 1,
            original = original,
            multiplier = 1.0,
            nativeFraction = 1.0,
            nativeArguments = { Fraction = 1.0, LerpTime = 0 },
            effectiveFraction = 1.0,
            applying = false,
        }
        state.wrapper = makeWrapper(state)
        rawset(_G, STATE_KEY, state)
        rawset(_G, "AdjustSimulationSpeed", state.wrapper)
    else
        assert(type(state) == "table" and state.version == 1
            and type(state.wrapper) == "function" and type(state.original) == "function",
            "hades.error.restartRequired")
        assert(rawget(_G, "AdjustSimulationSpeed") == state.wrapper,
            "hades.error.restartRequired")
    end

    local nativeArguments = copyArguments(state.nativeArguments)
    nativeArguments.Fraction = state.nativeFraction * multiplier
    state.applying = true
    local ok, result = pcall(state.original, nativeArguments)
    state.applying = false
    if not ok then
        error(result)
    end

    state.multiplier = multiplier
    state.effectiveFraction = nativeArguments.Fraction
    return response(state, true)
end

return {
    current = current,
    set = set,
}
