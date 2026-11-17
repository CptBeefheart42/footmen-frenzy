#!/usr/bin/env python3
"""Generate the data addon of the WC3 3.0 probe map (ff e2e probe; never released).

Why: WC3 3.0 reads some of our maps' object data differently than 2.0.4 did (unset levels 5+ read 0,
negative values reportedly ignored, out-of-range/blank values reportedly reset to defaults). Player
reports are vague, so the probe map reads back what the 3.0 engine actually loaded, with the natives
BlzGetAbility{Integer,Real,Boolean}LevelField, and compares it with what 2.0.4 used.

Writes one JASS file (a map addon, see tests/e2e/probe/) with `call FF_PB_Add(...)` rows:
  class 0 CTRL_X  explicitly set, valid value (one per ability/field — proves the field is readable)
  class 1 CTRL_S  unset at a level <= the base ability's SLK level count (SLK default, readable check)
  class 2 NEG     negative value in a field whose metadata minimum is >= 0
  class 3 BELOW   non-negative value below the metadata minimum
  class 4 ABOVE   value above the metadata maximum
  class 5 FILL    cell added by the build's level fill (levels above the base level count)
  class 6 GAP     unset, unfilled level between the base ability's SLK level count and 4 (expected: SLK value)
For each row the 3.0 "reset to default" value is also stored (SLK value at levels <= 4, 0 above),
so the probe can tell "read 0" from "read the default" from "read something else".

Plus FF_PB_Restore rows (the ward auras' out-of-range values, for the script-restore test),
FF_PB_UnitField rows (unit regen / bounty values outside the limits) and FF_PB_UnitAbil rows
(units whose ability list is explicitly blank: does 3.0 give them the base unit's defaults?).

usage: gen_probe.py --casc ~/wc3-stage --raw dump.csv --filled dump_fill.csv --out 60-probe-data.j
"""
import argparse
import collections
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "slk"))
import extract_ability_defaults as slkx  # noqa: E402

# The Death Ward chain (both maps' wards; A0F1/A0FG are the Solo ward's auras, present in main too) and Blizzard.
EXTRA_ABILITIES = ["AHbz", "A0FD", "A0F0", "A0IP", "A0F6", "A0F1", "A0FG"]
RESTORE_ABILITIES = ["A0F0", "A0F1", "A0FG"]
UNIT_FIELDS = ["uhpr", "umpr", "ulbs"]
CHUNK = 350

CTRL_X, CTRL_S, NEG, BELOW, ABOVE, FILL, GAP = range(7)


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def jreal(x):
    t = f"{x:.6f}".rstrip("0").rstrip(".")
    if t in ("", "-", "-0"):
        t = "0"
    return t if "." in t else t + ".0"


