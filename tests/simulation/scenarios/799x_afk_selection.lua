-- The AFK kick counts only selections of the player's own units: the map selects shops for the players (799X selects
-- the team's draft tavern for everyone at the start of a draft), and a selection the map makes is not the player's.
-- Pro, so the kick comes 15 s after the mass. Slot 2 only "selects" a neutral shop and is removed; slot 4 selects
-- its own footman and stays.
local M = require("modes")
M.boot()
M.pick("pro")
T.advance(5)
T.pickHero(1)
local shop = T.unit(PLAYER_NEUTRAL_PASSIVE + 1, "ntav")
T.select(2, shop)
T.select(4, T.unit(4, T.footman()))

local waited = 0
while not udg_mass_active and waited < 300 do
    T.advance(1)
    waited = waited + 1
end
T.advance(16)
T.check("selecting a neutral shop is no activity: the player is removed", function()
    T.eq(T.result(2), "defeat", "the map's verdict for slot 2")
end)
T.check("selecting an own unit is activity: the player stays", function()
    T.eq(T.result(4), nil, "the map's verdict for slot 4")
end)
