-- Our -debug is refused in a game hosted by one of the EFL bots (the games the ladder scores).
local lobby = T.defaultLobby()
lobby[13] = { name = "CoralShark#113567", observer = true }
T.lobby(lobby, 13)
T.boot()
T.advance(40)
T.chat(1, "-debug")
T.advance(1)
T.flush()

T.check("-debug is refused in a bot-hosted game", function()
    T.ok(not FF_DBG_on, "FF_DBG_on stays off")
    T.eq(T.saw(1, "not in games hosted by the EFL bots"), 1, "the player is told why")
    local m = require("modes").modes()
    T.eq(m and m.ffdebug, 0, "ffdebug")
end)
