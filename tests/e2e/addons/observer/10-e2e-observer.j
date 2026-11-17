// e2e scenario "observer": the client sits where a fleet bot sits (first observer slot, team 4, every
// participant slot a computer — `slots` file). Records, for tests/e2e/check_e2e.py to judge:
//   * where -loadfile seats the client, the other slots, bot identity, the game token and the file name;
//   * BotVision as the engine sees it: IsUnitVisible on an invisible unit (needs the bot's true-sight
//     detectors) and on a visible twin (needs only the observers' fog reveal) for EVERY slot, the bot's
//     shared vision both ways and its detector count — the twin proves that a 0 for the invisible unit
//     means "not detected", not "this slot sees nothing at all";
//   * the bot's chat commands: -cam 1 (camera on player 1's hero), -zoom 3500 (camera distance), -cam off,
//     -kd, -time — typed by tests/e2e/run.py, one screenshot each;
//   * one scripted unit kill and hero kill (player 1's hero kills player 4's), the map's -kd counters before
//     and after, for the kill log the bot reads;
//   * the game to its end, as the bot sees it: player 1's hero razes the bases of slots 4..12, team 1 wins, the
//     observer's own ff_result gets winner / placements / gameend (that file is the one the fleet reports), and
//     the bot still sees the invisible unit afterwards.

globals
    unit FF_E2E_ghost = null
    unit FF_E2E_plain = null
    integer FF_E2E_waited = 0
    integer FF_E2E_uk0 = 0
    integer FF_E2E_hk0 = 0
    group FF_E2E_probes = null
endglobals

// BotVision's coverage as FF_bv_Grid lays the cells out: "n=<detectors>,maxgap=<the largest distance from a
// cell centre to its nearest detector>,far=i:j@x:y;..." (cells whose nearest detector is more than 100 away).
function FF_E2E_ObsCoverage takes nothing returns string
    local rect r = GetPlayableMapRect()
    local real cw = (GetRectMaxX(r) - GetRectMinX(r)) / FF_bv_N
    local real ch = (GetRectMaxY(r) - GetRectMinY(r)) / FF_bv_N
    local string far = ""
    local real maxgap = 0.0
    local real best
    local real d
    local integer i = 0
    local integer j
    local real x
    local real y
    local group g = CreateGroup()
    local unit u
    loop
        exitwhen i >= FF_bv_N
        set j = 0
        loop
            exitwhen j >= FF_bv_N
            set x = GetRectMinX(r) + (i + 0.5) * cw
            set y = GetRectMinY(r) + (j + 0.5) * ch
            set best = 1000000000.0
            call GroupClear(g)
            call GroupAddGroup(FF_bv_units, g)
            loop
                set u = FirstOfGroup(g)
                exitwhen u == null
                call GroupRemoveUnit(g, u)
                set d = SquareRoot((GetUnitX(u) - x) * (GetUnitX(u) - x) + (GetUnitY(u) - y) * (GetUnitY(u) - y))
                if d < best then
                    set best = d
                endif
            endloop
            if best > 100.0 then
                set far = far + I2S(i) + ":" + I2S(j) + "@" + FF_E2E_R2S(x) + ":" + FF_E2E_R2S(y) + "~" + FF_E2E_R2S(best) + ";"
            endif
            if best > maxgap then
                set maxgap = best
            endif
            set j = j + 1
        endloop
        set i = i + 1
    endloop
    call DestroyGroup(g)
    set g = null
    set u = null
    set r = null
    return "n=" + I2S(CountUnitsInGroup(FF_bv_units)) + ",maxgap=" + FF_E2E_R2S(maxgap) + ",far=" + far
endfunction

// --- the end, as the bot sees it -------------------------------------------------------------------------------

