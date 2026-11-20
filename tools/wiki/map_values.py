"""Read map-local object fields and explicitly assigned JASS table values."""
from dataclasses import dataclass
import re
import struct


@dataclass(frozen=True)
class Cell:
    value: str | int | float
    source: str


def text(data):
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


WTS_ENTRY = re.compile(
    r"(?m)(?P<header>^STRING[ \t]+(?P<id>\d+)[^\n]*\n"
    r"(?:(?![ \t]*(?:\{|STRING[ \t]+\d+))[^\n]*\n)*[ \t]*\{[ \t]*\r?\n)"
    r"(?P<body>[\s\S]*?)(?P<footer>(?:\r?\n)?^\}[ \t]*\r?$)")


def string_table(data):
    source = text(data)
    entries = {int(m["id"]): m["body"].replace("\r\n", "\n") for m in WTS_ENTRY.finditer(source)}
    declared = re.findall(r"(?m)^STRING[ \t]+(\d+)\b", source)
    if len(entries) != len(declared):
        missing = set(map(int, declared)) - entries.keys()
        raise ValueError(f"Incomplete or duplicate WTS entries. Missing IDs: {sorted(missing)[:12]}")
    return entries


def display_name(cell, fallback):
    if not cell:
        return Cell(fallback, "Object ID")
    name = re.sub(r"\|c[0-9a-fA-F]{8}|\|r", "", str(cell.value)).replace("|n", " ").strip()
    return Cell(name or fallback, cell.source)


def real_value(data):
    # Drop binary32 display noise while retaining enough digits to round-trip.
    value = struct.unpack("<f", data)[0]
    for precision in range(1, 10):
        rounded = float(format(value, f".{precision}g"))
        try:
            if struct.pack("<f", rounded) == data:
                return rounded
        except OverflowError:
            continue
    return value


def decode_objects(data, entry, extended, strings, record=None):
    pos = 0

    def take(n):
        nonlocal pos
        if n < 0 or n > len(data) - pos:
            raise ValueError(f"Truncated {entry} at byte {pos}")
        pos += n
        return data[pos - n:pos]

    def integer():
        return struct.unpack("<i", take(4))[0]

    def count():
        n = integer()
        if n < 0:
            raise ValueError(f"Negative record count in {entry}")
        return n

    version = integer()
    if version not in (1, 2, 3):
        raise ValueError(f"Unsupported {entry} version {version}. Check that Git LFS files are present.")
    for _ in range(2):
        for _ in range(count()):
            parent = take(4).decode("ascii")
            custom = take(4)
            uid = parent if custom == bytes(4) else custom.decode("ascii")
            if version == 3:
                take(count() * 4)
            fields = {}
            for _ in range(count()):
                field = take(4).decode("ascii")
                kind = integer()
                level, pointer = (integer(), integer()) if extended else (0, 0)
                source = f"{entry} / {uid} / {field}"
                if extended:
                    source += f" [{level}, {pointer}]"
                offset = pos
                token = None
                if kind == 3:
                    value = text(take(data.index(b"\0", pos) - pos + 1)[:-1])
                    trigger = re.fullmatch(r"TRIGSTR_(\d+)", value)
                    if trigger and int(trigger[1]) in strings:
                        token = value
                        source += f" / war3map.wts {value}"
                        value = strings[int(trigger[1])]
                elif kind == 0:
                    value = integer()
                elif kind in (1, 2):
                    value = real_value(take(4))
                else:
                    raise ValueError(f"Unknown value type {kind} in {source}")
                take(4)  # Object modification end marker
                fields[field, level, pointer] = Cell(value, source)
                if record is not None:
                    record(uid, field, level, pointer, value, entry, kind, offset, token)
            yield uid, parent, fields
    if pos != len(data):
        raise ValueError(f"Trailing data in {entry} at byte {pos}")


