// e2e scenario "kd": the K/D cases of the map's own counters (the in-game -kd), with the client as player 1 (slot 1,
// a participant; slots 2-12 are computers — `slots` file), all before Mass START (~98s) at the empty map centre.
// Each case records the counters of slots 1, 2 and 4 right before and 2s after (`kd,case=<n>,when=0|1,...`);
// tests/e2e/check_e2e.py judges the change. Afterwards the kill log, the stats rows and a snapshot of every slot's
// counters are written in one tick (`kdsnap`), so the checker can compare all three exactly.
//   1 enemy footman killed by slot 1's hero        5 killer already dead          8 enemy hero killed
//   2 own footman                                  6 neutral-aggressive killer    9 allied hero killed
//   3 allied footman                               7 slot 4's cannon tower attacks a slot 1 footman (a real attack)
//   4 an illusion of slot 4 (Wand of Illusion)

globals
    unit FF_E2E_kdHero = null
    unit FF_E2E_kdVictim = null
    unit FF_E2E_kdKiller = null
    unit FF_E2E_kdTower = null
    unit FF_E2E_kdCreep = null
    integer FF_E2E_kdCase = 0
    integer FF_E2E_kdWaited = 0
    // the last death the scenario caused: the killer as the engine reports it
    string FF_E2E_kdDeath = ""
    code FF_E2E_kdNextCode = null
endglobals

function FF_E2E_KdCounters takes integer slot returns string
    return ",uk" + I2S(slot) + "=" + I2S(udg_unit_kills[slot]) + ",hk" + I2S(slot) + "=" + I2S(udg_hero_kills[slot]) + ",ud" + I2S(slot) + "=" + I2S(udg_unit_deaths[slot]) + ",hd" + I2S(slot) + "=" + I2S(udg_hero_deaths[slot])
endfunction

function FF_E2E_KdRecord takes integer when returns nothing
    call FF_E2E_Row("kd,case=" + I2S(FF_E2E_kdCase) + ",when=" + I2S(when) + FF_E2E_KdCounters(1) + FF_E2E_KdCounters(2) + FF_E2E_KdCounters(4))
endfunction

// Every death while a case runs: who died and the killer the engine names (owner slot, alive, illusion victim).
function FF_E2E_KdOnDeath takes nothing returns nothing
    local unit v = GetTriggerUnit()
    local unit k = GetKillingUnit()
    local string ks = "none"
    if FF_E2E_kdCase == 0 then
        set v = null
        set k = null
        return
    endif
    if k != null then
        set ks = I2S(GetPlayerId(GetOwningPlayer(k)) + 1) + ",kalive=" + FF_E2E_Bool(FF_UnitAlive(k))
    endif
    set FF_E2E_kdDeath = "death,case=" + I2S(FF_E2E_kdCase) + ",victim=" + I2S(GetPlayerId(GetOwningPlayer(v)) + 1) + ",vtype=" + FF_us_Id2S(GetUnitTypeId(v)) + ",illusion=" + FF_E2E_Bool(IsUnitIllusion(v)) + ",killer=" + ks
    call FF_E2E_Row(FF_E2E_kdDeath)
    set v = null
    set k = null
endfunction

function FF_E2E_KdCaseRead takes nothing returns nothing
    call FF_E2E_KdRecord(1)
    call FF_E2E_After(1.0, FF_E2E_kdNextCode)
endfunction

// Starts case `n`: the counters before, then the case's own action.
function FF_E2E_KdBegin takes integer n returns nothing
    set FF_E2E_kdCase = n
    call FF_E2E_KdRecord(0)
endfunction

function FF_E2E_KdFoot takes integer slot, real dx returns unit
    return CreateUnit(Player(slot - 1), 'hfoo', 0.0 + dx, -256.0, 0.0)
endfunction

// --- the end: kill log, stats and the counters in one tick -----------------------------------------------------

function FF_E2E_KdFinish takes nothing returns nothing
    call FF_E2E_Done()
endfunction

function FF_E2E_KdKdTyped takes nothing returns nothing
    call FF_E2E_After(2.0, function FF_E2E_KdFinish)
endfunction

