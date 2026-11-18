// e2e scenario "trade": gold between allies on the main map, each route in its own stats keys, with the client as
// player 1 (slot 1; slots 2-12 are computers — `slots` file). Waits for the map to allow autopool and resource
// trading (the pub timer, ~240s), then:
//   pool     -pool, the runner clicks the dialog's first ally (slot 2): slot 1's 1000 gold goes to slot 2; slot 1's
//            pool is switched off, slot 2 pools 400 back (set by script: a computer can't type -pool)
//   tribute  the Allies menu is opened (its button is disabled in a single-player game, so by BlzFrameClick), the
//            runner clicks slot 2's gold icon three times (100 each) and Accept (FF_E2E_TRADE_SEQ: real input,
//            fractions of the 4:3 UI area); the menu doesn't pause the game, so the scenario waits for the trade
// Each step records the score screen's gold given / received / mined (GetPlayerScore), the stats addon's pool
// counters and the gold of slots 1 and 2 (`trade,step=<name>,...`); at the end the stats rows are written.

globals
    // The runner's inputs once the script has opened the Allies menu: slot 2's gold icon three times, then Accept.
    // Fractions of the game's 4:3 UI area (tests/e2e/client.py ui_point), from a screenshot of the menu in a 1402x824
    // window: slot 2's gold icon (first row) at 883,170, Accept at 612,626.
    string FF_E2E_TRADE_SEQ = "wait 2; shot; tap 0.6657 0.2063; tap 0.6657 0.2063; tap 0.6657 0.2063; shot; tap 0.419 0.7597; wait 1; shot"
    integer FF_E2E_trWaited = 0
    // the gold of slots 1 and 2 one poll before (FF_E2E_TrTributeRead)
    integer FF_E2E_trGold1 = 0
    integer FF_E2E_trGold2 = 0
endglobals

function FF_E2E_TrGold takes integer slot returns integer
    return GetPlayerState(Player(slot - 1), PLAYER_STATE_RESOURCE_GOLD)
endfunction

function FF_E2E_TrSlot takes integer slot returns string
    local player p = Player(slot - 1)
    local string s = ",given" + I2S(slot) + "=" + I2S(GetPlayerScore(p, PLAYER_SCORE_GOLD_GIVEN)) + ",recv" + I2S(slot) + "=" + I2S(GetPlayerScore(p, PLAYER_SCORE_GOLD_RECEIVED)) + ",mined" + I2S(slot) + "=" + I2S(GetPlayerScore(p, PLAYER_SCORE_GOLD_MINED_TOTAL)) + ",out" + I2S(slot) + "=" + I2S(FF_st_poolOut[slot]) + ",in" + I2S(slot) + "=" + I2S(FF_st_poolIn[slot]) + ",gold" + I2S(slot) + "=" + I2S(FF_E2E_TrGold(slot))
    set p = null
    return s
endfunction

function FF_E2E_TrRecord takes string step returns nothing
    call FF_E2E_Row("trade,step=" + step + ",t=" + I2S(FF_E2E_Now()) + FF_E2E_TrSlot(1) + FF_E2E_TrSlot(2))
endfunction

// The Allies button and menu as the UI reports them (local frames: single player, so no desync).
function FF_E2E_TrFrames takes string when returns nothing
    local framehandle b = BlzGetFrameByName("UpperButtonBarAlliesButton", 0)
    local framehandle d = BlzGetFrameByName("AllianceDialog", 0)
    local string r = "frames,when=" + when + ",button=" + FF_E2E_Bool(b != null)
    if b != null then
        set r = r + ",enabled=" + FF_E2E_Bool(BlzFrameGetEnable(b)) + ",visible=" + FF_E2E_Bool(BlzFrameIsVisible(b))
    endif
    set r = r + ",dialog=" + FF_E2E_Bool(d != null)
    if d != null then
        set r = r + ",dvisible=" + FF_E2E_Bool(BlzFrameIsVisible(d)) + ",gold0=" + BlzFrameGetText(BlzGetFrameByName("GoldText", 0)) + ",gold1=" + BlzFrameGetText(BlzGetFrameByName("GoldText", 1))
    endif
    call FF_E2E_Row(r)
    set b = null
    set d = null
endfunction

// --- the end ---------------------------------------------------------------------------------------------------

function FF_E2E_TrFinish takes nothing returns nothing
    call FF_E2E_TrRecord("end")
    call FF_gr_RefreshStats()
    call FF_gr_Flush()
    call FF_E2E_Done()
endfunction

// --- tribute through the Allies menu ---------------------------------------------------------------------------

