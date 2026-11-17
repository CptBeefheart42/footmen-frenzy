#!/usr/bin/env python3
"""The order strings of WC3's base abilities, for the e2e `skills` scenario (it casts every hero skill by its base
ability's order) -> tests/e2e/ability_orders.csv (committed: CI has no WC3 install).

    tests/e2e/gen_orders.py [--client <Warcraft III install>] [--out tests/e2e/ability_orders.csv]

Reads the test client's own game data, read-only: the `_balance/custom_v1` set the maps load, then the common
files. In `units/*abilityfunc.txt`, each `[<code>]` section's Order= / Orderon= / Orderoff= / Unorder= lines. The
pre-3.0 install (~/wc3-stage) is never used: order strings are no balance data, and the test client is the 3.0 the
scenario runs on.

CSV columns: code,order,orderon,orderoff,unorder
"""
import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.common.paths import E2E_DIR, REPO, WC3_INSTALL, default_client, refuse_stage  # noqa: E402

sys.path.insert(0, str(REPO / "tools" / "slk"))
from extract_ability_defaults import Casc  # noqa: E402

SETS = ["war3.w3mod:_balance/custom_v1.w3mod:units/", "war3.w3mod:units/", "war3.w3mod:_balance/custom_v0.w3mod:units/",
        "war3.w3mod:_balance/melee_v0.w3mod:units/"]
FILES = ["humanabilityfunc.txt", "orcabilityfunc.txt", "undeadabilityfunc.txt", "nightelfabilityfunc.txt",
         "neutralabilityfunc.txt", "itemabilityfunc.txt", "commonabilityfunc.txt", "campaignabilityfunc.txt"]
KEYS = ("Order", "Orderon", "Orderoff", "Unorder")
_SECTION = re.compile(r"\[(\w{4})\]")
_ORDER = re.compile(r"(Order|Orderon|Orderoff|Unorder)=(\w+)")


def parse_orders(text, orders):
    """Adds the order strings of one abilityfunc.txt to `orders`; a code's first value for a key wins.

    Args:
        text: The file's content.
        orders: Ability code to {key: order string}, updated in place.
    """
    cur = None
    for line in text.splitlines():
        m = _SECTION.match(line)
        if m:
            cur = m.group(1)
            continue
        m = _ORDER.match(line)
        if cur and m and m.group(1) not in orders.get(cur, {}):
            orders.setdefault(cur, {})[m.group(1)] = m.group(2)


def read_orders(casc):
    """Collects the order strings from the client's game data, the balance set first.

    Args:
        casc: The client's CASC storage (tools/slk/extract_ability_defaults.Casc).

    Returns:
        Ability code to {key: order string}.
    """
    orders = {}
    for prefix in SETS:
        for f in FILES:
            path = prefix + f
            if path not in casc.files:
                continue
            try:
                parse_orders(casc.read(path).decode("utf-8", "replace"), orders)
            except KeyError:
                continue                          # not downloaded locally (another set's copy covers it)
    return orders


def write_csv(orders, out):
    """Writes ability_orders.csv."""
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "order", "orderon", "orderoff", "unorder"])
        for code in sorted(orders):
            w.writerow([code] + [orders[code].get(k, "") for k in KEYS])


def main(argv=None):
    """Regenerates the CSV from the test client.

    Args:
        argv: The command line (default: sys.argv[1:]).
    """
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", type=Path, default=default_client() / WC3_INSTALL)
    ap.add_argument("--out", type=Path, default=E2E_DIR / "ability_orders.csv")
    a = ap.parse_args(argv)
    refuse_stage(a.client, "gen_orders")
    orders = read_orders(Casc(str(a.client.expanduser())))
    write_csv(orders, a.out)
    print(f"gen_orders: {len(orders)} abilities -> {a.out}")


if __name__ == "__main__":
    main()
