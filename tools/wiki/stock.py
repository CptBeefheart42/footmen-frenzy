"""The Warcraft III stock data the wiki builds on: the game's object tables, editor metadata and command-button icons.

A map stores only what it changes, so names, base values, field labels and most icons come from the game. They are
collected once from a local Warcraft III 2.0.4 install into the stock pack (`ff wiki stock-pack`), a zip of:

- `<layer>/units/*.slk`, `<layer>/units/*.txt`, `<layer>/ui/*.txt`: the game's files of each layer (`base`, the
  `custom_v1` balance the maps load, and the `enUS` strings), as stored in the install;
- `portraits/<path>.webp`: every command-button icon, already shrunk to the wiki's size;
- `manifest.json`: the install's version and each file's SHA-256.

The pack holds Blizzard's files, so it lives only in the maintainers' private release store (tools/ff/blobs.py) and
never in Git; `data/wiki_stock.json` names it by checksum.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .mapfiles import text
from .portraits import UNREADABLE, decode

TABLES = {
    'units': ['unitdata', 'unitui', 'unitbalance', 'unitabilities', 'unitweapons'],
    'items': ['itemdata'], 'abilities': ['abilitydata'], 'effects': ['abilitybuffdata'],
    'upgrades': ['upgradedata'], 'destructibles': ['destructabledata'], 'doodads': ['doodads'],
}
META = {'units': 'unitmetadata', 'items': 'unitmetadata', 'abilities': 'abilitymetadata',
        'effects': 'abilitybuffmetadata', 'upgrades': 'upgrademetadata',
        'destructibles': 'destructablemetadata', 'doodads': 'doodadmetadata'}
LAYERS = (('base', ''), ('custom_v1', '_balance/custom_v1.w3mod:'), ('enUS', '_locales/enus.w3mod:'))
ICON_FOLDERS = ('replaceabletextures/commandbuttons/', 'replaceabletextures/passivebuttons/',
                'replaceabletextures/worldeditui/', 'ui/minimap/')
IMAGE_TYPES = ('.blp', '.dds', '.tga')
ART_COLUMNS = ('art', 'buffart', 'art:sd')


def game_files() -> list[str]:
    """The game's files the wiki reads (paths inside a layer, / separated)."""
    names = []
    for group, tables in TABLES.items():
        folder = 'doodads' if group == 'doodads' else 'units'
        names += [f'{folder}/{table}.slk' for table in [*tables, META[group]]]
    for race in ('common', 'human', 'orc', 'undead', 'nightelf', 'neutral', 'campaign', 'item'):
        for kind in ('unit', 'ability', 'upgrade'):
            names += [f'units/{race}{kind}{suffix}.txt' for suffix in ('func', 'strings')]
    names += [f'units/{name}.txt' for name in ('itemfunc', 'itemstrings', 'unitskin', 'itemskin', 'abilityskin',
                                               'abilitybuffskin', 'abilitybuffstrings', 'upgradeskin',
                                               'destructableskin', 'miscdata')]
    names += ['ui/worldeditstrings.txt', 'ui/worldeditgamestrings.txt', 'ui/miscdata.txt']
    return sorted(set(names))


def slk(data: bytes) -> dict[str, dict[str, str]]:
    """The rows of a SYLK table (the game's .slk files), by the value of their first column.

    Returns:
        Row id -> column name -> cell text.
    """
    header: dict[int, str] = {}
    rows: dict[int, dict[str, str]] = {}
    x = y = 0
    for line in text(data).splitlines():
        if not line.startswith('C;'):
            continue
        coords, sep, value = line.partition(';K')
        for part in coords.split(';')[1:]:
            if part.startswith('X'):
                x = int(part[1:])
            elif part.startswith('Y'):
                y = int(part[1:])
        if not sep:
            continue
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace('""', '"').replace(';;', ';')
        if y == 1:
            header[x] = value
        elif x in header:
            rows.setdefault(y, {})[header[x]] = value
    return {row[header[1]]: row for row in rows.values() if header[1] in row}


def ini(data: bytes) -> dict[str, dict[str, str]]:
    """The sections of an INI-style profile (the game's unit, ability and string .txt files).

    Returns:
        Section name -> key -> value.
    """
    section = ''
    sections: dict[str, dict[str, str]] = {}
    for line in text(data).splitlines():
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
        elif '=' in line and not line.startswith('//'):
            key, value = line.split('=', 1)
            sections.setdefault(section, {})[key.strip()] = value.strip()
    return sections


