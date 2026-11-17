-- Kills whose killer is dead, or a spell dummy, by the time the damage lands, on both maps. Each counts for the
-- killer's owner in the map's -kd counters, the kill log and the stats rows (they carry the map's counters):
--   * a killer that is already dead counts (the map's alive check is hooked out: anchors.txt). A coin-factory
--     moneybag (Lawyer's Student Debt: n02W/n02X/n02Y) dies in its own Kaboom before the blast kills.
--   * a spell dummy lives until its spell's damage is over (anchors.txt), so the last damage tick still has a
--     living killer: Objection's Soul Burn, Parasite, Hellfire's Flame Strikes, Jaina's fire orb, Thor's hammer.
--     A dummy that died earlier would be removed (h01K: 0.1 s death time) and leave no killer at all.
-- The client is a bot observer (slot 13), so the map writes the kill log.
local lobby = T.defaultLobby()
lobby[13] = { name = "MangoThief#115445", observer = true }
T.lobby(lobby, 13)
T.boot()
T.advance(20)
T.pickHeroes()

local me, enemy = 1, 4
if T.map == "solo" then enemy = 5 end

local function counters()
    local out = {}
    for _, s in ipairs({ me, enemy }) do
        out[s] = { uk = udg_unit_kills[s], hk = udg_hero_kills[s], ud = udg_unit_deaths[s], hd = udg_hero_deaths[s] }
    end
    return out
end

local function herokillRows()
    local n = 0
    for _, line in ipairs(T.file(T.dataFile("ff_killlog")) or {}) do
        if line:match("^herokill,") then n = n + 1 end
    end
    return n
end

-- Runs one case and checks how much each counter moved (`want` as in kd.lua, missing = 0) and that every counted
-- hero kill also reached the kill log's feed.
local function case(name, run, want)
    T.flush()
    local before, feedBefore = counters(), herokillRows()
    run()
    local after = counters()
    T.flush()
    T.check(name, function()
        for _, s in ipairs({ me, enemy }) do
            for _, k in ipairs({ "uk", "hk", "ud", "hd" }) do
                local w = (want[s] or {})[k] or 0
                T.eq(after[s][k] - before[s][k], w, "slot " .. s .. " " .. k)
            end
        end
        T.eq(herokillRows() - feedBefore, (want[me] or {}).hk or 0, "herokill rows")
    end)
end

local heroKill = { [me] = { hk = 1 }, [enemy] = { hd = 1 } }

-- A moneybag explodes: Kaboom kills the moneybag first, then its blast kills `victim`.
local function kaboom(bag, victim)
    local goblin = T.unit(me, bag)
    T.kill(goblin, nil)
    T.kill(victim, goblin)
end

-- A hero of type `heroType` for slot `me` with `levels` levels of skill `skill`.
local function caster(heroType, skill, levels)
    local hero = T.unit(me, heroType)
    for _ = 1, levels do T.learn(hero, skill) end
    return hero
end

-- The newest living unit of type `code` that slot `me` owns.
local function newest(code)
    local all = T.unitsOf(me, code)
    return all[#all]
end

-- How long the dummy spell `ability` deals damage at `level`: the longer of its two durations (normal, hero).
local function lasts(ability, level)
    return math.max(T.abilityReal(ability, "adur", level), T.abilityReal(ability, "ahdu", level))
end

-- The last damage tick of a dummy's spell kills the enemy hero `victim`: `secs` (the spell's duration) after the
-- order, plus the moment the spell takes to start (cast point, missile, effect delay).
local function lastTick(dummy, victim, secs)
    T.check("a dummy exists for the last tick", function() T.ok(dummy ~= nil, "no dummy") end)
    T.advance(secs + 0.2)
    T.kill(victim, dummy)
end

case("control: a living killer's hero kill counts", function() T.kill(T.unit(enemy, "H005"), T.unit(me, T.footman())) end,
    heroKill)

for _, bag in ipairs({ "n02W", "n02X", "n02Y" }) do
    case("coin factory: " .. bag .. " Kaboom kills an enemy hero", function() kaboom(bag, T.unit(enemy, "H005")) end,
        heroKill)
end
case("coin factory: Kaboom kills an enemy footman", function() kaboom("n02W", T.unit(enemy, T.footman())) end,
    { [me] = { uk = 1 }, [enemy] = { ud = 1 } })

case("objection: the last Soul Burn tick kills the enemy hero", function()
    local hero = T.unit(enemy, "H005")
    T.cast(caster("O00O", "A0M1", 6), "A0M1", hero)
    local dummy = newest("h01K")
    T.check("objection: the dummy casts Soul Burn (ANso)", function()
        T.ok(dummy and dummy.abilities[T.id("ANso")], "no h01K with ANso")
    end)
    lastTick(dummy, hero, lasts("ANso", 6))
end, heroKill)

case("parasite: the last Parasite tick kills the enemy hero", function()
    local hero = T.unit(enemy, "H005")
    T.cast(caster("H005", "A05E", 1), "A05E", hero)
    lastTick(newest("h01K"), hero, lasts("A0HL", 1))
end, heroKill)

case("hellfire: the last Flame Strike tick kills the enemy hero", function()
    local hero = T.unit(enemy, "H005")
    T.cast(caster("H005", "A0CC", 1), "A0CC", nil)
    lastTick(newest("h01K"), hero, lasts("A0CD", 1))
end, heroKill)

case("jaina: the fire orb's last Rain of Fire burn kills the enemy hero", function()
    local hero = T.unit(enemy, "H005")
    T.cast(caster("H005", "A048", 3), "A048", nil)
    local orb = udg_orb[2]
    T.advance(4.1)                                   -- the orbs vanish 4 s after the cast (its three waits)
    T.check("jaina: the orbs are hidden, not removed", function()
        T.ok(orb and orb.hidden and not orb.removed, "fire orb removed or still shown")
    end)
    lastTick(orb, hero, lasts("A064", 3))
end, heroKill)

case("thor: Mjolnir's Firebolt lands after the hammer hit", function()
    local thor = caster("H048", "A0EC", 1)
    udg_herO[me] = thor
    local hero = T.unit(enemy, "H005", 60, 0)
    T.cast(thor, "A0EC", hero)
    T.advance(0.1)                                   -- the hammer reaches the hero and casts its Firebolt
    lastTick(udg_dummy_mjolnir[me], hero, 0.4)       -- the missile's flight (up to 120 away)
end, heroKill)
