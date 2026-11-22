"""The e2e suite: test builds of the maps played in the real Warcraft III 3.0 client, then judged and scored.

A scenario (tests/e2e/addons/<scenario>/) is a folder of test addons that drive the game and record what happened
(`ff_e2e.txt`). Its test build is the map with the league addons, the e2e core, the scenario, the scenario's computer
slots (`slots.<map>` or `slots`) and object changes (`object_overrides.csv`), never released. tests/e2e/run.py plays it
on the test client (`~/wc3-test`, Linux with Proton), tests/e2e/check_e2e.py judges the files the game wrote, and the
ladder check scores the finished games with the efl-bot checkout (setting `efl_bot`). tests/e2e/README.md explains
the scenarios and the client.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import toolchain
from build import BuildError, TestParts, build
from repo import BUILD, ROOT, Project, project, setting

sys.path.insert(0, str(ROOT))
from tests.e2e import stage as e2e_stage  # noqa: E402

ADDONS = ROOT / 'tests' / 'e2e' / 'addons'
PROBE = ROOT / 'tests' / 'e2e' / 'probe'
PROBE_LOBBY = 'FF 3.0 Probe [probe]'
OUT = BUILD / 'e2e'
CLIENT = '(E2E)Tester#100000'
TIMEOUT = 1200
# map:scenario, in the order the suite plays them (the observers play to the end: their file is the one the fleet reports)
SUITE = ('799x:observer', '799x:ffa', 'solo:solo', 'solo:solo-observer', '799x:afk', 'solo:afk', '799x:skills',
         'solo:skills', '799x:kd', '799x:kill_credit', '799x:trade', '799x:towerfire', '799x:transmute_creeps',
         'solo:transmute_creeps', '799x:transmute_destroyed', '799x:transmute_left', 'solo:transmute_destroyed',
         'solo:transmute_left')
# the finished games the ladder check scores
LADDER_RUNS = ('799x-observer', '799x-ffa', 'solo-solo', 'solo-solo-observer')
# where the skills scenario's host clicks the mode dialog, and how long it waits before casting (per map)
SKILLS_CLICK = {'799x': '0.5 0.478', 'solo': '0.5 0.542'}
SKILLS_AFTER = {'799x': '10', 'solo': '95'}


def scenario_folder(scenario: str) -> Path:
    """The scenario's addon folder; raises BuildError when there is none."""
    folder = ADDONS / scenario
    if not folder.is_dir() or scenario == 'core':
        raise BuildError(f'no e2e scenario "{scenario}" in tests/e2e/addons')
    return folder


def slots(proj: Project, scenario: str) -> str:
    """The scenario's computer slots for this map (`slots.<map>`, else `slots`)."""
    folder = scenario_folder(scenario)
    for name in (f'slots.{proj.name}', 'slots'):
        if (folder / name).is_file():
            return (folder / name).read_text(encoding='utf-8').strip()
    raise BuildError(f'tests/e2e/addons/{scenario} has no slots file for {proj.name}')


def run_name(proj: Project, scenario: str) -> str:
    """The name of a scenario run: `<map>-<scenario>` (its stage, map and result folders)."""
    return f'{proj.name}-{scenario}'


def build_scenario(proj: Project, scenario: str, bot: str = CLIENT) -> Path:
    """Builds the scenario's test map into build/e2e/ff-e2e-<map>-<scenario>.w3x; returns it."""
    folder = scenario_folder(scenario)
    staged = OUT / 'stage' / run_name(proj, scenario)
    e2e_stage.stage(proj.name, scenario, staged, bot)
    if scenario == 'skills':
        skills_data(proj, staged)
    overrides = [ADDONS / 'core' / 'object_overrides.csv']
    if (folder / 'object_overrides.csv').is_file():
        overrides.append(folder / 'object_overrides.csv')
    parts = TestParts(staged / 'jass', staged / 'map', tuple(p for p in overrides if p.is_file()), slots(proj, scenario))
    return build(proj, f'ff-e2e-{run_name(proj, scenario)}.w3x', out=OUT, test=parts, title=lobby_name(proj, scenario))


def lobby_name(proj: Project, scenario: str) -> str:
    """The test map's lobby name; the runner finds it by this name in the menus (the closing bracket keeps one name
    from matching another in the filter)."""
    return f'FF e2e [{proj.name} {scenario}]'


