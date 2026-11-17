-- Two allies autopooling to each other: the map's own timer passes the same gold back and forth, so
-- pool_out / pool_in grow every 2 s while nobody gives anything. The counters stay honest per direction,
-- which is what lets a reader take the net (out - in) instead of the gross.
T.lobby({ [1] = { name = "Alpha#1111" }, [2] = { name = "Bravo#2222" }, [3] = { name = "Charlie#3333" },
          [4] = { name = "Delta#4444" } }, 1)
T.boot()
T.advance(20)
T.pickHeroes()
T.advance(222)                                     -- 799X opens the pool 230 s after its start (about 11 s in)

T.chat(1, "-pool"); T.click(1, "Bravo")
T.chat(2, "-pool"); T.click(2, "Alpha")
T.gold(1, 1000); T.gold(2, 0); T.gold(3, 0)
T.flush()

local function net(slot)
    local s = T.stats(slot)
    return s.pool_out - s.pool_in
end

T.check("mutual autopool: the gross grows, the net does not", function()
    T.eq(T.gold(1) + T.gold(2), 1000, "gold conserved between the two")
    T.ok(T.stats(1).pool_out >= 10000, "pool_out(1) counts every pass: " .. T.stats(1).pool_out)
    T.ok(T.stats(2).pool_out >= 10000, "pool_out(2) counts every pass: " .. T.stats(2).pool_out)
    T.eq(net(1), 1000 - T.gold(1), "net(1) = the gold slot 1 really gave away")
    T.eq(net(2), 0 - T.gold(2), "net(2) = the gold slot 2 really gave away")
end)

-- A third ally who really gives: Charlie's 500 joins the loop and stays with Alpha and Bravo.
T.chat(3, "-pool"); T.click(3, "Alpha")
local before = { [1] = net(1), [2] = net(2) }
T.gold(3, 500)
T.flush()

T.check("a real gift into the loop is the only net out", function()
    T.eq(T.stats(3).pool_out, 500, "pool_out(3)")
    T.eq(T.stats(3).pool_in, 0, "pool_in(3)")
    T.eq(net(3), 500, "net(3)")
    T.eq((net(1) - before[1]) + (net(2) - before[2]), -500, "Alpha and Bravo between them received 500")
    T.eq(T.gold(1) + T.gold(2), 1500, "gold conserved")
end)

T.check("pooling is zero-sum over the team", function()
    local out, inn = 0, 0
    for slot = 1, 3 do
        out = out + T.stats(slot).pool_out
        inn = inn + T.stats(slot).pool_in
    end
    T.eq(out, inn, "sum pool_out = sum pool_in")
end)
