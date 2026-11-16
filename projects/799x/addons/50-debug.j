// FF addons, main (9v3) map only (FF_JASS_MAP_ADDONS) — an admin debug switch for testing heroes quickly.
//
//   -debug     admins only: the battletags below (scripting/admins.txt) and the map's own admins
//              (udg_admin_level >= 90). Switches debug mode on for EVERYONE in this game, announced to all:
//   -lvl N     sets your selected heroes (or, with none selected, your picked hero) to level N (1-100);
//              plain "-lvl" adds one level.
//   -gold N    adds N gold (1-1000000) to you; plain "-gold" adds 10000.
//   heroes     unlimited hero picks: hero limit 12 and food cap 60 per player (a hero costs 5 food; the map's
//              init gives each player exactly 5), and the tavern's "already picked" flag (udg_tp_kill, set by the
//              map's TP hero trigger) is cleared every 0.25s, so every hero you buy is teleported out and becomes
//              your hero.
// Until an admin types -debug nothing changes; the map's own -lvl (admin level 105, unit level) and -debug stay as they are.

globals
    boolean FF_DBG_on = false
    integer FF_DBG_want = 0
    integer FF_DBG_count = 0
endglobals

function FF_DBG_IsAdmin takes player p returns boolean
    local integer pn = GetPlayerId(p) + 1
    local string name = udg_orig_player_name[pn]
    if name == null or name == "" then
        set name = GetPlayerName(p)
    endif
    if name == "CptBeefheart#21297" or name == "miRaculix#1853" then
        return true
    endif
    return udg_admin_level[pn] >= 90
endfunction

function FF_DBG_Keep takes nothing returns nothing
    local integer i = 0
    loop
        exitwhen i >= 12
        set udg_tp_kill[i + 1] = false
        call SetPlayerMaxHeroesAllowed(12, Player(i))
        if GetPlayerState(Player(i), PLAYER_STATE_FOOD_CAP_CEILING) < 60 then
            call SetPlayerState(Player(i), PLAYER_STATE_FOOD_CAP_CEILING, 60)
        endif
        if GetPlayerState(Player(i), PLAYER_STATE_RESOURCE_FOOD_CAP) < 60 then
            call SetPlayerState(Player(i), PLAYER_STATE_RESOURCE_FOOD_CAP, 60)
        endif
        set i = i + 1
    endloop
endfunction

function FF_DBG_SetLevel takes unit u returns nothing
    local integer target = FF_DBG_want
    if target <= 0 then
        set target = GetHeroLevel(u) + 1
    endif
    if target > 100 then
        set target = 100
    endif
    if target > GetHeroLevel(u) then
        call SetHeroLevel(u, target, true)
    elseif target < GetHeroLevel(u) then
        call UnitStripHeroLevel(u, GetHeroLevel(u) - target)
    endif
    set FF_DBG_count = FF_DBG_count + 1
endfunction

function FF_DBG_LevelEnum takes nothing returns nothing
    local unit u = GetEnumUnit()
    if IsUnitType(u, UNIT_TYPE_HERO) and GetOwningPlayer(u) == GetTriggerPlayer() and GetWidgetLife(u) > 0.405 then
        call FF_DBG_SetLevel(u)
    endif
    set u = null
endfunction

function FF_DBG_Lvl takes nothing returns nothing
    local player p = GetTriggerPlayer()
    local string msg = GetEventPlayerChatString()
    local unit hero = udg_herO[GetPlayerId(p) + 1]
    local group g
    if not FF_DBG_on or SubString(msg, 0, 4) != "-lvl" then
        return
    endif
    set FF_DBG_want = 0
    if StringLength(msg) > 5 then
        set FF_DBG_want = S2I(SubString(msg, 5, StringLength(msg)))
    endif
    set FF_DBG_count = 0
    set g = GetUnitsSelectedAll(p)
    call ForGroup(g, function FF_DBG_LevelEnum)
    call DestroyGroup(g)
    if FF_DBG_count == 0 and hero != null and GetWidgetLife(hero) > 0.405 then
        call FF_DBG_SetLevel(hero)
    endif
    if FF_DBG_count == 0 then
        call DisplayTimedTextToPlayer(p, 0, 0, 5.0, "-lvl: select your hero first (or pick one).")
    endif
    set g = null
    set hero = null
endfunction

function FF_DBG_Gold takes nothing returns nothing
    local player p = GetTriggerPlayer()
    local string msg = GetEventPlayerChatString()
    local integer amount = 10000
    if not FF_DBG_on or SubString(msg, 0, 5) != "-gold" then
        return
    endif
    if StringLength(msg) > 6 then
        set amount = S2I(SubString(msg, 6, StringLength(msg)))
    endif
    if amount < 1 or amount > 1000000 then
        call DisplayTimedTextToPlayer(p, 0, 0, 5.0, "-gold: use an amount from 1 to 1000000, e.g. -gold 50000")
        return
    endif
    call SetPlayerState(p, PLAYER_STATE_RESOURCE_GOLD, GetPlayerState(p, PLAYER_STATE_RESOURCE_GOLD) + amount)
endfunction

function FF_DBG_Cmd takes nothing returns nothing
    local player p = GetTriggerPlayer()
    if not FF_DBG_IsAdmin(p) then
        call DisplayTimedTextToPlayer(p, 0, 0, 5.0, "-debug: admins only.")
        return
    endif
    if FF_DBG_on then
        call DisplayTimedTextToPlayer(p, 0, 0, 5.0, "Debug mode is already on.")
        return
    endif
    set FF_DBG_on = true
    call FF_DBG_Keep()
    call TimerStart(CreateTimer(), 0.25, true, function FF_DBG_Keep)
    call DisplayTimedTextToForce(GetPlayersAll(), 20.0, "|cffffcc00DEBUG MODE|r enabled by " + udg_orig_player_name[GetPlayerId(p) + 1] + ": everyone can now use |cffffcc00-lvl <level>|r (selected hero), |cffffcc00-gold <amount>|r and pick unlimited heroes.")
endfunction

// Injected by the build runner right after `call FF_Init()` (FF_JASS_MAP_ADDONS).
function FF_MapInit takes nothing returns nothing
    local trigger cmd = CreateTrigger()
    local trigger lvl = CreateTrigger()
    local trigger gold = CreateTrigger()
    local integer i = 0
    call FF_MM_Init()
    call FF_MA_Init()
    loop
        exitwhen i >= 12
        call TriggerRegisterPlayerChatEvent(cmd, Player(i), "-debug", true)
        call TriggerRegisterPlayerChatEvent(lvl, Player(i), "-lvl", false)
        call TriggerRegisterPlayerChatEvent(gold, Player(i), "-gold", false)
        set i = i + 1
    endloop
    call TriggerAddAction(cmd, function FF_DBG_Cmd)
    call TriggerAddAction(lvl, function FF_DBG_Lvl)
    call TriggerAddAction(gold, function FF_DBG_Gold)
    set cmd = null
    set lvl = null
    set gold = null
endfunction
