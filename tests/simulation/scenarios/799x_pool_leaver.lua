-- Autopool into an ally who has left: the map keeps sending, and an ally can collect the gold back from the
-- leaver's base. Gold moving to a leaver is inherited, never pool, so the round trip earns no pool_out.
T.lobby({ [1] = { name = "Alpha#1111" }, [2] = { name = "Bravo#2222" }, [3] = { name = "Charlie#3333" },
          [4] = { name = "Delta#4444" } }, 1)
T.boot()
T.advance(20)
T.pickHeroes()
T.advance(218)

T.chat(1, "-pool"); T.click(1, "Bravo")
T.gold(1, 0); T.gold(2, 0)
T.advance(3)
T.flush()
local before = { [1] = T.stats(1), [2] = T.stats(2) }

T.leave(2)
T.advance(1)
T.gold(1, 800)
T.advance(3)
T.flush()

T.check("gold autopooled to a leaver is inherited, not pool", function()
    T.eq(T.stats(2).state, "left", "state(2)")
    T.eq(T.gold(2), 800, "the map still moves the gold")
    T.eq(T.stats(1).pool_out, before[1].pool_out, "pool_out(1) unchanged")
    T.eq(T.stats(2).pool_in, before[2].pool_in, "pool_in(2) unchanged")
    T.eq(T.stats(1).inh_out - before[1].inh_out, 800, "inh_out(1)")
    T.eq(T.stats(2).inh_in - before[2].inh_in, 800, "inh_in(2)")
end)
