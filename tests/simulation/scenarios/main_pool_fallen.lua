-- Autopool from a fallen ally: the map's timer checks only the receiver, so a player who is out keeps
-- forwarding gold that reaches their slot. That gold is inherited, never pool: pool_out / pool_in count only
-- what a player still in the game chose to send. A leaver's autopool the map switches off itself.
T.lobby({ [1] = { name = "Alpha#1111" }, [2] = { name = "Bravo#2222" }, [3] = { name = "Charlie#3333" },
          [4] = { name = "Delta#4444" } }, 1)
T.boot()
T.advance(20)
T.pickHeroes()
T.advance(218)

T.chat(2, "-pool"); T.click(2, "Alpha")
T.chat(3, "-pool"); T.click(3, "Alpha")
T.gold(1, 0); T.gold(2, 0); T.gold(3, 0)
T.advance(3)
T.flush()
local start = { [1] = T.stats(1), [2] = T.stats(2), [3] = T.stats(3) }

local enemy = T.unitsOf(4, "hfoo")[1]
T.kill(T.unitsOf(3, "hbar")[1], enemy)
T.advance(3)
T.gold(3, 600)
T.advance(3)
T.flush()

T.check("a player who is out forwards inherited gold, not pool gold", function()
    T.eq(T.stats(3).state, "out", "state(3)")
    T.eq(T.stats(3).pool_out, start[3].pool_out, "pool_out(3) unchanged")
    T.eq(T.stats(1).pool_in, start[1].pool_in, "pool_in(1) unchanged")
    T.ok(T.stats(3).inh_out - start[3].inh_out >= 600, "inh_out(3) carries the 600: " .. T.stats(3).inh_out)
    T.ok(T.stats(1).inh_in - start[1].inh_in >= 600, "inh_in(1) carries the 600: " .. T.stats(1).inh_in)
end)

local before = { [1] = T.stats(1), [2] = T.stats(2) }
T.leave(2)
T.advance(3)
T.gold(2, 700)
T.advance(3)
T.flush()

T.check("a player who has left forwards nothing: the map stops their autopool", function()
    T.eq(T.stats(2).state, "left", "state(2)")
    T.eq(T.stats(2).pool_out, before[2].pool_out, "pool_out(2) unchanged")
    T.eq(T.stats(2).inh_out, before[2].inh_out, "inh_out(2) unchanged")
    T.eq(T.stats(1).pool_in, before[1].pool_in, "pool_in(1) unchanged")
    T.eq(T.gold(2), 700, "the gold stays on the leaver's slot")
end)

T.check("gold between allies stays zero-sum over every route", function()
    local out, inn = 0, 0
    for slot = 1, 3 do
        local s = T.stats(slot)
        out = out + s.pool_out + s.inh_out
        inn = inn + s.pool_in + s.inh_in
    end
    T.eq(out, inn, "sum out = sum in")
end)
