// FF addons — KillLog: per-player kill/death tallies -> CustomMapData/ff_killlog_<token>.txt
// (FF_DataFile: the token tells concurrent games on one bot box apart).
// Port of scripting/Source/KillLog.cs (see its doc comment for the full design rationale).
// Key points preserved:
//   * one Preload flush per 30s AND only when dirty (per-death writes lagged);
//   * hero kills additionally append a "herokill,time,killerOwner,killerUnit,victimOwner,victim"
//     feed row (rare, so bounded small);
//   * ONLY the efl-bot fleet's clients write the file (FF_LocalClientIsBot: a GetLocalPlayer read
//     gating a local-only Preload write — touches no synced state, so it cannot desync; same as
//     the C# original).
// The owner rows are the map's OWN counters (udg_unit_kills / udg_hero_kills / udg_unit_deaths /
// udg_hero_deaths, slots 1..12, kept by Trig_Multiboard_Update), so the file always equals what
// the in-game -kd command shows. Own tallies drifted from it (ally/self kills, illusions, dead
// killers and creep kills counted). FF_kl_MapCounts mirrors that trigger's filter for the feed.
// Once the game has a result (20-gameresult.j's gameend) the file is written one last time and
// then frozen, so it keeps the same numbers as the final stats rows of ff_result even though
// units go on dying until the players leave.

globals
    boolean FF_kl_dirty = false
    // Set by FF_kl_Final at gameend: no more writes, no more feed rows.
    boolean FF_kl_done = false
    // The "who killed whom" feed; capped so the file stays constant-ish sized in marathon games.
    string array FF_kl_feed
    integer FF_kl_feedN = 0
endglobals

function FF_kl_Flush takes nothing returns nothing
    local integer i = 1
    if not FF_LocalClientIsBot() then
        return
    endif
    call PreloadGenClear()
    call PreloadGenStart()
    call Preload("owner,unit,hero,unit_died,hero_died")
    loop
        exitwhen i > 12
        if udg_unit_kills[i] != 0 or udg_hero_kills[i] != 0 or udg_unit_deaths[i] != 0 or udg_hero_deaths[i] != 0 then
            call Preload(FF_Sanitize(GetPlayerName(Player(i - 1))) + "," + I2S(udg_unit_kills[i]) + "," + I2S(udg_hero_kills[i]) + "," + I2S(udg_unit_deaths[i]) + "," + I2S(udg_hero_deaths[i]))
        endif
        set i = i + 1
    endloop
    set i = 0
    loop
        exitwhen i >= FF_kl_feedN
        call Preload(FF_kl_feed[i])
        set i = i + 1
    endloop
    call PreloadGenEnd(FF_DataFile("ff_killlog"))
endfunction

function FF_kl_OnFlushTick takes nothing returns nothing
    if FF_kl_done or not FF_kl_dirty then
        return
    endif
    set FF_kl_dirty = false
    call FF_kl_Flush()
endfunction

// The last write, at the moment the game has a result; the file stays as it is from here on.
function FF_kl_Final takes nothing returns nothing
    if FF_kl_done then
        return
    endif
    set FF_kl_done = true
    set FF_kl_dirty = false
    call FF_kl_Flush()
endfunction

// Trig_Multiboard_Update's filter (as hooked in the anchors files): enemy killer, alive or not, no
// illusion, killer owned by slot 1..12. Only such a death moves the map's counters.
function FF_kl_MapCounts takes unit victim, unit killer returns boolean
    local integer k
    if killer == null or not IsUnitEnemy(killer, GetOwningPlayer(victim)) or IsUnitIllusion(victim) then
        return false
    endif
    if GetUnitTypeId(killer) == 0 then
        return false
    endif
    set k = GetPlayerId(GetOwningPlayer(killer))
    return k >= 0 and k < 12
endfunction

function FF_kl_OnDeath takes nothing returns nothing
    local unit victim = GetTriggerUnit()
    local unit killer = GetKillingUnit()
    // The counters themselves are the map's; any death may have moved them, and the next tick
    // reads them (the map's trigger has long run by then, whatever the trigger order).
    set FF_kl_dirty = true
    // Hero kills are rare enough to record individually — only those the map counts, so the feed
    // agrees with the hero column. The killer may itself be a footman, not a hero, so its actual
    // name is logged.
    if not FF_kl_done and IsUnitType(victim, UNIT_TYPE_HERO) and FF_kl_feedN < 400 and FF_kl_MapCounts(victim, killer) then
        set FF_kl_feed[FF_kl_feedN] = "herokill," + FF_Elapsed() + "," + FF_Sanitize(GetPlayerName(GetOwningPlayer(killer))) + "," + FF_Sanitize(GetUnitName(killer)) + "," + FF_Sanitize(GetPlayerName(GetOwningPlayer(victim))) + "," + FF_Sanitize(GetUnitName(victim))
        set FF_kl_feedN = FF_kl_feedN + 1
    endif
    set victim = null
    set killer = null
endfunction

function FF_KillLog_Init takes nothing returns nothing
    local trigger t = CreateTrigger()
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_DEATH)
    call TriggerAddAction(t, function FF_kl_OnDeath)
    call TimerStart(CreateTimer(), 30.0, true, function FF_kl_OnFlushTick)
    // Write the header immediately so the file exists from match start.
    call FF_kl_Flush()
    set t = null
endfunction