// After the end: a fresh invisible unit of the winner (the scenario's first ones are gone by then: the map's end
// clears units), read 2s later.
function FF_E2E_ObsFinishRead takes nothing returns nothing
    local integer alive = 0
    local group g = CreateGroup()
    local unit u
    call GroupAddGroup(FF_bv_units, g)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if FF_UnitAlive(u) then
            set alive = alive + 1
        endif
    endloop
    call DestroyGroup(g)
    set g = null
    call FF_E2E_Row("vision,after_end=1,t=" + I2S(FF_E2E_Now()) + ",bot=" + FF_E2E_Bool(IsUnitVisible(FF_E2E_ghost, Player(12))) + ",slot4=" + FF_E2E_Bool(IsUnitVisible(FF_E2E_ghost, Player(3))) + ",ghost_alive=" + FF_E2E_Bool(FF_UnitAlive(FF_E2E_ghost)) + ",twin_bot=" + FF_E2E_Bool(IsUnitVisible(FF_E2E_plain, Player(12))) + ",detectors=" + I2S(CountUnitsInGroup(FF_bv_units)) + ",det_alive=" + I2S(alive))
    call FF_E2E_Done()
endfunction

function FF_E2E_ObsFinish takes nothing returns nothing
    set FF_E2E_ghost = CreateUnit(Player(0), 'hfoo', 0.0, 0.0, 0.0)
    call UnitAddAbility(FF_E2E_ghost, 'Apiv')
    set FF_E2E_plain = CreateUnit(Player(0), 'hfoo', 0.0, 0.0, 0.0)
    call SetUnitInvulnerable(FF_E2E_ghost, true)
    call SetUnitInvulnerable(FF_E2E_plain, true)
    call IssueImmediateOrder(FF_E2E_ghost, "holdposition")
    call IssueImmediateOrder(FF_E2E_plain, "holdposition")
    call FF_E2E_After(2.0, function FF_E2E_ObsFinishRead)
endfunction

// Slot 1's hero razes the bases of slots 4..12; team 1 wins.
function FF_E2E_ObsEndgame takes nothing returns nothing
    local integer s = 4
    loop
        exitwhen s > 12
        call FF_E2E_AddBase(s)
        set s = s + 1
    endloop
    call FF_E2E_EndGame(true, function FF_E2E_ObsFinish)
endfunction

// The direct test: an invisible unit of player 1 at every cell centre; which of them does the bot see?
function FF_E2E_ObsProbeRead takes nothing returns nothing
    local unit u
    local integer seen = 0
    local integer alive = 0
    local string unseen = ""
    loop
        set u = FirstOfGroup(FF_E2E_probes)
        exitwhen u == null
        call GroupRemoveUnit(FF_E2E_probes, u)
        if FF_UnitAlive(u) then
            set alive = alive + 1
            if IsUnitVisible(u, Player(12)) then
                set seen = seen + 1
            else
                set unseen = unseen + FF_E2E_R2S(GetUnitX(u)) + ":" + FF_E2E_R2S(GetUnitY(u)) + ";"
            endif
        endif
        call RemoveUnit(u)
    endloop
    call FF_E2E_Row("probes,t=" + I2S(FF_E2E_Now()) + ",alive=" + I2S(alive) + ",seen=" + I2S(seen) + ",unseen=" + unseen + ",daytime=" + FF_E2E_R2S(GetTimeOfDay()))
    call FF_E2E_ObsEndgame()
    set u = null
endfunction

function FF_E2E_ObsEnd takes nothing returns nothing
    local rect r = GetPlayableMapRect()
    local real cw = (GetRectMaxX(r) - GetRectMinX(r)) / FF_bv_N
    local real ch = (GetRectMaxY(r) - GetRectMinY(r)) / FF_bv_N
    local integer i = 0
    local integer j
    local unit u
    call FF_E2E_Row("detectors,end=1,t=" + I2S(FF_E2E_Now()) + "," + FF_E2E_ObsCoverage())
    set FF_E2E_probes = CreateGroup()
    loop
        exitwhen i >= FF_bv_N
        set j = 0
        loop
            exitwhen j >= FF_bv_N
            set u = CreateUnit(Player(0), 'hfoo', GetRectMinX(r) + (i + 0.5) * cw, GetRectMinY(r) + (j + 0.5) * ch, 0.0)
            call UnitAddAbility(u, 'Apiv')
            call SetUnitInvulnerable(u, true)
            call IssueImmediateOrder(u, "holdposition")
            call GroupAddUnit(FF_E2E_probes, u)
            set j = j + 1
        endloop
        set i = i + 1
    endloop
    call FF_E2E_After(3.0, function FF_E2E_ObsProbeRead)
    set u = null
    set r = null
