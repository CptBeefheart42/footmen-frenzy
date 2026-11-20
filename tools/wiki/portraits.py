"""Resolve in-game command art, preferring map imports over the installed game."""
from base64 import b64encode
from contextlib import ExitStack
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PureWindowsPath
import struct

from .import_game_data import GAME_LOCATION, game_reader


def decode(blob):
    from PIL import Image
    if blob[:4] == b"BLP1" and struct.unpack_from("<I", blob, 4)[0] == 1:
        depth, w, h = struct.unpack_from("<III", blob, 8)
        if depth not in (0, 1, 4, 8) or not 0 < w*h <= 4096**2:
            raise ValueError("Invalid palette image")
        offset = struct.unpack_from("<I", blob, 28)[0]
        size = w*h
        im = Image.frombytes("P", (w,h), blob[offset:offset+size])
        im.putpalette(blob[156:1180], "BGRX")
        im = im.convert("RGBA")
        if depth:
            alpha = blob[offset+size:]
            mask = (1 << depth)-1
            channel = bytes(((alpha[i*depth//8] >> (i*depth%8)) & mask)*255//mask for i in range(size))
            im.putalpha(Image.frombytes("L", im.size, channel))
    else:
        im = Image.open(BytesIO(blob)).convert("RGBA")
    im.thumbnail((96,96), Image.Resampling.LANCZOS)
    out = BytesIO()
    im.save(out, "WEBP", quality=88)
    return out.getvalue()


ART = {"units": ("uico","Art"), "items": ("iico","Art"), "upgrades": ("gar1","Art"),
       "abilities": ("aart","Art"), "effects": ("fart","Buffart")}


def art_path(key, objects):
    family = key.split("/")[0]
    if family not in ART:
        return None
    field, column = ART[family]
    seen = set()
    while key in objects and key not in seen:
        seen.add(key)
        obj = objects[key]
        for f in reversed(obj["fields"]):
            if f[0] == field and f[3]:
                return str(f[3]).split(",")[0].strip('" ')
        for row in reversed(list(obj["stock"].values())):
            columns = {k.casefold(): v for k,v in row.items()}
            for suffix in (":sd", "", ":de", ":hd"):
                val = columns.get(column.casefold()+suffix,"")
                if val.strip('" ') not in ("", "_", "-"):
                    return val.split(",")[0].strip('" ')
        key = family + "/" + obj["parent"]
    return None


def attach_portraits(db, read):
    images, paths = {}, {}
    with ExitStack() as stack:
        stock = None
        if GAME_LOCATION.exists():
            settings = json.loads(GAME_LOCATION.read_text())
            dll, game = Path(settings["dll"]), Path(settings["game"])
            if dll.is_file() and game.is_dir():
                stock = stack.enter_context(game_reader(dll, game))
        db["stock_art_loaded"] = stock is not None
        for key, obj in db["objects"].items():
            raw = art_path(key, db["objects"])
            if not raw:
                continue
            path = PureWindowsPath(raw)
            if path.drive or path.root or ".." in path.parts:
                continue
            obj["art_path"] = str(path)
            name = str(path).lower()
            if name not in paths:
                paths[name] = None
                variants = list(dict.fromkeys(str(path.with_suffix(s)) for s in (path.suffix, ".dds", ".blp", ".tga")))
                for source, reader in (("map", read), ("Warcraft", stock)):
                    if not reader:
                        continue
                    for filename in variants:
                        blob = reader(filename if source == "map" else "war3.w3mod:"+filename)
                        if not blob:
                            continue
                        try:
                            picture = decode(blob)
                        except (OSError, ValueError, IndexError, NotImplementedError, struct.error):
                            continue
                        digest = sha256(picture).hexdigest()[:24]
                        images[digest] = b64encode(picture).decode()
                        paths[name] = [digest, source, filename]
                        break
                    if paths[name]:
                        break
            if paths[name]:
                obj["art"], obj["art_source"], obj["art_file"] = paths[name]
    db["portraits"] = images
