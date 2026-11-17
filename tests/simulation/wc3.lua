-- Simulated WC3 engine for the built map scripts (tests/simulation).
--
-- The build runner translates common.j, Blizzard.j and the map's injected war3map.j into Lua
-- (`jass-to-lua`). The engine part the game itself would supply — the "natives", the functions
-- common.j only declares — comes from the modules in engine/:
--   core      handles, native stubs, the game clock and its threads
--   players   players and player groups (forces)
--   units     unit types, units, items, unit groups, locations and rects
--   events    triggers and events, event responses, regions, dialogs
--   data      timers, hashtables, strings, math, random numbers
--   preload   Preload files (what the map writes to disk)
--   misc      UI, effects and game settings without behaviour
--   api       T.*: the lobby and playing the game
--   checks    T.*: reading what the map wrote, and the checks
-- Every native in common.j that no module models gets a stub that returns its type's default and
-- is counted (T.unmodelled). Blizzard.j's functions run as they are.
--
-- Returns the engine state W; T (the scenario API) is a global the scenarios use.
local here = (...) or "."
local W = {}
T = {}
for _, m in ipairs({ "core", "players", "units", "events", "data", "preload", "misc", "api", "checks" }) do
    assert(loadfile(here .. "/engine/" .. m .. ".lua"))(W)
end
return W
