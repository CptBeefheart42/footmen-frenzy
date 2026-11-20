"""Every object-data cell stored with its field's type: a decimal field stored as the other decimal type (`real` where
Warcraft III expects `unreal`, or the reverse) reads as 0 in WC3 3.0, so a spell has no cooldown, no range, no
duration. The field types come from the game's metadata (data/object_fields.csv, column Type).

`ff check` fails on any such cell; `ff objects fix-types <map>` rewrites them with the field's type, values unchanged.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from repo import ROOT

DECIMAL = ('real', 'unreal')
CELL = re.compile(r'^([A-Za-z0-9]{4})((?:\.\d+\.\d+)?) (int|real|unreal|string) = ')
# object-data file extension -> the metadata kind of its fields
KINDS = {'w3a': 'ability', 'w3u': 'unit', 'w3t': 'item', 'w3b': 'destructable', 'w3d': 'doodad', 'w3h': 'buff',
         'w3q': 'upgrade'}


def field_types() -> dict[tuple[str, str], str]:
    """(kind, field) -> the metadata type (`unreal`, `int`, `string` ...), from data/object_fields.csv."""
    lines = (ROOT / 'data' / 'object_fields.csv').read_text(encoding='utf-8').splitlines()
    rows = csv.DictReader(line for line in lines if not line.startswith('#'))
    return {(r['Kind'], r['Field']): r['Type'] for r in rows}


def expected(types: dict, kind: str, field: str, stored: str) -> str | None:
    """The type a cell must be stored with when it is wrong, else None.

    Only decimal mix-ups are judged: a field whose metadata says real/unreal must use exactly that type, and a field of
    any other type must not use a decimal type. Skin files' fields may come from the skin metadata.
    """
    meta = types.get((kind, field)) or types.get(('skin', field))
    if not meta:
        return None
    if meta in DECIMAL:
        return meta if stored != meta else None
    if stored in DECIMAL:
        return 'int' if meta in ('int', 'bool') else None
    return None


def mismatches(objects: Path) -> list[tuple[Path, int, str, str, str]]:
    """Every wrongly typed cell in a map's object files (projects/<map>/objects).

    Returns:
        (file, line number, field, stored type, expected type) per cell.
    """
    types = field_types()
    found = []
    for path in sorted(objects.glob('*.txt')):
        kind = KINDS.get(path.name.removesuffix('.txt').rsplit('.', 1)[-1])
        if not kind:
            continue
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            cell = CELL.match(line)
            if cell:
                want = expected(types, kind, cell.group(1), cell.group(3))
                if want and want in DECIMAL:
                    found.append((path, number, cell.group(1), cell.group(3), want))
    return found


def fix(objects: Path) -> int:
    """Rewrites every wrongly typed decimal cell in a map's object files with its field's type (values unchanged).

    Returns:
        How many cells were rewritten.
    """
    by_file: dict[Path, dict[int, str]] = {}
    for path, number, _, stored, want in mismatches(objects):
        by_file.setdefault(path, {})[number] = want
    count = 0
    for path, lines_to_fix in by_file.items():
        lines = path.read_text(encoding='utf-8').split('\n')
        for number, want in lines_to_fix.items():
            line = lines[number - 1]
            field, rest = line.split(' ', 1)
            stored, tail = rest.split(' ', 1)
            new = f'{field} {want} {tail}'
            column = line.find('  #')
            if column >= 0:  # keep the comment where it was
                head, comment = new[:new.find('  #')].rstrip(), new[new.find('  #'):].lstrip()
                new = head.ljust(max(column + 2, len(head) + 1)) + comment
            lines[number - 1] = new
            count += 1
        path.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    return count
