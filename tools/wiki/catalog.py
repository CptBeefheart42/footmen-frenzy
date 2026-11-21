"""The wiki's object index: every object the map defines or reaches, with its name, links, stats and command keys.

Objects are keyed `<group>/<id>` (`units/E00A`, `abilities/A09T`). The index starts from the map's own objects and
every id the map's script, settings, placements and game constants name, then follows the references between objects
(ability lists, trained units, parents ...) until nothing new turns up.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from pathlib import Path

from .mapfiles import OBJECT_FILES, text
from .map_info import settings
from .placements import widgets

NAMES = {'units': 'unam', 'items': 'unam', 'abilities': 'anam', 'effects': 'fnam',
         'upgrades': 'gnam', 'destructibles': 'bnam', 'doodads': 'dnam'}
RAW = re.compile(r'(?<![\w])([A-Za-z0-9_]{4})(?![\w])')
COLOUR = re.compile(r'\|c[\da-fA-F]{8}|\|r')
REF_TYPES = {'abilCode', 'abilityList', 'abilitySkinList', 'heroAbilityList', 'unitList',
             'unitCode', 'unitSkinList', 'techList', 'upgradeList', 'upgradeCode', 'itemList',
             'buffList', 'effectList'}
NUMBER_TYPES = {'int', 'real', 'unreal'}
STAT_CATEGORIES = {'stats', 'data', 'combat', 'move', 'tech', 'path'}
NUMBER = re.compile(r'-?(?:\d+(?:\.\d*)?|\.\d+)')
COMMANDS = {'cast': ('Hotkey', 'Buttonpos', 'ahky', 'abpx', 'abpy'),
            'learn': ('Researchhotkey', 'Researchbuttonpos', 'arhk', 'arpx', 'arpy')}
PRESETS = json.loads((Path(__file__).with_name('reports.json')).read_text(encoding='utf-8'))


def load_objects(files, strings: dict[int, str]) -> dict[tuple[str, str], dict]:
    """The map's own objects: (group, id) -> {parent, fields: [(field, level, pointer, value, file)]}."""
    objects = {}
    for group in OBJECT_FILES:
        for uid, parent, cells in files.object_cells(group, strings):
            obj = objects.setdefault((group, uid), {'fields': []})
            obj['fields'].extend(cells)
            if parent != uid or 'parent' not in obj:
                obj['parent'] = parent
    return objects


def lineage(group: str, uid: str, objects: dict) -> list[str]:
    """An object and the objects it is based on, the object first."""
    chain, parent = [], uid
    while parent not in chain:
        chain.append(parent)
        parent = objects.get((group, parent), {}).get('parent', parent)
    return chain


def targets(value, known: set[str], allow_ids: bool) -> set[str]:
    """The known object ids a value refers to: a comma list of ids (when the field holds ids) and tooltip
    references like `<A001,DataA1>`; ordinary text is not read as ids."""
    if not isinstance(value, str):
        return set()
    ids = {v.strip() for v in value.split(',')} if allow_ids else set()
    ids.update(re.findall(r'<(\w{4}),', value))
    return ids & known


def ability_command(uid: str, objects: dict, stock: dict, custom: bool) -> dict:
    """An ability's command-card hotkey and button position, for casting and for learning (`cast`, `learn`).

    The game's row of each ancestor comes first, the map's fields over it; x and y can each be overridden alone.
    """
    chain = lineage('abilities', uid, objects)
    result = {}
    for mode, columns in COMMANDS.items():
        values = {}
        for ancestor in reversed(chain):
            values.update(stock_command(stock.get(('abilities', ancestor), {}), columns, custom))
            values.update(map_command(objects.get(('abilities', ancestor), {}), columns))
        command = {axis: int(str(values[axis]).strip()) for axis in ('x', 'y')
                   if re.fullmatch(r'-?\d+', str(values.get(axis, '')).strip())}
        key = str(values.get('key', '')).strip(' "')
        if key and key not in ('_', '-'):
            command['key'] = key.upper()
        if command:
            result[mode] = command
    return result


def stock_command(rows: dict, columns: tuple, custom: bool) -> dict:
    """The hotkey (`key`) and button position (`x`, `y`) an ability's game rows give."""
    hotkey, position = columns[0].casefold(), columns[1].casefold()
    values = {}
    for source, row in rows.items():
        if source.startswith('custom_v1/') and not custom:
            continue
        for column, value in row.items():
            if column.casefold() == hotkey:
                values['key'] = value
            elif column.casefold() == position:
                values.update(zip(('x', 'y'), value.split(',')))
    return values


def map_command(obj: dict, columns: tuple) -> dict:
    """The hotkey and button position fields an ability stores in the map."""
    names = dict(zip(columns[2:], ('key', 'x', 'y')))
    return {names[f[0]]: f[3] for f in obj.get('fields', []) if f[0] in names}


