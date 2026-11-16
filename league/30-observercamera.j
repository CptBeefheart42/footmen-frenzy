// FF addons — ObserverCamera: hero-follow spectator camera for observers (-cam N / -cam / -cam off; -obs is the same command).
// Port of scripting/Source/ObserverCamera.cs (see its doc comment for the full design).
//   * -cam N        lock onto player N's hero (1-based, matching udg_herO);
//   * -cam / auto   cycle participating players, 60s each;
//   * -cam off      release to free-look.
// Following uses SetCameraTargetControllerNoZForPlayer — a per-player camera native touches only
// the matching local client, so one observer's view never disturbs anyone else's (desync-safe).
// A dead/mid-revive target falls back to a living allied hero. In auto mode only, a hero kill
// hijacks the view for 5s (follow the killer, else the victim), then the cycle resumes with the
// interrupted player's dwell time intact. Observers = user slots on team 4 (as Observer_Vision_Fix).
// Observers may also scroll over the whole playable area: the map's "minimap correction" trigger
// (1s after start) stops every slot's camera about 400 units short of the corner shops, which an
// observer clicks to see what was bought.

globals
    // Per-observer state, indexed by 0-based player id.
    integer array FF_oc_mode        // 0 = off, 1 = manual, 2 = auto
    integer array FF_oc_focus       // manual: pinned player; auto: current cycle player (1..12)
    integer array FF_oc_cycleTick   // auto: director tick at which to advance
    unit array FF_oc_followed       // hero currently locked, so we only re-lock on a change
    integer FF_oc_tick = 0
    // Shared hero-kill interrupt (one event for everyone; the camera lock itself stays per-player).
    unit FF_oc_interruptUnit = null
    integer FF_oc_interruptUntil = 0
endglobals

// Director tick = 0.25s. Auto-cycle dwell 60s = 240 ticks; kill-interrupt window 5s = 20 ticks.

// Who may use / receive the director: a user-controlled, playing slot on the observer team (4).
function FF_oc_CanObserve takes player p returns boolean
    if GetPlayerSlotState(p) != PLAYER_SLOT_STATE_PLAYING or GetPlayerController(p) != MAP_CONTROL_USER then
        return false
    endif
    return GetPlayerTeam(p) == 4
endfunction

// A real participant to spectate: user-controlled, still playing, not an observer.
function FF_oc_IsActivePlayer takes integer pn returns boolean
    local player p = Player(pn - 1)
    return GetPlayerSlotState(p) == PLAYER_SLOT_STATE_PLAYING and GetPlayerController(p) == MAP_CONTROL_USER and GetPlayerTeam(p) != 4
endfunction

// Next participating player number after pn (wraps 12->1); pn unchanged if none qualify.
function FF_oc_NextActivePlayer takes integer pn returns integer
    local integer step = 0
    loop
        exitwhen step >= 12
        set pn = ModuloInteger(pn, 12) + 1
        if FF_oc_IsActivePlayer(pn) then
            return pn
        endif
        set step = step + 1
    endloop
    return pn
endfunction

// Player pn's hero if it exists and is alive (mid-revive / removed counts as not alive).
function FF_oc_LivingHero takes integer pn returns unit
    if pn < 1 or pn > 12 then
        return null
    endif
    if FF_UnitAlive(udg_herO[pn]) then
        return udg_herO[pn]
    endif
    return null
endfunction

// First living hero of a player allied with pn (the "same team" fallback on a death).
function FF_oc_LivingAlliedHero takes integer pn returns unit
    local integer n = 1
    if pn < 1 or pn > 12 then
        return null
    endif
    loop
        exitwhen n > 12
        if n != pn and IsPlayerAlly(Player(pn - 1), Player(n - 1)) and FF_oc_LivingHero(n) != null then
            return FF_oc_LivingHero(n)
        endif
        set n = n + 1
    endloop
    return null
endfunction

// The hero to show for player pn: their own if alive, else a living teammate's, else none.
function FF_oc_ResolveFocusHero takes integer pn returns unit
    if FF_oc_LivingHero(pn) != null then
        return FF_oc_LivingHero(pn)
    endif
    return FF_oc_LivingAlliedHero(pn)
endfunction

function FF_oc_PlayerLabel takes integer pn returns string
    return "player " + I2S(pn) + " (" + GetPlayerName(Player(pn - 1)) + ")"
endfunction

function FF_oc_OnCommand takes nothing returns nothing
    local player p = GetTriggerPlayer()
    local integer slot
    local string chat
    local string arg = ""
    local integer n
    if not FF_oc_CanObserve(p) then
        call DisplayTextToPlayer(p, 0, 0, "|cffff8000-cam / -obs is for observers only.|r")
        set p = null
        return
    endif
    set slot = GetPlayerId(p)
    // Tail after "-cam ", e.g. "3", "auto", "off", or "" for a bare "-cam".
    set chat = GetEventPlayerChatString()
    if StringLength(chat) > 5 then
        set arg = SubString(chat, 5, StringLength(chat))
    endif
    // (JASS string == is case-insensitive, so "off"/"OFF"/"Off" are all covered.)
    if arg == "off" or arg == "0" then
        set FF_oc_mode[slot] = 0
        set FF_oc_followed[slot] = null
        call ResetToGameCameraForPlayer(p, 0)
        call DisplayTextToPlayer(p, 0, 0, "|cffff8000Spectator camera: OFF|r - free-look.")
        set p = null
        return
    endif
    set n = S2I(arg)
    if n >= 1 and n <= 12 then
        set FF_oc_mode[slot] = 1
        set FF_oc_focus[slot] = n
        // Clearing the lock forces a re-lock on the next director tick.
        set FF_oc_followed[slot] = null
        call DisplayTextToPlayer(p, 0, 0, "|cff32cd32Spectator camera:|r following " + FF_oc_PlayerLabel(n) + ". Type -cam for auto-cycle, -cam off to stop.")
        set p = null
        return
    endif
    if StringLength(arg) == 0 or arg == "auto" then
        set FF_oc_mode[slot] = 2
        set FF_oc_focus[slot] = FF_oc_NextActivePlayer(0)
        set FF_oc_cycleTick[slot] = FF_oc_tick + 240
        set FF_oc_followed[slot] = null
        call DisplayTextToPlayer(p, 0, 0, "|cff32cd32Spectator camera: AUTO|r - cycling players (60s each). Type -cam N to lock one, -cam off to stop.")
        set p = null
        return
    endif
    call DisplayTextToPlayer(p, 0, 0, "|cffff8000Usage:|r -cam N (player 1-12), -cam (auto-cycle), or -cam off. -obs works the same.")
    set p = null
