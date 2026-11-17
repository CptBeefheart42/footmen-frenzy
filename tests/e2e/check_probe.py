#!/usr/bin/env python3
"""Verdict on a WC3 3.0 probe run (make probe-build, played by tests/e2e/run.py).

    tests/e2e/check_probe.py <ff_probe.txt> [--expect <probe_expect.csv>]

PASS needs three things:

  * the run finished (END);
  * every control and level-fill cell read back as stored, except the known deviations in probe_expect.csv;
  * Blizzard (the showcase of the level fill) hit units at every level, with damage rising by level, and never
    hurt a building (map fix Hbz4 = 0).

Prints one FAIL line per problem and a summary; exits 1 if anything failed.
"""
import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.common.checks import Checks  # noqa: E402
from tests.common.kv import parse_kv  # noqa: E402
from tests.common.paths import E2E_DIR  # noqa: E402
from tests.common.preload import read_rows  # noqa: E402

LANES = [1, 2, 3, 4, 5, 6]
BUILDING_LANES = (1, 2, 3)


@dataclass(frozen=True)
class Expectations:
    """The known deviations of a probe run (probe_expect.csv).

    Attributes:
        readbacks: (class, field, level) cells known not to read back as stored.
        max_unreadable: Per cell class, how many cells may be unreadable by the natives.
    """

    readbacks: frozenset
    max_unreadable: dict

    @classmethod
    def load(cls, path):
        """Reads probe_expect.csv (`readback,<class>,<field>,<level>` and `unreadable,<class>,<count>` rows)."""
        readbacks, unread = set(), {}
        lines = (line for line in Path(path).read_text().splitlines() if line.strip() and not line.startswith("#"))
        for r in csv.reader(lines):
            if r[0] == "readback":
                readbacks.add((r[1], r[2], int(r[3])))
            elif r[0] == "unreadable":
                unread[r[1]] = int(r[2])
        return cls(frozenset(readbacks), unread)


@dataclass(frozen=True)
class BlizzardLane:
    """One Blizzard test lane: the level cast there and the hit points each target type lost in 14 s.

    Attributes:
        level: The ability level cast.
        lost: (target unit type, hit points lost) per target, in the row's order.
    """

    level: int
    lost: tuple

    def of(self, unit):
        """The hit points lost by each target of a unit type."""
        return [hp for u, hp in self.lost if u == unit]


def readbacks(rows):
    """The cells that did not read back as stored (`R <ability> <field> L<level> ...` rows)."""
    return [(p[1], p[2], int(p[3][1:])) for p in (r.split() for r in rows if r.startswith("R "))]


def check_readbacks(checks, rows, exp):
    """Checks the cell readbacks (`R` rows) and the per-class summaries (`S` rows).

    Returns:
        The readback deviations found.
    """
    rb = readbacks(rows)
    for key in rb:
        checks.check(f"new readback deviation: {key[0]} {key[1]} L{key[2]}", key in exp.readbacks)
    zero_total = 0
    for r in rows:
        if not r.startswith("S "):
            continue
        cls, *fields = r.split()[1:]
        kv = parse_kv(fields)
        zero_total += int(kv["zero"])
        for k in ("default", "other", "noabil"):
            checks.check(f"{cls}: {k}={kv[k]}", kv[k] == "0")
        known = exp.max_unreadable.get(cls, 0)
        checks.check(f"{cls}: unreadable={kv['unreadable']} (known {known})", int(kv["unreadable"]) <= known)
    checks.check(f"zero cells {zero_total} != readback lines {len(rb)}", zero_total == len(rb))
    return rb


def blizzard_lanes(checks, rows):
    """Reads the Blizzard lanes (`BZ laneN Lx ...` rows) and checks that no level damages buildings.

    Returns:
        Lane number to BlizzardLane.
    """
    lanes = {}
    for r in rows:
        m = re.match(r"BZ lane(\d) L(\d) buildingDamage\(Hbz4\)=([\d.]+)", r)
        if m:
            checks.check(f"Blizzard L{m.group(2)} would damage buildings (Hbz4={m.group(3)}) — AHbz map fix missing",
                         float(m.group(3)) == 0)
        m = re.match(r"BZ lane(\d) L(\d) lost_14s: (.*)$", r)
        if m:
            lost = tuple((u, int(v)) for u, v in (x.split("=") for x in m.group(3).split()))
            lanes[int(m.group(1))] = BlizzardLane(int(m.group(2)), lost)
    return lanes


def check_blizzard(checks, lanes):
    """Checks what Blizzard did per lane: buildings untouched, units hit, damage rising with the level.

    Lanes 1-3 hold a guard tower (hwtw) and footmen (hfoo); lanes 4-6 one unit of each other target type.
    """
    checks.check(f"Blizzard lanes reported: {sorted(lanes)}", sorted(lanes) == LANES)
    if sorted(lanes) != LANES:
        return
    for n in BUILDING_LANES:
        lane = lanes[n]
        checks.check(f"AHbz L{lane.level} damaged the tower (lane {n})", all(v == 0 for v in lane.of("hwtw")))
        checks.check(f"AHbz L{lane.level} missed the footmen (lane {n})", all(v > 0 for v in lane.of("hfoo")))
    for n in sorted(set(LANES) - set(BUILDING_LANES)):
        lane = lanes[n]
        checks.check(f"AHbz L{lane.level} hit nothing on some target types (lane {n}): {lane.lost}",
                     all(v > 0 for _, v in lane.lost))
    dmg = {lane.level: lane.of("hfoo")[0] for lane in lanes.values()}
    order = sorted(dmg)
    rising = all(dmg[a] <= dmg[b] for a, b in zip(order, order[1:])) and dmg[order[0]] < dmg[order[-1]]
    checks.check(f"AHbz damage doesn't rise by level: {dict(sorted(dmg.items()))}", rising)


def judge(rows, exp):
    """Judges a probe run.

    Args:
        rows: The rows of ff_probe.txt.
        exp: The known deviations.

    Returns:
        (the checks, the number of readback rows).
    """
    checks = Checks("probe")
    checks.check("the probe did not finish (no END)", rows and rows[-1] == "END")
    head = rows[0] if rows else ""
    m = re.match(r"FF 3\.0 probe v(\d+) \| (\d+) cells", head)
    checks.check(f"header: {head!r}", m and int(m.group(2)) > 0)
    rb = check_readbacks(checks, rows, exp)
    check_blizzard(checks, blizzard_lanes(checks, rows))
    return checks, len(rb)


def main(argv=None):
    """Judges the probe file given on the command line.

    Args:
        argv: The command line (default: sys.argv[1:]).

    Returns:
        The exit code: 1 when anything failed, else 0.
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("probe", type=Path, help="the run's ff_probe.txt")
    ap.add_argument("expect_pos", type=Path, nargs="?", help=argparse.SUPPRESS)
    ap.add_argument("--expect", type=Path, help="the known deviations (default: tests/e2e/probe_expect.csv)")
    a = ap.parse_args(argv)
    rows = read_rows(a.probe) or []
    exp = Expectations.load(a.expect or a.expect_pos or E2E_DIR / "probe_expect.csv")
    checks, n_rb = judge(rows, exp)
    for key in sorted(exp.readbacks - set(readbacks(rows))):
        print(f"note: known deviation gone: {key[0]} {key[1]} L{key[2]} (remove it from probe_expect.csv)")
    for r in checks.failed:
        print(f"FAIL probe :: {r.name}")
    print(f"{'FAIL' if checks.failed else 'PASS'} probe :: {len(rows)} records, {n_rb} known readbacks")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.exit(main())
