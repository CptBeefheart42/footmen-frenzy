-- -sub switched on (799X built with settings sub.enabled): a player leaves, an ally picks the observer, the observer
-- accepts and plays the slot on. The result file records it: a `sub` row, the roster keeps the player who left, and the
-- slot's stats go on (state=sub) instead of stopping at the leave.
local lobby = T.defaultLobby()
lobby[13] = { name = "Oscar#1313", observer = true }
T.lobby(lobby)
T.boot()
T.advance(20)
T.pickHeroes()
T.advance(10)
T.leave(2)
T.advance(1)
T.chat(1, "-sub")
T.advance(0.5)
T.click(1, "Oscar")
T.advance(0.5)
T.click(13, "Yes")
T.advance(1)
T.flush()

T.check("a sub record names the slot and the substitute", function()
    local ev = T.events("sub")
    T.eq(#ev, 1, "sub records")
    if ev[1] then T.eq(ev[1][3] .. "," .. ev[1][4], "2,Oscar#1313", "slot,substitute") end
end)
T.check("the roster keeps the player who left", function()
    local roster = T.events("roster")[1]
    local line = roster and roster[2] or ""
    T.ok(line:find("2:Bravo#2222", 1, true), "roster: " .. line)
    T.ok(not line:find("Oscar", 1, true), "the substitute is not in the roster: " .. line)
end)
T.check("the slot's stats go on with state=sub", function()
    local s = T.stats(2)
    T.ok(s and s.state == "sub", "stats state of slot 2: " .. tostring(s and s.state))
end)
