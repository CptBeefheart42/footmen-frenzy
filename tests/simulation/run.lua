-- Runs one simulation scenario against a transpiled map script.
--   lua tests/simulation/run.lua <common.j> <lua dir> <map: 799x|solo> <scenario.lua>
-- <lua dir> holds common.lua, Blizzard.lua and <map>.lua from the runner's `jass-to-lua`.
-- Prints one `PASS|FAIL <scenario> :: <check>` line per check, then any script errors and the
-- natives the run called without a model; exits non-zero on any failure or script error.

local commonJ, luaDir, map, scenario = arg[1], arg[2], arg[3], arg[4]
local here = arg[0]:match("^(.*)[/\\][^/\\]*$") or "."
package.path = here .. "/?.lua;" .. package.path

local W = assert(loadfile(here .. "/wc3.lua"))(here)
W.loadNatives(commonJ)
-- JASS allows `return` mid-block (the build's stubbed functions start with one); Lua only as the
-- block's last statement. `do return end` means the same anywhere.
local function load_jass_lua(path)
    local f = assert(io.open(path))
    local lines = {}
    for l in f:lines() do lines[#lines + 1] = l end
    f:close()
    for i, l in ipairs(lines) do
        local ind, rest = l:match("^(%s*)return(.*)$")
        if ind and (rest == "" or rest:match("^%s")) then
            local nxt = lines[i + 1] or "end"
            if not (nxt:match("^%s*end") or nxt:match("^%s*else") or nxt:match("^%s*until")) then
                lines[i] = ind .. "do return" .. rest .. " end"
            end
        end
    end
    local src = table.concat(lines, "\n")
    assert(load(src, "@" .. path))()
end
load_jass_lua(luaDir .. "/common.lua")
W.nameConstants()
dofile(here .. "/unit_types.lua")
load_jass_lua(luaDir .. "/Blizzard.lua")
load_jass_lua(luaDir .. "/" .. map .. ".lua")
W.nameConstants()

T.map = map
local name = scenario:match("([^/\\]+)%.lua$")
local ok, err = xpcall(function() dofile(scenario) end, debug.traceback)

local failed = 0
local function printFails(r) for _, f in ipairs(r.fails) do print("     " .. f:gsub("\n", "\n     ")) end end
for _, r in ipairs(T.results) do
    if r.known and #r.fails > 0 then
        print(string.format("XFAIL %s :: %s", name, r.name))
        printFails(r)
    elseif r.known then
        failed = failed + 1
        print(string.format("FAIL %s :: %s (XPASS: the known bug is fixed, make it a T.check)", name, r.name))
    elseif #r.fails == 0 then
        print(string.format("PASS %s :: %s", name, r.name))
    else
        failed = failed + 1
        print(string.format("FAIL %s :: %s", name, r.name))
        printFails(r)
    end
end
if not ok then
    failed = failed + 1
    print(string.format("FAIL %s :: (scenario aborted)\n     %s", name, tostring(err):gsub("\n", "\n     ")))
end
-- Errors inside game threads (map triggers, our addons) fail the scenario: in the real game they
-- would silently kill that thread.
if T.errors and #T.errors > 0 and not T.allowErrors then
    failed = failed + 1
    print(string.format("FAIL %s :: script errors in game threads (%d)", name, #T.errors))
    local seen = {}
    for _, e in ipairs(T.errors) do
        local first = e:match("^[^\n]*")
        if not seen[first] then seen[first] = true; print("     " .. e:gsub("\n", "\n     ")) end
    end
end
if os.getenv("FF_SIM_VERBOSE") then
    local list = {}
    for k, v in pairs(T.unmodelled) do list[#list + 1] = { k, v } end
    table.sort(list, function(a, b) return a[2] > b[2] end)
    local s = {}
    for i = 1, math.min(#list, 40) do s[#s + 1] = list[i][1] .. "=" .. list[i][2] end
    print("     unmodelled natives: " .. table.concat(s, " "))
end
-- The files the map wrote, in the game's own Preload format (FF_SIM_OUT/<map>/<scenario>/),
-- for the bot's parser (map <-> bot contract check).
local outDir = os.getenv("FF_SIM_OUT")
if outDir then
    local dir = outDir .. "/" .. map .. "/" .. name   -- made by the runner (tests/simulation/run.py)
    for fname, lines in pairs(W.files) do
        local f = assert(io.open(dir .. "/" .. fname, "w"))
        f:write("function PreloadFiles takes nothing returns nothing\n\n\tcall PreloadStart()\n")
        for _, l in ipairs(lines) do f:write('\tcall Preload( "' .. l .. '" )\n') end
        f:write("\tcall PreloadEnd( 0.0 )\n\nendfunction\n\n")
        f:close()
    end
end
os.exit(failed == 0 and 0 or 1)
