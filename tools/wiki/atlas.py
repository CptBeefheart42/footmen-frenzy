"""Build the linked object, stock-data and trigger index from a single map."""
from collections import defaultdict, deque
from hashlib import sha256
import json
from pathlib import Path
import re
from zipfile import ZipFile

from .import_game_data import CACHE, META, TABLES, game_files
from .map_values import decode_objects, string_table, text
from .placements import widgets
from .map_info import settings


GROUPS = {"units": "w3u", "items": "w3t", "abilities": "w3a", "effects": "w3h",
          "upgrades": "w3q", "destructibles": "w3b", "doodads": "w3d"}
NAMES = {"units": "unam", "items": "unam", "abilities": "anam", "effects": "fnam",
         "upgrades": "gnam", "destructibles": "bnam", "doodads": "dnam"}
RAW = re.compile(r"(?<![\w])([A-Za-z0-9_]{4})(?![\w])")
REF_TYPES = {"abilCode", "abilityList", "abilitySkinList", "heroAbilityList", "unitList",
             "unitCode", "unitSkinList", "techList", "upgradeList", "upgradeCode", "itemList",
             "buffList", "effectList"}


def slk(data):
    header, rows = {}, {}
    x = y = 0
    for line in text(data).splitlines():
        if not line.startswith("C;"):
            continue
        coords, sep, value = line.partition(";K")
        for part in coords.split(";")[1:]:
            if part.startswith("X"):
                x = int(part[1:])
            elif part.startswith("Y"):
                y = int(part[1:])
        if not sep:
            continue
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1].replace('""', '"').replace(";;", ";")
        if y == 1:
            header[x] = value
        elif x in header:
            rows.setdefault(y, {})[header[x]] = value
    return {row[header[1]]: row for row in rows.values() if header[1] in row}


def ini(data):
    section = ""
    sections = {}
    for line in text(data).splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif "=" in line and not line.startswith("//"):
            key, value = line.split("=", 1)
            sections.setdefault(section, {})[key.strip()] = value.strip()
    return sections


def stock_data(read):
    sources = {}
    manifest = None
    if CACHE.is_file():
        with ZipFile(CACHE) as z:
            manifest = json.loads(z.read("manifest.json"))
            for name, digest in manifest["files"].items():
                payload = z.read(name)
                if sha256(payload).hexdigest() != digest:
                    raise ValueError(f"Stock cache checksum mismatch for {name}")
                sources[name] = payload
    # Maps can import native SLKs and unit profiles as loose MPQ entries.
    for name in sorted(set(game_files()) | {"splats/lightningdata.slk"}):
        blob = read(name.replace("/", "\\"))
        if blob is not None:
            sources["map/" + name] = blob
    stock = defaultdict(dict)
    meta = defaultdict(dict)
    labels = {}
    config = {}
    profiles = []
    for source, data in sources.items():
        filename = Path(source).stem.lower()
        if filename in {"worldeditstrings", "worldeditgamestrings"}:
            for section in ini(data).values():
                labels.update(section)
        elif filename == "miscdata" or filename == "lightningdata":
            config[source] = text(data)
        elif filename in META.values():
            for group, table in META.items():
                if filename == table:
                    meta[group].update(slk(data))
        elif source.endswith(".slk"):
            group = next(k for k, tables in TABLES.items() if filename in tables)
            for uid, row in slk(data).items():
                stock[group, uid][source] = row
        else:
            profiles.append((source, ini(data)))
    kinds = defaultdict(set)
    for group, uid in stock:
        kinds[uid].add(group)
    for source, sections in profiles:
        for uid, row in sections.items():
            # Preserve profile sections for custom IDs supplied only by the map.
            for group in kinds.get(uid, ()):
                stock[group, uid][source] = row
            if uid not in kinds and source.startswith("map/"):
                config.setdefault(source, text(sources[source]))
    for fields in meta.values():
        for field in fields.values():
            label = field.get("displayName", "")
            field["label"] = labels.get(label, field.get("field", label)).strip('"')
    return stock, meta, config, manifest, labels


