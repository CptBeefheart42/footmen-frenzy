-- Scenario API, part 1: setting up the lobby and playing the game.
--
-- Each helper changes the model the way the engine would and fires the same events, so the map's
-- own triggers and our addons both react as in a real game. Slots are roster slots: 1..12 =
-- Player(0..11); observers sit in 13..24.
local W = ...
local P, s2id = W.P, W.s2id

-- The standard lobbies: three players (two allies and an enemy) on the main map, four sides on Solo.
local DEFAULT_LOBBY = {
    ["799x"] = { [1] = { name = "Alpha#1111" }, [2] = { name = "Bravo#2222" }, [4] = { name = "Delta#4444" } },
    solo = { [1] = { name = "Alpha#1111" }, [5] = { name = "Bravo#2222" }, [8] = { name = "Charlie#3333" },
             [12] = { name = "Delta#4444" } },
}

--- A fresh copy of the standard lobby of the map under test (to adjust before T.lobby).
function T.defaultLobby()
    local out = {}
    for slot, d in pairs(DEFAULT_LOBBY[T.map]) do out[slot] = { name = d.name } end
    return out
end

--- Sets the lobby: { [slot] = { name=, team=, computer=bool, observer=bool } } (default: T.defaultLobby()),
--- played from `localSlot` (default 1). An observer watches: IsPlayerObserver is true for them.
function T.lobby(players, localSlot)
    W.lobby = players or T.defaultLobby()
    W.localPlayer = (localSlot or 1) - 1
end

local function applyLobby()
    for slot, d in pairs(W.lobby or {}) do
        local p = P(slot - 1)
        p.name = d.name or p.name
        p.slot = PLAYER_SLOT_STATE_PLAYING
        p.controller = d.computer and MAP_CONTROL_COMPUTER or MAP_CONTROL_USER
        p.controllerLocked = true
        p.observer = d.observer or false
        if d.team then p.team = d.team end
    end
end

--- Starts the game: config() + main() as the game runs them. The lobby's names, slots and
--- controllers win over the map's config, as in a real game where config only describes the slots.
function T.boot()
    applyLobby()
    W.callWith({}, function() config() end, "config")
    applyLobby()
    W.callWith({}, function() main() end, "main")
    T.advance(0)
end

--- The local player's camera bounds: { minx=, miny=, maxx=, maxy= } (nil until the map sets them).
function T.cameraBounds() return W.cameraBounds end

--- Player of roster slot `slot`.
function T.player(slot) return P(slot - 1) end

--- A new unit of type `code` for `slot` at x, y (default 0, 0).
function T.unit(slot, code, x, y) return W.newUnit(P(slot - 1), s2id(code), x or 0, y or 0, 0) end
--- The map's footman, the tier-0 unit every base sends (udg_spawn_unit[0]: h060 on 799X, hfoo on Solo).
function T.footman() return T.str(udg_spawn_unit[0]) end

--- A new illusion of type `code` for `slot` (what Wand of Illusion or Mirror Image creates).
function T.illusion(slot, code, x, y)
    local u = T.unit(slot, code, x, y)
    u.illusion = true
    return u
end

