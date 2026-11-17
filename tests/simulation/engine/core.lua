-- Engine core: handles, the native stubs from common.j, and the game clock with its threads.
--
-- A game "thread" is a Lua coroutine: trigger actions and ExecuteFunc run in one and may wait
-- (TriggerSleepAction); conditions, filters and timer callbacks are plain calls that cannot.
local W = ...

-- ---------------------------------------------------------------------------------------------
-- handles
-- ---------------------------------------------------------------------------------------------
local nextHandle = 0x100000

--- A new engine object of `kind` (unit, timer, ...) with a unique handle id.
function W.H(kind, t)
    t = t or {}
    t.__kind = kind
    t.__id = nextHandle
    nextHandle = nextHandle + 1
    return t
end
local H = W.H

-- Convert* constants (EVENT_*, PLAYER_STATE_*, UNIT_TYPE_*, ...) are interned per kind + id, so the
-- globals common.lua defines are the same objects the natives hand back.
local consts = {}

--- The interned constant `kind:id`.
function W.const(kind, id)
    local k = kind .. ":" .. tostring(id)
    if not consts[k] then consts[k] = H(kind, { const = true, cid = id }) end
    return consts[k]
end

-- JASS concatenates a null string as "" (the map relies on it); Lua would raise.
debug.setmetatable(nil, { __concat = function(a, b) return (a == nil and "" or a) .. (b == nil and "" or b) end })

