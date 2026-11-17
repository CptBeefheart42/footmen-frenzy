// e2e scenario "transmute_leaverbase" (main, exploratory, not in E2E_SUITE): the multiplayer Transmute crash through
// the map's leaver handling. Slot 4 leaves while its allies (slots 5, 6) stay, so the map gives them a h02Q with
// "BASE destroy" (A06W, Trig_BASE_destroy: kills every unit of the leaver). Transmute's range is 3000 in this build
// (object_overrides.csv), so a cast from 2000 away flies ~5 s at normal speed:
//   cast       slot 1's Alchemist on a slot-4 footman 2000 away: `inflight`
//   leave      single player: the map's own kick removes slot 4 (a computer) 0.5 s later; two clients over LAN
//              (slot 4 a human): the runner kills that client's game on `inflight` (a disconnect)
//   destroy    as soon as slot 5's h02Q exists, it casts BASE destroy: `basedestroy`
// Then a `tick` row every second for 20 s (slot 4's state, the target, Transmute counters), END. A crash leaves the
// last tick.

globals
    unit FF_E2E_lbHero = null
    unit FF_E2E_lbTarget = null
    integer FF_E2E_lbTicks = 0
    integer FF_E2E_lbTries = 0
    integer FF_E2E_lbWaited = 0
endglobals

function FF_E2E_LbState takes nothing returns string
    return "active4=" + FF_E2E_Bool(udg_player_active[4]) + ",state4=" + FF_E2E_State(Player(3)) + ",target=" + FF_E2E_Bool(FF_UnitAlive(FF_E2E_lbTarget)) + FF_E2E_Bool(GetUnitTypeId(FF_E2E_lbTarget) != 0) + "@" + I2S(R2I(GetUnitX(FF_E2E_lbTarget) - GetUnitX(FF_E2E_lbHero))) + ",hits=" + I2S(FF_st_tmHits[1]) + ",denied=" + I2S(FF_st_tmDenied[1])
endfunction

function FF_E2E_LbTick takes nothing returns nothing
    set FF_E2E_lbTicks = FF_E2E_lbTicks + 1
    call FF_E2E_Row("tick,n=" + I2S(FF_E2E_lbTicks) + ",t=" + I2S(FF_E2E_Now()) + "," + FF_E2E_LbState())
    if FF_E2E_lbTicks >= 20 then
        call FF_E2E_Done()
        return
    endif
    call FF_E2E_After(1.0, function FF_E2E_LbTick)
endfunction

// Slot 5's h02Q appears once the map has handled slot 4's leave: it casts BASE destroy at once.
function FF_E2E_LbDestroy takes nothing returns nothing
    local unit d = FF_E2E_Nearest(Player(4), 'h02Q', 0.0, 0.0)
    local boolean ok
    if d == null then
        set FF_E2E_lbWaited = FF_E2E_lbWaited + 1
        if FF_E2E_lbWaited < 150 then
            call FF_E2E_After(0.1, function FF_E2E_LbDestroy)
        else
            call FF_E2E_Row("basedestroy,none=1," + FF_E2E_LbState())
        endif
        return
    endif
    set ok = IssueImmediateOrder(d, "creepthunderclap")
    call FF_E2E_Row("basedestroy,order=" + FF_E2E_Bool(ok) + ",waited=" + I2S(FF_E2E_lbWaited) + ",t=" + I2S(FF_E2E_Now()) + "," + FF_E2E_LbState())
    set d = null
endfunction

function FF_E2E_LbKick takes nothing returns nothing
    set FF_afk_slot = 4
    call TriggerExecute(FF_afk_kickHook)
endfunction

function FF_E2E_LbOnSpell takes nothing returns nothing
    if GetSpellAbilityId() == 'A06W' then
        call FF_E2E_Row("basedestroy,effect=1,t=" + I2S(FF_E2E_Now()) + "," + FF_E2E_LbState())
        return
    endif
    if GetTriggerUnit() != FF_E2E_lbHero or GetSpellAbilityId() != 'ANtm' then
        return
    endif
    call FF_E2E_Row("inflight,t=" + I2S(FF_E2E_Now()) + ",slot4=" + FF_E2E_Ctrl(Player(3)) + "," + FF_E2E_LbState())
    if GetPlayerController(Player(3)) == MAP_CONTROL_COMPUTER then
        call FF_E2E_After(0.5, function FF_E2E_LbKick)
    endif
    call FF_E2E_After(0.2, function FF_E2E_LbDestroy)
    call FF_E2E_After(1.0, function FF_E2E_LbTick)
endfunction

function FF_E2E_LbOrder takes nothing returns nothing
    local boolean ok
    call UnitResetCooldown(FF_E2E_lbHero)
    call SetUnitState(FF_E2E_lbHero, UNIT_STATE_MANA, GetUnitState(FF_E2E_lbHero, UNIT_STATE_MAX_MANA))
    set ok = IssueTargetOrder(FF_E2E_lbHero, "transmute", FF_E2E_lbTarget)
    set FF_E2E_lbTries = FF_E2E_lbTries + 1
    if not ok and FF_E2E_lbTries < 10 then
        call FF_E2E_After(1.0, function FF_E2E_LbOrder)
        return
    endif
    call FF_E2E_Row("cast,order=" + FF_E2E_Bool(ok) + ",tries=" + I2S(FF_E2E_lbTries) + ",t=" + I2S(FF_E2E_Now()) + "," + FF_E2E_LbState())
endfunction

function FF_E2E_LbSetup takes nothing returns nothing
    call FF_E2E_Row("hero,slot1=" + FF_E2E_Bool(udg_herO[1] == FF_E2E_lbHero) + ",slot4=" + FF_E2E_Ctrl(Player(3)))
    call SetUnitInvulnerable(FF_E2E_lbHero, true)
    call SetHeroLevel(FF_E2E_lbHero, 6, false)
    call SelectHeroSkill(FF_E2E_lbHero, 'ANtm')
    call SetUnitPosition(FF_E2E_lbHero, -1000.0, -256.0)
    set FF_E2E_lbTarget = CreateUnit(Player(3), 'hfoo', 1000.0, -256.0, 0.0)
    call IssueImmediateOrder(FF_E2E_lbTarget, "holdposition")
    // the caster must see its target (2000 away, beyond its sight)
    call UnitShareVision(FF_E2E_lbTarget, Player(0), true)
    call FF_E2E_LbOrder()
endfunction

function FF_E2E_HostClick takes nothing returns string
    return ""
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    local trigger t = CreateTrigger()
    call FF_E2E_Begin("transmute_leaverbase")
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SPELL_EFFECT)
    call TriggerAddAction(t, function FF_E2E_LbOnSpell)
    // both possible humans get a hero in the tavern area (the map's AFK kick removes a human without one)
    set FF_E2E_lbHero = CreateUnit(Player(0), 'N01C', -2600.0, -300.0, 0.0)
    call CreateUnit(Player(3), 'H005', -2600.0, -300.0, 0.0)
    call FF_E2E_After(3.0, function FF_E2E_LbSetup)
    set t = null
endfunction