def object_records(read, extension, strings):
    records = {}
    found = False
    for prefix in ("war3mapSkin", "war3map"):
        entry = f"{prefix}.{extension}"
        data = read(entry)
        if data is None:
            continue
        found = True
        for uid, parent, fields in decode_objects(data, entry, extension in {"w3a", "w3q", "w3d"}, strings):
            base, merged = records.setdefault(uid, (parent, {}))
            if base != parent and uid not in {base, parent}:
                raise ValueError(f"Conflicting parents for {uid} in {entry}")
            if base == uid and parent != uid:
                records[uid] = (parent, merged)
            merged.update(fields)
    return records if found else None


def object_table(read, extension, strings):
    records = object_records(read, extension, strings)
    if records is None:
        raise ValueError(f"No map object data for {extension}")
    expanded = {}

    def inherit(uid, path):
        if uid in expanded:
            return expanded[uid]
        if uid in path:
            raise ValueError(f"Object inheritance cycle at {uid}")
        parent, fields = records[uid]
        inherited = inherit(parent, path | {uid}) if parent != uid and parent in records else {}
        expanded[uid] = inherited | fields
        return expanded[uid]

    for uid in records:
        inherit(uid, set())
    return expanded


def object_rows(objects, report, selected):
    extended = report["extension"] in {"w3a", "w3q", "w3d"}
    rows = []
    for uid, fields in objects.items():
        slots = sorted({(level, pointer) for field, level, pointer in fields if field in selected})
        for level, pointer in slots:
            name = fields.get((report["name"], level, 0)) or fields.get((report["name"], 0, 0))
            if name is None:
                name = fields.get((report["name"], 1, 0))
            row = {"id": Cell(uid, report["extension"]), "name": display_name(name, uid)}
            if extended:
                row.update(level=Cell(level, "Object field level"), pointer=Cell(pointer, "Object data pointer"))
            row.update({field: fields[field, level, pointer] for field in selected
                        if (field, level, pointer) in fields})
            rows.append(row)
    return sorted(rows, key=lambda r: (str(r["name"].value).casefold(), r["id"].value))


def script_rows(script, units, report, selected):
    identity = report["identity"]
    arrays = {identity, *selected}
    slots = {}
    active = None
    seen = set()
    depth = 0
    for number, line in enumerate(script.splitlines(), 1):
        line = line.partition("//")[0].strip()
        if line.startswith("function "):
            name = line.split()[1]
            active = name if name in report["functions"] else None
            depth = 0
            if active:
                seen.add(active)
        elif line == "endfunction":
            active = None
        elif active:
            if line.startswith("if ") or line == "loop":
                depth += 1
            elif line in {"endif", "endloop"}:
                depth -= 1
            match = re.fullmatch(r"set\s+(\w+)\s*\[(.+?)\]\s*=\s*(.+)", line)
            if not match or match[1] not in arrays:
                continue
            field, index, rhs = match.groups()
            source = f"war3map.j:{number} / {active} / {field}[{index}]"
            if depth or not index.strip().isdigit():
                raise ValueError(f"Expected an unconditional, fixed-index assignment at {source}")
            if re.fullmatch(r"'[^']{4}'", rhs):
                value = rhs[1:-1]
            elif re.fullmatch(r"-?\d+", rhs):
                value = int(rhs)
            elif re.fullmatch(r"-?(?:\d+\.\d*|\.\d+)", rhs):
                value = float(rhs)
            else:
                ref = re.fullmatch(re.escape(field) + r"\[(\d+)\]", rhs)
                prior = slots.get(int(ref[1]), {}).get(field) if ref else None
                if prior is None or f" / {active} / " not in prior.source:
                    raise ValueError(f"Unsupported expression at {source}: {rhs}")
                value = prior.value
                source += f" from {prior.source}"
            slots.setdefault(int(index), {})[field] = Cell(value, source)
    missing = set(report["functions"]) - seen
    if missing:
        raise ValueError(f"Missing JASS report functions: {', '.join(sorted(missing))}")
    rows = []
    for index, values in sorted(slots.items()):
        if identity not in values:
            row = {"index": Cell(index, next(iter(values.values())).source)}
        else:
            uid = values[identity]
            name = units.get(uid.value, {}).get(("unam", 0, 0))
            row = {"id": uid, "name": display_name(name, uid.value), "index": Cell(index, uid.source)}
        row.update({field: values[field] for field in selected if field in values})
        rows.append(row)
    return rows
