-- A lobby hosted by one of our bots (the bot watches from observer slot 13): the map picks Pub mode itself at 1s,
-- the human host never gets the game-type dialog, and the 8s "host was AFK" default has nothing left to do.
local lobby = T.defaultLobby()
local bot = T.map == "799x" and "CoralShark#113567" or "OhNaahs#1537"
lobby[13] = { name = bot, observer = true }
T.lobby(lobby, 13)
T.boot()
T.advance(2)

T.check("no game-type dialog for the host in a bot-hosted game", function()
    T.eq(#T.buttons(1), 0, "buttons shown to the host")
end)
T.check("the map picked Pub mode by itself", function()
    T.ok(udg_Host_Picked_A_Game_Mode, "udg_Host_Picked_A_Game_Mode")
    T.ok(udg_mode_pub, "udg_mode_pub")
    T.ok(not udg_mode_set_by_host, "not set by a host click")
    T.eq(udg_selected_mode, 3, "udg_selected_mode (SD)")
end)

local starts = GetTriggerExecCount(gg_trg_Start_game)
T.advance(10)
T.flush()
T.check("the game starts once, and the AFK default does not start it again", function()
    T.ok(starts >= 1, "Start_game ran by 2s")
    T.eq(GetTriggerExecCount(gg_trg_Start_game), starts, "Start_game runs after the AFK timer")
end)
T.check("ff_result reports the Pub game", function()
    local m = T.rows(T.dataFile("ff_result"), "modes")[1]
    T.ok(m, "modes row")
    T.eq(m.kv.pub, 1, "pub")
    T.eq(m.kv.sel, 3, "sel")
end)
