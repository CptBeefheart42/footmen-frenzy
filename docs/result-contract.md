# The result contract: what the map writes, what the bot relies on

The map and the league bot (efl-bot, which hosts the games and keeps the ladder) meet in three files the map writes into `CustomMapData/` with `Preload`. This is the contract
between them, and the spec every map flavour (today JASS, later Lua) must meet. The tests judge these files, never the
script that wrote them, so they carry over to a Lua map unchanged (see the porting checklist at the end).

The field-by-field formats live where they're written; this page is the overview and the rules.

| file | written by | read by | format reference |
|---|---|---|---|
| `ff_result.txt` / `ff_result_<token>.txt` | `league/20-gameresult.j` (+ `15-stats.j`, `16-usage.j`), every client | efl-bot `efl_league/ff_result.py` → `/report_match` | addon headers; `docs/ff_result-sample.txt` |
| `ff_killlog_<token>.txt` | `league/10-killlog.j`, bot clients only | efl-bot `efl_league/killlog.py` | `10-killlog.j` header |
| `ff_ping_<token>.txt` | `league/18-ping.j`, bot clients only (anonymous) | efl-bot `efl_league/ping_report.py` → `/ping_report` | `18-ping.j` header |
| `ff_e2e.txt` / `ff_e2e_phase.txt` | e2e builds only (`tests/e2e/addons/core`) | `tests/e2e/run.py`, `check_e2e.py` | `core/00-e2e-core.j` header |

`<token>`: a bot client's game token (`FF_DataFile`), so concurrent games on one box don't overwrite each other. Any
other client writes the plain name. Only the name differs: the content is the same on every client.

## ff_result records

| record | when | meaning |
|---|---|---|
| `format,<n>` | always, the first record | the file's format: 2 (a file without this row is format 1). Bumped only when a key's meaning changes, and that key also gets a new name; otherwise records and keys are only added, an existing row is never widened |
| `mode,ffa` / `mode,6v6` | always, after `format` | how slots form sides: FFA = 1-3, 4-6, 7-9, 10-12; 6v6 = West / East |
| `roster,<slot>:<name>;...` + `roster_more,...` | from the first second | every participant (never an observer); more rows when one would pass the length limit |
| `afk,<t>,<slot>,<name>` | a player is removed for having no hero, or having done nothing since the game started, 15 s after the mass began and once the gold pool is open (`league/25-afk.j`) | the game doesn't count for them: from then on the slot is in no roster, stats, usage row or side |
| `sub,<t>,<slot>,<name>` | 799X built with `sub.enabled`: an observer took over the slot of a player who left (`league/22-sub.j`) | the slot plays on: the roster keeps the player who left, the slot's stats continue with `state=sub`; efl-bot does not read it yet |
| `out,<t>,<slot>,<side>,<name>` | a player is out | the map cleared `udg_player_active`: base destroyed, or a whole team left |
| `sidedead,<t>,<side>` | a side is out | its last player is out |
| `winner,<t>,<side>,<members>` | exactly one side left | the map's own END condition |
| `placement,<n>,<side>,<members>` | with `winner` | 1 = winner, then the sides in reverse order of going out |
| `gameend,<t>` | with `winner`, **the file's last record** (after every telemetry row) | the game has a result |
| `pick`, `baseup`, `buy`, `used` | events | hero picks, base tiers; `buy,<t>,<slot>,<code>` / `used,<t>,<slot>,<code>`: a key item bought (Ring of J33bus `I002`, Sword of a Thousand Truths `I01Z` / `I048`, Altar of the Gods `o00B`) or used (Penguin Stone `I033`, Healing Wards of the Gods `I005`) |
| `stats,<slot>,t=...` ×2 | every 30 s when changed, at each `out`, at `gameend` | per-player numbers; two rows per slot with the same `t=` |
| `use`, `skills`, `modes`, `koth` | as `stats` | usage telemetry |

## stats keys

Each participant gets two `stats,<slot>,t=<mm:ss>,...` rows with the same `t=`; the bot merges them. Values are
integers and cumulative up to the file's last write, unless the table says otherwise. Both maps write every key.
`dmg_*` are left out when a build sets `FF_STATS_DAMAGE` off.

