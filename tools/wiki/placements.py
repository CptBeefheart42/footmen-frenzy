"""Read the widget layouts used by the active map families."""
from io import BytesIO
import struct


def widgets(data, filename):
    stream = BytesIO(data)

    def unpack(fmt):
        layout = struct.Struct("<" + fmt)
        buf = stream.read(layout.size)
        if len(buf) != layout.size:
            raise ValueError(f"Truncated {filename} at {stream.tell()}")
        return layout.unpack(buf)

    def number():
        return unpack("i")[0]

    def uid():
        return unpack("4s")[0].decode("latin-1")

    def count():
        value = number()
        if not 0 <= value <= len(data) - stream.tell():
            raise ValueError(f"Invalid count in {filename} at {stream.tell()}")
        return range(value)

    if uid() != "W3do":
        raise ValueError(f"Invalid {filename} signature")
    version, sub = unpack("ii")
    units = filename == "war3mapUnits.doo"
    if sub != 11 or version not in (8, 12, 13):
        raise ValueError(f"Unsupported {filename} version {version}.{sub}")
    rows = []
    for _ in count():
        record = {"entry": filename, "offset": stream.tell(), "id": uid(), "variation": number(),
                  "position": unpack("3f"), "angle": unpack("f")[0], "scale": unpack("3f")}
        if data[stream.tell()] >= 32:
            record["skin"] = uid()
        if version >= 12:
            record["group"] = number()
        record["flags"] = unpack("B")[0]
        if units:
            record["owner"], record["unknown1"], record["unknown2"], record["hp"], record["mana"] = unpack("iBBii")
        else:
            record["life"] = unpack("B")[0]
        record["item_table"] = number()
        record["drop_sets"] = [[{"item": uid(), "chance": number()} for _ in count()] for _ in count()]
        if units:
            record["gold"], record["acquisition"], record["level"], record["strength"], record["agility"], record["intelligence"] = unpack("ifiiii")
            record["inventory"] = [{"slot": number(), "item": uid()} for _ in count()]
            record["ability_settings"] = [{"ability": uid(), "autocast": number(), "level": number()} for _ in count()]
            mode = record["random_mode"] = number()
            if mode == 0:
                level, item_class = unpack("3sB")
                record.update(random_level=int.from_bytes(level, "little", signed=True), item_class=item_class)
            elif mode == 1:
                record["random_table"], record["column"] = unpack("ii")
            elif mode == 2:
                record["random_units"] = [{"unit": uid(), "chance": number()} for _ in count()]
            elif mode != -1:
                raise ValueError(f"Unknown random mode {mode} at {stream.tell()} in {filename}")
            record["color"], record["waygate_region"] = unpack("ii")
        if not units and version >= 13:
            record["unknown1"] = number()
        record["creation_id"] = number()
        if units and version >= 12:
            record["unknown4_6"] = unpack("iii")
        elif version >= 12:
            record["roll"], record["pitch"] = unpack("ff")
            record["lights"] = [dict(zip(("index", "casts_shadow", "bgra", "intensity", "shadow_start",
                                          "shadow_end", "quadratic", "linear", "damping"), unpack("III6f")))
                                for _ in count()]
        rows.append(record)
    if not units:
        special_version = number()
        for _ in count():
            rows.append({"entry": filename, "offset": stream.tell(), "special_version": special_version,
                         "id": uid(), "variation": number(), "terrain_position": unpack("ii")})
    if stream.tell() != len(data):
        raise ValueError(f"Trailing bytes in {filename} at {stream.tell()}")
    return rows
