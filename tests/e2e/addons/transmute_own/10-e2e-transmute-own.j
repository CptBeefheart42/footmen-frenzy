// e2e scenario "transmute_own" (main and Solo, exploratory, not in E2E_SUITE): the multiplayer Transmute crash with
// the CLIENT as the owner of the targets (in a live game the owner is a human; in the other transmute scenarios a
// computer). The client sits in slot 4 on main (team 2; slots 5 and 6 drop out first) and in slot 5 on Solo. Three
// computer Alchemists cast at once on three unpaused footmen of the client, 140 / 280 / 420 away; 0.3 s after the
// casts' effect the client drops out, the way FF_E2E_OWN_CASE says:
//   destroyed  its base falls (the map kills and removes its units; main does not defeat the player)
//   leave      RemovePlayer on the client itself, no defeat dialog (a dialog would pause the single-player game)
// Then a `tick` row every 2 s for 20 s, END. A crash leaves `loss` as the last record.

globals
    constant string FF_E2E_OWN_CASE = "destroyed"
    unit array FF_E2E_owCaster
    unit array FF_E2E_owTarget
    integer FF_E2E_owSide = 0
    integer FF_E2E_owTicks = 0
    integer FF_E2E_owTries = 0
    integer FF_E2E_owEffects = 0
    boolean FF_E2E_owArmed = false
endglobals

function FF_E2E_OwTargets takes nothing returns string
    local string s = ""
    local integer i = 0
    loop
        exitwhen i > 2
        set s = s + ",t" + I2S(i) + "=" + FF_E2E_Bool(FF_UnitAlive(FF_E2E_owTarget[i])) + FF_E2E_Bool(GetUnitTypeId(FF_E2E_owTarget[i]) != 0)
        set i = i + 1
    endloop
    return s
endfunction

function FF_E2E_OwTick takes nothing returns nothing
    set FF_E2E_owTicks = FF_E2E_owTicks + 1
    call FF_E2E_Row("tick,n=" + I2S(FF_E2E_owTicks) + ",t=" + I2S(FF_E2E_Now()) + ",active=" + FF_E2E_Bool(udg_player_active[FF_E2E_owSide]) + ",state=" + FF_E2E_State(Player(FF_E2E_owSide - 1)) + FF_E2E_OwTargets())
    if FF_E2E_owTicks >= 10 then
        call FF_E2E_Done()
        return
    endif
    call FF_E2E_After(2.0, function FF_E2E_OwTick)
endfunction

function FF_E2E_OwLoss takes nothing returns nothing
    local unit b = udg_base[FF_E2E_owSide]
    call FF_E2E_Row("loss,case=" + FF_E2E_OWN_CASE + ",side=" + I2S(FF_E2E_owSide) + ",effects=" + I2S(FF_E2E_owEffects) + ",t=" + I2S(FF_E2E_Now()) + FF_E2E_OwTargets())
    if FF_E2E_OWN_CASE == "destroyed" then
        call SetUnitInvulnerable(b, false)
        call FF_E2E_Kill(FF_E2E_owCaster[0], b)
    else
        call RemovePlayer(Player(FF_E2E_owSide - 1), PLAYER_GAME_RESULT_DEFEAT)
    endif
    call FF_E2E_Row("lost,active=" + FF_E2E_Bool(udg_player_active[FF_E2E_owSide]) + ",state=" + FF_E2E_State(Player(FF_E2E_owSide - 1)) + FF_E2E_OwTargets())
    call FF_E2E_After(2.0, function FF_E2E_OwTick)
    set b = null
endfunction

function FF_E2E_OwOnSpell takes nothing returns nothing
    if GetSpellAbilityId() != 'ANtm' then
        return
    endif
    set FF_E2E_owEffects = FF_E2E_owEffects + 1
    if FF_E2E_owArmed then
        set FF_E2E_owArmed = false
        call FF_E2E_After(0.3, function FF_E2E_OwLoss)
    endif
endfunction

