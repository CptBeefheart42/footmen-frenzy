"""Each object's icon as a small picture: the map's imported image first, else the game's (from the stock pack)."""
from __future__ import annotations

import struct
from base64 import b64encode
from hashlib import sha256
from io import BytesIO
from pathlib import PureWindowsPath

ART = {'units': ('uico', 'Art'), 'items': ('iico', 'Art'), 'upgrades': ('gar1', 'Art'),
       'abilities': ('aart', 'Art'), 'effects': ('fart', 'Buffart')}
SIZE = 96
UNREADABLE = (OSError, ValueError, IndexError, NotImplementedError, struct.error)


def decode(blob: bytes) -> bytes:
    """An image file of the game or a map (BLP, DDS, TGA ...) as a WebP picture of at most 96x96 pixels.

    Pillow reads every format except the paletted BLP1 the World Editor writes, which is unpacked here.

    Raises:
        ValueError: A paletted BLP with impossible dimensions.
        OSError: Pillow cannot read the image.
    """
    from PIL import Image
    if blob[:4] == b'BLP1' and struct.unpack_from('<I', blob, 4)[0] == 1:
        image = paletted_blp(blob)
    else:
        image = Image.open(BytesIO(blob)).convert('RGBA')
    image.thumbnail((SIZE, SIZE), Image.Resampling.LANCZOS)
    out = BytesIO()
    image.save(out, 'WEBP', quality=88)
    return out.getvalue()


def paletted_blp(blob: bytes):
    """A paletted BLP1 image (256 colours, 0/1/4/8-bit alpha) as a Pillow RGBA image."""
    from PIL import Image
    depth, width, height = struct.unpack_from('<III', blob, 8)
    if depth not in (0, 1, 4, 8) or not 0 < width * height <= 4096 ** 2:
        raise ValueError('invalid paletted BLP')
    offset = struct.unpack_from('<I', blob, 28)[0]
    size = width * height
    image = Image.frombytes('P', (width, height), blob[offset:offset + size])
    image.putpalette(blob[156:1180], 'BGRX')
    image = image.convert('RGBA')
    if depth:
        alpha = blob[offset + size:]
        mask = (1 << depth) - 1
        channel = bytes(((alpha[i * depth // 8] >> (i * depth % 8)) & mask) * 255 // mask for i in range(size))
        image.putalpha(Image.frombytes('L', image.size, channel))
    return image


def art_paths(key: str, objects: dict):
    """The icon file an object shows: its own icon field, else its game row's, else its parent's."""
    family = key.split('/')[0]
    if family not in ART:
        return None
    field, column = ART[family]
    seen = set()
    while key in objects and key not in seen:
        seen.add(key)
        obj = objects[key]
        for f in reversed(obj['fields']):
            if f[0] == field and f[3]:
                yield str(f[3]).split(',')[0].strip('" ')
        for row in reversed(list(obj['stock'].values())):
            columns = {k.casefold(): v for k, v in row.items()}
            for suffix in (':sd', '', ':de', ':hd'):
                value = columns.get(column.casefold() + suffix, '')
                if value.strip('" ') not in ('', '_', '-'):
                    yield value.split(',')[0].strip('" ')
        key = family + '/' + obj['parent']
    return None


def picture(path: PureWindowsPath, read, pack) -> bytes | None:
    """The picture of one icon file: the map's import of it wins over the game's; either may be stored as .dds,
    .blp or .tga instead."""
    variants = list(dict.fromkeys(str(path.with_suffix(s)) for s in (path.suffix, '.dds', '.blp', '.tga')))
    for filename in variants:
        blob = read(filename)
        if blob:
            try:
                return decode(blob)
            except UNREADABLE:
                continue
    return next((p for p in map(pack.icon, variants) if p), None)


def attach_portraits(db: dict, read, pack) -> None:
    """Sets each object's `art` (a picture id) and fills `db['portraits']` (picture id -> base64 WebP).

    Args:
        db: The wiki index (`objects` by key).
        read: Reads a map file by name.
        pack: The stock pack, for the game's icons.
    """
    images, found = {}, {}
    for key, obj in db['objects'].items():
        for raw in art_paths(key, db['objects']):
            path = PureWindowsPath(raw)
            if path.drive or path.root or '..' in path.parts:
                continue
            name = str(path).lower()
            if name not in found:
                image = picture(path, read, pack)
                found[name] = sha256(image).hexdigest()[:24] if image else None
                if image:
                    images[found[name]] = b64encode(image).decode()
            if found[name]:
                obj['art'] = found[name]
                break
    db['portraits'] = images
