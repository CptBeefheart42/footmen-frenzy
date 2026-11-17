"""Warns when a branch changes the maps, the league code or the tools without changing a test (AGENTS.md: every new
feature and every fix comes with a test). A warning, not a failure: a pull request may explain why a change can't be
tested.

    python tools/ff/scope.py <base ref>
"""
from __future__ import annotations

import subprocess
import sys

CODE = ('projects/', 'league/', 'shared/', 'tools/')
TESTS = ('tests/',)


def changed(base: str) -> list[str]:
    """The files the current branch changed since it left `base`."""
    out = subprocess.run(['git', 'diff', '--name-only', f'{base}...HEAD'], capture_output=True, text=True, check=True)
    return [f for f in out.stdout.splitlines() if f]


def main() -> int:
    """Prints the verdict; always exits 0."""
    files = changed(sys.argv[1] if len(sys.argv) > 1 else 'origin/main')
    code = [f for f in files if f.startswith(CODE)]
    tests = [f for f in files if f.startswith(TESTS)]
    if code and not tests:
        print(f'::warning::This branch changes {len(code)} file(s) of the maps, league code or tools but no test. '
              'A new feature or a fix needs a test; if it cannot be tested, say why in the pull request.')
    else:
        print(f'scope: {len(code)} code file(s), {len(tests)} test file(s) changed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
