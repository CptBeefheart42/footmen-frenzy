// FF addons — AFK kick: a player who still has no hero once FF_AFK_KICK seconds have passed since the mass began
// AND the gold pool is open is removed from the game, like the map's own kick. Removing a player hands their base
// and gold to the allies, a pool in all but name, so the kick waits until pooling is allowed: in a main-map Pub game
// that is the trading timer (230 s after the game started); in Pro, In-house and debug the pool is open from the
// start; Solo has no pool (its trading timer never runs), so there the kick comes FF_AFK_KICK seconds after the mass.
// Everyone without a hero is warned FF_AFK_WARN seconds after the mass began, and again FF_AFK_WARN_AGAIN seconds
// before a later kick.
// "No hero" = the map's per-slot hero global (udg_herO) is empty: a hero that died still counts as picked.
// Only human players in slots 1-12 who are still in the game; computers and observers never.
// The kick itself is the map's (its leaver handling differs per map): the map addon (jass-main / jass-solo
// 48-afk.j) sets FF_afk_kickHook, which removes slot FF_afk_slot. The result file drops the slot first
// (FF_gr_DropAfk), so the game doesn't count for a player who never played.

globals
    real FF_AFK_WARN = 5.0
    real FF_AFK_KICK = 15.0
    real FF_AFK_WARN_AGAIN = 10.0
    // the map addon's kick of slot FF_afk_slot
    trigger FF_afk_kickHook = null
    integer FF_afk_slot = 0
    // whole seconds since the mass began
    integer FF_afk_t = 0
endglobals

// A human player still in the game, without a hero.
function FF_afk_IsAfk takes integer slot returns boolean
    local player p = Player(slot - 1)
    if GetPlayerSlotState(p) != PLAYER_SLOT_STATE_PLAYING or GetPlayerController(p) != MAP_CONTROL_USER then
        return false
    endif
    if not udg_player_active[slot] or FF_gr_afk[slot] then
        return false
    endif
    return udg_herO[slot] == null or GetUnitTypeId(udg_herO[slot]) == 0
endfunction

// Whole seconds until the gold pool opens; 0 once it is open.
function FF_afk_PoolIn takes nothing returns integer
    if udg_autopoool_allowed then
        return 0
    endif
    return R2I(TimerGetRemaining(udg_timer_trading) + 0.99)
endfunction

// Whole seconds until the kick.
function FF_afk_KickIn takes nothing returns integer
    return IMaxBJ(R2I(FF_AFK_KICK) - FF_afk_t, FF_afk_PoolIn())
endfunction

function FF_afk_Warn takes integer left returns nothing
    local integer s = 1
    loop
        exitwhen s > 12
        if FF_afk_IsAfk(s) then
            call DisplayTimedTextToForce(GetPlayersAll(), 10.0, GetPlayerName(Player(s - 1)) + " has no hero: removed from the game in " + I2S(left) + " seconds (AFK).")
            call DisplayTimedTextToPlayer(Player(s - 1), 0, 0, 10.0, "|cffff4040Pick a hero within " + I2S(left) + " seconds, or you are removed from the game.|r")
        endif
        set s = s + 1
    endloop
endfunction

function FF_afk_Kick takes nothing returns nothing
    local integer s = 1
    loop
        exitwhen s > 12
        if FF_afk_IsAfk(s) then
            call DisplayTimedTextToForce(GetPlayersAll(), 10.0, GetPlayerName(Player(s - 1)) + " was removed from the game: no hero (AFK).")
            call FF_gr_DropAfk(s)
            set FF_afk_slot = s
            if FF_afk_kickHook != null then
                call TriggerExecute(FF_afk_kickHook)
            endif
        endif
        set s = s + 1
    endloop
endfunction

// Once a second from the mass on, until the kick.
function FF_afk_Tick takes nothing returns nothing
    local integer left
    set FF_afk_t = FF_afk_t + 1
    set left = FF_afk_KickIn()
    if left <= 0 then
        call DestroyTimer(GetExpiredTimer())
        call FF_afk_Kick()
    elseif FF_afk_t == R2I(FF_AFK_WARN) or (FF_afk_t > R2I(FF_AFK_WARN) and left == R2I(FF_AFK_WARN_AGAIN)) then
        call FF_afk_Warn(left)
    endif
endfunction

// The mass began (the map's pre-mass countdown ran out).
function FF_afk_OnMass takes nothing returns nothing
    call DestroyTrigger(GetTriggeringTrigger())
    set FF_afk_t = 0
    call TimerStart(CreateTimer(), 1.0, true, function FF_afk_Tick)
endfunction

function FF_Afk_Init takes nothing returns nothing
    local trigger t = CreateTrigger()
    call TriggerRegisterTimerExpireEvent(t, udg_timer_premass)
    call TriggerAddAction(t, function FF_afk_OnMass)
    set t = null
endfunction
