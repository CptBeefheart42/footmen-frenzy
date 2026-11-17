"""Builds a playable map from a project: shared code assembled, files packed, Warcraft III 3.0 fixes applied, checked.

Steps, all under build/<map>/:
1. the starting map is projects/<map>/base.w3x; the binary files that differ from it are downloaded by checksum
   (tools/ff/blobs.py);
2. the map script is assembled from src/war3map.j and shared/ (tools/shared_code.py), and the object data is turned
   from text (objects/) into the map's binary files (runner `objects to-binary`);
3. the runner packs the starting map with those sources and binaries.json (`pack`);
4. the runner injects the league addons (league/ for every map, projects/<map>/addons/ for this one, with its anchor
   hooks and stubbed functions), applies the level fill, the map fixes (data/object_overrides.csv), the 3.0 file-name
   fix and the map name, then verifies the result (`verify-map`);
5. every file of the project is looked up in the built map the way the game does (tools/ff/lookup.py);
6. pjass checks the final script.
"""
from __future__ import annotations

import dataclasses
import shutil
import subprocess
import sys
from pathlib import Path

import blobs
import json
import lookup
import toolchain
from repo import BUILD, ROOT, Project

sys.path.insert(0, str(ROOT / 'tools'))
from shared_code import assemble  # noqa: E402

OVERRIDES = ROOT / 'data' / 'object_overrides.csv'
LEAGUE = ROOT / 'league'


class BuildError(RuntimeError):
    """A build step failed; the message says which and why."""


def build(project: Project, name: str, out: Path | None = None, settings: dict | None = None) -> Path:
    """Builds `project` into build/<map>/<name>.

    Args:
        project: The map project.
        name: The map's file name, ending in .w3x; without the extension it is also the in-game map name.
        out: Another build folder (a variant of the map, e.g. for tests).
        settings: Settings that replace the project's own, key by key (e.g. {"sub": {"enabled": True}}).

    Returns:
        The built map.

    Raises:
        BuildError: A step failed.
    """
    if not name.lower().endswith('.w3x') or Path(name).name != name:
        raise BuildError(f'the map name must be a file name ending in .w3x, not "{name}"')
    title = name[:-4]
    if settings:
        project = dataclasses.replace(project, settings=merged(project.settings, settings))
    out = out or BUILD / project.name
    out.mkdir(parents=True, exist_ok=True)

    start = project.base
    if not start.is_file():
        raise BuildError(f'{start.relative_to(ROOT)} is missing: the starting map is part of the repository')
    script = out / 'assembled.j'
    script.write_bytes(assemble((project.src / 'war3map.j').read_bytes()))

    sources = stage_sources(project, out / 'sources')
    packed = out / 'packed.w3x'
    pack(project, sources, start, script, packed, out / 'missing.txt')

    finished = out / name
    anchors = project.addons / 'anchors.txt'
    map_addons = stage_map_addons(project, out / 'addons')
    step('add the league addons and the 3.0 fixes', toolchain.run_dotnet_tool('tools/runner', [], {
        'FF_JASS_ADDONS': str(LEAGUE), 'FF_JASS_MAP_ADDONS': str(map_addons) if map_addons else '',
        'FF_JASS_ANCHORS': str(anchors) if anchors.is_file() else '', 'FF_JASS_STUB_FUNCS': ','.join(project.stub_functions),
        'FF_BASEMAP': str(packed), 'FF_OUTPUT': str(out), 'FF_OUTPUT_MAP': name,
        'FF_OBJECT_OVERRIDES': str(OVERRIDES), 'FF_MAP_NAME': title}))
    verify = ['verify-map', str(finished), '--name', title, '--overrides', str(OVERRIDES)]
    if anchors.is_file():
        verify += ['--anchors', str(anchors)]
    if project.stub_functions:
        verify += ['--stubs', ','.join(project.stub_functions)]
    step('verify the built map', toolchain.run_dotnet_tool('tools/runner', verify))
    check_reachable(project, finished)
    check_script(out / 'war3map.j')
    return finished


def merged(base: dict, changes: dict) -> dict:
    """`base` with `changes` laid over it, nested dictionaries key by key."""
    result = dict(base)
    for key, value in changes.items():
        result[key] = merged(result.get(key, {}), value) if isinstance(value, dict) else value
    return result


