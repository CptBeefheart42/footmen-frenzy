"""ff: the one command for working on the maps, the same on Windows and Linux.

    ff doctor                     what is installed, what is missing
    ff setup                      install pjass and Lua into .tools/
    ff build <map> [--name F]     build a map into build/<map>/ (default name: <map>-dev.w3x)
    ff install <map> [--name F]   build, then put it into the Warcraft III Tests folder
    ff test sim [scenario ...]    build both maps and play the simulation scenarios against them
    ff blobs add <map> <entry> <file>   list a new binary file (model, texture) of a map
    ff blobs upload               upload listed binary files the release store lacks (maintainers)
    ff e2e build|run|check <map> <scenario>   an e2e scenario: build its test map / also play it on the test
                                  client and judge it / judge the last run (tests/e2e/README.md)
    ff e2e suite | ladder         every scenario, played and judged, then the ladder check / only the ladder check
                                  (suite --runs 799x:ffa solo:solo ... --no-probe: only these, without the probe)
    ff e2e probe | probe-build    the WC3 3.0 probe map: build, play and judge it / only build it
    ff pr fetch|check <N>         a contributor's pull request: copy it into a throwaway clone and list its changes /
                                  run ff check on it in an offline container (maintainers; the import-pr skill)
    ff objects fix-types <map>    store every object-data cell with its field's type (WC3 reads a wrong one as 0)
    ff hotkeys <map>              rewrite the map's hotkey list (projects/<map>/hotkeys.csv) after an intended change
    ff check                      every check a change passes before it is committed
    ff docker check               the same in a container (Linux or WSL with Docker; built locally from Dockerfile)
    ff release <version>          build every map with its release name (project.json) into build/release/ and zip them
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import blobs  # noqa: E402
import e2e  # noqa: E402
import hotkeys  # noqa: E402
import leaks  # noqa: E402
import objecttypes  # noqa: E402
import pr  # noqa: E402
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
    print('== object data types')
    for name, proj in projects().items():
        wrong = objecttypes.mismatches(proj.objects)
        for path, number, field, stored, want in wrong[:20]:
            print(f'{path.relative_to(ROOT)}:{number}: {field} is stored as {stored}, Warcraft III reads it as {want}')
        if wrong:
            print(f'{name}: {len(wrong)} cell(s) with the wrong type (WC3 3.0 reads them as 0): ff objects fix-types {name}')
            failed.append(f'object data types {name}')
        else:
            print(f'{name}: every cell has its field\'s type')
    print('== hotkeys')
    for name, proj in projects().items():
        changed = hotkeys.differences(proj)
        if changed:
            print(f'{name}: the hotkeys differ from projects/{name}/hotkeys.csv (`ff hotkeys {name}` after an intended change):')
            print('\n'.join(changed[:40]) + (f'\n... {len(changed) - 40} more' if len(changed) > 40 else ''))
            failed.append(f'hotkeys {name}')
        else:
            print(f'{name}: as listed')
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


DOCKER_IMAGE = 'footmen-frenzy-check'


def docker(command: list[str]) -> int:
    """Builds the image of Dockerfile locally and runs `ff <command>` in it, with the repository mounted and the
    caller's user, so every file it writes belongs to them. NuGet packages are kept in .tools/nuget."""
    if not shutil.which('docker'):
        raise toolchain.MissingTool('Docker is missing: install Docker (Linux) or Docker Desktop with WSL')
    with (ROOT / 'Dockerfile').open('rb') as dockerfile:
        if subprocess.run(['docker', 'build', '-q', '-t', DOCKER_IMAGE, '-'], stdin=dockerfile).returncode != 0:
            return 1
    user = ['--user', f'{os.getuid()}:{os.getgid()}'] if hasattr(os, 'getuid') else []
    # A git worktree's .git points to its main clone: mount that at the same path so git works inside.
    common = subprocess.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    mounts = ['-v', f'{common}:{common}'] if common and not Path(common).is_relative_to(ROOT) else []
    return subprocess.run(['docker', 'run', '--rm', *user, '-v', f'{ROOT}:/repo', *mounts, '-w', '/repo',
                           '-e', 'NUGET_PACKAGES=/repo/.tools/nuget', DOCKER_IMAGE,
                           'python3', 'tools/ff', *command]).returncode


