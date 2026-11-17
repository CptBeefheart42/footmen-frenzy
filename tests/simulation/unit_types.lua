-- Unit type facts for the simulation engine, from the repo's generated CSVs (the map's object data has
-- no flags the script could read back). Heroes need nothing here: a capital first letter is a hero.
local root = (arg[0]:match("^(.*)/tests/simulation/[^/]*$")) or "."

local function rows(file)
    local out, header = {}, nil
    local f = io.open(root .. "/" .. file)
    if not f then return out end
    for line in f:lines() do
        local cols = {}
        for c in (line .. ","):gmatch("([^,]*),") do cols[#cols + 1] = c end
        if not header then header = cols else
            local r = {}
            for i, h in ipairs(header) do r[h] = cols[i] end
            out[#out + 1] = r
        end
    end
    f:close()
    return out
end

for _, r in ipairs(rows("units.csv")) do
    local n = r.Name or ""
    if n:find("TOWER") or n:find("SHOP") or n:find("ALTAR") or n:find("BARRACKS") then
        T.unitType(r.RawCode, { structure = true, name = n })
    elseif r.RawCode then
        T.unitType(r.RawCode, { name = n })
    end
end
-- bases (every tier/race): town halls (the map finds a player's base and their elimination by it)
for _, r in ipairs(rows("bases.csv")) do
    T.unitType(r.Code, { structure = true, townhall = true, name = r.Spawns })
end
for _, r in ipairs(rows("spawns.csv")) do
    T.unitType(r.Code, { name = r.Name, tier = tonumber(r.Tier) })
end
-- Creep shops keep a creep's gold price in its lumber-bounty field (object data the CSVs don't carry).
T.unitType("n00Q", { ifield = { [UNIT_IF_LUMBER_BOUNTY_AWARDED_BASE] = 250 } })

-- Spell dummies and the durations of the spells they cast (799W object data, `dumpall`; only the levels the
-- scenarios cast are listed). h01K (the common dummy) has a 0.1 s death time: it is removed right after it dies.
T.unitType("h01K", { removeAfter = 0.1 })
T.abilityType("ANso", { rlf = { adur = { [5] = 10.0, [6] = 10.0 }, ahdu = { [6] = 6.5 } } })          -- Objection's Soul Burn
T.abilityType("A0HL", { rlf = { adur = { 10.0, 10.0, 10.0, 10.0, 10.0, 10.0 }, ahdu = { 3.0, 3.0, 3.0, 3.0, 3.0, 3.0 } } }) -- Parasite
T.abilityType("A0CD", { rlf = { adur = { 4.0, 4.0, 4.0 }, ahdu = { 2.0, 2.0, 2.0 } } })              -- Hellfire's Flame Strike
T.abilityType("A064", { rlf = { adur = { [2] = 4.0, [3] = 5.0 }, ahdu = { [2] = 4.0, [3] = 5.0 } } }) -- Jaina's fire orb Rain of Fire
