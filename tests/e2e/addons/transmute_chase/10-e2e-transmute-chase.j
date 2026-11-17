// e2e scenario "transmute_chase" (main and Solo, exploratory, not in E2E_SUITE): the multiplayer Transmute crash as
// players trigger it. The target runs away faster than the projectile (footmen at 522 move speed, the projectile at
// 380), so the projectile chases a unit it can't reach, and the target's side drops out during the chase. Three
// Alchemists of team 1 cast at once on three footmen of the side; each target runs east as soon as its cast takes
// effect, and FF_E2E_SW_DELAY s later the side drops out. Two losses per run:
//   main  slot 4 destroyed (its allies 5, 6 destroyed first), then slot 7 left (8, 9 kicked first)
//   Solo  slot 5 destroyed, then slot 8 left
// `loss` is recorded before each loss, `survived` 10 s after.

globals
    constant real FF_E2E_SW_DELAY = 2.5
    unit array FF_E2E_swCaster
    unit array FF_E2E_swTarget
    integer FF_E2E_swWave = 0
    integer FF_E2E_swSide = 0
    integer FF_E2E_swEffects = 0
    integer FF_E2E_swTries = 0
    boolean FF_E2E_swArmed = false
    code FF_E2E_swNext = null
endglobals

function FF_E2E_SwMain takes nothing returns boolean
    return GetPlayerSlotState(Player(3)) == PLAYER_SLOT_STATE_PLAYING
endfunction

// Wave n's side: its last player and how it drops out.
function FF_E2E_SwSideOf takes integer n returns integer
    if FF_E2E_SwMain() then
        if n == 1 then
            return 4
        endif
        return 7
    endif
    if n == 1 then
        return 5
    endif
    return 8
endfunction

function FF_E2E_SwDestroyed takes integer n returns boolean
    return n == 1
endfunction

function FF_E2E_SwDropOut takes integer slot, boolean destroyed returns nothing
    local unit b = udg_base[slot]
    if destroyed then
        call SetUnitInvulnerable(b, false)
        call FF_E2E_Kill(FF_E2E_swCaster[0], b)
    else
        set FF_afk_slot = slot
        call TriggerExecute(FF_afk_kickHook)
    endif
    set b = null
endfunction

function FF_E2E_SwTargets takes nothing returns string
    local string s = ""
    local integer i = 0
    loop
        exitwhen i > 2
        set s = s + ",t" + I2S(i) + "=" + FF_E2E_Bool(FF_UnitAlive(FF_E2E_swTarget[i])) + FF_E2E_Bool(GetUnitTypeId(FF_E2E_swTarget[i]) != 0) + "@" + I2S(R2I(GetUnitX(FF_E2E_swTarget[i]) - GetUnitX(FF_E2E_swCaster[i])))
        set i = i + 1
    endloop
    return s
endfunction

function FF_E2E_SwSurvived takes nothing returns nothing
    call FF_E2E_Row("survived,wave=" + I2S(FF_E2E_swWave) + ",t=" + I2S(FF_E2E_Now()) + FF_E2E_SwTargets() + ",casts=" + I2S(FF_st_tmCasts[1]) + ",hits=" + I2S(FF_st_tmHits[1]))
    if FF_E2E_swWave >= 2 then
        call FF_E2E_Done()
        return
    endif
    // FF_E2E_SwNextWave is defined below (it leads here): reached through a code global
    call FF_E2E_After(1.0, FF_E2E_swNext)
endfunction

function FF_E2E_SwLoss takes nothing returns nothing
    call FF_E2E_Row("loss,wave=" + I2S(FF_E2E_swWave) + ",side=" + I2S(FF_E2E_swSide) + ",destroyed=" + FF_E2E_Bool(FF_E2E_SwDestroyed(FF_E2E_swWave)) + ",effects=" + I2S(FF_E2E_swEffects) + ",t=" + I2S(FF_E2E_Now()) + FF_E2E_SwTargets())
    call FF_E2E_SwDropOut(FF_E2E_swSide, FF_E2E_SwDestroyed(FF_E2E_swWave))
    call FF_E2E_Row("lost,wave=" + I2S(FF_E2E_swWave) + ",active=" + FF_E2E_Bool(udg_player_active[FF_E2E_swSide]) + ",state=" + FF_E2E_State(Player(FF_E2E_swSide - 1)) + FF_E2E_SwTargets())
    call FF_E2E_After(10.0, function FF_E2E_SwSurvived)
endfunction

// The first effect of the wave arms the loss; the other casters' effects come in the same moment.
function FF_E2E_SwOnSpell takes nothing returns nothing
    if GetSpellAbilityId() != 'ANtm' then
        return
    endif
    set FF_E2E_swEffects = FF_E2E_swEffects + 1
    // the target flees: faster than the projectile, which keeps chasing it
    call IssuePointOrder(GetSpellTargetUnit(), "move", GetUnitX(GetSpellTargetUnit()) + 1500.0, GetUnitY(GetSpellTargetUnit()))
    if FF_E2E_swArmed then
        set FF_E2E_swArmed = false
        call FF_E2E_After(FF_E2E_SW_DELAY, function FF_E2E_SwLoss)
    endif