def load_dump(path):
    cells = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        cells[(r["Type"], r["ObjectCode"], r["Field"], int(r["Level"]))] = (r["BaseCode"], r["Type2"], r["Value"])
    return cells


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--casc", default="~/wc3-stage")
    ap.add_argument("--raw", required=True, help="dumpall of the base map (no level fill)")
    ap.add_argument("--filled", required=True, help="dumpall --fill of the same map (= what rc4 ships)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    casc = slkx.Casc(args.casc)
    _, custom = slkx.parse_slk(casc.read(slkx.CUSTOM_V1))
    _, base = slkx.parse_slk(casc.read(slkx.BASE_DATA))
    slk = dict(base)
    slk.update(custom)
    _, ameta_all = slkx.parse_slk(casc.read(slkx.METADATA))
    ametas = [m for m in ameta_all.values() if m.get("slk") == "AbilityData" and int(m.get("repeat") or 0) > 0 and len(m["ID"]) == 4]
    _, umeta = slkx.parse_slk(casc.read("war3.w3mod:units/unitmetadata.slk"))
    unit_slk = {}
    for name in ("unitbalance", "unitdata", "unitweapons", "unitabilities"):
        _, rows = slkx.parse_slk(casc.read(f"war3.w3mod:_balance/custom_v1.w3mod:units/{name}.slk"))
        unit_slk[name] = {k: {c.lower(): v for c, v in r.items()} for k, r in rows.items()}

    raw = load_dump(args.raw)
    filled = load_dump(args.filled)

    abil_base, abil_levels = {}, {}
    owners = collections.defaultdict(set)
    for (typ, obj, field, level), (b, t2, v) in filled.items():
        if typ == "Ability":
            abil_base[obj] = b
            if field == "alev" and level == 0:
                abil_levels[obj] = int(v)
        elif typ == "Unit" and field in ("uhab", "uabi"):
            for a in v.split(","):
                if a.strip():
                    owners[a.strip()].add((obj, field == "uhab"))

    def limits(m):
        return num(m.get("minVal")), num(m.get("maxVal"))

    def out_of_limits(v, m):
        lo, hi = limits(m)
        if v < 0 and (lo is None or lo >= 0):
            return NEG
        if lo is not None and v < lo:
            return BELOW
        if hi is not None and v > hi:
            return ABOVE
        return None

    selected = {a for a, os_ in owners.items() if any(h for _, h in os_) and a in abil_base}
    selected |= {a for a in EXTRA_ABILITIES if a in abil_base}
    # any ability (unit-owned too) that stores a value outside the limits
    for (typ, obj, field, level), (b, t2, v) in raw.items():
        if typ != "Ability" or level == 0 or t2 == "String":
            continue
        m = ameta_all.get(field)
        x = num(v)
        if m is not None and x is not None and out_of_limits(x, m) is not None:
            selected.add(obj)

    rows, skipped_strings, unknown_bases = [], 0, set()
    for obj in sorted(selected):
        b = abil_base[obj]
        rec = slk.get(b)
        if rec is None:
            unknown_bases.add(f"{obj}/{b}")
            continue
        slk_levels = max(1, int(rec.get("levels") or 1))
        levels = abil_levels.get(obj, slk_levels)
        for m in sorted(ametas, key=lambda m: m["ID"]):
            if not slkx.applicable(m, b, rec.get("code", b)):
                continue
            col = slkx.column_for(m)
            if col + "1" not in rec:
                continue
            typ = slkx.wc3_type(m["type"])
            if typ is None or typ == "String":
                skipped_strings += 1
                continue
            kind = 2 if m["type"] == "bool" else (0 if typ == "Int" else 1)

            def slk_value(level):  # the SLK cell at that level (level 4 for 5+); blank = 0, no carry-forward
                cell = rec.get(f"{col}{min(level, 4)}")
                x = None if slkx.is_empty(cell) else num(cell)
                if x is None:
                    return 0.0
                return float(int(x)) if typ == "Int" else x

            def default_30(level):  # what a "reset to default" reads on 3.0: the SLK column, 0 above level 4
                return slk_value(level) if level <= 4 else 0.0

            group, control, weak_control = [], None, None
            for level in range(1, levels + 1):
                key = ("Ability", obj, m["ID"], level)
                if key in raw:
                    x = num(raw[key][2])
                    if x is None:
                        continue
                    cls = out_of_limits(x, m)
                    if cls is None:
                        if x != 0 and control is None:
                            control = (obj, m["ID"], level, kind, CTRL_X, x, default_30(level))
                        elif weak_control is None:
                            weak_control = (obj, m["ID"], level, kind, CTRL_X, x, default_30(level))
                        continue
                    group.append((obj, m["ID"], level, kind, cls, x, default_30(level)))
                elif key in filled:
                    x = num(filled[key][2])
                    if x is not None:
                        group.append((obj, m["ID"], level, kind, FILL, x, default_30(level)))
                elif level <= 4:
                    x = slk_value(level)
                    if x == 0:
                        continue
                    if level > slk_levels:
                        group.append((obj, m["ID"], level, kind, GAP, x, default_30(level)))
                    elif control is None and level == 1:
                        control = (obj, m["ID"], level, kind, CTRL_S, x, default_30(level))
            if not group:
                continue
            ctrl = control or weak_control
            if ctrl is not None:
                rows.append(ctrl)
            rows.extend(group)

    restore = []
    for (typ, obj, field, level), (b, t2, v) in sorted(raw.items()):
        if typ == "Ability" and obj in RESTORE_ABILITIES and level > 0 and t2 in ("Real", "Unreal"):
            m = ameta_all.get(field)
            x = num(v)
            if m is not None and x is not None and out_of_limits(x, m) is not None:
                restore.append((obj, field, level, x))

    unit_fields = []
    per_field = collections.Counter()
    for (typ, obj, field, level), (b, t2, v) in sorted(raw.items()):
        if typ != "Unit" or field not in UNIT_FIELDS or per_field[field] >= 4:
            continue
        m = umeta.get(field)
        x = num(v)
        if m is None or x is None or out_of_limits(x, m) is None:
            continue
        src = {"UnitBalance": "unitbalance", "UnitData": "unitdata", "UnitWeapons": "unitweapons"}.get(m.get("slk"))
        d = num(unit_slk.get(src, {}).get(b, {}).get((m.get("field") or "").lower())) if src else None
        unit_fields.append((obj, field, 0 if m["type"] == "int" else 1, x, d or 0.0))
        per_field[field] += 1

    unit_abils = []
    for (typ, obj, field, level), (b, t2, v) in sorted(raw.items()):
        if typ == "Unit" and field == "uabi" and v == "" and len({u for u, _ in unit_abils}) < 8:
            defaults = [a.strip() for a in (unit_slk["unitabilities"].get(b, {}).get("abillist") or "").split(",")
                        if len(a.strip()) == 4]
            for a in defaults[:3]:
                unit_abils.append((obj, a))

    counts = collections.Counter(r[4] for r in rows)
    names = ["CTRL_X", "CTRL_S", "NEG", "BELOW", "ABOVE", "FILL", "GAP"]
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("// FF 3.0 probe — expected-value tables. GENERATED by tools/probe/gen_probe.py (ff e2e probe).\n")
        fh.write(f"// {len(rows)} ability cells on {len({r[0] for r in rows})} abilities: "
                 + ", ".join(f"{names[c]} {counts[c]}" for c in range(7))
                 + f"; {len(restore)} restore, {len(unit_fields)} unit fields, {len(unit_abils)} unit default abilities.\n")
        fh.write(f"// string fields not read back: {skipped_strings} ability/field pairs; bases without SLK data skipped: {len(unknown_bases)}\n\n")
        chunks = [rows[i:i + CHUNK] for i in range(0, len(rows), CHUNK)] or [[]]
        for n, chunk in enumerate(chunks):
            fh.write(f"function FF_PB_Data{n} takes nothing returns nothing\n")
            for a, f, lv, kind, cls, exp, dflt in chunk:
                fh.write(f"    call FF_PB_Add('{a}', '{f}', {lv}, {kind}, {cls}, {jreal(exp)}, {jreal(dflt)})\n")
            fh.write("endfunction\n\n")
        fh.write("function FF_PB_DataExtra takes nothing returns nothing\n")
        for a, f, lv, x in restore:
            fh.write(f"    call FF_PB_Restore('{a}', '{f}', {lv}, {jreal(x)})\n")
        for u, f, kind, x, d in unit_fields:
            fh.write(f"    call FF_PB_UnitField('{u}', '{f}', {kind}, {jreal(x)}, {jreal(d)})\n")
        for u, a in unit_abils:
            fh.write(f"    call FF_PB_UnitAbil('{u}', '{a}')\n")
        fh.write("endfunction\n\n")
        fh.write("function FF_PB_LoadData takes nothing returns nothing\n")
        for n in range(len(chunks)):
            fh.write(f"    call ExecuteFunc(\"FF_PB_Data{n}\")\n")
        fh.write("    call ExecuteFunc(\"FF_PB_DataExtra\")\n")
        fh.write("endfunction\n")
    print(f"PROBE DATA: {len(rows)} ability cells ({', '.join(f'{names[c]} {counts[c]}' for c in range(7))}), "
          f"{len(restore)} restore rows, {len(unit_fields)} unit fields, {len(unit_abils)} unit default abilities -> {args.out}")


if __name__ == "__main__":
    main()
