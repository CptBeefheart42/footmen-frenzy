-- Pub custom, the host's fourth button, with Single Draft voted: a Pub game whose host may buy extra modes at the
-- mode shop while everybody votes the hero mode. Single Draft brings the four shared taverns as in Pub, and
-- Pub's gold rules apply (799x_mode_pub.lua).
local M = require("modes")
M.boot()
M.pick("custom")
T.check("the mode shop offers the extra modes", function()
    local shop = T.unitsOf(1, "h03Y")[1]
    T.ok(shop, "mode shop")
    local stock = " " .. table.concat(T.stock(shop), " ") .. " "
    for _, code in ipairs({ "h03V", "h03Z", "h04B", "h054" }) do
        T.ok(stock:find(" " .. code .. " ", 1, true), code .. " in stock:" .. stock)
    end
end)
M.vote(1, "SD")
local started = M.untilStarted(15)
local gold = T.gold(1)

T.check("the vote starts the game", function() T.ok(started, "game started") end)
M.checkStart(gold, 100)
M.checkTaverns("SD")
M.checkPubTrading()
T.flush()
M.checkModes({ pub = 1, inhouse = 0, pro = 0 })
M.checkModes({ sel = 3 })