// Waits (up to 60s) for the trade the runner makes in the menu, polling every 0.05s: in the poll where slot 1's gold
// given goes up, the gold of both slots moves by the trade alone (income comes in whole seconds, and is recorded too).
function FF_E2E_TrTributeRead takes nothing returns nothing
    if GetPlayerScore(Player(0), PLAYER_SCORE_GOLD_GIVEN) == 0 and FF_E2E_trWaited < 1200 then
        set FF_E2E_trWaited = FF_E2E_trWaited + 1
        set FF_E2E_trGold1 = FF_E2E_TrGold(1)
        set FF_E2E_trGold2 = FF_E2E_TrGold(2)
        call FF_E2E_After(0.05, function FF_E2E_TrTributeRead)
        return
    endif
    call FF_E2E_Row("tradetick,dgold1=" + I2S(FF_E2E_TrGold(1) - FF_E2E_trGold1) + ",dgold2=" + I2S(FF_E2E_TrGold(2) - FF_E2E_trGold2))
    call FF_E2E_TrRecord("tribute")
    call FF_E2E_TrFrames("after")
    call FF_E2E_After(1.0, function FF_E2E_TrFinish)
endfunction

function FF_E2E_TrTribute takes nothing returns nothing
    call SetPlayerState(Player(0), PLAYER_STATE_RESOURCE_GOLD, 1000)
    call SetPlayerState(Player(1), PLAYER_STATE_RESOURCE_GOLD, 0)
    call FF_E2E_TrRecord("tribute0")
    call FF_E2E_Row("allies,locked=" + FF_E2E_Bool(IsMapFlagSet(MAP_LOCK_RESOURCE_TRADING)) + ",allies_only=" + FF_E2E_Bool(IsMapFlagSet(MAP_RESOURCE_TRADING_ALLIES_ONLY)) + ",ally2=" + FF_E2E_Bool(IsPlayerAlly(Player(0), Player(1))) + ",lock_alliances=" + FF_E2E_Bool(IsMapFlagSet(MAP_LOCK_ALLIANCE_CHANGES)) + ",alliances_hidden=" + FF_E2E_Bool(IsMapFlagSet(MAP_ALLIANCE_CHANGES_HIDDEN)))
    call FF_E2E_TrFrames("before")
    // single player disables the button (F11 does nothing); a click on it from the script still opens the menu
    call BlzFrameClick(BlzGetFrameByName("UpperButtonBarAlliesButton", 0))
    call FF_E2E_TrFrames("clicked")
    set FF_E2E_phase = FF_E2E_phase + 1
    call FF_E2E_PhaseFile("WAIT " + I2S(FF_E2E_phase) + " seq " + FF_E2E_TRADE_SEQ)
    set FF_E2E_trWaited = 0
    call FF_E2E_TrTributeRead()
endfunction

// --- -pool, there and back -------------------------------------------------------------------------------------

function FF_E2E_TrBackRead takes nothing returns nothing
    set udg_autopoolto[2] = 0
    call FF_E2E_TrRecord("back")
    call FF_E2E_After(3.0, function FF_E2E_TrTribute)
endfunction

function FF_E2E_TrBack takes nothing returns nothing
    set udg_autopoolto[1] = 0
    call FF_E2E_TrRecord("there")
    call SetPlayerState(Player(1), PLAYER_STATE_RESOURCE_GOLD, 400)
    set udg_autopoolto[2] = 1
    call FF_E2E_After(3.0, function FF_E2E_TrBackRead)
endfunction

// After -pool and the runner's click on the first ally button (the game is paused until then).
function FF_E2E_TrPool takes nothing returns nothing
    call FF_E2E_Ok()
    call FF_E2E_Row("pool,allowed=" + FF_E2E_Bool(udg_autopoool_allowed) + ",to=" + I2S(udg_autopoolto[1]) + ",threshold=" + I2S(udg_pool_threshold[1]))
    call FF_E2E_After(3.0, function FF_E2E_TrBack)
endfunction

function FF_E2E_TrWait takes nothing returns nothing
    if not udg_autopoool_allowed or IsMapFlagSet(MAP_LOCK_RESOURCE_TRADING) then
        set FF_E2E_trWaited = FF_E2E_trWaited + 2
        if FF_E2E_trWaited <= 400 then
            call FF_E2E_After(2.0, function FF_E2E_TrWait)
            return
        endif
        call FF_E2E_Row("wait,timeout=400")
    endif
    call SetPlayerState(Player(0), PLAYER_STATE_RESOURCE_GOLD, 1000)
    call SetPlayerState(Player(1), PLAYER_STATE_RESOURCE_GOLD, 0)
    call FF_E2E_TrRecord("start")
    call FF_E2E_WaitChatClick("-pool", "0.5 0.479", function FF_E2E_TrPool)
endfunction

// The host's game-type dialog: "Pub Game Default", the first of the main map's four buttons.
function FF_E2E_HostClick takes nothing returns string
    return "0.5 0.478"
endfunction

function FF_E2E_Scenario takes nothing returns nothing
    call FF_E2E_Begin("trade")
    call FF_E2E_Active()
    // a hero for the client (the map's tavern-area pick), or the AFK kick removes it after the mass
    call CreateUnit(Player(0), 'H005', -2600.0, -300.0, 0.0)
    call FF_E2E_After(2.0, function FF_E2E_TrWait)
endfunction
