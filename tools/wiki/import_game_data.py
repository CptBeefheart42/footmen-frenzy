"""Cache Warcraft III stock data and editor metadata for offline wiki exports."""
import argparse
import ctypes as c
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from tempfile import NamedTemporaryFile


ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "build/wiki-game-data.zip"
GAME_LOCATION = ROOT / "build/wiki-game-location.json"
TABLES = {
    "units": ["unitdata", "unitui", "unitbalance", "unitabilities", "unitweapons"],
    "items": ["itemdata"], "abilities": ["abilitydata"], "effects": ["abilitybuffdata"],
    "upgrades": ["upgradedata"], "destructibles": ["destructabledata"], "doodads": ["doodads"],
}
META = {"units": "unitmetadata", "items": "unitmetadata", "abilities": "abilitymetadata",
        "effects": "abilitybuffmetadata", "upgrades": "upgrademetadata",
        "destructibles": "destructablemetadata", "doodads": "doodadmetadata"}


def game_files():
    for group, tables in TABLES.items():
        folder = "doodads" if group == "doodads" else "units"
        for table in [*tables, META[group]]:
            yield f"{folder}/{table}.slk"
    for race in ("common", "human", "orc", "undead", "nightelf", "neutral", "campaign", "item"):
        for kind in ("unit", "ability", "upgrade"):
            for suffix in ("func", "strings"):
                yield f"units/{race}{kind}{suffix}.txt"
    for name in ("itemfunc", "itemstrings", "unitskin", "itemskin", "abilityskin", "abilitybuffskin",
                 "abilitybuffstrings", "upgradeskin", "destructableskin", "miscdata"):
        yield f"units/{name}.txt"
    yield from ("ui/worldeditstrings.txt", "ui/worldeditgamestrings.txt", "ui/miscdata.txt")


@contextmanager
def game_reader(dll, game):
    lib = c.WinDLL(str(dll.resolve()), use_last_error=True)
    handle, uint = c.c_void_p, c.c_uint32
    for name, args in {
        "CascOpenStorage": [c.c_char_p, uint, c.POINTER(handle)],
        "CascOpenFile": [handle, c.c_char_p, uint, uint, c.POINTER(handle)],
        "CascReadFile": [handle, handle, uint, c.POINTER(uint)],
        "CascGetFileSize": [handle, c.POINTER(uint)],
        "CascCloseFile": [handle], "CascCloseStorage": [handle],
    }.items():
        fn = getattr(lib, name)
        fn.argtypes = args
        fn.restype = uint if name == "CascGetFileSize" else c.c_bool
    storage = handle()
    if not lib.CascOpenStorage(str(game.resolve()).encode(), 2, c.byref(storage)):
        raise ValueError(f"Cannot open game storage at {game}")
    def read(internal):
        fh = handle()
        if not lib.CascOpenFile(storage, internal.encode(), 2, 0, c.byref(fh)):
            if c.get_last_error() not in (2, 3):
                raise OSError(c.get_last_error(), f"Cannot read {internal}")
            return None
        try:
            size = lib.CascGetFileSize(fh, None)
            if size == 0xffffffff:
                raise ValueError(f"Invalid size for {internal}")
            buf = c.create_string_buffer(size)
            got = uint()
            if not lib.CascReadFile(fh, buf, size, c.byref(got)) or got.value != size:
                raise ValueError(f"Incomplete read of {internal}")
            return buf.raw
        finally:
            lib.CascCloseFile(fh)
    try:
        yield read
    finally:
        lib.CascCloseStorage(storage)


def make_cache(dll, game, target):
    with game_reader(dll, game) as read:
        files = {}
        for layer, prefix in [("base", ""), ("custom_v1", "_balance\\custom_v1.w3mod:"),
                              ("enUS", "_locales\\enus.w3mod:")]:
            for name in sorted(set(game_files())):
                internal = "war3.w3mod:" + prefix + name.replace("/", "\\")
                payload = read(internal)
                if payload is not None:
                    files[f"{layer}/{name}"] = payload
    if "base/units/unitbalance.slk" not in files:
        raise ValueError("Warcraft unit data missing from storage")
    build = (game / ".build.info").read_text(encoding="utf-8").splitlines()
    headers = [key.partition("!")[0] for key in build[0].split("|")]
    versions = [dict(zip(headers, line.split("|"))) for line in build[1:]]
    manifest = {"versions": [{"version": v.get("Version"), "build_key": v.get("Build Key")}
                             for v in versions if v.get("Active") == "1"],
                "files": {k: sha256(v).hexdigest() for k, v in files.items()}}
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
        path = Path(tmp.name)
    try:
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
            archive.writestr("manifest.json", json.dumps(manifest))
        path.replace(target)
    finally:
        path.unlink(missing_ok=True)
    print(f"{target} ({len(files)} source tables and profiles)")
    GAME_LOCATION.write_text(json.dumps({"dll": str(dll.resolve()), "game": str(game.resolve())}))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--game", type=Path, required=True)
    cli.add_argument("--dll", type=Path, required=True)
    args = cli.parse_args()
    make_cache(args.dll, args.game, CACHE)
