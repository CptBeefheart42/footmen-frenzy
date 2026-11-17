# Simulation tests

These tests play the **built maps' own scripts** without Warcraft III. A map's game logic is a
script written in JASS, the language WC3 maps are programmed in. The build translates that script
into Lua ("transpiles" it: runner `jass-to-lua`), together with WC3's two standard script libraries,
`common.j` and `Blizzard.j`. A small stand-in for the game engine (`wc3.lua` and `engine/`) then runs
it.

The map's own triggers and our addons run unchanged. A scenario that kills a unit therefore exercises
the map's own `-kd` counter *and* our stats handler, exactly as a game would.

```
make test-sim        # build both maps, transpile, run every scenario, then the bot-parser contract
make sim-run         # re-run on the last transpiled scripts (fast loop while writing a scenario)
FF_SIM_VERBOSE=1 tests/simulation/run.sh bin/simulation tests/simulation/scenarios/main_combat.lua
```

Both maps start in well under a second, and the whole suite takes a few seconds. CI
(`.gitea/workflows/test.yml`) runs it on every push.

## Words used here

- **Native**: a function the game engine itself provides (create a unit, start a timer, write a file).
  `common.j` only declares the natives; the game supplies the code. Here the `engine/` modules supply it.
- **BJ functions**: the helpers in `Blizzard.j`. They are built from natives and run as they are.
- **Trigger**: the map's event handler ("when a unit dies, do ...").
- **Preload file**: the only way a map can write a file to disk. The map collects strings and saves
  them under `CustomMapData`. `ff_result.txt` is written this way. The real game keeps at most 259
  characters of each string.
- **Op limit**: the game stops a script thread that runs too long.

## What it covers, and what it does not

Covered: everything the map *script* decides, which includes:
- triggers and events;
- timers and waits;
- hashtables, unit groups and player groups;
- dialogs and regions;
- the files the map writes.

Not covered: gameplay the engine simulates, which includes:
- combat, damage, pathing and orders;
- what abilities actually do;
- the score screen (`mined`, `tech`, `razed` and `food` stay 0).

Those need the real client (`tests/e2e`). Desyncs need two clients.

## Layout

| file | what |
|------|------|
| `run.sh` | runs every scenario (or the ones given) on its map, prints PASS / FAIL / XFAIL per check |
| `run.lua` | runs one scenario in a fresh Lua state; writes the map's files to `FF_SIM_OUT` |
| `wc3.lua` | loads the engine modules below |
| `engine/core.lua` | object handles, the native stubs, the game clock and its threads, the op limit |
| `engine/players.lua` | players and player groups |
| `engine/units.lua` | unit types, units, items, unit groups, locations and rects |
| `engine/events.lua` | triggers and their events, regions, dialogs |
| `engine/data.lua` | timers, hashtables, strings, math, random numbers |
| `engine/preload.lua` | the files the map writes |
| `engine/misc.lua` | UI, effects and game settings, which have no behaviour here |
| `engine/api.lua` | the scenario API for setting up and playing a game |
| `engine/checks.lua` | the scenario API for reading the map's files and checking them |
| `modes.lua` | shared steps and checks of the game-mode scenarios (`*_mode_*`): dialog, vote, taverns, gold pool |
| `unit_types.lua` | unit facts the script cannot read from the map: bases, towers, shops, spawns, creep prices |
| `contract.py` | the bot-parser contract check (below) |

## Writing a scenario

A scenario is a file `scenarios/<name>.lua`:
- `main_*` runs on the main map, `solo_*` on Solo, anything else on both;
- each scenario is one game in a fresh Lua state.

```lua
T.lobby()                         -- the standard lobby: main = slots 1, 2 (allies), 4; Solo = 1, 5, 8, 12
T.boot()                          -- config() + main(): the map's init runs
T.advance(20)                     -- game time; timers, periodic triggers and waits fire in order
local foot = T.unitsOf(1, "hfoo")[1]
T.kill(T.unit(4, "hfoo"), foot)   -- fires the unit-death events like the engine
T.flush()                         -- past the next 30 s ff_result write
T.check("kill counted", function()
    T.eq(T.stats(1).ukills, 1, "ukills")
end)
```

**Setting up**
- `T.lobby(players, localSlot)`. `players` is `{ [slot] = { name=, team=, computer=, observer= } }`;
  start from `T.defaultLobby()` to adjust the standard lobby.
- Slots are roster slots: 1..12 = `Player(0..11)`. Observers sit in 13..24.

**Playing**
- `T.unit` / `T.illusion` / `T.unitsOf` (the living units of a slot) / `T.shop`
- `T.kill`, `T.buyItem`, `T.buyUnit`, `T.research`, `T.upgrade`, `T.learn`, `T.cast`, `T.damage`
- `T.chat`, `T.click` / `T.buttons` (dialog buttons), `T.leave`, `T.gold`
- `T.tribute(from, to, gold)`: gold through the Allies menu, as the engine counts it (gold given / received)
- `T.advance`, `T.flush`

