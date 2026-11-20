-- The same player attempts the old debug shortcut, then deliberately selects the hero in AP.
T.lobby()
T.boot()
T.advance(20)
local slot = 1
T.check("debug or single draft cannot grant Twisted Fate", function()
    udg_selected_mode = 3
    udg_mode_debugmode = true
    T.chat(slot, "-tf")
    T.eq(#T.unitsOf(slot, "HTf1"), 0, "no debug hero")
end)
T.check("the AP command grants exactly one starting hero", function()
    udg_mode_debugmode = false
    udg_selected_mode = 2
    DraftPending[slot] = true
    T.chat(slot, "-tf")
    T.advance(1)
    T.eq(#T.unitsOf(slot, "HTf1"), 1, "All Pick selection")
    T.eq(GetUnitTypeId(udg_herO[slot]), T.id("HTf1"), "registered as starting hero")
    T.chat(slot, "-tf")
    T.eq(#T.unitsOf(slot, "HTf1"), 1, "no duplicate selection")
end)
