#!/usr/bin/env python3
"""The map <-> bot contract: every ff_result.txt the simulation scenarios wrote must be documented and must reach
the league's own parser (efl_league.ff_result from efl-bot-2.0) without losing anything.

    tests/simulation/contract.py <out dir> [--bot <efl-bot-2.0 checkout>]

Two groups of checks, each file on its own line:

  * contract-doc: every stats / modes key a file holds is documented in docs/result-contract.md, and every
    documented stats key is written. Needs nothing else, so it runs in CI too.
  * contract: the bot's parser reads the file and keeps every stats, usage, skills, event and modes value. The
    checkout defaults to $FF_EFL_BOT or ../efl-bot-2.0 next to this repo; without one this group is skipped (said
    so, not a failure): the map repo's CI has no bot checkout.

Exits 1 if any check failed.
"""
import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.common.checks import Checks  # noqa: E402
from tests.common.ffresult import MAP_EVENTS, FFResultFile, FormatError  # noqa: E402
from tests.common.kv import as_int, parse_kv  # noqa: E402
from tests.common.paths import DOCS_DIR, REPO  # noqa: E402
from tests.common.preload import parse_rows  # noqa: E402

CONTRACT_DOC = DOCS_DIR / "result-contract.md"
OPTIONAL_STATS = {"left_t", "dmg_out", "dmg_bld", "dmg_in"}
TEXT_STATS = {"t", "state", "left_t"}
PARSER_FIELDS = ("stats", "usage", "skills", "map_events", "modes", "koth")


def doc_keys(doc=CONTRACT_DOC):
    """The stats and modes keys the contract documents.

    Args:
        doc: The contract (its `## stats keys` table and the `modes,` line below it).

    Returns:
        (stats keys, modes keys), two sets.
    """
    text = Path(doc).read_text()
    sec = text.split("## stats keys", 1)[1].split("\n## ", 1)[0]
    stats = set()
    for line in sec.splitlines():
        if line.startswith("| `"):
            stats.update(re.findall(r"`([a-z_0-9]+)`", line.split("|")[1]))
    modes_line = sec.split("`modes,", 1)[1].split("All are", 1)[0]
    return stats, set(re.findall(r"`([a-z_0-9]+)`", modes_line))


def result_files(out):
    """The result files under an out dir: `<map>/<scenario>/ff_result[_<token>].txt` (token: a bot client), sorted."""
    return sorted(p for p in Path(out).glob("*/*/ff_result*.txt") if re.fullmatch(r"ff_result(_\d+)?\.txt", p.name))


def file_tag(path):
    """A result file's name in the report: `<map>/<scenario>`."""
    return f"{path.parent.parent.name}/{path.parent.name}"


def doc_problems(res, stats_doc, modes_doc):
    """What a parsed file holds that the contract does not document, or lacks that it does.

    Args:
        res: The parsed result file.
        stats_doc: The documented stats keys.
        modes_doc: The documented modes keys.

    Returns:
        The problems, in words (empty when the file matches the contract).
    """
    problems = []
    for row in res.other_rows("modes"):
        undocumented = set(parse_kv(row.split(",")[1:])) - modes_doc
        if undocumented:
            problems.append(f"modes keys not in docs/result-contract.md: {sorted(undocumented)}")
    for slot, st in sorted(res.stats.items()):
        keys = set(st.values) - {"t"}
        if keys - stats_doc:
            problems.append(f"stats,{slot} keys not in docs/result-contract.md: {sorted(keys - stats_doc)}")
        absent = stats_doc - keys - OPTIONAL_STATS
        if absent:
            problems.append(f"stats,{slot} lacks documented keys: {sorted(absent)}")
    return problems


def check_doc_keys(out, doc=CONTRACT_DOC):
    """Checks every result file under `out` against the documented keys.

    Args:
        out: The simulation's out dir.
        doc: The contract document.

    Returns:
        The checks, one per file (`contract-doc <map>/<scenario>`).
    """
    stats_doc, modes_doc = doc_keys(doc)
    checks = Checks("contract-doc")
    for path in result_files(out):
        try:
            problems = doc_problems(FFResultFile.parse(parse_rows(path.read_text())), stats_doc, modes_doc)
        except FormatError as e:
            problems = [f"malformed row {e}"]
        checks.check(f"contract-doc {file_tag(path)}", not problems, "; ".join(problems[:6]))
    return checks


def load_parser(bot):
    """Loads the bot's result parser module on its own (the package's __init__ needs the database layer).

    Args:
        bot: The efl-bot-2.0 checkout.

    Returns:
        The `ff_result` module, or None when the checkout has none.
    """
    src = Path(bot) / "libs" / "efl-league" / "efl_league" / "ff_result.py"
    if not src.is_file():
        return None
    spec = importlib.util.spec_from_file_location("ff_result", src)
    module = importlib.util.module_from_spec(spec)
    sys.modules["ff_result"] = module
    spec.loader.exec_module(module)
    return module