def stage_sources(project: Project, folder: Path) -> Path:
    """Copies src/ into `folder` and adds the object-data files made from objects/; returns `folder`."""
    shutil.rmtree(folder, ignore_errors=True)
    shutil.copytree(project.src, folder)
    if project.objects.is_dir():
        step('turn the object data into the map\'s files', toolchain.run_dotnet_tool(
            'tools/runner', ['objects', 'to-binary', str(project.objects), str(folder)]))
    return folder


def stage_map_addons(project: Project, folder: Path) -> Path | None:
    """Copies the map's own addons into `folder` and adds the settings addon; returns None when there is neither."""
    shutil.rmtree(folder, ignore_errors=True)
    if not project.addons.is_dir() and not project.settings:
        return None
    if project.addons.is_dir():
        shutil.copytree(project.addons, folder, ignore=shutil.ignore_patterns('anchors.txt'))
    folder.mkdir(parents=True, exist_ok=True)
    if project.settings:
        (folder / '05-settings.j').write_text(settings_addon(project), encoding='utf-8', newline='\n')
    return folder


def settings_addon(project: Project) -> str:
    """The map's settings as JASS constants: {"pooling": {"pub_open_s": 230}} -> FF_CFG_POOLING_PUB_OPEN_S = 230."""
    lines = []

    def walk(prefix: str, value) -> None:
        if isinstance(value, dict):
            for key, inner in value.items():
                walk(f'{prefix}_{key}'.upper(), inner)
        elif isinstance(value, bool):
            lines.append(f'    constant boolean {prefix} = {"true" if value else "false"}')
        elif isinstance(value, int):
            lines.append(f'    constant integer {prefix} = {value}')
        elif isinstance(value, float):
            lines.append(f'    constant real {prefix} = {value}')
        else:
            text = str(value).replace('\\', '\\\\').replace('"', '\\"')
            lines.append(f'    constant string {prefix} = "{text}"')

    walk('FF_CFG', project.settings)
    return (f'// The settings of projects/{project.name}/project.json, written by ff build.\n'
            'globals\n' + '\n'.join(lines) + '\nendglobals\n')


def pack(project: Project, sources: Path, start: Path, script: Path, packed: Path, missing: Path) -> None:
    """Runs the runner's `pack`, downloading the binary files it reports missing and trying once more."""
    args = ['pack', str(start), str(sources), str(packed), '--script', str(script), '--binaries', str(project.binaries),
            '--blobs', str(blobs.CACHE), '--missing', str(missing)]
    if project.drop_entries:
        args += ['--drop', ','.join(project.drop_entries)]
    code = toolchain.run_dotnet_tool('tools/runner', args)
    if code == 3:
        needed = [blobs.Blob(sha, int(size)) for sha, size in (line.split() for line in missing.read_text().split('\n') if line)]
        blobs.fetch(needed)
        code = toolchain.run_dotnet_tool('tools/runner', args)
    step('pack the map', code)


def check_reachable(project: Project, map_file: Path) -> None:
    """Checks that the game finds every file of the project in the built map."""
    names = list(json.loads(project.binaries.read_text(encoding='utf-8')))
    names += [p.relative_to(project.src).as_posix() for p in project.src.rglob('*') if p.is_file()]
    names += [p.name.removesuffix('.txt') for p in project.objects.glob('*.txt')]
    lost = lookup.unreachable(map_file, names)
    if lost:
        raise BuildError('the game would not find these files in the built map: ' + ', '.join(lost[:10]))


def check_script(script: Path) -> None:
    """Checks a map script with pjass against data/common.j and data/Blizzard.j."""
    result = subprocess.run([toolchain.pjass(), str(ROOT / 'data' / 'common.j'), str(ROOT / 'data' / 'Blizzard.j'), str(script)],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise BuildError('pjass found problems in the map script:\n' + (result.stdout + result.stderr).strip())


def step(what: str, code: int) -> None:
    """Raises BuildError when a step's exit code is not 0."""
    if code != 0:
        raise BuildError(f'could not {what} (exit code {code}); the lines above say why')
