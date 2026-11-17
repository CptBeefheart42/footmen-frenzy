-- Forfeit by leaving, on the main map: the other sides leave instead of losing their bases. A player
-- whose allies stay is no elimination (the map hands their base over); a team that has left entirely is
-- out, and the side left standing wins. The bot scores this file, never the order people left in.
T.lobby({ [1] = { name = "Alpha#1111" }, [2] = { name = "Bravo#2222" }, [4] = { name = "Delta#4444" },
    [7] = { name = "Golf#7777" }, [8] = { name = "Hotel#8888" }, [10] = { name = "Kilo#1010" } })
T.boot()
T.advance(60)

T.leave(10)                                      -- team 4: its only player
T.advance(3)
T.leave(7)                                       -- team 3: one of two, Hotel stays
T.advance(3)

T.check("a leaver with an ally still in is no elimination", function()
    local outs = {}
    for _, o in ipairs(T.events("out")) do outs[#outs + 1] = o[3] end
    T.eq(table.concat(outs, " "), "10", "out events so far")
    T.eq(#T.events("winner"), 0, "no winner yet")
    T.eq(#T.events("gameend"), 0, "no gameend yet")
end)

T.leave(8)                                       -- team 3 has left entirely
T.advance(3)
T.leave(4)                                       -- team 2: the last side but one
T.advance(5)

T.check("the last side standing wins; placements follow the order the sides went out", function()
    local sides = {}
    for _, s in ipairs(T.events("sidedead")) do sides[#sides + 1] = s[3] end
    T.eq(table.concat(sides, " "), "team4 team3 team2", "sidedead order")
    T.eq(T.winner(), "team1,1:Alpha#1111;2:Bravo#2222", "winner team,members")
    T.eq(T.placements(), "1:team1 2:team2 3:team3 4:team4", "placements")
    T.eq(#T.events("gameend"), 1, "gameend")
end)
T.check("leavers are state=left with the time, the winners alive", function()
    for _, s in ipairs({ 4, 7, 8, 10 }) do
        local st = T.stats(s)
        T.ok(st, "stats," .. s)
        if st then
            T.eq(st.state, "left", "stats," .. s .. " state")
            T.ok(tostring(st.left_t):match("^%d%d:%d%d$"), "stats," .. s .. " left_t " .. tostring(st.left_t))
        end
    end
    T.eq(T.stats(1).state, "alive", "stats,1 state")
    T.eq(T.stats(2).state, "alive", "stats,2 state")
end)
T.check("the map's own END declares the same winner", function()
    T.advance(25)                                    -- END waits ~18 s before victory / defeat
    T.eq(T.result(1), "victory", "the map's verdict for slot 1")
    T.eq(T.result(2), "victory", "the map's verdict for slot 2")
end)
