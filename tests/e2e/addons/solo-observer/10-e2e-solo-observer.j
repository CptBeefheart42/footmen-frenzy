// e2e scenario "solo-observer" (Solo 1v1v1v1 map only): the client spectates, where a fleet bot sits (the first
// observer slot, Player 12; the four Solo seats 1, 5, 8, 12 are computers — `slots` file). The host is a computer,
// so nobody answers the game-type dialog and the map's AFK-host timer starts a pub game. The game is played to its
// end by script, and the file under test is the spectator's own ff_result: the one the fleet reports.
//   t~3     heroes for the four seats (created in the tavern area: the map's TP_hero makes them the seats' heroes);
//           an invisible footman of slot 1 (BotVision: the bot must see it)
//   chat    -kd typed by tests/e2e/run.py (an observer's command: not counted as player usage)
//   t>=125  (bases vulnerable at 120s) slot 1's hero razes the bases of slots 5, 8, 12: placements team1, team4,
//           team3, team2; the bot still sees the invisible unit afterwards

globals
    unit FF_E2E_ghost = null
endglobals

function FF_E2E_SoFinish takes nothing returns nothing
    call FF_E2E_Row("vision,after_end=1,t=" + I2S(FF_E2E_Now()) + ",bot=" + FF_E2E_Bool(IsUnitVisible(FF_E2E_ghost, Player(12))) + ",slot5=" + FF_E2E_Bool(IsUnitVisible(FF_E2E_ghost, Player(4))))
    call FF_E2E_Done()
endfunction

// From 125s (bases are vulnerable at 120s): slot 1's hero razes the bases of slots 5, 8, 12 in this order.
function FF_E2E_SoEndgame takes nothing returns nothing
    if FF_E2E_Now() < 125 then
        call FF_E2E_After(2.0, function FF_E2E_SoEndgame)
        return
    endif
    call FF_E2E_AddBase(5)
    call FF_E2E_AddBase(8)
    call FF_E2E_AddBase(12)
    call FF_E2E_EndGame(true, function FF_E2E_SoFinish)
endfunction

function FF_E2E_SoVision takes nothing returns nothing
    local integer i = 0
    local string inv = "vision,unit=invisible"
    loop
        exitwhen i >= 16
        set inv = inv + "," + I2S(i) + "=" + FF_E2E_Bool(IsUnitVisible(FF_E2E_ghost, Player(i)))
        set i = i + 1
    endloop
    call FF_E2E_Row(inv)
    call FF_E2E_Row("hero,1=" + FF_us_Id2S(GetUnitTypeId(udg_herO[1])) + ",5=" + FF_us_Id2S(GetUnitTypeId(udg_herO[5])) + ",8=" + FF_us_Id2S(GetUnitTypeId(udg_herO[8])) + ",12=" + FF_us_Id2S(GetUnitTypeId(udg_herO[12])))
    call FF_E2E_WaitChat("-kd", function FF_E2E_SoEndgame)
endfunction

// The host (Player 0) is a computer: the map's AFK-host timer picks the game type.
function FF_E2E_HostClick takes nothing returns string
    return ""
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    call FF_E2E_Begin("solo-observer")
    call CreateUnit(Player(0), 'H005', -2600.0, -300.0, 0.0)
    call CreateUnit(Player(4), 'H005', -2600.0, -300.0, 0.0)
    call CreateUnit(Player(7), 'H005', -2600.0, -300.0, 0.0)
    call CreateUnit(Player(11), 'H005', -2600.0, -300.0, 0.0)
    // never paused: a paused unit loses its permanent invisibility
    set FF_E2E_ghost = CreateUnit(Player(0), 'hfoo', 0.0, 0.0, 0.0)
    call UnitAddAbility(FF_E2E_ghost, 'Apiv')
    call SetUnitInvulnerable(FF_E2E_ghost, true)
    call IssueImmediateOrder(FF_E2E_ghost, "holdposition")
    call FF_E2E_After(5.0, function FF_E2E_SoVision)
endfunction
