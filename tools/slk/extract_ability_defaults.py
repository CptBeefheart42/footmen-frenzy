#!/usr/bin/env python3
"""Extract pre-3.0 ability level defaults from a local Warcraft III 2.0.4 CASC install.

Why: WC3 3.0.0 stopped carrying an ability's level-4 data to levels 5+ of abilities with more than
4 levels — an unset per-level field now reads 0 there. Our maps (saved for 2.0.4.23745) never
stored those cells, so the build fills them explicitly (tools/shared/AbilityLevelFill.cs) from the
table this script writes (repo-root ability_level_defaults.csv, committed — CI has no WC3 install).

What it reads (stdlib only, straight from the local CASC storage):
  war3.w3mod:_balance/custom_v1.w3mod:units/abilitydata.slk   TFT + game data set "Custom" (our maps)
  war3.w3mod:units/abilitydata.slk                            fallback for ids missing from custom_v1
  war3.w3mod:units/abilitymetadata.slk                        field id -> SLK column, type, applicability

For every ability alias and every metadata row with slk=AbilityData and repeat>0 that applies to it
(useSpecific/notSpecific), the level-4 cell is what 2.0.4 used for every level above 4. A blank level
cell ("-"/"_") is 0/empty — it is NOT carried forward from a lower level: the 3.0 probe map reads blank
level 2-4 cells as 0 (a range 3.0 did not change), and the maps rely on it (e.g. a "percent" flag the
designers zeroed only at level 1 of a 1-level base). So a blank level-4 cell means nothing to fill.
Zero/empty results are skipped (3.0 reads those as 0/empty anyway) — except "Targets Allowed": a blank target
list means "the ability's built-in default targets", which 3.0 still applies at levels 1-4 but not to an unset
cell above level 4 (Blizzard L5/L6 hit nothing). Writing the SLK's own blank token "_" restores the default
(probe map v4: L4 default and L5 "_" hit exactly the same units; "-" or "" hit nothing).

Validation (fails loudly): every per-level (base, field) already modified in the given dumpall CSVs
must be applicable, with the same object-data type and pointer; one pointer per field id.

usage: extract_ability_defaults.py --casc ~/wc3-stage --out ability_level_defaults.csv \
           [--observed dump1.csv dump2.csv ...]
"""
import argparse
import csv
import glob
import io
import os
import re
import struct
import sys
import zlib

CUSTOM_V1 = "war3.w3mod:_balance/custom_v1.w3mod:units/abilitydata.slk"
BASE_DATA = "war3.w3mod:units/abilitydata.slk"
METADATA = "war3.w3mod:units/abilitymetadata.slk"

# Metadata `type` -> object-data value type (w3a Int/Real/Unreal/String). Anything not listed is an
# error, so a new type gets a deliberate decision instead of a guess.
INT_TYPES = {"int", "bool", "attackBits", "channelFlags", "channelType", "deathType", "defenseTypeInt",
             "detectionType", "fullFlags", "interactionFlags", "morphFlags", "pickFlags", "silenceFlags",
             "spellDetail", "stackFlags", "teamColor", "techAvail", "versionFlags"}
STRING_TYPES = {"string", "abilCode", "abilityList", "abilitySkinList", "buffList", "effectList", "heroAbilityList",
                "itemList", "lightningEffect", "lightningList", "modelList", "orderString", "targetList",
                "techList", "unitCode", "unitList", "upgradeCode", "upgradeList", "icon", "model",
                "unitSkinList", "itemClass", "unitClass", "unitRace", "weaponType", "attributeType",
                "armorType", "attackType", "combatSound", "moveType", "regenType", "shadowImage",
                "shadowTexture", "soundLabel", "texture", "uberSplat", "unitSound", "destructableCode",
                "doodadCode", "tilesetList", "pathingTexture", "aiBuffer", "char"}
REAL_TYPES = {"real"}
UNREAL_TYPES = {"unreal"}


