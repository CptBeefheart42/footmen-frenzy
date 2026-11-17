#!/usr/bin/env python3
"""Data for the e2e `skills` scenario: every hero skill of a map, with the numbers the map stores for it.

    tests/e2e/gen_skills.py --dump <dumpall --fill CSV of the base map> --overrides <csv>[;<csv>...]
                            --orders tests/e2e/ability_orders.csv[;...] --out <stage>/map/05-e2e-skills-data.j
                            --expect <stage>/skills_expect.json

The dump is BalanceTool's `dumpall --fill` of the base map: the object data as the build ships it (with the WC3
3.0 level fill). The build's map fixes (FF_OBJECT_OVERRIDES rows) are applied on top, the same way the build does.
Hero skills are the abilities in any hero's `uhab` field. For each one the map's w3a holds:

  * every numeric cell (Int / Real / Unreal) at levels 1..N: the scenario reads it back from the engine
    (BlzGetAbility{Integer,Real,Boolean}LevelField) and records only the cells that differ;
  * its base ability's order strings (ability_orders.csv, from the test client's game data): the scenario casts it
    once per level and records whether the order was accepted, the effect, the mana spent and the cooldown started.

skills_expect.json holds what the checker compares the casts with: per ability and level the map's `amcs` (mana)
and `acdn` (cooldown) where the map stores them, the target list, and whether the base ability has an order.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

CHUNK = 300          # calls per generated function (the JASS op limit)
NUMERIC = {"Int": 0, "Real": 1, "Unreal": 1}

JASS_HEADER = """globals
    integer FF_SK_n = 0
    integer array FF_SK_aId
    integer array FF_SK_aHero
    integer array FF_SK_aLevels
    string array FF_SK_aOrder
    string array FF_SK_aOrderOn
    integer array FF_SK_aCell0
    integer array FF_SK_aCellN
    integer FF_SK_c = 0
    integer array FF_SK_cField
    integer array FF_SK_cLevel
    boolean array FF_SK_cReal
    integer array FF_SK_cInt
    real array FF_SK_cRealV
    integer FF_SK_chunks = 0
endglobals

function FF_SK_Abil takes integer id, integer hero, integer levels, string order, string orderon returns nothing
    set FF_SK_aId[FF_SK_n] = id
    set FF_SK_aHero[FF_SK_n] = hero
    set FF_SK_aLevels[FF_SK_n] = levels
    set FF_SK_aOrder[FF_SK_n] = order
    set FF_SK_aOrderOn[FF_SK_n] = orderon
    set FF_SK_aCell0[FF_SK_n] = FF_SK_c
    set FF_SK_aCellN[FF_SK_n] = FF_SK_c
    set FF_SK_n = FF_SK_n + 1
endfunction

function FF_SK_CellI takes integer field, integer level, integer v returns nothing
    set FF_SK_cField[FF_SK_c] = field
    set FF_SK_cLevel[FF_SK_c] = level
    set FF_SK_cReal[FF_SK_c] = false
    set FF_SK_cInt[FF_SK_c] = v
    set FF_SK_c = FF_SK_c + 1
    set FF_SK_aCellN[FF_SK_n - 1] = FF_SK_c
endfunction

function FF_SK_CellR takes integer field, integer level, real v returns nothing
    set FF_SK_cField[FF_SK_c] = field
    set FF_SK_cLevel[FF_SK_c] = level
    set FF_SK_cReal[FF_SK_c] = true
    set FF_SK_cRealV[FF_SK_c] = v
    set FF_SK_c = FF_SK_c + 1
    set FF_SK_aCellN[FF_SK_n - 1] = FF_SK_c
