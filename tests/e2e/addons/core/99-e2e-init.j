// FF e2e test addon — start (last file: it calls the scenario, defined in between).

// Game time 3s: the host's dialog (if any) is answered by now.
function FF_E2E_Start takes nothing returns nothing
    call FF_E2E_PhaseFile("OK 0")
    call FF_E2E_Scenario()
endfunction

// Runs from main() after the map's own init. A map whose initialization trigger runs inside InitCustomTriggers
// (799X) has recorded the players' names (udg_orig_player_name) by then; the names set here replace those records.
function FF_E2E_Init takes nothing returns nothing
    local integer i = 0
    // The client (the one User slot): the e2e build's E2E_BOT name, also on its bot list (stage.py)
    if FF_E2E_ClientName() != "" then
        loop
            exitwhen i >= bj_MAX_PLAYER_SLOTS
            if GetPlayerController(Player(i)) == MAP_CONTROL_USER and GetPlayerSlotState(Player(i)) == PLAYER_SLOT_STATE_PLAYING then
                call SetPlayerName(Player(i), FF_E2E_ClientName())
            endif
            set i = i + 1
        endloop
        set i = 0
    endif
    // Computer slots get battletag-like names as long as real ones get (clan tag, 6-digit number): the league
    // keys players by battletag, and 12 of these don't fit into one Preload string (roster + roster_more).
    loop
        exitwhen i >= 12
        if GetPlayerController(Player(i)) == MAP_CONTROL_COMPUTER then
            if i < 9 then
                call SetPlayerName(Player(i), "(E2E)LongBattleTag0" + I2S(i + 1) + "#10000" + I2S(i + 1))
            else
                call SetPlayerName(Player(i), "(E2E)LongBattleTag" + I2S(i + 1) + "#1000" + I2S(i + 1))
            endif
        endif
        if udg_orig_player_name[i + 1] != null and udg_orig_player_name[i + 1] != "" then
            set udg_orig_player_name[i + 1] = GetPlayerName(Player(i))
        endif
        set i = i + 1
    endloop
    set i = 0
    set FF_E2E_chatTrig = CreateTrigger()
    loop
        exitwhen i >= bj_MAX_PLAYER_SLOTS
        call TriggerRegisterPlayerChatEvent(FF_E2E_chatTrig, Player(i), "", false)
        set i = i + 1
    endloop
    call TriggerAddAction(FF_E2E_chatTrig, function FF_E2E_OnChat)
    // the client as the host: the map's game-type dialog (shown at 1s) pauses the game until it is answered. A
    // client on the hosting-bot list never sees it (the map picks Pub mode itself, see FF_hostBotGame).
    if GetLocalPlayer() == Player(0) and GetPlayerController(Player(0)) == MAP_CONTROL_USER and FF_E2E_HostClick() != "" and not FF_HostBotInGame() then
        call FF_E2E_PhaseFile("WAIT 0 click " + FF_E2E_HostClick())
    endif
    // after the addons' own boot (FF_Init: 0.10s) and the map's init
    call FF_E2E_After(3.0, function FF_E2E_Start)
endfunction
