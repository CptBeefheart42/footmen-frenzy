-- The AFK kick in a Pro game: the gold pool is open from the first second, so a player without a hero is removed
-- 15 s after the mass began, as on Solo (afk_kick: the Pub game waits for the pool). Slot 2 never picks a hero.
local M = require("modes")
M.boot()
M.pick("pro")
T.advance(5)
T.pickHero(1)
T.pickHero(4)

local waited = 0
while not udg_mass_active and waited < 300 do
    T.advance(1)
    waited = waited + 1
end
T.check("the mass begins", function()
    T.ok(udg_mass_active, "mass active after " .. waited .. " s")
end)
T.advance(13)
T.check("13 s after the mass: nobody is removed", function()
    T.eq(#T.events("afk"), 0, "afk records")
end)
T.advance(3)
T.check("16 s after the mass: the player without a hero is removed", function()
    T.eq(#T.events("afk"), 1, "afk records")
    T.eq(T.result(2), "defeat", "the map's verdict for slot 2")
    T.eq(T.result(1), nil, "the map's verdict for slot 1")
    T.eq(T.result(4), nil, "the map's verdict for slot 4")
end)