def script_index(script):
    functions = {}
    globals_ = []
    active = None
    for number, line in enumerate(script.splitlines(), 1):
        start = re.match(r"\s*function\s+(\w+)\s+takes\b", line)
        if start:
            active = {"line": number, "body": []}
            functions[start[1]] = active
        if active is None:
            if line.strip():
                globals_.append([number, line])
        else:
            active["body"].append(line)
            if line.strip().startswith("endfunction"):
                active = None
    by_id = defaultdict(set)
    constants = dict(re.findall(r"^\s*constant\s+integer\s+(\w+)\s*=\s*'(\w{4})'", script, re.M))
    def literal(expr):
        m = re.fullmatch(r"'(\w{4})'", expr)
        return m[1] if m else constants.get(expr)
    for name, fn in functions.items():
        fn["body"] = "\n".join(fn["body"])
        # Strip strings and comments before identifying calls and FourCC literals.
        code = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*', " ", fn["body"].partition("\n")[2])
        refs = set(re.findall(r"'([^'\r\n]{4})'", code))
        refs.update(constants[word] for word in set(re.findall(r"\b\w+\b", code)) & constants.keys())
        refs.update(re.findall(r'\bFourCC\s*\(\s*"(\w{4})"\s*\)', fn["body"]))
        fn["ids"] = sorted(refs)
        for uid in refs:
            by_id[uid].add(name)
        calls = set(re.findall(r"\b(\w+)\s*\(|\bfunction\s+(\w+)", code))
        targets = {a or b for a, b in calls} & functions.keys()
        targets.update(n for n in re.findall(r'\bExecuteFunc\s*\(\s*"(\w+)"', fn["body"]) if n in functions)
        fn["calls"] = sorted(targets)
        fn["consumes"] = re.findall(r"\bRemoveItem\s*\(\s*GetItemOfTypeFromUnitBJ\s*\([^,\n]+,\s*'(\w{4})'", code)
        fn["grants"] = re.findall(r"\bUnitAddItemByIdSwapped\s*\(\s*'(\w{4})'", code)
        aliases = re.findall(r"\b(\w+)\s*=\s*GetSpellAbilityId\(\)", code)
        spell = r"(?:GetSpellAbilityId\s*\(\s*\)" + "".join("|" + re.escape(v) for v in aliases) + ")"
        fn["spells"] = sorted({value for match in re.finditer(r"\b" + spell + r"\s*(?:==|!=)\s*('....'|\w+)", code)
                               if (value := literal(match[1]))})
        fn["creation_sites"] = []
        for offset, line in enumerate(fn["body"].splitlines()):
            for call in re.finditer(r"\b(BlzCreateUnitWithSkin|CreateUnit(?:AtLoc)?|CreateNUnitsAtLoc(?:BJ)?|"
                                    r"CreateNUnitsAtLocFacingLocBJ|CreateUnitAtLocSaveLast)\s*\(", line.partition("//")[0]):
                depth, start = 0, call.end()
                parts = []
                for i in range(start, len(line)):
                    char = line[i]
                    if char == "," and depth == 0:
                        parts.append(line[start:i].strip())
                        start = i + 1
                        if len(parts) == 2:
                            break
                    elif char in "([":
                        depth += 1
                    elif char in ")]":
                        depth -= 1
                if len(parts) == 2:
                    fn["creation_sites"].append([fn["line"]+offset, parts[1], literal(parts[1])])
        fn["creates"] = sorted({site[2] for site in fn["creation_sites"] if site[2]})
    # A GUI spell often tests the ID in a condition, then creates the unit in a
    # separately registered action. Join only callbacks on the same trigger.
    actions = defaultdict(set)
    for fn in functions.values():
        conditions = re.findall(r"TriggerAddCondition\s*\(\s*(\w+)\s*,\s*(?:Condition|Filter)\s*\(\s*function\s+(\w+)", fn["body"])
        registered = re.findall(r"TriggerAddAction\s*\(\s*(\w+)\s*,\s*function\s+(\w+)", fn["body"])
        for handle, condition in conditions:
            actions[condition].update(action for trigger, action in registered if trigger == handle)
    paths = defaultdict(list)
    for name, fn in functions.items():
        if not fn["spells"]:
            continue
        queue = deque([[name]] + [[name, n] for n in sorted(actions[name]) if n in functions])
        seen = set()
        while queue:
            path = queue.popleft()
            current = path[-1]
            if current in seen:
                continue
            seen.add(current)
            target = functions[current]
            for uid in target["creates"]:
                for ability in fn["spells"]:
                    paths[ability].append({"unit": uid, "path": path})
            queue.extend(path+[n] for n in target["calls"] if n not in seen)
    return functions, globals_, by_id, paths


