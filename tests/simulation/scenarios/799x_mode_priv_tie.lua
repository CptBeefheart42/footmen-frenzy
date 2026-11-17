-- In-house with a tied hero-mode vote (one vote Single Draft, one All Pick, the host does not vote): the game
-- falls back to Single Draft, with its taverns.
local M = require("modes")
M.boot()
M.pick("inhouse")
M.declineColossals()
M.vote(2, "SD")
M.vote(4, "AP")
local started = M.untilStarted(15)

T.check("a tied vote still starts the game", function() T.ok(started, "game started by the end of the vote") end)
M.checkTaverns("SD")
