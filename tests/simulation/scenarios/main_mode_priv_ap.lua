-- In-house with All Pick voted: the nine All Pick taverns, each with heroes for sale.
local M = require("modes")
M.boot()
M.pick("inhouse")
M.declineColossals()
M.vote(1, "AP")
M.untilStarted(15)
local gold = T.gold(1)

M.checkStart(gold, 275)
M.checkTaverns("AP")
T.advance(20)
T.flush()
M.checkModes({ sel = 2, pub = 0, inhouse = 1 })
