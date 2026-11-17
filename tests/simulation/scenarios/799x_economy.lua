-- Purchases, research, base tiers, towers and the gold pool on the main map.
T.lobby()
T.boot()
T.advance(20)
T.pickHeroes()

local hero = T.unit(1, "H005")
T.buyItem(hero, T.shop("n01B"), "ratc")
T.buyItem(hero, T.shop("n01B"), "ratc")
T.buyUnit(hero, T.shop("n00R"), "n00Q")
local base = T.unitsOf(1, "hbar")[1]
T.research(base, "Rhme"); T.research(base, "Rhme"); T.research(base, "Rhar")
T.research(T.unitsOf(1, "n003")[1], "R001")
T.upgrade(base, "h00W")
local tower = T.unitsOf(1, "hwtw")[1]
T.upgrade(tower, "hgtw"); T.upgrade(tower, "hwtw")
T.flush()

T.check("item and unit purchases", function()
    T.eq(T.use(1, "item").ratc, 2, "items bought")
    T.eq(T.use(1, "unit").n00Q, 1, "creep bought")
    local s = T.stats(1)
    T.eq(s.creeps, 1, "creeps")
    T.eq(s.creep_gold, 250, "creep_gold (price from the lumber-bounty field)")
end)
T.check("research levels", function()
    local s = T.stats(1)
    T.eq(s.atk_lvl, 2, "atk_lvl (Rhme)")
    T.eq(s.def_lvl, 1, "def_lvl (Rhar)")
    T.eq(s.team_res, 1, "team_res (research at n003)")
    local t = T.use(1, "tech")
    T.eq(t.Rhme, 2, "use tech Rhme"); T.eq(t.R001, 1, "use tech R001")
end)
T.check("research paid for: levels researched and their sum", function()
    local n, sum = T.use(1, "rsch"), T.use(1, "rlvl")
    T.eq(n.Rhme, 2, "rsch Rhme"); T.eq(sum.Rhme, 1 + 2, "rlvl Rhme")
    T.eq(n.Rhar, 1, "rsch Rhar"); T.eq(sum.Rhar, 1, "rlvl Rhar")
end)

-- The team research at n003 is copied to every ally for free; an ally who then researches the next level reaches
-- level 2 and paid for that one level only.
T.check("a team copy is free: the ally pays only for the level they research", function()
    T.eq(GetPlayerTechCount(T.player(2), T.id("R001"), true), 1, "the ally got R001 1 for free")
    T.eq(T.use(2, "rsch").R001, nil, "no rsch for the free copy")
    T.research(T.unitsOf(2, "n003")[1], "R001")
    T.flush()
    T.eq(T.use(2, "tech").R001, 2, "tech is the level reached")
    T.eq(T.use(2, "rsch").R001, 1, "rsch: one level researched")
    T.eq(T.use(2, "rlvl").R001, 2, "rlvl: that level was the 2nd")
end)

local sold = T.buyItem(hero, T.shop("n01B"), "rde3")
T.pawnItem(hero, T.shop("n01B"), sold)
T.flush()
T.check("an item sold back to a shop", function()
    T.eq(T.use(1, "pawn").rde3, 1, "pawn rde3")
    T.eq(T.use(1, "item").rde3, 1, "the purchase still counts as bought")
end)

T.check("base tier event and tower upgrades", function()
    local ev = T.events("baseup")
    T.eq(#ev, 1, "baseup events")
    if ev[1] then T.eq(ev[1][3] .. "," .. ev[1][4], "1,h00W", "baseup slot,type") end
    local tw = T.use(1, "tower")
    T.eq(tw.hgtw, 1, "tower upgrade"); T.eq(tw.hwtw, 1, "tower downgrade")
end)

T.advance(60)
T.buyItem(hero, T.shop("n01B"), "I01Z")
T.buyItem(T.unit(2, "H005"), T.shop("n01B"), "I002")
T.buyUnit(hero, T.shop("n00R"), "o00B")
T.useItem(hero, T.buyItem(hero, T.shop("n01B"), "I033"))
T.useItem(hero, T.buyItem(hero, T.shop("n01B"), "I005"))
T.useItem(hero, T.buyItem(hero, T.shop("n01B"), "rde3"))
T.flush()
T.check("key items bought and used are timed events", function()
    local function rows(kind)
        local out = {}
        for _, e in ipairs(T.events(kind)) do out[#out + 1] = e[3] .. "," .. e[4] end
        return table.concat(out, " ")
    end
    T.eq(rows("buy"), "1,I01Z 2,I002 1,o00B", "buy events: the sword, the ring and the altar, not the stones")
    T.eq(rows("used"), "1,I033 1,I005", "used events: penguin stone and ward, not an ordinary item")
    local ev = T.events("buy")[1]
    if ev then T.ok(ev[2]:match("^%d%d:%d%d$") ~= nil, "buy carries the game time") end
end)

-- Autopool: allowed after the pub trading timer; -pool opens the map's dialog, the ally button
-- activates it, and the map's 2 s timer moves the gold (our anchor hook counts it).
T.advance(220)
T.chat(1, "-pool")
T.click(1, "Bravo")
T.gold(1, 1000); T.gold(2, 0)
T.flush()
T.check("autopool through the map's own dialog + timer", function()
    T.eq(T.gold(2), 1000, "gold arrived at the ally")
    T.eq(T.stats(1).pool_out, 1000, "pool_out")
    T.eq(T.stats(2).pool_in, 1000, "pool_in")
end)
