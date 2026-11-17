"""Runs the simulation scenarios against the maps' transpiled scripts.

Every scenario (tests/simulation/scenarios/*.lua) runs in a fresh Lua state: `799x_*` scenarios on 799X, `solo_*` on
Solo, the rest on both. Each check prints PASS or FAIL (XFAIL: a known bug of the map, T.knownBug). The files a run
writes in the game's Preload format go to <out>/<map>/<scenario>/ for the contract check against the bot's parser.

    python -m tests.simulation.run <lua dir> <out dir> <lua interpreter> [scenario.lua ...]

<lua dir> holds common.lua, Blizzard.lua and <map>.lua (the runner's `jass-to-lua`; `ff test sim` makes them).
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
MAPS = ('799x', 'solo')


@dataclass
class Summary:
    """The counts of a simulation run and the scenarios that failed (`<map>/<scenario>`)."""
    passed: int = 0
    failed: int = 0
    known_bugs: int = 0
    broken: list[str] = field(default_factory=list)


def maps_of(scenario: Path) -> tuple[str, ...]:
    """The maps a scenario runs on, from its file name's prefix."""
    for name in MAPS:
        if scenario.stem.startswith(name + '_'):
            return (name,)
    return MAPS


def run(lua_dir: Path, out_dir: Path, lua: str, scenarios: list[Path] | None = None) -> Summary:
    """Runs scenarios and prints their checks.

    Args:
        lua_dir: The folder with common.lua, Blizzard.lua and one <map>.lua per map.
        out_dir: Where each run's files go (<out_dir>/<map>/<scenario>/).
        lua: The Lua 5.3 interpreter.
        scenarios: The scenarios to run; all of them when None.

    Returns:
        The counts and the failed scenarios.
    """
    summary = Summary()
    for scenario in scenarios or sorted((HERE / 'scenarios').glob('*.lua')):
        for name in maps_of(scenario):
            if not (lua_dir / f'{name}.lua').is_file():
                print(f'FAIL [{name}] {scenario.stem} :: {lua_dir / name}.lua missing')
                summary.failed += 1
                summary.broken.append(f'{name}/{scenario.stem}')
                continue
            (out_dir / name / scenario.stem).mkdir(parents=True, exist_ok=True)
            result = subprocess.run([lua, str(HERE / 'run.lua'), str(REPO / 'data' / 'common.j'), str(lua_dir), name,
                                     str(scenario)], capture_output=True, text=True,
                                    env={**os.environ, 'FF_SIM_OUT': str(out_dir)})
            for line in (result.stdout + result.stderr).splitlines():
                for word in ('PASS', 'FAIL', 'XFAIL'):
                    if line.startswith(word + ' '):
                        line = f'{word} [{name}] {line[len(word) + 1:]}'
                        summary.passed += word == 'PASS'
                        summary.failed += word == 'FAIL'
                        summary.known_bugs += word == 'XFAIL'
                        break
                print(line)
            if result.returncode != 0:
                summary.broken.append(f'{name}/{scenario.stem}')
    print(f'simulation: {summary.passed} passed, {summary.failed} failed, {summary.known_bugs} known bugs')
    if summary.broken:
        print('simulation: failing scenarios: ' + ' '.join(summary.broken))
    return summary


if __name__ == '__main__':
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    sys.exit(1 if run(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], [Path(p) for p in sys.argv[4:]] or None).broken else 0)
