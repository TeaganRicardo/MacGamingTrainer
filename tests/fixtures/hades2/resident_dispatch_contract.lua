-- Shared resident-harness guard.
--
-- The production backend never returns a raw dispatch table: every LLDB call is
-- wrapped as M.json(M.dispatch(...)) in Backend/games/hades2/adapter.py, so the
-- resident JSON encoder is part of the contract the host actually consumes. A
-- harness that inspects only the returned table leaves that encoder uncovered,
-- which is how an untagged array reached the game twice (#290, #292): the
-- fixtures were green while the real payload failed to serialize.
--
-- Installing this guard routes every harness dispatch through the production
-- encoding path, so a payload that is a valid Lua table but invalid JSON fails
-- the fixture instead of the game.
--
-- The harness must load the resident source before requiring this file.

local M = assert(__MacGamingTrainerV1, "resident runtime did not initialize")

local rawDispatch = M.dispatch

-- Self-check. The guard is only meaningful while the resident encoder rejects
-- an untagged array. If that ever stops holding, or this override stops being
-- reachable, the fixtures must fail loudly instead of passing vacuously.
do
  local untagged = {}
  untagged[1] = "untagged"
  if pcall(M.json, untagged) then
    error(
      "ASSERTION FAILED: the resident JSON contract accepted an untagged array, "
        .. "so this guard no longer detects the defect it exists for",
      0
    )
  end
end

M.dispatch = function(command, params)
  local result = rawDispatch(command, params)
  local ok, encoded = pcall(M.json, result)
  if not ok then
    error(
      "ASSERTION FAILED: dispatch payload for '"
        .. tostring(command)
        .. "' is not encodable by the resident JSON contract: "
        .. tostring(encoded),
      0
    )
  end
  if type(encoded) ~= "string" or encoded == "" then
    error(
      "ASSERTION FAILED: dispatch payload for '"
        .. tostring(command)
        .. "' did not encode to a non-empty string",
      0
    )
  end
  return result
end
