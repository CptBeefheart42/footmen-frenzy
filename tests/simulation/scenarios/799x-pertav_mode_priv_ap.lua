-- In-house All Pick with per-player taverns: every player's own draft tavern offers the All Pick heroes.
local M = require("modes")
M.boot()
M.pick("inhouse")
M.declineColossals()
M.vote(1, "AP")
M.untilStarted(15)

M.checkPlayerTaverns("AP", { 1, 2, 4 })
T.check("All Pick: a hero bought at the own tavern stays on offer for the ally", function()
    local hero = M.heroesIn(DraftShop[5])[1]
    T.ok(T.buyUnit(T.unitsOf(1, "eTWP")[1], DraftShop[5], hero), "slot 1 buys " .. tostring(hero))
    T.advance(0.5)
    T.ok(udg_herO[1] ~= nil, "slot 1 has a hero")
    T.ok(M.sells(DraftShop[6], hero), "slot 2's tavern still offers " .. tostring(hero))
end)
T.advance(20)
T.flush()
M.checkModes({ sel = 2, inhouse = 1 })
