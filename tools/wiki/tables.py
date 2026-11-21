"""Tables the map's script fills at start: hero starting stats and troop spawn settings (`set udg_x[i] = ...`).

Which functions and arrays make up a table is listed in reports.json (`heroes`, `spawns`). Each cell keeps where its
value was set (`war3map.j:<line> / <function> / <array>[<index>]`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .catalog import COLOUR, PRESETS, lineage

SCRIPT_TABLES = ('heroes', 'spawns')
ASSIGNMENT = re.compile(r'set\s+(\w+)\s*\[(.+?)\]\s*=\s*(.+)')


@dataclass(frozen=True)
class Value:
    """A table cell: its value and where it comes from."""
    value: str | int | float
    source: str


def unit_names(objects: dict) -> dict[str, Value]:
    """Unit id -> its name as the map stores it (inherited from the unit it is based on), colour codes removed."""
    names = {}
    for group, uid in objects:
        if group != 'units':
            continue
        for ancestor in lineage('units', uid, objects):
            cells = [f for f in objects.get(('units', ancestor), {}).get('fields', []) if f[0] == 'unam' and not f[1]]
            if cells:
                field, _, _, value, entry = cells[-1]
                name = COLOUR.sub('', str(value)).replace('|n', ' ').strip()
                names[uid] = Value(name or uid, f'{entry} / {ancestor} / {field}')
                break
    return names


def parse_value(rhs: str, field: str, slots: dict, active: str, source: str) -> tuple:
    """The value of an assignment's right-hand side: an object id, a number, or an earlier cell of the same array.

    Raises:
        ValueError: Any other expression.
    """
    if re.fullmatch(r"'[^']{4}'", rhs):
        return rhs[1:-1], source
    if re.fullmatch(r'-?\d+', rhs):
        return int(rhs), source
    if re.fullmatch(r'-?(?:\d+\.\d*|\.\d+)', rhs):
        return float(rhs), source
    ref = re.fullmatch(re.escape(field) + r'\[(\d+)\]', rhs)
    prior = slots.get(int(ref[1]), {}).get(field) if ref else None
    if prior is None or f' / {active} / ' not in prior.source:
        raise ValueError(f'unsupported expression at {source}: {rhs}')
    return prior.value, f'{source} from {prior.source}'


def assignments(script: str, report: dict, arrays: set[str]) -> dict[int, dict[str, Value]]:
    """Index -> array -> value of the report functions' unconditional, fixed-index assignments.

    Raises:
        ValueError: A report function is missing, or assigns a report array under a condition or a computed index.
    """
    slots: dict[int, dict[str, Value]] = {}
    active, depth, seen = None, 0, set()
    for number, line in enumerate(script.splitlines(), 1):
        line = line.partition('//')[0].strip()
        if line.startswith('function '):
            name = line.split()[1]
            active = name if name in report['functions'] else None
            depth = 0
            seen.update([active] if active else [])
        elif line == 'endfunction':
            active = None
        elif active:
            depth += (line.startswith('if ') or line == 'loop') - (line in {'endif', 'endloop'})
            match = ASSIGNMENT.fullmatch(line)
            if not match or match[1] not in arrays:
                continue
            field, index, rhs = match.groups()
            source = f'war3map.j:{number} / {active} / {field}[{index}]'
            if depth or not index.strip().isdigit():
                raise ValueError(f'expected an unconditional, fixed-index assignment at {source}')
            slots.setdefault(int(index), {})[field] = Value(*parse_value(rhs, field, slots, active, source))
    missing = set(report['functions']) - seen
    if missing:
        raise ValueError(f'missing report functions: {", ".join(sorted(missing))}')
    return slots


def script_table(key: str, script: str, names: dict[str, Value]) -> dict:
    """One table (`heroes` or `spawns`): key, title, note, columns and rows of {value, source} cells."""
    report = PRESETS[key]
    identity, selected = report['identity'], list(report['fields'])
    rows = []
    for index, values in sorted(assignments(script, report, {identity, *selected}).items()):
        if identity in values:
            uid = values[identity]
            row = {'id': uid, 'name': names.get(uid.value, Value(uid.value, 'Object ID')),
                   'index': Value(index, uid.source)}
        else:
            row = {'index': Value(index, next(iter(values.values())).source)}
        row.update({field: values[field] for field in selected if field in values})
        rows.append(row)
    if not rows:
        raise ValueError(f'no rows for {key}')
    columns = {'id': 'ID', 'name': 'Name', 'index': 'Index'} | {f: report['fields'].get(f, f) for f in selected}
    return dict(key=key, title=report['title'], columns=columns,
                note='Literal values assigned by the map’s initialization functions. A dash marks an absent '
                     'assignment. Game modes and later triggers can change these settings.',
                rows=[{k: vars(row[k]) if k in row else None for k in columns} for row in rows])


def script_tables(script: str, objects: dict) -> tuple[list[dict], dict[str, str]]:
    """Every table the map's script supports, and why the others are missing (table key -> error)."""
    names = unit_names(objects)
    tables, errors = [], {}
    for key in SCRIPT_TABLES:
        try:
            tables.append(script_table(key, script, names))
        except ValueError as error:
            errors[key] = str(error)
    return tables, errors
