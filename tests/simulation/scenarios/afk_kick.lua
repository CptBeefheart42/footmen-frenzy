-- The AFK kick on both maps: a human player who still has no hero once 15 s have passed since the mass began and the
-- gold pool is open is removed from the game the way the map's own kick does it, warned 5 s after the mass began
-- (and 10 s before a later kick). The game doesn't count for them: no roster entry, no stats row, no place in a
-- side, an `afk` record instead. A computer without a hero and a player who picks before the kick stay.
--   main (Pub, the AFK host's default): the pool opens 230 s after the game started, long after the mass, so the
--     kick waits for it. Slot 2 AFK (slot 1's ally), slot 3 a computer without a hero, slot 4 picks 30 s after
--     the mass. Pro opens the pool at once: main_afk_kick_pro.
--   Solo (no pool): the kick 15 s after the mass. Slot 5 AFK, slot 12 a computer without a hero, slot 8 picks
--     between the warning and the kick.
local afk, late, cpu = 2, 4, 3
if T.map == "solo" then afk, late, cpu = 5, 8, 12 end
local lobby = T.defaultLobby()
lobby[cpu] = { name = "Computer#3", computer = true }
T.lobby(lobby)

-- the "pick a hero within N seconds" warnings each player was shown: N per warning
local warned = {}
local display = DisplayTimedTextToPlayer
function DisplayTimedTextToPlayer(p, x, y, d, msg)
    local n = msg and msg:match("Pick a hero within (%d+) seconds")
    if n then
        local s = GetPlayerId(p) + 1
        warned[s] = (warned[s] and warned[s] .. "," or "") .. n
    end
    if display then return display(p, x, y, d, msg) end
end

T.boot()
T.advance(20)
T.pickHero(1)

local waited = 0
while not udg_mass_active and waited < 300 do
    T.advance(1)
    waited = waited + 1
end
T.check("the mass begins (main: 90 s countdown, Solo: 50 s)", function()
    T.ok(udg_mass_active, "mass active after " .. waited .. " s")
end)

local function rosterSlots()
    local out = {}
    for _, kind in ipairs({ "roster", "roster_more" }) do
        for _, r in ipairs(T.events(kind)) do
            for slot in (r[2] or ""):gmatch("(%d+):") do out[#out + 1] = tonumber(slot) end
        end
    end
    table.sort(out)
    return table.concat(out, ",")
end

local function checkNotKicked(when)
    T.check(when .. ": nobody is removed", function()
        T.eq(#T.events("afk"), 0, "afk records")
        T.eq(T.result(afk), nil, "the map's verdict for the AFK slot")
    end)
end

local function checkKicked()
    T.check("the player without a hero is removed by the map's own kick", function()
        T.eq(T.result(afk), "defeat", "the map's verdict for the AFK slot")
        if T.map == "main" then
            T.eq(udg_leave_or_votekick[afk], true, "the map's leaver handling ran (leave_or_votekick)")
        else
            T.eq(udg_player_active[afk], false, "player_active of the AFK slot")
        end
    end)
    T.check("the computer without a hero and the late picker stay", function()
        for _, s in ipairs({ 1, late, cpu }) do T.eq(T.result(s), nil, "the map's verdict for slot " .. s) end
        T.eq(udg_player_active[late], true, "player_active of the late picker")
    end)
    T.check("the AFK slot doesn't count: an afk record, no roster entry, no stats row", function()
        local ev = T.events("afk")
        T.eq(#ev, 1, "afk records")
        if ev[1] then T.eq(ev[1][3] .. "," .. ev[1][4], afk .. "," .. lobby[afk].name, "afk slot,name") end
        T.eq(T.stats(afk), nil, "stats row of the AFK slot")
        T.ok(not rosterSlots():find("%f[%d]" .. afk .. "%f[%D]"), "roster without the AFK slot: " .. rosterSlots())
        T.ok(T.stats(1) ~= nil, "stats row of slot 1")
    end)
end

if T.map == "solo" then
    T.advance(4)
    T.pickHero(late)
    T.advance(9)
    T.check("one warning 5 s after the mass: 10 s left", function()
        T.eq(warned[afk], "10", "warnings to the AFK slot (seconds left)")
    end)
    checkNotKicked("13 s after the mass")
    T.advance(3)
    checkKicked()
else
    local pool = math.ceil(TimerGetRemaining(udg_timer_trading))
    T.check("Pub: the pool is still closed when the mass begins", function()
        T.ok(not udg_autopoool_allowed and pool > 30, "pool opens in " .. pool .. " s")
    end)
    T.advance(16)
    checkNotKicked("16 s after the mass, with the pool closed")
    T.advance(14)
    T.pickHero(late)
    local early = false
    local steps = 0
    while not udg_autopoool_allowed and steps < 300 do
        T.advance(1)
        steps = steps + 1
        early = early or (#T.events("afk") > 0 and not udg_autopoool_allowed)
    end
    T.check("nobody is removed while the pool is closed", function()
        T.ok(udg_autopoool_allowed, "the pool opened")
        T.eq(early, false, "a kick before the pool opened")
    end)
    T.advance(1)
    T.check("two warnings: 5 s after the mass, and 10 s before the kick", function()
        T.eq(warned[afk], (pool - 5) .. ",10", "warnings to the AFK slot (seconds left)")
    end)
    checkKicked()
end

T.advance(60)
T.check("a kick later in the game never happens again", function()
    T.eq(#T.events("afk"), 1, "afk records")
end)