def menu_name(proj: Project, scenario: str) -> str:
    """The name the runner searches the menu's map list for: the lobby name, or empty for Solo, whose older map info
    (format 33) the 3.0.1 list shows without a name; the runner then takes the only map in Maps/Test."""
    return '' if proj.name == 'solo' else lobby_name(proj, scenario)


def skills_data(proj: Project, staged: Path) -> None:
    """Writes the skills scenario's data: every hero skill of the map as released, with its numbers and base order."""
    released = build(proj, f'{proj.name}-skills-source.w3x', out=OUT / 'skills-source')
    dump = staged / '_fill.csv'
    if toolchain.run_dotnet_tool('tools/BalanceTool', ['dumpall', str(released), str(dump), '--fill']) != 0:
        raise BuildError('could not dump the map\'s object data for the skills scenario')
    e2e = ROOT / 'tests' / 'e2e'
    result = subprocess.run([sys.executable, '-I', str(e2e / 'gen_skills.py'), '--dump', str(dump),
                             '--orders', f'{e2e / "ability_orders.csv"};{e2e / "ability_orders_extra.csv"}',
                             '--out', str(staged / 'map' / '05-e2e-skills-data.j'),
                             '--expect', str(staged / 'skills_expect.json'),
                             '--host-click', SKILLS_CLICK[proj.name], '--cast-after', SKILLS_AFTER[proj.name]])
    dump.unlink(missing_ok=True)
    if result.returncode != 0:
        raise BuildError('could not write the skills scenario\'s data (tests/e2e/gen_skills.py)')


def build_probe(proj: Project) -> Path:
    """Builds the WC3 3.0 probe map (never released) into build/e2e/ff-probe.w3x; returns it.

    The probe is the map's object data as released with the map's own triggers switched off, the league addons and
    the probe addons (tests/e2e/probe) with tables from tools/probe/gen_probe.py, which reads the pre-3.0 install
    (setting `wc3_stage`, default ~/wc3-stage). Played alone, it writes CustomMapData/ff_probe.txt.
    """
    stage_dir = Path(os.path.expanduser(setting('wc3_stage', 'FF_WC3_STAGE') or '~/wc3-stage'))
    if not (stage_dir / '.build.info').is_file():
        raise BuildError(f'no pre-3.0 Warcraft III install at {stage_dir} (setting wc3_stage)')
    folder = OUT / 'stage' / 'probe'
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    # the map as packed by the release build (the starting map rewritten by our runner, before the level fill)
    build(proj, f'{proj.name}-probe-source.w3x', out=OUT / 'probe-source')
    packed = OUT / 'probe-source' / 'packed.w3x'
    raw, filled = folder / '_raw.csv', folder / '_filled.csv'
    for dump, extra in ((raw, []), (filled, ['--fill'])):
        if toolchain.run_dotnet_tool('tools/BalanceTool', ['dumpall', str(packed), str(dump), *extra]) != 0:
            raise BuildError('could not dump the map\'s object data for the probe')
    if subprocess.run([sys.executable, str(ROOT / 'tools' / 'probe' / 'gen_probe.py'), '--casc', str(stage_dir),
                       '--raw', str(raw), '--filled', str(filled), '--out', str(folder / '60-probe-data.j')]).returncode:
        raise BuildError('could not write the probe tables (tools/probe/gen_probe.py)')
    raw.unlink()
    filled.unlink()
    for f in PROBE.glob('*.j'):
        shutil.copy2(f, folder / f.name)
    parts = TestParts(ROOT / 'league', folder, (PROBE / 'object_overrides.csv',),
                      stub_functions=('InitCustomTriggers',), anchors=False)
    return build(proj, 'ff-probe.w3x', out=OUT, test=parts, title=PROBE_LOBBY)


def probe() -> int:
    """Builds the probe map, plays it on the test client and judges it (tests/e2e/check_probe.py)."""
    built = build_probe(project('799x'))
    out = OUT / 'probe'
    played = subprocess.run([sys.executable, str(ROOT / 'tests' / 'e2e' / 'run.py'), str(built), str(out),
                             '--lobby', PROBE_LOBBY, '--done', 'ff_probe.txt', '--timeout', '900', '--collect', 'ff_probe.txt'], cwd=ROOT).returncode
    judged = subprocess.run([sys.executable, str(ROOT / 'tests' / 'e2e' / 'check_probe.py'), str(out / 'ff_probe.txt')],
                            cwd=ROOT).returncode
    return 0 if played == 0 and judged == 0 else 1


