-- Players and forces (player groups).
local W = ...
local H = W.H

local players = {}

--- Player `i` (0-based, like Player(i)), created on first use.
function W.P(i)
    if not players[i] then
        players[i] = H("player", {
            id = i, name = "Player " .. (i + 1), team = 0, startLoc = i, race = nil,
            state = {}, score = {}, tech = {}, alliance = {}, slot = nil, controller = nil,
            observer = false,
        })
    end
    return players[i]
end
local P = W.P

function Player(i) return P(i) end
function GetPlayerId(p) return p and p.id or -1 end
function GetPlayerName(p) return p and p.name or "" end
function SetPlayerName(p, n) if p then p.name = n end end
function GetPlayerTeam(p) return p and p.team or 0 end
function SetPlayerTeam(p, t) if p then p.team = t end end
function GetPlayerStartLocation(p) return p and p.startLoc or 0 end
function SetPlayerStartLocation(p, l) if p then p.startLoc = l end end
function ForcePlayerStartLocation(p, l) if p then p.startLoc = l end end
function GetPlayerSlotState(p) return p and p.slot or PLAYER_SLOT_STATE_EMPTY end
-- The map's own victory / defeat (CustomVictoryBJ / CustomDefeatBJ end in RemovePlayer): W.victories[slot] /
-- W.defeats[slot] = true, so a scenario can compare the map's verdict with ff_result's.
W.victories, W.defeats = {}, {}
function RemovePlayer(p, result)
    if not p then return end
    local slot = p.id + 1
    if result == PLAYER_GAME_RESULT_VICTORY then W.victories[slot] = true
    elseif result == PLAYER_GAME_RESULT_DEFEAT then W.defeats[slot] = true end
end
function GetPlayerController(p) return p and p.controller or MAP_CONTROL_NONE end
function SetPlayerController(p, c) if p and not p.controllerLocked then p.controller = c end end
function GetPlayerRace(p) return p and p.race or RACE_HUMAN end
function SetPlayerRacePreference() end
function GetPlayerState(p, s) return p and p.state[s] or 0 end
function SetPlayerState(p, s, v) if p then p.state[s] = v end end
function GetPlayerScore(p, s) return p and p.score[s] or 0 end
function GetPlayerTechCount(p, id, specific) return p and p.tech[id] or 0 end
function GetPlayerTechResearched(p, id, specific) return p and (p.tech[id] or 0) > 0 or false end
function SetPlayerTechResearched(p, id, lvl) if p then p.tech[id] = lvl end end
function AddPlayerTechResearched(p, id, lvl) if p then p.tech[id] = (p.tech[id] or 0) + lvl end end
-- tech limits (SetPlayerMaxHeroesAllowed is SetPlayerTechMaxAllowed(p, 'HERO', n)); -1 = no limit, as in the game
function GetPlayerTechMaxAllowed(p, id) return p and p.techMax and p.techMax[id] or -1 end
function SetPlayerTechMaxAllowed(p, id, n) if p then p.techMax = p.techMax or {}; p.techMax[id] = n end end
function SetPlayerAlliance(a, b, t, v)
    if not (a and b) then return end
    a.alliance[b] = a.alliance[b] or {}
    a.alliance[b][t] = v
end
function GetPlayerAlliance(a, b, t)
    if not (a and b) then return false end
    return (a.alliance[b] and a.alliance[b][t]) or false
end
function IsPlayerAlly(a, b)
    if a == nil or b == nil then return false end
    if a == b then return true end
    return GetPlayerAlliance(a, b, ALLIANCE_PASSIVE)
end
function IsPlayerEnemy(a, b) return not IsPlayerAlly(a, b) end
function GetLocalPlayer() return P(W.localPlayer or 0) end
function GetBJMaxPlayers() return 24 end
function GetBJMaxPlayerSlots() return 28 end
function GetBJPlayerNeutralVictim() return 25 end
function GetBJPlayerNeutralExtra() return 26 end
function GetPlayerNeutralPassive() return 27 end
function GetPlayerNeutralAggressive() return 24 end
-- The lobby screen's player / team counts; the map's config sets up its own slots and teams.
function GetPlayers() return 12 end
function GetTeams() return 2 end
function SetPlayers(n) end
function SetTeams(n) end
function IsPlayerObserver(p) return p and p.observer or false end
function GetPlayerHandicap() return 1.0 end
function GetPlayerColor(p) return W.const("playercolor", p and p.id or 0) end
function SetPlayerColor() end
function IsPlayerRacePrefSet() return false end
function GetPlayerSelectable() return true end
-- Map flags (resource trading lock, allies-only trading, ...): what SetMapFlag set last; unset is false.
W.mapFlags = {}
function SetMapFlag(f, on) W.mapFlags[f] = on or nil end
function IsMapFlagSet(f) return W.mapFlags[f] or false end
function SetPlayerOnScoreScreen() end

-- ---------------------------------------------------------------------------------------------
-- forces
-- ---------------------------------------------------------------------------------------------
local function newForce() return H("force", { members = {}, order = {} }) end
function CreateForce() return newForce() end
function DestroyForce() end
function IsPlayerInForce(p, f) return f and f.members[p] or false end
function ForceAddPlayer(f, p)
    if f and p and not f.members[p] then f.members[p] = true; f.order[#f.order + 1] = p end
end
function ForceRemovePlayer(f, p)
    if not (f and p and f.members[p]) then return end
    f.members[p] = nil
    for i, q in ipairs(f.order) do if q == p then table.remove(f.order, i) break end end
end
function ForceClear(f) f.members = {}; f.order = {} end

local function playing(p) return p.slot == PLAYER_SLOT_STATE_PLAYING end
local function enumPlayers(f, filter, pred)
    for i = 0, 27 do
        local p = P(i)
        if pred(p) then
            local keep = true
            if filter then
                keep = W.callWith(W.overlay({ filterPlayer = p }), function() return filter.fn() end, "ForceEnum filter")
            end
            if keep then ForceAddPlayer(f, p) end
        end
    end
end
function ForceEnumPlayers(f, filter) enumPlayers(f, filter, playing) end
function ForceEnumPlayersCounted(f, filter, n) ForceEnumPlayers(f, filter) end
function ForceEnumAllies(f, p, filter) enumPlayers(f, filter, function(q) return playing(q) and IsPlayerAlly(q, p) end) end
function ForceEnumEnemies(f, p, filter) enumPlayers(f, filter, function(q) return playing(q) and IsPlayerEnemy(q, p) end) end
function ForForce(f, fn)
    if not f then return end
    local list = {}
    for i, p in ipairs(f.order) do list[i] = p end
    for _, p in ipairs(list) do W.callWith(W.overlay({ enumPlayer = p }), fn, "ForForce") end
end
function GetEnumPlayer() return W.ctx().enumPlayer end
function GetFilterPlayer() return W.ctx().filterPlayer end

-- Every player slot, built on first use (after the map's config named them).
local allForce = nil
function GetPlayersAll()
    if not allForce then
        allForce = newForce()
        for i = 0, 27 do ForceAddPlayer(allForce, P(i)) end
    end
    return allForce
end
