// e2e scenario "towerfire": what a tower's attack does to allied units, with the client as player 1 (slot 1, a
// participant; slots 2-12 are computers — `slots` file). Slot 2 is slot 1's ally, slot 4 an enemy. At the empty map
// centre before Mass START (~98s), one case at a time, each with a fresh slot 2 cannon tower (`hctw`):
//   1 splash: the tower shoots an enemy footman on its own; a slot 1 (allied) and a slot 2 (own) footman stand next to it
//   2 an ordered attack on a slot 1 (allied) footman, a second slot 1 footman next to it
//   3 an ordered attack on a slot 2 (own) footman
//   4 control: the tower shoots an enemy footman on its own, a second enemy footman next to it (does splash kill at all?)
//   5 like 1 with an Arcane Tower of Terror (`h00S`, its splash list names allies explicitly)
// The footmen can't attack or move (`Abun`, hold position) and have 5 hit points. Every death records its killer
// (`death,case=..`), every order a test tower gets is recorded (`order,case=..`), and the deny counters of slots 1
// and 2 are read 2s after each case (`deny,case=..`). Then, until 180s (past Mass START, the spawns running), every
// order the game issues is counted (`orders,...`): how often order events fire, and whether the map itself ever
// orders a building to attack an allied or own unit. tests/e2e/check_e2e.py judges.

globals
    unit FF_E2E_tfTower = null
    integer FF_E2E_tfCase = 0
    code FF_E2E_tfNextCode = null
    // order events from Mass START on: all, unit-target, by buildings, a building's attack order on an allied or own unit
    integer FF_E2E_tfOrders = 0
    integer FF_E2E_tfTargetOrders = 0
    integer FF_E2E_tfBuildingOrders = 0
    integer FF_E2E_tfFriendlyAttacks = 0
    integer FF_E2E_tfCountFrom = -1
endglobals

function FF_E2E_TfSlot takes unit u returns string
    if u == null then
        return "none"
    endif
    return I2S(GetPlayerId(GetOwningPlayer(u)) + 1)
endfunction

// A footman of `slot` at (x, -256) that neither attacks nor moves, with 5 hit points.
function FF_E2E_TfFoot takes integer slot, real x returns unit
    local unit u = CreateUnit(Player(slot - 1), 'hfoo', x, -256.0, 0.0)
    call UnitAddAbility(u, 'Abun')
    call IssueImmediateOrder(u, "holdposition")
    call SetUnitState(u, UNIT_STATE_LIFE, 5.0)
    return u
endfunction

function FF_E2E_TfOnDeath takes nothing returns nothing
    local unit v = GetTriggerUnit()
    local unit k = GetKillingUnit()
    if FF_E2E_tfCase > 0 then
        call FF_E2E_Row("death,case=" + I2S(FF_E2E_tfCase) + ",victim=" + FF_E2E_TfSlot(v) + ",vtype=" + FF_us_Id2S(GetUnitTypeId(v)) + ",killer=" + FF_E2E_TfSlot(k) + ",bytower=" + FF_E2E_Bool(k != null and k == FF_E2E_tfTower) + ",t=" + I2S(FF_E2E_Now()))
    endif
    set v = null
    set k = null
endfunction

// Every order event: the test tower's own orders are recorded one by one; after Mass START all are counted.
function FF_E2E_TfOnOrder takes nothing returns nothing
    local unit u = GetTriggerUnit()
    local unit t = GetOrderTargetUnit()
    local boolean building = IsUnitType(u, UNIT_TYPE_STRUCTURE)
    if u == FF_E2E_tfTower and FF_E2E_tfCase > 0 then
        call FF_E2E_Row("order,case=" + I2S(FF_E2E_tfCase) + ",id=" + I2S(GetIssuedOrderId()) + ",name=" + OrderId2String(GetIssuedOrderId()) + ",target=" + FF_E2E_TfSlot(t) + ",t=" + I2S(FF_E2E_Now()))
    endif
    if FF_E2E_tfCountFrom >= 0 then
        set FF_E2E_tfOrders = FF_E2E_tfOrders + 1
        if t != null then
            set FF_E2E_tfTargetOrders = FF_E2E_tfTargetOrders + 1
        endif
        if building then
            set FF_E2E_tfBuildingOrders = FF_E2E_tfBuildingOrders + 1
            if t != null and GetIssuedOrderId() == 851983 and (GetOwningPlayer(t) == GetOwningPlayer(u) or IsPlayerAlly(GetOwningPlayer(t), GetOwningPlayer(u))) then
                set FF_E2E_tfFriendlyAttacks = FF_E2E_tfFriendlyAttacks + 1
            endif
        endif
    endif
    set u = null
    set t = null
endfunction

// --- the order count after Mass START -------------------------------------------------------------------------

function FF_E2E_TfCountEnd takes nothing returns nothing
    call FF_E2E_Row("orders,from=" + I2S(FF_E2E_tfCountFrom) + ",to=" + I2S(FF_E2E_Now()) + ",all=" + I2S(FF_E2E_tfOrders) + ",target=" + I2S(FF_E2E_tfTargetOrders) + ",building=" + I2S(FF_E2E_tfBuildingOrders) + ",friendly_attack=" + I2S(FF_E2E_tfFriendlyAttacks))
    call FF_E2E_Done()
endfunction

function FF_E2E_TfCountStart takes nothing returns nothing
    set FF_E2E_tfCase = 0
    if FF_E2E_tfTower != null then
        call RemoveUnit(FF_E2E_tfTower)
        set FF_E2E_tfTower = null
    endif
    // from 100s (right after Mass START) to 180s
    if FF_E2E_Now() < 100 then
        call FF_E2E_After(100.0 - FF_E2E_Now(), function FF_E2E_TfCountStart)
        return
    endif
    set FF_E2E_tfCountFrom = FF_E2E_Now()
    call FF_E2E_After(80.0, function FF_E2E_TfCountEnd)