Every helper has a one-line description in `engine/api.lua`.

**Reading the result**
- `T.file`, `T.rows`, `T.stats` (a slot's two stats rows merged), `T.use`, `T.events`
- `T.dataFile(base)`: the name the map wrote `base` under (`ff_result.txt`, or `ff_result_<token>.txt` when the
  local client is a bot); `T.killlog()`: the kill log's owner rows by player name (bot clients only)
- `T.winner` (`"team1,1:Alpha#1111;..."`), `T.placements` (`"1:team1 2:team3 ..."`)
- `T.result(slot)`: the map's own victory / defeat verdict
- `T.mapFlag(flag)`: a map flag the script set (`MAP_LOCK_RESOURCE_TRADING`, ...); `T.stock(shop)`: the codes a
  shop has in stock
- plus any map global (`udg_unit_kills[1]`)

**Checking**
- `T.check(name, fn)` with `T.eq` / `T.ok` inside.
- Common checks: `T.checkNoResult()` (nobody won) and `T.checkFileShape()` (`format,2` first, `gameend` last).
- `T.knownBug(name, fn)`: a check of the intended behaviour where the map has a known bug. While it fails, the
  runner prints `XFAIL` and the run stays green; once it passes, it prints `FAIL ... (XPASS ...)`, so a fixed bug
  turns into a plain `T.check`. The summary counts the known bugs.

**Unit type facts**
- The map's object data holds some facts the script cannot read back. Declare them with `T.unitType`; for
  example, a creep's price lives in its lumber-bounty field:
  `T.unitType("n00Q", { ifield = { [UNIT_IF_LUMBER_BOUNTY_AWARDED_BASE] = 250 } })`.
- The shared ones live in `unit_types.lua`.
- A unit type whose code starts with a capital letter is a hero.
- Timed life (`UnitApplyTimedLife`) kills the unit with no killer when it runs out; a type declared with
  `removeAfter = s` (a short death time, like the spell dummy `h01K`) is removed `s` later.
- Spell durations the map reads back (`BlzGetAbilityRealLevelField`) are declared per ability and level with
  `T.abilityType("ANso", { rlf = { adur = { [6] = 10.0 } } })` and read in scenarios with `T.abilityReal`.

## JASS rules the engine keeps

The engine matches JASS, the game's own script language, where it differs from Lua:
- **Null strings:** a `null` string joins onto other text as `""`. `string array` elements start out
  `null`.
- **`SubString` past the end** of a string returns `null`, not `""`. The map's name scan relies on this
  to stop.
- **`return` in the middle of a block** (the build's stubbed functions) is rewritten to `do return end`
  when loading.
- **Op limit:** a thread that runs longer than `FF_SIM_SLICE` seconds (default 5) is stopped with a
  traceback. An endless loop then fails the scenario instead of hanging the run.
- **Script errors:** an error in a game thread (trigger actions, timer callbacks) fails the scenario.
  In the game, the error would silently stop that thread.
- **Preload strings:** a string longer than 259 characters is an error, because the real game cuts it.

## The contract check

`contract.py` checks every `ff_result.txt` the scenarios wrote. It uses the league bot's own parser:
`efl_league.ff_result` from efl-bot-2.0, found through `FF_EFL_BOT` or `../efl-bot-2.0`.

It fails when any of these holds:
- a record is unknown;
- a value is lost;
- a finished game is not complete enough to score.

It is skipped when there is no bot checkout or no Python.

## How a game ends

`T.leave(slot)` fires the map's own leave trigger. These scenarios pin down how a game ends:

| scenario | what happens | expected file |
|----------|--------------|---------------|
| `main_gameend`, `solo_game` | bases fall | the file names the winner and placements; `gameend` is the last row |
| `main_forfeit`, `solo_forfeit` | the other sides leave | the side left standing wins, and the map's own END agrees |
| `main_dissolve`, `solo_dissolve` | everybody leaves while several sides still stand | no `winner`, `placement` or `gameend` |
| `main_leave_after_end` | units die and players leave after `gameend` | no result row changes |
| `main_observer` | an observer watches the whole game | the observer never appears in the result |
| `main_kd_gameend` | units die after `gameend` | the kill log keeps the final stats' kill counts |

On the main map, a team is out only once all of its players have left.

`make test-sim-ladder` then puts these files through the bot version the fleet runs
(`tests/e2e/ladder_check.py`):
- a forfeit is scored;
- a game nobody won is not (`--unscored`).

The rules themselves are in `docs/result-contract.md`.
