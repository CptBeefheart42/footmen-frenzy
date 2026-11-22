-- Pub (Single Draft) with per-player taverns (project setting taverns.per_player): every player hires from an own
-- draft tavern, stocked from the team's pool. A hero bought there closes that tavern, the team's other taverns stay
-- and no longer offer it (Single Draft: one of each hero per team); another player's tavern sells nothing to you.
local M = require("modes")
M.boot()
M.pick("pub")

M.checkPlayerTaverns("SD", { 1, 2, 4 })
T.check("a hero bought at the own tavern: the team's other taverns no longer offer it", function()
    local own, ally = DraftShop[5], DraftShop[6]
    local hero = M.heroesIn(own)[1]
    T.ok(M.sells(ally, hero), "slot 2's tavern offers " .. tostring(hero) .. " first")
    T.ok(T.buyUnit(T.unitsOf(1, "eTWP")[1], own, hero), "slot 1 buys " .. tostring(hero))
    T.advance(0.5)
    T.ok(udg_herO[1] ~= nil, "slot 1 has a hero")
    T.ok(DraftShop[5] == nil, "slot 1's tavern closed")
    T.ok(T.unitsOf(1, "eTWP")[1] == nil, "slot 1's wisp gone")
    T.ok(DraftShop[6] ~= nil, "slot 2's tavern still stands")
    T.ok(not M.sells(DraftShop[6], hero), "slot 2's tavern no longer offers " .. tostring(hero))
end)
T.check("another player's tavern sells nothing to you", function()
    local other = DraftShop[6]
    T.buyUnit(T.unitsOf(4, "eTWP")[1], other, M.heroesIn(other)[1])
    T.advance(0.5)
    T.ok(udg_herO[4] == nil, "slot 4 has no hero")
    T.ok(DraftShop[8] ~= nil, "slot 4's own tavern still stands")
end)
T.flush()
M.checkModes({ sel = 3, pub = 1 })
