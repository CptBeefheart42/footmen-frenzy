-- Triggers and their events, the event-response natives, regions and dialogs.
--
-- A registration ties a trigger to an event, optionally scoped to a player, a unit, a region or a
-- dialog. Firing an event runs every matching registration the way the engine does: the trigger
-- must be enabled, its conditions must pass, then each action runs in its own game thread.
local W = ...
local H = W.H

local regs = {}       -- event name -> list of registrations { trig, ev, player, unit, region, filter, ... }

local function addReg(ev, r)
    local name = ev and ev.name or "?"
    regs[name] = regs[name] or {}
    r.ev = ev
    regs[name][#regs[name] + 1] = r
    return H("event")
end

--- A copy of the registrations for `evName`: a trigger may register more while one fires.
function W.regsOf(evName)
    local snapshot = {}
    for i, r in ipairs(regs[evName] or {}) do snapshot[i] = r end
    return snapshot
end

function CreateTrigger() return H("trigger", { conds = {}, actions = {}, enabled = true, evals = 0, execs = 0 }) end
function DestroyTrigger(t) if t then t.destroyed = true end end
function EnableTrigger(t) if t then t.enabled = true end end
function DisableTrigger(t) if t then t.enabled = false end end
function IsTriggerEnabled(t) return t and t.enabled or false end
function TriggerAddCondition(t, c) if t and c then t.conds[#t.conds + 1] = c end return H("triggercondition") end
function TriggerClearConditions(t) if t then t.conds = {} end end
function TriggerRemoveCondition() end
function TriggerAddAction(t, fn) if t and fn then t.actions[#t.actions + 1] = fn end return H("triggeraction") end
function TriggerClearActions(t) if t then t.actions = {} end end
function TriggerRemoveAction() end
function ResetTrigger(t) end
function GetTriggerEvalCount(t) return t and t.evals or 0 end
function GetTriggerExecCount(t) return t and t.execs or 0 end
function TriggerWaitOnSleeps() end
function GetTriggeringTrigger() return W.ctx().trigger end
function GetTriggerEventId() return W.ctx().eventId end

local function conditionsPass(t, c)
    t.evals = t.evals + 1
    for _, cond in ipairs(t.conds) do
        if not W.callWith(c, cond.fn, "condition") then return false end
    end
    return true
end
local function runActions(t, c)
    t.execs = t.execs + 1
    for _, fn in ipairs(t.actions) do W.spawn(fn, c, "action") end
end

function TriggerEvaluate(t) return t and conditionsPass(t, W.ctx()) or false end
-- An executed trigger keeps the caller's event responses, but is itself the triggering trigger (so its own
-- DestroyTrigger(GetTriggeringTrigger()) destroys it); a destroyed trigger no longer runs.
function TriggerExecute(t) if t and not t.destroyed then runActions(t, W.overlay({ trigger = t })) end end
function TriggerExecuteWait(t) TriggerExecute(t) end

--- Fires trigger `t` with event context `c`: enabled + conditions, then the actions as threads.
function W.runTrigger(t, c)
    if t.destroyed or not t.enabled then return end
    c.trigger = t
    if conditionsPass(t, c) then runActions(t, c) end
end

--- Fires one registration `r` with (a copy of) event context `c`, through its filter if it has one.
function W.fireReg(r, c)
    local cc = {}
    for k, v in pairs(c) do cc[k] = v end
    cc.eventId = r.ev
    if r.filter then
        local fc = setmetatable({ filterUnit = cc.unit, filterPlayer = cc.player }, { __index = cc })
        if not W.callWith(fc, function() return r.filter.fn() end, "event filter") then return end
    end
    W.runTrigger(r.trig, cc)
end

--- Fires event `evName` to every registration that `match` accepts (all of them without `match`).
function W.fire(evName, c, match)
    for _, r in ipairs(W.regsOf(evName)) do
        if not match or match(r) then W.fireReg(r, c) end
    end
end

--- Fires a unit event: unit-scoped registrations of `unit`, player-scoped ones of its owner, and global ones.
--- The triggering player is the unit's owner, as GetTriggerPlayer returns it for player-unit events.
function W.fireUnit(evName, unit, c)
    c.unit = unit
    local owner = unit and unit.owner
    if c.player == nil then c.player = owner end
    W.fire(evName, c, function(r)
        if r.unit then return r.unit == unit end
        if r.player then return r.player == owner end
        return true
    end)
end

function TriggerRegisterPlayerUnitEvent(t, p, ev, filter) return addReg(ev, { trig = t, player = p, filter = filter }) end
function TriggerRegisterPlayerEvent(t, p, ev) return addReg(ev, { trig = t, player = p }) end
function TriggerRegisterUnitEvent(t, u, ev) return addReg(ev, { trig = t, unit = u }) end
function TriggerRegisterPlayerChatEvent(t, p, s, exact) return addReg(EVENT_PLAYER_CHAT, { trig = t, player = p, text = s, exact = exact }) end
function TriggerRegisterGameEvent(t, ev) return addReg(ev, { trig = t }) end
function TriggerRegisterTimerEvent(t, timeout, periodic)
    local delay = math.max(timeout, 0.0001)   -- a 0 s periodic event would never let game time advance
    local function tick()
        if t.destroyed then return end
        W.runTrigger(t, {})
        if periodic then W.schedule(W.now + delay, tick) end
    end
    W.schedule(W.now + timeout, tick)
    return H("event")
end
function TriggerRegisterTimerExpireEvent(t, tm)
    tm.expireTrigs = tm.expireTrigs or {}
    tm.expireTrigs[#tm.expireTrigs + 1] = t
    return H("event")
end
function TriggerRegisterVariableEvent(t, name, op, v)
    W.varEvents = W.varEvents or {}
    W.varEvents[#W.varEvents + 1] = { trig = t, name = name, op = op, value = v }
    return H("event")
end

-- ---------------------------------------------------------------------------------------------
-- event responses
-- ---------------------------------------------------------------------------------------------
local function field(name, default) return function() local v = W.ctx()[name]; if v == nil then return default end return v end end
GetTriggerUnit = field("unit")
GetDyingUnit = field("unit")
GetKillingUnit = field("killer")
GetTriggerPlayer = field("player")
GetEventPlayerChatString = field("chat", "")
GetEventPlayerChatStringMatched = field("chatMatched", "")
GetSoldItem = field("soldItem")
GetSoldUnit = field("soldUnit")
GetSellingUnit = field("seller")
GetBuyingUnit = field("buyer")
GetManipulatingUnit = field("unit")
GetManipulatedItem = field("item")
GetResearched = field("research", 0)
GetResearchingUnit = field("unit")
GetLearnedSkill = field("skill", 0)
GetLearningUnit = field("unit")
GetLearnedSkillLevel = field("skillLevel", 0)
GetSpellAbilityId = field("spell", 0)
GetSpellAbilityUnit = field("unit")
GetSpellTargetUnit = field("target")
GetSpellTargetX = field("tx", 0.0)
GetSpellTargetY = field("ty", 0.0)
function GetSpellTargetLoc() return Location(GetSpellTargetX(), GetSpellTargetY()) end
function GetEventDamage() local h = W.ctx().hit return h and h.amount or 0.0 end
function BlzSetEventDamage(amount) local h = W.ctx().hit if h then h.amount = amount end end
GetEventDamageSource = field("source")
GetExpiredTimer = field("timer")
GetLevelingUnit = field("unit")
GetTrainedUnit = field("trained")
GetConstructedStructure = field("unit")
GetEnteringUnit = field("unit")
GetLeavingUnit = field("unit")
GetAttacker = field("attacker")
GetSummonedUnit = field("summoned")
GetSummoningUnit = field("unit")
GetOrderedUnit = field("unit")
GetIssuedOrderId = field("order", 0)

-- ---------------------------------------------------------------------------------------------
-- regions: enter / leave events fire when a unit is created inside one or moves across its edge
-- ---------------------------------------------------------------------------------------------
function CreateRegion() return H("region", { rects = {}, inside = {} }) end
function RegionAddRect(r, rect) if r and rect then r.rects[#r.rects + 1] = rect end end
function RegionClearRect(r, rect)
    if not r then return end
    for i, x in ipairs(r.rects) do if x == rect then table.remove(r.rects, i) break end end
end
function RemoveRegion() end
local function inRegion(r, x, y)
    for _, rc in ipairs(r.rects) do
        if x >= rc.minx and x <= rc.maxx and y >= rc.miny and y <= rc.maxy then return true end
    end
    return false
end
function IsUnitInRegion(r, u) return r and u and inRegion(r, u.x, u.y) or false end
function IsPointInRegion(r, x, y) return r and inRegion(r, x, y) or false end
function TriggerRegisterEnterRegion(t, r, f) return addReg({ name = "ENTER_REGION" }, { trig = t, region = r, filter = f }) end
function TriggerRegisterLeaveRegion(t, r, f) return addReg({ name = "LEAVE_REGION" }, { trig = t, region = r, filter = f }) end

--- Updates which registered regions unit `u` is inside and fires the enter / leave events it crossed.
function W.checkRegions(u)
    if u.removed then return end
    local crossed = {}    -- region -> "ENTER_REGION" | "LEAVE_REGION" | false
    for _, kind in ipairs({ "ENTER_REGION", "LEAVE_REGION" }) do
        for _, r in ipairs(regs[kind] or {}) do
            local rg = r.region
            if rg and crossed[rg] == nil then
                local now, was = inRegion(rg, u.x, u.y), rg.inside[u] or false
                rg.inside[u] = now
                crossed[rg] = (now ~= was) and (now and "ENTER_REGION" or "LEAVE_REGION")
            end
        end
    end
    for _, kind in ipairs({ "ENTER_REGION", "LEAVE_REGION" }) do
        W.fire(kind, { unit = u }, function(r) return r.region and crossed[r.region] == kind end)
    end
end

-- ---------------------------------------------------------------------------------------------
-- dialogs: buttons are real handles so a test can click them (T.click)
-- ---------------------------------------------------------------------------------------------
function DialogCreate() return H("dialog", { buttons = {}, shown = {} }) end
function DialogClear(d) if d then d.buttons = {} end end
function DialogDestroy() end
function DialogSetMessage(d, m) if d then d.message = m end end
function DialogAddButton(d, text, hotkey)
    if not d then return nil end
    local b = H("button", { dialog = d, text = text })
    d.buttons[#d.buttons + 1] = b
    return b
end
function DialogAddQuitButton(d, end_, text, hotkey) return DialogAddButton(d, text, hotkey) end
function DialogDisplay(p, d, flag) if d and p then d.shown[p] = flag end end
function TriggerRegisterDialogEvent(t, d) return addReg({ name = "DIALOG_CLICK" }, { trig = t, dialog = d }) end
function TriggerRegisterDialogButtonEvent(t, b) return addReg({ name = "DIALOG_CLICK" }, { trig = t, button = b }) end
function GetClickedButton() return W.ctx().button end
function GetClickedDialog() return W.ctx().dialog end