class Catalog:
    """Builds the index of one map (see the module docstring)."""

    def __init__(self, files, stock):
        self.files = files
        self.strings = files.strings()
        self.objects = load_objects(files, self.strings)
        self.stock = stock
        self.custom = False

    def build(self, script) -> dict:
        """The index: objects, script functions, settings, placements, models, recipes and unresolved ids."""
        info_data = self.files.read('war3map.w3i')
        info = settings(info_data) if info_data else {}
        self.custom = info.get('game_data_set') == 1
        placements = []
        for entry in ('war3mapUnits.doo', 'war3map.doo'):
            data = self.files.read(entry)
            if data is not None:
                placements.extend(widgets(data, entry))
        config = self.stock.config
        for filename in ('war3mapMisc.txt', 'war3mapExtra.txt', 'war3mapSkin.txt'):
            blob = self.files.read(filename)
            if blob is not None:
                config[filename] = text(blob)
        catalog = self.reach(script, info, placements, config)
        for key, obj in catalog.items():
            self.describe(key, obj)
        return {'objects': catalog, 'functions': script.functions, 'globals': script.outside, 'config': config,
                'wts': self.strings, 'metadata': self.stock.meta, 'game': self.stock.manifest,
                'placements': placements, 'settings': info, 'creation_paths': script.creation_paths,
                'models': model_index(catalog, script.functions), 'recipes': script.recipes(),
                'unresolved': sorted(set(script.by_id) - self.known())}

    def kinds(self) -> dict[str, set[str]]:
        """Object id -> the groups it exists in (the map's and the game's objects)."""
        kinds = defaultdict(set)
        for group, uid in self.stock.stock.keys() | self.objects.keys():
            kinds[uid].add(group)
        return kinds

    def known(self) -> set[str]:
        """Every object id of the map and the game."""
        return set(self.kinds())

    def reach(self, script, info: dict, placements: list, config: dict) -> dict:
        """Every object the map defines or reaches (breadth-first along references), with its entry."""
        kinds = self.kinds()
        known = set(kinds)
        placed_refs, seeds = placement_refs(placements)
        seeds |= set(script.by_id)
        seeds.update(RAW.findall(json.dumps(info)))
        for _, line in script.outside:
            seeds.update(re.findall(r"'(\w{4})'", line))
        for body in config.values():
            seeds.update(RAW.findall(body))
        queue = deque(self.objects)
        for uid in sorted(seeds & known):
            queue.extend((group, uid) for group in sorted(kinds[uid]))
        ref_columns = {group: {f.get('field', '').lower() for f in fields.values() if f.get('type') in REF_TYPES}
                       for group, fields in self.stock.meta.items()}
        catalog = {}
        while queue:
            group, uid = queue.popleft()
            key = group + '/' + uid
            if key in catalog:
                continue
            catalog[key] = self.entry(group, uid, known, placed_refs[uid], ref_columns, script.by_id)
            for ref in catalog[key]['refs']:
                queue.extend((g, ref) for g in sorted(kinds.get(ref, ())))
        return catalog

    def entry(self, group: str, uid: str, known: set, placed: set, ref_columns: dict, by_id: dict) -> dict:
        """One object's entry: id, group (heroes, buildings and units apart), name, parent, fields, game rows, refs."""
        obj = self.objects.get((group, uid), {})
        parent = obj.get('parent', uid)
        fields = obj.get('fields', [])
        defaults = self.stock.stock.get((group, uid), {})
        rows = defaults or self.stock.stock.get((group, parent), {})
        refs = defaultdict(set)
        for target in placed:
            refs[target].add('Placed instance inventory, ability or random table')
        for field, level, pointer, value, entry in fields:
            details = self.stock.meta.get(group, {}).get(field, {})
            for ref in targets(value, known, not details or details.get('type') in REF_TYPES):
                refs[ref].add(f'{details.get("label", field)} · {entry} {field} [{level}, {pointer}]')
        for source, row in defaults.items():
            for column, value in row.items():
                base_column = re.sub(r'\d+$', '', column.lower())
                allow = base_column in ref_columns.get(group, ()) or base_column in {'code', 'requires', 'trains'}
                for ref in targets(value, known, allow) - {uid}:
                    refs[ref].add(f'{source} {column}')
        if parent != uid:
            refs[parent].add('Parent object')
        return dict(id=uid, group=category(group, uid, fields, rows), name=self.name(group, uid, fields, rows),
                    parent=parent, fields=fields, stock=defaults,
                    refs={i: sorted(v) for i, v in sorted(refs.items()) if i != uid},
                    functions=sorted(by_id.get(uid, ())), defined=(group, uid) in self.objects)

    def name(self, group: str, uid: str, fields: list, rows: dict) -> str:
        """An object's display name: the map's name field, else the game row's, else its id; colour codes removed."""
        name = next((f[3] for f in reversed(fields) if f[0] == NAMES[group] and f[3]), None)
        if not name:
            name = next((row[k] for row in reversed(list(rows.values()))
                         for k in ('Name', 'name', 'comments', 'comment(s)') if row.get(k) not in (None, '', '_')), uid)
        return COLOUR.sub('', self.stock.labels.get(name, str(name))).strip('"')

    def describe(self, key: str, obj: dict) -> None:
        """Adds an object's `command` (abilities), `linked_fields`, `stats` and `visuals` (model files)."""
        group, uid = key.split('/', 1)
        numeric, primary = self.stat_fields(group)
        if group == 'abilities':
            obj['command'] = ability_command(uid, self.objects, self.stock.stock, self.custom)
        visuals = []
        obj['linked_fields'], obj['stats'] = self.resolved_fields(group, uid, numeric, visuals)
        obj['visuals'] = sorted(set(visuals))
        for stat in obj['stats']:
            if stat['field'] not in primary:
                stat['additional'] = True

    def stat_fields(self, group: str) -> tuple[dict[str, str], set[str]]:
        """The number fields shown as stats of a group (field -> label), and the main ones among them."""
        meta = self.stock.meta.get(group, {})
        numeric = {k: v for k, v in PRESETS.get(group, {}).get('fields', {}).items()
                   if meta.get(k, {}).get('type') in NUMBER_TYPES}
        if group == 'abilities':
            numeric.update({k: m['label'] for k, m in meta.items()
                            if m.get('type') in NUMBER_TYPES and (m.get('field') == 'Data' or k == 'alev')})
        if group == 'units':
            numeric.update({'ua1d': 'Damage dice', 'ua1s': 'Sides per die', 'ua1r': 'Attack range'})
        primary = set(numeric)
        for field, spec in meta.items():
            if spec.get('type') not in NUMBER_TYPES or spec.get('category') not in STAT_CATEGORIES:
                continue
            label = spec['label']
            if group == 'upgrades' and field[:3] in {'gba', 'gmo'}:
                label = f'Effect {field[-1]} ' + ('base value' if field.startswith('gba') else 'increment per level')
                primary.add(field)
            numeric.setdefault(field, label)
        return numeric, primary

    def field_specs(self, group: str, chain: list[str], numeric: dict) -> dict:
        """The metadata of the fields the wiki resolves for an object: references, stats and art models."""
        seen = set(chain)
        prefix = {'items': 'i', 'units': 'u'}.get(group)
        return {k: m for k, m in self.stock.meta.get(group, {}).items()
                if (m.get('type') in REF_TYPES or k in numeric
                    or m.get('type') in {'model', 'modelList'} and m['field'].lower().endswith('art'))
                and (not prefix or k.startswith(prefix))
                and (not m.get('useSpecific') or seen.intersection(m['useSpecific'].split(',')))}

    def resolved_fields(self, group: str, uid: str, numeric: dict, visuals: list) -> tuple[list, list]:
        """An object's reference fields (`linked_fields`) and stats with their final values per level and pointer.

        Each ancestor's game row comes first, then its map fields, so the object's own values win.
        """
        chain = lineage(group, uid, self.objects)
        specs = self.field_specs(group, chain, numeric)
        resolved = {}
        for ancestor in reversed(chain):
            resolved.update(self.stock_values(group, ancestor, specs))
            for field, lvl, ptr, value, entry in self.objects.get((group, ancestor), {}).get('fields', []):
                if field in specs:
                    slot = ptr or (int(specs[field].get('data', '0')) if specs[field]['field'] == 'Data' else 0)
                    resolved[field, lvl, slot] = (value, f'{entry} / {ancestor} / {field} [{lvl}, {ptr}]')
        return classify(resolved, specs, numeric, visuals)

    def stock_values(self, group: str, ancestor: str, specs: dict) -> dict:
        """(field, level, pointer) -> (value, source) from an object's game rows."""
        values = {}
        for source, row in self.stock.stock.get((group, ancestor), {}).items():
            if source.startswith('custom_v1/') and not self.custom:
                continue
            table = Path(source).stem.lower() if source.endswith('.slk') else 'profile'
            for key, spec in specs.items():
                if spec.get('slk', '').lower() == table:
                    values.update(spec_values(key, spec, row, f'{source} / {ancestor} / '))
        return values


