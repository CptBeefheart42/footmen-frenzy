"""Bringing a contributor's pull request in safely: its code never runs on this machine outside a sandbox.

`ff pr fetch <N>` copies pull request N of the public GitHub repository into a separate throwaway clone
(build/pr/<N>/repo, its own .git: nothing it contains can reach this repository's git hooks or settings) and prints
what it changes, the paths that run code or instruct AI tools first. Nothing of it is run.

`ff pr check <N>` runs `ff check` on that clone in a container built from THIS repository's Dockerfile (not the pull
request's), with no network, no environment secrets and only the clone mounted. The tools' caches (.tools) are
copied in, so the build works offline.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from repo import BUILD, ROOT, setting

GITHUB = 'https://github.com/CptBeefheart42/footmen-frenzy'
IMAGE = 'footmen-frenzy-check'
# Paths whose changes run code on a maintainer's machine or in CI, or instruct AI tools: read these first.
RISKY = ('tools/', 'tests/', '.github/', '.githooks/', '.agents/', '.claude/', 'Dockerfile', 'ff', 'ff.cmd',
         'AGENTS.md', 'CLAUDE.md', 'CONTRIBUTING.md', 'shared_code.py', '.gitattributes')


def folder(number: int) -> Path:
    """The throwaway clone of pull request `number`."""
    return BUILD / 'pr' / str(number) / 'repo'


def git(*args: str, cwd: Path) -> str:
    """Runs git without any hook or the user's configured helpers; returns its output."""
    result = subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)}: {result.stderr.strip()}')
    return result.stdout


def fetch(number: int) -> list[str]:
    """Clones this repository (its checked-out commit as `main`) into build/pr/<N>/repo and checks out pull request N.

    Returns:
        The changed paths (`git diff --name-status`), risky paths first.
    """
    clone = folder(number)
    shutil.rmtree(clone.parent, ignore_errors=True)
    clone.parent.mkdir(parents=True)
    head = git('rev-parse', 'HEAD', cwd=ROOT).strip()
    git('clone', '--quiet', '--no-hardlinks', '--no-checkout', str(ROOT), str(clone), cwd=ROOT)
    git('checkout', '--quiet', '-B', 'main', head, cwd=clone)
    url = setting('github_repo', 'FF_GITHUB_REPO') or GITHUB
    git('remote', 'set-url', 'origin', url, cwd=clone)  # the clone keeps no link to this folder
    git('fetch', '--quiet', url, f'pull/{number}/head:pr-{number}', cwd=clone)
    git('checkout', '--quiet', f'pr-{number}', cwd=clone)
    changed = git('diff', '--name-status', 'main...HEAD', cwd=clone).splitlines()
    return sorted(changed, key=lambda line: (not is_risky(line.split('\t')[-1]), line.split('\t')[-1]))


def is_risky(path: str) -> bool:
    """Whether a changed path runs code or instructs AI tools."""
    return path in RISKY or path.startswith(tuple(p for p in RISKY if p.endswith('/')))


def check(number: int) -> int:
    """Runs ff check on the pull request's clone in an offline container; returns its exit code."""
    clone = folder(number)
    if not clone.is_dir():
        raise RuntimeError(f'pull request {number} is not fetched: ff pr fetch {number}')
    with (ROOT / 'Dockerfile').open('rb') as dockerfile:
        if subprocess.run(['docker', 'build', '-q', '-t', IMAGE, '-'], stdin=dockerfile).returncode != 0:
            return 1
    tools = clone / '.tools'
    shutil.rmtree(tools, ignore_errors=True)
    if (ROOT / '.tools').is_dir():
        shutil.copytree(ROOT / '.tools', tools, symlinks=False)
    user = ['--user', f'{os.getuid()}:{os.getgid()}'] if hasattr(os, 'getuid') else []
    return subprocess.run(['docker', 'run', '--rm', '--network', 'none', *user, '-v', f'{clone}:/repo', '-w', '/repo',
                           '-e', 'NUGET_PACKAGES=/repo/.tools/nuget', IMAGE, 'python3', 'tools/ff', 'check']).returncode
