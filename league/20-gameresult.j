// FF addons — GameResult: authoritative end-of-game result -> CustomMapData/ff_result.txt
// (ff_result_<token>.txt on a bot client — FF_DataFile tells concurrent games on one box apart).
// Port of scripting/Source/GameResult.cs (see its doc comment). It polls the very globals the
// map's own END trigger reads (udg_player_active[1..12] + udg_mode_6v6) and records, with match
// time: each player's elimination ("out"), each side's death ("sidedead"), and — only on a clean
// victory (>=2 sides played, exactly 1 left) — "winner" + the full "placement" table + "gameend" (the file's last
// record). The first record is "format,<n>".
// A game that just dissolves never gets a winner line, so the bot can tell result from abort.
// Sides: FFA = four teams (slots 1-3, 4-6, 7-9, 10-12); 6v6 = West (1-3 + 10-12) vs East (4-9),
// mirroring Trig_END_Actions. Preload writes run on every client (no bot gate, unlike the kill
// log — the result is the load-bearing signal, so it must not hinge on the tag list being
// current); only the file NAME differs on a bot client, and that is a local decision.
// A roster longer than a Preload string continues in "roster_more" rows.
// A player removed for having no hero after the mass (25-afk.j) is no participant: an "afk" record instead of a
// roster entry, stats, usage rows or a place in a side's members, so the game doesn't count for them.
// After the event rows: the usage events (pick / baseup / buy / used), two `stats,<slot>,t=..` rows per participant
// (15-stats.j), the `modes` and `koth` rows and each participant's `use` / `skills` rows (16-usage.j) — the
// latest cumulative numbers, refreshed every 30s when they changed, at each "out" and at "gameend".

globals
    // Slots 1..12 (index 0 unused): ever-active participants, and who we already reported out.
    boolean array FF_gr_participant
    boolean array FF_gr_eliminated
    // Slots removed by the AFK kick (FF_gr_DropAfk): never a participant again.
    boolean array FF_gr_afk
    // Side index 1..4 (FFA) / 1..2 (6v6); the mode is fixed well before the first death.
    boolean array FF_gr_sideDead
    // Sides in elimination order (first to die = last place).
    integer array FF_gr_deathOrder
    integer FF_gr_deathN = 0
    integer FF_GR_EVENT_MAX = 200
    string array FF_gr_events
    integer FF_gr_eventN = 0
    boolean FF_gr_ended = false
    // "gameend,<t>" once the game has a result: written as the file's LAST record (after every telemetry row), so a
    // file cut off mid-write never looks finished
    string FF_gr_gameendRow = null
    timer FF_gr_pollTimer = null
endglobals

function FF_gr_SideParticipated takes integer side returns boolean
    local integer p = 1
    loop
        exitwhen p > 12
        if FF_IsMember(p, side) and FF_gr_participant[p] then
            return true
        endif
        set p = p + 1
    endloop
    return false
endfunction

// "alive" mirrors END: purely player_active, so a winner is never declared before the map's own
// victory logic would declare it.
function FF_gr_SideAlive takes integer side returns boolean
    local integer p = 1
    loop
        exitwhen p > 12
        if FF_IsMember(p, side) and udg_player_active[p] then
            return true
        endif
        set p = p + 1
    endloop
    return false
endfunction

// A substituted slot keeps the name of the player who left it (22-sub.j); the map renames the slot to the substitute.
function FF_gr_Name takes integer slot returns string
    if FF_sub_active[slot] then
        return FF_Sanitize(FF_sub_origName[slot])
    endif
    return FF_Sanitize(udg_orig_player_name[slot])
endfunction

// "slot:name;slot:name" for a side's participants; side < 0 means everyone (the full roster).
function FF_gr_RosterOf takes integer side returns string
    local string out = ""
    local integer p = 1
    loop
        exitwhen p > 12
        if FF_gr_participant[p] and (side < 0 or FF_IsMember(p, side)) then
            if StringLength(out) > 0 then
                set out = out + ";"
            endif
            set out = out + I2S(p) + ":" + FF_gr_Name(p)
        endif
        set p = p + 1
    endloop
    return out
