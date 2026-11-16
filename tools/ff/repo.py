"""The repository's maps: where they live and what their project.json says."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build'
TOOLS = ROOT / '.tools'


@dataclass(frozen=True)
class Project:
    """One map project under projects/<name>/.

    Attributes:
        name: Folder name, e.g. `799x`.
        family: The map's family name (`map_type`), which names its Warcraft III test folder, e.g. `799X`.
        start_name: File name of the starting map, the complete map a build starts from.
        start_sha256: The starting map's SHA-256 (its contents are a released file, not in the repository).
        start_size: The starting map's size in bytes.
        stub_functions: Functions of the map script the build turns into no-ops (the map's own writers of the files
            the league addons write).
    """
    name: str
    family: str
    start_name: str
    start_sha256: str
    start_size: int
    stub_functions: tuple[str, ...] = ()

    @property
    def folder(self) -> Path:
        """The project folder."""
        return ROOT / 'projects' / self.name

    @property
    def src(self) -> Path:
        """The folder holding every file of the map."""
        return self.folder / 'src'

    @property
    def addons(self) -> Path:
        """The map's own league addons (`*.j`, `anchors.txt`, `imports/`)."""
        return self.folder / 'addons'

    @property
    def binaries(self) -> Path:
        """The list of the map's binary files: name -> SHA-256 and size."""
        return self.folder / 'binaries.json'


def projects() -> dict[str, Project]:
    """Reads every project under projects/.

    Returns:
        The projects by folder name, sorted.
    """
    found = {}
    for meta in sorted((ROOT / 'projects').glob('*/project.json')):
        data = json.loads(meta.read_text(encoding='utf-8'))
        start = data['start_map']
        found[meta.parent.name] = Project(meta.parent.name, data['map_type'], start['name'], start['sha256'],
                                          start['size'], tuple(data.get('stub_functions', ())))
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
