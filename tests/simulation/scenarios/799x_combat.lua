-- Kills, denies and Transmute on the main map: the map's own -kd counters feed ukills/hkills,
-- our death handler feeds deny_* and tm_*.
T.lobby()
T.boot()
T.advance(20)

local foot = T.unitsOf(1, T.footman())[1]
T.kill(T.unit(4, T.footman()), foot)                -- enemy footman: a kill
T.kill(T.unit(1, T.footman()), foot)                -- own footman: deny
T.kill(T.unit(2, "earc"), foot)                -- allied archer (tier 1): deny
T.kill(T.unit(2, "hkni"), foot)                -- allied knight (not a feed unit): neither

local hero = T.unit(1, "H005")
T.learn(hero, "ANtm")
local hit = T.unit(4, T.footman()); T.cast(hero, "ANtm", hit); T.kill(hit, hero)
local saved = T.unit(4, T.footman()); T.cast(hero, "ANtm", saved); T.kill(saved, T.unitsOf(4, T.footman())[1])
local dodged = T.unit(4, T.footman()); T.cast(hero, "ANtm", dodged)
T.flush()

T.check("kills come from the map's -kd counters", function()
    local s = T.stats(1)
    T.eq(s.ukills, udg_unit_kills[1], "ukills vs udg_unit_kills")
    T.eq(s.ukills, 2, "ukills (enemy footman + transmute hit; denies don't count)")
    T.eq(s.hkills, 0, "hkills")
end)
T.check("denies: own and allied feed units, nothing else", function()
    local s = T.stats(1)
    T.eq(s.deny_own, 1, "deny_own")
    T.eq(s.deny_ally, 1, "deny_ally")
end)
T.check("transmute: hit, denied by the target's owner, dodged", function()
    local s = T.stats(1)
    T.eq(s.tm_casts, 3, "tm_casts")
    T.eq(s.tm_hits, 1, "tm_hits")
    T.eq(s.tm_denied, 1, "tm_denied")
    local o = T.stats(4)
    T.eq(o.tm_saves, 1, "tm_saves of the owner who killed the target")
    T.eq(o.deny_own, 1, "the save is also a deny of the owner's own footman")
end)
T.check("hero spell + skill build rows", function()
    T.eq(T.use(1, "spell").ANtm, 3, "use spell ANtm")
    local sk = T.rows("ff_result.txt", "skills")[1]
    T.ok(sk and sk.line == "skills,1,H005,ANtm", "skills row: " .. tostring(sk and sk.line))
end)
T.check("stats rows: every roster slot, state alive", function()
    for _, slot in ipairs({ 1, 2, 4 }) do
        local s = T.stats(slot)
        T.ok(s, "stats row for slot " .. slot)
        if s then T.eq(s.state, "alive", "state of slot " .. slot) end
    end
end)
