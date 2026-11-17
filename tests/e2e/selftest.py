#!/usr/bin/env python3
"""Negative controls for the e2e checks: doctored copies of a real, passing run must FAIL, for the right reason.

    tests/e2e/selftest.py <out dir of a passing ffa run> [<out dir of a passing probe run>]
                          [--skills <main-skills out dir>] [--kd <main-kd out dir>]
                          [--trade <main-trade out dir>]

Each mutation is what a real regression would look like in the files the map writes: the result's end missing, an
engine counter stuck at 0, the file under the wrong name, a slot's second stats row lost, a tie in the placements,
a kill-log row short of a field, a kill log off the -kd counters, an Allies-menu trade not counted; for the probe, Blizzard dealing no damage at level 5; for the skills, a spell
that costs no mana. The unmodified copy must pass first, else the selftest proves nothing.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.common.checks import Checks  # noqa: E402
from tests.common.paths import E2E_DIR  # noqa: E402
from tests.common.preload import rewrite_rows  # noqa: E402


def result_file(d):
    """The run's result file (ff_result.txt or ff_result_<token>.txt)."""
    return next(Path(d).glob("ff_result*.txt"))


def drop_gameend(d):
    """Removes the result's gameend row."""
    rewrite_rows(result_file(d), lambda r: None if r.startswith("gameend,") else r)


def zero_dmg_bld(d):
    """Sets slot 1's building damage to 0."""
    rewrite_rows(result_file(d), lambda r: re.sub(r"dmg_bld=\d+", "dmg_bld=0", r) if r.startswith("stats,1,") else r)


def wrong_token(d):
    """Renames the result file to another game's token."""
    result_file(d).rename(Path(d) / "ff_result_123.txt")


def lose_second_stats_row(d):
    """Keeps only slot 3's first stats row."""
    seen = []

    def fn(r):
        if r.startswith("stats,3,"):
            seen.append(r)
            return r if len(seen) == 1 else None
        return r
    rewrite_rows(result_file(d), fn)


def given_by_script(d):
    """Makes slot 2's pooled gold show up as gold received on the score screen."""
    rewrite_rows(result_file(d), lambda r: r.replace(",recv=0,", ",recv=500,", 1) if r.startswith("stats,2,") else r)


def placement_tie(d):
    """Turns place 3 into a second place 2."""
    rewrite_rows(result_file(d), lambda r: r.replace("placement,3,", "placement,2,", 1))


def short_killlog_row(d):
    """Cuts the last field off the kill log's first owner row."""
    done = []

    def fn(r):
        if not done and not r.startswith(("owner,", "herokill,")):
            done.append(r)
            return r.rsplit(",", 1)[0]
        return r
    rewrite_rows(next(Path(d).glob("ff_killlog*.txt")), fn)


def killlog_off_by_one(d):
    """Adds one unit kill to the kill log's first owner row (a log that drifted from the -kd counters)."""
    done = []

    def fn(r):
        if not done and not r.startswith(("owner,", "herokill,")):
            done.append(r)
            name, unit, rest = r.split(",", 2)
            return f"{name},{int(unit) + 1},{rest}"
        return r
    rewrite_rows(next(Path(d).glob("ff_killlog*.txt")), fn)


def trade_not_given(d):
    """Drops the Allies-menu trade from the score screen (what a lost tribute would look like)."""
    rewrite_rows(Path(d) / "ff_e2e.txt",
                 lambda r: re.sub(r",given1=\d+,", ",given1=0,", r) if r.startswith("trade,step=tribute,") else r)


def skills_mana_zero(d):
    """Makes the first effective cast free of mana (what a level with unset cells does)."""
    done = []

    def fn(r):
        if not done and r.startswith("c,") and ",eff=1," in r and ",mana=0," not in r:
            done.append(r)
            return re.sub(r",mana=\d+,", ",mana=0,", r)
        return r
    rewrite_rows(Path(d) / "ff_e2e.txt", fn)


def blizzard_l5_zero(d):
    """Makes Blizzard's level 5 lane lose no hit points (a level that hits nothing)."""
    rewrite_rows(Path(d) / "ff_probe.txt",
                 lambda r: re.sub(r"=\d+", "=0", r) if r.startswith("BZ lane5 L5 lost_14s:") else r)


