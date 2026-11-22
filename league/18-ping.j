// FF addons — Ping probe: anonymous in-game sync latency -> CustomMapData/ff_ping_<token>.txt
// (FF_DataFile: the token tells concurrent games on one bot box apart).
// Every 30s (first probe at 15s so short/dissolved games still produce samples), each active
// human client calls BlzSendSyncData("ffp", I2S(round)). The sync trigger measures elapsed game
// time from when the round started, deduplicates per player per round, insertion-sorts non-bot
// player delays (ms), and writes one anonymous aggregate row per round:
//
//   format,1
//   round,<mm:ss>,<n>,<p50>,<p90>,<max>,<gt200>,<gt350>,<bot_ms>
//   summary,<mm:ss>,<rounds>,<samples>,<gt200>,<gt350>,<max>,<bot_samples>,<bot_max>
//   pingend,<mm:ss>
//
// Privacy invariant: no BattleTags, player names or slot indices are ever written.
// Bot-only output: gated on FF_LocalClientIsBot() (local-only Preload write, zero desync risk).
// Frozen at gameend by FF_pg_Final().

globals
    trigger FF_pg_trig = null
    boolean FF_pg_done = false
    integer FF_pg_round = 0
    real FF_pg_sentAt = 0.0
    integer array FF_pg_seenRound
    integer array FF_pg_curVals
    integer FF_pg_curN = 0
    integer FF_pg_curBotMs = -1

    integer FF_pg_MAX_ROWS = 240
    string array FF_pg_rows
    integer FF_pg_rowN = 0
    string FF_pg_endRow = null

    integer FF_pg_totRounds = 0
    integer FF_pg_totSamples = 0
    integer FF_pg_totGt200 = 0
    integer FF_pg_totGt350 = 0
    integer FF_pg_totMax = 0
    integer FF_pg_totBotSamples = 0
    integer FF_pg_totBotMax = 0
endglobals

function FF_pg_Flush takes nothing returns nothing
    local integer i = 0
    if not FF_LocalClientIsBot() then
        return
    endif
    call PreloadGenClear()
    call PreloadGenStart()
    call Preload("format,1")
    loop
        exitwhen i >= FF_pg_rowN
        call Preload(FF_pg_rows[i])
        set i = i + 1
    endloop
    call Preload("summary," + FF_Elapsed() + "," + I2S(FF_pg_totRounds) + "," + I2S(FF_pg_totSamples) + "," + I2S(FF_pg_totGt200) + "," + I2S(FF_pg_totGt350) + "," + I2S(FF_pg_totMax) + "," + I2S(FF_pg_totBotSamples) + "," + I2S(FF_pg_totBotMax))
    if FF_pg_endRow != null then
        call Preload(FF_pg_endRow)
    endif
    call PreloadGenEnd(FF_DataFile("ff_ping"))
endfunction

function FF_pg_SortCur takes nothing returns nothing
    local integer i = 1
    local integer j
    local integer key
    loop
        exitwhen i >= FF_pg_curN
        set key = FF_pg_curVals[i]
        set j = i - 1
        loop
            exitwhen j < 0
            exitwhen FF_pg_curVals[j] <= key
            set FF_pg_curVals[j + 1] = FF_pg_curVals[j]
            set j = j - 1
        endloop
        set FF_pg_curVals[j + 1] = key
        set i = i + 1
    endloop
endfunction

function FF_pg_CloseRound takes nothing returns nothing
    local integer n = FF_pg_curN
    local integer p50 = 0
    local integer p90 = 0
    local integer rmax = 0
    local integer gt200 = 0
    local integer gt350 = 0
    local integer i = 0
    local integer v
    if FF_pg_round <= 0 then
        return
    endif
    if n == 0 and FF_pg_curBotMs < 0 then
        return
    endif
    if n > 0 then
        call FF_pg_SortCur()
        set p50 = FF_pg_curVals[(n - 1) / 2]
        set p90 = FF_pg_curVals[((n - 1) * 9) / 10]
        set rmax = FF_pg_curVals[n - 1]
        loop
            exitwhen i >= n
            set v = FF_pg_curVals[i]
            if v > 200 then
                set gt200 = gt200 + 1
            endif
            if v > 350 then
                set gt350 = gt350 + 1
            endif
            set i = i + 1
        endloop
    endif
    set FF_pg_totRounds = FF_pg_totRounds + 1
    set FF_pg_totSamples = FF_pg_totSamples + n
    set FF_pg_totGt200 = FF_pg_totGt200 + gt200
    set FF_pg_totGt350 = FF_pg_totGt350 + gt350
    if rmax > FF_pg_totMax then
        set FF_pg_totMax = rmax
    endif
    if FF_pg_curBotMs >= 0 then
        set FF_pg_totBotSamples = FF_pg_totBotSamples + 1
        if FF_pg_curBotMs > FF_pg_totBotMax then
            set FF_pg_totBotMax = FF_pg_curBotMs
        endif
    endif
    if FF_pg_rowN < FF_pg_MAX_ROWS then
        set FF_pg_rows[FF_pg_rowN] = "round," + FF_Elapsed() + "," + I2S(n) + "," + I2S(p50) + "," + I2S(p90) + "," + I2S(rmax) + "," + I2S(gt200) + "," + I2S(gt350) + "," + I2S(FF_pg_curBotMs)
        set FF_pg_rowN = FF_pg_rowN + 1
    endif
    set FF_pg_curN = 0
    set FF_pg_curBotMs = -1
    call FF_pg_Flush()