function FF_E2E_OwOrder takes nothing returns nothing
    local integer i = 0
    local integer ok = 0
    loop
        exitwhen i > 2
        call UnitResetCooldown(FF_E2E_owCaster[i])
        call SetUnitState(FF_E2E_owCaster[i], UNIT_STATE_MANA, GetUnitState(FF_E2E_owCaster[i], UNIT_STATE_MAX_MANA))
        if IssueTargetOrder(FF_E2E_owCaster[i], "transmute", FF_E2E_owTarget[i]) then
            set ok = ok + 1
        endif
        set i = i + 1
    endloop
    set FF_E2E_owTries = FF_E2E_owTries + 1
    if ok < 3 and FF_E2E_owTries < 10 then
        call FF_E2E_After(1.0, function FF_E2E_OwOrder)
        return
    endif
    call FF_E2E_Row("cast,ordered=" + I2S(ok) + ",tries=" + I2S(FF_E2E_owTries))
endfunction

function FF_E2E_OwCast takes nothing returns nothing
    local integer i = 0
    call FF_E2E_Row("allies,t=" + I2S(FF_E2E_Now()) + ",active5=" + FF_E2E_Bool(udg_player_active[5]) + ",state5=" + FF_E2E_State(Player(4)) + ",active6=" + FF_E2E_Bool(udg_player_active[6]))
    loop
        exitwhen i > 2
        call SetUnitInvulnerable(FF_E2E_owCaster[i], true)
        call SetHeroLevel(FF_E2E_owCaster[i], 6, false)
        call SelectHeroSkill(FF_E2E_owCaster[i], 'ANtm')
        call SetUnitPosition(FF_E2E_owCaster[i], 0.0, -256.0 + 600.0 * (i - 1))
        set FF_E2E_owTarget[i] = CreateUnit(Player(FF_E2E_owSide - 1), 'hfoo', GetUnitX(FF_E2E_owCaster[i]) + 140.0 * (i + 1), GetUnitY(FF_E2E_owCaster[i]), 180.0)
        call IssueImmediateOrder(FF_E2E_owTarget[i], "holdposition")
        set i = i + 1
    endloop
    set FF_E2E_owArmed = true
    call FF_E2E_OwOrder()
endfunction

// Main: the client's allies (slots 5, 6) drop out first, so the client is its team's last player.
function FF_E2E_OwAlly takes nothing returns nothing
    local integer n = 5 + FF_E2E_owTicks
    local unit b = udg_base[n]
    call SetUnitInvulnerable(b, false)
    call FF_E2E_Kill(FF_E2E_owCaster[0], b)
    set b = null
    set FF_E2E_owTicks = FF_E2E_owTicks + 1
    if FF_E2E_owTicks < 2 then
        call FF_E2E_After(3.0, function FF_E2E_OwAlly)
        return
    endif
    set FF_E2E_owTicks = 0
    call FF_E2E_After(3.0, function FF_E2E_OwCast)
endfunction

function FF_E2E_OwStart takes nothing returns nothing
    if FF_E2E_owSide == 4 then
        call FF_E2E_OwAlly()
    else
        call FF_E2E_OwCast()
    endif
endfunction

function FF_E2E_HostClick takes nothing returns string
    return ""
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    local trigger t = CreateTrigger()
    local integer i = 0
    local integer array owner
    call FF_E2E_Begin("transmute_own")
    set FF_E2E_owSide = GetPlayerId(GetLocalPlayer()) + 1
    // the casters: team 1 on main, the other three seats on Solo
    if FF_E2E_owSide == 4 then
        set owner[0] = 0
        set owner[1] = 1
        set owner[2] = 2
    else
        set owner[0] = 0
        set owner[1] = 7
        set owner[2] = 11
    endif
    loop
        exitwhen i > 2
        set FF_E2E_owCaster[i] = CreateUnit(Player(owner[i]), 'N01C', -2600.0, -300.0, 0.0)
        set i = i + 1
    endloop
    // the client's hero (the map's AFK kick would remove a client without one)
    call CreateUnit(Player(FF_E2E_owSide - 1), 'H005', -2600.0, -300.0, 0.0)
    call TriggerRegisterAnyUnitEventBJ(t, EVENT_PLAYER_UNIT_SPELL_EFFECT)
    call TriggerAddAction(t, function FF_E2E_OwOnSpell)
    call FF_E2E_After(3.0, function FF_E2E_OwStart)
    set t = null
endfunction
