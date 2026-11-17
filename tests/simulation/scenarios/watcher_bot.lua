-- The stream bot (MangoThief) also watches games other people host: it never changes the game. The host still gets
-- the game-type dialog and picks the mode; here the host chooses the first button.
local lobby = T.defaultLobby()
lobby[13] = { name = "MangoThief#115445", observer = true }
T.lobby(lobby, 13)
T.boot()
T.advance(2)

local want = T.map == "main" and 4 or 2           -- main: Pub / Pro / In-house / Pub custom; Solo: Normal / 4k
T.check("only a watching bot: the host still gets the dialog", function()
    T.eq(#T.buttons(1), want, "buttons shown to the host")
    T.ok(not udg_Host_Picked_A_Game_Mode, "no mode picked yet")
end)

T.click(1, T.buttons(1)[1])
T.advance(1)
T.check("the host's own pick decides the mode", function()
    T.ok(udg_mode_set_by_host, "set by the host's click")
    T.ok(udg_Host_Picked_A_Game_Mode and udg_mode_pub, "Pub mode")
end)
