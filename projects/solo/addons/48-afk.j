// FF addons (Solo map only) — the AFK kick (25-afk.j) removes a player the way the map's admin kick does
// (Trig_KICK_execute_Actions): defeat, then the player is out of the game (its units go, END is asked).

function FF_MA_AfkKick takes nothing returns nothing
    local integer n = FF_afk_slot
    call CustomDefeatBJ(Player(n - 1), "Removed from the game (AFK).")
    // a leave event the defeat raised has run the map's own leaver handling already
    if not udg_player_active[n] then
        return
    endif
    if udg_mode_koth and udg_KOTH_Team_Number == udg_teamnumber[n] then
        call TriggerExecute(gg_trg_KOTH_Set_Neutral_Hill)
        call TriggerExecute(gg_trg_KOTH_Reset_Hill)
    endif
    set SoloFoots_LastEliminatedPlayerNumber = n
    set SoloFoots_FinalStrikePlayer = null
    set SoloFoots_FinalEliminationWasLeave = true
    set udg_player_active[n] = false
    call ForceRemovePlayerSimple(Player(n - 1), udg_Active_PlayGroup)
    set SafeRemoval_GraceTicks = 0
    call EnableTrigger(gg_trg_Kill_units_of_inactive_player)
    call EnableTrigger(gg_trg_Visibility)
    call ConditionalTriggerExecute(gg_trg_Visibility)
    call ConditionalTriggerExecute(gg_trg_END)
    call EnableTrigger(gg_trg_check_if_team_active)
endfunction

function FF_MA_Init takes nothing returns nothing
    set FF_afk_kickHook = CreateTrigger()
    call TriggerAddAction(FF_afk_kickHook, function FF_MA_AfkKick)
endfunction
