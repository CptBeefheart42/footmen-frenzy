-- Both race trees assign the Ghoul its base attack cooldown when they spawn it.
T.lobby()
T.boot()
T.advance(20)

T.check("both Ghoul spawn entries attack five percent faster", function()
    for _, index in ipairs({17, 44}) do
        T.eq(udg_spawn_unit[index], FourCC("ugho"), "spawn type in slot " .. index)
        T.ok(math.abs(udg_unit_att_CD[index] - 1.1 / 1.05) < 0.000001,
            "Ghoul cooldown in slot " .. index)
    end
end)