-- JASS string arrays start out null (the editor's InitGlobals sets the udg_ ones to "" itself);
-- the transpiler declares them with "".
function __jarray(default)
    if default == "" then default = nil end
    return setmetatable({}, { __index = function() return default end })
end

-- ---------------------------------------------------------------------------------------------
-- native stubs from common.j: typed defaults, unmodelled calls counted
-- ---------------------------------------------------------------------------------------------
T.unmodelled = {}

local function defaultFor(name, rt)
    if rt == "nothing" or rt == "code" then return nil end
    if rt == "integer" then return 0 end
    if rt == "real" then return 0.0 end
    if rt == "boolean" then return false end
    if rt == "string" then return "" end
    -- handles: getters find nothing; constructors hand out a fresh opaque handle
    if name:match("^Get") or name:match("^BlzGet") or name:match("^First") or name:match("^Load") then
        return nil
    end
    return H(rt)
end

--- Gives every native declared in common.j a stub, unless a module already models it.
function W.loadNatives(commonJPath)
    for line in io.lines(commonJPath) do
        local name, rt = line:match("^%s*constant%s+native%s+([%w_]+)%s+takes.-returns%s+([%w_]+)")
        if not name then name, rt = line:match("^%s*native%s+([%w_]+)%s+takes.-returns%s+([%w_]+)") end
        if name then
            if name:match("^Convert") then
                local kind = rt
                _G[name] = function(i) return W.const(kind, i) end
            elseif type(_G[name]) ~= "function" then
                _G[name] = function()
                    T.unmodelled[name] = (T.unmodelled[name] or 0) + 1
                    return defaultFor(name, rt)
                end
            end
        end
    end
end

--- Names the constants (EVENT_PLAYER_UNIT_DEATH, ...) after common.lua ran, for readable dispatch.
function W.nameConstants()
    for k, v in pairs(_G) do
        if type(v) == "table" and v.const and not v.name then v.name = k end
    end
end

-- ---------------------------------------------------------------------------------------------
-- clock, threads, scheduler
-- ---------------------------------------------------------------------------------------------
W.now = 0.0
local queue = {}      -- { at, seq, fn }
local seq = 0

--- Runs `fn` when game time reaches `at` (ties in the order they were scheduled).
function W.schedule(at, fn)
    seq = seq + 1
    queue[#queue + 1] = { at = at, seq = seq, fn = fn }
end

-- Event context (GetTriggerUnit, GetEnumPlayer, ...): a thread's own context, overlaid by the
-- callbacks it runs (ForForce, ForGroup, filters) on that thread's own stack.
local threadCtx = setmetatable({}, { __mode = "k" })
local stacks = setmetatable({}, { __mode = "k" })
local mainKey = {}
local function stackOf()
    local co = coroutine.running()
    local k = co or mainKey
    if not stacks[k] then stacks[k] = {} end
    return stacks[k], co
end

--- The event context of the running code (GetTriggerUnit & co read it).
function W.ctx()
    local st, co = stackOf()
    if #st > 0 then return st[#st] end
    if co and threadCtx[co] then return threadCtx[co] end
    return {}
end

--- `fields` layered over the current context: a callback inside a trigger still sees its trigger's event.
function W.overlay(fields)
    return setmetatable(fields, { __index = W.ctx() })
end

-- Op limit: the game kills a thread that runs too long; here a slice that spins for more than
-- FF_SIM_SLICE seconds (default 5) errors with a traceback instead of hanging the test run.
local sliceLimit = tonumber(os.getenv("FF_SIM_SLICE") or "5")
local sliceStart, sliceDepth = nil, 0
local function opHook()
    if sliceStart and os.clock() - sliceStart > sliceLimit then
        sliceStart = os.clock()
        error("op limit: thread ran longer than " .. sliceLimit .. "s", 2)
    end
end
local function hook(co)
    if co then debug.sethook(co, opHook, "", 100000) else debug.sethook(opHook, "", 100000) end
end
hook()
local function enter() sliceDepth = sliceDepth + 1; if sliceDepth == 1 then sliceStart = os.clock() end end
local function leave() sliceDepth = sliceDepth - 1; if sliceDepth == 0 then sliceStart = nil end end

--- Records a script error; any error fails the scenario (in the game it silently ends that thread).
function W.report(err, where)
    T.errors = T.errors or {}
    T.errors[#T.errors + 1] = (where or "?") .. ": " .. tostring(err)
end

local function resumeThread(co)
    local depth, start = sliceDepth, sliceStart
    enter()
    local ok, err = coroutine.resume(co)
    sliceDepth, sliceStart = depth, start      -- a thread may yield from inside nested callbacks
    if not ok then W.report(debug.traceback(co, err), "thread") end
end

--- Runs `fn` as a game thread (trigger actions, ExecuteFunc) with event context `c`; it may wait.
function W.spawn(fn, c, where)
    local co = coroutine.create(function() fn() end)
    hook(co)
    threadCtx[co] = c or W.ctx()
    resumeThread(co)
end

--- Calls `fn` with event context `c` (conditions, filters, timer callbacks): no waits possible.
function W.callWith(c, fn, where)
    local st = stackOf()
    st[#st + 1] = c
    enter()
    local ok, r = xpcall(fn, debug.traceback)
    leave()
    st[#st] = nil
    if not ok then W.report(r, where); return nil end
    return r
end

function TriggerSleepAction(s)
    local co = coroutine.running()
    if not co or not threadCtx[co] then return end
    W.schedule(W.now + math.max(s, 0), function() resumeThread(co) end)
    coroutine.yield()
end

function ExecuteFunc(name)
    local fn = _G[name]
    if type(fn) ~= "function" then W.report("ExecuteFunc: no function " .. tostring(name), "ExecuteFunc") return end
    W.spawn(fn, W.ctx(), "ExecuteFunc " .. name)
end

--- Advances game time by `sec`, running due timers and waking sleeping threads in time order.
function T.advance(sec)
    local target = W.now + (sec or 0)
    while true do
        local best, bi = nil, nil
        for i, e in ipairs(queue) do
            if e.at <= target + 1e-9 and (not best or e.at < best.at - 1e-9 or (math.abs(e.at - best.at) <= 1e-9 and e.seq < best.seq)) then
                best, bi = e, i
            end
        end
        if not best then break end
        table.remove(queue, bi)
        if best.at > W.now then W.now = best.at end
        best.fn()
    end
    W.now = target
end

-- ---------------------------------------------------------------------------------------------
-- boolexprs
-- ---------------------------------------------------------------------------------------------
function Condition(fn) return fn and H("boolexpr", { fn = fn }) or nil end
function Filter(fn) return fn and H("boolexpr", { fn = fn }) or nil end
function DestroyBoolExpr() end
function DestroyCondition() end
function DestroyFilter() end
function And(a, b) return H("boolexpr", { fn = function() return a.fn() and b.fn() end }) end
function Or(a, b) return H("boolexpr", { fn = function() return a.fn() or b.fn() end }) end
function Not(a) return H("boolexpr", { fn = function() return not a.fn() end }) end
