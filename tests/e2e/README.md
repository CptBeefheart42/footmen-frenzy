# e2e — the real maps in the real WC3 3.0 client

What only the engine and the bot's own code can show: the numbers the score screen fills in, damage, deaths,
true-sight detection, chat commands typed into the game, the files the bot reads (names, row lengths, the kill log),
and what the bot's parser and the league make of them. Manual, before a release, on the machine with the test client
(`~/wc3-test`). The simulation tests (`tests/simulation`) cover what the map *script* decides, on every push.

```
ff e2e suite                    # everything (~100 min): the probe + every scenario (tools/ff/e2e.py SUITE), each
                                #   judged, then the ladder check
ff e2e run 799x ffa             # one scenario: build, play, judge (build/e2e/799x-ffa/)
ff e2e build 799x ffa           # only its test map (build/e2e/ff-e2e-799x-ffa.w3x)
ff e2e check 799x ffa           # judge the last run again
ff e2e probe                    # the WC3 3.0 probe map: build (needs the pre-3.0 install, setting wc3_stage), play, judge
ff e2e ladder                   # score the finished games with the efl-bot checkout (setting efl_bot)
python3 tests/e2e/selftest.py build/e2e/799x-ffa build/e2e/probe   # doctored copies of the last real runs must FAIL
```

## The test client

- `~/wc3-test`: a Proton prefix with Battle.net + WC3 3.0 (setup: `docs/testing-plan.md`), logged in with a
  **dedicated test account** ("keep me logged in"; its credentials live in the untracked env file below). Never one
  of the fleet's accounts, never `~/wc3-stage`.
- When the saved session is gone (Battle.net shows its login window, no game starts), the runner logs in by itself:
  `tests/e2e/bnet_login.py` (also by hand) restarts Battle.net and types the test account's credentials from
  `~/.config/footmen-frenzy/e2e-bnet.env` (`FF_E2E_BNET_EMAIL` / `FF_E2E_BNET_PASSWORD`, mode 600, never in git, never
  logged). An e-mail security code can't be automated: it has to be typed in by hand.
- `FF_WC3_PREFIX` points the runner at another prefix.

## How a run works (`run.py`)

1. Battle.net closed (its main window closed; when it only hides in the tray, the runner launches WC3 once so it
   exits by itself, then closes the game).
2. The map copied to `Maps/Test`; `-nowfpause -windowmode windowed` into `Battle.net.config`'s WC3 launch arguments,
   Battle.net started, asked to launch WC3, the arguments removed again (always, also on failure).
3. The runner clicks through the menus like a player (`run.py` `start_from_menu`): Single Player, Custom Games, Quick
   Filter "Test", Open Folder, Quick Filter with the map's lobby name (`--lobby`: `FF e2e [<map> <scenario>]`, the
   probe's `FF 3.0 Probe [probe]`; the closing bracket keeps one name from matching another), Create, Start Game. The
   lobby seats the map's own Computer slots and the client in the first User slot, an observer slot when every seat
   is a computer. The clicks are window pixels of the client's 1402x824 game window, scaled to another size. When WC3
   shows its own Battle.net login instead of the main menu, the run stops with exit code 2 (`wc3-login.png`): log in
   once by hand. `-loadfile` isn't used: since 3.0.1 a game started with it ignores the Battle.net login and, logged
   in on its own screen, never loads the map.
4. "Press any key": space until the map writes its first file. A map that hasn't started after 300 s (a loading
   screen that sits at ~85%) is taken for a hang, closed and launched once more. While it loads, the game's memory is
   watched: above `FF_WC3_LOAD_RSS_MAX_GB` (default 7), or when the game exits before the map writes a file, the run
   stops at once with exit code 3.