endfunction

// After the last command: past the map's Mass END (~246s; afterwards the map kills units entering the tavern
// area and hero showroom, where some detector cells lie) for the second detector count, and at least one more
// 30s stats / kill-log refresh, so both files hold the final numbers.
function FF_E2E_ObsSettle takes nothing returns nothing
    if FF_E2E_Now() < 280 then
        call FF_E2E_After(5.0, function FF_E2E_ObsSettle)
        return
    endif
    call FF_E2E_Row("wait,settle=32")
    call FF_E2E_After(32.0, function FF_E2E_ObsEnd)
endfunction

function FF_E2E_ObsTime takes nothing returns nothing
    call FF_E2E_WaitChat("-time", function FF_E2E_ObsSettle)
endfunction

function FF_E2E_ObsKillsAfter takes nothing returns nothing
    call FF_E2E_Row("kills,slot=1,ukills0=" + I2S(FF_E2E_uk0) + ",ukills1=" + I2S(udg_unit_kills[1]) + ",hkills0=" + I2S(FF_E2E_hk0) + ",hkills1=" + I2S(udg_hero_kills[1]) + ",victim_hero_alive=" + FF_E2E_Bool(FF_UnitAlive(udg_herO[4])))
    call FF_E2E_WaitChat("-kd", function FF_E2E_ObsTime)
endfunction

// Player 1's hero kills a fresh footman of player 4, then player 4's hero (real damage, so the map's own
// death triggers count them like any other kill).
function FF_E2E_ObsKills takes nothing returns nothing
    local unit h = udg_herO[1]
    local unit foot = CreateUnit(Player(3), 'hfoo', GetUnitX(h) + 100.0, GetUnitY(h), 0.0)
    set FF_E2E_uk0 = udg_unit_kills[1]
    set FF_E2E_hk0 = udg_hero_kills[1]
    call FF_E2E_Kill(h, foot)
    call FF_E2E_Kill(h, udg_herO[4])
    call FF_E2E_After(2.0, function FF_E2E_ObsKillsAfter)
    set h = null
    set foot = null
endfunction

function FF_E2E_ObsZoomRead takes nothing returns nothing
    call FF_E2E_Row("zoom,after=" + FF_E2E_R2S(GetCameraField(CAMERA_FIELD_TARGET_DISTANCE)))
    call FF_E2E_WaitChat("-cam off", function FF_E2E_ObsKills)
endfunction

function FF_E2E_ObsCamRead takes nothing returns nothing
    local unit h = udg_herO[1]
    local real dx = GetCameraTargetPositionX() - GetUnitX(h)
    local real dy = GetCameraTargetPositionY() - GetUnitY(h)
    call FF_E2E_Row("cam,after=1,dist=" + FF_E2E_R2S(SquareRoot(dx * dx + dy * dy)) + ",hero=" + FF_E2E_R2S(GetUnitX(h)) + ":" + FF_E2E_R2S(GetUnitY(h)))
    call FF_E2E_Row("zoom,before=" + FF_E2E_R2S(GetCameraField(CAMERA_FIELD_TARGET_DISTANCE)))
    call FF_E2E_WaitChat("-zoom 3500", function FF_E2E_ObsZoomRead)
    set h = null
endfunction

function FF_E2E_ObsCamWait takes nothing returns nothing
    call FF_E2E_After(2.0, function FF_E2E_ObsCamRead)
endfunction

function FF_E2E_ObsCam takes nothing returns nothing
    local unit h = udg_herO[1]
    local real dx = GetCameraTargetPositionX() - GetUnitX(h)
    local real dy = GetCameraTargetPositionY() - GetUnitY(h)
    // before the command: the camera is wherever the game put it, normally far from the hero
    call FF_E2E_Row("cam,before=1,dist=" + FF_E2E_R2S(SquareRoot(dx * dx + dy * dy)))
    call FF_E2E_WaitChat("-cam 1", function FF_E2E_ObsCamWait)
    set h = null
endfunction