def spec_values(key: str, spec: dict, row: dict, where: str) -> dict:
    """The values one field's metadata finds in a game row: its column, or its numbered columns per level."""
    column, slot = spec['field'], 0
    if column == 'Data' and spec.get('data', '0').isdigit() and int(spec['data']) > 0:
        slot = int(spec['data'])
        column += chr(64 + slot)
    values = {}
    for col, val in row.items():
        if col.casefold() == column.casefold():
            values[key, 0, slot] = (val, where + col)
        elif spec.get('repeat', '0') != '0' and col.startswith(column) and col[len(column):].isdigit():
            values[key, int(col[len(column):]), slot] = (val, where + col)
    return values


def classify(resolved: dict, specs: dict, numeric: dict, visuals: list) -> tuple[list, list]:
    """Sorts resolved values into reference fields and stats; model paths go to `visuals`."""
    links, stats = [], []
    for (key, lvl, ptr), (value, source) in sorted(resolved.items()):
        if specs[key].get('type') in {'model', 'modelList'}:
            visuals.extend(p.strip().strip('"') for p in str(value).split(',')
                           if p.strip().lower().endswith(('.mdx', '.mdl')))
        elif key in numeric:
            if isinstance(value, (float, int)) or NUMBER.fullmatch(str(value)):
                stats.append(dict(field=key, label=numeric[key], level=lvl, pointer=ptr, value=value, source=source))
        elif isinstance(value, str):
            ids = [v.strip() for v in value.split(',') if re.fullmatch(r'\w{4}', v.strip())]
            if ids:
                label = {'uhab': 'Hero abilities', 'uabi': 'Unit abilities'}.get(key, specs[key]['label'])
                links.append(dict(field=key, label=label, level=lvl, pointer=ptr, ids=ids, source=source))
    return links, stats


