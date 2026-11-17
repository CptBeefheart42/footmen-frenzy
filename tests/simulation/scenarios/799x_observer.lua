-- An observer watches a whole game on the main map: they sit in an observer slot (13 and up), so
-- they never take part in the result — no roster entry, no stats, no side, no placement.
local lobby = T.defaultLobby()
lobby[13] = { name = "Oscar#1313", observer = true }
T.lobby(lobby)
T.boot()
T.advance(60)
T.chat(13, "-kd")
local foot = T.unitsOf(1, T.footman())[1]
T.kill(T.unitsOf(4, "hbar")[1], foot)
T.advance(5)

T.check("the observer is not in the roster", function()
    for _, kind in ipairs({ "roster", "roster_more" }) do
        for _, r in ipairs(T.rows("ff_result.txt", kind)) do
            T.ok(not r.line:find("Oscar#1313", 1, true), kind .. " row names the observer: " .. r.line)
        end
    end
    T.ok(#T.rows("ff_result.txt", "roster") == 1, "a roster row")
end)
T.check("no stats or usage rows for the observer", function()
    T.eq(T.stats(13), nil, "stats,13")
    for _, r in ipairs(T.rows("ff_result.txt", "use")) do T.ok(r.parts[2] ~= "13", "use row of the observer: " .. r.line) end
end)
T.check("the result is decided by the players alone", function()
    T.eq(T.winner(), "team1,1:Alpha#1111;2:Bravo#2222", "winner team,members")
    T.eq(T.placements(), "1:team1 2:team2", "placements")
    for _, line in ipairs(T.file("ff_result.txt") or {}) do
        T.ok(not line:find("Oscar#1313", 1, true), "a row names the observer: " .. line)
    end
end)
