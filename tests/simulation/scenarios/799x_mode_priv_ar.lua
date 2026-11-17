-- In-house with All Random voted: no taverns, every player gets a random hero.
local M = require("modes")
M.boot()
M.pick("inhouse")
M.declineColossals()
M.vote(1, "AR")
M.untilStarted(15)
local gold = T.gold(1)

M.checkStart(gold, 275)
T.advance(1)
T.check("every player has a hero", function()
    for _, slot in ipairs({ 1, 2, 4 }) do
        local n = 0
        for _, u in ipairs(T.unitsOf(slot)) do if IsUnitType(u, UNIT_TYPE_HERO) then n = n + 1 end end
        T.eq(n, 1, "heroes of slot " .. slot)
    end
end)
T.advance(20)
T.flush()
M.checkModes({ sel = 1, pub = 0, inhouse = 1 })
