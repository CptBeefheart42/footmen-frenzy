// e2e scenario "transmute_mp" (main, exploratory, two clients over LAN; not in E2E_SUITE): the multiplayer
// Transmute crash. Client 1 (slot 1, Player 0) has the Alchemist; client 2 (slot 4, Player 3) owns the target and
// is the last player of team 2 (slots 5 and 6 are destroyed first). The target runs away faster than the projectile
// (522 against 380), as players do, so the projectile chases it; `inflight` is written when the cast takes effect:
//   leave      the runner kills client 2 (a real disconnect) during the chase
//   destroyed  slot 4's base falls 2 s after the cast; client 2 stays in the game
// Then a `tick` row every second for 30 s (the target, slot 4's state), END. A crash leaves the last tick.

globals
    constant string FF_E2E_MP_CASE = "leave"
    unit FF_E2E_mpHero = null
    unit FF_E2E_mpTarget = null
    integer FF_E2E_mpTicks = 0
    integer FF_E2E_mpTries = 0
endglobals

function FF_E2E_MpState takes nothing returns string
    return "active4=" + FF_E2E_Bool(udg_player_active[4]) + ",state4=" + FF_E2E_State(Player(3)) + ",target=" + FF_E2E_Bool(FF_UnitAlive(FF_E2E_mpTarget)) + FF_E2E_Bool(GetUnitTypeId(FF_E2E_mpTarget) != 0) + "@" + I2S(R2I(GetUnitX(FF_E2E_mpTarget) - GetUnitX(FF_E2E_mpHero))) + ",hits=" + I2S(FF_st_tmHits[1]) + ",denied=" + I2S(FF_st_tmDenied[1])
endfunction

function FF_E2E_MpTick takes nothing returns nothing
    set FF_E2E_mpTicks = FF_E2E_mpTicks + 1
    call FF_E2E_Row("tick,n=" + I2S(FF_E2E_mpTicks) + ",t=" + I2S(FF_E2E_Now()) + "," + FF_E2E_MpState())
    if FF_E2E_mpTicks >= 30 then
        call FF_E2E_Done()
        return
    endif
    call FF_E2E_After(1.0, function FF_E2E_MpTick)
endfunction

function FF_E2E_MpDestroy takes nothing returns nothing
    call SetUnitInvulnerable(udg_base[4], false)
    call FF_E2E_Kill(FF_E2E_mpHero, udg_base[4])
    call FF_E2E_Row("loss,case=destroyed,t=" + I2S(FF_E2E_Now()) + "," + FF_E2E_MpState())
endfunction

function FF_E2E_MpOnSpell takes nothing returns nothing
    if GetTriggerUnit() != FF_E2E_mpHero or GetSpellAbilityId() != 'ANtm' then
        return
    endif
    call IssuePointOrder(FF_E2E_mpTarget, "move", GetUnitX(FF_E2E_mpTarget) + 1500.0, GetUnitY(FF_E2E_mpTarget))
    call FF_E2E_Row("inflight,case=" + FF_E2E_MP_CASE + ",t=" + I2S(FF_E2E_Now()) + "," + FF_E2E_MpState())
    if FF_E2E_MP_CASE == "destroyed" then
        call FF_E2E_After(2.0, function FF_E2E_MpDestroy)
    endif
    call FF_E2E_After(1.0, function FF_E2E_MpTick)
endfunction

function FF_E2E_MpOrder takes nothing returns nothing
    local boolean ok
    call UnitResetCooldown(FF_E2E_mpHero)
    call SetUnitState(FF_E2E_mpHero, UNIT_STATE_MANA, GetUnitState(FF_E2E_mpHero, UNIT_STATE_MAX_MANA))
    set ok = IssueTargetOrder(FF_E2E_mpHero, "transmute", FF_E2E_mpTarget)
    set FF_E2E_mpTries = FF_E2E_mpTries + 1
    if not ok and FF_E2E_mpTries < 10 then
        call FF_E2E_After(1.0, function FF_E2E_MpOrder)
        return
    endif
    call FF_E2E_Row("cast,order=" + FF_E2E_Bool(ok) + ",tries=" + I2S(FF_E2E_mpTries) + ",t=" + I2S(FF_E2E_Now()))
endfunction

function FF_E2E_MpCast takes nothing returns nothing
    call FF_E2E_Row("allies,t=" + I2S(FF_E2E_Now()) + ",active5=" + FF_E2E_Bool(udg_player_active[5]) + ",active6=" + FF_E2E_Bool(udg_player_active[6]) + ",slot4=" + FF_E2E_State(Player(3)) + "," + FF_E2E_Ctrl(Player(3)))
    set FF_E2E_mpTarget = CreateUnit(Player(3), 'hfoo', GetUnitX(FF_E2E_mpHero) + 400.0, GetUnitY(FF_E2E_mpHero), 180.0)
    call SetUnitMoveSpeed(FF_E2E_mpTarget, 522.0)
    call IssueImmediateOrder(FF_E2E_mpTarget, "holdposition")
    call FF_E2E_MpOrder()
endfunction

function FF_E2E_MpAlly6 takes nothing returns nothing
    call SetUnitInvulnerable(udg_base[6], false)
    call FF_E2E_Kill(FF_E2E_mpHero, udg_base[6])
    call FF_E2E_After(3.0, function FF_E2E_MpCast)
endfunction

function FF_E2E_MpSetup takes nothing returns nothing
    call FF_E2E_Row("hero,slot1=" + FF_E2E_Bool(udg_herO[1] == FF_E2E_mpHero) + ",slot4=" + FF_us_Id2S(GetUnitTypeId(udg_herO[4])))
    call SetUnitInvulnerable(FF_E2E_mpHero, true)
    call SetHeroLevel(FF_E2E_mpHero, 6, false)
    call SelectHeroSkill(FF_E2E_mpHero, 'ANtm')
    call SetUnitPosition(FF_E2E_mpHero, 0.0, -256.0)
    call SetUnitInvulnerable(udg_base[5], false)
    call FF_E2E_Kill(FF_E2E_mpHero, udg_base[5])
    call FF_E2E_After(3.0, function FF_E2E_MpAlly6)
endfunction

function FF_E2E_HostClick takes nothing returns string
    return ""
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    local trigger t = CreateTrigger()
    call FF_E2E_Begin("transmute_mp")
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SPELL_EFFECT)
    call TriggerAddAction(t, function FF_E2E_MpOnSpell)
    // both humans get a hero in the tavern area (the map's AFK kick removes a human without one)
    set FF_E2E_mpHero = CreateUnit(Player(0), 'N01C', -2600.0, -300.0, 0.0)
    call CreateUnit(Player(3), 'H005', -2600.0, -300.0, 0.0)
    call FF_E2E_After(3.0, function FF_E2E_MpSetup)
    set t = null
endfunction
