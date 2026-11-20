// FF addons — AFK kick: a player who still has no hero, or has done nothing at all since the game started, once
// FF_AFK_KICK seconds have passed since the mass began AND the gold pool is open is removed from the game, like the
// map's own kick. When the mass begins, a map addon may first give every player without a hero a random one
// (FF_afk_autoHeroHook; 799X does), so there a player who is not there is recognised by having done nothing.
// "Done something" counts only what players do themselves: selecting one of their own units (not the selections the
// map makes: a player's mode selector at the start, a freshly picked hero, a shop such as 799X's draft tavern), chatting, buying an item or unit, starting research,
// an upgrade or training, the arrow keys, Esc and the F keys. Orders don't count: the map orders units itself
// (autosend). Removing a player hands their base
// and gold to the allies, a pool in all but name, so the kick waits until pooling is allowed: in a main-map Pub game
// that is the trading timer (230 s after the game started); in Pro, In-house and debug the pool is open from the
// start; Solo has no pool (its trading timer never runs), so there the kick comes FF_AFK_KICK seconds after the mass.
// Everyone about to be removed is warned FF_AFK_WARN seconds after the mass began, and again FF_AFK_WARN_AGAIN seconds
// before a later kick.
// "No hero" = the map's per-slot hero global (udg_herO) is empty: a hero that died still counts as picked.
// Only human players in slots 1-12 who are still in the game; computers and observers never.
// The kick itself is the map's (its leaver handling differs per map): the map addon (projects/<map>/addons/48-afk.j)
// sets FF_afk_kickHook, which removes slot FF_afk_slot. The result file drops the slot first
// (FF_gr_DropAfk), so the game doesn't count for a player who never played.

globals
    real FF_AFK_WARN = 5.0
    real FF_AFK_KICK = 15.0
    real FF_AFK_WARN_AGAIN = 10.0
    // the map addon's kick of slot FF_afk_slot
    trigger FF_afk_kickHook = null
    // the map addon's auto hero: a random hero for every player without one, when the mass begins
    trigger FF_afk_autoHeroHook = null
    integer FF_afk_slot = 0
    // whole seconds since the mass began
    integer FF_afk_t = 0
    // the slot did something itself since the game started
    boolean array FF_afk_present
    // what first counted the slot as present (e.g. `select:hfoo`, `event:17`, `sell`), for tests and complaints
    string array FF_afk_presentBy
endglobals

function FF_afk_NoHero takes integer slot returns boolean
    return udg_herO[slot] == null or GetUnitTypeId(udg_herO[slot]) == 0
endfunction

// A human player still in the game, without a hero or who has done nothing yet.
function FF_afk_IsAfk takes integer slot returns boolean
    local player p = Player(slot - 1)
    if GetPlayerSlotState(p) != PLAYER_SLOT_STATE_PLAYING or GetPlayerController(p) != MAP_CONTROL_USER then
        return false
    endif
    if not udg_player_active[slot] or FF_gr_afk[slot] then
        return false
    endif
    return FF_afk_NoHero(slot) or not FF_afk_present[slot]
endfunction

// Counts the player as present; `by` says what they did (kept for the first time only).
function FF_afk_PresentBy takes player p, string by returns nothing
    local integer slot = GetPlayerId(p) + 1
    if slot >= 1 and slot <= 12 then
        if not FF_afk_present[slot] then
            set FF_afk_presentBy[slot] = by
        endif
        set FF_afk_present[slot] = true
    endif
endfunction

function FF_afk_Present takes player p returns nothing
    call FF_afk_PresentBy(p, "event:" + I2S(GetHandleId(GetTriggerEventId())))
endfunction

function FF_afk_OnPlayerSignal takes nothing returns nothing
    call FF_afk_Present(GetTriggerPlayer())
endfunction

// A unit was selected: the map's own selections (its mode selector at the start, a freshly picked hero) don't count.
function FF_afk_OnSelect takes nothing returns nothing
    local integer slot = GetPlayerId(GetTriggerPlayer()) + 1
    local unit u = GetTriggerUnit()
    if slot >= 1 and slot <= 12 and GetOwningPlayer(u) == GetTriggerPlayer() and u != udg_herO[slot] and u != udg_mode_selector[slot] then
        call FF_afk_PresentBy(GetTriggerPlayer(), "select:" + FF_us_Id2S(GetUnitTypeId(u)))
    endif
    set u = null
endfunction