# Records the map writes before efl-bot's parser learns them, with where that happens; reported, never a failure.
NOT_YET_IN_THE_BOT = {"sub": "efl-bot PR for 799X's -sub (league/22-sub.j)"}


def lost_values(mine, theirs):
    """Compares the map's file with the bot's parse of it.

    Args:
        mine: The file as tests.common.ffresult parsed it.
        theirs: The bot's FFResult for the same text.

    Returns:
        What the bot lost or read differently, in words.
    """
    problems = []
    unknown = [r for r in theirs.unknown_records if r.split(",", 1)[0] not in NOT_YET_IN_THE_BOT]
    if unknown:
        problems.append(f"records the parser does not know: {unknown[:5]}")
    roster = {e.slot for e in theirs.roster} if theirs.roster and hasattr(theirs.roster[0], "slot") else None
    for slot, st in sorted(mine.stats.items()):
        got = theirs.stats.get(slot)
        if got is None:
            problems.append(f"stats,{slot} lost")
            continue
        if roster is not None and slot not in roster:
            problems.append(f"stats,{slot} for a slot outside the roster")
        for k, v in st.values.items():
            if k in TEXT_STATS:
                continue
            if as_int(v) is None:
                problems.append(f"stats,{slot} {k}={v}: not an integer")
            elif got.values.get(k) != int(v):
                problems.append(f"stats,{slot} {k}: map {v}, parser {got.values.get(k)}")
    for (slot, cat), counts in sorted(mine.use.items()):
        got = theirs.usage.get((slot, cat), {})
        problems += [f"use,{slot},{cat} {k}: map {v}, parser {got.get(k)}" for k, v in counts.items() if got.get(k) != v]
    for (slot, hero), order in sorted(mine.skills.items()):
        if theirs.skills.get((slot, hero)) != order:
            problems.append(f"skills,{slot},{hero} order lost")
    for e in mine.events:
        if e.kind in MAP_EVENTS and e.extra and not any(
                x.kind == e.kind and x.slot == as_int(e.subject) and x.code == e.extra[0] for x in theirs.map_events):
            problems.append(f"{e.kind} event {e.subject},{e.extra[0]} lost")
    for row in mine.other_rows("modes"):
        for k, v in parse_kv(row.split(",")[1:]).items():
            if as_int(v) is None or theirs.modes.get(k) != int(v):
                problems.append(f"modes {k}: map {v}, parser {theirs.modes.get(k)}")
    if "gameend" in mine.result_kinds and not theirs.is_complete:
        problems.append("game ended but the parser finds it not complete enough to score")
    return problems


def check_parser(out, ff_result):
    """Puts every result file under `out` through the bot's parser.

    Args:
        out: The simulation's out dir.
        ff_result: The bot's parser module (load_parser).

    Returns:
        The checks, one per file (`contract <map>/<scenario>`).
    """
    checks = Checks("contract")
    files = result_files(out)
    if not files:
        checks.check(f"result files under {out}", False, "none")
    for path in files:
        text = path.read_text()
        try:
            mine = FFResultFile.parse(parse_rows(text))
        except FormatError as e:
            checks.check(f"contract {file_tag(path)}", False, f"malformed row {e}")
            continue
        try:
            theirs = ff_result.parse(text)
        except Exception as e:  # the parser rejecting a file the map wrote is the worst case
            checks.check(f"contract {file_tag(path)}", False, f"parser raised {type(e).__name__}: {e}")
            continue
        problems = lost_values(mine, theirs)
        checks.check(f"contract {file_tag(path)}", not problems, "; ".join(problems))
    return checks


def main(argv=None):
    """Runs both groups of checks.

    Args:
        argv: The command line (default: sys.argv[1:]).

    Returns:
        The exit code: 1 when a check failed, else 0.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="the simulation's out dir (<map>/<scenario>/ff_result.txt)")
    ap.add_argument("--bot", help="an efl-bot-2.0 checkout (default: $FF_EFL_BOT, else ../efl-bot-2.0)")
    a = ap.parse_args(argv)
    code = check_doc_keys(a.out).report()
    bot = Path(a.bot or os.environ.get("FF_EFL_BOT", REPO.parent / "efl-bot-2.0"))
    ff_result = load_parser(bot)
    if ff_result is None:
        print(f"contract: SKIPPED — no efl-bot checkout at {bot} (set FF_EFL_BOT)")
        return code
    missing = [f for f in PARSER_FIELDS if f not in getattr(ff_result.FFResult, "__dataclass_fields__", {})]
    if missing:
        print(f"contract: FAIL — the parser at {bot} has no {', '.join(missing)}: it cannot read the map's stats / "
              "usage rows; point FF_EFL_BOT at a checkout that has them")
        return 1
    return check_parser(a.out, ff_result).report() or code


if __name__ == "__main__":
    sys.exit(main())
