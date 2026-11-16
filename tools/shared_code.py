"""Code that several maps share, written once under `shared/` and placed into each map's script at build time.

A map's `src/war3map.j` refers to a shared file with a marker line:

    //! shared ff-config/functions.j

The build replaces every marker line with the bytes of that file (`assemble`), so the packed map holds a complete
script. `extract` moves code that is byte-identical in several maps into `shared/` and leaves markers behind; it only
writes when assembling the edited scripts gives back the original bytes, so extracting never changes a map.
`duplicates` counts functions that are still copied between map scripts; `check` fails when that count grows, so new
copies go into `shared/` instead of being pasted into every map.

Usage:
    python tools/shared_code.py assemble <project> [-o <file>]
    python tools/shared_code.py extract <name> --functions A,B [--globals X,Y] [--projects 799x,solo]
    python tools/shared_code.py modules
    python tools/shared_code.py duplicates
    python tools/shared_code.py check [--update-baseline]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / 'shared'
BASELINE = SHARED / 'duplicates-baseline.json'
PROJECTS = tuple(sorted(p.name for p in (ROOT / 'projects').iterdir() if (p / 'src' / 'war3map.j').is_file()))

MARKER = re.compile(rb'^//! shared ([A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+\.j)(\r?\n|$)', re.M)
FUNCTION = re.compile(rb'^function (\w+)\b.*?^[ \t]*endfunction[^\r\n]*(?:\r?\n|$)', re.M | re.S)


class SharedCodeError(Exception):
    """A shared file is missing, or code meant to be shared differs between maps."""


def script_path(project: str) -> Path:
    """Returns the path of a project's editable map script.

    Args:
        project: Project folder name under `projects/`, e.g. `799x`.

    Returns:
        Path to `projects/<project>/src/war3map.j`.
    """
    return ROOT / 'projects' / project / 'src' / 'war3map.j'


def assemble(script: bytes, shared_root: Path = SHARED, pending: dict[str, bytes] | None = None) -> bytes:
    """Replaces every marker line of a script with the shared file it names.

    Args:
        script: A map script that may contain `//! shared <module>/<file>.j` lines.
        shared_root: Folder holding the shared modules.
        pending: Shared files not written yet, keyed by `<module>/<file>.j`; they win over files on disk.

    Returns:
        The complete script, ready to pack into the map.

    Raises:
        SharedCodeError: A marker names a file that does not exist.
    """
    def insert(match: re.Match) -> bytes:
        if pending and match[1].decode() in pending:
            return pending[match[1].decode()]
        path = shared_root / match[1].decode()
        if not path.is_file():
            raise SharedCodeError(f'missing shared file: {path.relative_to(shared_root.parent)}')
        return path.read_bytes()
    return MARKER.sub(insert, script)


@dataclass
class Span:
    """A byte range of a script that holds code to be shared."""
    start: int
    end: int


def _global_span(script: bytes, name: str) -> Span:
    """Finds the one line inside the globals block that declares `name`."""
    block = re.search(rb'^globals\r?\n(.*?)^endglobals', script, re.M | re.S)
    if not block:
        raise SharedCodeError('script has no globals block')
    pattern = rb'^[ \t]*(?:constant[ \t]+)?\w+[ \t]+(?:array[ \t]+)?' + re.escape(name.encode()) + rb'\b[^\r\n]*\r?\n'
    found = list(re.finditer(pattern, script[:block.end(1)][block.start(1):], re.M))
    if len(found) != 1:
        raise SharedCodeError(f'global {name}: expected one declaration, found {len(found)}')
    return Span(block.start(1) + found[0].start(), block.start(1) + found[0].end())


def _function_span(script: bytes, name: str) -> Span:
    """Finds a function from its `function` line to its `endfunction` line."""
    found = [m for m in FUNCTION.finditer(script) if m[1] == name.encode()]
    if len(found) != 1:
        raise SharedCodeError(f'function {name}: expected one definition, found {len(found)}')
    return Span(found[0].start(), found[0].end())


def _contiguous(script: bytes, spans: list[Span], what: str) -> Span:
    """Joins spans that follow each other with only blank lines between them into one span."""
    spans = sorted(spans, key=lambda s: s.start)
    for before, after in zip(spans, spans[1:]):
        if script[before.end:after.start].strip():
            raise SharedCodeError(f'{what} are not next to each other; extract them one by one')
    return Span(spans[0].start, spans[-1].end)


def _replace(script: bytes, span: Span, marker: bytes) -> bytes:
    newline = b'\r\n' if script[span.start:span.end].endswith(b'\r\n') else b'\n'
    return script[:span.start] + marker + newline + script[span.end:]


def extract(name: str, functions: list[str], globals_: list[str], scripts: dict[str, bytes],
            shared_root: Path = SHARED) -> dict[str, bytes]:
    """Moves code that is identical in several maps into `shared/<name>/`.

    Each map's functions (and globals) must be byte-identical and, inside each map, next to each other. The shared
    files are `functions.j` and `globals.j`; each map keeps one marker line per file.

    Args:
        name: Module folder name, e.g. `ff-config`.
        functions: Function names, all defined in one block in every map.
        globals_: Global variable names, all declared on consecutive lines in every map.
        scripts: The scripts of the maps that share the code, keyed by project.
        shared_root: Folder that receives the module's files.

    Returns:
        The edited script of each project, keyed by project. Only the module's files are written here; the caller
        writes the scripts.

    Raises:
        SharedCodeError: The code differs between maps, is spread out, or the module already exists.
    """
    if (shared_root / name).exists():
        raise SharedCodeError(f'shared/{name} already exists')
    parts = [(f'{name}/globals.j', globals_, _global_span, 'globals'),
             (f'{name}/functions.j', functions, _function_span, 'functions')]
    projects = list(scripts)
    originals = dict(scripts)
    edited = dict(originals)
    files: dict[str, bytes] = {}
    for file, names, finder, what in parts:
        if not names:
            continue
        texts = {}
        for project in projects:
            script = edited[project]
            span = _contiguous(script, [finder(script, n) for n in names], what)
            texts[project] = script[span.start:span.end]
            edited[project] = _replace(script, span, b'//! shared ' + file.encode())
        if len(set(texts.values())) != 1:
            differing = [p for p in projects if texts[p] != texts[projects[0]]]
            raise SharedCodeError(f'{what} differ between {projects[0]} and {", ".join(differing)}')
        files[file] = texts[projects[0]]
    for project in projects:
        if assemble(edited[project], shared_root, files) != assemble(originals[project], shared_root):
            raise SharedCodeError(f'{project}: assembling the edited script does not give back the original')
    for file, data in files.items():
        (shared_root / file).parent.mkdir(parents=True, exist_ok=True)
        (shared_root / file).write_bytes(data)
    return edited


def modules(projects: tuple[str, ...] = PROJECTS) -> dict[str, list[str]]:
    """Lists which maps use each shared file.

    Args:
        projects: The maps to look at.

    Returns:
        Each shared file (`<module>/<file>.j`) mapped to the projects whose script refers to it.
    """
    users: dict[str, list[str]] = {}
    for project in projects:
        for match in MARKER.finditer(script_path(project).read_bytes()):
            users.setdefault(match[1].decode(), []).append(project)
    return users


def functions_of(script: bytes) -> dict[bytes, bytes]:
    """Maps each function name of a script to its full text (first definition wins)."""
    result: dict[bytes, bytes] = {}
    for match in FUNCTION.finditer(script):
        result.setdefault(match[1], match[0])
    return result


def duplicates(projects: tuple[str, ...] = PROJECTS) -> dict[str, int]:
    """Counts functions that are still copied, byte for byte, between map scripts.

    Shared files are not counted: the maps' own scripts only hold markers for them.

    Args:
        projects: The maps to compare.

    Returns:
        `copied`: functions identical in at least two maps; `in_all`: functions identical in every map.
    """
    per_map = [functions_of(script_path(p).read_bytes()) for p in projects]
    counts: dict[tuple[bytes, bytes], int] = {}
    for functions in per_map:
        for name, text in functions.items():
            counts[(name, text)] = counts.get((name, text), 0) + 1
    return {'copied': len({n for (n, _), c in counts.items() if c >= 2}),
            'in_all': len({n for (n, _), c in counts.items() if c == len(projects)})}


def check(update_baseline: bool = False) -> list[str]:
    """Checks that every map assembles and that no new copies appeared between maps.

    Args:
        update_baseline: Writes the current counts as the new baseline when they did not grow.

    Returns:
        Problems found; empty when the check passes.
    """
    problems = []
    for project in PROJECTS:
        try:
            assemble(script_path(project).read_bytes())
        except SharedCodeError as error:
            problems.append(f'{project}: {error}')
    now = duplicates()
    before = json.loads(BASELINE.read_text()) if BASELINE.exists() else None
    if before and now['copied'] > before['copied']:
        problems.append(f'{now["copied"] - before["copied"]} more functions are copied between maps than before '
                        f'({before["copied"]} -> {now["copied"]}); put shared code in shared/ '
                        '(python tools/shared_code.py extract ...)')
    elif update_baseline or not before:
        BASELINE.write_text(json.dumps(now, indent=2) + '\n')
    print(f'functions copied between maps: {now["copied"]} (in all {len(PROJECTS)}: {now["in_all"]})'
          + (f', baseline {before["copied"]}' if before else ''))
    return problems


def main(argv: list[str] | None = None) -> int:
    """Runs the command-line interface; returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('assemble', help="print or write a project's complete script")
    p.add_argument('project', choices=PROJECTS)
    p.add_argument('-o', '--output', type=Path)
    p = commands.add_parser('extract', help='move code identical in several maps into shared/<name>/')
    p.add_argument('name')
    p.add_argument('--functions', default='')
    p.add_argument('--globals', default='')
    p.add_argument('--projects', default=','.join(PROJECTS))
    commands.add_parser('modules', help='list which maps use each shared file')
    commands.add_parser('duplicates', help='count functions still copied between maps')
    p = commands.add_parser('check', help='every map assembles; copies between maps did not grow')
    p.add_argument('--update-baseline', action='store_true')
    args = parser.parse_args(argv)
    split = lambda text: [x for x in text.split(',') if x]
    try:
        if args.command == 'assemble':
            data = assemble(script_path(args.project).read_bytes())
            if args.output:
                args.output.write_bytes(data)
            else:
                sys.stdout.buffer.write(data)
        elif args.command == 'extract':
            scripts = {p: script_path(p).read_bytes() for p in split(args.projects)}
            edited = extract(args.name, split(args.functions), split(args.globals), scripts)
            for project, script in edited.items():
                script_path(project).write_bytes(script)
            print(f'shared/{args.name}: written; {len(edited)} map scripts now refer to it')
        elif args.command == 'modules':
            for file, users in sorted(modules().items()):
                print(f'{file}: {", ".join(users)}')
        elif args.command == 'duplicates':
            print(json.dumps(duplicates(), indent=2))
        else:
            problems = check(args.update_baseline)
            for problem in problems:
                print(f'FAIL {problem}', file=sys.stderr)
            return 1 if problems else 0
    except SharedCodeError as error:
        print(f'error: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
