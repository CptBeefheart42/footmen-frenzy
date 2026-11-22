// FF addons — startup. The build runner injects `call FF_Init()` into main() (after
// InitCustomTriggers), and FF_Init defers the system inits by 0.10s — same as the C# build's
// delayed startup callback — so the map's own init (udg_ globals, GUI triggers) is fully done
// before the addons hook events off it.

function FF_BootTick takes nothing returns nothing
    call DestroyTimer(GetExpiredTimer())
    set FF_gameTimer = CreateTimer()
    call TimerStart(FF_gameTimer, 1000000.0, false, null)
    set FF_gameToken = FF_ComputeGameToken()  // before the first flush names a file
    set FF_hostBotGame = FF_HostBotInGame()
    call FF_KillLog_Init()
    call FF_Ping_Init()
    call FF_Stats_Init()
    call FF_Usage_Init()
    call FF_GameResult_Init()
    call FF_Afk_Init()
    call FF_ObserverCamera_Init()
    call FF_BotVision_Init()
endfunction

function FF_Init takes nothing returns nothing
    call TimerStart(CreateTimer(), 0.10, false, function FF_BootTick)
endfunction
