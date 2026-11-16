"""Builds a playable map from a project: shared code assembled, files packed, Warcraft III 3.0 fixes applied, checked.

Steps, all under build/<map>/:
1. the starting map and the binary files that differ from it are downloaded by checksum (tools/ff/blobs.py);
2. the map script is assembled from src/war3map.j and shared/ (tools/shared_code.py);
3. the runner packs the starting map with src/ and binaries.json (`pack`);
4. the runner injects the league addons (league/ for every map, projects/<map>/addons/ for this one, with its anchor
   hooks and stubbed functions), applies the level fill, the map fixes (data/object_overrides.csv), the 3.0 file-name
   fix and the map name, then verifies the result (`verify-map`);
5. pjass checks the final script.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import blobs
import toolchain
from repo import BUILD, ROOT, Project

sys.path.insert(0, str(ROOT / 'tools'))
from shared_code import assemble  # noqa: E402

OVERRIDES = ROOT / 'data' / 'object_overrides.csv'
LEAGUE = ROOT / 'league'


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

    start_blob = blobs.Blob(project.start_sha256, project.start_size)
    blobs.fetch([start_blob])
    start = start_blob.path
    script = out / 'assembled.j'
    script.write_bytes(assemble((project.src / 'war3map.j').read_bytes()))

    packed = out / 'packed.w3x'
    pack(project, start, script, packed, out / 'missing.txt')

    finished = out / name
    anchors = project.addons / 'anchors.txt'
    step('add the league addons and the 3.0 fixes', toolchain.run_dotnet_tool('tools/runner', [], {
        'FF_JASS_ADDONS': str(LEAGUE), 'FF_JASS_MAP_ADDONS': str(project.addons) if project.addons.is_dir() else '',
        'FF_JASS_ANCHORS': str(anchors) if anchors.is_file() else '', 'FF_JASS_STUB_FUNCS': ','.join(project.stub_functions),
        'FF_BASEMAP': str(packed), 'FF_OUTPUT': str(out), 'FF_OUTPUT_MAP': name,
        'FF_OBJECT_OVERRIDES': str(OVERRIDES), 'FF_MAP_NAME': title}))
    verify = ['verify-map', str(finished), '--name', title, '--overrides', str(OVERRIDES)]
    if anchors.is_file():
        verify += ['--anchors', str(anchors)]
    if project.stub_functions:
        verify += ['--stubs', ','.join(project.stub_functions)]
    step('verify the built map', toolchain.run_dotnet_tool('tools/runner', verify))
    check_script(out / 'war3map.j')
    return finished


def pack(project: Project, start: Path, script: Path, packed: Path, missing: Path) -> None:
    """Runs the runner's `pack`, downloading the binary files it reports missing and trying once more."""
    args = ['pack', str(start), str(project.src), str(packed), '--script', str(script), '--binaries', str(project.binaries),
            '--blobs', str(blobs.CACHE), '--missing', str(missing)]
    code = toolchain.run_dotnet_tool('tools/runner', args)
    if code == 3:
        needed = [blobs.Blob(sha, int(size)) for sha, size in (line.split() for line in missing.read_text().split('\n') if line)]
        blobs.fetch(needed)
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