@dataclass
class StockData:
    """The game's data as the wiki uses it, with the map's own copies of game files applied.

    Attributes:
        stock: (group, object id) -> source file -> the object's row in that file.
        meta: group -> field id -> the field's editor metadata row, with its display `label`.
        config: source file -> text of the game constants (miscdata) and of profiles of the map's own objects.
        manifest: The pack's manifest (install version, file checksums); None without a pack.
        labels: Editor string id -> text (WESTRING_...).
    """
    stock: dict = field(default_factory=lambda: defaultdict(dict))
    meta: dict = field(default_factory=lambda: defaultdict(dict))
    config: dict = field(default_factory=dict)
    manifest: dict | None = None
    labels: dict = field(default_factory=dict)


class StockPack:
    """A stock pack on disk (see the module docstring), or none: then the wiki has only the map's own data."""

    def __init__(self, path: Path | None):
        self.path = path
        self._icons: dict[str, bytes] | None = None

    def files(self) -> tuple[dict[str, bytes], dict | None]:
        """The pack's game files by `<layer>/<path>`, checked against the manifest, and the manifest.

        Raises:
            ValueError: A file does not match its checksum.
        """
        if not self.path:
            return {}, None
        with zipfile.ZipFile(self.path) as pack:
            manifest = json.loads(pack.read('manifest.json'))
            files = {name: pack.read(name) for name in manifest['files']}
        for name, data in files.items():
            if hashlib.sha256(data).hexdigest() != manifest['files'][name]:
                raise ValueError(f'stock pack: {name} does not match its checksum')
        return files, manifest

    def icon(self, path: str) -> bytes | None:
        """The ready-made picture of a game image (`ReplaceableTextures\\CommandButtons\\BTNFoo.blp`), if packed."""
        if self._icons is None:
            self._icons = {}
            if self.path:
                with zipfile.ZipFile(self.path) as pack:
                    self._icons = {name[len('portraits/'):-len('.webp')]: pack.read(name)
                                   for name in pack.namelist() if name.startswith('portraits/')}
        return self._icons.get(path.replace('\\', '/').lower())


def load(pack: StockPack, read) -> StockData:
    """Reads the stock data: the pack's game files, then the map's own copies of game files on top.

    Args:
        pack: The stock pack.
        read: Reads a map file by name; None when the map has no such file.
    """
    sources, manifest = pack.files()
    for name in sorted(set(game_files()) | {'splats/lightningdata.slk'}):
        blob = read(name.replace('/', '\\'))
        if blob is not None:
            sources['map/' + name] = blob
    data = StockData(manifest=manifest)
    profiles = []
    for source, blob in sources.items():
        add_file(data, source, blob, profiles)
    add_profiles(data, profiles, sources)
    for fields in data.meta.values():
        for spec in fields.values():
            label = spec.get('displayName', '')
            spec['label'] = data.labels.get(label, spec.get('field', label)).strip('"')
    return data


def add_file(data: StockData, source: str, blob: bytes, profiles: list) -> None:
    """Adds one game file to the stock data by what it is: editor strings, game constants, field metadata, an object
    table, or a profile (collected in `profiles`, added once every table is in)."""
    filename = Path(source).stem.lower()
    if filename in {'worldeditstrings', 'worldeditgamestrings'}:
        for section in ini(blob).values():
            data.labels.update(section)
    elif filename in {'miscdata', 'lightningdata'}:
        data.config[source] = text(blob)
    elif filename in META.values():
        for group, table in META.items():
            if filename == table:
                data.meta[group].update(slk(blob))
    elif source.endswith('.slk'):
        group = next(k for k, tables in TABLES.items() if filename in tables)
        for uid, row in slk(blob).items():
            data.stock[group, uid][source] = row
    else:
        profiles.append((source, ini(blob)))


def add_profiles(data: StockData, profiles: list, sources: dict[str, bytes]) -> None:
    """Adds each profile section to the objects of that id; a map's profile of only its own objects goes to config."""
    kinds = defaultdict(set)
    for group, uid in data.stock:
        kinds[uid].add(group)
    for source, sections in profiles:
        for uid, row in sections.items():
            for group in kinds.get(uid, ()):
                data.stock[group, uid][source] = row
            if uid not in kinds and source.startswith('map/'):
                data.config.setdefault(source, text(sources[source]))


