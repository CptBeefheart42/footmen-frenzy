// e2e scenario "afk" (main and Solo): the AFK kick in the real client. The client is slot 1 (Player 0) and never
// picks a hero; the other seats are computers without heroes (never kicked: only human players are). The client is
// on the hosting-bot list (E2E_BOT), so the map starts in Pub mode without the host's dialog.
//   mass      the map's pre-mass countdown runs out (main 90 s, Solo 50 s): `mass,t=..`
//   +6 s      after the warning: still in the game, a screenshot of the warning (`seq-<n>-0.png`)
//   kick      15 s after the mass, once the gold pool is open (main Pub: the trading timer, 230 s after the game
//             started; Solo has no pool: +15 s): an action after the map addon's own kick (FF_afk_kickHook) records
//             the state the kick left, asks for a screenshot of the defeat dialog and ends the scenario. The dialog
//             pauses the single-player game, so nothing after the kick would run.

globals
    integer FF_E2E_afkWaited = 0
    integer FF_E2E_afkMass = 0
    integer FF_E2E_afkMassPoolIn = 0
endglobals

// player_active of the computer seats (slots 2-12 in the game), one 0/1 per seat.
function FF_E2E_AfkOthers takes nothing returns string
    local string s = ""
    local integer i = 2
    loop
        exitwhen i > 12
        if GetPlayerSlotState(Player(i - 1)) == PLAYER_SLOT_STATE_PLAYING then
            set s = s + FF_E2E_Bool(udg_player_active[i])
        endif
        set i = i + 1
    endloop
    return s
endfunction

function FF_E2E_AfkKicked takes nothing returns nothing
    call FF_E2E_Row("kicked,slot=" + I2S(FF_afk_slot) + ",t=" + I2S(FF_E2E_Now()) + ",after=" + I2S(FF_E2E_Now() - FF_E2E_afkMass) + ",dropped=" + FF_E2E_Bool(FF_gr_afk[1]) + ",participant=" + FF_E2E_Bool(FF_gr_participant[1]) + ",state=" + FF_E2E_State(Player(0)) + ",active=" + FF_E2E_Bool(udg_player_active[1]) + ",others=" + FF_E2E_AfkOthers() + ",poolin=" + I2S(FF_afk_PoolIn()))
    set FF_E2E_phase = FF_E2E_phase + 1
    call FF_E2E_PhaseFile("WAIT " + I2S(FF_E2E_phase) + " seq wait 1; shot")
    call FF_E2E_Done()
endfunction

function FF_E2E_AfkWarned takes nothing returns nothing
    call FF_E2E_Row("warned,t=" + I2S(FF_E2E_Now()) + ",afk=" + FF_E2E_Bool(FF_afk_IsAfk(1)) + ",dropped=" + FF_E2E_Bool(FF_gr_afk[1]) + ",active=" + FF_E2E_Bool(udg_player_active[1]))
    set FF_E2E_phase = FF_E2E_phase + 1
    call FF_E2E_PhaseFile("WAIT " + I2S(FF_E2E_phase) + " seq shot")
endfunction

function FF_E2E_AfkMassRow takes nothing returns nothing
    call FF_E2E_Row("mass,t=" + I2S(FF_E2E_afkMass) + ",hero=" + FF_E2E_Bool(udg_herO[1] != null) + ",poolin=" + I2S(FF_E2E_afkMassPoolIn))
endfunction

function FF_E2E_AfkWaitMass takes nothing returns nothing
    if not udg_mass_active then
        set FF_E2E_afkWaited = FF_E2E_afkWaited + 1
        if FF_E2E_afkWaited > 180 then
            call FF_E2E_Row("mass,timeout=180")
            call FF_E2E_Done()
            return
        endif
        call FF_E2E_After(1.0, function FF_E2E_AfkWaitMass)
        return
    endif
    set FF_E2E_afkMass = FF_E2E_Now()
    set FF_E2E_afkMassPoolIn = FF_afk_PoolIn()
    // the auto hero is created at the tavern when the mass starts; the map's tavern trigger makes it the slot's hero
    // a moment later, so the hero is read 3 s after the mass (t and poolin stay those of the mass itself)
    call FF_E2E_After(3.0, function FF_E2E_AfkMassRow)
    call FF_E2E_After(FF_AFK_WARN + 1.0, function FF_E2E_AfkWarned)
endfunction

function FF_E2E_HostClick takes nothing returns string
    return ""
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    call FF_E2E_Begin("afk")
    call TriggerAddAction(FF_afk_kickHook, function FF_E2E_AfkKicked)
    call FF_E2E_After(1.0, function FF_E2E_AfkWaitMass)
endfunction