endfunction

// --- the cases -------------------------------------------------------------------------------------------------

function FF_E2E_TfRead takes nothing returns nothing
    call FF_E2E_Row("deny,case=" + I2S(FF_E2E_tfCase) + ",own1=" + I2S(FF_st_denyOwn[1]) + ",ally1=" + I2S(FF_st_denyAlly[1]) + ",own2=" + I2S(FF_st_denyOwn[2]) + ",ally2=" + I2S(FF_st_denyAlly[2]))
    call RemoveUnit(FF_E2E_tfTower)
    set FF_E2E_tfTower = null
    call FF_E2E_After(1.0, FF_E2E_tfNextCode)
endfunction

function FF_E2E_TfTowerOf takes integer typeId returns nothing
    set FF_E2E_tfTower = CreateUnit(Player(1), typeId, 400.0, -256.0, 180.0)
endfunction

function FF_E2E_TfTower takes nothing returns nothing
    call FF_E2E_TfTowerOf('hctw')
endfunction

function FF_E2E_TfCase5 takes nothing returns nothing
    set FF_E2E_tfCase = 5
    set FF_E2E_tfNextCode = function FF_E2E_TfCountStart
    call FF_E2E_TfTowerOf('h00S')
    call FF_E2E_TfFoot(4, 0.0)
    call FF_E2E_TfFoot(1, 60.0)
    call FF_E2E_TfFoot(2, -60.0)
    call FF_E2E_After(8.0, function FF_E2E_TfRead)
endfunction

function FF_E2E_TfCase4 takes nothing returns nothing
    set FF_E2E_tfCase = 4
    set FF_E2E_tfNextCode = function FF_E2E_TfCase5
    call FF_E2E_TfTower()
    call FF_E2E_TfFoot(4, 0.0)
    call FF_E2E_TfFoot(4, -60.0)
    call FF_E2E_After(8.0, function FF_E2E_TfRead)
endfunction

function FF_E2E_TfCase3 takes nothing returns nothing
    local unit own
    set FF_E2E_tfCase = 3
    set FF_E2E_tfNextCode = function FF_E2E_TfCase4
    call FF_E2E_TfTower()
    set own = FF_E2E_TfFoot(2, 0.0)
    call FF_E2E_Row("issue,case=3,ok=" + FF_E2E_Bool(IssueTargetOrder(FF_E2E_tfTower, "attack", own)))
    call FF_E2E_After(8.0, function FF_E2E_TfRead)
    set own = null
endfunction

function FF_E2E_TfCase2 takes nothing returns nothing
    local unit ally
    set FF_E2E_tfCase = 2
    set FF_E2E_tfNextCode = function FF_E2E_TfCase3
    call FF_E2E_TfTower()
    set ally = FF_E2E_TfFoot(1, 0.0)
    call FF_E2E_TfFoot(1, 60.0)
    call FF_E2E_Row("issue,case=2,ok=" + FF_E2E_Bool(IssueTargetOrder(FF_E2E_tfTower, "attack", ally)))
    call FF_E2E_After(8.0, function FF_E2E_TfRead)
    set ally = null
endfunction

function FF_E2E_TfCase1 takes nothing returns nothing
    local integer i = 1
    local string h = "hero"
    loop
        exitwhen i > 12
        set h = h + "," + I2S(i) + "=" + FF_us_Id2S(GetUnitTypeId(udg_herO[i]))
        set i = i + 1
    endloop
    call FF_E2E_Row(h)
    // the client's hero away from the centre, so the tower only sees the case's footmen
    call SetUnitInvulnerable(udg_herO[1], true)
    call SetUnitPosition(udg_herO[1], -2600.0, -300.0)
    call PauseUnit(udg_herO[1], true)
    set FF_E2E_tfCase = 1
    set FF_E2E_tfNextCode = function FF_E2E_TfCase2
    call FF_E2E_TfTower()
    call FF_E2E_TfFoot(4, 0.0)
    call FF_E2E_TfFoot(1, 60.0)
    call FF_E2E_TfFoot(2, -60.0)
    call FF_E2E_After(8.0, function FF_E2E_TfRead)
endfunction

// The host's game-type dialog: "Pub Game Default", the first of the main map's four buttons.
function FF_E2E_HostClick takes nothing returns string
    return "0.5 0.478"
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    local integer i = 0
    local trigger d = CreateTrigger()
    local trigger o = CreateTrigger()
    call FF_E2E_Begin("towerfire")
    call TriggerRegisterAnyUnitEventBJ(d, EVENT_PLAYER_UNIT_DEATH)
    call TriggerAddAction(d, function FF_E2E_TfOnDeath)
    call TriggerRegisterAnyUnitEventBJ(o, EVENT_PLAYER_UNIT_ISSUED_ORDER)
    call TriggerRegisterAnyUnitEventBJ(o, EVENT_PLAYER_UNIT_ISSUED_POINT_ORDER)
    call TriggerRegisterAnyUnitEventBJ(o, EVENT_PLAYER_UNIT_ISSUED_TARGET_ORDER)
    call TriggerAddAction(o, function FF_E2E_TfOnOrder)
    loop
        exitwhen i >= 12
        call CreateUnit(Player(i), 'H005', -2600.0, -300.0, 0.0)
        set i = i + 1
    endloop
    call FF_E2E_After(3.0, function FF_E2E_TfCase1)
    set d = null
    set o = null
endfunction
