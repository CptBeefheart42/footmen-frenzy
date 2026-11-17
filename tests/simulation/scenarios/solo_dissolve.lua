-- Everybody leaves a Solo game at once: nobody won, so no winner / placement / gameend.
local lobby = T.defaultLobby()
lobby[12] = nil
T.lobby(lobby)
T.boot()
T.advance(100)
T.leave(5)
T.leave(8)
T.leave(1)
T.advance(40)
T.checkNoResult()
