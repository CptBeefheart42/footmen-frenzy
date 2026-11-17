-- Shared steps and checks of the game-mode scenarios (scenarios/*_mode_*.lua): the host's game-type dialog, the
-- hero-mode vote, the taverns each hero mode needs, and the gold pool / trading rules of each mode.
--   local M = require("modes")
--
-- The checks look at what a player sees (taverns standing, heroes for sale, the pool dialog opening, gold moving,
-- the trading flags, the modes row of ff_result), not at the map's mode globals, so the same scenarios hold for a
-- map version that implements the modes differently.
local M = {}

-- The host's game-type dialog, in the order the buttons are shown. On 799X, Custom opens a second dialog: Private /
-- Tournament (the in-house mode), and 4k when its setting is on.
local BUTTONS = {
    ["799x"] = { pub = 1, pro = 2, custom = 3, debug = 4 },
    solo = { normal = 1, ["4k"] = 2 },
}
local CUSTOM = { ["799x"] = { inhouse = 1, ["4k"] = 2 } }
-- 799X's Private host picks the hero mode in a dialog.
local HERO_MODE = { SD = "Single Draft (SD)", AR = "All Random (AR)", AP = "All Pick (AP)" }
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

--- The host picks game type `mode` in the dialog (799X "pub", "pro", "debug", and through Custom "inhouse", "4k";
--- Solo "normal", "4k"), or picks nothing for "afk" (the map's AFK default starts the game about 11 s in: follow with
--- M.untilStarted).
function M.pick(mode)
    if mode == "afk" then T.advance(5) return end
    local sub = CUSTOM[T.map] and CUSTOM[T.map][mode]
    if sub then
        T.click(1, T.buttons(1)[BUTTONS[T.map].custom])
        T.advance(0.1)
        T.click(1, T.buttons(1)[sub])
    else
        T.click(1, T.buttons(1)[BUTTONS[T.map][mode]])
    end
    T.advance(0.1)                          -- the next dialog opens on a short timer
end

--- The host's Custom dialog: its buttons.
function M.customButtons()
    T.click(1, T.buttons(1)[BUTTONS[T.map].custom])
    T.advance(0.1)
    return T.buttons(1)
end

--- In-house only: whether the host is asked about colossals (799X: how many); answers the first button so the game
--- goes on.
function M.declineColossals()
    local buttons = T.buttons(1)
    if #buttons == 0 then return false end
    T.click(1, buttons[1])
    T.advance(0.1)
    return true
end

--- The hero mode `kind` ("SD", "AP", "AR") is chosen: 799X's Private host picks it in a dialog (other players have
--- no say).
function M.vote(slot, kind)
    if slot == 1 then T.click(1, HERO_MODE[kind]) end
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

--- Check: hero mode `kind` sells heroes and slot 1 can buy one. 799X sells through each team's draft tavern (nTDP,
--- stocked from the mode's hidden taverns: SD the 4 `n02I`, AP the 9 `n01A`), bought with the player's wisp.
--- `check` is T.check (the default) or T.knownBug, as for every check here.
function M.checkTaverns(kind, check)
    local run = check or T.check
    run(kind .. " taverns stand and sell heroes", function()
        T.advance(0.5)
        local taverns = M.neutral("nTDP")
        T.ok(#taverns > 0, "a team draft tavern stands")
        local tavern, heroes = nil, {}
        for _, t in ipairs(taverns) do
            if #M.heroesIn(t) > 0 then tavern, heroes = t, M.heroesIn(t) break end
        end
        T.ok(tavern, "a draft tavern has heroes in stock")
        local buyer = T.unitsOf(1, "eTWP")[1] or T.unitsOf(1)[1]
        T.ok(tavern and T.buyUnit(buyer, tavern, heroes[1]) ~= nil, "slot 1 buys a hero")
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

--- Check: gold trading through the Allies menu is open (or locked) right now. 799X keeps the Allies menu locked in
--- every mode (gold moves only through -pool, the autopool and F3), so there it is always locked.
function M.checkTradingOpen(open, when, check)
    local run = check or T.check
    local menuOpen = open and T.map ~= "799x"
    run(when .. ": the Allies menu's gold trading " .. (menuOpen and "open" or "locked"), function()
        T.eq(T.mapFlag(M.TRADING_LOCKED), not menuOpen, "trading locked")
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

--- Checks of Pub's gold rules, from right after the start: -pool and the autopool stay locked for 230 s, then open
--- between allies (on Solo with the Allies menu too).
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
