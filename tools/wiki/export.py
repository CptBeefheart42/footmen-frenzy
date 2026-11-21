"""`ff wiki`: the wiki bundles of the maps, for the league website.

    ff wiki <map>|all            build the map(s), then write build/wiki/<map>.json (+ .gz) and build/wiki/index.json
    ff wiki stock-pack <game>    write the stock pack from a local Warcraft III 2.0.4 install (maintainers)

A bundle is made from the finished map, so it shows what the game loads: the object data after the WC3 3.0 level
fill and the map fixes, and the script with the league addons. The game's own data comes from the stock pack
(wiki/stock.py), which `data/wiki_stock.json` names by checksum and the release store holds. `ff release` adds the
bundles to the release as Footmen_Frenzy_<version>-wiki.zip.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from . import bundle, stock
from .catalog import Catalog
from .mapfiles import MapFiles
from .portraits import attach_portraits
from .reachability import trace
from .script import ScriptIndex
from .tables import script_tables

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'ff'))

import blobs  # noqa: E402
import toolchain  # noqa: E402
from repo import BUILD, Project  # noqa: E402

PACK_LIST = ROOT / 'data' / 'wiki_stock.json'
OUT = BUILD / 'wiki'


def listed_pack() -> blobs.Blob:
    """The stock pack data/wiki_stock.json names."""
    listed = json.loads(PACK_LIST.read_text(encoding='utf-8'))
    return blobs.Blob(listed['sha256'], listed['size'])


def stock_pack() -> stock.StockPack | None:
    """The listed stock pack, downloaded into the blob cache; None when no release store is set up (contributors
    without access to it build no wiki)."""
    blob = listed_pack()
    if not blob.path.is_file() and not blobs.setting('blob_url', 'FF_BLOB_URL'):
        return None
    blobs.fetch([blob])
    return stock.StockPack(blob.path)


def commit() -> str:
    """The repository's current commit, short; `unknown` outside Git."""
    found = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    return found.stdout.strip() or 'unknown'


def map_files(project: Project, finished: Path) -> MapFiles:
    """The files of a finished map: its sources from the build, its object data exported as text, its script.

    Raises:
        RuntimeError: The object data could not be exported.
    """
    objects = finished.parent / 'wiki-objects'
    shutil.rmtree(objects, ignore_errors=True)
    if toolchain.run_dotnet_tool('tools/runner', ['objects', 'export', str(finished), str(objects)]) != 0:
        raise RuntimeError(f'could not export the object data of {finished.name}')
    return MapFiles(finished.parent / 'sources', objects, finished.with_suffix('.j'))


def has_pillow() -> bool:
    """Whether Pillow (the image library the icons need) is installed."""
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def index(files: MapFiles, pack: stock.StockPack, family: str) -> dict:
    """The full wiki index of one map: objects, script, tables, trace and portraits.

    Raises:
        toolchain.MissingTool: Pillow is not installed.
    """
    if not has_pillow():
        raise toolchain.MissingTool('the wiki needs Pillow for the icons: apt install python3-pil, or pip install pillow')
    data = stock.load(pack, files.read)
    script = ScriptIndex(files.jass())
    catalog = Catalog(files, data)
    result = catalog.build(script)
    result['family'] = family
    result['tables'], result['table_errors'] = script_tables(files.jass(), catalog.objects)
    result['trace'] = trace(result)
    attach_portraits(result, files.read, pack)
    return result


def export(project: Project, finished: Path, pack: stock.StockPack, out: Path = OUT) -> dict:
    """Writes the bundle of one finished map into `out`; returns its index.json entry ({id, title})."""
    full = index(map_files(project, finished), pack, project.family)
    result = bundle.slim(full, {'input': finished.name, 'commit': commit()})
    bundle.save(result, out, project.name)
    print(f'wiki {project.name}: {len(result["objects"])} objects, {len(result["portraits"])} pictures '
          f'-> {(out / project.name).with_suffix(".json")}')
    return {'id': project.name, 'title': project.family}


def write_index(entries: list[dict], out: Path = OUT) -> Path:
    """Writes index.json: the maps the bundles of `out` cover, in order."""
    return bundle.write(out / 'index.json', json.dumps(entries, ensure_ascii=False).encode('utf-8'))


def release_zip(entries: list[dict], target: Path, out: Path = OUT) -> Path:
    """Zips index.json and every bundle in `entries` (with its .gz copy) into `target`."""
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(out / 'index.json', 'index.json')
        for entry in entries:
            for suffix in ('.json', '.json.gz'):
                archive.write(out / (entry['id'] + suffix), entry['id'] + suffix)
    return target


def new_pack(game: Path) -> Path:
    """Writes a stock pack from a local install into the blob cache and lists it in data/wiki_stock.json."""
    temporary = blobs.CACHE / 'wiki-stock.part'
    manifest = stock.build_pack(game, temporary)
    digest, size = stock.pack_digest(temporary)
    temporary.replace(blobs.Blob(digest, size).path)
    listed = {'sha256': digest, 'size': size, 'versions': manifest['versions']}
    bundle.write(PACK_LIST, (json.dumps(listed, indent=1, sort_keys=True) + '\n').encode('utf-8'))
    return PACK_LIST