function FF_E2E_KdSnapshot takes nothing returns nothing
    local integer i = 1
    local string a = "kdsnap,part=1"
    local string b = "kdsnap,part=2"
    set FF_E2E_kdCase = 0
    call FF_kl_Flush()
    call FF_gr_RefreshStats()
    call FF_gr_Flush()
    loop
        exitwhen i > 12
        if i <= 6 then
            set a = a + FF_E2E_KdCounters(i)
        else
            set b = b + FF_E2E_KdCounters(i)
        endif
        set i = i + 1
    endloop
    call FF_E2E_Row(a)
    call FF_E2E_Row(b)
    call FF_E2E_WaitChat("-kd", function FF_E2E_KdKdTyped)
endfunction

// --- the cases -------------------------------------------------------------------------------------------------

function FF_E2E_KdCase9 takes nothing returns nothing
    call FF_E2E_KdBegin(9)
    set FF_E2E_kdNextCode = function FF_E2E_KdSnapshot
    call FF_E2E_Kill(FF_E2E_kdHero, udg_herO[2])
    call FF_E2E_After(2.0, function FF_E2E_KdCaseRead)
endfunction

function FF_E2E_KdCase8 takes nothing returns nothing
    call FF_E2E_KdBegin(8)
    set FF_E2E_kdNextCode = function FF_E2E_KdCase9
    call FF_E2E_Kill(FF_E2E_kdHero, udg_herO[4])
    call FF_E2E_After(2.0, function FF_E2E_KdCaseRead)
endfunction

// The tower attacks on its own; if the footman still lives after 12s the tower deals the damage directly.
function FF_E2E_KdTowerWait takes nothing returns nothing
    if FF_UnitAlive(FF_E2E_kdVictim) and FF_E2E_kdWaited < 12 then
        set FF_E2E_kdWaited = FF_E2E_kdWaited + 1
        call FF_E2E_After(1.0, function FF_E2E_KdTowerWait)
        return
    endif
    if FF_UnitAlive(FF_E2E_kdVictim) then
        call FF_E2E_Row("tower,attack=0")
        call FF_E2E_Kill(FF_E2E_kdTower, FF_E2E_kdVictim)
    else
        call FF_E2E_Row("tower,attack=1,secs=" + I2S(FF_E2E_kdWaited))
    endif
    call FF_E2E_After(2.0, function FF_E2E_KdCaseRead)
endfunction

function FF_E2E_KdCase7 takes nothing returns nothing
    call FF_E2E_KdBegin(7)
    set FF_E2E_kdNextCode = function FF_E2E_KdCase8
    set FF_E2E_kdTower = CreateUnit(Player(3), 'hctw', 300.0, -256.0, 180.0)
    set FF_E2E_kdVictim = FF_E2E_KdFoot(1, 0.0)
    call SetUnitState(FF_E2E_kdVictim, UNIT_STATE_LIFE, 5.0)
    set FF_E2E_kdWaited = 0
    call FF_E2E_After(1.0, function FF_E2E_KdTowerWait)
endfunction

function FF_E2E_KdCase7Prep takes nothing returns nothing
    // the tower must only see its victim: nothing else of slot 1 and no other unit of slot 4 near the centre
    call SetUnitPosition(FF_E2E_kdHero, -2600.0, -300.0)
    call RemoveUnit(FF_E2E_kdCreep)
    if FF_UnitAlive(FF_E2E_kdVictim) then
        call RemoveUnit(FF_E2E_kdVictim)
    endif
    call FF_E2E_KdCase7()
endfunction

function FF_E2E_KdCase6 takes nothing returns nothing
    call FF_E2E_KdBegin(6)
    set FF_E2E_kdNextCode = function FF_E2E_KdCase7Prep
    set FF_E2E_kdCreep = CreateUnit(Player(PLAYER_NEUTRAL_AGGRESSIVE), 'hfoo', 0.0, -456.0, 0.0)
    call PauseUnit(FF_E2E_kdCreep, true)
    call FF_E2E_Kill(FF_E2E_kdCreep, FF_E2E_KdFoot(1, 0.0))
    call FF_E2E_After(2.0, function FF_E2E_KdCaseRead)
endfunction

function FF_E2E_KdCase5 takes nothing returns nothing
    call FF_E2E_KdBegin(5)
    set FF_E2E_kdNextCode = function FF_E2E_KdCase6
    set FF_E2E_kdKiller = FF_E2E_KdFoot(1, -200.0)
    set FF_E2E_kdVictim = FF_E2E_KdFoot(4, 100.0)
    call PauseUnit(FF_E2E_kdVictim, true)
    // the killer's own death is a case-5 death too (no killer): recorded, counted for nobody
    call KillUnit(FF_E2E_kdKiller)
    call FF_E2E_Kill(FF_E2E_kdKiller, FF_E2E_kdVictim)
    call FF_E2E_After(2.0, function FF_E2E_KdCaseRead)
