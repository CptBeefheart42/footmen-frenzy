-- The host picks no game type: after 8 s the map starts a Pub game by itself, with everything Pub has
-- (main_mode_pub.lua).
local M = require("modes")
M.boot()
T.check("no game before the AFK default", function() T.eq(M.starts(), 0, "game starts") end)
M.pick("afk")
local started = M.untilStarted(4)
local gold = T.gold(1)

T.check("the AFK default starts the game", function() T.ok(started, "game started by 11 s") end)
T.advance(2)
M.checkStart(gold, 100)
M.checkTaverns("SD")
M.checkPubTrading()
T.flush()
M.checkModes({ sel = 3, pub = 1, inhouse = 0, pro = 0 })
