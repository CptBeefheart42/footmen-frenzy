-- Timers, hashtables, strings, math and the random number generator.
local W = ...
local H = W.H

-- ---------------------------------------------------------------------------------------------
-- timers: `timeout` is the period; `due` is the length of the countdown that runs right now
-- (shorter than the period after ResumeTimer)
-- ---------------------------------------------------------------------------------------------
local function arm(t, due)
    t.gen = t.gen + 1
    local gen = t.gen
    t.running, t.start, t.due = true, W.now, due
    local function expire()
        if t.gen ~= gen or t.destroyed then return end
        if t.periodic then arm(t, math.max(t.timeout, 0.0001)) else t.running = false end
        if t.fn then W.callWith({ timer = t }, t.fn, "timer") end
        for _, tr in ipairs(t.expireTrigs or {}) do W.runTrigger(tr, { timer = t }) end
    end
    W.schedule(W.now + due, expire)
end

function CreateTimer() return H("timer", { gen = 0, running = false, timeout = 0, start = 0, due = 0 }) end
function DestroyTimer(t) if t then t.destroyed = true; t.running = false; t.gen = t.gen + 1 end end
function TimerStart(t, timeout, periodic, fn)
    if not t then return end
    t.timeout, t.periodic, t.fn = timeout, periodic, fn
    arm(t, timeout)
end
function TimerGetRemaining(t) return t and t.running and math.max(t.due - (W.now - t.start), 0) or 0.0 end
function TimerGetElapsed(t) return t and t.running and (t.timeout - TimerGetRemaining(t)) or 0.0 end
function TimerGetTimeout(t) return t and t.timeout or 0.0 end
function PauseTimer(t) if t then t.remaining = TimerGetRemaining(t); t.running = false; t.gen = t.gen + 1 end end
function ResumeTimer(t) if t and t.remaining then arm(t, t.remaining) end end
function CreateTimerDialog() return H("timerdialog") end

-- ---------------------------------------------------------------------------------------------
-- hashtables: one store per value kind (integer, real, boolean, string, handle)
-- ---------------------------------------------------------------------------------------------
local KINDS = { "i", "r", "b", "s", "h" }
function InitHashtable() return H("hashtable", { i = {}, r = {}, b = {}, s = {}, h = {} }) end
local function hget(ht, kind, p, c) local t = ht[kind][p]; return t and t[c] end
local function hset(ht, kind, p, c, v) ht[kind][p] = ht[kind][p] or {}; ht[kind][p][c] = v end
local function hhave(ht, kind, p, c) return hget(ht, kind, p, c) ~= nil end
function SaveInteger(ht, p, c, v) hset(ht, "i", p, c, v) end
function SaveReal(ht, p, c, v) hset(ht, "r", p, c, v) end
function SaveBoolean(ht, p, c, v) hset(ht, "b", p, c, v) end
function SaveStr(ht, p, c, v) hset(ht, "s", p, c, v); return true end
function LoadInteger(ht, p, c) return hget(ht, "i", p, c) or 0 end
function LoadReal(ht, p, c) return hget(ht, "r", p, c) or 0.0 end
function LoadBoolean(ht, p, c) return hget(ht, "b", p, c) or false end
function LoadStr(ht, p, c) return hget(ht, "s", p, c) or "" end
function HaveSavedInteger(ht, p, c) return hhave(ht, "i", p, c) end
function HaveSavedReal(ht, p, c) return hhave(ht, "r", p, c) end
function HaveSavedBoolean(ht, p, c) return hhave(ht, "b", p, c) end
function HaveSavedString(ht, p, c) return hhave(ht, "s", p, c) end
function HaveSavedHandle(ht, p, c) return hhave(ht, "h", p, c) end
function RemoveSavedInteger(ht, p, c) hset(ht, "i", p, c, nil) end
function RemoveSavedReal(ht, p, c) hset(ht, "r", p, c, nil) end
function RemoveSavedBoolean(ht, p, c) hset(ht, "b", p, c, nil) end
function RemoveSavedString(ht, p, c) hset(ht, "s", p, c, nil) end
function RemoveSavedHandle(ht, p, c) hset(ht, "h", p, c, nil) end
function FlushChildHashtable(ht, p) for _, k in ipairs(KINDS) do ht[k][p] = nil end end
function FlushParentHashtable(ht) for _, k in ipairs(KINDS) do ht[k] = {} end end
-- every Save*Handle / Load*Handle shares the handle store
for _, name in ipairs({ "Unit", "Item", "Timer", "Trigger", "Group", "Player", "Force", "Location",
    "Rect", "Effect", "Widget", "Destructable", "Region", "Fogmodifier", "Hashtable",
    "TriggerCondition", "TriggerAction", "TriggerEvent", "BooleanExpr", "Sound", "Lightning",
    "TextTag", "Multiboard", "MultiboardItem", "Dialog", "Button", "Quest", "QuestItem",
    "Leaderboard", "Image", "Ubersplat", "TimerDialog", "Trackable", "DefeatCondition",
    "FogState", "UnitPool", "ItemPool", "FrameHandle", "AbilityHandle", "ItemHandle", "UnitHandle" }) do
    _G["Save" .. name .. "Handle"] = function(ht, p, c, v) hset(ht, "h", p, c, v); return true end
    _G["Load" .. name .. "Handle"] = function(ht, p, c) return hget(ht, "h", p, c) end