endfunction

function FF_gr_AddEvent takes string line returns nothing
    if FF_gr_eventN < FF_GR_EVENT_MAX then
        set FF_gr_events[FF_gr_eventN] = line
        set FF_gr_eventN = FF_gr_eventN + 1
    endif
endfunction

// Rebuilds the stats / usage rows that changed (only those: every JASS string lives until the game ends);
// true if any did.
function FF_gr_RefreshStats takes nothing returns boolean
    local boolean changed = FF_us_RefreshShared()
    local integer p = 1
    loop
        exitwhen p > 12
        if FF_gr_participant[p] then
            if FF_st_Refresh(p) then
                set changed = true
            endif
            if FF_us_Refresh(p) then
                set changed = true
            endif
        endif
        set p = p + 1
    endloop
    return changed
endfunction

// The roster: "roster,slot:name;..." with the entries that fit, the rest in "roster_more," rows: 12 battletags
// (up to ~23 chars per entry) don't fit in one Preload string. A parser that reads only the roster row still
// gets the full head of the list.
function FF_gr_PreloadRoster takes nothing returns nothing
    local string head = "roster,"
    local string cur = head
    local string e
    local integer p = 1
    loop
        exitwhen p > 12
        if FF_gr_participant[p] then
            set e = I2S(p) + ":" + FF_gr_Name(p)
            if cur != head and StringLength(cur) + 1 + StringLength(e) > FF_PRELOAD_MAX then
                call Preload(cur)
                set head = "roster_more,"
                set cur = head
            endif
            if cur == head then
                set cur = cur + e
            else
                set cur = cur + ";" + e
            endif
        endif
        set p = p + 1
    endloop
    call Preload(cur)
endfunction

// Preload has no append mode, so the whole buffer is rewritten on every change.
function FF_gr_Flush takes nothing returns nothing
    local integer i = 0
    local string now = FF_Elapsed()
    call PreloadGenClear()
    call PreloadGenStart()
    // The file's format: bumped when a key's meaning changes (that key also gets a new name); otherwise records and
    // keys are only ever added (docs/result-contract.md). A file without this row is format 1.
    call Preload("format,2")
    if udg_mode_6v6 then
        call Preload("mode,6v6")
    else
        call Preload("mode,ffa")
    endif
    call FF_gr_PreloadRoster()
    loop
        exitwhen i >= FF_gr_eventN
        call Preload(FF_gr_events[i])
        set i = i + 1
    endloop
    call FF_us_PreloadEvents()
    set i = 1
    loop
        exitwhen i > 12
        if FF_gr_participant[i] and FF_st_row[i] != null then
            call Preload("stats," + I2S(i) + ",t=" + now + FF_st_row[i])
            call Preload("stats," + I2S(i) + ",t=" + now + FF_st_row2[i])
        endif
        set i = i + 1
    endloop
    call FF_us_PreloadShared()
    set i = 1
    loop
        exitwhen i > 12
        if FF_gr_participant[i] then
            call FF_us_PreloadSlot(i)
        endif
        set i = i + 1
    endloop
    if FF_gr_gameendRow != null then
        call Preload(FF_gr_gameendRow)
    endif
    call PreloadGenEnd(FF_DataFile("ff_result"))
endfunction