endfunction

function FF_pg_StartRound takes nothing returns nothing
    local player lp
    set FF_pg_round = FF_pg_round + 1
    set FF_pg_sentAt = TimerGetElapsed(FF_gameTimer)
    set FF_pg_curN = 0
    set FF_pg_curBotMs = -1
    set lp = GetLocalPlayer()
    if GetPlayerSlotState(lp) == PLAYER_SLOT_STATE_PLAYING and GetPlayerController(lp) == MAP_CONTROL_USER then
        call BlzSendSyncData("ffp", I2S(FF_pg_round))
    endif
    set lp = null
endfunction

function FF_pg_OnSync takes nothing returns nothing
    local player p
    local integer pid
    local integer ms
    if FF_pg_done or FF_pg_round <= 0 then
        return
    endif
    if BlzGetTriggerSyncPrefix() != "ffp" then
        return
    endif
    if S2I(BlzGetTriggerSyncData()) != FF_pg_round then
        return
    endif
    set p = GetTriggerPlayer()
    set pid = GetPlayerId(p)
    if pid < 0 or pid >= bj_MAX_PLAYER_SLOTS then
        set p = null
        return
    endif
    if FF_pg_seenRound[pid] == FF_pg_round then
        set p = null
        return
    endif
    set FF_pg_seenRound[pid] = FF_pg_round
    set ms = R2I((TimerGetElapsed(FF_gameTimer) - FF_pg_sentAt) * 1000.0 + 0.5)
    if ms < 0 then
        set ms = 0
    endif
    if FF_IsBotName(GetPlayerName(p)) then
        if FF_pg_curBotMs < 0 or ms > FF_pg_curBotMs then
            set FF_pg_curBotMs = ms
        endif
    elseif not IsPlayerObserver(p) and FF_pg_curN < 24 then
        set FF_pg_curVals[FF_pg_curN] = ms
        set FF_pg_curN = FF_pg_curN + 1
    endif
    set p = null
endfunction

function FF_pg_OnTick takes nothing returns nothing
    if FF_pg_done then
        return
    endif
    call FF_pg_CloseRound()
    call FF_pg_StartRound()
endfunction

function FF_pg_FirstTick takes nothing returns nothing
    call DestroyTimer(GetExpiredTimer())
    if FF_pg_done then
        return
    endif
    call FF_pg_StartRound()
    call TimerStart(CreateTimer(), 30.0, true, function FF_pg_OnTick)
endfunction

// Final flush at gameend: closes the in-flight round, writes pingend and freezes the file.
function FF_pg_Final takes nothing returns nothing
    if FF_pg_done then
        return
    endif
    set FF_pg_done = true
    call FF_pg_CloseRound()
    set FF_pg_endRow = "pingend," + FF_Elapsed()
    call FF_pg_Flush()
endfunction

function FF_Ping_Init takes nothing returns nothing
    local integer i = 0
    set FF_pg_trig = CreateTrigger()
    loop
        exitwhen i >= bj_MAX_PLAYER_SLOTS
        call BlzTriggerRegisterPlayerSyncEvent(FF_pg_trig, Player(i), "ffp", false)
        set FF_pg_seenRound[i] = 0
        set i = i + 1
    endloop
    call TriggerAddAction(FF_pg_trig, function FF_pg_OnSync)
    call TimerStart(CreateTimer(), 15.0, false, function FF_pg_FirstTick)
endfunction
