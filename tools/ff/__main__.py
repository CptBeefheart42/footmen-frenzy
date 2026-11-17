"""ff: the one command for working on the maps, the same on Windows and Linux.

    ff doctor                     what is installed, what is missing
    ff setup                      install pjass and Lua into .tools/
    ff build <map> [--name F]     build a map into build/<map>/ (default name: <map>-dev.w3x)
    ff install <map> [--name F]   build, then put it into the Warcraft III Tests folder
    ff test sim [scenario ...]    build both maps and play the simulation scenarios against them
    ff blobs add <map> <entry> <file>   list a new binary file (model, texture) of a map
    ff blobs upload               upload listed binary files the release store lacks (maintainers)
    ff check                      every check a change passes before it is committed
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import blobs  # noqa: E402
import leaks  # noqa: E402
import toolchain  # noqa: E402
from build import BuildError, build  # noqa: E402
from install import install, maps_folder  # noqa: E402
from repo import BUILD, ROOT, project, projects, setting  # noqa: E402


def doctor() -> int:
    """Lists the programs the commands need and whether each was found."""
    checks = [('Git', True, lambda: shutil.which('git') or fail('install Git')),
              ('.NET SDK', True, lambda: toolchain.dotnet()[0]),
              ('pjass', True, toolchain.pjass),
              ('Lua 5.3', True, toolchain.lua),
              ('Warcraft III maps folder (for ff install)', False, lambda: str(maps_folder())),
              ('openpyxl (for the workbook tests: pip install openpyxl)', False, lambda: __import__('openpyxl').__version__)]
    missing = 0
    for label, required, find in checks:
        try:
            print(f'  ok       {label}: {find()}')
        except Exception as error:  # every failure is reported, none stops the list
            missing += required
            print(f'  {"missing " if required else "optional"} {label}: {error}')
    return 1 if missing else 0


def fail(message: str):
    """Raises the message as a missing-tool error (for doctor's one-line checks)."""
    raise toolchain.MissingTool(message)


def setup() -> int:
    """Installs pjass and Lua into .tools/, makes the skills visible to Claude Code and turns on the pre-commit check."""
    for install_one in (toolchain.setup_pjass, toolchain.setup_lua):
        print(install_one())
    print(link_skills())
    subprocess.run(['git', 'config', 'core.hooksPath', '.githooks'], cwd=ROOT, check=True)
    print('pre-commit check: on')
    return doctor()


def link_skills() -> str:
    """Claude Code reads skills from .claude/skills, every other tool from .agents/skills: a link where the system
    allows one, else a copy (run ff setup again after changing a skill)."""
    target, link = ROOT / '.agents' / 'skills', ROOT / '.claude' / 'skills'
    link.parent.mkdir(exist_ok=True)
    if link.is_symlink() or link.is_file():
        link.unlink()
    elif link.is_dir():
        shutil.rmtree(link)
    try:
        link.symlink_to(Path('..') / '.agents' / 'skills', target_is_directory=True)
        return 'skills: .claude/skills links to .agents/skills'
    except OSError:
        shutil.copytree(target, link)
        return 'skills: copied to .claude/skills (no links on this system: run ff setup again after changing a skill)'


# Map variants the simulation plays too: a map built with some settings changed. Their scenarios are named
# <variant>_*.lua (tests/simulation/run.py).
SIM_VARIANTS = {'799x-sub': ('799x', {'sub': {'enabled': True}})}


def simulate(scenarios: list[str] | None = None, build_maps: bool = True) -> int:
    """Plays the simulation scenarios against both maps' built scripts, then checks the files they wrote against
    efl-bot's parser (skipped without an efl-bot checkout)."""
    sim = BUILD / 'simulation'
    lua_dir, out = sim / 'lua', sim / 'out'
    shutil.rmtree(sim, ignore_errors=True)
    lua_dir.mkdir(parents=True)
    pairs = [str(ROOT / 'data' / 'common.j'), str(lua_dir / 'common.lua'), str(ROOT / 'data' / 'Blizzard.j'), str(lua_dir / 'Blizzard.lua')]
    for name, proj in projects().items():
        if build_maps:
            build(proj, f'{name}-sim.w3x')
        pairs += [str(BUILD / name / 'war3map.j'), str(lua_dir / f'{name}.lua')]
    for variant, (base, settings) in SIM_VARIANTS.items():
        build(project(base), f'{variant}-sim.w3x', BUILD / variant, settings)
        pairs += [str(BUILD / variant / 'war3map.j'), str(lua_dir / f'{variant}.lua')]
    if toolchain.run_dotnet_tool('tools/runner', ['jass-to-lua', *pairs]) != 0:
        print('could not turn the map scripts into Lua')
        return 1
    sys.path.insert(0, str(ROOT))
    from tests.simulation.run import run  # noqa: E402 (the tests are a package of the repository)
    chosen = [ROOT / 'tests' / 'simulation' / 'scenarios' / f'{s}.lua' for s in scenarios] if scenarios else None
    summary = run(lua_dir, out, toolchain.lua(), chosen)
    contract = subprocess.run([sys.executable, '-m', 'tests.simulation.contract', str(out)], cwd=ROOT, env=test_environment())
    return 1 if summary.broken or contract.returncode != 0 else 0


def check() -> int:
    """Runs every check: private details, shared code, tool tests, a full build of every map, and the simulation."""
    failed = []
    print('== private details')
    found = leaks.scan(leaks.tracked_and_staged())
    print('\n'.join(found) if found else 'none found')
    if found:
        failed.append('private details')
    for label, command in [('shared code', [sys.executable, str(ROOT / 'tools' / 'shared_code.py'), 'check']),
                           ('tool tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-t', '.'])]:
        print(f'== {label}')
        if subprocess.run(command, cwd=ROOT, env=test_environment()).returncode != 0:
            failed.append(label)
    for name, proj in projects().items():
        print(f'== build {name}')
        try:
            build(proj, f'{name}-check.w3x')
        except (BuildError, toolchain.MissingTool) as error:
            print(error)
            failed.append(f'build {name}')
    if not any(f.startswith('build') for f in failed):
        print('== simulation')
        if simulate(build_maps=False) != 0:
            failed.append('simulation')
    print('all checks passed' if not failed else 'FAILED: ' + ', '.join(failed))
    return 1 if failed else 0