5. The map's test addon asks for input through `CustomMapData/ff_e2e_phase.txt`: `WAIT <n> chat <text>` (the runner
   types it into the chat and takes a screenshot, `chat-<n>.png`), `WAIT <n> key <key>` (one key press) or
   `WAIT <n> click <x> <y>` (a click into a dialog, see below) or `WAIT <n> seq <step>;...` (keys and single clicks
   in a row, for a menu that pauses the game: `key <key>`, `tap <x> <y>`, `wait <s>`, `shot`; a screenshot after each key, tap and shot). Click and tap positions are fractions of the game's 4:3 UI area (as tall as
   the window, centred in it: `client.ui_point`), so they hold at any window size. Input goes to the focused game window as real key and
   mouse events — WC3 under Wine ignores xdotool's `--window` events.
6. Done when `ff_e2e.txt` ends with `END`; the outputs (`ff_result*`, `ff_killlog*`, `ff_e2e*`) and the screenshots
   land in `build/e2e/<map>-<scenario>/`; WC3 is closed (window, then the process).
7. A crash ends the run at once: when the WC3 process is gone or its crash reporter (`BlizzardError.exe`) is up, the
   runner writes `crash.txt` (seconds into the game, the last `ff_e2e.txt` record) and copies WC3's new crash reports (a
   folder each: `Crash.txt`, `War3Log.txt`, `War3.dmp`) to `Errors/`. Every scenario's check then fails "the client did not crash".

## e2e builds (`tests/e2e/addons`, never released)

`ff e2e build` = the release build of the map + `tests/e2e/addons/core` + `tests/e2e/addons/<scenario>` (+ the
shared folders its `include` file names, one per line), and:

- the participant slots the scenario's `slots` file names become Computer slots in the map's player data
  (`FF_SLOT_CONTROLLERS`), so the one client sits in the first slot left a User slot;
- the client (offline WC3 calls it `Local Player`, which the league drops: not a battletag) is renamed to `E2E_BOT`
  (default `(E2E)Tester#100000`) before the map records the names, and that name is appended to the bot list, so the
  client gets what a fleet bot gets: token file names, the kill log, BotVision — and counts as a ladder player;
- the computer slots get long battletag-like names (`(E2E)LongBattleTag05#100005`), like a full real lobby.

`verify-map` (the release gate) rejects any map with `FF_E2E_` symbols or a bot list that differs from
`league/00-common.j`.

The computers do nothing on their own (the map has no AI): the scenario gives every slot its hero by creating it in
the tavern area, where the map's own `TP_hero` makes it the slot's hero. Everything else goes through real orders
(shops, research, upgrades, spells) and real damage (`UnitDamageTarget`), so the map's triggers and the engine's score
screen count it like in a real game. The addon only records (`ff_e2e.txt`); `check_e2e.py` judges.

## Scenarios

