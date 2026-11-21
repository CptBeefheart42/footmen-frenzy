"""The wiki bundle of a map: the part of the index the league website's wiki shows, as one JSON file.

The website shows heroes, spells, units, items and upgrades; it never shows the map's script, string table,
placements or imports, so those stay out, and each object keeps only the properties the website reads. A bundle:

    {"schema": 1, "family": ..., "source": {"input": ..., "commit": ...}, "metadata": ..., "tables": [...],
     "trace": {...}, "objects": {...}, "models": {...}, "portraits": {...}}
"""
from __future__ import annotations

import gzip
import json
import os
import tempfile
from pathlib import Path

SCHEMA = 1
OBJECT_KEYS = ('id', 'group', 'name', 'parent', 'defined', 'art', 'command', 'linked_fields', 'stats')
STAT_KEYS = ('field', 'label', 'level', 'value', 'additional')
TEXT_FIELDS = {'unsf', 'utub', 'aub1', 'fube', 'gub1'}
TRACE_LEFT_OUT = ('functions', 'dynamic', 'unresolved')


def slim_object(obj: dict) -> dict:
    """The properties of one object the website reads: its links and stats, the tooltip fields and game tooltips."""
    out = {k: obj[k] for k in OBJECT_KEYS if k in obj}
    out['stats'] = [{k: s[k] for k in STAT_KEYS if k in s} for s in obj.get('stats', [])]
    out['fields'] = [list(f[:4]) for f in obj['fields'] if f[0] in TEXT_FIELDS]
    tips = {}
    for source, row in obj.get('stock', {}).items():
        tip = row.get('Ubertip') or row.get('Buffubertip')
        if tip:
            tips[source] = {'Ubertip': tip}
    out['stock'] = tips
    out['functions'] = []
    return out


def slim(index: dict, source: dict) -> dict:
    """The bundle of one map's full index: only objects the game reaches (or that they are based on or refer to).

    Args:
        index: The full index, with its `trace` and `portraits`.
        source: What the bundle was made from (`input`: the map, `commit`: the repository's commit).
    """
    trace = index['trace']
    keys = set(trace['via']) | set(trace['support']) | set(trace['parents'])
    for edges in trace['edges'].values():
        keys |= {e['to'] for e in edges}
    objects = {k: slim_object(index['objects'][k]) for k in sorted(keys) if k in index['objects']}
    art = {o.get('art') for o in objects.values()}
    return {'schema': SCHEMA, 'family': index['family'], 'source': source, 'metadata': index['metadata'],
            'tables': index['tables'], 'trace': {k: v for k, v in trace.items() if k not in TRACE_LEFT_OUT},
            'objects': objects, 'models': {k: v for k, v in index['models'].items() if k in trace['visuals']},
            'portraits': {k: v for k, v in index['portraits'].items() if k in art}}


def write(path: Path, data: bytes) -> Path:
    """Writes a file whole or not at all (a temporary file renamed over it), readable by everyone (0644)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(handle, 'wb') as out:
            out.write(data)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def save(bundle: dict, folder: Path, name: str) -> tuple[Path, Path]:
    """Writes `<name>.json` and its gzip copy `<name>.json.gz` (for servers that send it compressed)."""
    data = json.dumps(bundle, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return write(folder / f'{name}.json', data), write(folder / f'{name}.json.gz', gzip.compress(data, mtime=0))
