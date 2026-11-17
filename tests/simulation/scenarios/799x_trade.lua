-- Gold between allies on the main map, each way in its own keys: -pool / autopool in pool_out / pool_in, the Allies
-- menu (the score screen's gold given / received) in given / recv, a fallen ally's gold in inh_out / inh_in. A round
-- trip shows up in both directions, so out - in is the gold a player really gave away.
T.lobby({ [1] = { name = "Alpha#1111" }, [2] = { name = "Bravo#2222" }, [3] = { name = "Charlie#3333" },
          [4] = { name = "Delta#4444" } }, 1)
T.boot()
T.advance(20)
T.pickHeroes()
T.advance(222)                                     -- 799X opens the pool 230 s after its start (about 11 s in)

local CANCEL = "TRIGSTR_1684"                      -- the pool dialog's cancel button (map strings stay unresolved)

-- A -> B, cancelled; then B -> A with less.
T.chat(1, "-pool"); T.click(1, "Bravo")
T.gold(1, 1000); T.gold(2, 0)
T.advance(3)
T.chat(1, "-pool"); T.click(1, CANCEL)
T.chat(2, "-pool"); T.click(2, "Alpha")
T.gold(2, 400)
T.advance(3)
T.chat(2, "-pool"); T.click(2, CANCEL)
T.advance(10)
T.flush()

T.check("-pool round trip: every pass counted once per direction", function()
    T.eq(T.gold(1), 400, "gold of slot 1")
    T.eq(T.gold(2), 0, "gold of slot 2")
    T.eq(T.stats(1).pool_out, 1000, "pool_out(1)"); T.eq(T.stats(2).pool_in, 1000, "pool_in(2)")
    T.eq(T.stats(2).pool_out, 400, "pool_out(2)"); T.eq(T.stats(1).pool_in, 400, "pool_in(1)")
end)
T.check("a cancelled pool moves nothing more", function()
    T.gold(1, 700)
    T.advance(10)
    T.eq(T.gold(1), 700, "gold stays with slot 1")
    T.eq(T.gold(2), 0, "nothing arrives at slot 2")
end)

-- The Allies menu: only the score screen's keys move.
T.tribute(1, 3, 300)
T.flush()
T.check("Allies-menu gold is given / recv, not pool_*", function()
    T.eq(T.stats(1).given, 300, "given(1)"); T.eq(T.stats(3).recv, 300, "recv(3)")
    T.eq(T.stats(1).pool_out, 1000, "pool_out(1) unchanged")
    T.eq(T.stats(3).pool_in, 0, "pool_in(3)")
end)

-- Script gold moves (SetPlayerState, a fallen ally's gold) never reach the score screen's keys.
T.gold(3, 900)
T.kill(T.unitsOf(3, "hbar")[1], T.unit(4, T.footman()))
T.advance(1)
T.flush()
T.check("a fallen ally's gold is inh_out / inh_in, never given / recv", function()
    T.eq(T.stats(3).inh_out, 900, "inh_out(3)")
    T.eq(T.stats(1).inh_in + T.stats(2).inh_in, 900, "inh_in(1) + inh_in(2)")
    T.eq(T.stats(2).given + T.stats(2).recv, 0, "given / recv of slot 2")
    T.eq(T.stats(3).given, 0, "given(3)")
end)

T.check("over every route, out - in is the gold a player really gave away", function()
    local function net(s)
        local st = T.stats(s)
        return (st.pool_out + st.given + st.inh_out) - (st.pool_in + st.recv + st.inh_in)
    end
    T.eq(net(1), 1000 - 400 + 300 - T.stats(1).inh_in, "net(1)")
    T.eq(net(1) + net(2) + net(3), 0, "zero-sum over the team")
end)
