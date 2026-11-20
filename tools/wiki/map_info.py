"""Map rules, players, tech restrictions and global random tables in Reforged W3I files."""
import struct
from .map_values import text


def settings(data):
    pos = 0

    def read(fmt):
        nonlocal pos
        size = struct.calcsize("<" + fmt)
        if pos + size > len(data):
            raise ValueError(f"Truncated war3map.w3i at {pos}")
        values = struct.unpack_from("<" + fmt, data, pos)
        pos += size
        return values[0] if len(values) == 1 else values

    def string():
        nonlocal pos
        end = data.index(b"\0", pos)
        value = text(data[pos:end])
        pos = end + 1
        return value

    def count():
        n = read("i")
        if n < 0 or n > len(data)-pos:
            raise ValueError(f"Invalid war3map.w3i count at {pos}")
        return range(n)

    def uid():
        return read("4s").decode("latin-1")

    version = read("i")
    if version not in (31, 32, 33, 39):
        raise ValueError(f"Unsupported map settings version {version}")
    result = {"format": version, "map_revision": read("i"), "editor": read("i"), "game_version": read("4i")}
    for key in ("name", "author", "description", "recommended_players"):
        result[key] = string()
    result.update(camera_bounds=read("8f"), camera_margins=read("4i"), dimensions=read("2i"),
                  flags=read("I"), tileset=read("B"), loading_background=read("i"))
    if version >= 39:
        result["race_hud"] = read("i")
    for key in ("loading_path", "loading_text", "loading_title", "loading_subtitle"):
        result[key] = string()
    result["game_data_set"] = read("i")
    for key in ("prologue_path", "prologue_text", "prologue_title", "prologue_subtitle"):
        result[key] = string()
    result.update(fog_style=read("i"), fog_start_end_density=read("3f"), fog_bgra=read("I"))
    if version >= 39:
        result.update(fog_height_start_end=read("2f"), fog_linear_start_end=read("2f"),
                      fog_max_opacity=read("f"), fog_over_sky=read("i"))
    result.update(weather=uid(), sound_environment=string(), light_environment=read("B"), water_bgra=read("I"),
                  script_language=read("i"), supported_modes=read("i"), game_data_version=read("i"))
    if version >= 32:
        result["default_zoom"], result["max_zoom"] = read("ii")
    if version >= 33:
        result["min_zoom"] = read("i")
    if version >= 39:
        result["water_and_minimap"] = dict(zip(("min_opacity","max_opacity","reflectivity","emissivity",
                                                "edge_softness","vertex_displacement","normal_strength",
                                                "override_bgra","environment_reflectivity","alpha_tile_bgra"), read("10I")))
    players = []
    for _ in count():
        player = {"id": read("i"), "controller": read("i"), "race": read("i")}
        if version >= 39:
            player["race_hud"] = read("i")
        player.update(flags=read("I"), name=string(), start=read("2f"), ally_priority=read("2I"),
                      enemy_priority=read("2I"))
        players.append(player)
    result["players"] = players
    result["forces"] = [{"flags": read("I"), "players": read("I"), "name": string()} for _ in count()]
    if data[pos:] == b"\xff":
        return result
    result["upgrades"] = [dict(players=read("I"), id=uid(), level=read("i"), availability=read("i"))
                          for _ in count()]
    if pos == len(data):
        return result
    result["tech_restrictions"] = [dict(players=read("I"), id=uid()) for _ in count()]
    result["random_unit_tables"] = []
    for _ in count():
        record = dict(index=read("i"), name=string(), types=[read("i") for _ in count()])
        record["sets"] = [dict(chance=read("i"), ids=[uid() for _ in record["types"]]) for _ in count()]
        result["random_unit_tables"].append(record)
    result["random_item_tables"] = [dict(index=read("i"), name=string(), sets=[
        [dict(chance=read("i"), item=uid()) for _ in count()] for _ in count()]) for _ in count()]
    if pos != len(data):
        raise ValueError(f"Trailing war3map.w3i data at {pos}")
    return result
