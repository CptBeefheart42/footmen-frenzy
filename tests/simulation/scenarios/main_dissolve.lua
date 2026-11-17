-- A game that dissolves on the main map: everybody leaves while three sides still stand. No side won,
-- so the file must not say one did (no winner / placement / gameend): the bot then scores nothing.
-- What did happen is still in the file: the roster and who left when.
T.lobby({ [1] = { name = "Alpha#1111" }, [4] = { name = "Delta#4444" }, [7] = { name = "Golf#7777" } })
T.boot()
T.advance(5)

T.check("the roster is on disk from the start", function()
    local r = T.rows("ff_result.txt", "roster")[1]
    T.ok(r and r.line:find("1:Alpha#1111", 1, true) and r.line:find("7:Golf#7777", 1, true),
        "roster row: " .. tostring(r and r.line))
end)

T.advance(55)
T.leave(4)
T.leave(7)
T.leave(1)
T.advance(40)

T.checkNoResult()
T.check("the leaves are recorded", function()
    for _, s in ipairs({ 1, 4, 7 }) do
        local st = T.stats(s)
        T.eq(st and st.state, "left", "stats," .. s .. " state")
    end
end)
