-- Transmute in flight when the side of its target drops out, on the main map. The projectile is modelled by T.cast
-- (the cast) and T.land (it arrives): the side's last player is destroyed or leaves in between, and the map removes
-- a destroyed side's units at once; a side that left keeps its units for 20 s (the map's SafeRemoval grace), so a
-- projectile in flight lands on a living unit and counts as a hit. The engine's own handling of the projectile is the
-- e2e scenarios' part (tests/e2e/addons/transmute); here the map's triggers and the addons must handle a target
-- that died, vanished or outlived its side. The control is a deny: the target's owner kills it while the projectile
-- flies.
T.lobby({ [1] = { name = "Alpha#1111" }, [2] = { name = "Bravo#2222" },
          [4] = { name = "Delta#4444" }, [5] = { name = "Echo#5555" }, [6] = { name = "Foxtrot#6666" },
          [7] = { name = "Golf#7777" }, [8] = { name = "Hotel#8888" }, [9] = { name = "India#9999" },
          [10] = { name = "Kilo#1010" } })
T.boot()
T.advance(20)
T.pickHeroes()
T.advance(10)

local hero = T.unit(1, "H005")
T.learn(hero, "ANtm")
local foot = T.unitsOf(1, "hfoo")[1] or T.unit(1, "hfoo")

-- the control: team 4's own footman kills the target in flight
local denied = T.unit(10, "hfoo")
T.cast(hero, "ANtm", denied)
T.kill(denied, T.unit(10, "hfoo"))
T.land(hero, denied)
T.advance(5)

-- destroyed: team 2's last player (slot 4) loses its base while the projectile flies
for _, s in ipairs({ 5, 6 }) do
    T.kill(T.unitsOf(s, "hbar")[1], foot)
    T.advance(3)
end
local destroyed = T.unit(4, "hfoo")
T.cast(hero, "ANtm", destroyed)
T.kill(T.unitsOf(4, "hbar")[1], foot)
T.land(hero, destroyed)
T.advance(5)

-- left: team 3's last player (slot 7) leaves while the projectile flies
for _, s in ipairs({ 8, 9 }) do
    T.leave(s)
    T.advance(3)
end
local left = T.unit(7, "hfoo")
T.cast(hero, "ANtm", left)
T.leave(7)
T.land(hero, left)
T.advance(25)
T.flush()

T.check("the targets of the lost sides are gone", function()
    T.ok(destroyed.removed, "destroyed side's target removed")
    T.ok(left.removed, "leaver's target removed")
end)
T.check("transmute counters: three casts; the leaver's unit is hit, the deny and the destroyed side's kill are denied", function()
    local s = T.stats(1)
    T.eq(s.tm_casts, 3, "tm_casts")
    T.eq(s.tm_hits, 1, "tm_hits (the leaver's unit outlives the leave by 20 s)")
    T.eq(s.tm_denied, 2, "tm_denied (the deny, the destroyed side's unit killed by the map)")
    T.eq(T.stats(10).tm_saves, 1, "tm_saves of the owner who denied")
end)
T.check("teams 2 and 3 are out, the game goes on", function()
    local sides = {}
    for _, s in ipairs(T.events("sidedead")) do sides[#sides + 1] = s[3] end
    T.eq(table.concat(sides, " "), "team2 team3", "sidedead order")
    T.eq(#T.events("gameend"), 0, "no gameend (teams 1 and 4 remain)")
    T.eq(T.stats(4).state, "out", "stats,4 state")
    T.eq(T.stats(7).state, "left", "stats,7 state")
end)
T.checkNoResult()
