-- Each map sources random picks and repicks from this roster.
T.lobby()
T.boot()
T.advance(20)
local retired = {"HMu1", "HDk1", "HVg1", "HTf1"}
T.check("retired heroes are absent from the playable roster", function()
    for _, code in ipairs(retired) do
        for index = 1, udg_total_hero_count do
            T.ok(udg_hero_type[index] ~= T.id(code), code .. " at roster index " .. index)
        end
        if T.map == "799x" then
            T.ok(MF_HeroDisabled(T.id(code)), code .. " excluded from taverns")
            for team = 1, 4 do T.ok(SD_TeamCarry(team) ~= T.id(code), code .. " offered in Single Draft") end
        else
            T.ok(SoloFootsIsNoMuteHeroType(T.id(code)), code .. " excluded from Solo taverns")
        end
    end
end)
T.check("Twisted Fate cannot be spawned with the former chat command", function()
    udg_mode_debugmode = true
    T.chat(1, "-tf")
    T.eq(#T.unitsOf(1, "HTf1"), 0, "no Twisted Fate")
end)