def blob_command(args) -> int:
    """ff blobs add <map> <entry> <file> | ff blobs upload."""
    if args.action == 'add':
        if not (args.map and args.entry and args.file):
            raise RuntimeError('usage: ff blobs add <map> <path inside the map> <file>')
        blob = blobs.add(project(args.map).binaries, args.entry, args.file)
        print(f'listed {args.entry} ({blob.size} bytes, {blob.sha256[:12]}) in projects/{args.map}/binaries.json')
        return 0
    listed = [blobs.Blob(b['sha256'], b['size']) for p in projects().values()
              for b in json.loads(p.binaries.read_text(encoding='utf-8')).values()]
    done = blobs.upload([b for b in listed if b.path.is_file()])
    print(f'uploaded {len(done)} binary file(s) to the release store')
    return 0


def test_environment() -> dict:
    """The environment for the tests: the efl-bot checkout from `efl_bot` in ff.local.json (FF_EFL_BOT)."""
    env = dict(os.environ)
    bot = setting('efl_bot', 'FF_EFL_BOT')
    if bot:
        env['FF_EFL_BOT'] = str(Path(bot).expanduser())
    return env


def main(argv: list[str] | None = None) -> int:
    """Runs a command; returns the exit code."""
    parser = argparse.ArgumentParser(prog='ff', description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor', help='what is installed, what is missing')
    commands.add_parser('setup', help='install pjass and Lua, turn on the pre-commit check')
    for name, text in (('build', 'build a map'), ('install', 'build a map and put it into the Warcraft III Tests folder')):
        p = commands.add_parser(name, help=text)
        p.add_argument('map', choices=list(projects()))
        p.add_argument('--name', help='file name of the map, ending in .w3x (default: <map>-dev.w3x)')
    p = commands.add_parser('blobs', help='binary files of a map (models, textures, sounds)')
    p.add_argument('action', choices=['add', 'upload'])
    p.add_argument('map', nargs='?', choices=list(projects()))
    p.add_argument('entry', nargs='?', help='add: the path inside the map, e.g. war3mapImported/Hero.mdx')
    p.add_argument('file', nargs='?', type=Path, help='add: the file on disk')
    p = commands.add_parser('test', help='run a test suite')
    p.add_argument('suite', choices=['sim'])
    p.add_argument('scenarios', nargs='*', help='scenario names (default: all)')
    commands.add_parser('check', help='every check a change passes before it is committed')
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            return doctor()
        if args.command == 'setup':
            return setup()
        if args.command == 'check':
            return check()
        if args.command == 'test':
            return simulate(args.scenarios)
        if args.command == 'blobs':
            return blob_command(args)
        proj = project(args.map)
        built = build(proj, args.name or f'{proj.name}-dev.w3x')
        print(f'built {built}')
        if args.command == 'install':
            print(f'installed {install(built, proj.family, maps_folder())}')
        return 0
    except (BuildError, toolchain.MissingTool, RuntimeError, KeyError) as error:
        print(f'ff: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
