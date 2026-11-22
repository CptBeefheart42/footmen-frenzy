"""The repository's maps: where they live and what their project.json says."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build'
TOOLS = ROOT / '.tools'


@dataclass(frozen=True)
class Release:
    """How a released map is named and stamped. Every text may hold {version}, the map's release version.

    Attributes:
        file: The map's file name, e.g. `Reforged_Footmen_Frenzy_v{version}.w3x`.
        title: The map name in the lobby and the map list; empty = the file name without `.w3x`.
        loading_title: The loading-screen title; empty = the map's own.
        author: The author the map must name (checked, never rewritten); empty = not checked.
        credits: A line appended to the map's in-game Credits quest; empty = none.
        own_version: The base version of a map numbered on its own (`<base>-<rebuild>`, e.g. 1.8-3) instead of with
            the release's tag; empty = the tag's version.
    """
    file: str = '{map}-{version}.w3x'
    title: str = ''
    loading_title: str = ''
    author: str = ''
    credits: str = ''
    own_version: str = ''

    def names(self, version: str, map_name: str) -> tuple[str, str, str]:
        """The file name, title and loading title for one version."""
        file = self.file.format(version=version, map=map_name)
        title = self.title.format(version=version) if self.title else file.removesuffix('.w3x')
        return file, title, self.loading_title.format(version=version)


@dataclass(frozen=True)
class Project:
    """One map project under projects/<name>/.

    Attributes:
        name: Folder name, e.g. `799x`.
        family: The map's family name (`map_type`), which names its Warcraft III test folder, e.g. `799X`.
        start_name: The release the starting map (`base.w3x`, the complete map a build starts from) came from.
        stub_functions: Functions of the map script the build turns into no-ops (the map's own writers of the files
            the league addons write).
        drop_entries: Files of the starting map the built map leaves out.
        settings: The map's game settings; the build hands them to the map script as FF_CFG_* constants.
        release: How the released map is named and stamped (project.json `release`).
    """
    name: str
    family: str
    start_name: str
    stub_functions: tuple[str, ...] = ()
    drop_entries: tuple[str, ...] = ()
    settings: dict = field(default_factory=dict, hash=False, compare=False)
    release: Release = field(default_factory=Release, hash=False, compare=False)

    @property
    def folder(self) -> Path:
        """The project folder."""
        return ROOT / 'projects' / self.name

    @property
    def base(self) -> Path:
        """The starting map: terrain, placed objects and imports as the World Editor last saved them."""
        return self.folder / 'base.w3x'

    @property
    def src(self) -> Path:
        """The folder holding every file of the map."""
        return self.folder / 'src'

    @property
    def addons(self) -> Path:
        """The map's own league addons (`*.j`, `anchors.txt`, `imports/`)."""
        return self.folder / 'addons'

    @property
    def objects(self) -> Path:
        """The map's object data (units, items, abilities ...) as text, one file per object-data file."""
        return self.folder / 'objects'

    @property
    def binaries(self) -> Path:
        """The list of the map's binary files: name -> SHA-256 and size."""
        return self.folder / 'binaries.json'


def setting(key: str, environment: str) -> str | None:
    """A local setting: the environment variable when set, else `key` in ff.local.json (a file Git ignores)."""
    config = ROOT / 'ff.local.json'
    configured = json.loads(config.read_text(encoding='utf-8')).get(key) if config.is_file() else None
    return os.environ.get(environment) or configured


def projects() -> dict[str, Project]:
    """Reads every project under projects/.

    Returns:
        The projects by folder name, sorted.
    """
    found = {}
    for meta in sorted((ROOT / 'projects').glob('*/project.json')):
        data = json.loads(meta.read_text(encoding='utf-8'))
        start = data['start_map']
        found[meta.parent.name] = Project(meta.parent.name, data['map_type'], start['name'],
                                          tuple(data.get('stub_functions', ())),
                                          tuple(data.get('drop_entries', ())), data.get('settings', {}),
                                          Release(**data.get('release', {})))
    return found


def project(name: str) -> Project:
    """Returns one project.

    Args:
        name: Folder name under projects/.

    Raises:
        KeyError: No such project; the message lists the existing ones.
    """
    all_projects = projects()
    if name not in all_projects:
        raise KeyError(f'no map project "{name}"; choose one of: {", ".join(all_projects)}')
    return all_projects[name]
