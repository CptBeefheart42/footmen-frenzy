-- One way kills and deaths are counted, on both maps: the map's own -kd counters decide every case, and the kill
-- log (written by a bot client) and the stats rows of ff_result carry exactly those counters.
-- The client is a bot observer (slot 13), so the map writes the kill log and token-named files.
local lobby = T.defaultLobby()
lobby[13] = { name = "MangoThief#115445", observer = true }
T.lobby(lobby, 13)
T.boot()
T.advance(20)

local me, ally, enemy = 1, 2, 4
if T.map == "solo" then
    -- Solo has no teams; an alliance between slots 1 and 8 gives the ally case.
    ally, enemy = 8, 5
    for _, pair in ipairs({ { 1, 8 }, { 8, 1 } }) do
        SetPlayerAlliance(T.player(pair[1]), T.player(pair[2]), ALLIANCE_PASSIVE, true)
    end
end

local function counters()
    local out = {}
    for _, s in ipairs({ me, ally, enemy }) do
        out[s] = { uk = udg_unit_kills[s], hk = udg_hero_kills[s], ud = udg_unit_deaths[s], hd = udg_hero_deaths[s] }
    end
    return out
end

-- Runs one case and checks how much each counter moved: `want` = { [slot] = { uk=, hk=, ud=, hd= } }, missing = 0.
local function case(name, run, want)
    local before = counters()
    run()
    local after = counters()
    T.check("K/D: " .. name, function()
        for _, s in ipairs({ me, ally, enemy }) do
            for _, k in ipairs({ "uk", "hk", "ud", "hd" }) do
                local w = (want[s] or {})[k] or 0
                T.eq(after[s][k] - before[s][k], w, "slot " .. s .. " " .. k)
            end
        end
    end)
end

local foot = T.unit(me, "hfoo")
case("enemy footman killed: a kill and a death", function() T.kill(T.unit(enemy, "hfoo"), foot) end,
    { [me] = { uk = 1 }, [enemy] = { ud = 1 } })
case("own footman killed: not counted", function() T.kill(T.unit(me, "hfoo"), foot) end, {})
case("allied footman killed: not counted", function() T.kill(T.unit(ally, "hfoo"), foot) end, {})
case("illusion killed: not counted", function() T.kill(T.illusion(enemy, "hfoo"), foot) end, {})
case("killer already dead: counted for its owner", function()
    local dead = T.unit(me, "hfoo")
    dead.alive, dead.life = false, 0                 -- e.g. its missile lands after it died
    T.kill(T.unit(enemy, "hfoo"), dead)
end, { [me] = { uk = 1 }, [enemy] = { ud = 1 } })
case("creep killer: counted for nobody", function() T.kill(T.unit(me, "hfoo"), T.unit(25, "n00Q")) end, {})
case("no killer: counted for nobody", function() T.kill(T.unit(me, "hfoo"), nil) end, {})
case("enemy cannon tower kills a footman: kill for the tower owner, death for the footman owner",
    function() T.kill(T.unit(me, "hfoo"), T.unit(enemy, "hctw")) end,
    { [enemy] = { uk = 1 }, [me] = { ud = 1 } })
case("enemy hero killed: a hero kill and a hero death", function() T.kill(T.unit(enemy, "H005"), foot) end,
    { [me] = { hk = 1 }, [enemy] = { hd = 1 } })
case("allied hero killed: not counted", function() T.kill(T.unit(ally, "H005"), foot) end, {})
case("hero illusion killed: not counted", function() T.kill(T.illusion(enemy, "H005"), foot) end, {})
T.flush()

T.check("kill log owner rows = the map's counters", function()
    local log = T.killlog()
    for _, s in ipairs({ me, ally, enemy }) do
        local row = log[lobby[s].name] or { unit = 0, hero = 0, unit_died = 0, hero_died = 0 }
        T.eq(row.unit, udg_unit_kills[s], "slot " .. s .. " unit")
        T.eq(row.hero, udg_hero_kills[s], "slot " .. s .. " hero")
        T.eq(row.unit_died, udg_unit_deaths[s], "slot " .. s .. " unit_died")
        T.eq(row.hero_died, udg_hero_deaths[s], "slot " .. s .. " hero_died")
    end
end)
T.check("stats ukills / hkills = the map's counters", function()
    for _, s in ipairs({ me, ally, enemy }) do
        T.eq(T.stats(s).ukills, udg_unit_kills[s], "slot " .. s .. " ukills")
        T.eq(T.stats(s).hkills, udg_hero_kills[s], "slot " .. s .. " hkills")
    end
end)
T.check("one hero-kill feed row per counted hero kill", function()
    local feed = 0
    for _, line in ipairs(T.file(T.dataFile("ff_killlog")) or {}) do
        if line:match("^herokill,") then feed = feed + 1 end
    end
    T.eq(feed, udg_hero_kills[me] + udg_hero_kills[ally] + udg_hero_kills[enemy], "herokill rows")
end)