def play(proj: Project, scenario: str, built: Path) -> int:
    """Plays a built scenario on the test client; the files land in build/e2e/<map>-<scenario>/. Returns run.py's code."""
    return subprocess.run([sys.executable, str(ROOT / 'tests' / 'e2e' / 'run.py'), str(built),
                           str(OUT / run_name(proj, scenario)), '--lobby', menu_name(proj, scenario), '--done', 'ff_e2e.txt', '--timeout', str(TIMEOUT),
                           '--collect', 'ff_result*.txt', 'ff_killlog*.txt', 'ff_ping*.txt', 'ff_e2e*.txt'], cwd=ROOT).returncode


def judge(proj: Project, scenario: str, bot: bool = True) -> int:
    """Judges the last run of a scenario (tests/e2e/check_e2e.py); returns its exit code."""
    return subprocess.run([sys.executable, str(ROOT / 'tests' / 'e2e' / 'check_e2e.py'), scenario,
                           str(OUT / run_name(proj, scenario)), '--map', proj.name, '--bot' if bot else '--no-bot'],
                          cwd=ROOT, env=test_env()).returncode


def ladder(runs: tuple[str, ...] = LADDER_RUNS) -> int:
    """Scores finished games with the efl-bot commit the fleet runs (tests/e2e/efl-bot.ref) and that repository's
    Python (.venv); returns the exit code.

    The commit is checked out as a worktree of the efl-bot repository (setting `efl_bot_repo`) into build/e2e/efl-bot.
    """
    repo = setting('efl_bot_repo', 'FF_EFL_BOT_REPO')
    if not repo:
        print('ladder: no efl-bot repository (set efl_bot_repo in ff.local.json): skipped')
        return 1
    repo = Path(os.path.expanduser(repo))
    ref = (ROOT / 'tests' / 'e2e' / 'efl-bot.ref').read_text(encoding='utf-8').split()[0]
    checkout = OUT / 'efl-bot'
    head = subprocess.run(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    if head != ref:
        subprocess.run(['git', '-C', str(repo), 'worktree', 'remove', '--force', str(checkout)], capture_output=True)
        subprocess.run(['git', '-C', str(repo), 'worktree', 'prune'], check=True)
        subprocess.run(['git', '-C', str(repo), 'worktree', 'add', '-q', '--detach', str(checkout), ref], check=True)
    python = repo / '.venv' / 'bin' / 'python'
    return subprocess.run([str(python if python.is_file() else sys.executable), str(ROOT / 'tests' / 'e2e' / 'ladder_check.py'),
                           str(checkout), *(str(OUT / r) for r in runs)], cwd=ROOT).returncode


def test_env() -> dict:
    """The environment of the judging scripts: the efl-bot checkout, when one is set."""
    env = dict(os.environ)
    bot = setting('efl_bot', 'FF_EFL_BOT')
    if bot:
        env['FF_EFL_BOT'] = os.path.expanduser(bot)
    return env


def scenario(map_name: str, name: str, only_build: bool = False) -> int:
    """Builds one scenario, then (unless `only_build`) plays and judges it; returns 0 when it passed."""
    proj = project(map_name)
    built = build_scenario(proj, name)
    print(f'built {built}')
    if only_build:
        return 0
    played = play(proj, name, built)
    judged = judge(proj, name)
    return 0 if played == 0 and judged == 0 else 1


def suite(runs: tuple[str, ...] = SUITE, with_probe: bool = True) -> int:
    """Plays and judges the probe and every scenario of the suite, then the ladder check; returns 0 when all passed."""
    failed = []
    if with_probe:
        print('== e2e probe')
        try:
            if probe() != 0:
                failed.append('probe')
        except BuildError as error:
            print(error)
            failed.append('probe')
    for run in runs:
        map_name, name = run.split(':')
        print(f'== e2e {run}')
        try:
            if scenario(map_name, name) != 0:
                failed.append(run)
        except BuildError as error:
            print(error)
            failed.append(run)
    print('== e2e ladder')
    if ladder() != 0:
        failed.append('ladder')
    print('e2e: PASS' if not failed else 'e2e: FAIL ' + ', '.join(failed))
    return 1 if failed else 0
