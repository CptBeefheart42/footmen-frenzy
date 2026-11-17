"""The hotkey list of a map (projects/<map>/hotkeys.csv): every hotkey and command-card button position its ability and
unit data stores, and the clashes on a unit's command card (two visible abilities on one button or one hotkey).

`ff check` fails when the object data no longer matches the list, so a hotkey a new map version drops, a moved button or
a new clash shows up in review. After an intended change, `ff hotkeys <map>` rewrites the list; its diff shows what
changed.

Rows: `A,<ability>,<field>,<value>`, `U,<unit>,<field>,<value>` and `C,<unit>,pos|key,<where>,<abilities>`.
"""
from __future__ import annotations

import re
from pathlib import Path

from repo import Project

ABILITY_FIELDS = ('ahky', 'auhk', 'arhk', 'abpx', 'abpy', 'aubx', 'auby', 'arpx', 'arpy')
UNIT_FIELDS = ('uhot', 'ubpx', 'ubpy')
HEADER = ('# Hotkey list (tools/ff/hotkeys.py): every hotkey and command-card position the map stores, and the clashes\n'
          '# on a unit\'s command card (C rows). `ff check` fails on any difference; `ff hotkeys <map>` rewrites it after\n'
          '# an intended change. Rows: A,ability,field,value / U,unit,field,value / C,unit,pos|key,where,abilities\n')

OBJECT = re.compile(r'^\[(\S+?)(?: : \S+)?\]')
CELL = re.compile(r'^([A-Za-z0-9]{4})(?:\.(\d+)\.(\d+))? (int|real|unreal|string) = (.*)$')
TRIGSTR = re.compile(r'^TRIGSTR_0*(\d+)$')
ESCAPES = {'"': '"', '\\': '\\', 'n': '\n', 'r': '\r', 't': '\t'}


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


def read_objects(path: Path) -> dict[str, dict[str, str]]:
    """The level-0 cells of one object-data text file: object code -> field -> value as text."""
    objects: dict[str, dict[str, str]] = {}
    cells: dict[str, str] = {}
    if not path.is_file():
        return objects
    for line in path.read_text(encoding='utf-8').splitlines():
        header = OBJECT.match(line)
        if header:
            cells = objects.setdefault(header.group(1), {})
            continue
        cell = CELL.match(line)
        if not cell or (cell.group(2) not in (None, '0')):
            continue
        field, kind, rest = cell.group(1), cell.group(4), cell.group(5)
        cells[field] = unquote(rest)[0] if kind == 'string' else rest.split()[0]
    return objects


def read_strings(wts: Path) -> dict[int, str]:
    """The map's string table (war3map.wts): number -> text."""
    if not wts.is_file():
        return {}
    text = wts.read_text(encoding='utf-8-sig')
    return {int(n): body for n, body in re.findall(r'STRING (\d+)[^\n]*\n(?://[^\n]*\n)?\{\n(.*?)\n\}', text, re.S)}


def merged(project: Project, ext: str, strings: dict[int, str]) -> dict[str, dict[str, str]]:
    """Object code -> field -> value of one object type, the main file first and its war3mapSkin twin over it."""
    result: dict[str, dict[str, str]] = {}
    for name in (f'war3map.{ext}.txt', f'war3mapSkin.{ext}.txt'):
        for code, cells in read_objects(project.objects / name).items():
            target = result.setdefault(code, {})
            for field, value in cells.items():
                ref = TRIGSTR.match(value)
                if ref:
                    value = strings.get(int(ref.group(1)), value)
                target[field] = value.replace(',', ';').replace('\r', '').replace('\n', '|n')
    return result


def rows(project: Project) -> list[str]:
    """The hotkey list of `project`, sorted."""
    strings = read_strings(project.src / 'war3map.wts')
    abilities = merged(project, 'w3a', strings)
    units = merged(project, 'w3u', strings)
    out = [f'A,{code},{f},{cells[f]}' for code, cells in abilities.items() for f in ABILITY_FIELDS if f in cells]
    for code, cells in units.items():
        out += [f'U,{code},{f},{cells[f]}' for f in UNIT_FIELDS if f in cells]
        on_card = []
        for field in ('uabi', 'uhab'):
            for a in cells.get(field, '').split(';'):
                if len(a) >= 3 and a in abilities and a not in on_card:
                    on_card.append(a)
        out += clashes(code, 'pos', {a: f"{abilities[a]['abpx']}/{abilities[a]['abpy']}" for a in on_card
                                     if 'abpx' in abilities[a] and 'abpy' in abilities[a] and abilities[a]['abpy'] != '-11'})
        out += clashes(code, 'key', {a: abilities[a]['ahky'].upper() for a in on_card if abilities[a].get('ahky')})
    return sorted(out)


def clashes(unit: str, kind: str, where: dict[str, str]) -> list[str]:
    """`C` rows for the places (button positions or hotkeys) two or more of `unit`'s abilities share."""
    groups: dict[str, list[str]] = {}
    for ability, place in where.items():
        groups.setdefault(place, []).append(ability)
    return [f'C,{unit},{kind},{place},{" ".join(sorted(names))}' for place, names in groups.items() if len(names) > 1]


def list_file(project: Project) -> Path:
    """The project's committed hotkey list."""
    return project.folder / 'hotkeys.csv'


def write(project: Project) -> Path:
    """Rewrites the project's hotkey list from its object data; returns the file."""
    path = list_file(project)
    path.write_text(HEADER + '\n'.join(rows(project)) + '\n', encoding='utf-8', newline='\n')
    return path


def differences(project: Project, committed_list: Path | None = None) -> list[str]:
    """Rows only in the committed list (`-`) or only in the object data (`+`); empty when they match.

    Args:
        project: The map project.
        committed_list: Another list to compare with (default: the project's hotkeys.csv).
    """
    path = committed_list or list_file(project)
    committed = {line for line in path.read_text(encoding='utf-8').splitlines() if line and not line.startswith('#')} \
        if path.is_file() else set()
    current = set(rows(project))
    return [f'- {r}' for r in sorted(committed - current)] + [f'+ {r}' for r in sorted(current - committed)]
