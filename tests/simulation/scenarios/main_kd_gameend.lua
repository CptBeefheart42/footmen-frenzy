-- The kill log stops with the result: once the game has a winner its owner rows are the final stats rows, even though
-- units go on dying (and the map's -kd counters go on counting) until the players leave.
local lobby = T.defaultLobby()
lobby[13] = { name = "MangoThief#115445", observer = true }
T.lobby(lobby, 13)
T.boot()
T.advance(60)

local foot = T.unitsOf(1, "hfoo")[1]
T.kill(T.unit(4, "hfoo"), foot)
T.kill(T.unit(4, "H005"), foot)
T.kill(T.unitsOf(4, "hbar")[1], foot)
T.advance(5)
local killsAtEnd = udg_unit_kills[1]

T.kill(T.unit(4, "hfoo"), foot)
T.kill(T.unit(4, "hfoo"), foot)
T.kill(T.unit(4, "H005"), foot)
T.flush()
T.advance(60)

T.check("the game has ended and the map kept counting afterwards", function()
    T.eq(#T.events("gameend"), 1, "gameend")
    T.ok(udg_unit_kills[1] > killsAtEnd, "map counter moved after gameend")
end)
T.check("kill log = final stats rows, not the later counters", function()
    local log = T.killlog()
    for _, s in ipairs({ 1, 2, 4 }) do
        local row = log[lobby[s].name] or { unit = 0, hero = 0 }
        T.eq(row.unit, T.stats(s).ukills, "slot " .. s .. " unit vs ukills")
        T.eq(row.hero, T.stats(s).hkills, "slot " .. s .. " hero vs hkills")
    end
    T.eq(log["Alpha#1111"].unit, killsAtEnd, "slot 1 unit kills at gameend")
end)
T.check("no hero-kill feed row after gameend", function()
    local feed = 0
    for _, line in ipairs(T.file(T.dataFile("ff_killlog")) or {}) do
        if line:match("^herokill,") then feed = feed + 1 end
    end
    T.eq(feed, 1, "herokill rows")
end)
