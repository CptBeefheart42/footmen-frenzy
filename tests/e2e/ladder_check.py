#!/usr/bin/env python3
"""The ladder check: the games an e2e or simulation run wrote, scored by the efl-bot code the fleet runs.

    <bot python> tests/e2e/ladder_check.py <efl-bot checkout> [--unscored] <out dir> [[--unscored] <out dir> ...]

Run it with the bot's own Python (its dependencies: SQLModel, FastAPI, httpx), against a checkout of the pinned
commit (tests/e2e/efl-bot.ref; `make test-e2e-ladder` makes the worktree). For each out dir of a finished game (an
ff_result*.txt with gameend) it does what the bot's host does after a game, without the network:

  1. parse the result file (efl_league.ff_result): finished and complete enough to score;
  2. read the kill log: kills and deaths per player (efl_league.killlog, as the host's kd_for does);
  3. post the report to the league API's /report_match (FastAPI's TestClient, a throwaway sqlite DB);
  4. check the stored match: the map's placements, every roster player on it, Elo moved (winners up, last place
     down), and the per-player stats / telemetry where this bot version stores them.

An out dir after `--unscored` holds a game nobody won (everybody left: no gameend). The bot must parse it and refuse
to score it, never rank it some other way.

Records this bot version does not know are listed, never an error (an older bot ignores newer rows): what must hold
is that the bot scores the game. Prints PASS/FAIL lines and exits 1 if any failed.
"""
import argparse
import importlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.common.checks import Checks  # noqa: E402
from tests.common.preload import parse_rows  # noqa: E402


class Bot:
    """The league code of an efl-bot checkout, imported from that checkout.

    Attributes:
        root: The checkout.
        api: efl_league.api (the FastAPI app and its database engine).
        parse: efl_league.ff_result.parse.
        killlog: efl_league.killlog.
        models: efl_league.models (Match, MatchPlayerLink).
    """

    def __init__(self, root):
        self.root = Path(root).resolve()
        sys.path.insert(0, str(self.root / "libs" / "efl-league"))
        import efl_league
        if not str(Path(efl_league.__file__).resolve()).startswith(str(self.root)):
            sys.exit(f"ladder: efl_league comes from {efl_league.__file__}, not from {self.root} "
                     "(a site-packages copy wins)")
        self.api = importlib.import_module("efl_league.api")
        self.parse = importlib.import_module("efl_league.ff_result").parse
        self.killlog = importlib.import_module("efl_league.killlog")
        self.models = importlib.import_module("efl_league.models")

    def kills(self, out, players):
        """Kills and deaths per battletag from the run's kill log (empty without one)."""
        logs = sorted(Path(out).glob("ff_killlog*.txt"))
        if not logs:
            return {}
        slots = [{"team": p.get("team"), "name": p.get("battletag"), "color": None, "is_observer": False}
                 for p in players]
        board = self.killlog.attribute(self.killlog.parse_killlog(logs[0].read_text(errors="replace")), slots)
        return {p["name"]: {"kills": p.get("unit", 0) + p.get("hero", 0),
                            "deaths": p.get("unit_died", 0) + p.get("hero_died", 0)}
                for p in board["players"] if p.get("team") is not None}

    def fresh_db(self, path):
        """Points the league API at an empty sqlite database at `path`.

        The API module keeps its engine in module globals, so they are replaced for the check.

        Returns:
            The database engine.
        """
        from sqlmodel import SQLModel, create_engine
        engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        self.api.engine = engine
        self.api.sqlite_file_name = str(path)
        SQLModel.metadata.create_all(engine)
        return engine


def roster_entries(text):
    """How many roster entries the map wrote (the `roster` and `roster_more` rows)."""
    rows = [r for r in parse_rows(text) if r.startswith(("roster,", "roster_more,"))]
    return sum(len([e for e in r.split(",", 1)[1].split(";") if e]) for r in rows)


def run_tag(out):
    """A run's name in the report: `<map>/<scenario>` for simulation runs, the folder name otherwise."""
    return f"{out.parent.name}/{out.name}" if out.parent.name in ("main", "solo") else out.name


def check_stored_match(checks, tag, bot, engine, result, kills):
    """Checks the match the league stored: placements, players, Elo, kills.

    Returns:
        The stored match's id.
    """
    from sqlmodel import Session, select
    Match, Link = bot.models.Match, bot.models.MatchPlayerLink
    with Session(engine) as s:
        match = s.exec(select(Match)).one()
        links = s.exec(select(Link)).all()
        checks.check(f"{tag}: stored placements = the map's", json.loads(match.placements) == result.ranked_teams,
                     f"{match.placements} vs {result.ranked_teams}")
        checks.check(f"{tag}: every roster player is on the match", len(links) == len(result.roster),
                     f"{len(links)} links, {len(result.roster)} roster")
        first = [x.elo_change for x in links if x.placement == 1]
        last = [x.elo_change for x in links if x.placement == max(y.placement for y in links)]
        checks.check(f"{tag}: Elo: the winners gain, the last place loses",
                     first and all(c > 0 for c in first) and last and all(c < 0 for c in last),
                     f"first {first}, last {last}")
        if kills:
            checks.check(f"{tag}: kills stored on the match", [x for x in links if getattr(x, "kills", None)],
                         "no link has kills")
        return match.id