| scenario | map | client | what it covers |
|---|---|---|---|
| `observer` | 799X | slot 13 (team 4), like a fleet bot | seating; token file names + kill log; **BotVision**: an invisible unit seen by the bot and the owner's team only, `IsUnitInvisible` per slot, the bot's shared vision revoked, the detector grid (count, coverage, still there after Mass END), an invisible unit at each of the 81 grid cells seen by the bot at night; `-cam 1` (camera on the hero), `-zoom 3500`, `-cam off`, `-kd`, `-time`; a scripted unit + hero kill in the map's counters and the kill log; observer commands not counted as usage; **the game to its end in the observer's own file** (the one the fleet reports): the bases fall to the Raze skill, winner / placements / `gameend`, the observer in no roster or placement, BotVision still on afterwards |
| `ffa` | 799X | slot 1 (participant) | a whole game to `gameend`: item / creep purchases, research (attack x2, armor, team research), tower and base upgrades, the skill build, Transmute hit / denied / dodged, denies, kills, `-kd -time -cam -zoom -pool` counted as `use,1,cmd`, autopool, King of the Hill, gold inherited from a fallen ally, eliminations, placements, every stats key — exact where the scenario controls it, ranges for engine values |
| `solo-observer` | Solo | slot 13 (first observer slot), like a fleet bot | the computer host's AFK timer starts the game; BotVision on an invisible unit; `-kd` not counted as usage; the bases fall to the Raze skill; the spectator's file: roster of the four seats, winner, placements, `gameend`, the Solo modes row |
| `solo` | Solo | slot 1 (participant) | a whole 1v1v1v1 deathmatch game: the four Solo seats, purchases, research, kills, KOTH, placements, the Solo modes row |
| `afk` | 799X + Solo | slot 1 (participant, never picks a hero) | the AFK kick: the mass begins (main 90 s, Solo 50 s), the warning 5 s later (screenshot), the kick 15 s after the mass began (main Pub: when the trading timer opens the gold pool) through the map's own kick (an action after it records the state; the defeat dialog's screenshot); the computers without a hero stay; the result file: an `afk` record with the client's name, slot 1 in no roster, stats or usage row |
| `transmute_destroyed`, `transmute_left` | 799X + Solo | slot 1 (participant, the Alchemist) | a Transmute projectile in the air when the side of its target drops out — its last player destroyed (the base falls) or left (the map's own kick); on main the side's allies (slots 5, 6) go first the same way, so slot 4 is its last player; on Solo it is slot 5. The control first: a deny (the target's own footman kills it in flight, no crash). Then the loss, 30 s of play (Solo removes a lost player's units ~20 s later), the side out of the game, the Transmute counters (a leaver's target is hit on Solo, dodged on main). A crash fails the run with `loss` as the last record. One shared script (`transmute/`), one run per loss: a crash ends the run. **Single player does not reproduce the multiplayer crash** this guards against: the target's owner is a computer, whose client never leaves the game; the crash needs a human whose client really leaves (see below) |
| `skills` | 799X + Solo | slot 1 | every hero skill (~280) at every level the engine gives it: every stored numeric cell read back (`BlzGetAbility*LevelField`), then one cast per level (8 at a time, a fresh caster with 100000 mana, enemy / enemy hero / damaged ally / own unit / point / instant, one retry elsewhere). Mana spent and cooldown started must equal the map's `amcs` / `acdn`: the WC3 3.0 level-fill check in the real client. Data from `gen_skills.py` (map object data + map fixes), orders from `gen_orders.py` (the test client's game data), known cases in `skills_exceptions.csv`; a skill fails when 2+ of its levels are refused or have no effect (single misses move between runs). ~12 min per map |
| `kd` | 799X | slot 1 (participant) | the map's -kd counters case by case before Mass START: an enemy footman (a kill and a death), own and allied footmen, an illusion (Wand of Illusion), a killer already dead (counted for its owner), a neutral-aggressive killer, slot 4's cannon tower killing a footman by its own attack (kill for the tower's owner), enemy and allied heroes; then kill log = stats `ukills`/`hkills` = the counters of all 12 slots at one snapshot, and `-kd` |
| `kill_credit` | 799X | slot 1 (participant) | enemy heroes killed by a killer that is dead, or a spell dummy, when the damage lands — a moneybag's Kaboom (coin factory), Objection's Soul Burn and Parasite ticks after the dummies' old 0.10 s life, a Hellfire Flame Strike tick, a Rain of Fire burn after Jaina's orbs vanished, Thor's hammer Firebolt — by real casts: each counts for slot 1 (hero kill, hero death, the engine names a slot-1 killer, slot 1's hero earns XP); then stats `ukills`/`hkills` = the counters of all 12 slots |
| `towerfire` | 799X | slot 1 (participant) | a tower's attack on friendly units before Mass START: a cannon's splash kills an enemy next to its target (control) but spares allied and own footmen, also the Arcane Tower of Terror's; a tower accepts an attack order on an allied or own footman (order event `attack` + that target) and kills only that one; the deny counters per case; from Mass START on, every order event counted (~250/s, almost all the map's own) and the map never orders a building to attack a friendly unit |
| `trade` | 799X | slot 1 (participant) | gold between allies once the map allows it (~240 s): `-pool` to slot 2 and 400 back (`pool_out`/`pool_in`, the score screen untouched); the Allies menu by real input (single player disables its button, so the script clicks it open; the runner clicks slot 2's gold icon three times and Accept): the score screen's gold given = received = 300, the gold of both slots moves by exactly that in the tick it lands, no pool counter moves; the stats rows carry both routes |
| `transmute_creeps` | 799X + Solo | slot 1 (participant, the Alchemist) | which Transmutes count as `tm_creeps`: two enemy sides hire four creeps (`n00A`, level 3: Transmute takes creeps up to level 6-8, the level-10 Turtle never) through real sales at the creep shops, each marked as hired; one Transmute per case at the empty map centre: on a hired creep (a hit and a `tm_creeps`), on the same creep type nobody hired (a hit only), on a footman (a hit only), on a hired creep its own side kills first (denied, a save for that side), on a hired creep removed in flight (a cast only); a hired creep killed without a Transmute leaves the hired group; then the stats rows, the kill log and the counters at one snapshot, the game paused so no later flush adds to them |
| probe | probe map | — | `ff e2e probe`: the WC3 3.0 ability data the client loaded + Blizzard's damage by level (`check_probe.py`, `probe_expect.csv`) |

Not covered (single player can't): a second human (another observer seeing the bot's detection), a real leaver,
desyncs, and the multiplayer crash when a Transmute projectile is in the air while its target's owner leaves or is
destroyed (crashes every client; `transmute_*` show single player survives the same steps). Leaving is covered by the simulation (`main_forfeit`, `main_dissolve`, `main_leave_after_end`, `solo_forfeit`,
`solo_dissolve`). The rules are listed with
their tests in `docs/result-contract.md`.

### The Raze skill (`E2Ra`, e2e builds only)

`tests/e2e/addons/core/object_overrides.csv` adds an ability to every e2e build: a creep Storm Bolt copy (`ACtb`) with unlimited range, no
cost and no cooldown. `FF_E2E_Raze(caster, target)` orders the cast, and the spell's effect deals the killing damage
from the caster. A scripted kill then goes through a real order and cast with a hero as the killer, and a manual test
can end a game with it. The observer scenarios kill the bases with it. **Known limitation:** the engine refuses the
order on an enemy base, even from 300 away; `FF_E2E_Raze` then deals the damage directly from the caster, and the
checks only report the cast counts (`INFO Raze`). The build path's `Obj,<new>,0,0,String,<base>` row creates the
object.
`verify-map` rejects any `E2xx` ability.

Dialogs pause a single-player game, so the runner answers them with real clicks (`WAIT <n> click <x> <y>`): the
host's game-type dialog when the client is Player 0 ("Pub Game Default") and the autopool dialog after `-pool` (the
first ally); the addon asks for the click from inside the event that opens the dialog.