end
function GetHandleId(h) return h and h.__id or 0 end

-- ---------------------------------------------------------------------------------------------
-- strings + math
-- ---------------------------------------------------------------------------------------------
function I2S(i) return string.format("%d", math.tointeger(i) or math.floor(i)) end
function R2S(r) return string.format("%.3f", r) end
function R2SW(r, w, p) return string.format("%" .. w .. "." .. p .. "f", r) end
function I2R(i) return i + 0.0 end
function R2I(r) local v = math.tointeger(r >= 0 and math.floor(r) or math.ceil(r)); return v or 0 end
function S2I(s) local n = s and s:match("^%s*([+-]?%d+)"); return n and math.tointeger(tonumber(n)) or 0 end
function S2R(s) local n = s and s:match("^%s*([+-]?%d*%.?%d+)"); return n and tonumber(n) + 0.0 or 0.0 end
function StringLength(s) return s and #s or 0 end
function SubString(s, a, b)
    if not s then return nil end
    -- past the end the game returns null, not "" (the map's name scan only terminates that way)
    if a > #s then return nil end
    if a < 0 then a = 0 end
    if b > #s then b = #s end
    if b <= a then return "" end
    return s:sub(a + 1, b)
end
function StringCase(s, upper) if not s then return nil end return upper and s:upper() or s:lower() end
function StringHash(s)
    local h = 0
    for i = 1, #(s or "") do h = (h * 31 + s:byte(i)) & 0xffffffff end
    if h >= 0x80000000 then h = h - 0x100000000 end
    return h
end
function GetLocalizedString(s) return s end
function GetLocalizedHotkey() return 0 end
function Sin(x) return math.sin(x) end
function Cos(x) return math.cos(x) end
function Tan(x) return math.tan(x) end
function Asin(x) return math.asin(x) end
function Acos(x) return math.acos(x) end
function Atan(x) return math.atan(x) end
function Atan2(y, x) return math.atan(y, x) end
function SquareRoot(x) return x > 0 and math.sqrt(x) or 0.0 end
function Pow(a, b) return a ^ b end
function Deg2Rad(d) return d * math.pi / 180 end
function Rad2Deg(r) return r * 180 / math.pi end

-- deterministic random numbers: every scenario starts from the same seed
local rng = 12345
local function rnd() rng = (rng * 1103515245 + 12345) & 0x7fffffff; return rng end
function GetRandomInt(a, b) if b < a then a, b = b, a end return a + rnd() % (b - a + 1) end
function GetRandomReal(a, b) return a + (rnd() / 0x7fffffff) * (b - a) end
function SetRandomSeed(s) rng = s & 0x7fffffff end
