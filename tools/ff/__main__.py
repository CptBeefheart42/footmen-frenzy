"""ff: the one command for working on the maps, the same on Windows and Linux.

    ff doctor                     what is installed, what is missing
    ff setup                      install pjass and Lua into .tools/
    ff build <map> [--name F]     build a map into build/<map>/ (default name: <map>-dev.w3x)
    ff install <map> [--name F]   build, then put it into the Warcraft III Tests folder
    ff check                      every check a change passes before it is committed
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import toolchain  # noqa: E402
from build import BuildError, build  # noqa: E402
from install import install, maps_folder  # noqa: E402
from repo import ROOT, project, projects, setting  # noqa: E402


def doctor() -> int:
    """Lists the programs the commands need and whether each was found."""
    checks = [('Git', True, lambda: shutil.which('git') or fail('install Git')),
              ('.NET SDK', True, lambda: toolchain.dotnet()[0]),
              ('pjass', True, toolchain.pjass),
              ('Lua 5.3', True, toolchain.lua),
              ('Warcraft III maps folder (for ff install)', False, lambda: str(maps_folder()))]
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
    """Installs pjass and Lua into .tools/ and turns on the pre-commit check."""
    for install_one in (toolchain.setup_pjass, toolchain.setup_lua):
        print(install_one())
    subprocess.run(['git', 'config', 'core.hooksPath', '.githooks'], cwd=ROOT, check=True)
    print('pre-commit check: on')
    return doctor()


def check() -> int:
    """Runs every check: shared code, tool tests, and a full build of every map."""
    failed = []
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
    print('all checks passed' if not failed else 'FAILED: ' + ', '.join(failed))
    return 1 if failed else 0


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
    commands.add_parser('check', help='every check a change passes before it is committed')
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            return doctor()
        if args.command == 'setup':
            return setup()
        if args.command == 'check':
            return check()
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