**Status** decides what the bot may use (Elo = the ladder's skill rating). Only `stable` keys are shown, and only they may ever feed Elo or balance.
`probation`: written and stored, not shown, until the open point is settled. `deprecated`: still written, about to
go away; a key whose meaning changes gets a new name instead.

| key | meaning | source | status |
|---|---|---|---|
| `state` | `alive`, `out` (base destroyed / whole team left), `left` (the player left while alive) | slot state + `udg_player_active` | stable |
| `left_t` | when a `left` player left (mm:ss) | | stable |
| `given` / `recv` | gold given to / received from allies | score screen | stable |
| `pool_out` / `pool_in` | gold the map's autopool moved | anchor hook | stable |
| `inh_out` / `inh_in` | gold inherited from a fallen or leaving ally, including what an eliminated ally's autopool still forwards | anchor hook | stable |
| `ukills` / `hkills` | unit / hero kills, the map's own counters (= `-kd`, = the kill log) | map counter | stable |
| `razed` | buildings razed | score screen | stable |
| `food` | food used | score screen | stable |
| `koth_gold` | King of the Hill income | anchor hook | stable |
| `deny_own` / `deny_ally` | own / an ally's spawns killed by the slot | map events | stable |
| `tm_casts` / `tm_hits` / `tm_denied` / `tm_saves` | Transmute outcomes | map events | stable |
| `tm_creeps` | the `tm_hits` whose target was a creep hired at a creep shop | map events | stable |
| `creeps` / `creep_gold` | creeps hired, gold paid | map events | stable |
| `atk_lvl` / `def_lvl` / `race_lvl` / `team_res` | upgrade levels; research at the team building | tech counts | stable |
| `mined` | gold "mined". It includes pooled, inherited, KotH and start gold (e2e 799x-ffa: slot 2 `mined` 25763 = 136 + `pool_in` 25627) | score screen | probation |
| `tech` | the score screen's tech score; may credit allies' research | score screen | probation |
| `hero_lvl` | highest hero level: a running maximum while alive, frozen at `out` / `left` | hero | stable |
| `deny_tower` | own spawns killed by an ally's building (the slot brought them to a teammate's tower); the tower's owner also counts them as `deny_ally` | map events | probation |
| `dmg_out` / `dmg_bld` / `dmg_in` | damage to non-structures / structures / taken, between non-allies, overkill included | damage events | probation |

`modes,<k>=<v>,...` (written once, when the modes are final): `sel`, `pub`, `inhouse`, `koth`, `club777`, `madness`,
`mirror`, `overdrive`, `colossal`, `onev1`, `debug`, `nomass`, `strong`. 799X adds `pro`, `notransmute`, `4k` and
`ffdebug` (our `-debug` was used: the row is written again with `ffdebug=1` when it comes after the modes were final);
Solo adds `nopool`. All are 0/1 except `sel` (the selected mode) and `colossal`.

`koth,<side>,hold=<s>,caps=<n>`: sides are numbered like `out` / `placement` (`team1..team4`, `west` / `east` in
6v6).

## Rules (invariants) and the tests that enforce them

