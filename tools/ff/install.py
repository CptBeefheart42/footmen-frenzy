"""Puts a built map where Warcraft III finds it, keeping exactly one active test map per map family.

Layout under the Warcraft III maps folder:
- `Tests/<family>/<map>`: the one active test map; earlier ones move to `Tests/<family>/Test Archives/<time>/`.
- `<family>/<map>`: the same file as the family's current map; the earlier one moves to `Archive/<family>/<time>/`.
`Foots/` (live maps) is never touched. Copies are staged outside the maps folder and checked by SHA-256, so the game
never sees a half-written map.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from repo import ROOT

MAP_SUFFIXES = {'.w3x', '.w3m'}


def maps_folder() -> Path:
    """The Warcraft III maps folder: `maps_folder` in ff.local.json, else Documents/Warcraft III/Maps on Windows.

    Raises:
        RuntimeError: Not configured (Linux) or the folder does not exist.
    """
    config = ROOT / 'ff.local.json'
    configured = json.loads(config.read_text(encoding='utf-8')).get('maps_folder') if config.is_file() else None
    if configured:
        folder = Path(configured).expanduser()
    elif platform.system() == 'Windows':
        folder = Path(os.environ['USERPROFILE']) / 'Documents' / 'Warcraft III' / 'Maps'
    else:
        raise RuntimeError('set "maps_folder" in ff.local.json to your Warcraft III Maps folder')
    if not folder.is_dir():
        raise RuntimeError(f'Warcraft III maps folder not found: {folder} (set "maps_folder" in ff.local.json)')
    return folder


def install(map_file: Path, family: str, root: Path) -> Path:
    """Installs a map as the active test map and the current map of its family.

    Args:
        map_file: The built map.
        family: The map family, e.g. `799X`; names the folders.
        root: The Warcraft III maps folder.

    Returns:
        The installed test map.

    Raises:
        RuntimeError: A copy did not arrive intact; the folder keeps its earlier maps.
    """
    if map_file.suffix.lower() not in MAP_SUFFIXES:
        raise RuntimeError(f'not a Warcraft III map: {map_file}')
    checksum = sha256(map_file)
    stamp = datetime.now().strftime('%Y-%m-%d_%H%M%S') + '_' + uuid.uuid4().hex[:8]
    test = place(map_file, checksum, root / 'Tests' / family, root / 'Tests' / family / 'Test Archives' / stamp, root)
    place(map_file, checksum, root / family, root / 'Archive' / family / stamp, root)
    return test


def place(map_file: Path, checksum: str, folder: Path, archive: Path, root: Path) -> Path:
    """Makes `map_file` the only map in `folder`, moving the others into `archive`."""
    target = folder / map_file.name
    folder.mkdir(parents=True, exist_ok=True)
    if not (target.is_file() and sha256(target) == checksum):
        staging = root.parent / 'Map Install Staging'
        staging.mkdir(exist_ok=True)
        staged = staging / (uuid.uuid4().hex + '.pending')
        shutil.copyfile(map_file, staged)
        if sha256(staged) != checksum:
            staged.unlink()
            raise RuntimeError(f'copy of {map_file.name} arrived damaged; {folder} is unchanged')
        move_others(folder, target, archive)
        staged.replace(target)
        if sha256(target) != checksum:
            raise RuntimeError(f'installed {target} does not match the built map')
    else:
        move_others(folder, target, archive)
    return target


def move_others(folder: Path, keep: Path, archive: Path) -> None:
    """Moves every map in `folder` except `keep` into `archive`."""
    others = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in MAP_SUFFIXES and p != keep]
    if others:
        archive.mkdir(parents=True, exist_ok=True)
        for path in others:
            path.replace(archive / path.name)


def sha256(path: Path) -> str:
    """The SHA-256 of a file."""
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()
