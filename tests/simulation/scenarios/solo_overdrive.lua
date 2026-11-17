-- Overdrive on Solo (4k game: Overdrive on). Every base spawns 2 footmen per cycle before the mass and 1 after it;
-- Overdrive (the base's 'A082') doubles its owner's spawns for 45 s, and when it runs out only that owner drops back.
--
-- Solo's own Mass START keeps the 2; the anchor hook in scripting/jass-solo/anchors.txt sets it to 1 as the main
-- map's Mass START does. Without it every base keeps spawning 2, Overdrive adds nothing, and the first Overdrive to
-- run out drops every player not in one to 1 (BASE Overdrive END loops over all 12 players).
--
-- Spawns are counted over whole cycles (8 s for the footman, spawn index 0) after the mass bonus waves are over.
-- The counted footmen are removed after each window so nobody reaches the unit cap.
local M = require("modes")
local SLOTS = { 1, 5, 8, 12 }
local CYCLE = 8.00
local OVERDRIVE = 45.00

local function clearSpawns()
    for _, slot in ipairs(SLOTS) do
        for _, u in ipairs(T.unitsOf(slot)) do
            if u.typeId == udg_spawn_unit[0] then RemoveUnit(u) end
        end
    end
end

--- Plays `cycles` spawn cycles and returns { [slot] = footmen spawned per cycle }.
local function spawnsPerCycle(cycles)
    clearSpawns()
    T.advance(cycles * CYCLE)
    local out = {}
    for _, slot in ipairs(SLOTS) do
        local n = 0
        for _, u in ipairs(T.unitsOf(slot)) do
            if u.typeId == udg_spawn_unit[0] then n = n + 1 end
        end
        out[slot] = n // cycles
    end
    clearSpawns()
    return out
end

local function overdrive(slot)
    T.cast(udg_base[slot], "A082")
    return TimerGetElapsed(FF_gameTimer)
end

local function advanceTo(t) T.advance(t - TimerGetElapsed(FF_gameTimer)) end

M.boot()
M.pick("4k")
T.advance(20)
T.pickHeroes()
advanceTo(7 * 60)    -- Overdrive is handed out at 7:00; the mass and its bonus waves are long over

local normal = spawnsPerCycle(3)
local t8 = overdrive(8)
local during8 = spawnsPerCycle(2)
overdrive(5)
advanceTo(t8 + OVERDRIVE + 1)
local after8 = spawnsPerCycle(2)    -- slot 8's Overdrive is over, slot 5's still runs
advanceTo(t8 + 2 * OVERDRIVE + 10)
local allOver = spawnsPerCycle(3)

T.check("Overdrive's mode is on in a 4k game", function()
    T.ok(udg_mode_overdrive, "udg_mode_overdrive")
end)
T.check("a running Overdrive keeps its owner's spawns when another player's Overdrive ends", function()
    T.eq(after8[5], 2 * normal[5], "slot 5 per cycle during its Overdrive (twice its normal)")
end)
T.check("after the mass every base spawns 1 footman per cycle", function()
    for _, slot in ipairs(SLOTS) do T.eq(normal[slot], 1, "slot " .. slot .. " per cycle") end
end)
T.check("Overdrive doubles its owner's spawns, nobody else's", function()
    T.eq(during8[8], 2 * normal[8], "slot 8 per cycle during its Overdrive (twice its normal)")
    T.eq(during8[1], normal[1], "slot 1 per cycle (its normal)")
    T.eq(during8[12], normal[12], "slot 12 per cycle (its normal)")
end)
T.check("one player's Overdrive running out leaves the other players' spawns alone", function()
    T.eq(after8[1], normal[1], "slot 1 per cycle (its normal)")
    T.eq(after8[12], normal[12], "slot 12 per cycle (its normal)")
end)
T.check("every base is back to its normal spawns when all Overdrives are over", function()
    for _, slot in ipairs(SLOTS) do T.eq(allOver[slot], 1, "slot " .. slot .. " per cycle") end
end)