def targets(value, known, allow_ids):
    if not isinstance(value, str):
        return set()
    # Object lists and Warcraft tooltip field references. Avoid ordinary prose matches.
    ids = {v.strip() for v in value.split(",")} if allow_ids else set()
    ids.update(re.findall(r"<(\w{4}),", value))
    return ids & known


def ability_command(uid, objects, stock, custom):
    """Resolve cast and learn commands independently, including partial XY overrides."""
    modes = {"cast":("Hotkey","Buttonpos","ahky","abpx","abpy"),
             "learn":("Researchhotkey","Researchbuttonpos","arhk","arpx","arpy")}
    lineage = []
    while uid not in lineage:
        lineage.append(uid)
        uid = objects.get(("abilities",uid),{}).get("parent",uid)
    result = {}
    for mode,(hotkey,position,hf,xf,yf) in modes.items():
        values = {}
        for ancestor in reversed(lineage):
            for source,row in stock.get(("abilities",ancestor),{}).items():
                if source.startswith("custom_v1/") and not custom:
                    continue
                for column,value in row.items():
                    if column.casefold()==hotkey.casefold():
                        values["key"]=value
                    elif column.casefold()==position.casefold():
                        values.update(zip(("x","y"),value.split(",")))
            for field,_,_,value,*_ in objects.get(("abilities",ancestor),{}).get("fields",[]):
                if field in (hf,xf,yf):
                    values[{hf:"key",xf:"x",yf:"y"}[field]]=value
        command = {axis:int(str(values[axis]).strip()) for axis in ("x","y") if re.fullmatch(r"-?\d+",str(values.get(axis,"")).strip())}
        key = str(values.get("key","")).strip(' "')
        if key and key not in ("_","-"):
            command["key"]=key.upper()
        if command:
            result[mode]=command
    return result


def resolved_fields(group, uid, objects, stock, meta, custom, numeric_fields, visuals):
    lineage = []
    seen = set()
    parent = uid
    while parent not in seen:
        seen.add(parent)
        lineage.append(parent)
        obj = objects.get((group, parent), {})
        parent = obj.get("parent", parent)
    definitions = meta.get(group, {})
    fields = {k: m for k, m in definitions.items() if (m.get("type") in REF_TYPES or k in numeric_fields
              or m.get("type") in {"model","modelList"} and m["field"].lower().endswith("art"))
              and (group not in {"items", "units"} or k.startswith("i" if group == "items" else "u"))
              and (not m.get("useSpecific") or seen.intersection(m["useSpecific"].split(",")))}
    resolved = {}
    for ancestor in reversed(lineage):
        for source, row in stock.get((group, ancestor), {}).items():
            if source.startswith("custom_v1/") and not custom:
                continue
            table = Path(source).stem.lower() if source.endswith(".slk") else "profile"
            for key, spec in fields.items():
                if spec.get("slk", "").lower() != table:
                    continue
                column = spec["field"]
                slot = 0
                if column == "Data" and spec.get("data", "0").isdigit() and int(spec["data"]) > 0:
                    slot = int(spec["data"])
                    column += chr(64+slot)
                for col, val in row.items():
                    if col.casefold() == column.casefold():
                        resolved[key, 0, slot] = (val, source + " / " + ancestor + " / " + col)
                    elif spec.get("repeat", "0") != "0" and col.startswith(column) and col[len(column):].isdigit():
                        resolved[key, int(col[len(column):]), slot] = (val, source + " / " + ancestor + " / " + col)
        for field, lvl, ptr, value, entry, *_ in objects.get((group, ancestor), {}).get("fields", []):
            if field in fields:
                slot = ptr or (int(fields[field].get("data","0")) if fields[field]["field"]=="Data" else 0)
                resolved[field, lvl, slot] = (value, f"{entry} / {ancestor} / {field} [{lvl}, {ptr}]")
    links, stats = [], []
    for (key, lvl, ptr), (value, source) in sorted(resolved.items()):
        if fields[key].get("type") in {"model","modelList"}:
            visuals.extend(p.strip().strip('"') for p in str(value).split(",") if p.strip().lower().endswith((".mdx",".mdl")))
            continue
        if key in numeric_fields:
            if isinstance(value, (float,int)) or re.fullmatch(r"-?(?:\d+(?:\.\d*)?|\.\d+)", str(value)):
                stats.append(dict(field=key, label=numeric_fields[key], level=lvl, pointer=ptr, value=value, source=source))
            continue
        if not isinstance(value, str):
            continue
        ids = [v.strip() for v in value.split(",") if re.fullmatch(r"\w{4}", v.strip())]
        if ids:
            label = {"uhab": "Hero abilities", "uabi": "Unit abilities"}.get(key, fields[key]["label"])
            links.append(dict(field=key, label=label, level=lvl, pointer=ptr, ids=ids, source=source))
    return links, stats