// Computer slots never pick a hero (the map has no AI): the scenario gives players 1 and 4 one each by
// creating it inside the tavern area, where the map's own TP_hero trigger makes it the slot's hero
// (udg_herO), teleports it home and hands out the starting items — as for a bought hero.
function FF_E2E_ObsWaitHero takes nothing returns nothing
    if FF_UnitAlive(udg_herO[1]) and FF_UnitAlive(udg_herO[4]) then
        call FF_E2E_Row("hero,1=" + FF_us_Id2S(GetUnitTypeId(udg_herO[1])) + ",4=" + FF_us_Id2S(GetUnitTypeId(udg_herO[4])) + ",waited=" + I2S(FF_E2E_waited))
        call FF_E2E_ObsCam()
        return
    endif
    set FF_E2E_waited = FF_E2E_waited + 2
    if FF_E2E_waited > 300 then
        call FF_E2E_Row("hero,timeout=300")
        call FF_E2E_WaitChat("-kd", function FF_E2E_ObsTime)
        return
    endif
    call FF_E2E_After(2.0, function FF_E2E_ObsWaitHero)
endfunction

function FF_E2E_ObsVision takes nothing returns nothing
    local integer i = 0
    local string inv = "vision,unit=invisible"
    local string vis = "vision,unit=visible"
    local string invto = "invisible_to"
    local string share = "share,from=12"
    local string back = "share,to=12"
    loop
        exitwhen i >= bj_MAX_PLAYER_SLOTS
        set inv = inv + "," + I2S(i) + "=" + FF_E2E_Bool(IsUnitVisible(FF_E2E_ghost, Player(i)))
        set vis = vis + "," + I2S(i) + "=" + FF_E2E_Bool(IsUnitVisible(FF_E2E_plain, Player(i)))
        set invto = invto + "," + I2S(i) + "=" + FF_E2E_Bool(IsUnitInvisible(FF_E2E_ghost, Player(i)))
        if i != 12 then
            set share = share + "," + I2S(i) + "=" + FF_E2E_Bool(GetPlayerAlliance(Player(12), Player(i), ALLIANCE_SHARED_VISION))
            set back = back + "," + I2S(i) + "=" + FF_E2E_Bool(GetPlayerAlliance(Player(i), Player(12), ALLIANCE_SHARED_VISION))
        endif
        set i = i + 1
    endloop
    call FF_E2E_Row(inv + ",flag=" + FF_E2E_Bool(IsUnitInvisible(FF_E2E_ghost, GetLocalPlayer())))
    call FF_E2E_Row(vis)
    call FF_E2E_Row(invto)
    call FF_E2E_Row(share)
    call FF_E2E_Row(back)
    // BotVision's detector dummies (Locust, so no unit-group enumeration finds them: its own group)
    call FF_E2E_Row("detectors,start=1,t=" + I2S(FF_E2E_Now()) + "," + FF_E2E_ObsCoverage())
    call FF_E2E_After(1.0, function FF_E2E_ObsWaitHero)
endfunction

// The host's game-type dialog: the host is a computer (Player 0): the map answers its dialog itself after 8s.
function FF_E2E_HostClick takes nothing returns string
    return ""
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    call FF_E2E_Begin("observer")
    // Two footmen of player 1 (slot 0) in the middle of the map, out of everyone's way: one permanently
    // invisible, one plain.
    set FF_E2E_ghost = CreateUnit(Player(0), 'hfoo', 0.0, 0.0, 0.0)
    call UnitAddAbility(FF_E2E_ghost, 'Apiv')
    set FF_E2E_plain = CreateUnit(Player(0), 'hfoo', 0.0, 0.0, 0.0)
    // never paused: a paused unit loses its permanent invisibility
    call SetUnitInvulnerable(FF_E2E_ghost, true)
    call SetUnitInvulnerable(FF_E2E_plain, true)
    call IssueImmediateOrder(FF_E2E_ghost, "holdposition")
    call IssueImmediateOrder(FF_E2E_plain, "holdposition")
    call CreateUnit(Player(0), 'H005', -2600.0, -300.0, 0.0)
    call CreateUnit(Player(3), 'H005', -2600.0, -300.0, 0.0)
    call FF_E2E_After(3.0, function FF_E2E_ObsVision)
endfunction
