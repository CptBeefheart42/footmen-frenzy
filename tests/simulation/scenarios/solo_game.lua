-- A whole Solo (1v1v1v1) game. The lobby's players sit in slots 1, 5, 8 and 12 (the map's
-- InitCustomTeams: Player(0/4/7/11)), one per side of ff_result's slot triples.
T.lobby()
T.boot()
T.advance(40)

local foot = T.unit(1, "hfoo")
T.kill(T.unit(5, "hfoo"), foot)
T.kill(T.unit(8, "hfoo"), foot)
T.kill(T.unit(1, "hfoo"), foot)                    -- own footman: a deny, not a kill
local hero = T.buyUnit(T.unitsOf(1)[1], T.unitsOf(1, "n02I")[1], "H005")   -- each player has an own tavern on Solo
T.buyUnit(hero, T.shop("n00R"), "n00Q")
T.buyItem(hero, T.shop("n01B"), "ratc")
T.advance(2)
for _, s in ipairs({ 5, 8, 12 }) do
    T.kill(T.unitsOf(s, "hbar")[1], foot)
    T.advance(3)
end
T.advance(5)

T.check("four sides, placements in reverse elimination order", function()
    T.eq(#T.events("out"), 3, "out events")
    T.eq(T.winner(), "team1,1:Alpha#1111", "winner")
    T.eq(T.placements(), "1:team1 2:team4 3:team3 4:team2", "placements")
end)
T.check("kills, deny and creep on Solo", function()
    local s = T.stats(1)
    T.eq(s.ukills, udg_unit_kills[1], "ukills vs udg_unit_kills")
    T.eq(s.ukills, 2, "ukills")
    T.eq(s.deny_own, 1, "deny_own")
    T.eq(s.creeps, 1, "creeps"); T.eq(s.creep_gold, 250, "creep_gold")
    T.eq(T.use(1, "item").ratc, 1, "item")
end)
T.check("hero pick from the player's own tavern", function()
    local ev = T.events("pick")
    T.eq(#ev, 1, "pick events")
    if ev[1] then T.eq(table.concat(ev[1], ",", 3), "1,H005,pick", "pick") end
end)
T.check("Solo modes row (nopool instead of the main map's extras)", function()
    local m = T.rows("ff_result.txt", "modes")[1]
    T.ok(m and m.kv.nopool ~= nil and m.kv.pro == nil, "modes row: " .. tostring(m and m.line))
end)
T.checkFileShape()
