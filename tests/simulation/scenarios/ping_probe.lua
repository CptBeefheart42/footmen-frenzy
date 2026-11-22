-- Anonymous in-game ping probe (league/18-ping.j) on a bot client: measures per-round player sync RTT
-- percentiles, optional bot observer RTT, summary totals, gameend freeze, Preload <= 259 chars, and
-- zero BattleTags anywhere in ff_ping_<token>.txt.
local lobby = T.defaultLobby()
local players
if T.map == "799x" then
    lobby[5] = { name = "Echo#5555" }
    players = { 1, 2, 4, 5 }
else
    players = { 1, 5, 8, 12 }
end
lobby[13] = { name = "MangoThief#115445", observer = true }
T.lobby(lobby, 13)

T.setPlayerRtt(players[1], 0.10)
T.setPlayerRtt(players[2], 0.10)
T.setPlayerRtt(players[3], 0.24)
T.setPlayerRtt(players[4], 0.42)
T.setPlayerRtt(13, 0.08)

T.boot()
-- First probe fires at 15.1s and all round-1 echoes arrive by 15.6s.
T.advance(20)
T.pickHeroes()
-- Suppress bot echo for round 2+ to verify bot_ms = -1 handling.
T.setPlayerRtt(13, -1)
-- Advance past round 1 close (45.1s) and round 2 close (75.1s) so round 3 is in flight with echoes landed.
T.advance(58)

-- End the game by forfeiting every side except slot 1's side.
if T.map == "799x" then
    T.leave(4)
    T.leave(5)
else
    T.leave(5)
    T.leave(8)
    T.leave(12)
end
T.advance(10)
-- Advance further after gameend: the probe must stay frozen.
T.advance(40)

local fname = T.dataFile("ff_ping")
local lines = T.file(fname) or {}
local rounds = T.rows(fname, "round")
local summaries = T.rows(fname, "summary")
local ends = T.rows(fname, "pingend")

T.check("bot client writes token-named ff_ping starting with format,1 and ending with pingend", function()
    T.ok(fname and fname:match("^ff_ping_%d+%.txt$"), "file name: " .. tostring(fname))
    T.eq(lines[1], "format,1", "first record")
    T.eq(#ends, 1, "pingend count")
    T.ok(lines[#lines] and lines[#lines]:match("^pingend,"), "last record: " .. tostring(lines[#lines]))
end)

T.check("round rows carry exact percentiles, thresholds and optional bot_ms", function()
    T.eq(#rounds, 3, "round count (frozen after gameend)")
    local r1 = rounds[1].parts
    T.eq(tonumber(r1[3]), 4, "r1 n")
    T.eq(tonumber(r1[4]), 100, "r1 p50")
    T.eq(tonumber(r1[5]), 240, "r1 p90")
    T.eq(tonumber(r1[6]), 420, "r1 max")
    T.eq(tonumber(r1[7]), 2, "r1 gt200")
    T.eq(tonumber(r1[8]), 1, "r1 gt350")
    T.eq(tonumber(r1[9]), 80, "r1 bot_ms")
    local r2 = rounds[2].parts
    T.eq(tonumber(r2[9]), -1, "r2 bot_ms when observer did not echo")
end)

T.check("summary totals match every closed round", function()
    T.eq(#summaries, 1, "summary row count")
    local s = summaries[1].parts
    T.eq(tonumber(s[3]), 3, "summary rounds")
    T.eq(tonumber(s[4]), 12, "summary samples")
    T.eq(tonumber(s[5]), 6, "summary gt200")
    T.eq(tonumber(s[6]), 3, "summary gt350")
    T.eq(tonumber(s[7]), 420, "summary max")
    T.eq(tonumber(s[8]), 1, "summary bot_samples")
    T.eq(tonumber(s[9]), 80, "summary bot_max")
end)

T.check("ff_ping is strictly anonymous and under the 259-char Preload limit", function()
    for _, line in ipairs(lines) do
        T.ok(#line <= 259, "line length <= 259: " .. tostring(#line))
        T.ok(not line:find("#", 1, true), "no battletag '#' in " .. line)
        for _, d in pairs(lobby) do
            T.ok(not line:find(d.name, 1, true), "no player name in " .. line)
        end
    end
end)