function FF_gr_Poll takes nothing returns nothing
    local string now
    local boolean changed = false
    local integer p = 1
    local integer s = 1
    local integer sideCount
    local integer participated = 0
    local integer alive = 0
    local integer lastAlive = 0
    local integer place
    local integer i
    if FF_gr_ended then
        return
    endif
    set now = FF_Elapsed()
    // 1. participant tracking + individual eliminations. A player is "out" the moment the map
    //    flips their player_active off (their base died) — the same signal END reads.
    loop
        exitwhen p > 12
        if udg_player_active[p] and not FF_gr_afk[p] then
            // a new participant rewrites the file at once, so its roster names everyone from the start
            // (a game that dissolves early still says who played)
            if not FF_gr_participant[p] then
                set FF_gr_participant[p] = true
                set changed = true
            endif
        elseif FF_gr_participant[p] and not FF_gr_eliminated[p] then
            set FF_gr_eliminated[p] = true
            call FF_gr_AddEvent("out," + now + "," + I2S(p) + "," + FF_SideLabel(FF_SideOf(p)) + "," + FF_gr_Name(p))
            set changed = true
        endif
        // The stats row's state: alive -> out, or -> left (a leaver still gets the "out" row above).
        if FF_gr_participant[p] and FF_st_Track(p, udg_player_active[p]) then
            set changed = true
        endif
        set p = p + 1
    endloop
    // 2. side bookkeeping.
    set sideCount = FF_SideCount()
    loop
        exitwhen s > sideCount
        if FF_gr_SideParticipated(s) then
            set participated = participated + 1
        endif
        if FF_gr_SideAlive(s) then
            set alive = alive + 1
            set lastAlive = s
        elseif FF_gr_SideParticipated(s) and not FF_gr_sideDead[s] then
            set FF_gr_sideDead[s] = true
            set FF_gr_deathOrder[FF_gr_deathN] = s
            set FF_gr_deathN = FF_gr_deathN + 1
            call FF_gr_AddEvent("sidedead," + now + "," + FF_SideLabel(s))
            set changed = true
        endif
        set s = s + 1
    endloop
    // 3. clean victory: >=2 sides played, exactly one standing. Placement table: 1st = survivor,
    //    then the dead sides in reverse death order (last to die finished 2nd).
    if participated >= 2 and alive == 1 then
        set FF_gr_ended = true
        call PauseTimer(FF_gr_pollTimer)
        call FF_gr_AddEvent("winner," + now + "," + FF_SideLabel(lastAlive) + "," + FF_gr_RosterOf(lastAlive))
        call FF_gr_AddEvent("placement,1," + FF_SideLabel(lastAlive) + "," + FF_gr_RosterOf(lastAlive))
        set place = 2
        set i = FF_gr_deathN - 1
        loop
            exitwhen i < 0
            call FF_gr_AddEvent("placement," + I2S(place) + "," + FF_SideLabel(FF_gr_deathOrder[i]) + "," + FF_gr_RosterOf(FF_gr_deathOrder[i]))
            set place = place + 1
            set i = i - 1
        endloop
        set FF_gr_gameendRow = "gameend," + now
        set changed = true
    endif
    if changed then
        call FF_gr_RefreshStats()
        call FF_gr_Flush()
    endif
    // The kill log and ping probe's last writes in the same tick as the final stats rows.
    if FF_gr_ended then
        call FF_kl_Final()
        call FF_pg_Final()
    endif
endfunction

// The AFK kick removes a slot from the game: from here on it is no participant, and the file says so at once.
function FF_gr_DropAfk takes integer slot returns nothing
    if FF_gr_ended or FF_gr_afk[slot] then
        return
    endif
    set FF_gr_afk[slot] = true
    set FF_gr_participant[slot] = false
    call FF_gr_AddEvent("afk," + FF_Elapsed() + "," + I2S(slot) + "," + FF_gr_Name(slot))
    call FF_gr_Flush()
endfunction

// Every 30s: rewrites the file when a stats or usage row changed.
function FF_gr_OnStatsTick takes nothing returns nothing
    if not FF_gr_ended and FF_gr_RefreshStats() then
        call FF_gr_Flush()
    endif
endfunction

function FF_GameResult_Init takes nothing returns nothing
    set FF_gr_pollTimer = CreateTimer()
    call TimerStart(FF_gr_pollTimer, 1.00, true, function FF_gr_Poll)
    call TimerStart(CreateTimer(), 30.00, true, function FF_gr_OnStatsTick)
    // Ensure the file exists from match start, even for an instantly-aborted game.
    call FF_gr_Flush()
endfunction
