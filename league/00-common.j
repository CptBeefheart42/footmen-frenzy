// FF addons — shared helpers. Plain-JASS ports of the C# systems in scripting/Source, injected
// into the ORIGINAL war3map.j by the build runner (FF_JASS_ADDONS) so the map keeps the proven
// JASS engine path (no Lua transpile). Files are concatenated in filename order; every top-level
// `globals` block is merged into the map's globals, everything else is inserted before main().
// All identifiers use the FF_ prefix (the base script has none — checked at build time).

globals
    // Never expires; only TimerGetElapsed is read off it, to timestamp log rows (mirrors the C#
    // systems' gameTimer). Started by FF_BootTick in 90-init.j.
    timer FF_gameTimer = null
    // Tells concurrent games on one box apart in the output file names (see FF_DataFile).
    // Computed once at boot by FF_ComputeGameToken; identical on every client.
    string FF_gameToken = ""
    // The longest row written to a Preload file: the game keeps at most 259 characters of a Preload string.
    integer FF_PRELOAD_MAX = 240
    // A hosting bot is in the game (FF_HostBotInGame), set at boot before the map's 1.00s mode dialog:
    // the maps' MODE GUI show hooks then pick Pub mode instead of asking the host.
    boolean FF_hostBotGame = false
endglobals

function FF_Pad2 takes integer n returns string
    if n < 10 then
        return "0" + I2S(n)
    endif
    return I2S(n)
endfunction

// Match time as "mm:ss" (measured from FF_BootTick, ~0.1s after map init — same as the C# port).
function FF_Elapsed takes nothing returns string
    local integer total = R2I(TimerGetElapsed(FF_gameTimer))
    return FF_Pad2(total / 60) + ":" + FF_Pad2(ModuloInteger(total, 60))
endfunction

// Player / unit names can't be allowed to break the CSV-ish log formats: commas, semicolons and
// newlines become spaces, double quotes become single. (KillLog only needs commas stripped, but
// stripping the roster separator ';' too is harmless there and lets both systems share this.)
function FF_Sanitize takes string s returns string
    local string out = ""
    local integer i = 0
    local integer n
    local string c
    if s == null then
        return ""
    endif
    set n = StringLength(s)
    loop
        exitwhen i >= n
        set c = SubString(s, i, i + 1)
        if c == "," or c == ";" or c == "\n" or c == "\r" then
            set out = out + " "
        elseif c == "\"" then
            set out = out + "'"
        else
            set out = out + c
        endif
        set i = i + 1
    endloop
    return out
endfunction

// NOTE: JASS string comparison is case-insensitive; for battletag suffixes that's acceptable
// (Battle.net tags are unique modulo case).
function FF_EndsWith takes string s, string suffix returns boolean
    local integer ls = StringLength(s)
    local integer lx = StringLength(suffix)
    if lx > ls then
        return false
    endif
    return SubString(s, ls - lx, ls) == suffix
endfunction

// Alive check without the UnitAlive native (not declared in this map's script): a null/removed
// handle or a dead/mid-revive hero all count as not alive — matching the C# UnitAlive usage.
function FF_UnitAlive takes unit u returns boolean
    return u != null and GetUnitTypeId(u) != 0 and not IsUnitType(u, UNIT_TYPE_DEAD)
endfunction

// The efl-bot fleet's Battle.net tags, in two lists. Endswith tolerates a leading clan tag
// ("(EFL)Name#1234"); a human can't forge another account's "#1234" suffix.
// If a bot account is (re-)provisioned, update here AND in KillLog.cs, then rebuild.
// Both take the name so they can be asked about ANY player (synced: GetPlayerName is the same on
// every client) — only FF_LocalClientIsBot below reads GetLocalPlayer, for local-only decisions.

// The bots that host lobbies: a game with one of them in it is a bot-hosted game, which starts in
// Pub mode without the host's mode dialog (the anchors in scripting/jass-main and jass-solo).
// efl-9v3 hosts the 9v3 OFFICIAL lobby, efl-1v1-0 / efl-1v1-1 the 1v1v1v1 lobbies.
function FF_IsHostBotName takes string name returns boolean
    if name == null then
        return false
    endif
    return FF_EndsWith(name, "CoralShark#113567") or FF_EndsWith(name, "OhNaahs#1537") or FF_EndsWith(name, "LustyPuppy#1929")
