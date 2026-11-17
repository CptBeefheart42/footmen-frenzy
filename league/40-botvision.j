// FF addons — BotVision: true-sight detection over the whole map for the fleet's bot clients and a
// few named human observers.
// The map already gives every team-4 ("observer") slot a whole-map fog reveal (its own
// Observer Vision Fix trigger), but a fog reveal never shows invisible units: WC3 renders those
// only to the owner, to the owner's allies, or to a player whose true-sight detection covers
// the spot. Allying the bots is not an option — the map's own triggers read alliances (BASE
// collect gold splits a leaver's gold among GetPlayersAllies, Upgrades level pushes tech to
// allies) and WC3 routes "Allies" chat by alliance, which would put both teams' team chat on the
// stream. So each bot observer gets a grid of detector dummies instead.
//
// What detects, and why these exact pieces (all from the map's own object data):
//   * Adtg — the true sight the map's owls carry (n00W/n00X/n00B), i.e. proven to reveal
//     invisible heroes in play; A0CV (the tiger's true sight, same base) scales its `aran`
//     700..950 per level, so for this family `aran` IS the detection radius.
//   * A05H — the map's Magic Sentry variant with `aran` 99999.
//   * Detection only works where the DETECTOR UNIT itself sees (its own sight radius, not the
//     owner's fog state): a first cut on h01K (sight 0, raised at runtime) revealed nothing.
//     h055 is the map's flying, model-less, shadow-less Locust dummy that inherits the Footman's
//     real sight (1400 day / 800 night) — flying, so cliffs don't block it. The grid is dense
//     enough for the night value. It also inherits -10 HP/s regen, hence the keep-alive.
// Detection reveals to the detector's OWNER and to whoever the owner SHARES VISION with — and the
// observer force (lobby slots 12-23, both maps) shares vision among all its members, so the true
// sight would show on every observer's screen. Each detector owner therefore stops sharing its vision with everyone else (FF_bv_Unshare): a one-way, vision-only
// change — alliances, "Allies" chat and the humans' own whole-map fog reveal stay as they are,
// and the owner keeps receiving the others' shared vision. Players in the game see nothing
// different. Locust units are skipped by unit-group enumeration, untargetable and
// collision-free, so spells, bounces, spawns and counts never meet them — the same guarantee
// the map's spell dummies rely on.
// A few human accounts (FF_bv_IsTrueSightName) get the same grid when they observe; every other
// human observer keeps only the map's fog reveal.
// Identity is decided from GetPlayerName (synced), so the units are created identically on
// every client: nothing in here branches on GetLocalPlayer.

globals
    // FF_bv_N x FF_bv_N detectors per bot over the playable area: ~7000 / 9 = ~780 cells, half
    // diagonal ~550 — inside the dummy's 800 night sight with margin.
    integer FF_bv_N = 9
    real FF_bv_SIGHT = 2000.0
    integer FF_bv_DUMMY = 'h055'
    integer FF_bv_DETECT_OWL = 'Adtg'
    integer FF_bv_DETECT_SENTRY = 'A05H'
    group FF_bv_units = null
endglobals

// The human accounts that observe with the bots' true sight.
function FF_bv_IsTrueSightName takes string name returns boolean
    if name == null then
        return false
    endif
    return FF_EndsWith(name, "CptBeefheart#21297") or FF_EndsWith(name, "RJE#2927") or FF_EndsWith(name, "RJE#11113")
endfunction

// A playing, user-controlled slot on the observer team (4) whose name is on the fleet list or the
// true-sight list. Never someone in a player slot: a detector grid there would be a cheat.
function FF_bv_IsTrueSightObserver takes player p returns boolean
    local string name = GetPlayerName(p)
    if GetPlayerSlotState(p) != PLAYER_SLOT_STATE_PLAYING or GetPlayerController(p) != MAP_CONTROL_USER then
        return false
    endif
    return GetPlayerTeam(p) == 4 and (FF_IsBotName(name) or FF_bv_IsTrueSightName(name))
endfunction

function FF_bv_Place takes player owner, real x, real y returns nothing
    local unit u = CreateUnit(owner, FF_bv_DUMMY, x, y, 0.0)
    if u == null then
        return
    endif
    call UnitAddAbility(u, FF_bv_DETECT_OWL)
    call UnitAddAbility(u, FF_bv_DETECT_SENTRY)
    call BlzSetUnitRealField(u, UNIT_RF_SIGHT_RADIUS, FF_bv_SIGHT)
    call BlzSetUnitRealField(u, UNIT_RF_HIT_POINTS_REGENERATION_RATE, 0.0)
    call SetUnitInvulnerable(u, true)
    call SetUnitVertexColor(u, 255, 255, 255, 0)
    call GroupAddUnit(FF_bv_units, u)
    set u = null
endfunction

function FF_bv_Grid takes player owner returns nothing
    local rect r = GetPlayableMapRect()
    local real x0 = GetRectMinX(r)
    local real y0 = GetRectMinY(r)
    local real cw = (GetRectMaxX(r) - x0) / FF_bv_N
    local real ch = (GetRectMaxY(r) - y0) / FF_bv_N
    local integer i = 0
    local integer j
    loop
        exitwhen i >= FF_bv_N
        set j = 0
        loop
            exitwhen j >= FF_bv_N
            call FF_bv_Place(owner, x0 + (i + 0.5) * cw, y0 + (j + 0.5) * ch)
            set j = j + 1
        endloop
        set i = i + 1
    endloop
    set r = null
endfunction

// Keep the detection with its owner: revoke the owner's outgoing shared vision to every other slot. The
// map's own triggers only ever touch alliances among the 12 participants (udg_ally1/2), never the
// observer force, so once at init is enough; a human observer cannot make the bot share again.
function FF_bv_Unshare takes player bot returns nothing
    local integer i = 0
    loop
        exitwhen i >= bj_MAX_PLAYER_SLOTS
        if Player(i) != bot then
            call SetPlayerAlliance(bot, Player(i), ALLIANCE_SHARED_VISION, false)
        endif
        set i = i + 1
    endloop
endfunction

// Keep-alive: the dummy type bleeds 10 HP/s by design (it is a short-lived effect carrier in
// the map). Invulnerability does not stop regeneration, and the runtime regen field may be
// ignored, so top the detectors up every 2s — a handful of units, no I/O.
function FF_bv_TopUp takes nothing returns nothing
    local unit u = GetEnumUnit()
    call SetUnitState(u, UNIT_STATE_LIFE, GetUnitState(u, UNIT_STATE_MAX_LIFE))
    set u = null
endfunction

function FF_bv_OnTick takes nothing returns nothing
    call ForGroup(FF_bv_units, function FF_bv_TopUp)
endfunction

function FF_BotVision_Init takes nothing returns nothing
    local integer i = 0
    local boolean any = false
    set FF_bv_units = CreateGroup()
    loop
        exitwhen i >= bj_MAX_PLAYER_SLOTS
        if FF_bv_IsTrueSightObserver(Player(i)) then
            call FF_bv_Unshare(Player(i))
            call FF_bv_Grid(Player(i))
            set any = true
        endif
        set i = i + 1
    endloop
    if any then
        call TimerStart(CreateTimer(), 2.0, true, function FF_bv_OnTick)
    endif
endfunction
