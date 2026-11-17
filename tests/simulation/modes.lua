-- Shared steps and checks of the game-mode scenarios (scenarios/*_mode_*.lua): the host's game-type dialog, the
-- hero-mode vote, the taverns each hero mode needs, and the gold pool / trading rules of each mode.
--   local M = require("modes")
--
-- The checks look at what a player sees (taverns standing, heroes for sale, the pool dialog opening, gold moving,
-- the trading flags, the modes row of ff_result), not at the map's mode globals, so the same scenarios hold for a
-- map version that implements the modes differently.
local M = {}

-- The host's game-type dialog, in the order the buttons are shown.
local BUTTONS = {
    ["799x"] = { pub = 1, pro = 2, inhouse = 3, custom = 4 },
    solo = { normal = 1, ["4k"] = 2 },
}
-- The vote spells of the hero-mode vote (In-house and Pub custom).
local VOTE_SPELL = { SD = "A01T", AP = "A01F", AR = "A01R" }
local COLOSSAL_NO = "TRIGSTR_11522"     -- In-house: the "play with colossals?" dialog's No
local POOL_THRESHOLD = "TRIGSTR_1683"   -- pool dialog: set the gold kept back
local POOL_CANCEL = "TRIGSTR_1684"
local THRESHOLD_150 = "TRIGSTR_1674"    -- threshold dialog, third button: keep 150

M.TRADING_LOCKED = MAP_LOCK_RESOURCE_TRADING
M.TRADING_ALLIES_ONLY = MAP_RESOURCE_TRADING_ALLIES_ONLY

--- Boots the standard lobby (three players on the main map: 1 and 2 allied, 4 the enemy; four on Solo) and
--- waits until the host's dialog is up.
function M.boot()
    T.lobby()
    T.boot()
    T.advance(2)
end

--- The host picks game type `mode` in the dialog ("pub", "pro", "inhouse", "custom"; Solo "normal", "4k"), or
--- picks nothing for "afk" (the map's AFK default starts the game 8 s in: follow with M.untilStarted).
function M.pick(mode)
    if mode == "afk" then T.advance(5) return end
    local i = BUTTONS[T.map][mode]
    T.click(1, T.buttons(1)[i])
    T.advance(0)
end

--- In-house only: whether the host is asked about colossals; answers No so the game goes on.
function M.declineColossals()
    for _, b in ipairs(T.buttons(1)) do
        if b == COLOSSAL_NO then T.click(1, b) T.advance(0) return true end
    end
    return false
end

--- `slot` votes for hero mode `kind` ("SD", "AP", "AR") by casting the vote spell. A vote of the host (slot 1)
--- decides the vote for everyone and ends it after 1 s.
function M.vote(slot, kind)
    local caster = T.unitsOf(slot)[1] or T.unit(slot, T.footman())
    T.cast(caster, VOTE_SPELL[kind])
    T.advance(0)
end

--- How often the game has started (Start_game ran).
function M.starts() return GetTriggerExecCount(gg_trg_Start_game) end

--- Advances in small steps until the game starts, at most `limit` seconds; returns whether it started. Stops
--- right at the start, before any income, so the players' gold is the mode's start gold.
function M.untilStarted(limit)
    local waited = 0
    while M.starts() == 0 and waited < limit do
        T.advance(0.25)
        waited = waited + 0.25
    end
    return M.starts() > 0
end

--- The neutral units of type `code` (taverns, shops).
function M.neutral(code)
    local out = {}
    for slot = 25, 28 do
        for _, u in ipairs(T.unitsOf(slot, code)) do out[#out + 1] = u end
    end
    return out
end

--- The heroes a shop has in stock, as codes.
function M.heroesIn(shop)
    local out = {}
    for _, code in ipairs(T.stock(shop)) do
        if IsHeroUnitId(T.id(code)) then out[#out + 1] = code end
    end
    return out
end

--- Check: hero mode `kind` has its taverns, each with heroes for sale, and slot 1 can buy one (SD: the 4 shared
--- `n02I`, AP: the 9 `n01A`). `check` is T.check (the default) or T.knownBug, as for every check here.
function M.checkTaverns(kind, check)
    local code, want = "n02I", 4
    if kind == "AP" then code, want = "n01A", 9 end
    local run = check or T.check
    run(kind .. " taverns stand and sell heroes", function()
        local taverns = M.neutral(code)
        T.eq(#taverns, want, code .. " taverns")
        for i, t in ipairs(taverns) do
            T.ok(#M.heroesIn(t) > 0, code .. " #" .. i .. " has no hero in stock: " .. table.concat(T.stock(t), " "))
        end
        local first = taverns[1] and M.heroesIn(taverns[1])[1]
        T.ok(first and T.buyUnit(T.unitsOf(1)[1], taverns[1], first) ~= nil, "slot 1 buys a hero")
    end)
end

--- Check (Solo): each of `slots` has own taverns (`n02I`) with heroes for sale.
function M.checkOwnTaverns(slots)
    T.check("every player has own taverns with heroes", function()
        for _, slot in ipairs(slots) do
            local heroes = 0
            for _, t in ipairs(T.unitsOf(slot, "n02I")) do heroes = heroes + #M.heroesIn(t) end
            T.ok(heroes > 0, "heroes for sale to slot " .. slot)
        end
    end)
end

--- The modes row of ff_result as { key = value } (written once the modes are final, 15 s after the start, then
--- with the next file write), or nil.
function M.modes()
    local r = T.rows(T.dataFile("ff_result"), "modes")[1]
    return r and r.kv
end

--- Check: the modes row has every key/value of `want`.
function M.checkModes(want, check)
    local keys = {}
    for k in pairs(want) do keys[#keys + 1] = k end
    table.sort(keys)
    local parts = {}
    for _, k in ipairs(keys) do parts[#parts + 1] = k .. "=" .. tostring(want[k]) end
    local run = check or T.check
    run("modes row: " .. table.concat(parts, " "), function()
        local m = M.modes()
        T.ok(m, "modes row written")
        for _, k in ipairs(keys) do T.eq(m and m[k], want[k], k) end
    end)
end

--- `slot` types -pool; returns the buttons of the pool dialog it opened (empty when the map refused).
function M.openPool(slot)
    T.chat(slot, "-pool")
    T.advance(0)
    return T.buttons(slot)
end

--- `from` autopools to ally `to` through the map's dialog, then the map's 2 s pool timer runs with `gold` on
--- `from`; returns what `from` and `to` hold afterwards. Errors when the dialog does not open.
function M.autopool(from, to, gold)
    M.openPool(from)
    T.click(from, GetPlayerName(T.player(to)))
    T.gold(from, gold)
    local before = T.gold(to)
    T.advance(2.5)
    return T.gold(from), T.gold(to) - before
end

--- `slot` sets the gold the autopool keeps back to 150 through the pool dialog.
function M.keep150(slot)
    M.openPool(slot)
    T.click(slot, POOL_THRESHOLD)
    T.advance(0)
    T.click(slot, THRESHOLD_150)
    T.advance(0)
end

--- Closes the pool dialog of `slot` if it is open.
function M.closePool(slot)
    for _, b in ipairs(T.buttons(slot)) do
        if b == POOL_CANCEL then T.click(slot, b) T.advance(0) return end
    end
end

--- Check: `-pool` opens the pool dialog (`open`) or is refused; `check` as in M.checkTaverns.
function M.checkPoolDialog(open, when, check)
    local run = check or T.check
    run(when .. ": -pool " .. (open and "opens the pool dialog" or "is refused"), function()
        local buttons = M.openPool(1)
        if open then
            T.ok(#buttons > 0, "pool dialog shown")
        else
            T.eq(#buttons, 0, "pool dialog buttons")
        end
        M.closePool(1)
    end)
end

--- Check: slot 1's autopool moves its gold to ally slot 2, and no gold is made or lost on the way.
function M.checkAutopool(when, check)
    local run = check or T.check
    run(when .. ": autopool moves the gold to the ally", function()
        local left, moved = M.autopool(1, 2, 1000)
        T.eq(left, 0, "gold left with slot 1")
        T.eq(moved, 1000, "gold arrived at slot 2")
    end)
end

--- Check: gold trading through the Allies menu is open (or locked) right now.
function M.checkTradingOpen(open, when, check)
    local run = check or T.check
    run(when .. ": gold trading " .. (open and "open" or "locked"), function()
        T.eq(T.mapFlag(M.TRADING_LOCKED), not open, "trading locked")
    end)
end

--- Check: gold can be traded to allies only (or to anybody) right now.
function M.checkAlliesOnly(on, when, check)
    local run = check or T.check
    run(when .. ": gold trading " .. (on and "with allies only" or "not limited to allies"), function()
        T.eq(T.mapFlag(M.TRADING_ALLIES_ONLY), on, "allies only")
    end)
end

--- Check: the game has started exactly once, and slot 1 got `gold` start gold (read by the caller right at the
--- start, see M.untilStarted).
function M.checkStart(gold, startGold, check)
    local run = check or T.check
    run("the game starts once, with start gold " .. startGold, function()
        T.eq(M.starts(), 1, "game starts")
        T.eq(gold, startGold, "start gold of slot 1")
    end)
end

--- Checks of Pub's gold rules, from right after the start: trading, -pool and the autopool stay locked for 230 s,
--- then open between allies.
function M.checkPubTrading()
    T.advance(10)
    M.checkTradingOpen(false, "10 s in")
    M.checkPoolDialog(false, "10 s in")
    T.advance(225)
    M.checkTradingOpen(true, "after 230 s")
    M.checkAlliesOnly(true, "after 230 s")
    M.checkPoolDialog(true, "after 230 s")
    M.checkAutopool("after 230 s")
end

return M
