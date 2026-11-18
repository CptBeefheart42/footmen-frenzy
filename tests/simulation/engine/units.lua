-- Unit types, units, items, unit groups and map geometry (locations, rects).
local W = ...
local H = W.H

--- The integer object id of a four-letter code ("hfoo"); numbers pass through.
function W.s2id(s)
    if type(s) == "number" then return s end
    local n = 0
    for i = 1, 4 do n = n * 256 + s:byte(i) end
    return n
end
--- The four-letter code of an object id.
function W.id2s(n)
    return string.char((n >> 24) & 255, (n >> 16) & 255, (n >> 8) & 255, n & 255)
end
local s2id, id2s = W.s2id, W.id2s
T.id, T.str = s2id, id2s
-- The game's own Lua native: the transpiled scripts write object codes as FourCC("hfoo").
FourCC = s2id

-- Per-type facts the script cannot read from the object data, declared by tests or unit_types.lua:
-- structure, townhall, summoned, ancient, mechanical, flying, peon, name, life, ifield = { [UNIT_IF_*] = v }.
-- A hero is a type whose code starts with a capital letter (WC3's own rule).
W.unitTypes = {}

--- Declares (or extends) the facts of unit type `code`.
function T.unitType(code, t)
    local id = s2id(code)
    W.unitTypes[id] = W.unitTypes[id] or {}
    for k, v in pairs(t) do W.unitTypes[id][k] = v end
end
local function typeInfo(id) return W.unitTypes[id] or {} end
local function isHeroId(id) local c = (id >> 24) & 255; return c >= 65 and c <= 90 end

W.allUnits = {}

--- A new unit of type `id` for player `p`; entering a region fires its events.
function W.newUnit(p, id, x, y, face)
    local ti = typeInfo(id)
    local u = H("unit", {
        owner = p, typeId = id, x = x or 0, y = y or 0, face = face or 0,
        life = ti.life or 100, maxLife = ti.life or 100, mana = 0, alive = true,
        hero = isHeroId(id), level = 1, xp = 0, abilities = {}, abilityLevel = {},
        ifield = {}, rfield = {}, illusion = false, paused = false, hidden = false,
        items = {}, userData = 0,
    })
    if ti.ifield then for k, v in pairs(ti.ifield) do u.ifield[k] = v end end
    W.allUnits[#W.allUnits + 1] = u
    W.checkRegions(u)
    return u
end
local newUnit = W.newUnit

local function moved(u) W.checkRegions(u) end

function CreateUnit(p, id, x, y, face) return newUnit(p, id, x, y, face) end
function CreateUnitByName(p, name, x, y, face) return nil end
function BlzCreateUnitWithSkin(p, id, x, y, face, skin) return newUnit(p, id, x, y, face) end
function CreateUnitAtLoc(p, id, loc, face) return newUnit(p, id, loc and loc.x, loc and loc.y, face) end
function CreateUnitAtLocByName() return nil end
function RemoveUnit(u) if u then u.removed = true; u.alive = false end end
function ShowUnit(u, show) if u then u.hidden = not show end end
function IsUnitHidden(u) return u and u.hidden or false end
function GetUnitTypeId(u) return u and u.typeId or 0 end
function GetOwningPlayer(u) return u and u.owner or nil end
-- immediate orders are recorded, in order, as `u.orders`
function IssueImmediateOrder(u, order)
    if not u then return false end
    u.orders = u.orders or {}
    u.orders[#u.orders + 1] = order
    return true
end
function SetUnitOwner(u, p, color) if u then u.owner = p end end
function GetUnitX(u) return u and u.x or 0.0 end
function GetUnitY(u) return u and u.y or 0.0 end
function SetUnitX(u, x) if u then u.x = x; moved(u) end end
function SetUnitY(u, y) if u then u.y = y; moved(u) end end
function SetUnitPosition(u, x, y) if u then u.x, u.y = x, y; moved(u) end end
function GetUnitLoc(u) return Location(GetUnitX(u), GetUnitY(u)) end
function SetUnitPositionLoc(u, l) if u and l then u.x, u.y = l.x, l.y; moved(u) end end
function GetUnitFacing(u) return u and u.face or 0.0 end
-- Move speed: unit types carry no speed here, so every unit starts at 270 (a footman's default); scripts may change it.
function GetUnitDefaultMoveSpeed(u) return u and 270.0 or 0.0 end
function GetUnitMoveSpeed(u) return u and (u.moveSpeed or 270.0) or 0.0 end
function SetUnitMoveSpeed(u, v) if u then u.moveSpeed = v end end
function GetUnitName(u) return u and (typeInfo(u.typeId).name or id2s(u.typeId)) or "" end
function GetObjectName(id) return typeInfo(id).name or id2s(id) end
function GetUnitLevel(u) return u and u.level or 0 end
function GetHeroLevel(u) return u and u.level or 0 end
function SetHeroLevel(u, l, fx) if u then u.level = l end end
function GetHeroXP(u) return u and u.xp or 0 end
function GetUnitUserData(u) return u and u.userData or 0 end
function SetUnitUserData(u, v) if u then u.userData = v end end
function IsUnitIllusion(u) return u and u.illusion or false end
function IsUnitPaused(u) return u and u.paused or false end
function PauseUnit(u, f) if u then u.paused = f end end
function UnitAlive(u) return u and u.alive or false end
function IsUnitAliveBJ(u) return u and u.alive or false end
function GetWidgetLife(u) return u and (u.alive and u.life or 0.0) or 0.0 end
function SetWidgetLife(u, v) if u then u.life = v end end
function GetUnitState(u, s)
    if not u then return 0.0 end
    if s == UNIT_STATE_LIFE then return u.alive and u.life or 0.0 end
    if s == UNIT_STATE_MAX_LIFE then return u.maxLife end
    if s == UNIT_STATE_MANA then return u.mana end
    return 0.0
end
function SetUnitState(u, s, v)
    if not u then return end
    if s == UNIT_STATE_LIFE then u.life = v elseif s == UNIT_STATE_MANA then u.mana = v end
end
function IsUnitType(u, t)
    if not u then return false end
    local ti = typeInfo(u.typeId)
    if t == UNIT_TYPE_HERO then return u.hero end
    if t == UNIT_TYPE_DEAD then return not u.alive end
    if t == UNIT_TYPE_STRUCTURE then return ti.structure or false end
    if t == UNIT_TYPE_TOWNHALL then return ti.townhall or false end
    if t == UNIT_TYPE_SUMMONED then return ti.summoned or u.summoned or false end
    if t == UNIT_TYPE_ANCIENT then return ti.ancient or false end
    if t == UNIT_TYPE_MECHANICAL then return ti.mechanical or false end
    if t == UNIT_TYPE_FLYING then return ti.flying or false end
    if t == UNIT_TYPE_GROUND then return not ti.flying end
    if t == UNIT_TYPE_PEON then return ti.peon or false end
    return false
end
function IsUnitIdType(id, t)
    if t == UNIT_TYPE_HERO then return isHeroId(id) end
    local ti = typeInfo(id)
    if t == UNIT_TYPE_STRUCTURE then return ti.structure or false end
    if t == UNIT_TYPE_TOWNHALL then return ti.townhall or false end
    return false
end
function IsHeroUnitId(id) return isHeroId(id) end
function IsUnitAlly(u, p) return u and IsPlayerAlly(u.owner, p) or false end
function IsUnitEnemy(u, p) return u and IsPlayerEnemy(u.owner, p) or false end
function IsUnitOwnedByPlayer(u, p) return u and u.owner == p or false end
function IsUnit(a, b) return a == b end
function IsUnitInRangeXY(u, x, y, r) return u and ((u.x - x) ^ 2 + (u.y - y) ^ 2) <= r * r or false end
function IsUnitInRange(a, b, r) return a and b and IsUnitInRangeXY(a, b.x, b.y, r) or false end
function UnitAddAbility(u, a) if u and not u.abilities[a] then u.abilities[a] = true; u.abilityLevel[a] = 1; return true end return false end
function UnitRemoveAbility(u, a) if u and u.abilities[a] then u.abilities[a] = nil; return true end return false end
function GetUnitAbilityLevel(u, a) return u and u.abilities[a] and (u.abilityLevel[a] or 1) or 0 end
function SetUnitAbilityLevel(u, a, l) if u then u.abilities[a] = true; u.abilityLevel[a] = l end return l end
function BlzGetUnitIntegerField(u, f) return u and (u.ifield[f] or 0) or 0 end
function BlzSetUnitIntegerField(u, f, v) if u then u.ifield[f] = v end return true end
function BlzGetUnitRealField(u, f) return u and (u.rfield[f] or 0.0) or 0.0 end
function BlzSetUnitRealField(u, f, v) if u then u.rfield[f] = v end return true end
function KillUnit(u) T.kill(u, nil) end

-- Timed life: at expiry the unit dies with no killer (like the engine). A type declared with
-- `removeAfter = s` (a short death time, e.g. a locust dummy) is gone `s` later, so its handle is dead
-- AND removed by then. A later call replaces the earlier timer, as in the game.
function UnitApplyTimedLife(u, buff, secs)
    if not u then return end
    local token = {}
    u.timedLife = token
    W.schedule(W.now + math.max(secs, 0), function()
        if u.timedLife ~= token or not u.alive then return end
        T.kill(u, nil)
        local after = typeInfo(u.typeId).removeAfter
        if after then W.schedule(W.now + after, function() RemoveUnit(u) end) end
    end)
end

-- Ability level fields the script reads back (spell durations): declared per ability code, since the
-- object data is not loaded. T.abilityType("ANso", { rlf = { adur = { [6] = 10.0 } } }); unknown = 0.
W.abilityTypes = {}

--- Declares (or extends) the level-field facts of ability `code`: rlf = { <field code> = { [level] = v } }.
function T.abilityType(code, t)
    local id = s2id(code)
    W.abilityTypes[id] = W.abilityTypes[id] or { rlf = {} }
    for field, levels in pairs(t.rlf or {}) do W.abilityTypes[id].rlf[s2id(field)] = levels end
end

--- The declared value of real level field `field` (a code like "adur") of ability `code` at `level` (1-based).
function T.abilityReal(code, field, level)
    local a = W.abilityTypes[s2id(code)]
    local v = a and a.rlf[s2id(field)] and a.rlf[s2id(field)][level]
    return v or 0.0
end

function BlzGetUnitAbility(u, a)
    if not (u and u.abilities[a]) then return nil end
    u.abilityHandles = u.abilityHandles or {}
    u.abilityHandles[a] = u.abilityHandles[a] or H("ability", { id = a })
    return u.abilityHandles[a]
end
function BlzGetAbilityRealLevelField(ab, field, level)
    return ab and T.abilityReal(ab.id, field.cid, level + 1) or 0.0
end
function GetUnitFoodUsed() return 0 end

-- ---------------------------------------------------------------------------------------------
-- items: a unit carries up to six, in inventory slots 0..5
-- ---------------------------------------------------------------------------------------------
local INVENTORY = 6

--- A new item of type `id` lying at x, y.
function W.newItem(id, x, y) return H("item", { typeId = id, x = x or 0, y = y or 0, removed = false }) end

local function drop(i)
    local u = i.holder
    if not u then return end
    for s = 0, INVENTORY - 1 do if u.items[s] == i then u.items[s] = nil end end
    i.holder = nil
end

function CreateItem(id, x, y) return W.newItem(id, x, y) end
function BlzCreateItemWithSkin(id, x, y, s) return W.newItem(id, x, y) end
function RemoveItem(i) if i then drop(i); i.removed = true end end
function GetItemTypeId(i) return i and i.typeId or 0 end
function GetItemX(i) return i and i.x or 0.0 end
function GetItemY(i) return i and i.y or 0.0 end
function GetItemName(i) return i and id2s(i.typeId) or "" end
function UnitInventorySize(u) return INVENTORY end
function UnitItemInSlot(u, s) return u and u.items[s] or nil end
function UnitAddItem(u, i)
    if not (u and i) then return false end
    for s = 0, INVENTORY - 1 do
        if not u.items[s] then drop(i); u.items[s] = i; i.holder = u; return true end
    end
    return false
end
function UnitRemoveItem(u, i) if i and i.holder == u then drop(i) end end

-- ---------------------------------------------------------------------------------------------
-- shop stock: unit.stock = { [unit or item type] = { current =, max = } }
-- ---------------------------------------------------------------------------------------------
local function setStock(u, id, cur, max)
    if not u then return end
    u.stock = u.stock or {}
    u.stock[id] = { current = cur, max = max }
end
local function unstock(u, id) if u and u.stock then u.stock[id] = nil end end
function AddUnitToStock(u, id, cur, max) setStock(u, id, cur, max) end
function AddItemToStock(u, id, cur, max) setStock(u, id, cur, max) end
function RemoveUnitFromStock(u, id) unstock(u, id) end
function RemoveItemFromStock(u, id) unstock(u, id) end

-- ---------------------------------------------------------------------------------------------
-- groups
-- ---------------------------------------------------------------------------------------------
-- Every group and location ever made, so a test can count the ones still alive (leaks: T.live).
W.allGroups, W.allLocations = {}, {}
function CreateGroup()
    local g = H("group", { list = {} })
    W.allGroups[#W.allGroups + 1] = g
    return g
end
-- A destroyed group stays empty: adding to it or filling it does nothing, as with a dead handle in the game.
function DestroyGroup(g) if g then g.destroyed = true; g.list = {} end end
function GroupAddUnit(g, u)
    if not (g and u) or g.destroyed then return false end
    for _, v in ipairs(g.list) do if v == u then return false end end
    g.list[#g.list + 1] = u
    return true
end
function GroupRemoveUnit(g, u)
    if not (g and u) then return false end
    for i, v in ipairs(g.list) do if v == u then table.remove(g.list, i) return true end end
    return false
end
function GroupClear(g) if g then g.list = {} end end
function IsUnitInGroup(u, g) if g then for _, v in ipairs(g.list) do if v == u then return true end end end return false end
function FirstOfGroup(g)
    if not g then return nil end
    for _, v in ipairs(g.list) do if not v.removed then return v end end
    return nil
end
function BlzGroupGetSize(g) return g and #g.list or 0 end
function BlzGroupUnitAt(g, i) return g and g.list[i + 1] or nil end
function ForGroup(g, fn)
    if not g then return end
    local list = {}
    for i, u in ipairs(g.list) do list[i] = u end
    for _, u in ipairs(list) do
        if not u.removed then W.callWith(W.overlay({ enumUnit = u }), fn, "ForGroup") end
    end
end

-- Adds every unit that passes `pred` and the boolexpr `filter` to group `g`.
local function groupEnum(g, filter, pred)
    if not g or g.destroyed then return end
    for _, u in ipairs(W.allUnits) do
        if not u.removed and pred(u) then
            local keep = true
            if filter then
                keep = W.callWith(W.overlay({ filterUnit = u }), function() return filter.fn() end, "GroupEnum filter")
            end
            if keep then GroupAddUnit(g, u) end
        end
    end
end
function GroupEnumUnitsOfPlayer(g, p, filter) groupEnum(g, filter, function(u) return u.owner == p end) end
function GroupEnumUnitsOfType(g, name, filter) groupEnum(g, filter, function(u) return GetUnitName(u) == name end) end
function GroupEnumUnitsInRange(g, x, y, r, filter) groupEnum(g, filter, function(u) return IsUnitInRangeXY(u, x, y, r) end) end
function GroupEnumUnitsInRangeOfLoc(g, l, r, filter) GroupEnumUnitsInRange(g, l.x, l.y, r, filter) end
function GroupEnumUnitsInRect(g, rect, filter)
    groupEnum(g, filter, function(u)
        return rect and u.x >= rect.minx and u.x <= rect.maxx and u.y >= rect.miny and u.y <= rect.maxy
    end)
end
function GroupEnumUnitsSelected() end
function GetEnumUnit() return W.ctx().enumUnit end
function GetFilterUnit() return W.ctx().filterUnit end

-- ---------------------------------------------------------------------------------------------
-- geometry
-- ---------------------------------------------------------------------------------------------
function Location(x, y)
    local l = H("location", { x = x, y = y })
    W.allLocations[#W.allLocations + 1] = l
    return l
end
-- A removed location reads as (0, 0), as a dead handle does in the game; `removed` lets a test see it.
function RemoveLocation(l) if l then l.removed = true; l.x, l.y = 0.0, 0.0 end end
function MoveLocation(l, x, y) l.x, l.y = x, y end
function GetLocationX(l) return l and l.x or 0.0 end
function GetLocationY(l) return l and l.y or 0.0 end
function GetLocationZ() return 0.0 end
function Rect(a, b, c, d) return H("rect", { minx = a, miny = b, maxx = c, maxy = d }) end
function RectFromLoc(a, b) return Rect(a.x, a.y, b.x, b.y) end
function SetRect(r, a, b, c, d) r.minx, r.miny, r.maxx, r.maxy = a, b, c, d end
function RemoveRect() end
function GetRectMinX(r) return r and r.minx or 0.0 end
function GetRectMinY(r) return r and r.miny or 0.0 end
function GetRectMaxX(r) return r and r.maxx or 0.0 end
function GetRectMaxY(r) return r and r.maxy or 0.0 end
function GetRectCenterX(r) return r and (r.minx + r.maxx) / 2 or 0.0 end
function GetRectCenterY(r) return r and (r.miny + r.maxy) / 2 or 0.0 end
function GetWorldBounds() return Rect(-8192, -8192, 8192, 8192) end
function GetEntireMapRect() return Rect(-8192, -8192, 8192, 8192) end
-- the local player's camera bounds (W.cameraBounds, a rect): set by the map's config and triggers
local function setCameraBounds(minx, miny, maxx, maxy)
    W.cameraBounds = { minx = minx, miny = miny, maxx = maxx, maxy = maxy }
end
function SetCameraBounds(x1, y1, x2, y2, x3, y3, x4, y4)
    setCameraBounds(math.min(x1, x2, x3, x4), math.min(y1, y2, y3, y4), math.max(x1, x2, x3, x4), math.max(y1, y2, y3, y4))
end
function SetCameraBoundsToRect(r) setCameraBounds(r.minx, r.miny, r.maxx, r.maxy) end
local function cameraBound(k, default) return W.cameraBounds and W.cameraBounds[k] or default end
function GetCameraBoundMinX() return cameraBound("minx", -8192.0) end
function GetCameraBoundMinY() return cameraBound("miny", -8192.0) end
function GetCameraBoundMaxX() return cameraBound("maxx", 8192.0) end
function GetCameraBoundMaxY() return cameraBound("maxy", 8192.0) end
function GetStartLocationX(i) return 0.0 end
function GetStartLocationY(i) return 0.0 end
function GetStartLocationLoc(i) return Location(0, 0) end