# ------------------------------------------------------------------------------------------ CASC
class Casc:
    """Minimal read-only local CASC reader for Warcraft III (TVFS root, BLTE N/Z frames)."""

    def __init__(self, root):
        self.root = os.path.expanduser(root)
        self.data_dir = os.path.join(self.root, "Data", "data")
        self.build, self.config = self._build_config()
        self.idx = self._load_idx(self.data_dir)
        self.files = {}
        self.vfs = {}
        for m in re.finditer(r"^(vfs-\d+) = (\w+) (\w+)", self.config, re.M):
            self.vfs[bytes.fromhex(m.group(3))[:9]] = m.group(1)
        root_ekey = re.search(r"^vfs-root = \w+ (\w+)", self.config, re.M).group(1)
        self._walk(self.read_ekey(bytes.fromhex(root_ekey)), "")

    def _build_config(self):
        with open(os.path.join(self.root, ".build.info"), encoding="utf-8") as fh:
            lines = [ln.rstrip("\n") for ln in fh if ln.strip()]
        header = [h.split("!")[0] for h in lines[0].split("|")]
        rows = [dict(zip(header, ln.split("|"))) for ln in lines[1:]]
        row = next((r for r in rows if r.get("Active") == "1"), rows[0])
        key = row["Build Key"]
        with open(os.path.join(self.root, "Data", "config", key[0:2], key[2:4], key), encoding="utf-8") as fh:
            config = fh.read()
        return row.get("Version", "?"), config

    @staticmethod
    def _load_idx(data_dir):
        newest = {}
        for f in glob.glob(os.path.join(data_dir, "*.idx")):
            name = os.path.basename(f)[:-4]
            bucket, version = name[:2], int(name[2:], 16)
            if bucket not in newest or version > newest[bucket][0]:
                newest[bucket] = (version, f)
        idx = {}
        for _, f in sorted(newest.values(), key=lambda v: v[1]):
            b = open(f, "rb").read()
            esz = struct.unpack_from("<I", b, 0x20)[0]
            for i in range(esz // 18):
                e = b[0x28 + i * 18:0x28 + i * 18 + 18]
                off = int.from_bytes(e[9:14], "big")
                idx[e[:9]] = (off >> 30, off & ((1 << 30) - 1), struct.unpack_from("<I", e, 14)[0])
        return idx

    def read_ekey(self, ekey):
        k = ekey[:9]
        if k not in self.idx:
            raise KeyError(f"EKey {ekey.hex()} not in local indices")
        archive, offset, size = self.idx[k]
        with open(os.path.join(self.data_dir, "data.%03d" % archive), "rb") as fh:
            fh.seek(offset)
            d = fh.read(size)[30:]
        if d[:4] != b"BLTE":
            raise ValueError(f"EKey {ekey.hex()}: not a BLTE blob")
        header_size = struct.unpack(">I", d[4:8])[0]
        if header_size == 0:
            chunks, pos = [len(d) - 8], 8
        else:
            n = int.from_bytes(d[9:12], "big")
            chunks, pos = [struct.unpack_from(">I", d, 12 + i * 24)[0] for i in range(n)], header_size
        out = bytearray()
        for c in chunks:
            blk = d[pos:pos + c]
            pos += c
            mode = blk[:1]
            if mode == b"N":
                out += blk[1:]
            elif mode == b"Z":
                out += zlib.decompress(blk[1:])
            else:
                raise ValueError(f"EKey {ekey.hex()}: unsupported BLTE frame mode {mode!r}")
        return bytes(out)

    def _walk(self, data, prefix):
        ptoff, ptsz, vtoff, vtsz, ctoff, ctsz = struct.unpack_from(">6I", data, 12)
        cosz = 4 if ctsz > 0xFFFFFF else 3 if ctsz > 0xFFFF else 2 if ctsz > 0xFF else 1

        def entry(path, spans):
            full = prefix + path
            if len(spans) == 1 and spans[0][0] in self.vfs:
                sub = self.read_ekey(spans[0][0])
                if sub[:4] == b"TVFS":
                    self._walk(sub, full + ":")
                    return
            self.files[full] = spans

        def files(p, end, base):
            path = base
            while p < end:
                val = None
                if data[p] == 0:
                    path += "/"
                    p += 1
                if p < end and data[p] != 0xFF:
                    ln = data[p]
                    path += data[p + 1:p + 1 + ln].decode("latin1")
                    p += 1 + ln
                if p < end and data[p] == 0:
                    path += "/"
                    p += 1
                if p < end:
                    if data[p] == 0xFF:
                        val = struct.unpack_from(">I", data, p + 1)[0]
                        p += 5
                    else:
                        path += "/"
                if val is not None:
                    if val & 0x80000000:
                        sz = val & 0x7FFFFFFF
                        files(p, p + sz - 4, path)
                        p += sz - 4
                    else:
                        q = vtoff + val
                        n = data[q]
                        q += 1
                        spans = []
                        for _ in range(n):
                            _, span_size = struct.unpack_from(">II", data, q)
                            q += 8
                            co = int.from_bytes(data[q:q + cosz], "big")
                            q += cosz
                            spans.append((data[ctoff + co:ctoff + co + 9], span_size))
                        entry(path, spans)
                    path = base

        files(ptoff, ptoff + ptsz, "")

    def read(self, path):
        if path not in self.files:
            raise KeyError(f"{path} not found in CASC ({len(self.files)} files indexed)")
        return b"".join(self.read_ekey(ek) for ek, _ in self.files[path])


# ------------------------------------------------------------------------------------------- SLK
def parse_slk(raw):
    """SYLK -> (header list, {first-column id: {column: value}}). Values are raw strings, unquoted."""
    cells, y, x = {}, 0, 0
    for ln in raw.decode("latin1").splitlines():
        if not ln.startswith("C;"):
            continue
        v = None
        for part in ln.split(";")[1:]:
            tag = part[:1]
            if tag == "X":
                x = int(part[1:])
            elif tag == "Y":
                y = int(part[1:])
            elif tag == "K":
                v = part[1:]
        if v is not None:
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                v = v[1:-1]
            cells[(y, x)] = v
    width = max(k[1] for k in cells)
    height = max(k[0] for k in cells)
    rows = [[cells.get((r, c), "") for c in range(1, width + 1)] for r in range(1, height + 1)]
    header = rows[0]
    return header, {r[0]: dict(zip(header, r)) for r in rows[1:] if r[0]}


def is_empty(v):
    return v is None or v.strip() in ("", "-", "_")


def wc3_type(meta_type):
    if meta_type in REAL_TYPES:
        return "Real"
    if meta_type in UNREAL_TYPES:
        return "Unreal"
    if meta_type in INT_TYPES:
        return "Int"
    if meta_type in STRING_TYPES:
        return "String"
    return None


def normalize(value, typ, notes, label):
    """Return the CSV value text, or None when the cell means 0/empty (nothing to fill)."""
    if is_empty(value):
        return None
    v = value.strip()
    if typ == "String":
        return v
    try:
        f = float(v)
    except ValueError:
        notes.append(f"{label}: non-numeric {value!r} in a {typ} field (the engine reads 0), skipped")
        return None
    if typ == "Int":
        if f != int(f):
            notes.append(f"{label}: non-integral {value!r} in an Int field, truncated to {int(f)}")
        return None if int(f) == 0 else str(int(f))
    if f == 0.0:
        return None
    return repr(struct.unpack("<f", struct.pack("<f", f))[0])  # float32-exact text


def column_for(meta):
    data = int(meta["data"] or 0)
    return f"{meta['field']}{chr(ord('A') + data - 1)}" if data > 0 else meta["field"]


def split_codes(s):
    return {t.strip() for t in (s or "").split(",") if t.strip() and t.strip() not in ("-", "_")}


def applicable(meta, alias, code):
    use = split_codes(meta.get("useSpecific"))
    nope = split_codes(meta.get("notSpecific"))
    ids = {alias, code}
    if ids & nope:
        return False
    return not use or bool(ids & use)


# ---------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--casc", default="~/wc3-stage")
    ap.add_argument("--out", required=True)
    ap.add_argument("--observed", nargs="*", default=[], help="BalanceTool dumpall CSVs to validate against")
    args = ap.parse_args()

    casc = Casc(args.casc)
    print(f"CASC: {os.path.expanduser(args.casc)} build {casc.build}, {len(casc.files)} files indexed")
    _, custom = parse_slk(casc.read(CUSTOM_V1))
    _, base = parse_slk(casc.read(BASE_DATA))
    _, meta_all = parse_slk(casc.read(METADATA))
    fallback = sorted(set(base) - set(custom))
    abilities = dict(custom)
    for a in fallback:
        abilities[a] = base[a]
    print(f"SLK: custom_v1 {len(custom)} abilities, base-only fallback {len(fallback)}: {' '.join(fallback)}")

    metas = [m for m in meta_all.values() if m.get("slk") == "AbilityData" and int(m.get("repeat") or 0) > 0]
    unknown_types = sorted({m["type"] for m in metas if wc3_type(m["type"]) is None})
    if unknown_types:
        sys.exit(f"ERROR: unmapped metadata types (decide Int/String/...): {unknown_types}")
    indexed = [m["ID"] for m in metas if (m.get("index") or "-1").strip() not in ("-1", "")]
    if indexed:
        sys.exit(f"ERROR: per-level AbilityData fields with an index (sub-value) are unsupported: {indexed}")

    # ---- what the maps already store (validation + tie-breaks for shared columns)
    per_level_ids = {m["ID"] for m in metas}
    observed = []                     # (dump, object, base, field, pointer, type)
    observed_fields = {}              # base -> {field}
    for dump in args.observed:
        with open(dump, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["Type"] != "Ability" or int(r["Level"]) == 0 or r["Field"] not in per_level_ids:
                    continue
                observed.append((os.path.basename(dump), r["ObjectCode"], r["BaseCode"], r["Field"],
                                 int(r["Pointer"]), r["Type2"]))
                observed_fields.setdefault(r["BaseCode"], set()).add(r["Field"])

    problems, notes = [], []
    rows = []                         # (alias, field, pointer, type, value)
    applies = {}                      # alias -> {field: (pointer, type)}
    carried = []                      # (alias, field, L1..4 cells) whose level-4 cell is blank
    for alias in sorted(abilities):
        rec = abilities[alias]
        code = rec.get("code", alias)
        by_col = {}
        applies[alias] = {}
        for m in metas:
            if not applicable(m, alias, code):
                continue
            col = column_for(m)
            if col + "1" not in rec:
                continue              # column doesn't exist in this SLK (e.g. DataJ in the overlays)
            by_col.setdefault(col, []).append(m)
            applies[alias][m["ID"]] = (int(m["data"] or 0), wc3_type(m["type"]))
        for col, ms in sorted(by_col.items()):
            if len(ms) > 1:
                seen = [m for m in ms if m["ID"] in observed_fields.get(alias, ())]
                pick = sorted(seen or ms, key=lambda m: m["ID"])[0]
                notes.append(f"{alias}: column {col} is shared by {', '.join(sorted(m['ID'] for m in ms))}; filling as {pick['ID']}")
            else:
                pick = ms[0]
            typ = wc3_type(pick["type"])
            cells = [rec.get(f"{col}{lv}") for lv in (1, 2, 3, 4)]
            # The level-4 cell itself: a blank cell reads 0/empty in 2.0.4 too (no carry-forward).
            effective = None if is_empty(cells[3]) else cells[3]
            if is_empty(cells[3]) and any(not is_empty(v) for v in cells[:3]):
                carried.append((alias, pick["ID"], cells))
            if pick["type"] == "targetList" and effective is None:
                rows.append((alias, pick["ID"], int(pick["data"] or 0), typ, "_"))   # default targets, see above
                continue
            try:
                val = normalize(effective, typ, notes, f"{alias} {pick['ID']}")
            except ValueError as e:
                problems.append(f"{alias} {pick['ID']} ({col}): {e}")
                continue
            if val is not None:
                rows.append((alias, pick["ID"], int(pick["data"] or 0), typ, val))

    field_ptrs = {}
    for fields in applies.values():
        for fid, (ptr, _) in fields.items():
            field_ptrs.setdefault(fid, set()).add(ptr)
    multi_ptr = {f: p for f, p in field_ptrs.items() if len(p) > 1}
    if multi_ptr:
        problems.append(f"field ids with more than one pointer: {multi_ptr}")
    unknown_bases = {}
    for dump, obj, b, f, ptr, type2 in observed:
        if b not in applies:
            unknown_bases.setdefault(b, set()).add(obj)
            continue
        if f not in applies[b]:
            problems.append(f"{dump}: {obj} (base {b}) sets {f} which metadata says does not apply")
            continue
        p, typ = applies[b][f]
        if ptr != p or typ != type2:
            problems.append(f"{dump}: {obj} {f}: map has {type2}/P{ptr}, metadata says {typ}/P{p}")
    for b, objs in sorted(unknown_bases.items()):
        notes.append(f"base {b} is not a Blizzard ability ({len(objs)} object(s), e.g. {sorted(objs)[0]}): no defaults exist, skipped")
    print(f"VALIDATE: {len(observed)} existing per-level ability cells checked across {len(args.observed)} dump(s)")

    # ---- gate report: the in-game confirmed Warden cases must resolve to real values
    lookup = {(r[0], r[1]): r[4] for r in rows}
    print("GATE (value in effect at level 4, used for 5+):")
    for alias, fid in [("AEfk", "amcs"), ("AEfk", "acdn"), ("AEsh", "amcs"), ("AEsh", "acdn"), ("AEbl", "aran"), ("AHbz", "atar")]:
        print(f"  {alias} {fid}: {lookup.get((alias, fid))}")
    print(f"  fields with a blank level-4 cell but a value at a lower level (NOT filled: 0 at levels 4+ in 2.0.4 too): {len(carried)}")
    for a, f, cells in carried[:5]:
        print(f"    {a} {f}: L1..4 = {cells}")
    for n in notes:
        print("NOTE:", n)

    if problems:
        for p in problems[:60]:
            print("PROBLEM:", p, file=sys.stderr)
        sys.exit(f"ERROR: {len(problems)} validation problem(s) — {args.out} NOT written")
    if any(lookup.get(k) is None for k in [("AEfk", "amcs"), ("AEsh", "amcs"), ("AEsh", "acdn"), ("AEbl", "aran")]):
        sys.exit("ERROR: a confirmed Warden default resolved to nothing — the fill rule would not fix the known bug")
    if lookup.get(("AHbz", "atar")) != "_":
        sys.exit("ERROR: Blizzard's level-5+ targets did not resolve to the default token '_' — Blizzard L5/L6 would hit nothing")

    with_rows = {r[0] for r in rows}
    buf = io.StringIO()
    buf.write("# Pre-3.0 ability defaults in effect at level 4, applied to unset levels 5+ by tools/shared/AbilityLevelFill.cs.\n")
    buf.write(f"# Source: local CASC Warcraft III {casc.build}; {CUSTOM_V1} (TFT + game data set Custom),\n")
    buf.write(f"#   fallback {BASE_DATA} for: {' '.join(fallback)}; metadata {METADATA}.\n")
    buf.write("# Generated by tools/slk/extract_ability_defaults.py (make level-defaults). Do not edit by hand.\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["BaseCode", "Field", "Pointer", "Type", "Value"])
    for row in sorted(rows, key=lambda r: (r[0], r[1])):
        w.writerow(row)
    for alias in sorted(set(abilities) - with_rows):
        w.writerow([alias, "", "", "", ""])     # known base, nothing to fill
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        fh.write(buf.getvalue())
    print(f"WROTE {args.out}: {len(rows)} default cell(s) for {len(with_rows)} of {len(abilities)} abilities")


if __name__ == "__main__":
    main()