def release(version: str) -> Path:
    """Builds every map with its release name for `version` and zips them into build/release/; returns the zip."""
    if not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z._-]*', version):
        raise RuntimeError(f'not a version: "{version}" (letters, digits, . _ -)')
    folder = BUILD / 'release'
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    built = []
    for name, proj in projects().items():
        file_name = proj.release_name.format(version=version, map=name)
        built.append(build(proj, file_name))
        shutil.copy2(built[-1], folder / file_name)
    archive = folder / f'Footmen_Frenzy_{version}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in built:
            z.write(folder / path.name, path.name)
    print(f'release {version}: ' + ', '.join(p.name for p in built) + f' -> {archive}')
    return archive


def e2e_command(args) -> int:
    """Runs `ff e2e <action> [map scenario]`; returns the exit code."""
    if args.action == 'suite':
        return e2e.suite(tuple(args.runs) if args.runs else e2e.SUITE, with_probe=not args.no_probe)
    if args.action == 'ladder':
        return e2e.ladder()
    if args.action == 'probe':
        return e2e.probe()
    if args.action == 'probe-build':
        print(f'built {e2e.build_probe(project("799x"))}')
        return 0
    if not args.map or not args.scenario:
        fail(f'ff e2e {args.action} needs a map and a scenario, e.g. ff e2e {args.action} 799x observer')
    if args.action == 'check':
        return e2e.judge(project(args.map), args.scenario)
    return e2e.scenario(args.map, args.scenario, only_build=args.action == 'build')


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
    p = commands.add_parser('release', help='build every map with its release name and zip them')
    p.add_argument('version')
    p = commands.add_parser('docker', help='run an ff command in a container built from Dockerfile')
    p.add_argument('rest', nargs=argparse.REMAINDER, help='the ff command, e.g. check')
    p = commands.add_parser('test', help='run a test suite')
    p.add_argument('suite', choices=['sim'])
    p.add_argument('scenarios', nargs='*', help='scenario names (default: all)')
    p = commands.add_parser('e2e', help='the real-client e2e suite (tests/e2e/README.md)')
    p.add_argument('action', choices=['build', 'run', 'check', 'suite', 'ladder', 'probe', 'probe-build'])
    p.add_argument('map', nargs='?', choices=list(projects()))
    p.add_argument('scenario', nargs='?')
    p.add_argument('--runs', nargs='+', metavar='MAP:SCENARIO', help='suite: only these runs (default: all)')
    p.add_argument('--no-probe', action='store_true', help='suite: without the probe map')
    p = commands.add_parser('pr', help="a contributor's pull request, safely (maintainers; the import-pr skill)")
    p.add_argument('action', choices=['fetch', 'check'])
    p.add_argument('number', type=int)
    p = commands.add_parser('objects', help="a map's object data (objects/*.txt)")
    p.add_argument('action', choices=['fix-types'])
    p.add_argument('map', choices=list(projects()))
    p = commands.add_parser('hotkeys', help="rewrite a map's hotkey list after an intended change")
    p.add_argument('map', choices=list(projects()))
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
        if args.command == 'docker':
            return docker(args.rest or ['check'])
        if args.command == 'e2e':
            return e2e_command(args)
        if args.command == 'pr':
            if args.action == 'fetch':
                changed = pr.fetch(args.number)
                print(f'pull request {args.number} -> {pr.folder(args.number)} (nothing of it was run)')
                for line in changed:
                    print(('RISKY  ' if pr.is_risky(line.split(chr(9))[-1]) else '       ') + line)
                return 0
            return pr.check(args.number)
        if args.command == 'objects':
            print(f'fixed {objecttypes.fix(project(args.map).objects)} cell type(s) in projects/{args.map}/objects')
            return 0
        if args.command == 'hotkeys':
            print(f'wrote {hotkeys.write(project(args.map))}')
            return 0
        if args.command == 'release':
            release(args.version)
            return 0
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
