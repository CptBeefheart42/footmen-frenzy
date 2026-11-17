-- One hero per player, on both maps: the map gives every player a food cap of 5 and a hero costs 5, so the game
-- sells nobody a second hero (the engine model refuses it the way the client does), not even while the first one
-- lies dead waiting to be revived. On the main map a second hero that reaches the tavern area anyway is not made the
-- player's hero (TP_hero checks the tavern's picked flag, udg_tp_kill); Solo's TP_hero has no such check, so there the
-- food cap is the only guard. Main map control: in admin debug mode a second hero IS sold, so the refusals above come
-- from the limit.
local lobby = T.defaultLobby()
if T.map == "main" then lobby[1] = { name = "CptBeefheart#21297" } end   -- an admin, for the debug-mode control
T.lobby(lobby)
T.boot()
T.advance(20)

local active = T.map == "main" and { 1, 2, 4 } or { 1, 5, 8, 12 }
-- the shared tavern (main) or the player's own (Solo, gone once the player has picked: kept from before)
local tavern = T.map == "main" and T.shop("n02I") or T.unitsOf(1, "n02I")[1]
local function heroCount()
    local n = 0
    for _, u in ipairs(T.unitsOf(1)) do if IsUnitType(u, UNIT_TYPE_HERO) then n = n + 1 end end
    return n
end

T.check("every player starts with room for exactly one hero", function()
    for _, s in ipairs(active) do
        T.eq(GetPlayerState(T.player(s), PLAYER_STATE_RESOURCE_FOOD_CAP), 5, "food cap of slot " .. s)
    end
end)

local first = T.buyUnit(T.unitsOf(1)[1], tavern, "H005")
T.advance(2)
T.check("the first hero is sold and becomes the player's hero", function()
    T.ok(first ~= nil, "first hero sold")
    T.ok(udg_herO[1] == first, "udg_herO[1] is the bought hero")
    T.ok(udg_tp_kill[1], "the tavern's picked flag")
end)

local second = T.buyUnit(first, tavern, "H00T")
local same = T.buyUnit(first, tavern, "H005")
T.advance(2)
T.check("a second hero is never sold (another hero or the same one)", function()
    T.ok(second == nil and same == nil, "second purchase refused")
    T.eq(heroCount(), 1, "heroes of slot 1")
end)

T.kill(first, T.unit(4, "hfoo"))
T.advance(1)
T.check("not even while the first hero is dead (it can be revived)", function()
    T.ok(T.buyUnit(T.unitsOf(1)[1], tavern, "H00T") == nil, "purchase with a dead hero refused")
end)

if T.map == "main" then
    -- a hero that reaches the tavern area by other means (a trigger, a bug) is not taken as the player's hero
    local stray = T.unit(1, "H00T", tavern.x, tavern.y)
    T.flush()
    T.check("the map keeps the first hero as the player's hero", function()
        T.ok(udg_herO[1] == first, "udg_herO[1] unchanged")
        T.eq(#T.events("pick"), 1, "pick events (one, the first hero)")
    end)
    RemoveUnit(stray)

    T.chat(1, "-debug")
    T.advance(1)
    T.check("control: in admin debug mode the same purchase is sold", function()
        T.ok(T.buyUnit(T.unitsOf(1)[1], tavern, "H00T") ~= nil, "second hero sold with debug mode on")
    end)
end
