-- An observer can scroll to every corner shop (to see what was bought there). Camera bounds are
-- per client, so the game is played from the observer's slot.
local SHOPS = { { -3264, 3008 }, { 3264, 3008 }, { -3264, -3520 }, { 3264, -3520 } }

local lobby = T.defaultLobby()
lobby[13] = { name = "Oscar#1313", observer = true }
T.lobby(lobby, 13)
T.boot()
T.advance(5)
T.check("the observer's camera reaches every corner shop", function()
    local b = T.cameraBounds()
    T.eq(GetPlayerTeam(T.player(13)), 4, "observer team")
    for _, s in ipairs(SHOPS) do
        -- the camera target gets within one cell (128) of the shop
        T.ok(s[1] >= b.minx - 128 and s[1] <= b.maxx + 128 and s[2] >= b.miny - 128 and s[2] <= b.maxy + 128,
            "shop at " .. s[1] .. "," .. s[2])
    end
end)
