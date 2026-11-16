"""The programs the build uses: .NET for the runner, pjass for script checks, Lua for the simulation tests.

`setup` puts pjass and Lua into `.tools/` (pinned versions, checksums verified); .NET, Git and Python are installed by
the person (see README).
"""
from __future__ import annotations

import hashlib
import io
import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from repo import ROOT, TOOLS

WINDOWS = platform.system() == 'Windows'
PJASS_TAG = 'release-2026-06-15'
PJASS_EXE = (f'https://github.com/lep/pjass/releases/download/{PJASS_TAG}/pjass.exe',
             'e6384d68fbaf4950d68e174945377dbd8b3b7c310c59122651d5a95ec0fb37d6')
PJASS_SOURCE = (f'https://github.com/lep/pjass/archive/refs/tags/{PJASS_TAG}.tar.gz',
                '3798cbe4293829a838725d76c2e8b1d187deef6b40481b399b0422e768bd89f4')
LUA_WINDOWS = ('https://downloads.sourceforge.net/project/luabinaries/5.3.6/Tools%20Executables/lua-5.3.6_Win64_bin.zip',
               '5150a30db5b62956d1bca4c2f3e5d1e08c00e398d8c902f0572b09f014012287')


class MissingTool(RuntimeError):
    """A program the command needs is not installed; the message says how to get it."""


def dotnet() -> tuple[str, dict]:
    """Finds the .NET SDK.

    Returns:
        The dotnet executable and the environment to run it with.

    Raises:
        MissingTool: No .NET SDK found.
    """
    env = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
    found = shutil.which('dotnet')
    if found:
        return found, env
    home = Path.home() / '.dotnet' / ('dotnet.exe' if WINDOWS else 'dotnet')
    if home.is_file():
        env['DOTNET_ROOT'] = str(home.parent)
        return str(home), env
    raise MissingTool('.NET SDK not found: install the .NET 6 (or newer) SDK from https://dotnet.microsoft.com/download')


def run_dotnet_tool(project: str, args: list[str], env: dict | None = None) -> int:
    """Runs one of the repository's .NET tools (`tools/runner`, `tools/BalanceTool`) and returns its exit code."""
    exe, base_env = dotnet()
    return subprocess.run([exe, 'run', '--project', str(ROOT / project), '-c', 'Release', '-v', 'q', '--', *args],
                          env={**base_env, **(env or {}), 'FF_REPO': str(ROOT)}).returncode


def pjass() -> str:
    """Returns the pjass executable: `.tools/` first, then PATH.

    Raises:
        MissingTool: pjass is not installed; run `ff setup`.
    """
    local = TOOLS / ('pjass.exe' if WINDOWS else 'pjass')
    if local.is_file():
        return str(local)
    found = shutil.which('pjass')
    if found:
        return found
    raise MissingTool('pjass (the map script checker) is missing: run `ff setup`')


def lua() -> str:
    """Returns a Lua 5.3 interpreter: `.tools/` first, then lua5.3, texlua or lua on PATH.

    Raises:
        MissingTool: No Lua found.
    """
    local = TOOLS / 'lua' / 'lua53.exe'
    if local.is_file():
        return str(local)
    for name in ('lua5.3', 'texlua', 'lua'):
        found = shutil.which(name)
        if found:
            return found
    raise MissingTool('Lua 5.3 is missing: run `ff setup` (Windows) or install it (Linux: sudo apt install lua5.3)')


def setup_pjass() -> str:
    """Installs pjass into `.tools/` unless it is already available; returns what it did."""
    try:
        return f'pjass: {pjass()}'
    except MissingTool:
        pass
    TOOLS.mkdir(exist_ok=True)
    if WINDOWS:
        (TOOLS / 'pjass.exe').write_bytes(download(*PJASS_EXE))
        return 'pjass: downloaded'
    if not all(shutil.which(t) for t in ('gcc', 'make', 'flex', 'bison')):
        raise MissingTool('pjass has to be built here: install gcc, make, flex and bison '
                          '(Ubuntu/Debian: sudo apt install build-essential flex bison), then run `ff setup` again')
    work = TOOLS / 'pjass-src'
    shutil.rmtree(work, ignore_errors=True)
    with tarfile.open(fileobj=io.BytesIO(download(*PJASS_SOURCE))) as archive:
        safe = {'filter': 'data'} if hasattr(tarfile, 'data_filter') else {}  # Python before 3.10.12 lacks filters
        archive.extractall(work, **safe)
    source = next(work.iterdir())
    subprocess.run(['make', 'pjass', f'VERSION={PJASS_TAG}', 'CFLAGS=-O2 -w'], cwd=source, check=True,
                   stdout=subprocess.DEVNULL)
    shutil.copy2(source / 'pjass', TOOLS / 'pjass')
    shutil.rmtree(work)
    return 'pjass: built from source'


def setup_lua() -> str:
    """Installs Lua 5.3 into `.tools/` on Windows; on Linux it only checks for one; returns what it did."""
    try:
        return f'Lua: {lua()}'
    except MissingTool:
        if not WINDOWS:
            raise
    with zipfile.ZipFile(io.BytesIO(download(*LUA_WINDOWS))) as archive:
        archive.extractall(TOOLS / 'lua')
    return 'Lua: downloaded'


def download(url: str, sha256: str) -> bytes:
    """Downloads a file and refuses it unless its SHA-256 is the pinned one."""
    with urllib.request.urlopen(url) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise RuntimeError(f'{url}: the download does not match its pinned checksum; nothing installed')
    return data
