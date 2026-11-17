-- Pub custom with extra modes bought by the host at the mode shop while the vote runs: No Transmute (h03V), 777
-- Club (h03Z: start gold 2000), King of the Hill off (h054) and "without Pooling" (h04B: -pool stays refused).
-- All Pick is voted, so the game does not depend on the Single Draft taverns.
local M = require("modes")
M.boot()
M.pick("custom")
local shop = T.unitsOf(1, "h03Y")[1]
for _, code in ipairs({ "h03V", "h03Z", "h054", "h04B" }) do T.buyUnit(T.unitsOf(1)[1], shop, code) end
M.vote(1, "AP")
local started = M.untilStarted(15)
local gold = T.gold(1)

T.check("the vote starts the game", function() T.ok(started, "game started") end)
M.checkStart(gold, 2000)
M.checkTaverns("AP")
T.advance(240)
M.checkPoolDialog(false, "after 240 s, without Pooling")
T.flush()
M.checkModes({ pub = 1, notransmute = 1, club777 = 1, koth = 0, sel = 2 })
