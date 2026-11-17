-- In-house (private / tournament), the host's third button, with Single Draft voted: the host is asked about
-- colossals, the host's vote decides the hero mode, and Single Draft brings the four shared taverns as in Pub.
-- In-house rules: start gold 275, no towers, no autosend, the gold pool open between allies from the start.
local M = require("modes")
M.boot()
M.pick("inhouse")
T.check("the host is asked about colossals", function() T.ok(M.declineColossals(), "colossal dialog shown") end)
M.vote(1, "SD")
local started = M.untilStarted(15)
local gold = T.gold(1)

T.check("the vote starts the game", function() T.ok(started, "game started") end)
M.checkStart(gold, 275)
M.checkTaverns("SD")
T.check("no towers and no autosend", function()
    T.ok(GetPlayerTechCount(T.player(1), T.id("R00F"), true) > 0, "tower removal (R00F) researched")
    local base = T.unitsOf(1, "hbar")[1]
    T.ok(base, "base")
    T.eq(GetUnitAbilityLevel(base, T.id("A06X")), 0, "autosend ability A06X")
end)
T.advance(1)
M.checkTradingOpen(true, "right after the start")
M.checkAlliesOnly(true, "right after the start")
M.checkPoolDialog(true, "right after the start")
M.checkAutopool("right after the start")
T.advance(20)
T.flush()
M.checkModes({ pub = 0, inhouse = 1 })
M.checkModes({ sel = 3 })
