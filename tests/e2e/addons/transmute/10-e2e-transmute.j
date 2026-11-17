// Shared script of the e2e scenarios "transmute_destroyed" and "transmute_left" (main and Solo): a Transmute
// projectile is in the air when the side of its target's owner drops out of the game — destroyed (its base falls)
// or left (the map's own kick: defeat, then its leaver handling). Each scenario defines FF_E2E_TmCase. A crash of
// the client ends the run early (tests/e2e/run.py writes crash.txt), so the two losses are separate runs.
// In multiplayer these steps crash every client when the target's owner is a human whose client leaves; single
// player can't do that (the owner here is a computer), and the game survives them.
// The client is slot 1 with the Alchemist (N01C, Transmute: a projectile, 400/s). The target side T is the last
// player of its team: slot 4 on main (its allies, slots 5 and 6, drop out first, the same way), slot 5 on Solo.
//   t~3      slot 1's hero, created in the tavern area (the map's TP_hero makes it slot 1's hero), at hero level 6
//            with Transmute learned, at the empty map centre
//   main     T's allies drop out: `allies,..`
//   deny     the control: a Transmute on a T footman, which T's own footman kills while the projectile flies
//            (no crash in live games): `deny,..`
//   loss     a Transmute on another T footman; while the projectile flies, T drops out: `loss,..`
//   +30 s    a `tick` row every 5 s (the map's unit removal of the side: at once on main, after ~20 s on Solo),
//            then the state: `after,..`, END

globals
    unit FF_E2E_tlHero = null
    unit FF_E2E_tlTarget = null
    unit FF_E2E_tlKiller = null
    integer FF_E2E_tlSide = 0
    integer FF_E2E_tlTries = 0
    integer FF_E2E_tlTicks = 0
    boolean FF_E2E_tlDeny = true
endglobals

// Whether slot n is still in the game for the map (player_active) and its slot state.
function FF_E2E_TlSlot takes integer n returns string
    return "active" + I2S(n) + "=" + FF_E2E_Bool(udg_player_active[n]) + ",state" + I2S(n) + "=" + FF_E2E_State(Player(n - 1))
endfunction

// The Transmute counters of the stats addon: slot 1's casts, hits, denied and the side's saves.
function FF_E2E_TlCounters takes nothing returns string
    return "casts=" + I2S(FF_st_tmCasts[1]) + ",hits=" + I2S(FF_st_tmHits[1]) + ",denied=" + I2S(FF_st_tmDenied[1]) + ",saves=" + I2S(FF_st_tmSaves[FF_E2E_tlSide])
endfunction

// Slot n drops out the way the case says: its base is destroyed by slot 1's hero, or the map's own kick removes it.
function FF_E2E_TlDropOut takes integer n returns nothing
    local unit b = udg_base[n]
    if FF_E2E_TmCase() == "destroyed" then
        // bases may be invulnerable before the mass; the kill must be a real one the map's triggers see
        call SetUnitInvulnerable(b, false)
        call FF_E2E_Kill(FF_E2E_tlHero, b)
    else
        set FF_afk_slot = n
        call TriggerExecute(FF_afk_kickHook)
    endif
    set b = null
endfunction

function FF_E2E_TlAfter takes nothing returns nothing
    call FF_E2E_Row("after,t=" + I2S(FF_E2E_Now()) + ",removed=" + FF_E2E_Bool(GetUnitTypeId(FF_E2E_tlTarget) == 0) + ",alive=" + FF_E2E_Bool(FF_UnitAlive(FF_E2E_tlTarget)) + ",hero=" + FF_E2E_Bool(FF_UnitAlive(FF_E2E_tlHero)) + "," + FF_E2E_TlSlot(FF_E2E_tlSide) + "," + FF_E2E_TlCounters())
    call FF_E2E_Done()
endfunction

function FF_E2E_TlTick takes nothing returns nothing
    set FF_E2E_tlTicks = FF_E2E_tlTicks + 1
    call FF_E2E_Row("tick,n=" + I2S(FF_E2E_tlTicks) + ",t=" + I2S(FF_E2E_Now()))
    if FF_E2E_tlTicks >= 6 then
        call FF_E2E_TlAfter()
        return
    endif
    call FF_E2E_After(5.0, function FF_E2E_TlTick)
endfunction

// The projectile is in the air (the cast's effect was 0.4 s ago, the flight takes ~1 s): the side drops out.
function FF_E2E_TlLoss takes nothing returns nothing
    local boolean alive = FF_UnitAlive(FF_E2E_tlTarget)
    call FF_E2E_TlDropOut(FF_E2E_tlSide)
    call FF_E2E_Row("loss,case=" + FF_E2E_TmCase() + ",side=" + I2S(FF_E2E_tlSide) + ",inflight=" + FF_E2E_Bool(alive) + ",t=" + I2S(FF_E2E_Now()) + "," + FF_E2E_TlSlot(FF_E2E_tlSide) + ",base=" + FF_E2E_Bool(FF_UnitAlive(udg_base[FF_E2E_tlSide])))
    call FF_E2E_After(5.0, function FF_E2E_TlTick)
endfunction

// The control: the side's own footman kills the target while the projectile flies (a deny).
function FF_E2E_TlDenyKill takes nothing returns nothing
    call FF_E2E_Kill(FF_E2E_tlKiller, FF_E2E_tlTarget)
endfunction

