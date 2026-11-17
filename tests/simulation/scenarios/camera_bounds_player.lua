-- A player's camera keeps the map's own limit (its "minimap correction" trigger); only observers
-- get the whole playable area.
T.lobby(T.defaultLobby(), 1)
T.boot()
T.advance(5)
T.check("the player's camera keeps the map's limit", function()
    local b = T.cameraBounds()
    T.eq(b.minx, -3000.0, "left")
    T.eq(b.maxx, 2850.0, "right")
    T.eq(b.miny, -3400.0, "bottom")
    T.eq(b.maxy, 2600.0, "top")
end)