--- The living units of `slot`, all of them or only those of type `code`.
function T.unitsOf(slot, code)
    local out = {}
    local id = code and s2id(code)
    for _, u in ipairs(W.allUnits) do
        if u.owner == P(slot - 1) and u.alive and (not id or u.typeId == id) then out[#out + 1] = u end
    end
    return out
end

--- A neutral shop or building of type `code` (for purchases); fails the scenario if there is none.
function T.shop(code)
    local id = s2id(code)
    for slot = 25, 28 do
        for _, u in ipairs(T.unitsOf(slot)) do if u.typeId == id then return u end end
    end
    error("T.shop: no " .. code, 2)
end

--- `victim` dies, killed by `killer` (nil: no killer, like KillUnit).
function T.kill(victim, killer)
    if not victim or not victim.alive then return end
    victim.alive = false
    victim.life = 0
    W.fireUnit("EVENT_PLAYER_UNIT_DEATH", victim, { killer = killer })
    W.fireUnit("EVENT_UNIT_DEATH", victim, { killer = killer })
end

--- `slot` types `msg`. A registration matches the whole message (exact) or any part of it.
function T.chat(slot, msg)
    local p = P(slot - 1)
    for _, r in ipairs(W.regsOf("EVENT_PLAYER_CHAT")) do
        if r.player == p then
            local hit
            if r.exact then hit = (msg == r.text) else hit = (r.text == "" or msg:find(r.text, 1, true) ~= nil) end
            if hit then W.fireReg(r, { player = p, chat = msg, chatMatched = r.text }) end
        end
    end
end

--- `buyer` buys an item of type `code` at `shop`; the item goes into the buyer's inventory.
function T.buyItem(buyer, shop, code)
    local it = W.newItem(s2id(code), shop and shop.x or 0, shop and shop.y or 0)
    UnitAddItem(buyer, it)
    W.fireUnit("EVENT_PLAYER_UNIT_SELL_ITEM", shop, { seller = shop, buyer = buyer, soldItem = it })
    W.fireUnit("EVENT_PLAYER_UNIT_PICKUP_ITEM", buyer, { item = it })
    return it
end

--- `seller` sells item `it` back to `shop`: the engine fires the pawn event and removes the item.
function T.pawnItem(seller, shop, it)
    W.fireUnit("EVENT_PLAYER_UNIT_PAWN_ITEM", seller, { seller = seller, buyer = shop, soldItem = it })
    RemoveItem(it)
end

--- `user` uses item `it` from its inventory.
function T.useItem(user, it)
    W.fireUnit("EVENT_PLAYER_UNIT_USE_ITEM", user, { item = it })
end

-- Every hero of both maps costs 5 food (the debug addon relies on it too: 50-debug.j).
local HERO_FOOD = 5

-- Whether the game sells player `p` one more hero: under its hero limit, with the food for it (the food of
-- anything else is not counted: with a food cap of 5, a hero is all the food a player has).
local function heroAllowed(p)
    local heroes = 0
    for _, u in ipairs(W.allUnits) do
        -- a dead hero still counts until it is removed: it can be revived
        if u.owner == p and u.hero and not u.removed and not u.illusion then heroes = heroes + 1 end
    end
    local max = GetPlayerTechMaxAllowed(p, s2id("HERO"))
    local cap = GetPlayerState(p, PLAYER_STATE_RESOURCE_FOOD_CAP)
    return (max < 0 or heroes < max) and (heroes + 1) * HERO_FOOD <= cap
end

--- `buyer` buys a unit of type `code` at `shop` (a hero at a tavern, a creep, a mercenary). A hero the game would
--- refuse (hero limit or food, as the client checks) is not sold: nil.
function T.buyUnit(buyer, shop, code)
    if IsHeroUnitId(s2id(code)) and not heroAllowed(buyer.owner) then return nil end
    local u = W.newUnit(buyer.owner, s2id(code), shop.x, shop.y, 0)
    W.fireUnit("EVENT_PLAYER_UNIT_SELL", shop, { seller = shop, buyer = buyer, soldUnit = u })
    return u
end

--- Slot `slot` picks hero `code` (default H005) the way a player does: bought at the tavern (main: the shared one,
--- Solo: the slot's own), so the map's TP_hero makes it the slot's hero (udg_herO). Returns the hero, or nil.
function T.pickHero(slot, code)
    local tavern = T.map == "799x" and T.shop("n02I") or T.unitsOf(slot, "n02I")[1]
    return T.buyUnit(T.unitsOf(slot)[1], tavern, code or "H005")
end

--- Every human player of the lobby picks a hero (T.pickHero): a game that goes on after the mass needs them, or the
--- AFK kick removes the players without one.
function T.pickHeroes()
    for slot, d in pairs(W.lobby or {}) do
        if slot <= 12 and not d.computer and not d.observer then T.pickHero(slot) end
    end
    T.advance(2)
end

--- `unit` finishes one level of research `code` for its owner.
function T.research(unit, code)
    local id = s2id(code)
    local p = unit.owner
    p.tech[id] = (p.tech[id] or 0) + 1
    W.fireUnit("EVENT_PLAYER_UNIT_RESEARCH_FINISH", unit, { research = id })
end

--- `unit` (a base or tower) finishes upgrading into type `code`.
function T.upgrade(unit, code)
    unit.typeId = s2id(code)
    W.fireUnit("EVENT_PLAYER_UNIT_UPGRADE_FINISH", unit, {})
end

--- `hero` learns one more level of ability `code`.
function T.learn(hero, code)
    local id = s2id(code)
    hero.abilities[id] = true
    hero.abilityLevel[id] = (hero.abilityLevel[id] or 0) + 1
    W.fireUnit("EVENT_PLAYER_HERO_SKILL", hero, { skill = id, skillLevel = hero.abilityLevel[id] })
end

--- `caster` casts ability `code` (on `target`, if any): fires the five spell events in the game's order.
function T.cast(caster, code, target)
    local c = { spell = s2id(code), target = target, tx = target and target.x or 0, ty = target and target.y or 0 }
    for _, ev in ipairs({ "EVENT_PLAYER_UNIT_SPELL_CHANNEL", "EVENT_PLAYER_UNIT_SPELL_CAST", "EVENT_PLAYER_UNIT_SPELL_EFFECT",
        "EVENT_PLAYER_UNIT_SPELL_FINISH", "EVENT_PLAYER_UNIT_SPELL_ENDCAST" }) do
        W.fireUnit(ev, caster, c)
    end
end

--- `source` deals `amount` damage to `target` (the damage events only; life is not reduced).
function T.damage(source, target, amount)
    W.fireUnit("EVENT_PLAYER_UNIT_DAMAGED", target, { source = source, damage = amount })
    W.fireUnit("EVENT_UNIT_DAMAGED", target, { source = source, damage = amount })
end

--- `slot` leaves the game.
function T.leave(slot)
    local p = P(slot - 1)
    p.slot = PLAYER_SLOT_STATE_LEFT
    W.fire("EVENT_PLAYER_LEAVE", { player = p }, function(r) return r.player == p end)
end

--- The gold of `slot`; sets it first when `v` is given.
function T.gold(slot, v)
    if v then SetPlayerState(P(slot - 1), PLAYER_STATE_RESOURCE_GOLD, v) end
    return GetPlayerState(P(slot - 1), PLAYER_STATE_RESOURCE_GOLD)
end

--- `from` sends `gold` to `to` through the Allies menu, as the engine does it: the gold moves and the
--- score screen counts it as gold given / received. No script can do this in the real game (there is
--- no tribute native); the e2e `trade` scenario checks the same behaviour on the real client.
function T.tribute(from, to, gold)
    local a, b = P(from - 1), P(to - 1)
    SetPlayerState(a, PLAYER_STATE_RESOURCE_GOLD, GetPlayerState(a, PLAYER_STATE_RESOURCE_GOLD) - gold)
    SetPlayerState(b, PLAYER_STATE_RESOURCE_GOLD, GetPlayerState(b, PLAYER_STATE_RESOURCE_GOLD) + gold)
    a.score[PLAYER_SCORE_GOLD_GIVEN] = (a.score[PLAYER_SCORE_GOLD_GIVEN] or 0) + gold
    b.score[PLAYER_SCORE_GOLD_RECEIVED] = (b.score[PLAYER_SCORE_GOLD_RECEIVED] or 0) + gold
end

local function shownDialog(p)
    for _, r in ipairs(W.regsOf("DIALOG_CLICK")) do
        if r.dialog and r.dialog.shown[p] then return r.dialog end
    end
end

--- `slot` clicks a dialog button: `which` is the button handle or a part of its text.
function T.click(slot, which)
    local p = P(slot - 1)
    local b = type(which) == "table" and which or nil
    if not b then
        for _, r in ipairs(W.regsOf("DIALOG_CLICK")) do
            local d = r.dialog
            if d and d.shown[p] then
                for _, x in ipairs(d.buttons) do
                    if tostring(x.text):find(which, 1, true) then b = x break end
                end
            end
            if b then break end
        end
    end
    if not b then error("T.click: no shown button matching " .. tostring(which), 2) end
    b.dialog.shown[p] = false
    W.fire("DIALOG_CLICK", { player = p, button = b, dialog = b.dialog }, function(r)
        return r.button == b or r.dialog == b.dialog
    end)
end

--- The button texts of the dialog shown to `slot` right now.
function T.buttons(slot)
    local out = {}
    local d = shownDialog(P(slot - 1))
    for _, x in ipairs(d and d.buttons or {}) do out[#out + 1] = x.text end
    return out
end

--- Runs past the next periodic ff_result write (every 30 s when something changed).
function T.flush() T.advance(31) end