function FF_E2E_TlOnSpell takes nothing returns nothing
    if GetTriggerUnit() != FF_E2E_tlHero or GetSpellAbilityId() != 'ANtm' then
        return
    endif
    if FF_E2E_tlDeny then
        call FF_E2E_After(0.4, function FF_E2E_TlDenyKill)
    else
        call FF_E2E_After(0.4, function FF_E2E_TlLoss)
    endif
endfunction

// A footman of the side, paused (no wandering, no attacks), at distance d east of the hero.
function FF_E2E_TlFootman takes real d returns unit
    local unit u = CreateUnit(Player(FF_E2E_tlSide - 1), 'hfoo', GetUnitX(FF_E2E_tlHero) + d, GetUnitY(FF_E2E_tlHero), 180.0)
    call PauseUnit(u, true)
    return u
endfunction

// The cast order, again every second while the hero refuses it.
function FF_E2E_TlOrder takes nothing returns nothing
    local boolean ok
    call UnitResetCooldown(FF_E2E_tlHero)
    call SetUnitState(FF_E2E_tlHero, UNIT_STATE_MANA, GetUnitState(FF_E2E_tlHero, UNIT_STATE_MAX_MANA))
    set ok = IssueTargetOrder(FF_E2E_tlHero, "transmute", FF_E2E_tlTarget)
    set FF_E2E_tlTries = FF_E2E_tlTries + 1
    if not ok and FF_E2E_tlTries < 10 then
        call FF_E2E_After(1.0, function FF_E2E_TlOrder)
        return
    endif
    call FF_E2E_Row("cast,deny=" + FF_E2E_Bool(FF_E2E_tlDeny) + ",order=" + FF_E2E_Bool(ok) + ",tries=" + I2S(FF_E2E_tlTries) + ",t=" + I2S(FF_E2E_Now()))
    if not ok then
        call FF_E2E_Done()
    endif
endfunction

function FF_E2E_TlCast takes nothing returns nothing
    set FF_E2E_tlTarget = FF_E2E_TlFootman(350.0)
    set FF_E2E_tlTries = 0
    call FF_E2E_TlOrder()
endfunction

function FF_E2E_TlLossCast takes nothing returns nothing
    call FF_E2E_Row("deny,t=" + I2S(FF_E2E_Now()) + ",dead=" + FF_E2E_Bool(not FF_UnitAlive(FF_E2E_tlTarget)) + "," + FF_E2E_TlCounters())
    set FF_E2E_tlDeny = false
    call FF_E2E_TlCast()
endfunction

function FF_E2E_TlDenyCast takes nothing returns nothing
    set FF_E2E_tlKiller = FF_E2E_TlFootman(450.0)
    call FF_E2E_TlCast()
    // the projectile lands within ~1 s; the stats addon resolves the cast on the death
    call FF_E2E_After(6.0, function FF_E2E_TlLossCast)
endfunction

function FF_E2E_TlAllies takes nothing returns nothing
    call FF_E2E_Row("allies,t=" + I2S(FF_E2E_Now()) + "," + FF_E2E_TlSlot(5) + "," + FF_E2E_TlSlot(6) + "," + FF_E2E_TlSlot(4))
    call FF_E2E_TlDenyCast()
endfunction

function FF_E2E_TlAlly6 takes nothing returns nothing
    call FF_E2E_TlDropOut(6)
    call FF_E2E_After(3.0, function FF_E2E_TlAllies)
endfunction

function FF_E2E_TlHero takes nothing returns nothing
    call FF_E2E_Row("hero,slot1=" + FF_us_Id2S(GetUnitTypeId(udg_herO[1])) + ",ours=" + FF_E2E_Bool(udg_herO[1] == FF_E2E_tlHero) + ",side=" + I2S(FF_E2E_tlSide))
    call SetUnitInvulnerable(FF_E2E_tlHero, true)
    // Transmute is the Alchemist's ultimate (hero level 6)
    call SetHeroLevel(FF_E2E_tlHero, 6, false)
    call SelectHeroSkill(FF_E2E_tlHero, 'ANtm')
    call SetUnitPosition(FF_E2E_tlHero, 0.0, -256.0)
    call FF_E2E_Row("skill,ANtm=" + I2S(GetUnitAbilityLevel(FF_E2E_tlHero, 'ANtm')))
    if FF_E2E_tlSide == 4 then
        call FF_E2E_TlDropOut(5)
        call FF_E2E_After(3.0, function FF_E2E_TlAlly6)
    else
        call FF_E2E_TlDenyCast()
    endif
endfunction

function FF_E2E_HostClick takes nothing returns string
    return ""
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    local trigger t = CreateTrigger()
    call FF_E2E_Begin("transmute_" + FF_E2E_TmCase())
    // main: slot 4, the first of team 2; Solo (seats 1, 5, 8, 12): slot 5
    if GetPlayerSlotState(Player(3)) == PLAYER_SLOT_STATE_PLAYING then
        set FF_E2E_tlSide = 4
    else
        set FF_E2E_tlSide = 5
    endif
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SPELL_EFFECT)
    call TriggerAddAction(t, function FF_E2E_TlOnSpell)
    set FF_E2E_tlHero = CreateUnit(Player(0), 'N01C', -2600.0, -300.0, 0.0)
    call FF_E2E_After(3.0, function FF_E2E_TlHero)
    set t = null
endfunction
