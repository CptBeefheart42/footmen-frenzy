-- Non-bot clients never write ff_ping (same local-client gate as ff_killlog).
local lobby = T.defaultLobby()
T.lobby(lobby, 1)
T.boot()
T.advance(60)

T.check("non-bot client writes no ff_ping file", function()
    T.eq(T.dataFile("ff_ping"), nil, "ff_ping file")
end)
