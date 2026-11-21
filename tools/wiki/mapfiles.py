"""The files of a built map the wiki reads, and the map's string table.

`ff build <map>` leaves everything the wiki needs under build/<map>/: the map's files as packed (`sources/`), and the
finished map, whose object data (after the WC3 3.0 level fill and the map fixes) and script are what the game loads.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import objectdata

OBJECT_FILES = {'units': 'w3u', 'items': 'w3t', 'abilities': 'w3a', 'effects': 'w3h',
                'upgrades': 'w3q', 'destructibles': 'w3b', 'doodads': 'w3d'}
WTS_ENTRY = re.compile(
    r'(?m)(?P<header>^STRING[ \t]+(?P<id>\d+)[^\n]*\n'
    r'(?:(?![ \t]*(?:\{|STRING[ \t]+\d+))[^\n]*\n)*[ \t]*\{[ \t]*\r?\n)'
    r'(?P<body>[\s\S]*?)(?P<footer>(?:\r?\n)?^\}[ \t]*\r?$)')
TRIGSTR = re.compile(r'TRIGSTR_(\d+)')


def text(data: bytes) -> str:
    """A map or game text file as text: UTF-8 (with or without BOM), else Windows-1252."""
    try:
        return data.decode('utf-8-sig')
    except UnicodeDecodeError:
        return data.decode('cp1252')


def string_table(data: bytes) -> dict[int, str]:
    """The entries of a string table (war3map.wts): number -> text.

    Raises:
        ValueError: An entry is incomplete or declared twice.
    """
    source = text(data)
    entries = {int(m['id']): m['body'].replace('\r\n', '\n') for m in WTS_ENTRY.finditer(source)}
    declared = re.findall(r'(?m)^STRING[ \t]+(\d+)\b', source)
    if len(entries) != len(declared):
        missing = set(map(int, declared)) - entries.keys()
        raise ValueError(f'war3map.wts: incomplete or duplicate entries, missing {sorted(missing)[:12]}')
    return entries


@dataclass(frozen=True)
class MapFiles:
    """A built map's files.

    Attributes:
        sources: The map's files as packed (build/<map>/sources).
        objects: The finished map's object data as text (`runner objects export`).
        script: The finished map's script.
    """
    sources: Path
    objects: Path
    script: Path

    def read(self, name: str) -> bytes | None:
        """A file of the map by its name in the archive (`war3mapImported\\x.blp`); None when it has none."""
        path = (self.sources / name.replace('\\', '/')).resolve()
        if not path.is_relative_to(self.sources.resolve()) or not path.is_file():
            return None
        return path.read_bytes()

    def strings(self) -> dict[int, str]:
        """The map's string table."""
        return string_table(self.read('war3map.wts') or b'')

    def jass(self) -> str:
        """The finished map script."""
        return text(self.script.read_bytes())

    def object_cells(self, group: str, strings: dict[int, str]):
        """Every object of one group in the order the game reads them: the skin file, then the main file.

        Args:
            group: `units`, `items`, `abilities`, `effects`, `upgrades`, `destructibles` or `doodads`.
            strings: The string table, to resolve TRIGSTR_ references.

        Yields:
            (object id, parent id, [(field, level, pointer, value, file)]) per object.
        """
        for prefix in ('war3mapSkin', 'war3map'):
            entry = f'{prefix}.{OBJECT_FILES[group]}'
            for record in objectdata.read(self.objects / f'{entry}.txt'):
                yield record.code, record.parent, [
                    (c.field, c.level, c.pointer, resolve(c.value, strings), entry) for c in record.cells]


def resolve(value, strings: dict[int, str]):
    """A cell value with a TRIGSTR_ reference replaced by its text from the string table."""
    if isinstance(value, str):
        ref = TRIGSTR.fullmatch(value)
        if ref and int(ref[1]) in strings:
            return strings[int(ref[1])]
    return value
