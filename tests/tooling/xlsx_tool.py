#!/usr/bin/env python3
"""Tiny xlsx helper for the build-chain integration tests.

Used to mutate fixture workbooks (simulate a team edit) and to assert on the
output of `balancetool reconcile`. Keeps the bash test readable.

Subcommands:
  set   <xlsx> <tab> <code> <colHeader> <value>   set a numeric cell, save in place
  get   <xlsx> <tab> <code> <colHeader>           print the cell value
  getlvl <xlsx> <tab> <code> <level> <colHeader>   print the cell value on that Level row
  setlvl <xlsx> <tab> <code> <level> <colHeader> <value>  set a numeric cell on that Level row
  hasrow<xlsx> <tab> <code>                        exit 0 if a data row has Code==code
  outdated <xlsx>                                  print count of rows flagged OUTDATED
  tabs  <xlsx>                                     print tab names, one per line
"""
import sys
import openpyxl

OUTDATED_MARK = "OUTDATED"


def _headers(ws):
    """Return {header_text: column_index} from row 1."""
    out = {}
    for cell in ws[1]:
        if cell.value is not None:
            out[str(cell.value).strip()] = cell.column
    return out


def _code_col(ws):
    return _headers(ws).get("Code")


def cmd_set(path, tab, code, header, value):
    wb = openpyxl.load_workbook(path)
    ws = wb[tab]
    hdr = _headers(ws)
    ccol, vcol = hdr["Code"], hdr[header]
    for row in ws.iter_rows(min_row=2):
        if row[ccol - 1].value and str(row[ccol - 1].value).strip() == code:
            ws.cell(row=row[0].row, column=vcol).value = float(value)
            wb.save(path)
            return 0
    print(f"set: no row with Code={code} in tab {tab}", file=sys.stderr)
    return 1


def cmd_get(path, tab, code, header):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[tab]
    hdr = _headers(ws)
    ccol, vcol = hdr["Code"], hdr[header]
    for row in ws.iter_rows(min_row=2):
        if row[ccol - 1].value and str(row[ccol - 1].value).strip() == code:
            print(row[vcol - 1].value)
            return 0
    print(f"get: no row with Code={code} in tab {tab}", file=sys.stderr)
    return 1


def _level_row(ws, code, level):
    hdr = _headers(ws)
    ccol, lcol = hdr["Code"], hdr["Level"]
    for row in ws.iter_rows(min_row=2):
        c, lv = row[ccol - 1].value, row[lcol - 1].value
        if c is not None and str(c).strip() == code and lv is not None and int(float(lv)) == int(level):
            return row
    return None


def cmd_getlvl(path, tab, code, level, header):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[tab]
    row = _level_row(ws, code, level)
    if row is None:
        print(f"getlvl: no row with Code={code} Level={level} in tab {tab}", file=sys.stderr)
        return 1
    v = row[_headers(ws)[header] - 1].value
    print("" if v is None else v)
    return 0


def cmd_setlvl(path, tab, code, level, header, value):
    wb = openpyxl.load_workbook(path)
    ws = wb[tab]
    row = _level_row(ws, code, level)
    if row is None:
        print(f"setlvl: no row with Code={code} Level={level} in tab {tab}", file=sys.stderr)
        return 1
    ws.cell(row=row[0].row, column=_headers(ws)[header]).value = float(value)
    wb.save(path)
    return 0


def cmd_hasrow(path, tab, code):
    """Exit 0 if a data row has Code==code. tab='*' searches every tab."""
    wb = openpyxl.load_workbook(path, read_only=True)
    sheets = wb.worksheets if tab == "*" else [wb[tab]]
    for ws in sheets:
        ccol = _code_col(ws)
        if ccol is None:
            continue
        for row in ws.iter_rows(min_row=2):
            if row[ccol - 1].value and str(row[ccol - 1].value).strip() == code:
                return 0
    return 1


def cmd_outdated(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    n = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None and OUTDATED_MARK in str(c.value):
                    n += 1
                    break
    print(n)
    return 0


def cmd_tabs(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    for name in wb.sheetnames:
        print(name)
    return 0


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, rest = argv[1], argv[2:]
    fns = {
        "set": cmd_set, "get": cmd_get, "getlvl": cmd_getlvl, "setlvl": cmd_setlvl, "hasrow": cmd_hasrow,
        "outdated": cmd_outdated, "tabs": cmd_tabs,
    }
    if cmd not in fns:
        print(f"unknown subcommand: {cmd}", file=sys.stderr)
        return 2
    return fns[cmd](*rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
