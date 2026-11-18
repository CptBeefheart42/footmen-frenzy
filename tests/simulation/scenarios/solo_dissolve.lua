-- Everybody leaves a Solo game at once: nobody won, so no winner / placement / gameend.
local lobby = T.defaultLobby()
lobby[12] = nil
T.lobby(lobby)
T.boot()
-- after the mass (~50 s), before the AFK kick removes the hero-less seats once the pool opens (72 s)
T.advance(60)
T.leave(5)
T.leave(8)
T.leave(1)
T.advance(40)
T.checkNoResult()