@dataclass(frozen=True)
class Mutation:
    """A doctored copy of a run and the failure it must cause.

    Attributes:
        name: The regression it stands for, in words.
        mutate: Changes the copied run dir in place.
        expect: Text of the FAIL line the checker must print (empty: any failure).
    """

    name: str
    mutate: object
    expect: str = ""


FFA = [
    Mutation("the result's gameend row missing", drop_gameend, "gameend written once"),
    Mutation("an engine counter stuck at 0 (dmg_bld)", zero_dmg_bld, "stats,1 dmg_bld"),
    Mutation("the result under another token", wrong_token, "result files written"),
    Mutation("a slot's second stats row lost", lose_second_stats_row, "stats,3: every key"),
    Mutation("a tie in the placements", placement_tie, "placements 1..N"),
    Mutation("script gold counted as received on the score screen", given_by_script, "leave the score screen's given"),
    Mutation("a kill-log row one field short", short_killlog_row, "kill log owner rows"),
]
PROBE = [Mutation("Blizzard level 5 deals no damage", blizzard_l5_zero)]
SKILLS = [Mutation("one cast free of mana (unset level cells)", skills_mana_zero, "mana spent")]
TRADE = [Mutation("the Allies-menu trade not counted as gold given", trade_not_given, "gave 300")]
KD = [Mutation("a kill log one kill off the map's counters", killlog_off_by_one, "kill log owner rows = the map's counters")]


def run_check(cmd):
    """Runs a checker.

    Args:
        cmd: The command line.

    Returns:
        (exit code, the FAIL lines it printed).
    """
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, [line for line in p.stdout.splitlines() if line.startswith("FAIL")]


def control(checks, label, run_dir, cmd, mutations, prepare=None):
    """Checks the unmodified run, then every mutation of a copy of it.

    Args:
        checks: Where the outcomes are recorded.
        label: The run's kind (`ffa`, `probe`, `skills`), for the check names.
        run_dir: The real run.
        cmd: Builds the checker's command line for a run dir.
        mutations: The doctored variants.
        prepare: Called on the copy before every check (to add files the checker needs), or None.
    """
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "run"
        shutil.copytree(run_dir, d)
        if prepare:
            prepare(d)
        code, fails = run_check(cmd(d))
    checks.check(f"the unmodified {label} run passes", code == 0, "; ".join(fails[:3]))
    for m in mutations:
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "run"
            shutil.copytree(run_dir, d)
            if prepare:
                prepare(d)
            m.mutate(d)
            code, fails = run_check(cmd(d))
            want = f" -> FAIL '{m.expect}'" if m.expect else " -> FAIL"
            checks.check(f"{label}: {m.name}{want}", code != 0 and any(m.expect in f for f in fails),
                         f"exit {code}, fails {fails[:4]}")


def main(argv=None):
    """Runs the negative controls.

    Args:
        argv: The command line (default: sys.argv[1:]).

    Returns:
        The exit code: 1 when a control failed, else 0.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ffa", type=Path, help="out dir of a passing ffa run")
    ap.add_argument("probe", type=Path, nargs="?", help="out dir of a passing probe run")
    ap.add_argument("--skills", type=Path, help="out dir of a passing main-skills run")
    ap.add_argument("--kd", type=Path, help="out dir of a passing main-kd run")
    ap.add_argument("--trade", type=Path, help="out dir of a passing main-trade run")
    a = ap.parse_args(argv)
    py, checker = sys.executable, str(E2E_DIR / "check_e2e.py")
    checks = Checks("selftest")
    control(checks, "ffa", a.ffa, lambda d: [py, checker, "ffa", str(d)], FFA)
    if a.probe:
        control(checks, "probe", a.probe, lambda d: [py, str(E2E_DIR / "check_probe.py"), str(d / "ff_probe.txt")],
                PROBE)
    if a.skills:
        expect = a.skills.parent / "stage" / "main-skills" / "skills_expect.json"
        control(checks, "skills", a.skills, lambda d: [py, checker, "skills", str(d), "--map", "main"], SKILLS,
                prepare=lambda d: shutil.copy2(expect, d / "skills_expect.json"))
    if a.kd:
        control(checks, "kd", a.kd, lambda d: [py, checker, "kd", str(d)], KD)
    if a.trade:
        control(checks, "trade", a.trade, lambda d: [py, checker, "trade", str(d)], TRADE)
    return checks.report()


if __name__ == "__main__":
    sys.exit(main())
