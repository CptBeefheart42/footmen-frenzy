-- In-house where nobody votes for a hero mode: the game falls back to Single Draft, with its taverns.
local M = require("modes")
M.boot()
M.pick("inhouse")
M.declineColossals()
local started = M.untilStarted(15)

T.check("a vote without votes still starts the game", function() T.ok(started, "game started by the end of the vote") end)
M.checkTaverns("SD")
