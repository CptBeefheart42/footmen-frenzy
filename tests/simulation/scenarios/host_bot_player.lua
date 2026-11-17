-- A hosting bot in a playing slot (not observing) makes the game bot-hosted too: Pub mode without the dialog.
local lobby = T.defaultLobby()
if T.map == "799x" then
    lobby[3] = { name = "(EFL)CoralShark#113567" }      -- a leading clan tag still matches
else
    lobby[12] = { name = "LustyPuppy#1929" }
end
T.lobby(lobby)
T.boot()
T.advance(2)

T.check("a hosting bot in a player slot: Pub mode, no dialog", function()
    T.eq(#T.buttons(1), 0, "buttons shown to the host")
    T.ok(udg_Host_Picked_A_Game_Mode and udg_mode_pub, "Pub mode picked")
    T.ok(not udg_mode_set_by_host, "not set by a host click")
end)
