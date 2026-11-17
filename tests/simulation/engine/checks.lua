-- Scenario API, part 2: reading what the map wrote, and the checks a scenario makes.
--
-- A scenario is a list of named checks; the runner prints one PASS / FAIL line per check.
local W = ...

-- ---------------------------------------------------------------------------------------------
-- the map's output
-- ---------------------------------------------------------------------------------------------
--- The strings of the latest write of a CustomMapData file (ff_result.txt, ...), or nil.
function T.file(name) return W.files[name] end

--- The name of a data file the map wrote: `base`.txt, or `base`_<token>.txt when the local client is a bot
--- (FF_DataFile); nil when the map wrote neither.
function T.dataFile(base)
    if W.files[base .. ".txt"] then return base .. ".txt" end
    for name in pairs(W.files) do
        if name:match("^" .. base .. "_%d+%.txt$") then return name end
    end
end

--- The map's own verdict for `slot`: "victory" / "defeat" (CustomVictoryBJ / CustomDefeatBJ ran) or nil.
function T.result(slot)
    if W.victories[slot] then return "victory" end
    if W.defeats[slot] then return "defeat" end
end

--- The `<kind>,...` rows of file `name`, each as { parts = comma-split fields, kv = { key = value }, line }.
function T.rows(name, kind)
    local out = {}
    for _, line in ipairs(name and W.files[name] or {}) do
        local parts = {}
        for f in (line .. ","):gmatch("([^,]*),") do parts[#parts + 1] = f end
        if parts[1] == kind then
            local kv = {}
            for _, f in ipairs(parts) do
                local k, v = f:match("^([%w_]+)=(.*)$")
                if k then kv[k] = tonumber(v) or v end
            end
            out[#out + 1] = { parts = parts, kv = kv, line = line }
        end
    end
    return out
end

--- The stats of `slot` as { key = value }, or nil without a stats row. The map splits a slot's
--- numbers over two rows with the same t= (the Preload length limit); this merges them.
function T.stats(slot)
    local out = nil
    for _, r in ipairs(T.rows(T.dataFile("ff_result"), "stats")) do
        if tonumber(r.parts[2]) == slot then
            out = out or {}
            for k, v in pairs(r.kv) do out[k] = v end
        end
    end
    return out
end

--- The kill log's owner rows as { [player name] = { unit=, hero=, unit_died=, hero_died= } }; empty
--- when the map wrote no kill log (only a bot client writes one).
function T.killlog()
    local out = {}
    local name = T.dataFile("ff_killlog")
    for i, line in ipairs(name and W.files[name] or {}) do
        local who, u, h, ud, hd = line:match("^([^,]+),(%d+),(%d+),(%d+),(%d+)$")
        if i > 1 and who then
            out[who] = { unit = tonumber(u), hero = tonumber(h), unit_died = tonumber(ud), hero_died = tonumber(hd) }
        end
    end
    return out
end

--- The usage counts of `slot` in category `cat` (item, unit, tech, tower, spell, cmd) as { code = count }.
function T.use(slot, cat)
    local out = {}
    for _, r in ipairs(T.rows(T.dataFile("ff_result"), "use")) do
        if tonumber(r.parts[2]) == slot and r.parts[3] == cat then
            for k, v in pairs(r.kv) do out[k] = v end
        end
    end
    return out
end

--- The ff_result rows of one kind (pick, baseup, out, winner, ...), each as its comma-split fields.
function T.events(kind)
    local out = {}
    for _, r in ipairs(T.rows(T.dataFile("ff_result"), kind)) do out[#out + 1] = r.parts end
    return out
end

--- The winning side and its members as "team1,1:Alpha#1111;2:Bravo#2222", or nil without a winner.
function T.winner()
    local w = T.events("winner")[1]
    return w and (w[3] .. "," .. w[4]) or nil
end

--- The placements as "1:team1 2:team3 ...", in the order the file lists them.
function T.placements()
    local order = {}
    for _, p in ipairs(T.events("placement")) do order[#order + 1] = p[2] .. ":" .. p[3] end
    return table.concat(order, " ")
end

--- Whether map flag `flag` (MAP_LOCK_RESOURCE_TRADING, ...) is set right now.
function T.mapFlag(flag) return W.mapFlags[flag] or false end

--- The codes a shop has in stock (units and items), sorted.
function T.stock(shop)
    local out = {}
    for id in pairs(shop and shop.stock or {}) do out[#out + 1] = W.id2s(id) end
    table.sort(out)
    return out
end

-- ---------------------------------------------------------------------------------------------
-- checks
-- ---------------------------------------------------------------------------------------------
T.results = {}
local current = nil

--- A named check: `fn` runs the assertions; an error inside it fails the check, not the scenario.
function T.check(name, fn)
    current = { name = name, fails = {} }
    local ok, err = xpcall(fn, debug.traceback)
    if not ok then current.fails[#current.fails + 1] = "error: " .. tostring(err) end
    T.results[#T.results + 1] = current
    current = nil
end

--- A check of the intended behaviour where the map has a known bug, so it is expected to fail. The runner
--- prints XFAIL while it fails and FAIL (XPASS) once it passes: a fixed bug then becomes a plain T.check.
function T.knownBug(name, fn)
    T.check(name, fn)
    T.results[#T.results].known = true
end

local function fail(msg)
    if current then current.fails[#current.fails + 1] = msg else error(msg, 3) end
end

--- Fails the current check unless `got` equals `want`.
function T.eq(got, want, what)
    if got ~= want then fail(string.format("%s: got %s, want %s", what or "value", tostring(got), tostring(want))) end
end

--- Fails the current check unless `cond` holds.
function T.ok(cond, what) if not cond then fail(what or "condition false") end end

--- Check: no side won, so the file names no winner, no placements and no game end.
function T.checkNoResult()
    T.check("nobody won: no winner, placement or gameend", function()
        T.eq(#T.events("winner"), 0, "winner rows")
        T.eq(#T.events("placement"), 0, "placement rows")
        T.eq(#T.events("gameend"), 0, "gameend rows")
    end)
end

--- Check: the file starts with its format and ends with gameend, after every telemetry row.
function T.checkFileShape()
    T.check("format,2 first, gameend last (after the telemetry rows)", function()
        local f = T.file(T.dataFile("ff_result")) or {}
        T.eq(f[1], "format,2", "first record")
        T.ok(f[#f] and f[#f]:match("^gameend,"), "last record: " .. tostring(f[#f]))
    end)
end
