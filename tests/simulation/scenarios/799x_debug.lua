-- Our -debug (projects/799x/addons/50-debug.j): any player may switch it on, and the modes row then says ffdebug=1,
-- also when the row was written before -debug.
local M = require("modes")
T.lobby()
T.boot()
T.advance(40)                                  -- the modes are final (AI hero-pick timer) before -debug
T.flush()
local before = M.modes()
T.chat(4, "-debug")
T.advance(1)
T.flush()

T.check("any player switches debug mode on", function()
    T.ok(FF_DBG_on, "FF_DBG_on")
    T.eq(T.saw(4, "not in games hosted by the EFL bots"), 0, "no refusal")
end)
T.check("the modes row says ffdebug, before and after -debug", function()
    T.eq(before and before.ffdebug, 0, "ffdebug before")
    T.eq(M.modes().ffdebug, 1, "ffdebug after")
end)
