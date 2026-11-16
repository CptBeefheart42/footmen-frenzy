"""Builds a playable map from a project: shared code assembled, files packed, Warcraft III 3.0 fixes applied, checked.

Steps, all under build/<map>/:
1. the starting map (downloaded from LFS when the clone has only its pointer) is checked against project.json;
2. the map script is assembled from src/war3map.j and shared/ (tools/shared_code.py);
3. the runner packs the starting map with src/ (`pack`), downloading the LFS objects of changed files;
4. the runner applies the level fill, the map fixes (data/object_overrides.csv), the 3.0 file-name fix and the map
   name, then verifies the result (`verify-map`);
5. pjass checks the final script.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import lfs
import toolchain
from install import sha256
from repo import BUILD, ROOT, Project

sys.path.insert(0, str(ROOT / 'tools'))
from shared_code import assemble  # noqa: E402

OVERRIDES = ROOT / 'data' / 'object_overrides.csv'


class BuildError(RuntimeError):
    """A build step failed; the message says which and why."""


def build(project: Project, name: str) -> Path:
    """Builds `project` into build/<map>/<name>.

    Args:
        project: The map project.
        name: The map's file name, ending in .w3x; without the extension it is also the in-game map name.

    Returns:
        The built map.

    Raises:
        BuildError: A step failed.
    """
    if not name.lower().endswith('.w3x') or Path(name).name != name:
        raise BuildError(f'the map name must be a file name ending in .w3x, not "{name}"')
    title = name[:-4]
    out = BUILD / project.name
    out.mkdir(parents=True, exist_ok=True)

    start = lfs.content(project.start_map)
    if sha256(start) != project.sha256:
        raise BuildError(f'{project.start_map.name} does not match the checksum in project.json')
    script = out / 'assembled.j'
    script.write_bytes(assemble((project.src / 'war3map.j').read_bytes()))

    packed = out / 'packed.w3x'
    pack(project, start, script, packed, out / 'missing.txt')

    no_addons = out / 'no-addons'
    no_addons.mkdir(exist_ok=True)
    finished = out / name
    step('apply the 3.0 fixes and the map name', toolchain.run_dotnet_tool('tools/runner', [], {
        'FF_JASS_ADDONS': str(no_addons), 'FF_BASEMAP': str(packed), 'FF_OUTPUT': str(out), 'FF_OUTPUT_MAP': name,
        'FF_OBJECT_OVERRIDES': str(OVERRIDES), 'FF_MAP_NAME': title}))
    step('verify the built map', toolchain.run_dotnet_tool(
        'tools/runner', ['verify-map', str(finished), '--name', title, '--overrides', str(OVERRIDES)]))
    check_script(out / 'war3map.j')
    return finished


def pack(project: Project, start: Path, script: Path, packed: Path, missing: Path) -> None:
    """Runs the runner's `pack`, downloading the LFS objects it reports missing and trying once more."""
    args = ['pack', str(start), str(project.src), str(packed), '--script', str(script),
            '--lfs-cache', str(lfs.CACHE), '--missing', str(missing)]
    code = toolchain.run_dotnet_tool('tools/runner', args)
    if code == 3:
        objects = [lfs.LfsObject(oid, int(size)) for oid, size in (line.split() for line in missing.read_text().split('\n') if line)]
        lfs.fetch(objects)
        code = toolchain.run_dotnet_tool('tools/runner', args)
    step('pack the map', code)


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
