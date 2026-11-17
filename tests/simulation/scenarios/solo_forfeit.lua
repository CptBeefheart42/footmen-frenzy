-- Forfeit by leaving on Solo (1v1v1v1): a leave takes the player out at once. The last one in wins,
-- the others place in reverse order of leaving -- and the map's own END agrees with the addon.
T.lobby()
T.boot()
T.advance(20)
T.pickHeroes()
T.advance(78)
for _, s in ipairs({ 12, 5, 8 }) do
    T.leave(s)
    T.advance(3)
end
T.advance(5)

T.check("the last player in wins; placements in reverse order of leaving", function()
    T.eq(T.winner(), "team1,1:Alpha#1111", "winner")
    T.eq(T.placements(), "1:team1 2:team3 3:team2 4:team4", "placements")
    T.eq(#T.events("gameend"), 1, "gameend")
end)
T.check("leavers are state=left", function()
    for _, s in ipairs({ 5, 8, 12 }) do T.eq(T.stats(s) and T.stats(s).state, "left", "stats," .. s .. " state") end
end)
T.check("the map's own END declares the same winner", function()
    T.advance(25)                                    -- END waits 20 s before victory / defeat
    T.eq(udg_player_active[1], true, "player_active[1]")
    T.eq(T.result(1), "victory", "the map's verdict for slot 1")
end)