endfunction

// Any hero kill arms the shared interrupt: auto observers snap to the killer (alive, at the
// scene; else the victim) for 5s. A newer kill refreshes the window and retargets.
function FF_oc_OnDeath takes nothing returns nothing
    local unit victim = GetTriggerUnit()
    local unit killer
    if not IsUnitType(victim, UNIT_TYPE_HERO) then
        set victim = null
        return
    endif
    set killer = GetKillingUnit()
    if killer == null then
        set victim = null
        return
    endif
    if FF_UnitAlive(killer) then
        set FF_oc_interruptUnit = killer
    else
        set FF_oc_interruptUnit = victim
    endif
    set FF_oc_interruptUntil = FF_oc_tick + 20
    set victim = null
    set killer = null
endfunction

// Director: for each active observer, resolve who to watch and re-lock only when it changes.
function FF_oc_OnTick takes nothing returns nothing
    local integer i = 0
    local boolean interrupt
    local player p
    local unit hero
    set FF_oc_tick = FF_oc_tick + 1
    set interrupt = FF_oc_tick < FF_oc_interruptUntil and FF_UnitAlive(FF_oc_interruptUnit)
    // Drop the reference once the window closes, so a dead hero's handle is not pinned
    // by this global until the next hero kill happens to overwrite it.
    if not interrupt and FF_oc_interruptUnit != null then
        set FF_oc_interruptUnit = null
    endif
    loop
        exitwhen i >= bj_MAX_PLAYER_SLOTS
        if FF_oc_mode[i] != 0 then
            set p = Player(i)
            if FF_oc_CanObserve(p) then
                if FF_oc_mode[i] == 2 and interrupt then
                    // Hold the cycle while the kill is on screen (keep the dwell time).
                    if FF_oc_cycleTick[i] <= FF_oc_tick then
                        set FF_oc_cycleTick[i] = FF_oc_tick + 1
                    endif
                    if FF_oc_interruptUnit != FF_oc_followed[i] then
                        set FF_oc_followed[i] = FF_oc_interruptUnit
                        call SetCameraTargetControllerNoZForPlayer(p, FF_oc_interruptUnit, 0, 0, false)
                    endif
                else
                    if FF_oc_mode[i] == 2 and FF_oc_tick >= FF_oc_cycleTick[i] then
                        set FF_oc_focus[i] = FF_oc_NextActivePlayer(FF_oc_focus[i])
                        set FF_oc_cycleTick[i] = FF_oc_tick + 240
                        call DisplayTextToPlayer(p, 0, 0, "|cff9acd32Now watching:|r " + FF_oc_PlayerLabel(FF_oc_focus[i]))
                    endif
                    set hero = FF_oc_ResolveFocusHero(FF_oc_focus[i])
                    if hero != null and hero != FF_oc_followed[i] then
                        set FF_oc_followed[i] = hero
                        call SetCameraTargetControllerNoZForPlayer(p, hero, 0, 0, false)
                    endif
                endif
            endif
        endif
        set i = i + 1
    endloop
    set p = null
    set hero = null
endfunction

// Lets every observer's camera reach the playable area's edges (camera bounds are local: no desync).
function FF_oc_WidenBounds takes nothing returns nothing
    local integer i = 0
    call DestroyTimer(GetExpiredTimer())
    loop
        exitwhen i >= bj_MAX_PLAYER_SLOTS
        if FF_oc_CanObserve(Player(i)) then
            call SetCameraBoundsToRectForPlayerBJ(Player(i), bj_mapInitialPlayableArea)
        endif
        set i = i + 1
    endloop
endfunction

function FF_ObserverCamera_Init takes nothing returns nothing
    local trigger ct = CreateTrigger()
    local trigger dt = CreateTrigger()
    local integer i = 0
    // Listen from every slot (prefix match, so "-cam 3" fires too); OnCommand enforces the
    // observer-only rule.
    loop
        exitwhen i >= bj_MAX_PLAYER_SLOTS
        call TriggerRegisterPlayerChatEvent(ct, Player(i), "-cam", false)
        call TriggerRegisterPlayerChatEvent(ct, Player(i), "-obs", false)
        set i = i + 1
    endloop
    call TriggerAddAction(ct, function FF_oc_OnCommand)
    call TriggerRegisterAnyUnitEventBJ(dt, EVENT_PLAYER_UNIT_DEATH)
    call TriggerAddAction(dt, function FF_oc_OnDeath)
    call TimerStart(CreateTimer(), 0.25, true, function FF_oc_OnTick)
    // After the map's own clamp at 1.0s (this init runs at 0.1s).
    call TimerStart(CreateTimer(), 1.5, false, function FF_oc_WidenBounds)
    set ct = null
    set dt = null
endfunction
