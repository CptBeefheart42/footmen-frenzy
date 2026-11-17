"""Reading and rewriting the files the map writes with WC3's `Preload` native.

Every file the map writes into `CustomMapData/` is a Preload file: a small JASS function whose lines look like
`call Preload( "<row>" )`. The rows are the data; everything else is the wrapper WC3 adds.
"""
import re
from pathlib import Path

PREFIX = 'call Preload( "'
SUFFIX = '" )'
_ROW_LINE = re.compile(r'(\s*call Preload\( ")(.*)(" \)\s*)$')


def parse_rows(text):
    """Extracts the rows of a Preload file's text.

    Args:
        text: The file's content.

    Returns:
        The rows, in file order, without the `call Preload( "..." )` wrapper.
    """
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(PREFIX) and line.endswith(SUFFIX):
            rows.append(line[len(PREFIX):-len(SUFFIX)])
    return rows


def read_rows(path):
    """Reads the rows of a Preload file.

    Args:
        path: The file to read.

    Returns:
        The rows in file order, or None when the file cannot be read (missing, unreadable).
    """
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return None
    return parse_rows(text)


def rewrite_rows(path, fn):
    """Rewrites every row of a Preload file in place; the wrapper lines are kept as they are.

    Args:
        path: The file to rewrite.
        fn: Called with each row; returns the new row, or None to drop it.
    """
    path = Path(path)
    out = []
    for line in path.read_text(errors="replace").splitlines(keepends=True):
        m = _ROW_LINE.match(line)
        if not m:
            out.append(line)
            continue
        new = fn(m.group(2))
        if new is not None:
            out.append(m.group(1) + new + m.group(3))
    path.write_text("".join(out))