endfunction

// Slot 4's illusion of its footman, killed by slot 1's hero.
function FF_E2E_KdIllusionKill takes nothing returns nothing
    local group g = CreateGroup()
    local unit u
    local unit ill = null
    call GroupEnumUnitsOfPlayer(g, Player(3), null)
    loop
        set u = FirstOfGroup(g)
        exitwhen u == null
        call GroupRemoveUnit(g, u)
        if IsUnitIllusion(u) and FF_UnitAlive(u) then
            set ill = u
        endif
    endloop
    call DestroyGroup(g)
    call FF_E2E_Row("illusion,found=" + FF_E2E_Bool(ill != null))
    call SetUnitPosition(udg_herO[4], -2600.0, -300.0)
    if ill != null then
        call FF_E2E_Kill(FF_E2E_kdHero, ill)
    endif
    call FF_E2E_After(2.0, function FF_E2E_KdCaseRead)
    set g = null
    set ill = null
endfunction

function FF_E2E_KdCase4 takes nothing returns nothing
    local unit h4 = udg_herO[4]
    local item wand
    call FF_E2E_KdBegin(4)
    set FF_E2E_kdNextCode = function FF_E2E_KdCase5
    set FF_E2E_kdVictim = FF_E2E_KdFoot(4, 150.0)
    call PauseUnit(FF_E2E_kdVictim, true)
    call SetUnitPosition(h4, 300.0, -256.0)
    set wand = UnitAddItemById(h4, 'will')
    call FF_E2E_Row("illusion,order=" + FF_E2E_Bool(UnitUseItemTarget(h4, wand, FF_E2E_kdVictim)))
    call FF_E2E_After(2.0, function FF_E2E_KdIllusionKill)
    set h4 = null
    set wand = null
endfunction

function FF_E2E_KdCase3 takes nothing returns nothing
    call FF_E2E_KdBegin(3)
    set FF_E2E_kdNextCode = function FF_E2E_KdCase4
    call FF_E2E_Kill(FF_E2E_kdHero, FF_E2E_KdFoot(2, 100.0))
    call FF_E2E_After(2.0, function FF_E2E_KdCaseRead)
endfunction

function FF_E2E_KdCase2 takes nothing returns nothing
    call FF_E2E_KdBegin(2)
    set FF_E2E_kdNextCode = function FF_E2E_KdCase3
    call FF_E2E_Kill(FF_E2E_kdHero, FF_E2E_KdFoot(1, 100.0))
    call FF_E2E_After(2.0, function FF_E2E_KdCaseRead)
endfunction

function FF_E2E_KdCase1 takes nothing returns nothing
    local integer i = 1
    local string h = "hero"
    loop
        exitwhen i > 12
        set h = h + "," + I2S(i) + "=" + FF_us_Id2S(GetUnitTypeId(udg_herO[i]))
        set i = i + 1
    endloop
    call FF_E2E_Row(h)
    set FF_E2E_kdHero = udg_herO[1]
    // paused: it kills only through the scenario's damage, never by attacking on its own
    call SetUnitInvulnerable(FF_E2E_kdHero, true)
    call SetUnitPosition(FF_E2E_kdHero, -300.0, -256.0)
    call PauseUnit(FF_E2E_kdHero, true)
    call FF_E2E_KdBegin(1)
    set FF_E2E_kdNextCode = function FF_E2E_KdCase2
    call FF_E2E_Kill(FF_E2E_kdHero, FF_E2E_KdFoot(4, 100.0))
    call FF_E2E_After(2.0, function FF_E2E_KdCaseRead)
endfunction

// The host's game-type dialog: "Pub Game Default", the first of the main map's four buttons.
function FF_E2E_HostClick takes nothing returns string
    return "0.5 0.478"
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    local integer i = 0
    local trigger t = CreateTrigger()
    call FF_E2E_Begin("kd")
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_DEATH)
    call TriggerAddAction(t, function FF_E2E_KdOnDeath)
    loop
        exitwhen i >= 12
        call CreateUnit(Player(i), 'H005', -2600.0, -300.0, 0.0)
        set i = i + 1
    endloop
    call FF_E2E_After(3.0, function FF_E2E_KdCase1)
    set t = null
endfunction
