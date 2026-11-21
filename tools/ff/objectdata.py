"""Reads a map's object data as text (projects/<map>/objects/*.txt, or `runner objects export` of a built map).

One text file per object-data file (tools/runner/ObjectText.cs has the format):

    [A0KF : AFv1]                 a new object (its id : the object it is based on); [hfoo] changes a stock object
    acdn.1.0 real = 12.5          field.level.pointer (abilities, upgrades, doodads)
    unam string = "Footman" @0    field (units, items, buffs, destructables)

Text after # is a comment, `end = ...` and `unk = ...` lines are storage details this reader skips.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

OBJECT = re.compile(r'^\[(\S+?)(?: : (\S+))?\]')
CELL = re.compile(r'^([A-Za-z0-9]{4})(?:\.(\d+)\.(\d+))? (int|real|unreal|string) = (.*)$')
ESCAPES = {'"': '"', '\\': '\\', 'n': '\n', 'r': '\r', 't': '\t'}


@dataclass(frozen=True)
class Cell:
    """One stored value of an object.

    Attributes:
        field: The four-character field id, e.g. `acdn`.
        level: The ability or upgrade level (doodads: the variation); 0 for types without levels.
        pointer: The data pointer (which `Data` column of an ability); 0 for types without levels.
        kind: `int`, `real`, `unreal` or `string`.
        value: The value: an int, a float or the unescaped text.
    """
    field: str
    level: int
    pointer: int
    kind: str
    value: int | float | str


@dataclass
class ObjectRecord:
    """One object of an object-data file: its id, the object it is based on (itself for a changed stock object) and
    its cells in file order."""
    code: str
    parent: str
    cells: list[Cell] = field(default_factory=list)


def unquote(text: str) -> tuple[str, str]:
    """Reads a quoted string literal at the start of `text`; returns its value and the rest of the line."""
    out, i = [], 1
    while text[i] != '"':
        if text[i] == '\\':
            i += 1
            if text[i] == 'u':
                out.append(chr(int(text[i + 1:i + 5], 16)))
                i += 4
            else:
                out.append(ESCAPES[text[i]])
        else:
            out.append(text[i])
        i += 1
    return ''.join(out), text[i + 1:]


def parse_value(kind: str, text: str) -> int | float | str:
    """The value of a cell from the text after `=`: a quoted string, an integer or a decimal."""
    if kind == 'string':
        return unquote(text)[0]
    number = text.split()[0]
    return int(number) if kind == 'int' else float(number)


def read(path: Path) -> list[ObjectRecord]:
    """Every object of one object-data text file, in file order; an empty list when the file does not exist."""
    records: list[ObjectRecord] = []
    if not path.is_file():
        return records
    for line in path.read_text(encoding='utf-8').splitlines():
        header = OBJECT.match(line)
        if header:
            records.append(ObjectRecord(header.group(1), header.group(2) or header.group(1)))
            continue
        cell = CELL.match(line)
        if cell and records:
            field_id, level, pointer, kind, rest = cell.groups()
            records[-1].cells.append(Cell(field_id, int(level or 0), int(pointer or 0), kind, parse_value(kind, rest)))
    return records
