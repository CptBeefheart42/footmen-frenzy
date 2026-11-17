-- A whole (short) game on the main map: the last base of team 2 falls, the map's own logic
-- eliminates the player, and ff_result carries what the league scores (winner, placements, end).
T.lobby()
T.boot()
T.advance(60)
local foot = T.unitsOf(1, "hfoo")[1]
T.kill(T.unit(4, "hfoo"), foot)
T.kill(T.unitsOf(4, "hbar")[1], foot)
T.advance(5)

T.check("elimination, winner and placements", function()
    local out = T.events("out")
    T.eq(#out, 1, "out events")
    if out[1] then T.eq(out[1][3] .. "," .. out[1][4], "4,team2", "out slot,team") end
    T.eq(T.winner(), "team1,1:Alpha#1111;2:Bravo#2222", "winner team,members")
    T.eq(#T.events("placement"), 2, "placements")
    T.eq(#T.events("gameend"), 1, "gameend")
end)
T.check("final stats rows at game end", function()
    local s = T.stats(4)
    T.eq(s.state, "out", "loser state")
    T.eq(T.stats(1).ukills, 1, "winner ukills")
end)
T.checkFileShape()
