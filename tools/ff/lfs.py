"""Large files kept in Git LFS, readable without git-lfs installed.

A clone without git-lfs holds small pointer files instead of maps and models. The build only needs the real content of
a few of them, so this module downloads exactly those objects from the repository's LFS storage (the public LFS
download API, no login) into a local cache, `.tools/lfs/<oid>`.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from repo import ROOT, TOOLS

CACHE = TOOLS / 'lfs'
POINTER_START = b'version https://git-lfs.github.com/spec/v1\n'


@dataclass(frozen=True)
class LfsObject:
    """One LFS object: its SHA-256 (`oid`) and size in bytes."""
    oid: str
    size: int


def read_pointer(path: Path) -> LfsObject | None:
    """Returns the object a pointer file names, or None when the file holds real content."""
    with path.open('rb') as f:
        head = f.read(512)
    if not head.startswith(POINTER_START):
        return None
    fields = dict(line.split(' ', 1) for line in head.decode('ascii').splitlines() if ' ' in line)
    return LfsObject(fields['oid'].removeprefix('sha256:'), int(fields['size']))


def content(path: Path) -> Path:
    """Returns a path holding the real content of a file that may be an LFS pointer, downloading it if needed."""
    pointer = read_pointer(path)
    if pointer is None:
        return path
    fetch([pointer])
    return CACHE / pointer.oid


def fetch(objects: list[LfsObject]) -> None:
    """Downloads the objects missing from the cache and checks each one's SHA-256.

    Raises:
        RuntimeError: The download failed or delivered different bytes.
    """
    missing = [o for o in objects if not (CACHE / o.oid).is_file()]
    if not missing:
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    url = lfs_url()
    for start in range(0, len(missing), 100):
        batch = missing[start:start + 100]
        request = urllib.request.Request(
            url, json.dumps({'operation': 'download', 'transfer': ['basic'],
                             'objects': [{'oid': o.oid, 'size': o.size} for o in batch]}).encode(),
            {'Accept': 'application/vnd.git-lfs+json', 'Content-Type': 'application/vnd.git-lfs+json'})
        with urllib.request.urlopen(request) as response:
            answer = json.load(response)
        for item in answer['objects']:
            if 'actions' not in item:
                raise RuntimeError(f'LFS object {item["oid"]} is not on the server: {item.get("error")}')
            with urllib.request.urlopen(item['actions']['download']['href']) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != item['oid']:
                raise RuntimeError(f'LFS object {item["oid"]}: the download does not match its checksum')
            temporary = CACHE / (item['oid'] + '.part')
            temporary.write_bytes(data)
            temporary.replace(CACHE / item['oid'])
        print(f'downloaded {len(batch)} large file(s)')


def lfs_url() -> str:
    """The LFS API address of the `origin` remote (an SSH address is turned into its HTTPS form)."""
    remote = subprocess.run(['git', 'config', '--get', 'remote.origin.url'], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.strip()
    if remote.startswith('git@'):
        host, path = remote[4:].split(':', 1)
        remote = f'https://{host}/{path}'
    elif remote.startswith('ssh://'):
        remote = 'https://' + remote[6:].split('@', 1)[-1]
    if not remote.endswith('.git'):
        remote += '.git'
    return remote + '/info/lfs/objects/batch'