endfunction

// Every bot: the hosts above plus the ones that only watch. These are the only clients that write
// the bot's files under per-game names (and the kill log at all), and the only observers that get
// true-sight detection (40-botvision.j). The watchers also join other people's games, so they never
// change how a game is played.
function FF_IsBotName takes string name returns boolean
    if name == null then
        return false
    endif
    if FF_IsHostBotName(name) then
        return true
    endif
    // efl-obs (observes and streams), and the retired 1.0 fleet accounts (still ours).
    return FF_EndsWith(name, "MangoThief#115445") or FF_EndsWith(name, "Vertical#11718") or FF_EndsWith(name, "Industry#11190") or FF_EndsWith(name, "BryanBoitano#1725")
endfunction

// Whether a hosting bot holds any user-controlled playing slot (player or observer): the game's
// lobby is one of ours. Synced inputs only, so every client computes the same answer.
function FF_HostBotInGame takes nothing returns boolean
    local integer i = 0
    local player p
    loop
        exitwhen i >= bj_MAX_PLAYER_SLOTS
        set p = Player(i)
        if GetPlayerSlotState(p) == PLAYER_SLOT_STATE_PLAYING and GetPlayerController(p) == MAP_CONTROL_USER and FF_IsHostBotName(GetPlayerName(p)) then
            return true
        endif
        set i = i + 1
    endloop
    return false
endfunction

function FF_LocalClientIsBot takes nothing returns boolean
    return FF_IsBotName(GetPlayerName(GetLocalPlayer()))
endfunction

// The 2.0 bot runs several WC3 instances per account on one box, all writing into ONE
// CustomMapData folder — a fixed "ff_result.txt" there is whichever game flushed last. Games
// running at the same time can't share a player, so a hash of the roster (every user-controlled
// playing slot, observers and the bot included) is distinct across them. Synced inputs, pure
// function: the same string on every client. Two consecutive games with the very same roster
// reuse the name, which is fine — the bot consumes and deletes a finished file within a second.
function FF_ComputeGameToken takes nothing returns string
    local string roster = ""
    local integer i = 0
    local integer h
    local player p
    loop
        exitwhen i >= bj_MAX_PLAYER_SLOTS
        set p = Player(i)
        if GetPlayerSlotState(p) == PLAYER_SLOT_STATE_PLAYING and GetPlayerController(p) == MAP_CONTROL_USER then
            set roster = roster + GetPlayerName(p) + "|"
        endif
        set i = i + 1
    endloop
    set p = null
    // Fold the signed hash into 0..2^31-1 so the name never carries a '-'.
    set h = StringHash(roster)
    if h < 0 then
        set h = h + 2147483647
        set h = h + 1
    endif
    return I2S(h)
endfunction

// Output file name for one of the bot's data files: "ff_result" -> "ff_result_<token>.txt" on a
// bot client, plain "ff_result.txt" everywhere else. Only bot boxes run several games in one
// folder; a human's client keeps the single overwritten file instead of collecting one per game.
// Decided per call off GetLocalPlayer — it only ever names a local Preload write, never feeds
// synced state, so clients disagreeing here cannot desync.
function FF_DataFile takes string base returns string
    if FF_LocalClientIsBot() then
        return base + "_" + FF_gameToken + ".txt"
    endif
    return base + ".txt"
endfunction

// Sides as ff_result numbers them, mirroring the map's END trigger: FFA = four trios (team1..team4, slots 1-3,
// 4-6, 7-9, 10-12), 6v6 = west (slots 1-3 + 10-12) and east (4-9).
function FF_SideCount takes nothing returns integer
    if udg_mode_6v6 then
        return 2
    endif
    return 4
endfunction

function FF_SideOf takes integer slot returns integer
    if udg_mode_6v6 then
        if (slot >= 1 and slot <= 3) or (slot >= 10 and slot <= 12) then
            return 1
        endif
        return 2
    endif
    return (slot - 1) / 3 + 1
endfunction

function FF_IsMember takes integer slot, integer side returns boolean
    return FF_SideOf(slot) == side
endfunction

function FF_SideLabel takes integer side returns string
    if udg_mode_6v6 then
        if side == 1 then
            return "west"
        endif
        return "east"
    endif
    return "team" + I2S(side)
endfunction