def effect_index(catalog, functions):
    effects = {}
    def add(path, owner, source):
        path = path.strip().strip('"').replace("\\\\", "\\").replace("/", "\\")
        if not path.lower().endswith((".mdl", ".mdx")):
            return
        key = re.sub(r"\.mdl$", ".mdx", path.lower())
        effect = effects.setdefault(key, {"path": path, "uses": []})
        effect["uses"].append([owner, source])
    for key, obj in catalog.items():
        for field, level, ptr, value, entry, *_ in obj["fields"]:
            if isinstance(value, str) and (".mdl" in value.lower() or ".mdx" in value.lower()):
                for path in value.split(","):
                    add(path, key, f"{entry} / {field} [{level}, {ptr}]")
        for src, row in obj["stock"].items():
            for column, value in row.items():
                if ".mdl" in value.lower() or ".mdx" in value.lower():
                    for path in value.split(","):
                        add(path, key, f"{src} / {column}")
    for name, fn in functions.items():
        for delta, line in enumerate(fn["body"].splitlines()):
            for path in re.findall(r'"([^"\r\n]+\.(?:mdl|mdx))"', line, re.I):
                add(path, "fn/"+name, "war3map.j:"+str(fn["line"]+delta))
    return effects


def atlas(read):
    strings = string_table(read("war3map.wts") or b"")
    objects = {}
    for group, ext in GROUPS.items():
        for prefix in ("war3mapSkin", "war3map"):
            entry = f"{prefix}.{ext}"
            data = read(entry)
            if data is None:
                continue
            def field(uid, *values):
                obj = objects.setdefault((group, uid), {"fields": []})
                obj["fields"].append(values)
            for uid, parent, _ in decode_objects(data, entry, ext in {"w3a", "w3q", "w3d"}, strings, field):
                obj = objects.setdefault((group, uid), {"fields": []})
                if parent != uid or "parent" not in obj:
                    obj["parent"] = parent
    jass = read("war3map.j")
    if jass is None:
        raise ValueError("Missing war3map.j")
    functions, globals_, by_id, creation_paths = script_index(text(jass))
    recipes = [{"fn": name, "consumes": fn["consumes"], "grants": fn["grants"]}
               for name, fn in functions.items() if fn["consumes"] and fn["grants"]]
    placements = []
    for entry in ("war3mapUnits.doo", "war3map.doo"):
        data = read(entry)
        if data is not None:
            placements.extend(widgets(data, entry))
    stock, meta, config, game, labels = stock_data(read)
    ref_columns = {group: {f.get("field", "").lower() for f in fields.values()
                           if f.get("type") in REF_TYPES} for group, fields in meta.items()}
    for filename in ("war3mapMisc.txt", "war3mapExtra.txt", "war3mapSkin.txt"):
        blob = read(filename)
        if blob is not None:
            config[filename] = text(blob)
    allkeys = stock.keys() | objects.keys()
    kinds = defaultdict(set)
    for group, uid in allkeys:
        kinds[uid].add(group)
    known = set(kinds)
    queue = deque(objects)
    raw_refs = set(by_id)
    info_data = read("war3map.w3i")
    info = settings(info_data) if info_data else {}
    raw_refs.update(RAW.findall(json.dumps(info)))
    placed_refs = defaultdict(set)
    for rec in placements:
        raw_refs.add(rec["id"])
        for sub in [*rec.get("drop_sets", []), rec.get("inventory", []), rec.get("ability_settings", []),
                    rec.get("random_units", [])]:
            for values in sub:
                for name in ("item", "ability", "unit"):
                    if name in values:
                        placed_refs[rec["id"]].add(values[name])
                        raw_refs.add(values[name])
        if "skin" in rec:
            raw_refs.add(rec["skin"])
    for _, line in globals_:
        raw_refs.update(re.findall(r"'(\w{4})'", line))
    for body in config.values():
        raw_refs.update(RAW.findall(body))
    for uid in sorted(raw_refs & known):
        queue.extend((group, uid) for group in sorted(kinds[uid]))
    catalog = {}
    while queue:
        group, uid = queue.popleft()
        key = group + "/" + uid
        if key in catalog:
            continue
        obj = objects.get((group, uid), {})
        parent = obj.get("parent", uid)
        fields = obj.get("fields", [])
        defaults = stock.get((group, uid), {})
        name = next((f[3] for f in reversed(fields) if f[0] == NAMES[group] and f[3]), None)
        parent_stock = stock.get((group, parent), {})
        if not name:
            name = next((row[k] for row in reversed(list((defaults or parent_stock).values()))
                         for k in ("Name", "name", "comments", "comment(s)") if row.get(k) not in (None,"","_")), uid)
        name = re.sub(r"\|c[\da-fA-F]{8}|\|r", "", labels.get(name, str(name))).strip('"')
        refs = defaultdict(set)
        for target in placed_refs[uid]:
            refs[target].add("Placed instance inventory, ability or random table")
        for field, level, pointer, value, entry, *_ in fields:
            details = meta.get(group, {}).get(field, {})
            for ref in targets(value, known, not details or details.get("type") in REF_TYPES):
                refs[ref].add(f'{details.get("label", field)} · {entry} {field} [{level}, {pointer}]')
        for source, row in defaults.items():
            for column, value in row.items():
                base_column = re.sub(r"\d+$", "", column.lower())
                allow = base_column in ref_columns.get(group, ()) or base_column in {"code", "requires", "trains"}
                for ref in targets(value, known, allow) - {uid}:
                    refs[ref].add(f"{source} {column}")
        if parent != uid:
            refs[parent].add("Parent object")
        for ref in sorted(refs):
            queue.extend((g, ref) for g in sorted(kinds.get(ref, ())))
        flags = {f[0]: f[3] for f in fields}
        building = flags.get("ubdg")
        if building is None:
            building = next((r["isbldg"] for r in reversed(list((defaults or parent_stock).values()))
                             if "isbldg" in r), "0")
        category = group
        if group == "units":
            category = "buildings" if str(building) == "1" else "heroes" if uid[:1].isupper() else "units"
        catalog[key] = dict(id=uid, group=category, name=name, parent=parent, fields=fields,
                            stock=defaults, refs={i: sorted(v) for i, v in sorted(refs.items()) if i != uid},
                            functions=sorted(by_id.get(uid, ())), defined=(group, uid) in objects)
    presets = json.loads(Path(__file__).with_name("reports.json").read_text(encoding="utf-8"))
    for key, obj in catalog.items():
        group, uid = key.split("/", 1)
        numeric = {k: v for k, v in presets.get(group, {}).get("fields", {}).items()
                   if meta.get(group, {}).get(k, {}).get("type") in {"int", "real", "unreal"}}
        if group == "abilities":
            obj["command"] = ability_command(uid,objects,stock,info.get("game_data_set")==1)
            numeric.update({k: m["label"] for k, m in meta.get(group, {}).items()
                            if m.get("type") in {"int", "real", "unreal"} and
                            (m.get("field") == "Data" or k == "alev")})
        if group == "units":
            numeric.update({"ua1d": "Damage dice", "ua1s": "Sides per die", "ua1r": "Attack range"})
        primary = set(numeric)
        for field, spec in meta.get(group, {}).items():
            if spec.get("type") not in {"int","real","unreal"} or spec.get("category") not in {"stats","data","combat","move","tech","path"}:
                continue
            label = spec["label"]
            if group == "upgrades" and field[:3] in {"gba","gmo"}:
                label = f"Effect {field[-1]} " + ("base value" if field.startswith("gba") else "increment per level")
                primary.add(field)
            numeric.setdefault(field,label)
        visuals = []
        obj["linked_fields"], obj["stats"] = resolved_fields(
            group, uid, objects, stock, meta, info.get("game_data_set")==1, numeric, visuals)
        obj["visuals"] = sorted(set(visuals))
        for stat in obj["stats"]:
            if stat["field"] not in primary:
                stat["additional"] = True
    return {"objects": catalog, "functions": functions, "globals": globals_, "config": config,
            "wts": strings, "metadata": meta, "game": game, "placements": placements, "settings": info,
            "creation_paths": creation_paths, "models": effect_index(catalog, functions), "recipes": recipes,
            "unresolved": sorted(set(by_id) - known)}