def check_report(checks, tag, bot, result, kills):
    """Posts the game to /report_match on a throwaway database and checks what the league stored."""
    from fastapi.testclient import TestClient
    league = "deathmatch" if len(result.roster) <= 4 else "pub"
    payload = result.to_report_payload(league=league, game_name=f"e2e {tag}")
    if hasattr(result, "events_json"):
        payload["events"] = result.events_json()
    for p in payload.get("players") or []:
        p.update(kills.get(p.get("battletag"), {}))
    with tempfile.TemporaryDirectory() as tmp:
        engine = bot.fresh_db(Path(tmp) / "league.db")
        with TestClient(bot.api.app) as client:
            resp = client.post("/report_match", json=payload)
            checks.check(f"{tag}: /report_match accepts it ({league})",
                         resp.status_code == 200 and resp.json().get("status") == "success",
                         f"{resp.status_code} {resp.text[:300]}")
            if resp.status_code != 200:
                return
            mid = check_stored_match(checks, tag, bot, engine, result, kills)
            if "/matches/{match_id}/telemetry" in {getattr(r, "path", "") for r in bot.api.app.routes}:
                t = client.get(f"/matches/{mid}/telemetry")
                body = t.json() if t.status_code == 200 else {}
                checks.check(f"{tag}: telemetry stored (GET /matches/{{id}}/telemetry)", t.status_code == 200 and body,
                             f"{t.status_code} {t.text[:200]}")
                print(f"INFO {tag}: telemetry keys "
                      f"{sorted(body)[:12] if isinstance(body, dict) else type(body).__name__}")
            else:
                print(f"INFO {tag}: this bot version has no telemetry endpoint (stats/usage rows are ignored)")
    if getattr(result, "stats", None):
        with_stats = [p for p in result.players() if "stats" in p]
        checks.check(f"{tag}: per-player stats reach the report", len(with_stats) == len(result.roster),
                     f"{len(with_stats)} of {len(result.roster)}")


def check_run(checks, bot, out, unscored):
    """Scores one run's game (or checks that a game nobody won is not scored)."""
    tag = run_tag(out)
    files = sorted(out.glob("ff_result*.txt"))
    if len(files) != 1:
        checks.check(f"{tag}: one result file", False, f"{[f.name for f in files]}")
        return
    text = files[0].read_text(errors="replace")
    try:
        result = bot.parse(text)
    except Exception as e:
        checks.check(f"{tag}: the bot parses the result file", False, f"{type(e).__name__}: {e}")
        return
    checks.check(f"{tag}: the bot parses the result file", True)
    if unscored:
        checks.check(f"{tag}: nobody won -> the bot does not score it", not result.finished and not result.is_complete,
                     f"finished={result.finished} ranked_teams={result.ranked_teams}")
        checks.check(f"{tag}: ... but it knows who played", len(result.roster) > 0, "empty roster")
        return
    unknown = sorted({r.split(",")[0] for r in result.unknown_records})
    print(f"INFO {tag}: records this bot version ignores: {unknown or 'none'}")
    checks.check(f"{tag}: finished and complete enough to score", result.finished and result.is_complete,
                 f"finished={result.finished} ranked_teams={result.ranked_teams}")
    entries = roster_entries(text)
    checks.check(f"{tag}: every roster entry the map wrote reaches the bot", len(result.roster) == entries,
                 f"map wrote {entries}, bot sees {len(result.roster)} (roster_more rows unknown to this bot version?)")
    if not result.is_complete:
        return
    kills = bot.kills(out, result.players())
    if sorted(out.glob("ff_killlog*.txt")):
        checks.check(f"{tag}: kill log attributed to roster players", kills and any(v["kills"] for v in kills.values()),
                     f"{kills}")
    check_report(checks, tag, bot, result, kills)


def parse_args(argv):
    """Reads the command line.

    Returns:
        (bot checkout, [(out dir, unscored)]).
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bot", type=Path)
    ap.add_argument("runs", nargs=argparse.REMAINDER, help="out dirs, each optionally preceded by --unscored")
    a = ap.parse_args(argv)
    runs, unscored = [], False
    for arg in a.runs:
        if arg == "--unscored":
            unscored = True
            continue
        runs.append((Path(arg), unscored))
        unscored = False
    if not runs:
        ap.error("no out dir given")
    return a.bot, runs


def main(argv=None):
    """Scores every run given on the command line.

    Args:
        argv: The command line (default: sys.argv[1:]).

    Returns:
        The exit code: 1 when a check failed or nothing was checked, else 0.
    """
    bot_dir, runs = parse_args(argv)
    bot = Bot(bot_dir)
    checks = Checks(f"ladder (bot {bot.root})")
    for out, unscored in runs:
        check_run(checks, bot, out, unscored)
    return checks.report() or (0 if checks.results else 1)


if __name__ == "__main__":
    sys.exit(main())