function FF_afk_OnSell takes nothing returns nothing
    call FF_afk_PresentBy(GetOwningPlayer(GetBuyingUnit()), "sell")
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
        if FF_afk_IsAfk(s) and FF_afk_NoHero(s) then
            call DisplayTimedTextToForce(GetPlayersAll(), 10.0, GetPlayerName(Player(s - 1)) + " has no hero: removed from the game in " + I2S(left) + " seconds (AFK).")
            call DisplayTimedTextToPlayer(Player(s - 1), 0, 0, 10.0, "|cffff4040Pick a hero within " + I2S(left) + " seconds, or you are removed from the game.|r")
        elseif FF_afk_IsAfk(s) then
            call DisplayTimedTextToForce(GetPlayersAll(), 10.0, GetPlayerName(Player(s - 1)) + " has not played yet: removed from the game in " + I2S(left) + " seconds (AFK).")
            call DisplayTimedTextToPlayer(Player(s - 1), 0, 0, 10.0, "|cffff4040Select a unit, chat or buy something within " + I2S(left) + " seconds, or you are removed from the game.|r")
        endif
        set s = s + 1
    endloop
endfunction

function FF_afk_Kick takes nothing returns nothing
    local integer s = 1
    loop
        exitwhen s > 12
        if FF_afk_IsAfk(s) then
            if FF_afk_NoHero(s) then
                call DisplayTimedTextToForce(GetPlayersAll(), 10.0, GetPlayerName(Player(s - 1)) + " was removed from the game: no hero (AFK).")
            else
                call DisplayTimedTextToForce(GetPlayersAll(), 10.0, GetPlayerName(Player(s - 1)) + " was removed from the game: did not play (AFK).")
            endif
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
    if FF_afk_autoHeroHook != null then
        call TriggerExecute(FF_afk_autoHeroHook)
    endif
    set FF_afk_t = 0
    call TimerStart(CreateTimer(), 1.0, true, function FF_afk_Tick)
endfunction

function FF_Afk_Init takes nothing returns nothing
    local trigger t = CreateTrigger()
    local trigger signal = CreateTrigger()
    local trigger select = CreateTrigger()
    local trigger sell = CreateTrigger()
    local integer i = 0
    call TriggerRegisterTimerExpireEvent(t, udg_timer_premass)
    call TriggerAddAction(t, function FF_afk_OnMass)
    loop
        exitwhen i >= 12
        call TriggerRegisterPlayerChatEvent(signal, Player(i), "", false)
        call TriggerRegisterPlayerUnitEvent(signal, Player(i), EVENT_PLAYER_UNIT_RESEARCH_START, null)
        call TriggerRegisterPlayerUnitEvent(signal, Player(i), EVENT_PLAYER_UNIT_UPGRADE_START, null)
        call TriggerRegisterPlayerUnitEvent(signal, Player(i), EVENT_PLAYER_UNIT_TRAIN_START, null)
        call TriggerRegisterPlayerEvent(signal, Player(i), EVENT_PLAYER_ARROW_LEFT_DOWN)
        call TriggerRegisterPlayerEvent(signal, Player(i), EVENT_PLAYER_ARROW_RIGHT_DOWN)
        call TriggerRegisterPlayerEvent(signal, Player(i), EVENT_PLAYER_ARROW_UP_DOWN)
        call TriggerRegisterPlayerEvent(signal, Player(i), EVENT_PLAYER_ARROW_DOWN_DOWN)
        call TriggerRegisterPlayerEvent(signal, Player(i), EVENT_PLAYER_END_CINEMATIC)
        call BlzTriggerRegisterPlayerKeyEvent(signal, Player(i), OSKEY_F1, 0, true)
        call BlzTriggerRegisterPlayerKeyEvent(signal, Player(i), OSKEY_F2, 0, true)
        call BlzTriggerRegisterPlayerKeyEvent(signal, Player(i), OSKEY_F3, 0, true)
        call BlzTriggerRegisterPlayerKeyEvent(signal, Player(i), OSKEY_F4, 0, true)
        call TriggerRegisterPlayerUnitEvent(select, Player(i), EVENT_PLAYER_UNIT_SELECTED, null)
        set i = i + 1
    endloop
    call TriggerAddAction(signal, function FF_afk_OnPlayerSignal)
    call TriggerAddAction(select, function FF_afk_OnSelect)
    call TriggerRegisterAnyUnitEventBJ(sell, EVENT_PLAYER_UNIT_SELL)
    call TriggerRegisterAnyUnitEventBJ(sell, EVENT_PLAYER_UNIT_SELL_ITEM)
    call TriggerAddAction(sell, function FF_afk_OnSell)
    set t = null
    set signal = null
    set select = null
    set sell = null
endfunction
