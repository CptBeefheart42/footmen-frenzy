-- Solo's Normal game, the host's first button: every player gets own taverns with heroes for sale.
local M = require("modes")
M.boot()
M.pick("normal")

T.check("the game starts once", function() T.eq(M.starts(), 1, "game starts") end)
M.checkOwnTaverns({ 1, 5, 8, 12 })
T.advance(20)
T.flush()
M.checkModes({ sel = 3, pub = 1, club777 = 0, overdrive = 0, nopool = 0 })
