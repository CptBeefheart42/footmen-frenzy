-- deny_tower: a slot's own feed units killed by an ally's building (walked into a teammate's tower to deny them)
-- count for the slot that brought them, while the tower's owner still gets its deny_ally. Slots 1 and 2 are allies;
-- slot 2 owns the cannon tower.
T.lobby()
T.boot()
T.advance(20)

local tower = T.unit(2, "hctw")
T.kill(T.unit(1, T.footman()), tower)                -- slot 1's footman, killed by slot 2's tower
T.kill(T.unit(1, T.footman()), tower)
T.kill(T.unit(1, T.footman()), T.unitsOf(2, T.footman())[1])   -- slot 1's footman, killed by a slot 2 footman
T.kill(T.unit(2, T.footman()), tower)                -- slot 2's own footman, killed by its own tower
T.flush()

T.check("the slot whose footmen died to the ally's tower gets deny_tower", function()
    T.eq(T.stats(1).deny_tower, 2, "slot 1 deny_tower (the footman killed by a footman doesn't count)")
end)
T.check("the tower's owner keeps its deny_ally", function()
    T.eq(T.stats(2).deny_ally, 3, "slot 2 deny_ally (two by the tower, one by its footman)")
    T.eq(T.stats(2).deny_own, 1, "slot 2 deny_own (its own footman)")
    T.eq(T.stats(2).deny_tower, 0, "slot 2 deny_tower: an own building is an own deny, not a tower deny")
end)
