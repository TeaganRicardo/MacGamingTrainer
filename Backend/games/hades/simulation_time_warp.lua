-- Wrap Hades I's game-owned simulation-speed control. Native slow/fast effects
-- keep their own semantics; the Trainer multiplies the requested fraction.
local STATE_KEY = "__MGT_SIMULATION_TIME_WARP_V1"

local function copyArguments(arguments)
    local copy = {}
    if type(arguments) == "table" then
        for key, value in pairs(arguments) do copy[key] = value end
    end
    return copy
end

local function numberJSON(value)
    return (string.format("%.17g", value):gsub(",", "."))
end

local function response(state)
    local multiplier = state and state.multiplier or 1.0
    local nativeFraction = state and state.nativeFraction or 1.0
    return "{\"wrapperInstalled\":" .. tostring(state ~= nil)
        .. ",\"multiplier\":" .. numberJSON(multiplier)
        .. ",\"nativeFraction\":" .. numberJSON(nativeFraction)
        .. ",\"effectiveFraction\":" .. numberJSON(multiplier * nativeFraction) .. "}"
end

local function verify(state)
    assert(type(state) == "table" and state.version == 1
        and type(state.wrapper) == "function" and type(state.original) == "function",
        "hades.error.restartRequired")
    assert(rawget(_G, "AdjustSimulationSpeed") == state.wrapper,
        "hades.error.restartRequired")
end

local function makeWrapper(state)
    return function(arguments)
        if state.applying then return state.original(arguments) end
        if type(arguments) ~= "table" or type(arguments.Fraction) ~= "number"
            or arguments.Fraction ~= arguments.Fraction then
            return state.original(arguments)
        end
        local nativeArguments = copyArguments(arguments)
        local nativeFraction = nativeArguments.Fraction
        nativeArguments.Fraction = nativeFraction * state.multiplier
        -- Keep observed native state only after the native call succeeds.
        local result = state.original(nativeArguments)
        state.nativeFraction = nativeFraction
        state.nativeArguments = copyArguments(arguments)
        return result
    end
end

local function current()
    local state = rawget(_G, STATE_KEY)
    if state ~= nil then verify(state) end
    return response(state)
end

local function set(multiplier)
    assert(type(multiplier) == "number" and multiplier == multiplier
        and multiplier >= 0 and multiplier <= 10, "hades.error.invalidValue")
    local state = rawget(_G, STATE_KEY)
    if state == nil then
        local original = rawget(_G, "AdjustSimulationSpeed")
        assert(type(original) == "function", "hades.error.runtimeNotReady")
        -- An already active native effect has an unknown current interpolation
        -- phase. Installing here could overwrite it; defer until it retires.
        local mapState = rawget(_G, "MapState")
        local changes = type(mapState) == "table" and mapState.SimSpeedChanges or nil
        if type(changes) == "table" and next(changes) ~= nil then
            error("hades.error.runtimeNotReady")
        end
        state = {
            version = 1, original = original, multiplier = 1.0,
            nativeFraction = 1.0, nativeArguments = { Fraction = 1.0, LerpTime = 0 },
            applying = false,
        }
        state.wrapper = makeWrapper(state)
        rawset(_G, STATE_KEY, state)
        rawset(_G, "AdjustSimulationSpeed", state.wrapper)
    else
        verify(state)
    end
    local arguments = copyArguments(state.nativeArguments)
    arguments.Fraction = state.nativeFraction * multiplier
    state.applying = true
    local ok, result = pcall(state.original, arguments)
    state.applying = false
    if not ok then error(result) end
    state.multiplier = multiplier
    return response(state)
end

return { current = current, set = set }
