-- Pub, the host's first button: Single Draft at once (the four shared taverns), start gold 100, and the gold
-- pool (trading, -pool, the autopool) locked for the first 230 s, then open between allies.
local M = require("modes")
M.boot()
M.pick("pub")
local gold = T.gold(1)

M.checkStart(gold, 100)
M.checkTaverns("SD")
M.checkPubTrading()
T.flush()
M.checkModes({ sel = 3, pub = 1, inhouse = 0, pro = 0 })
