-- Solo's 4k game, the host's second button: a Normal game (solo_mode_normal.lua) with 777 Club (start gold 2000)
-- and Overdrive on.
local M = require("modes")
M.boot()
M.pick("4k")
local gold = T.gold(1)

M.checkStart(gold, 2000)
M.checkOwnTaverns({ 1, 5, 8, 12 })
T.advance(20)
T.flush()
M.checkModes({ sel = 3, pub = 1, club777 = 1, overdrive = 1, nopool = 0 })