def build_pack(game: Path, target: Path) -> dict:
    """Writes a stock pack from a local Warcraft III install.

    Args:
        game: The install folder (with .build.info), a 2.0.4 one: the version the maps were made for.
        target: The pack file to write.

    Returns:
        The pack's manifest.

    Raises:
        ValueError: The install lacks the unit data.
    """
    casc = open_install(game)
    files = {}
    for layer, prefix in LAYERS:
        for name in game_files():
            blob = casc.get('war3.w3mod:' + prefix + name)
            if blob is not None:
                files[f'{layer}/{name}'] = blob
    if 'base/units/unitbalance.slk' not in files:
        raise ValueError(f'{game}: the Warcraft III unit data is missing')
    manifest = {'versions': install_versions(game), 'files': {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}}
    icons = {}
    for path in icon_paths(casc.names(), files):
        picture = decode_or_none(casc.get(path))
        if picture:
            icons[path.split(':', 1)[1]] = picture
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as pack:
        for name, blob in files.items():
            pack.writestr(fixed_entry(name), blob)
        for path, picture in sorted(icons.items()):
            pack.writestr(fixed_entry(f'portraits/{path}.webp'), picture)
        pack.writestr(fixed_entry('manifest.json'), json.dumps(manifest, sort_keys=True))
    return manifest


def fixed_entry(name: str) -> zipfile.ZipInfo:
    """A zip entry with a fixed date, so the same install always gives the same pack bytes (and checksum)."""
    entry = zipfile.ZipInfo(name, (2002, 7, 3, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_DEFLATED
    return entry


def icon_paths(names, files: dict[str, bytes]) -> list[str]:
    """The install's images to pack: the command-button folders and every image a game table names as art."""
    named = set()
    for name, blob in files.items():
        if name.endswith('.slk') or name.endswith('.txt'):
            rows = slk(blob).values() if name.endswith('.slk') else ini(blob).values()
            for row in rows:
                for column, value in row.items():
                    if column.casefold() in ART_COLUMNS:
                        named.update(PurePosixPath(p.strip('" ').replace('\\', '/').lower()).with_suffix('').as_posix()
                                     for p in value.split(',') if p.strip('" '))
    found = []
    for name in names:
        if not name.startswith('war3.w3mod:') or not name.endswith(IMAGE_TYPES):
            continue
        path = name.split(':', 1)[1]
        if path.startswith(ICON_FOLDERS) or path.rsplit('.', 1)[0] in named:
            found.append(name)
    return sorted(found)


def decode_or_none(blob: bytes | None) -> bytes | None:
    """The wiki picture of an image, or None when there is no image or Pillow cannot read it."""
    if not blob:
        return None
    try:
        return decode(blob)
    except UNREADABLE:
        return None


def install_versions(game: Path) -> list[dict]:
    """The active versions an install's .build.info lists (version and build key)."""
    lines = (game / '.build.info').read_text(encoding='utf-8').splitlines()
    headers = [key.partition('!')[0] for key in lines[0].split('|')]
    versions = [dict(zip(headers, line.split('|'))) for line in lines[1:] if line.strip()]
    return [{'version': v.get('Version'), 'build_key': v.get('Build Key')} for v in versions if v.get('Active') == '1']


class _Install:
    """Case-insensitive file access to a local install, through the repository's CASC reader."""

    def __init__(self, casc):
        self.casc = casc
        self.lower = {name.lower(): name for name in casc.files}

    def names(self) -> list[str]:
        """Every file name in the install, lower case."""
        return list(self.lower)

    def get(self, name: str) -> bytes | None:
        """The bytes of one file, by name in any case; None when the install has no such file."""
        key = self.lower.get(name.replace('\\', '/').lower())
        return self.casc.read(key) if key else None


def open_install(game: Path) -> _Install:
    """Opens a local Warcraft III install with tools/slk/extract_ability_defaults.py's CASC reader."""
    import sys
    slk_tools = str(Path(__file__).resolve().parents[1] / 'slk')
    if slk_tools not in sys.path:
        sys.path.insert(0, slk_tools)
    from extract_ability_defaults import Casc
    return _Install(Casc(str(game)))


def pack_digest(path: Path) -> tuple[str, int]:
    """The SHA-256 and size of a pack file, as data/wiki_stock.json lists it."""
    blob = path.read_bytes()
    return hashlib.sha256(blob).hexdigest(), len(blob)

