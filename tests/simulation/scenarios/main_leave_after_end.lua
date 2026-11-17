-- Nothing after the game has ended changes its result: the bases decided it, so neither a unit
-- dying afterwards nor the winners quitting the score screen adds or moves a single result row.
T.lobby()
T.boot()
T.advance(60)
local foot = T.unitsOf(1, "hfoo")[1]
T.kill(T.unitsOf(4, "hbar")[1], foot)
T.advance(5)

local function resultRows()
    local out = {}
    for _, line in ipairs(T.file("ff_result.txt") or {}) do
        local kind = line:match("^([%w_]+),")
        if kind == "winner" or kind == "placement" or kind == "gameend" or kind == "out" or kind == "sidedead" then
            out[#out + 1] = line
        end
    end
    return table.concat(out, "\n")
end
local before = resultRows()

T.kill(T.unit(2, "hfoo"), T.unit(4, "hfoo"))
T.kill(T.unitsOf(2, "hbar")[1], foot)
T.advance(5)
T.leave(4)
T.leave(2)
T.leave(1)
T.advance(40)

T.check("the result rows after more deaths and the leaves are the ones at gameend", function()
    T.ok(before:find("gameend,", 1, true), "gameend before the leaves")
    T.eq(resultRows(), before, "result rows")
    T.eq(#T.events("winner"), 1, "winner rows")
    T.eq(#T.events("gameend"), 1, "gameend rows")
end)