| rule | enforced by |
|---|---|
| A `winner` only when exactly one side is left (the map's own `player_active`), never from leave order | simulation `799x_gameend`, `799x_forfeit`, `solo_forfeit`, `solo_game`; e2e `ffa`, `solo`, `observer`, `solo-observer` |
| A forfeit is a result: sides that have left are out, the side left standing wins, and the map's END agrees | simulation `799x_forfeit`, `solo_forfeit` (incl. the map's victory) |
| A player who leaves while allies stay is not out (the map hands the base over) | simulation `799x_forfeit` |
| A game nobody won has no `winner` / `placement` / `gameend`, and the bot does not score it | simulation `799x_dissolve`, `solo_dissolve`; `ff test ladder` (`--unscored`) |
| Nothing changes after `gameend` (leaving the score screen, more deaths) | simulation `799x_leave_after_end` (leaves and a death after `gameend`) |
| `gameend` exactly once, after every other result record; placements 1..N, no ties | e2e `check_files`; selftest (dropped `gameend`, a tie) |
| `format,2` is the first record; `gameend` is the **last** record, and the `PreloadEnd` trailer is the commit marker. A reader treats a file as finished only with both, so a file cut off mid-write never looks finished | simulation `799x_gameend`, `solo_game`; e2e `check_files`; the bot's parser (`efl_league/ff_result.py`) |
| The roster names every participant from the start, and never an observer | simulation `799x_dissolve`, `799x_full_lobby`, `799x_observer`; e2e `observer`, `solo-observer` |
| A player without a hero 15 s after the mass began, once the gold pool is open (799X Pub: the 230 s trading timer; Pro, In-house and Solo: 15 s after the mass), is removed by the map's own kick (warned at 5 s and 10 s before a later kick); humans only, never a computer or an observer. The slot gets an `afk` record and no roster entry, stats, usage row or place in a side | simulation `afk_kick` (both maps, incl. a late pick before the kick; main Pub waits for the pool), `799x_afk_kick_pro` (Pro: 15 s); e2e `afk` (both maps, the client itself) |
| A leaver's stats row: `state=left`, `left_t=<mm:ss>` | simulation `799x_players`, `799x_forfeit`, `solo_forfeit` |
| Every `Preload` string ≤ 259 characters (the game silently truncates longer ones) | simulation (`PRELOAD_MAX` fails any longer row; `799x_full_lobby`); e2e `observer` (12 long battletag-like names) |
| Every stats key present, engine values non-zero where the scenario caused them | e2e `ffa`, `solo`; selftest (a counter stuck at 0, a lost second row) |
| The bot's parser reads every record the map writes; the league stores the match | simulation `contract.py`; `ff test ladder`; `ff test e2e --ladder` |
| One K/D: only an enemy kill of a non-illusion by a living unit of slots 1-12 counts (no own / allied kills, illusions, dead killers, creeps); an enemy tower's kill counts for its owner. Kill log = stats `ukills`/`hkills` = `-kd` | simulation `kd` (both maps); e2e `kd` (real 3.0 client, incl. a real tower attack and a Wand of Illusion illusion); selftest (a kill log one kill off) |
| The kill log is written one last time at `gameend` and then frozen, so it equals the final stats rows | simulation `799x_kd_gameend` |
| Gold between allies per route: `-pool` in `pool_out`/`pool_in`, the Allies menu in `given`/`recv`, a fallen ally's gold in `inh_out`/`inh_in`; script gold moves never reach `given`/`recv`; autopool from an eliminated player, or into one who has left, is `inh_*`, never `pool_*`; out − in over all routes = gold really given | simulation `799x_trade`, `799x_pool_net`, `799x_pool_fallen`, `799x_pool_leaver`; e2e `trade` (a real Allies-menu trade and `-pool` there and back), `ffa` (autopool, inheritance and `SetPlayerState` leave `given`/`recv` at 0); selftest |
| Kill-log rows: owner rows 5 fields, feed rows 6 fields; only bot clients write it | e2e `check_files`; selftest (a short row) |
| `ff_ping_<token>.txt`: bot clients only, strictly anonymous (`format,1`, `round`, `summary`, `pingend`; zero BattleTags, player names or slot indices; every `Preload` line ≤ 259 chars) | simulation `ping_probe`, `ping_probe_nonbot` |
| `use` `tech` is the level reached; `rsch`/`rlvl` count only the levels a player researched themselves and their sum (allies' team copies, start-of-game and mode grants fire no research event), so an upgrade costing base + step × (level − 1) cost base × rsch + step × (rlvl − rsch). `pawn` counts items sold back to a shop, for the selling player; the purchase stays in `item` | simulation `799x_economy` |
| Observer commands are not counted as player usage | simulation `799x_observer`; e2e `observer`, `solo-observer` |

## Porting checklist: a Lua map

- **Unchanged:** `tests/e2e/run.py`, `check_e2e.py`, `ladder_check.py`, `selftest.py`, `tests/simulation/contract.py`.
  They read files only.
- **The writers:** `GameResult`, `Stats`, `Usage`, `KillLog` must write the same records, row for row. The C# originals
  are in `lua/Source/`, but stats and usage exist only in JASS today, and `KillLog.cs` still keeps its own tallies (the JASS kill log
  reports the map's `-kd` counters, filters the hero feed like the map, caps it and freezes at `gameend`). The 259-character limit applies in Lua
  too.
- **e2e addons** (`tests/e2e/addons`): port them to Lua / C#, injected into `war3map.lua` instead of
  `war3map.j`. The phase protocol and records stay the same.
- **Simulation:** run the map's `war3map.lua` directly (no JASS→Lua step). The scenario helpers need the globals the
  map keeps (`udg_player_active`, `udg_base`, `udg_herO`, `gg_rct_*`). If the Lua map renames them, adjust the
  helpers, not the checks.
- **`verify-map`:** the checks that read the script text need Lua versions
  (`tools/runner/Program.cs`: `--funcs` / `FF_Init` / `FF_EarlyInit` order, no `FF_E2E_`, the bot list in
  `FF_IsBotName`, `--stubs`, `--anchors`, the Credits quest, referenced dotted imports). The checks on the archive
  and the data stay as they are.
- **Static:** replace pjass with a Lua linter (luacheck) plus whatever the C#→Lua compiler checks.
- **Desyncs:** Lua is less forgiving of local-only work (`GetLocalPlayer`-gated reads). Neither the simulation nor a
  one-client e2e run sees a desync.
- **While both flavours exist:** run the same suite against both. The same scenario must produce the same records.
