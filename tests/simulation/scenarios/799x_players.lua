-- Hero picks, chat-command counting (spam-safe) and a player leaving, on the main map.
T.lobby()
T.boot()
T.advance(20)

-- the bought hero appears in the tavern area; the map's TP_hero trigger makes it the player's hero
T.buyUnit(T.unitsOf(1)[1], T.shop("n02I"), "H005")
T.advance(2)

-- 10 messages in one second: only the burst limit (4) counts; later ones count again
for _ = 1, 10 do T.chat(1, "-kd") end
T.advance(2)
for _ = 1, 3 do T.chat(1, "-kd") end
T.chat(1, "-kdx")                               -- not a command (boundary check)
T.chat(1, "hello -kd")                          -- not a command (must start the message)

T.leave(2)
T.flush()

T.check("hero pick event through the map's tavern logic", function()
    local ev = T.events("pick")
    T.eq(#ev, 1, "pick events")
    if ev[1] then T.eq(table.concat(ev[1], ",", 3), "1,H005,pick", "pick slot,hero,kind") end
    T.eq(T.stats(1).hero_lvl, 1, "hero_lvl")
end)
T.check("chat commands: burst-limited and exact", function()
    T.eq(T.use(1, "cmd").kd, 7, "-kd counted (4 of the burst + 3)")
end)
T.check("a leaver is state=left with the time", function()
    local s = T.stats(2)
    T.eq(s.state, "left", "state")
    T.ok(s.left_t and tostring(s.left_t):match("^%d%d:%d%d$"), "left_t mm:ss: " .. tostring(s.left_t))
end)
