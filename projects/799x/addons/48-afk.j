// FF addons (main map only) — the AFK kick (25-afk.j) removes a player the way the map's votekick does: defeat, then
// the map's leaver handling (Trig_player_leaves: the allies take over the base and its gold).

function FF_MA_AfkKick takes nothing returns nothing
    local player p = Player(FF_afk_slot - 1)
    call CustomDefeatBJ(p, "Removed from the game: no hero (AFK).")
    set udg_Votekick_Target_Player = p
    set udg_Votekick_Defeat_Kicked_Player = true
    call TriggerExecute(gg_trg_player_leaves)
    set p = null
endfunction

function FF_MA_Init takes nothing returns nothing
    set FF_afk_kickHook = CreateTrigger()
    call TriggerAddAction(FF_afk_kickHook, function FF_MA_AfkKick)
endfunction
