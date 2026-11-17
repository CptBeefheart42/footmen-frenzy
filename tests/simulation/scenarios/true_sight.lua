-- True sight over the whole map (40-botvision.j) goes to the bots and a few named human accounts, and only while
-- they observe. Any other observer keeps the map's fog reveal alone, and a named account in a player slot gets
-- nothing: there the grid would be a cheat.
local lobby = T.defaultLobby()
lobby[1].name = "RJE#2927"
lobby[13] = { name = "RJE#11113", observer = true }
lobby[14] = { name = "Oscar#1313", observer = true }
lobby[15] = { name = "CptBeefheart#21297", observer = true }
lobby[16] = { name = "MangoThief#115445", observer = true }
T.lobby(lobby)
T.boot()
T.advance(5)

local function detectors(slot)
    local n = 0
    for _, u in ipairs(T.unitsOf(slot, "h055")) do
        if u.abilities[T.id("Adtg")] and u.abilities[T.id("A05H")] then n = n + 1 end
    end
    return n
end

T.check("the named observers get the same detector grid as a bot", function()
    T.ok(detectors(16) >= 70, "the bot's grid: " .. detectors(16))
    T.eq(detectors(13), detectors(16), "RJE#11113 in slot 13")
    T.eq(detectors(15), detectors(16), "CptBeefheart#21297 in slot 15")
end)
T.check("an observer off the list gets none", function()
    T.eq(detectors(14), 0, "Oscar#1313 in slot 14")
end)
T.check("a named account in a player slot gets none", function()
    T.eq(detectors(1), 0, "RJE#2927 in slot 1")
end)
T.check("a named observer shares its vision with nobody", function()
    for slot = 1, 24 do
        if slot ~= 13 then
            T.ok(not GetPlayerAlliance(T.player(13), T.player(slot), ALLIANCE_SHARED_VISION), "shares with slot " .. slot)
        end
    end
end)