def category(group: str, uid: str, fields: list, rows: dict) -> str:
    """The wiki group of an object: units split into heroes (capital first letter), buildings and units."""
    if group != 'units':
        return group
    building = {f[0]: f[3] for f in fields}.get('ubdg')
    if building is None:
        building = next((r['isbldg'] for r in reversed(list(rows.values())) if 'isbldg' in r), '0')
    return 'buildings' if str(building) == '1' else 'heroes' if uid[:1].isupper() else 'units'


def placement_refs(placements: list) -> tuple[dict[str, set], set]:
    """What placed objects carry (placed id -> item, ability and unit ids), and every id placements name."""
    refs, seeds = defaultdict(set), set()
    for rec in placements:
        seeds.add(rec['id'])
        for sub in [*rec.get('drop_sets', []), rec.get('inventory', []), rec.get('ability_settings', []),
                    rec.get('random_units', [])]:
            for values in sub:
                for name in ('item', 'ability', 'unit'):
                    if name in values:
                        refs[rec['id']].add(values[name])
                        seeds.add(values[name])
        if 'skin' in rec:
            seeds.add(rec['skin'])
    return refs, seeds


class ModelIndex:
    """Every model file the objects and the script use: lower-case .mdx path -> {path, uses: [[owner, source]]}."""

    def __init__(self):
        self.models: dict[str, dict] = {}

    def add(self, path: str, owner: str, source: str) -> None:
        """Records one use of a model file (anything not ending in .mdl or .mdx is skipped)."""
        path = path.strip().strip('"').replace('\\\\', '\\').replace('/', '\\')
        if not path.lower().endswith(('.mdl', '.mdx')):
            return
        key = re.sub(r'\.mdl$', '.mdx', path.lower())
        self.models.setdefault(key, {'path': path, 'uses': []})['uses'].append([owner, source])

    def add_values(self, value, owner: str, source: str) -> None:
        """Records the model files of a comma-separated field value."""
        if isinstance(value, str) and ('.mdl' in value.lower() or '.mdx' in value.lower()):
            for path in value.split(','):
                self.add(path, owner, source)

    def add_object(self, key: str, obj: dict) -> None:
        """Records the model files of an object's map fields and game rows."""
        for field, level, ptr, value, entry in obj['fields']:
            self.add_values(value, key, f'{entry} / {field} [{level}, {ptr}]')
        for src, row in obj['stock'].items():
            for column, value in row.items():
                self.add_values(value, key, f'{src} / {column}')

    def add_function(self, name: str, fn: dict) -> None:
        """Records the model files a script function names in string literals."""
        for delta, line in enumerate(fn['body'].splitlines()):
            for path in re.findall(r'"([^"\r\n]+\.(?:mdl|mdx))"', line, re.I):
                self.add(path, 'fn/' + name, 'war3map.j:' + str(fn['line'] + delta))


def model_index(catalog: dict, functions: dict) -> dict:
    """Every model file the objects and the script use: lower-case .mdx path -> {path, uses: [[owner, source]]}."""
    index = ModelIndex()
    for key, obj in catalog.items():
        index.add_object(key, obj)
    for name, fn in functions.items():
        index.add_function(name, fn)
    return index.models
