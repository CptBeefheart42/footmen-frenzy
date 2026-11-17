-- Transmute in flight when the side of its target drops out, on Solo (each player is a whole side). The projectile is
-- modelled by T.cast (the cast) and T.land (it arrives): the target's owner is destroyed or leaves in between. A
-- destroyed player's units die at once; Solo removes a lost player's units ~20 s later (its own SafeRemoval grace),
-- so a leaver's target is still there when the projectile lands. The control is a deny: the target's owner kills
-- it while the projectile flies.
T.lobby()
T.boot()
T.advance(20)
T.pickHeroes()
T.advance(10)

local hero = T.unit(1, "H005")
T.learn(hero, "ANtm")
local foot = T.unitsOf(1, "hfoo")[1] or T.unit(1, "hfoo")

-- the control: slot 12's own footman kills the target in flight
local denied = T.unit(12, "hfoo")
T.cast(hero, "ANtm", denied)
T.kill(denied, T.unit(12, "hfoo"))
T.land(hero, denied)
T.advance(5)

-- destroyed: slot 5 loses its base while the projectile flies
local destroyed = T.unit(5, "hfoo")
T.cast(hero, "ANtm", destroyed)
T.kill(T.unitsOf(5, "hbar")[1], foot)
T.land(hero, destroyed)
T.advance(5)

-- left: slot 8 leaves while the projectile flies
local left = T.unit(8, "hfoo")
T.cast(hero, "ANtm", left)
T.leave(8)
T.land(hero, left)
T.advance(30)
T.flush()

T.check("the targets of the lost players are gone after Solo's grace", function()
    T.ok(destroyed.removed, "destroyed player's target removed")
    T.ok(left.removed, "leaver's target removed")
end)
T.check("transmute counters: the leaver's target is hit, the deny and the destroyed player's are denied", function()
    local s = T.stats(1)
    T.eq(s.tm_casts, 3, "tm_casts")
    T.eq(s.tm_hits, 1, "tm_hits (the leaver's target, alive during Solo's grace)")
    T.eq(s.tm_denied, 2, "tm_denied (the deny, the destroyed player's unit killed by the map)")
    T.eq(T.stats(12).tm_saves, 1, "tm_saves of the owner who denied")
end)
T.check("slots 5 and 8 are out, the game goes on", function()
    local sides = {}
    for _, s in ipairs(T.events("sidedead")) do sides[#sides + 1] = s[3] end
    T.eq(table.concat(sides, " "), "team2 team3", "sidedead order")
    T.eq(#T.events("gameend"), 0, "no gameend (slots 1 and 12 remain)")
    T.eq(T.stats(5).state, "out", "stats,5 state")
    T.eq(T.stats(8).state, "left", "stats,8 state")
end)
T.checkNoResult()