## The ladder check (`ladder_check.py`)

`ff e2e ladder` runs `ladder_check.py` with the efl-bot checkout of the setting `efl_bot` (and its `.venv` Python)
on the finished games (`799x-observer`, `799x-ffa`, `solo-solo`, `solo-solo-observer`): the bot's parser, the kill-log attribution, `to_report_payload`,
`POST /report_match` on the league API into a throwaway sqlite DB, then the stored match: placements, every roster
player, Elo (winners up, last place down), kills, the stats / telemetry if that bot version knows them. Records the
bot version doesn't know are listed, never an error. `FF_EFL_BOT=<checkout>` scores with another checkout (a bot PR).

## Gotchas

- **Preload keeps 259 characters of a string, silently.** So each slot's stats come in two `stats` rows with the same
  `t=`, a long roster continues in `roster_more` rows, and the simulation fails any longer row.
- A **paused** unit loses its permanent invisibility (`Apiv`): visibility tests must use unpaused units.
- Offline, the client's name is `Local Player`, which the league drops (it keeps only battletag-like names), so the
  e2e build renames the client. The map renames players at their hero pick (`(Paladin) Red`), so the kill log names
  them that way.
- After Mass END (~246 s) the map kills units entering the tavern area / hero showroom.
- The empty observer slots see nothing at all, so they can't stand in for a second (human) observer.
- Many logins in a row (every run starts Battle.net) can trigger Battle.net's security checkpoint: Battle.net hangs
  on a spinner and WC3 never starts ("no WC3 window"). Stopping Battle.net and starting it once more clears it; if it
  asks for an e-mail code, that code has to be typed in by hand.
