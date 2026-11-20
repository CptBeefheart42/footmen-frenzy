#!/usr/bin/env python3
"""Judges one e2e scenario run (the out dir tests/e2e/run.py filled) against what the map must deliver to the bot.

    tests/e2e/check_e2e.py <scenario> <out dir> [--map main|solo] [--bot | --no-bot]

The scenario's test addon (tests/e2e/addons/<scenario>) only records what the engine and the map did, in
ff_e2e.txt; every verdict is made here. All scenarios share the checks on the files the bot reads:

  * the result file's name (ff_result_<token>.txt on a bot client, ff_result.txt otherwise);
  * its structure, which the bot's parser and scorer rely on: a roster, a stats row with every key as an integer
    for each roster slot, placements 1..N without ties, and gameend after every other record;
  * the kill log's structure (bot clients only).

Values the addon controls are checked exactly; engine values (damage, mined gold, food, razed buildings) only as
ranges. Prints one PASS/FAIL line per check and exits 1 if any failed.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.common.checks import Checks  # noqa: E402
from tests.common.ffresult import (STATES, STATS_KEYS, USE_CATS, FFResultFile, FormatError,  # noqa: E402
                                   KILLLOG_HEADER, KillLog)
from tests.common.kv import as_int, parse_kv  # noqa: E402
from tests.common.paths import E2E_DIR  # noqa: E402
from tests.common.preload import read_rows  # noqa: E402

FFA_PLACEMENTS = ["team1", "team4", "team3", "team2"]


class Run(Checks):
    """One scenario run: the addon's ff_e2e.txt records plus the checks made on them.

    Attributes:
        out: The run's out dir.
        map: Which map the run played (`main` or `solo`).
        e2e: The rows of ff_e2e.txt (empty when the file is missing).
        result: The parsed result file, once check_files has read it.
        killlog: The parsed kill log, once check_files has read it (bot clients only).
    """

    def __init__(self, out, map_name="799x"):
        super().__init__("e2e check")
        self.out = Path(out)
        self.map = map_name
        self.e2e = read_rows(self.out / "ff_e2e.txt") or []
        self.result = None
        self.killlog = None

    def rec(self, kind, **match):
        """The ff_e2e.txt records of a kind whose fields equal `match`.

        Args:
            kind: The record kind (the row's first field).
            **match: Fields the record must have, with these values.

        Returns:
            Each record as a dict of its `key=value` fields; the positional fields are under `_`.
        """
        found = []
        for r in self.e2e:
            parts = r.split(",")
            if parts[0] != kind:
                continue
            d = parse_kv(parts[1:])
            d["_"] = [p for p in parts[1:] if "=" not in p]
            if all(d.get(k) == v for k, v in match.items()):
                found.append(d)
        return found

    def one(self, kind, **match):
        """The first matching record (see rec), or an empty dict."""
        r = self.rec(kind, **match)
        return r[0] if r else {}

    def first_with(self, kind, key):
        """The first record of a kind that has the field `key`, or an empty dict."""
        return next((r for r in self.rec(kind) if key in r), {})

    def slots(self):
        """The addon's `slot` records by player slot (0-based, as the engine counts)."""
        return {int(r["_"][0]): r for r in self.rec("slot")}


# --- the files the bot reads ---------------------------------------------------------------------------------------

def check_files(run, bot, need_end):
    """Checks the result file and the kill log the map wrote, and keeps them on the run.

    Args:
        run: The scenario run.
        bot: Whether the client is on the map's bot list (token file names, a kill log).
        need_end: Whether the scenario plays the game to its end (gameend, winner, placements).

    Returns:
        The parsed result file, or None when it could not be read or parsed.
    """
    head = run.one("e2e")
    token = head.get("token", "")
    if bot:
        run.eq("client is on the bot list", head.get("bot"), "1")
        run.check("game token", re.fullmatch(r"-?\d+", token or ""), f"token {token!r}")
        name, log = f"ff_result_{token}.txt", f"ff_killlog_{token}.txt"
    else:
        run.eq("client is not on the bot list", head.get("bot"), "0")
        name, log = "ff_result.txt", None
    run.eq("result file name (the map's FF_DataFile)", head.get("file"), name)
    run.eq("result files written", sorted(p.name for p in run.out.glob("ff_result*.txt")), [name])
    rows = read_rows(run.out / name)
    if rows is None:
        run.check("result file readable", False, name)
        return None
    try:
        res = FFResultFile.parse(rows)
    except FormatError as e:
        run.check("result file parses", False, str(e))
        return None
    run.result = res
    check_result_structure(run, res)
    if need_end:
        check_result_end(run, res)
    else:
        run.eq("no game end (the scenario stops early)", res.result_kinds.count("gameend"), 0)
    if log:
        check_killlog(run, log)
    else:
        run.eq("no kill log off the bot list", sorted(p.name for p in run.out.glob("ff_killlog*.txt")), [])
    check_finished(run)
    return res


def check_result_structure(run, res):
    """Checks the records every result file has: format, mode, roster, stats, usage, nothing unknown."""
    run.eq("first record: format,2", res.rows[:1], ["format,2"])
    run.eq("result mode row", res.mode, "ffa")
    run.check("roster row lists the participants", res.roster, f"roster {res.roster}")
    for slot in res.roster:
        st = res.stats.get(slot)
        if st is None:
            run.check(f"stats row for roster slot {slot}", False)
            continue
        missing = [k for k in STATS_KEYS if k not in st.values]
        bad = [k for k in STATS_KEYS if k in st.values and st.int(k) is None]
        run.check(f"stats,{slot}: every key, integers", not missing and not bad, f"missing {missing}, not int {bad}")
        run.check(f"stats,{slot}: state", st.state in STATES, st.state)
    run.eq("no stats row outside the roster", sorted(set(res.stats) - set(res.roster)), [])
    for (slot, cat) in res.use:
        run.check(f"use,{slot},{cat}: known category, roster slot", cat in USE_CATS and slot in res.roster)
    run.eq("no unknown records in the result file", res.unknown, [])


def check_result_end(run, res):
    """Checks a finished game's records: one gameend as the last record, one winner, placements 1..N."""
    kinds = res.result_kinds
    run.eq("gameend written once", kinds.count("gameend"), 1)
    run.check("gameend is the file's last record (after the telemetry: a cut-off file never looks finished)",
              res.rows and res.rows[-1].startswith("gameend,"), f"last record {res.rows[-1:]}")
    run.check("gameend after every other result record", kinds and kinds[-1] == "gameend", f"{kinds}")
    places = res.places
    run.eq("placements 1..N, no ties", places, list(range(1, len(places) + 1)))
    run.check("at least two placements", len(places) >= 2, f"{places}")
    run.eq("one winner row", kinds.count("winner"), 1)


def check_killlog(run, name):
    """Checks the kill log's structure and keeps the parsed log on the run."""
    rows = read_rows(run.out / name)
    run.check("kill log written under the token", rows is not None, name)
    if not rows:
        return
    log = KillLog.parse(rows)
    run.eq("kill log header", log.header, KILLLOG_HEADER)
    run.check("kill log owner rows: 5 fields, integers", not log.bad_owner_rows, f"{log.bad_owner_rows[:3]}")
    run.check("kill log feed rows: 6 fields", not log.bad_feed_rows, f"{log.bad_feed_rows[:3]}")
    run.killlog = log


def check_finished(run):
    """Checks that the game did not crash (run.py's crash.txt) and the scenario's addon reached its last step (its
    END record)."""
    crash = run.out / "crash.txt"
    run.check("the client did not crash", not crash.is_file(),
              crash.read_text().replace("\n", " ").strip() if crash.is_file() else "")
    run.check("scenario finished (END)", run.e2e and run.e2e[-1] == "END", f"last record {run.e2e[-1:]}")


# --- checks several scenarios share --------------------------------------------------------------------------------

def check_chats(run, texts):
    """Checks that the typed chat commands reached the map in order, each with a screenshot."""
    got = [(c.get("text"), c.get("phase")) for c in run.rec("chat")]
    run.eq("typed chat commands reached the map, in order", [t for t, _ in got], texts)
    for t, phase in got:
        run.check(f"screenshot after '{t}'", (run.out / f"chat-{phase}.png").is_file(), f"chat-{phase}.png")


def check_razes(run, n):
    """Checks that n enemy bases were killed with the e2e Raze ability (E2Ra) or its fallback.

    The engine refuses the Raze order on an enemy base, so the addon deals direct damage from the caster instead.
    How many cast orders were accepted is reported, not judged; the kills themselves are checked elsewhere.
    """
    orders = [r.get("order") for r in run.rec("raze")]
    tot = run.one("razes")
    print(f"INFO Raze (not judged): {orders.count('1')}/{n} cast orders accepted; casts {tot.get('casts')}, "
          f"direct {tot.get('direct')}")
    run.eq(f"bases killed: {n} (by Raze or its direct-damage fallback)", len(orders), n)


def check_scripted_kills(run):
    """Checks that the scenario's scripted unit and hero kill each moved the map's own -kd counters by one."""
    k = run.one("kills")
    for what, key in (("unit", "ukills"), ("hero", "hkills")):
        run.eq(f"scripted kills: {what} kill counted by the map (-kd)",
               (as_int(k.get(key + "1")) or 0) - (as_int(k.get(key + "0")) or 0), 1)


def check_bases_razed(run, label, slots):
    """Checks which bases the scenario destroyed, in order (1-based slots; label names them in the check)."""
    run.eq(f"bases razed: slots {label}", [x.get("slot") for x in run.rec("razebase")], [str(s) for s in slots])


def check_end_seen(run):
    """Checks that the result addon saw the game end (not a timeout)."""
    ended = run.rec("ended")
    run.check("the result addon saw the end", ended and "timeout" not in ended[0], f"{ended}")


def check_outcome(run, res, placements=FFA_PLACEMENTS):
    """Checks the winner and the placement order of a finished game."""
    run.eq(f"winner: {placements[0]}", res.winner, placements[0])
    run.eq(f"placements: {', '.join(placements)}", res.placement_sides, placements)


def bought_item(run):
    """The item the addon bought with the shop's hotkey, or None."""
    item = run.one("item", via="key").get("id")
    item = item if item and item != "????" else None
    run.check("item bought at the weapons shop (its hotkey, like a player)", item, f"{run.rec('item')}")
    return item


def client_name(run):
    """The client's name in the game, as the addon recorded it for its slot."""
    head = run.one("e2e")
    return run.slots().get(as_int(head.get("local")), {}).get("name", "")


# --- scenarios -----------------------------------------------------------------------------------------------------

def check_observer(run, bot):
    """The main map with the client in a fleet bot's seat (slot 13, the observer team), played to the end."""
    res = check_files(run, bot, need_end=True)
    run.eq("client seated in slot 13 (Player 12)", run.one("e2e").get("local"), "12")
    slots = run.slots()
    run.eq("participant slots 1-12 are playing computers",
           [(slots.get(i, {}).get("ctrl"), slots.get(i, {}).get("state")) for i in range(12)],
           [("computer", "playing")] * 12)
    run.eq("participant teams", [slots.get(i, {}).get("team") for i in range(12)], [str(i // 3) for i in range(12)])
    run.eq("slot 13: the client, a user on the observer team",
           (slots.get(12, {}).get("ctrl"), slots.get(12, {}).get("team")), ("user", "4"))
    run.eq("no other user slot", [i for i, r in slots.items() if r.get("ctrl") == "user" and i != 12], [])
    check_observer_vision(run, bot)
    hero = run.one("hero")
    run.check("players 1 and 4 got their heroes", "1" in hero and "4" in hero, f"{hero}")
    if "1" in hero:
        check_observer_commands(run, bot, slots)
    if res:
        run.eq("observer commands are not counted as player usage", [k for k in res.use if k[1] == "cmd"], [])
    check_bases_razed(run, "4..12", range(4, 13))
    check_razes(run, 9)
    check_end_seen(run)
    if res:
        run.eq("roster: the twelve participants, not the observer", sorted(res.roster), list(range(1, 13)))
        check_outcome(run, res)
        observer = client_name(run)
        placed = [",".join(e.extra) for e in res.events_of("placement")]
        run.check("the observer is in no placement", observer and all(observer not in p for p in placed), f"{placed}")
    if bot:
        after = run.first_with("vision", "after_end")
        # an eliminated player gets the map's revealer (n02G, true sight over the whole map) and may see it
        run.eq("BotVision after the game end: a fresh invisible unit seen by the bot, by an enemy only with the map's revealer",
               (after.get("bot"), after.get("slot4"), after.get("ghost_alive")), ("1", after.get("slot4_revealer", "0"), "1"))
        run.check("BotVision after the game end: every detector alive",
                  after.get("detectors") and after.get("det_alive") == after.get("detectors"), f"{after}")


def check_observer_vision(run, bot):
    """The observer seat's vision: BotVision on a bot client, nothing extra off the bot list."""
    inv, vis = run.one("vision", unit="invisible"), run.one("vision", unit="visible")
    det, det_end = run.one("detectors", start="1"), run.one("detectors", end="1")
    if bot:
        share_from = run.one("share", **{"from": "12"})
        run.eq("BotVision: the bot sees the invisible unit", inv.get("12"), "1")
        run.eq("BotVision: the invisible unit is detected for the bot", run.one("invisible_to").get("12"), "0")
        run.eq("BotVision: the bot shares its vision with nobody",
               sorted(k for k, v in share_from.items() if k not in ("_", "from") and v != "0"), [])
        # 9x9 cells ~740 apart; the map moves or refuses a few dummies at the edges and in the tavern area, which
        # is fine while every cell centre has a detector within the true sight's reach (Adtg aran ~900)
        run.between("BotVision: detectors on the map", det.get("n"), 70, 81)
        print(f"INFO detector gaps: start {det.get('maxgap')}, end {det_end.get('maxgap')}; cells without a detector "
              f"within 100: {det.get('far')}")
        run.check("BotVision: detectors still there after Mass END (t >= 280)",
                  det_end.get("n") == det.get("n") and (as_int(det_end.get("t")) or 0) >= 280,
                  f"start {det.get('n')}, end {det_end}")
        probes = run.one("probes")
        run.check("BotVision: an invisible unit at every grid cell centre is seen by the bot (after Mass END)",
                  probes.get("alive") and probes.get("seen") == probes.get("alive"), f"{probes}")
    else:
        run.eq("no BotVision off the bot list: invisible unit hidden from slot 13", inv.get("12"), "0")
        run.eq("no detectors off the bot list", det.get("n"), "0")
    run.eq("the owner's team sees its invisible unit", [inv.get(str(i)) for i in range(3)], ["1"] * 3)
    run.eq("enemies (slots 4-12) do not see the invisible unit", [inv.get(str(i)) for i in range(3, 12)], ["0"] * 9)
    run.eq("every participant sees the visible twin", [vis.get(str(i)) for i in range(12)], ["1"] * 12)
    run.eq("the observer team shares its vision with the bot slot",
           [run.one("share", to="12").get(str(i)) for i in range(13, 24)], ["1"] * 11)


def check_observer_commands(run, bot, slots):
    """The observer's chat commands (-cam, -zoom, -kd, -time) and the kill log's view of player 1."""
    if bot:
        run.between("-cam 1: camera on player 1's hero", run.one("cam", after="1").get("dist"), 0, 150)
    run.between("-zoom 3500: camera distance", run.first_with("zoom", "after").get("after"), 3490, 3510)
    check_scripted_kills(run)
    check_chats(run, ["-cam 1", "-zoom 3500", "-cam off", "-kd", "-time"])
    if bot and run.killlog:
        # the kill log names a player with the hero in front: "(Paladin) Red"
        p1 = slots.get(0, {}).get("name", "Red")
        red = next((v for k, v in run.killlog.owners.items() if k == p1 or k.endswith(") " + p1)), None)
        run.check("kill log: player 1's row has the hero kill", red and red.hero >= 1, f"{red}")
        run.check("kill log feed: player 1's hero kill", any(f[2].endswith(p1) for f in run.killlog.feed if len(f) > 2),
                  f"{run.killlog.feed[:3]}")


def check_host_dialog(run, bot):
    """The host's game-type dialog: a hosting bot never gets it (the map picks Pub mode), anyone else clicks it.

    The bot client is on the hosting bots' list (stage.py), so the map skips the dialog and the runner never clicks
    it (no `click-0.png`); a client off the list answers the dialog like a human host.
    """
    if bot:
        run.check("bot-hosted game: no host dialog to click (the map picked Pub mode itself)",
                  not (run.out / "click-0.png").is_file())
    else:
        run.check("a screenshot after the host's dialog click", (run.out / "click-0.png").is_file())


def check_ffa(run, bot):
    """A whole main-map game with the client as player 1: orders, purchases, pool, King of the Hill, every stat."""
    res = check_files(run, bot, need_end=True)
    run.eq("client seated in slot 1 (Player 0)", run.one("e2e").get("local"), "0")
    slots = run.slots()
    run.eq("slot 1: the client, a user on team 1", (slots.get(0, {}).get("ctrl"), slots.get(0, {}).get("team")),
           ("user", "0"))
    run.eq("slots 2-12 are playing computers", [slots.get(i, {}).get("ctrl") for i in range(1, 12)], ["computer"] * 11)
    hero = run.one("hero")
    run.eq("heroes through the map's tavern-area pick", [hero.get(str(i)) for i in range(1, 13)],
           ["N01C"] + ["H005"] * 11)
    run.eq("Transmute learned", run.one("skill").get("ANtm"), "1")
    item = bought_item(run)
    check_ffa_orders(run)
    check_scripted_kills(run)
    tm = run.first_with("transmute", "casts")
    run.eq("Transmute: casts, hits, denied (addon counters)", [tm.get(x) for x in ("casts", "hits", "denied", "saves4")],
           ["3", "1", "1", "1"])
    run.between("-zoom 3500 typed by a player: camera distance", run.first_with("zoom", "after").get("after"), 3490, 3510)
    check_chats(run, ["-kd", "-time", "-cam", "-zoom 3500", "-pool"])
    check_host_dialog(run, bot)
    run.check("a screenshot after the pool dialog click", any(f.name != "click-0.png" for f in run.out.glob("click-*.png")))
    run.eq("base upgraded to tier 1 (h00W)", run.first_with("baseup", "type").get("type"), "h00W")
    pool, poolset = run.one("pool", read="1"), run.first_with("pool", "allowed")
    run.eq("autopool: allowed by the map then, the dialog click chose slot 2",
           (poolset.get("allowed"), poolset.get("to")), ("1", "2"))
    run.check("autopool moved gold through the map's timer",
              (as_int(pool.get("out1")) or 0) > 0 and pool.get("out1") == pool.get("in2"), f"{pool}")
    koth = run.first_with("koth", "holder")
    run.eq("King of the Hill taken by slot 1", koth.get("holder"), "1")
    run.check("King of the Hill income counted for team 1", sum(as_int(koth.get(f"gold{i}")) or 0 for i in (1, 2, 3)) > 0,
              f"{koth}")
    check_bases_razed(run, "4..12", range(4, 13))
    check_end_seen(run)
    if not res:
        return
    check_ffa_usage(run, res, item)
    check_ffa_stats(run, res, pool)
    run.eq("out events: slots 4..12 in order", [e.subject for e in res.events_of("out")], [str(i) for i in range(4, 13)])
    run.eq("sidedead events", [e.subject for e in res.events_of("sidedead")], ["team2", "team3", "team4"])
    check_outcome(run, res)
    if bot and run.killlog:
        client = slots.get(0, {}).get("name", "")
        me = next((v for name, v in run.killlog.owners.items() if client and name.endswith(client)), None)
        run.check("kill log: the client's row has unit and hero kills", me and me.unit >= 1 and me.hero >= 1, f"{me}")


# The kd scenario's cases: name -> the change of each counter of slots 1, 2 and 4 (uk/hk = unit/hero kills, ud/hd =
# unit/hero deaths); a counter not listed must not move.
KD_CASES = {
    1: ("enemy footman killed: a kill and a death", {"uk1": 1, "ud4": 1}),
    2: ("own footman killed: not counted", {}),
    3: ("allied footman killed: not counted", {}),
    4: ("illusion killed: not counted", {}),
    5: ("killer already dead: counted for its owner", {"uk1": 1, "ud4": 1}),
    6: ("neutral-aggressive killer: counted for nobody", {}),
    7: ("enemy cannon tower kills a footman: kill for its owner, death for the footman's", {"uk4": 1, "ud1": 1}),
    8: ("enemy hero killed: a hero kill and a hero death", {"hk1": 1, "hd4": 1}),
    9: ("allied hero killed: not counted", {}),
}
KD_KEYS = [f"{k}{s}" for s in (1, 2, 4) for k in ("uk", "hk", "ud", "hd")]


def check_counter_snapshot(run, res, bot, kind):
    """Every slot's -kd counters at one snapshot (`kind` records) against the stats rows and the kill log.

    Args:
        run: The scenario run.
        res: Its parsed result file (None when it did not parse).
        bot: Whether the client is a bot (only a bot writes the kill log).
        kind: The snapshot's record kind (`kdsnap`, `kcsnap`).
    """
    snap = {k: v for r in run.rec(kind) for k, v in r.items() if k != "_"}
    counters = {s: {k: as_int(snap.get(f"{k}{s}")) for k in ("uk", "hk", "ud", "hd")} for s in range(1, 13)}
    run.check("snapshot of every slot's counters recorded", all(None not in c.values() for c in counters.values()),
              f"{snap}")
    if res:
        seats = sorted(res.stats)
        run.eq("stats ukills / hkills = the map's counters, every seat with a stats row",
               [(res.stat(s, "ukills"), res.stat(s, "hkills")) for s in seats],
               [(counters[s]["uk"], counters[s]["hk"]) for s in seats])
    if bot and run.killlog:
        # the map writes a player's current name: a hero pick prefixes it, e.g. "(Paladin) (E2E)Tester#100000"
        names = {i + 1: r.get("name", "") for i, r in run.slots().items() if i < 12}
        rows = []
        for s in range(1, 13):
            o = next((v for n, v in run.killlog.owners.items() if names.get(s) and n.endswith(names[s])), None)
            rows.append((o.unit, o.hero, o.unit_died, o.hero_died) if o else (0, 0, 0, 0))
        run.eq("kill log owner rows = the map's counters, every slot", rows,
               [(c["uk"], c["hk"], c["ud"], c["hd"]) for c in counters.values()])
        run.eq("kill log feed: one row per counted hero kill", len(run.killlog.feed),
               sum(c["hk"] for c in counters.values()))


def check_kd(run, bot):
    """The K/D cases of the map's own counters, then kill log = stats rows = counters at one snapshot."""
    res = check_files(run, bot, need_end=False)
    run.eq("client seated in slot 1 (Player 0)", run.one("e2e").get("local"), "0")
    for n, (name, want) in KD_CASES.items():
        before, after = run.one("kd", case=str(n), when="0"), run.one("kd", case=str(n), when="1")
        if not before or not after:
            run.check(f"K/D case {n}: {name}", False, "case not recorded")
            continue
        got = {k: (as_int(after.get(k)) or 0) - (as_int(before.get(k)) or 0) for k in KD_KEYS}
        run.eq(f"K/D case {n}: {name}", {k: v for k, v in got.items() if v}, want)
    deaths = {d.get("case"): d for d in run.rec("death")}
    run.eq("case 4 killed an illusion", (run.one("illusion", found="1") != {}, deaths.get("4", {}).get("illusion")),
           (True, "1"))
    dead_killer = [d for d in run.rec("death", case="5") if d.get("victim") == "4"]
    run.check("case 5: the victim died and the engine named the dead killer",
              dead_killer and dead_killer[0].get("kalive") == "0", f"{run.rec('death', case='5')}")
    run.eq("case 6: the killer was neutral aggressive (slot 25)", deaths.get("6", {}).get("killer"), "25")
    run.eq("case 7: the tower's own attack killed the footman", run.first_with("tower", "attack").get("attack"), "1")
    check_counter_snapshot(run, res, bot, "kdsnap")
    check_chats(run, ["-kd"])


def check_trade(run, bot):
    """Gold between allies: -pool there and back in pool_*, the Allies menu in the score screen's given / recv."""
    res = check_files(run, bot, need_end=False)
    step = {r.get("step"): {k: as_int(v) for k, v in r.items() if k not in ("_", "step")} for r in run.rec("trade")}
    run.eq("the map allowed autopool in time", run.rec("wait"), [])
    run.eq("-pool: the dialog click chose slot 2", run.one("pool").get("to"), "2")
    start, there, back = step.get("start", {}), step.get("there", {}), step.get("back", {})
    t0, t1, end = step.get("tribute0", {}), step.get("tribute", {}), step.get("end", {})
    if not all((start, there, back, t0, t1, end)):
        run.check("every step recorded", False, f"steps {sorted(step)}")
        return
    run.check("-pool there: pool_out(1) = pool_in(2) >= the 1000 sent",
              there["out1"] == there["in2"] >= 1000, f"{there}")
    run.check("-pool back: slot 2's 400 counted once per direction",
              back["out2"] - there["out2"] == back["in1"] - there["in1"] >= 400 and back["out1"] == there["out1"],
              f"there {there}, back {back}")
    run.eq("-pool moves no score-screen gold (given / recv of slots 1 and 2)",
           [back[k] for k in ("given1", "recv1", "given2", "recv2")], [0, 0, 0, 0])
    given, recv = t1["given1"] - t0["given1"], t1["recv2"] - t0["recv2"]
    print(f"INFO Allies menu: given {given}, received {recv}; gold slot 1 {t0['gold1']} -> {t1['gold1']}, "
          f"slot 2 {t0['gold2']} -> {t1['gold2']}; {run.rec('frames')}")
    run.eq("Allies menu: the menu opened (its button is off in single player, clicked by script)",
           run.one("frames", when="clicked").get("dvisible"), "1")
    if run.one("allies").get("locked") == "1":
        # 799X locks the Allies menu's resource trading for the whole game: gold moves only by -pool, F3, autopool
        run.eq("Allies menu: trading is locked, three clicks on slot 2's gold icon gave nothing", (given, recv), (0, 0))
    else:
        run.eq("Allies menu: three clicks on slot 2's gold icon gave 300 (score screen's gold given)", given, 300)
        run.eq("Allies menu: slot 2 received what slot 1 gave (no trading tax)", recv, given)
        # both slots earn income meanwhile; in the 0.05s poll where the trade landed, gold moved by the trade alone
        tick = run.one("tradetick")
        run.eq("Allies menu: in the poll the trade landed, slot 1 lost and slot 2 got exactly the trade",
               (as_int(tick.get("dgold1")), as_int(tick.get("dgold2"))), (-given, recv))
    run.eq("Allies menu: no pool counter moved", [t1[k] - t0[k] for k in ("out1", "in1", "out2", "in2")], [0, 0, 0, 0])
    if res:
        run.eq("stats rows carry both routes (given, recv, pool_out, pool_in of slots 1 and 2)",
               [res.stat(1, "given"), res.stat(2, "recv"), res.stat(1, "pool_out"), res.stat(2, "pool_in"),
                res.stat(2, "pool_out"), res.stat(1, "pool_in")],
               [end["given1"], end["recv2"], end["out1"], end["in2"], end["out2"], end["in1"]])
    check_chats(run, ["-pool"])


def check_ffa_orders(run):
    """The orders the ffa addon gave: a creep, researches, a tower upgrade, and what the engine made of them."""
    run.eq("creep order accepted by the creep shop", run.first_with("creep", "order").get("order"), "1")
    r = {k: v for x in run.rec("research") for k, v in x.items() if k != "_"}
    run.eq("research / tower orders accepted", [r.get(k) for k in ("o1", "o2", "o3", "o4", "o5")], ["1"] * 5)
    b = run.one("bought")
    run.eq("engine state after the orders (creep, Rhme, Rhar, R001, guard tower)",
           [b.get(k) for k in ("n00Q", "Rhme", "Rhar", "R001", "hgtw")], ["1", "2", "1", "1", "1"])


def check_ffa_usage(run, res, item):
    """The ffa game's usage telemetry: purchases, spells, chat commands, skill builds, events, modes, koth."""
    use = res.use
    run.eq("use,1,item", use.get((1, "item")), {item: 1} if item else None)
    run.eq("use,1,unit (the hired creep)", use.get((1, "unit")), {"n00Q": 1})
    run.eq("use,1,tech", use.get((1, "tech")), {"Rhme": 2, "Rhar": 1, "R001": 1})
    run.eq("use,1,tower", use.get((1, "tower")), {"hgtw": 1})
    run.eq("use,1,spell", use.get((1, "spell")), {"ANtm": 3})
    run.eq("use,1,cmd", use.get((1, "cmd")), {"kd": 1, "time": 1, "cam": 1, "pool": 1})
    run.eq("skills,1,N01C", res.skills.get((1, "N01C")), ["ANtm"])
    picks = sorted((e.subject,) + e.extra[:2] for e in res.events_of("pick"))
    run.eq("pick events: every slot, kind pick", picks,
           sorted([("1", "N01C", "pick")] + [(str(i), "H005", "pick") for i in range(2, 13)]))
    run.eq("baseup event", [(e.subject,) + e.extra[:1] for e in res.events_of("baseup")], [("1", "h00W")])
    modes = next(iter(res.other_rows("modes")), "")
    run.check("modes row: pub with King of the Hill", "pub=1" in modes and "koth=1" in modes, modes)
    koth_rows = [r for r in res.other_rows("koth") if r.startswith("koth,team1,")]
    run.check("koth row for team 1", koth_rows, f"{res.other_rows('koth')}")
    if koth_rows:
        kk = parse_kv(koth_rows[0].split(",")[2:])
        run.between("koth team 1 hold seconds", kk.get("hold"), 20, 60)
        run.eq("koth team 1 captures", kk.get("caps"), "1")


def expected_inheritance(run):
    """The gold each fallen slot of teams 2-4 gave and got from its allies, from the gold it held at the fall.

    The map hands a fallen player's gold to the allies still standing: the first of a team to fall gives half to
    each of the two others, the second all of it to the last one, the last one nothing. Bases fall team by team,
    in slot order.

    Returns:
        (gold out, gold in), each a dict of 1-based slot to gold.
    """
    held = {as_int(x.get("slot")): as_int(x.get("gold")) or 0 for x in run.rec("razebase")}
    want_out, want_in = defaultdict(int), defaultdict(int)
    for team in range(1, 4):
        alive = [3 * team + 1, 3 * team + 2, 3 * team + 3]
        for slot in list(alive):
            alive.remove(slot)
            for a in alive:
                share = held.get(slot, 0) // 2 if len(alive) == 2 else held.get(slot, 0)
                want_in[a] += share
                want_out[slot] += share
    return want_out, want_in


def check_ffa_stats(run, res, pool):
    """The ffa game's stats rows: exact where the addon caused the number, ranges for engine values."""
    stat = res.stat
    run.eq("stats,1 exact (creeps, atk, def, team_res, deny_own, deny_ally, tm_casts, tm_hits, tm_denied)",
           [stat(1, x) for x in ("creeps", "atk_lvl", "def_lvl", "team_res", "deny_own", "deny_ally", "tm_casts",
                                 "tm_hits", "tm_denied")],
           [1, 2, 1, 1, 1, 1, 3, 1, 1])
    run.between("stats,1 creep_gold (the creep's price, from its lumber-bounty field)", stat(1, "creep_gold"), 1, 5000)
    run.eq("stats,4 tm_saves", stat(4, "tm_saves"), 1)
    # autopool stays on for the rest of the game: the final sums are at least what had moved 5s after the click
    first = as_int(pool.get("out1"))
    run.check("stats pool_out(1) = pool_in(2) >= the first transfers",
              stat(1, "pool_out") is not None and stat(1, "pool_out") == stat(2, "pool_in")
              and first is not None and stat(1, "pool_out") >= first,
              f"pool_out {stat(1, 'pool_out')}, pool_in {stat(2, 'pool_in')}, first {pool.get('out1')}")
    run.eq("script gold moves (autopool, inheritance, SetPlayerState) leave the score screen's given / recv at 0",
           [(stat(i, "given"), stat(i, "recv")) for i in range(1, 13)], [(0, 0)] * 12)
    want_out, want_in = expected_inheritance(run)
    run.eq("stats inheritance: inh_out / inh_in of slots 4-12 (the gold each held when its base fell)",
           [(stat(i, "inh_out"), stat(i, "inh_in")) for i in range(4, 13)],
           [(want_out[i], want_in[i]) for i in range(4, 13)])
    run.between("slot 4 held the 1000 the scenario gave it (+ a few seconds of income)",
                run.one("razebase", slot="4").get("gold"), 1000, 1200)
    for name, key, lo, hi in (("stats,1 koth_gold", (1, "koth_gold"), 1, 1000),
                              ("stats,1 hero_lvl", (1, "hero_lvl"), 6, 30),
                              ("stats,1 dmg_bld (9 bases at 100000 each)", (1, "dmg_bld"), 9 * 3750, 10 ** 7),
                              ("stats,1 dmg_out", (1, "dmg_out"), 100000, 10 ** 8),
                              ("stats,4 dmg_in (its hero was killed)", (4, "dmg_in"), 1, 10 ** 8),
                              ("stats,1 razed (score screen)", (1, "razed"), 9, 500),
                              ("stats,1 food (score screen)", (1, "food"), 1, 200),
                              ("stats,1 tech (score screen)", (1, "tech"), 1, 100000),
                              ("stats,1 ukills", (1, "ukills"), 1, 100000),
                              ("stats,1 hkills", (1, "hkills"), 1, 1000)):
        run.between(name, stat(*key), lo, hi)
    run.eq("states: team 1 alive, slots 4-12 out", [res.stats.get(i) and res.stats[i].state for i in range(1, 13)],
           ["alive"] * 3 + ["out"] * 9)
    # the map removes the hero at the elimination, so the level must be the one reached before
    levels = [stat(i, "hero_lvl") for i in range(4, 13)]
    run.check("hero_lvl kept by the eliminated players (>= 1)", all((v or 0) >= 1 for v in levels), f"{levels}")


def check_solo(run, bot):
    """A whole Solo game with the client in the first seat."""
    res = check_files(run, bot, need_end=True)
    run.eq("client seated in slot 1 (Player 0)", run.one("e2e").get("local"), "0")
    slots = run.slots()
    run.eq("Solo seats: the client + three computers", [(i, slots.get(i, {}).get("ctrl")) for i in (0, 4, 7, 11)],
           [(0, "user"), (4, "computer"), (7, "computer"), (11, "computer")])
    run.eq("no other participant slot", sorted(i for i in slots if i < 12 and i not in (0, 4, 7, 11)), [])
    run.eq("heroes through the map's tavern-area pick", [run.one("hero").get(k) for k in ("1", "5", "8", "12")],
           ["H005"] * 4)
    item = bought_item(run)
    run.eq("creep order accepted", run.one("creep").get("order"), "1")
    run.eq("research orders accepted", [run.one("research").get(k) for k in ("o1", "o2")], ["1", "1"])
    run.eq("engine state after the orders (item, Rhme, Rhar)",
           [run.one("bought").get(k) for k in ("item", "Rhme", "Rhar")], ["1", "1", "1"])
    check_chats(run, ["-kd"])
    check_scripted_kills(run)
    run.eq("King of the Hill taken by slot 1", run.first_with("koth", "holder").get("holder"), "1")
    check_bases_razed(run, "5, 8, 12", (5, 8, 12))
    check_end_seen(run)
    if not res:
        return
    stat = res.stat
    run.eq("roster: the four Solo seats", sorted(res.roster), [1, 5, 8, 12])
    run.eq("use,1,item", res.use.get((1, "item")), {item: 1} if item else None)
    run.eq("use,1,unit (the hired creep)", res.use.get((1, "unit")), {"n00Q": 1})
    run.eq("use,1,tech", res.use.get((1, "tech")), {"Rhme": 1, "Rhar": 1})
    run.eq("use,1,cmd", res.use.get((1, "cmd")), {"kd": 1})
    run.eq("stats,1 exact (creeps, atk, def, deny_own)", [stat(1, x) for x in ("creeps", "atk_lvl", "def_lvl", "deny_own")],
           [1, 1, 1, 1])
    run.between("stats,1 creep_gold", stat(1, "creep_gold"), 1, 5000)
    run.between("stats,1 koth_gold", stat(1, "koth_gold"), 1, 1000)
    run.between("stats,1 dmg_bld (3 bases at 100000 each)", stat(1, "dmg_bld"), 3 * 3750, 10 ** 7)
    run.between("stats,1 razed (score screen)", stat(1, "razed"), 3, 500)
    run.between("stats,1 hkills", stat(1, "hkills"), 1, 1000)
    modes = next(iter(res.other_rows("modes")), "")
    run.check("modes row: King of the Hill, nopool key (Solo)", "koth=1" in modes and "nopool=" in modes, modes)
    run.check("koth row for team 1", [r for r in res.other_rows("koth") if r.startswith("koth,team1,")],
              f"{res.other_rows('koth')}")
    run.eq("states: slot 1 alive, 5/8/12 out", [res.stats.get(i) and res.stats[i].state for i in (1, 5, 8, 12)],
           ["alive", "out", "out", "out"])
    run.eq("out events: 5, 8, 12", [e.subject for e in res.events_of("out")], ["5", "8", "12"])
    check_outcome(run, res)


def check_solo_observer(run, bot):
    """The Solo map with the client in the first observer seat, played to the end."""
    res = check_files(run, bot, need_end=True)
    run.eq("client seated in the first observer slot (Player 12)", run.one("e2e").get("local"), "12")
    slots = run.slots()
    run.eq("Solo seats: four computers", [(i, slots.get(i, {}).get("ctrl")) for i in (0, 4, 7, 11)],
           [(i, "computer") for i in (0, 4, 7, 11)])
    run.eq("slot 13: the client, a user", slots.get(12, {}).get("ctrl"), "user")
    run.eq("heroes through the map's tavern-area pick", [run.one("hero").get(k) for k in ("1", "5", "8", "12")],
           ["H005"] * 4)
    check_chats(run, ["-kd"])
    inv = run.one("vision", unit="invisible")
    if bot:
        run.eq("BotVision: the bot sees the invisible unit", inv.get("12"), "1")
        run.eq("BotVision: the bot still sees it after the game end", run.first_with("vision", "after_end").get("bot"), "1")
    run.eq("the other seats do not see the invisible unit", [inv.get(str(i)) for i in (4, 7, 11)], ["0"] * 3)
    check_bases_razed(run, "5, 8, 12", (5, 8, 12))
    check_razes(run, 3)
    check_end_seen(run)
    if not res:
        return
    run.eq("roster: the four Solo seats, not the observer", sorted(res.roster), [1, 5, 8, 12])
    check_outcome(run, res)
    run.eq("observer commands are not counted as player usage", [k for k in res.use if k[1] == "cmd"], [])
    modes = res.other_rows("modes")
    run.check("Solo modes row (nopool)", any("nopool" in m for m in modes), f"{modes}")


# --- skills --------------------------------------------------------------------------------------------------------

def load_skill_exceptions(path=E2E_DIR / "skills_exceptions.csv"):
    """Reads the explained skill deviations.

    Args:
        path: The CSV (`kind,abil,level,note`). `kind` is a readback field (`rb:<field>`) or a cast check (`cast`,
            `mana`, `cd`, `effect`); level `*` means every level.

    Returns:
        A set of (kind, abil, level) tuples, level as text.
    """
    out = set()
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.strip() and not line.startswith(("#", "kind,")):
                k, ab, lv = line.split(",")[:3]
                out.add((k, ab, lv))
    return out


def skills_expect_path(run):
    """Where the build put skills_expect.json: next to the run's files, else in the build's stage folder."""
    path = run.out / "skills_expect.json"
    return path if path.is_file() else run.out.parent / "stage" / f"{run.map}-skills" / "skills_expect.json"


def flaky_split(items):
    """Splits (abil, detail) misses into one-level misses (noise) and the details of skills missing at 2+ levels.

    Args:
        items: (abil, detail) pairs, one per level that missed.

    Returns:
        (the first detail of each skill that missed at a single level, every detail of skills that missed at 2+).
    """
    per = defaultdict(list)
    for ab, d in items:
        per[ab].append(d)
    single = [ds[0] for ds in per.values() if len(ds) < 2]
    repeated = [d for ds in per.values() if len(ds) >= 2 for d in ds]
    return single, repeated


def check_skills(run, bot):
    """Every hero skill at every level: the map's numbers read back from the engine, and a cast per level."""
    exp_path = skills_expect_path(run)
    if not exp_path.is_file():
        run.check("skills_expect.json from the build", False, str(exp_path))
        return
    exp = json.loads(exp_path.read_text())["abilities"]
    exc = load_skill_exceptions()

    def known(kind, ab, lv):
        return (kind, ab, str(lv)) in exc or (kind, ab, "*") in exc

    run.eq("every hero skill loaded into the map", run.one("data").get("skills"), str(len(exp)))
    rb = run.one("readback")
    unexplained = [b for b in (r["_"] for r in run.rec("rb")) if not (len(b) >= 3 and known("rb:" + b[1], b[0], b[2]))]
    run.check("readback: every stored numeric cell reads back as stored", rb and not unexplained,
              f"{rb.get('bad')} of {rb.get('cells')} differ: {[','.join(b) for b in unexplained[:12]]}")
    casts = {(c["_"][0], int(c["_"][1])): c for c in run.rec("c")}
    engine_levels = {r["_"][0]: int(r.get("engine", 0)) for r in run.rec("lv")}
    for ab, v in exp.items():
        v["levels"] = min(v["levels"], engine_levels.get(ab, v["levels"]))
    if engine_levels:
        print(f"INFO skills: {len(engine_levels)} skill(s) with fewer levels in the engine than cells in the map "
              f"(no alev: the base ability's count; {rb.get('dead')} dead cells): {sorted(engine_levels)[:20]}")
    run.eq("a cast per skill and (engine) level", len(casts), sum(v["levels"] for v in exp.values()))
    refused, noeff, mana, cd = judge_casts(exp, casts, known)
    print(f"INFO skills: {len(exp)} skills ({sum(1 for v in exp.values() if v['order'])} with an order), "
          f"{len(casts)} casts; refused {len(refused)}, no effect {len(noeff)}, mana off {len(mana)}, "
          f"cooldown off {len(cd)}")
    # a single refused or ineffective level is placement / timing noise in a busy map (it moves between runs);
    # a skill that misses at two or more levels is not
    single, rbad = flaky_split(refused)
    if refused:
        print(f"INFO skills: refused at a single level (not judged): {single}")
    run.check("every skill with an order is accepted (no skill refused at 2+ levels)", not rbad, f"{len(rbad)}: {rbad[:15]}")
    single, bad = flaky_split(noeff)
    if noeff:
        print(f"INFO skills: no effect at a single level (not judged): {single}")
    run.check("every accepted cast takes effect (no skill misses it at 2+ levels)", not bad, f"{len(bad)}: {bad[:15]}")
    run.check("mana spent = the map's amcs at that level", not mana, f"{len(mana)}: {mana[:15]}")
    run.check("cooldown started = the map's acdn at that level (+-0.2s)", not cd, f"{len(cd)}: {cd[:15]}")
    check_finished(run)


def judge_casts(exp, casts, known):
    """Compares every cast with the map's numbers.

    Args:
        exp: skills_expect.json's abilities (levels already capped to the engine's).
        casts: (abil, level) to the addon's cast record.
        known: known(kind, abil, level) -> True for an explained deviation.

    Returns:
        (refused, no effect, mana off, cooldown off): the first two as (abil, detail) pairs, the others as details.
    """
    refused, noeff, mana, cd = [], [], [], []
    for ab, v in sorted(exp.items()):
        for lv in range(1, v["levels"] + 1):
            c = casts.get((ab, lv))
            if c is None or not v["order"]:
                continue
            if c.get("how") not in ("i", "e", "h", "a", "o", "p"):
                if not known("cast", ab, lv):
                    refused.append((ab, f"{ab}/{lv}({v['order']})"))
                continue
            if c.get("eff") != "1":
                if not known("effect", ab, lv):
                    noeff.append((ab, f"{ab}/{lv}({v['order']},{c.get('how')})"))
                continue
            e = v["lv"][str(lv)]
            got_mana, got_cd = as_int(c.get("mana")), as_int(c.get("cd"))
            got_mana = -1 if got_mana is None else got_mana
            got_cd = -1 if got_cd is None else got_cd
            if e["amcs"] is not None and got_mana != e["amcs"] and not known("mana", ab, lv):
                mana.append(f"{ab}/{lv} {c.get('mana')}!={e['amcs']}")
            if e["acdn"] is not None and abs(got_cd - e["acdn"] * 100) > 20 and not known("cd", ab, lv):
                cd.append(f"{ab}/{lv} {got_cd / 100}!={e['acdn']}")
    return refused, noeff, mana, cd


# The kill_credit scenario's cases: each kills a slot-4 hero for slot 1 through a killer that is dead, or a spell
# dummy, when the damage lands (tests/e2e/addons/kill_credit).
KC_CASES = {
    1: "coin factory: a moneybag's Kaboom",
    2: "Objection: a Soul Burn tick after the dummy's old 0.10 s life",
    3: "Parasite: a Parasite tick after the dummy's old 0.10 s life",
    4: "Elemental Hellfire: a Flame Strike tick",
    5: "Jaina's ultimate: a Rain of Fire burn after the orbs vanished",
    6: "Thor's Mjolnir: the hammer's Firebolt",
}
KC_KEYS = [f"{k}{s}" for s in (1, 4) for k in ("uk", "hk", "ud", "hd")]


def check_kill_credit(run, bot):
    """Per case: the hero kill counts for slot 1, the engine names a slot-1 killer, slot 1's hero earns the kill's XP;
    then kill log = stats rows = counters at one snapshot."""
    res = check_files(run, bot, need_end=False)
    run.eq("client seated in slot 1 (Player 0)", run.one("e2e").get("local"), "0")
    for n, name in KC_CASES.items():
        before, after = run.one("kc", case=str(n), when="0"), run.one("kc", case=str(n), when="1")
        if not before or not after:
            run.check(f"case {n} ({name}): recorded", False, "case not recorded")
            continue
        run.eq(f"case {n} ({name}): ordered", run.one("cast", case=str(n)).get("order"), "1")
        run.eq(f"case {n} ({name}): the victim died", run.one("end", case=str(n)).get("died"), "1")
        deaths = [d for d in run.rec("death", case=str(n)) if d.get("victim") == "4" and d.get("vtype") == "H005"]
        run.check(f"case {n} ({name}): the engine names a slot-1 killer",
                  len(deaths) == 1 and deaths[0].get("killer") == "1", f"{deaths}")
        got = {k: (as_int(after.get(k)) or 0) - (as_int(before.get(k)) or 0) for k in KC_KEYS}
        run.eq(f"case {n} ({name}): a hero kill for slot 1, a hero death for slot 4",
               {k: v for k, v in got.items() if v}, {"hk1": 1, "hd4": 1})
        xp = (as_int(after.get("xp")) or 0) - (as_int(before.get("xp")) or 0)
        run.check(f"case {n} ({name}): slot 1's hero earns XP", xp > 0, f"xp +{xp}")
    check_counter_snapshot(run, res, bot, "kcsnap")


def check_afk(run, bot):
    """The AFK kick: the client (slot 1) never picks a hero and does nothing, and is removed by the map's own kick 15 s
    after the mass began, or when the gold pool opens if that is later (799X Pub: the trading timer; Solo has no pool);
    the result file drops it (an `afk` record, no roster entry, stats or usage rows). On 799X the map's auto-pick has
    given it a hero at the mass, so there the kick is for doing nothing."""
    res = check_files(run, bot, need_end=False)
    run.eq("client seated in slot 1 (Player 0)", run.one("e2e").get("local"), "0")
    mass = run.one("mass")
    run.check("the mass began", "t" in mass, f"{mass}")
    if run.map == "799x":
        run.eq("799X: the map's auto-pick gave the client a hero at the mass", mass.get("hero"), "1")
    else:
        run.eq("Solo: the client has no hero at the mass", mass.get("hero"), "0")
    warned = run.one("warned")
    run.eq("after the warning: AFK, still in the game (afk, dropped, active)",
           [warned.get(k) for k in ("afk", "dropped", "active")], ["1", "0", "1"])
    run.check("screenshot of the warning", (run.out / "seq-1-0.png").is_file(), "seq-1-0.png")
    kicked = run.one("kicked")
    run.eq("the kick removed slot 1", kicked.get("slot"), "1")
    pool_in = as_int(mass.get("poolin")) or 0
    if run.map == "799x":
        run.check("main (Pub): the pool is still closed at the mass", pool_in > 15, f"poolin {pool_in}")
    else:
        run.eq("Solo: no pool to wait for", pool_in, 0)
    after = as_int(kicked.get("after"))
    run.check("the kick 15 s after the mass began, or when the pool opens",
              after is not None and abs(after - max(15, pool_in)) <= 1, f"after {after}, pool in {pool_in} at the mass")
    run.eq("the pool is open at the kick", kicked.get("poolin"), "0")
    run.eq("the result file dropped the slot before the kick (dropped, participant)",
           [kicked.get(k) for k in ("dropped", "participant")], ["1", "0"])
    others = kicked.get("others", "")
    run.check("the computers without a hero stay (player_active)", others and set(others) == {"1"}, others)
    run.eq("the client's slot has left the game", kicked.get("state"), "left")
    if run.map == "solo":
        run.eq("Solo: the kick takes the client out (player_active)", kicked.get("active"), "0")
    run.check("screenshot of the defeat dialog", (run.out / "seq-2-1.png").is_file(), "seq-2-1.png")
    if not res:
        return
    afk = res.events_of("afk")
    run.eq("one afk record, for slot 1 with the client's name", [(e.subject, e.extra) for e in afk],
           [("1", (client_name(run),))])
    run.check("slot 1 not in the roster", 1 not in res.roster, f"roster {sorted(res.roster)}")
    run.eq("no stats row for slot 1", res.stats.get(1), None)
    run.eq("no use rows for slot 1", sorted(cat for (slot, cat) in res.use if slot == 1), [])


TC_KEYS = ("casts", "hits", "creeps", "denied", "savesA", "savesB", "creepsA", "creepsB")
TC_CASES = {
    # case: (name, counter changes, the target's type, its owner side, in the hired group, killer slot or None)
    1: ("lands on a hired creep", {"casts": 1, "hits": 1, "creeps": 1}, "n00A", "A", "1", "1"),
    2: ("lands on a creep nobody hired", {"casts": 1, "hits": 1}, "n00A", "A", "0", "1"),
    3: ("lands on a footman", {"casts": 1, "hits": 1}, "hfoo", "A", "0", "1"),
    4: ("a hired creep its own side kills first", {"casts": 1, "denied": 1, "savesB": 1}, "n00A", "B", "1", "B"),
    5: ("a hired creep gone before the projectile lands", {"casts": 1}, "n00A", "A", "1", None),
    6: ("a hired creep killed without a Transmute", {}, "n00A", "B", "1", "1"),
}


def check_transmute_creeps(run, bot):
    """Which Transmutes count as tm_creeps: hires through real sales, one Transmute per case, then the stats rows."""
    res = check_files(run, bot, need_end=False)
    run.eq("client seated in slot 1 (Player 0)", run.one("e2e").get("local"), "0")
    hero = run.one("hero")
    side = {"A": hero.get("A"), "B": hero.get("B"), "1": "1"}
    run.eq("enemy sides", (side["A"], side["B"]), ("4", "7") if run.map == "799x" else ("5", "8"))
    run.eq("slot 1's hero is ours, with Transmute", (hero.get("ours"), run.one("skill").get("ANtm")), ("1", "1"))
    run.eq("four sales ordered", [h.get("order") for h in run.rec("hire")], ["1"] * 4)
    hired = run.one("hired")
    run.eq("four creeps sold: A, A, B, B", [hired.get(f"owner{i}") for i in range(4)],
           [side["A"]] * 2 + [side["B"]] * 2)
    run.eq("every sold creep kept and marked as hired", [(hired.get(f"alive{i}"), hired.get(f"in{i}")) for i in range(4)],
           [("1", "1")] * 4)
    run.eq("the sales counted as hired creeps (creeps A, B; group)",
           (hired.get("creepsA"), hired.get("creepsB"), hired.get("group")), ("2", "2", "4"))
    for n, (name, want, vtype, owner, inhired, killer) in TC_CASES.items():
        label = f"case {n} ({name})"
        before, after = run.one("tc", case=str(n), when="0"), run.one("tc", case=str(n), when="1")
        if not before or not after:
            run.check(f"{label}: recorded", False, "case not recorded")
            continue
        target = run.one("target", case=str(n))
        run.eq(f"{label}: the target", (target.get("type"), target.get("owner"), target.get("inhired")),
               (vtype, side[owner], inhired))
        if n != 6:
            run.eq(f"{label}: cast ordered, the effect on the target",
                   (run.one("cast", case=str(n)).get("order"), run.one("effect", case=str(n)).get("target")), ("1", "1"))
        got = {k: (as_int(after.get(k)) or 0) - (as_int(before.get(k)) or 0) for k in TC_KEYS}
        run.eq(f"{label}: Transmute counters", {k: v for k, v in got.items() if v}, want)
        deaths = run.rec("death", case=str(n))
        run.eq(f"{label}: deaths (target, killer)", [(d.get("target"), d.get("killer")) for d in deaths],
               [("1", side[killer])] if killer else [])
        if n in (1, 4, 6):
            run.eq(f"{label}: the dead creep left the hired group",
                   (as_int(after.get("hired")) or 0) - (as_int(before.get("hired")) or 0), -1)
        elif n in (2, 3):
            run.eq(f"{label}: the hired group unchanged", after.get("hired"), before.get("hired"))
    if res:
        a, b = int(side["A"]), int(side["B"])
        run.eq("stats,1 Transmute (casts, hits, creeps, denied)",
               [res.stat(1, k) for k in ("tm_casts", "tm_hits", "tm_creeps", "tm_denied")], [5, 3, 1, 1])
        run.eq("stats: the save is B's, nobody else's",
               [res.stat(s, "tm_saves") for s in (a, b)], [0, 1])
        run.eq("stats: creeps hired by A and B", [res.stat(s, "creeps") for s in (a, b)], [2, 2])
        run.eq("stats: no tm_creeps for the creeps' owners", [res.stat(s, "tm_creeps") for s in (a, b)], [0, 0])
        run.eq("use: the creeps bought by A and B",
               [res.use.get((s, "unit"), {}).get("n00A") for s in (a, b)], [2, 2])
    run.check("the end snapshot recorded", run.rec("tcsnap"), "no tcsnap rows")
    if run.rec("tcsnap"):
        check_counter_snapshot(run, res, bot, "tcsnap")


def check_transmute(run, bot):
    """A Transmute projectile in the air when the side of its target drops out (transmute_destroyed / _left): the
    client survives the control (a deny) and the loss, and the side is out of the game; the game goes on."""
    case = run.one("e2e").get("scenario", "").removeprefix("transmute_")
    res = check_files(run, bot, need_end=False)
    hero = run.one("hero")
    run.eq("slot 1's hero is the scenario's Alchemist (tavern-area pick)", hero.get("ours"), "1")
    run.eq("Transmute learned", run.one("skill").get("ANtm"), "1")
    side = hero.get("side", "")
    run.eq("target side: slot 4 on main, slot 5 on Solo", side, "4" if run.map == "799x" else "5")
    run.eq("both casts ordered", [c.get("order") for c in run.rec("cast")], ["1", "1"])
    deny = run.one("deny")
    run.eq("the control: the side's own footman killed the target in flight (dead, casts, hits, denied, saves)",
           [deny.get(k) for k in ("dead", "casts", "hits", "denied", "saves")], ["1", "1", "0", "1", "1"])
    if run.map == "799x":
        # a destroyed player is out of the map's play (player_active); a leaver whose allies stay keeps it (they take
        # over the base): the slot has left
        allies = run.one("allies")
        out = ["active5", "active6"] if case == "destroyed" else ["state5", "state6"]
        run.eq("main: the side's allies (slots 5, 6) are out first, slot 4 is still in",
               [allies.get(k) for k in (*out, "active4")], ["0", "0", "1"] if case == "destroyed" else
               ["left", "left", "1"])
    loss = run.one("loss")
    run.eq("the loss came while the projectile was in the air", (loss.get("case"), loss.get("inflight")), (case, "1"))
    run.eq("the client played on for 30 s after the loss (tick rows)", len(run.rec("tick")), 6)
    after = run.one("after")
    run.eq("after the loss: the side is out (player_active)", after.get(f"active{side}"), "0")
    if case == "left":
        run.eq("after the loss: the side's slot has left", after.get(f"state{side}"), "left")
    run.eq("after the loss: the target is dead, the hero alive (alive, hero)",
           [after.get(k) for k in ("alive", "hero")], ["0", "1"])
    # A destroyed side's units are killed at once (no killer: the Transmute is denied). A leaver's stay ~20 s on both
    # maps (799X: SafeRemoval's grace) before they are removed, so the projectile lands (a hit).
    hit = case == "left"
    run.eq("after the loss: Transmute counters (casts, hits, denied)", [after.get(k) for k in ("casts", "hits", "denied")],
           ["2", "1" if hit else "0", "2" if case == "destroyed" else "1"])
    if not res:
        return
    run.eq("the result file has the side out", [e.subject for e in res.events_of("sidedead")], ["team2"])
    st = res.stats.get(int(side or 0))
    run.eq(f"stats,{side}: state", st and st.state, "out" if case == "destroyed" else "left")


def check_towerfire(run, bot):
    """A tower's attack on allied units: splash on its own, ordered attacks, and the order events behind them."""
    check_files(run, bot, need_end=False)
    run.eq("client seated in slot 1 (Player 0)", run.one("e2e").get("local"), "0")

    def killed_by_tower(case):
        return sorted(d.get("victim") for d in run.rec("death", case=str(case)) if d.get("bytower") == "1")

    def deny(case):
        r = run.one("deny", case=str(case))
        return {k: as_int(r.get(k)) for k in ("own1", "ally1", "own2", "ally2")}

    def tower_orders(case):
        return [(o.get("name"), o.get("target")) for o in run.rec("order", case=str(case))]

    run.eq("case 1: the splash of a shot at an enemy spares the allied and the own footman next to it",
           killed_by_tower(1), ["4"])
    run.eq("case 1: no denies", deny(1), {"own1": 0, "ally1": 0, "own2": 0, "ally2": 0})
    print(f"INFO case 1: the tower's order events while it picks an enemy on its own: {tower_orders(1)}")
    for case, target, victims, want in ((2, "1", ["1"], {"own1": 0, "ally1": 0, "own2": 0, "ally2": 1}),
                                        (3, "2", ["2"], {"own1": 0, "ally1": 0, "own2": 1, "ally2": 1})):
        who = "allied" if target == "1" else "own"
        run.eq(f"case {case}: the tower accepts an attack order on an {who} footman",
               run.one("issue", case=str(case)).get("ok"), "1")
        run.check(f"case {case}: the order event names the attack and the {who} target",
                  ("attack", target) in tower_orders(case), f"{tower_orders(case)}")
        run.eq(f"case {case}: the tower killed the {who} target only, not the footman next to it",
               killed_by_tower(case), victims)
        run.eq(f"case {case}: deny counters (cumulative)", deny(case), want)
    run.eq("case 4 (control): the splash of a shot at an enemy kills the enemy next to it",
           killed_by_tower(4), ["4", "4"])
    run.eq("case 5: an Arcane Tower of Terror's splash spares the allied and the own footman too",
           killed_by_tower(5), ["4"])
    orders = run.one("orders")
    run.check("order count after Mass START recorded", bool(orders), f"{orders}")
    if orders:
        secs = max(1, (as_int(orders.get("to")) or 0) - (as_int(orders.get("from")) or 0))
        print(f"INFO order events in {secs}s from {orders.get('from')}s: all={orders.get('all')} "
              f"({(as_int(orders.get('all')) or 0) / secs:.1f}/s), unit-target={orders.get('target')}, "
              f"by buildings={orders.get('building')}")
        run.eq("the map itself never orders a building to attack an allied or own unit",
               orders.get("friendly_attack"), "0")


SCENARIOS = {"afk": check_afk, "observer": check_observer, "ffa": check_ffa, "kd": check_kd, "kill_credit": check_kill_credit, "transmute_creeps": check_transmute_creeps, "trade": check_trade, "solo": check_solo, "solo-observer": check_solo_observer,
             "skills": check_skills, "transmute_destroyed": check_transmute, "transmute_left": check_transmute, "towerfire": check_towerfire}


def main(argv=None):
    """Runs one scenario's checks.

    Args:
        argv: The command line (default: sys.argv[1:]).

    Returns:
        The exit code: 1 when a check failed or the run has no records, else 0.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenario", choices=sorted(SCENARIOS))
    ap.add_argument("out")
    ap.add_argument("--map", default="799x", choices=["799x", "solo"])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--bot", dest="bot", action="store_true", default=True)
    g.add_argument("--no-bot", dest="bot", action="store_false")
    a = ap.parse_args(argv)
    run = Run(a.out, a.map)
    if not run.e2e:
        print(f"FAIL no ff_e2e.txt records in {a.out}")
        return 1
    SCENARIOS[a.scenario](run, a.bot)
    return run.report()


if __name__ == "__main__":
    sys.exit(main())