endfunction

function FF_E2E_SwOrder takes nothing returns nothing
    local integer i = 0
    local integer ok = 0
    loop
        exitwhen i > 2
        call UnitResetCooldown(FF_E2E_swCaster[i])
        call SetUnitState(FF_E2E_swCaster[i], UNIT_STATE_MANA, GetUnitState(FF_E2E_swCaster[i], UNIT_STATE_MAX_MANA))
        if IssueTargetOrder(FF_E2E_swCaster[i], "transmute", FF_E2E_swTarget[i]) then
            set ok = ok + 1
        endif
        set i = i + 1
    endloop
    set FF_E2E_swTries = FF_E2E_swTries + 1
    if ok < 3 and FF_E2E_swTries < 10 then
        call FF_E2E_After(1.0, function FF_E2E_SwOrder)
        return
    endif
    call FF_E2E_Row("cast,wave=" + I2S(FF_E2E_swWave) + ",ordered=" + I2S(ok) + ",tries=" + I2S(FF_E2E_swTries))
endfunction

function FF_E2E_SwCast takes nothing returns nothing
    local integer i = 0
    local real x
    local real y
    loop
        exitwhen i > 2
        call SetUnitPosition(FF_E2E_swCaster[i], 0.0, -256.0 + 600.0 * (i - 1))
        set x = GetUnitX(FF_E2E_swCaster[i]) + 140.0 * (i + 1)
        set y = GetUnitY(FF_E2E_swCaster[i])
        set FF_E2E_swTarget[i] = CreateUnit(Player(FF_E2E_swSide - 1), 'hfoo', x, y, 180.0)
        call SetUnitMoveSpeed(FF_E2E_swTarget[i], 522.0)
        call IssueImmediateOrder(FF_E2E_swTarget[i], "holdposition")
        set i = i + 1
    endloop
    set FF_E2E_swEffects = 0
    set FF_E2E_swTries = 0
    set FF_E2E_swArmed = true
    call FF_E2E_SwOrder()
endfunction

function FF_E2E_SwAllies takes nothing returns nothing
    call FF_E2E_Row("allies,wave=" + I2S(FF_E2E_swWave) + ",side=" + I2S(FF_E2E_swSide) + ",a1=" + FF_E2E_Bool(udg_player_active[FF_E2E_swSide + 1]) + FF_E2E_State(Player(FF_E2E_swSide)) + ",a2=" + FF_E2E_Bool(udg_player_active[FF_E2E_swSide + 2]) + FF_E2E_State(Player(FF_E2E_swSide + 1)))
    call FF_E2E_SwCast()
endfunction

function FF_E2E_SwAlly2 takes nothing returns nothing
    call FF_E2E_SwDropOut(FF_E2E_swSide + 2, FF_E2E_SwDestroyed(FF_E2E_swWave))
    call FF_E2E_After(3.0, function FF_E2E_SwAllies)
endfunction

function FF_E2E_SwNextWave takes nothing returns nothing
    set FF_E2E_swWave = FF_E2E_swWave + 1
    set FF_E2E_swSide = FF_E2E_SwSideOf(FF_E2E_swWave)
    if FF_E2E_SwMain() then
        call FF_E2E_SwDropOut(FF_E2E_swSide + 1, FF_E2E_SwDestroyed(FF_E2E_swWave))
        call FF_E2E_After(3.0, function FF_E2E_SwAlly2)
    else
        call FF_E2E_SwCast()
    endif
endfunction

function FF_E2E_SwSetup takes nothing returns nothing
    local integer i = 0
    call FF_E2E_Row("hero,ours=" + FF_E2E_Bool(udg_herO[1] == FF_E2E_swCaster[0]))
    loop
        exitwhen i > 2
        call SetUnitInvulnerable(FF_E2E_swCaster[i], true)
        call SetHeroLevel(FF_E2E_swCaster[i], 6, false)
        call SelectHeroSkill(FF_E2E_swCaster[i], 'ANtm')
        set i = i + 1
    endloop
    call FF_E2E_SwNextWave()
endfunction

function FF_E2E_HostClick takes nothing returns string
    return ""
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    local trigger t = CreateTrigger()
    call FF_E2E_Begin("transmute_chase")
    set FF_E2E_swNext = function FF_E2E_SwNextWave
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SPELL_EFFECT)
    call TriggerAddAction(t, function FF_E2E_SwOnSpell)
    set FF_E2E_swCaster[0] = CreateUnit(Player(0), 'N01C', -2600.0, -300.0, 0.0)
    if FF_E2E_SwMain() then
        set FF_E2E_swCaster[1] = CreateUnit(Player(1), 'N01C', 0.0, 0.0, 0.0)
        set FF_E2E_swCaster[2] = CreateUnit(Player(2), 'N01C', 0.0, 0.0, 0.0)
    else
        set FF_E2E_swCaster[1] = CreateUnit(Player(0), 'N01C', 0.0, 0.0, 0.0)
        set FF_E2E_swCaster[2] = CreateUnit(Player(0), 'N01C', 0.0, 0.0, 0.0)
    endif
    call FF_E2E_After(3.0, function FF_E2E_SwSetup)
    set t = null
endfunction
