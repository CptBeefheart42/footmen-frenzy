-- A full 12-player lobby with long battletags: the game keeps at most 259 characters of a Preload string (the
-- simulation fails any longer row, like the cut the real client makes silently), so the roster continues in
-- roster_more rows and every slot's stats come in two rows that together carry every key.
local lobby = {}
for i = 1, 12 do lobby[i] = { name = string.format("(EFL)LongBattleTag%02d#%06d", i, 100000 + i) } end
T.lobby(lobby)
T.boot()
T.advance(40)
T.flush()

T.check("roster: every participant, over roster + roster_more", function()
    local names = {}
    for _, kind in ipairs({ "roster", "roster_more" }) do
        for _, r in ipairs(T.rows("ff_result.txt", kind)) do
            for e in (r.line:sub(#kind + 2) .. ";"):gmatch("([^;]*);") do
                local slot, name = e:match("^(%d+):(.*)$")
                if slot then names[tonumber(slot)] = name end
            end
        end
    end
    for i = 1, 12 do T.eq(names[i], lobby[i].name, "roster entry " .. i) end
    T.eq(#T.rows("ff_result.txt", "roster"), 1, "exactly one roster row (a parser that reads one keeps the last)")
end)
T.check("stats: two rows per slot, every key", function()
    for i = 1, 12 do
        local s = T.stats(i)
        T.ok(s, "stats for slot " .. i)
        if s then
            for _, k in ipairs({ "state", "given", "mined", "food", "koth_gold", "hero_lvl", "deny_own", "team_res", "dmg_out", "dmg_in" }) do
                T.ok(s[k] ~= nil, "slot " .. i .. " key " .. k)
            end
        end
    end
end)