endfunction
"""


def read_csv_rows(path):
    """The lines of a CSV file without blank lines and `#` comments."""
    with open(path, encoding="utf-8") as fh:
        return [line for line in fh if line.strip() and not line.lstrip().startswith("#")]


def load_orders(paths):
    """Reads ability_orders.csv files (`code,order,orderon,orderoff,unorder`).

    Args:
        paths: The files; the first one that lists a code wins.

    Returns:
        Base ability code to its row (a dict).
    """
    orders = {}
    for p in paths:
        for r in csv.DictReader(read_csv_rows(p)):
            orders.setdefault(r["code"], r)
    return orders


def jstr(s):
    """A JASS string literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def jreal(x):
    """A JASS real literal (always with a decimal point, never in exponent notation)."""
    s = repr(float(x))
    if "e" in s or "E" in s:
        s = f"{float(x):.6f}"
    return s if "." in s else s + ".0"


@dataclass
class ObjectData:
    """The hero skills' data from a map dump.

    Attributes:
        cells: Ability code to {(field, level): (type, value)}.
        base: Ability code to its base ability code.
        heroes: Hero unit code to its skills (`uhab`).
    """

    cells: dict = field(default_factory=lambda: defaultdict(dict))
    base: dict = field(default_factory=dict)
    heroes: dict = field(default_factory=dict)

    @classmethod
    def load(cls, dump):
        """Reads BalanceTool's `dumpall` CSV (ObjectCode, BaseCode, Type, Field, Level, Type2, Value columns)."""
        data = cls()
        with open(dump, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["Type"] == "Unit" and r["Field"] == "uhab":
                    data.heroes[r["ObjectCode"]] = [x for x in r["Value"].split(",") if x]
                elif r["Type"] == "Ability":
                    data.base[r["ObjectCode"]] = r["BaseCode"]
                    data.cells[r["ObjectCode"]][(r["Field"], int(r["Level"]))] = (r["Type2"], r["Value"])
        return data

    def apply_overrides(self, path):
        """Applies a map-fix file (`Object,Field,Level,Pointer,Type,Value`) to the abilities the dump holds.

        A value `<unset>` removes the cell; `<new>` rows (objects the build creates) are skipped.
        """
        for line in read_csv_rows(path):
            obj, fld, level, _ptr, typ, value = line.rstrip("\n").split(",", 5)
            if fld == "<new>" or obj not in self.cells:
                continue
            if value == "<unset>":
                self.cells[obj].pop((fld, int(level)), None)
            else:
                self.cells[obj][(fld, int(level))] = (typ, value)

    def skill_owners(self):
        """Every hero skill to the first hero (by code) that has it."""
        owner = {}
        for h in sorted(self.heroes):
            for ab in self.heroes[h]:
                owner.setdefault(ab, h)
        return owner

    def levels(self, ab):
        """The skill's level count: its `alev` cell, else the highest level any cell has."""
        c = self.cells[ab]
        lev = c.get(("alev", 0))
        return int(lev[1]) if lev and lev[0] == "Int" else max([lv for _, lv in c] + [1])

    def order(self, ab, orders):
        """The skill's order strings (order, orderon).

        A Channel (ANcl) copy is ordered by its own Base Order ID (`Ncl6`), not by `channel`.
        """
        o = orders.get(self.base[ab], {})
        order, orderon = o.get("order", ""), o.get("orderon", "")
        if self.base[ab] == "ANcl":
            ncl6 = self.cells[ab].get(("Ncl6", 1))
            if ncl6 and ncl6[1]:
                order, orderon = ncl6[1], ""
        return order, orderon


def skill_calls(data, ab, owner, orders):
    """The JASS calls that register one skill and its numeric cells, and its entry in skills_expect.json.

    Returns:
        (calls, number of cells, expectation dict).
    """
    c, levels = data.cells[ab], data.levels(ab)
    order, orderon = data.order(ab, orders)
    calls = [f"call FF_SK_Abil('{ab}', '{owner}', {levels}, {jstr(order)}, {jstr(orderon)})"]
    num = sorted(((f, lv, t, v) for (f, lv), (t, v) in c.items() if 1 <= lv <= levels and t in NUMERIC and len(f) == 4),
                 key=lambda x: (x[1], x[0]))
    for f, lv, t, v in num:
        if NUMERIC[t] == 0:
            calls.append(f"call FF_SK_CellI('{f}', {lv}, {int(float(v))})")
        else:
            calls.append(f"call FF_SK_CellR('{f}', {lv}, {jreal(v)})")
    lv_exp = {}
    for lv in range(1, levels + 1):
        m, cd, tgt = c.get(("amcs", lv)), c.get(("acdn", lv)), c.get(("atar", lv))
        lv_exp[lv] = {"amcs": int(float(m[1])) if m else None, "acdn": float(cd[1]) if cd else None,
                      "atar": tgt[1] if tgt else None}
    exp = {"hero": owner, "base": data.base[ab], "levels": levels, "order": order or orderon, "lv": lv_exp}
    return calls, len(num), exp


def emit_jass(calls, abils, ncells, missing, cast_after, host_click):
    """The generated JASS file: the data functions, cut into chunks, plus the scenario's settings.

    Returns:
        (the file's text, the number of chunks).
    """
    out = ["// generated by tests/e2e/gen_skills.py — the e2e `skills` scenario's data (never in a release map)",
           f"// {len(abils)} hero skills, {ncells} numeric cells"
           + (f"; not in the map's w3a: {' '.join(missing)}" if missing else ""),
           JASS_HEADER]
    chunks = [calls[i:i + CHUNK] for i in range(0, len(calls), CHUNK)]
    for i, ch in enumerate(chunks):
        out += [f"function FF_SK_Data{i} takes nothing returns nothing"] + ["    " + c for c in ch] + ["endfunction", ""]
    out += ["// one chunk per call (each in its own thread: the op limit); FF_SK_chunks = how many",
            "function FF_SK_LoadChunk takes integer i returns nothing"]
    for i in range(len(chunks)):
        out += [f"    {'if' if i == 0 else 'elseif'} i == {i} then", f"        call FF_SK_Data{i}()"]
    if chunks:
        out.append("    endif")
    out += ["endfunction", "",
            "function FF_SK_Chunks takes nothing returns integer", f"    return {len(chunks)}", "endfunction", "",
            "function FF_SK_CastAfter takes nothing returns integer", f"    return {cast_after}", "endfunction", "",
            "// the client is the host (Player 0): its game-type dialog, per map",
            "function FF_E2E_HostClick takes nothing returns string", f"    return {jstr(host_click)}", "endfunction"]
    return "\n".join(out) + "\n", len(chunks)


def main(argv=None):
    """Writes the scenario's data file and its expectations.

    Args:
        argv: The command line (default: sys.argv[1:]).
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--overrides", default="")
    ap.add_argument("--orders", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect", required=True)
    ap.add_argument("--host-click", default="", help="the host's game-type dialog click (\"<x> <y>\"), per map")
    ap.add_argument("--cast-after", type=int, default=10,
                    help="game seconds before the first cast (Solo refuses orders before 90)")
    a = ap.parse_args(argv)

    data = ObjectData.load(a.dump)
    for p in filter(None, a.overrides.split(";")):
        data.apply_overrides(p)
    orders = load_orders(a.orders.split(";"))
    owner = data.skill_owners()
    abils = sorted(ab for ab in owner if ab in data.cells)
    missing = sorted(ab for ab in owner if ab not in data.cells)
    calls, expect, ncells = [], {}, 0
    for ab in abils:
        ab_calls, n, expect[ab] = skill_calls(data, ab, owner[ab], orders)
        calls += ab_calls
        ncells += n
    text, nchunks = emit_jass(calls, abils, ncells, missing, a.cast_after, a.host_click)
    Path(a.out).write_text(text)
    Path(a.expect).write_text(json.dumps({"abilities": expect, "missing": missing, "cells": ncells}, indent=1,
                                         sort_keys=True))
    print(f"gen_skills: {len(abils)} hero skills, {ncells} cells, {nchunks} chunks -> {a.out}"
          + (f" ({len(missing)} not in the w3a: {' '.join(missing)})" if missing else ""))


if __name__ == "__main__":
    sys.exit(main())
