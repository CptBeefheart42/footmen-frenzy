"""Binary files (maps, models, textures, object data), which the repository lists by SHA-256 but does not hold.

`projects/<map>/binaries.json` names each binary entry of a map with its SHA-256 and size, and project.json names the
starting map the same way. The contents are released files; this module downloads the ones a build needs into the
local cache `.tools/blobs/<sha256>`, checking every checksum. Download sources, first match wins:
1. the cache;
2. `blob_url` in ff.local.json (or the FF_BLOB_URL environment variable): an address with `{sha256}` in it, e.g. a
   release whose files are named by their SHA-256; a private store's token is read from the file `blob_token_file`
   names (or FF_BLOB_TOKEN_FILE) and sent as `Authorization: token ...`;
3. the Git LFS storage of the `origin` remote (public, no login), which holds the files of the imported maps.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from repo import ROOT, TOOLS, setting

CACHE = TOOLS / 'blobs'


@dataclass(frozen=True)
class Blob:
    """A file known by its SHA-256 and size in bytes."""
    sha256: str
    size: int

    @property
    def path(self) -> Path:
        """Where the cache keeps it."""
        return CACHE / self.sha256


def fetch(blobs: list[Blob]) -> None:
    """Downloads the blobs missing from the cache.

    Raises:
        RuntimeError: A blob is in none of the sources, or a download does not match its checksum.
    """
    missing = [b for b in dict.fromkeys(blobs) if not b.path.is_file()]
    if not missing:
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    url = setting('blob_url', 'FF_BLOB_URL')
    if url:
        before = len(missing)
        missing = [b for b in missing if not download(url.format(sha256=b.sha256), b)]
        print(f'downloaded {before - len(missing)} binary file(s) from the release store')
    if missing:
        from_lfs(missing)
        print(f'downloaded {len(missing)} binary file(s) from Git LFS storage')


def download(url: str, blob: Blob, check_only: bool = False) -> bool:
    """Downloads one blob into the cache; returns False when the address has no such file. With `check_only`, only
    asks whether the address has it."""
    headers = {}
    token_file = setting('blob_token_file', 'FF_BLOB_TOKEN_FILE')
    if token_file:
        headers['Authorization'] = 'token ' + Path(token_file).expanduser().read_text(encoding='utf-8').strip()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers, method='HEAD' if check_only else 'GET')) as response:
            if check_only:
                return True
            data = response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return False
        raise
    store(data, blob)
    return True


def from_lfs(blobs: list[Blob]) -> None:
    """Downloads blobs from the LFS storage of the `origin` remote."""
    for start in range(0, len(blobs), 100):
        batch = blobs[start:start + 100]
        request = urllib.request.Request(
            lfs_url(), json.dumps({'operation': 'download', 'transfer': ['basic'],
                                   'objects': [{'oid': b.sha256, 'size': b.size} for b in batch]}).encode(),
            {'Accept': 'application/vnd.git-lfs+json', 'Content-Type': 'application/vnd.git-lfs+json'})
        with urllib.request.urlopen(request) as response:
            answer = {item['oid']: item for item in json.load(response)['objects']}
        for blob in batch:
            item = answer.get(blob.sha256, {})
            if 'actions' not in item:
                raise RuntimeError(f'binary file {blob.sha256} is in no release and not in LFS storage; '
                                   'it has to be uploaded to the release store first')
            with urllib.request.urlopen(item['actions']['download']['href']) as response:
                store(response.read(), blob)


def store(data: bytes, blob: Blob) -> None:
    """Writes a downloaded blob into the cache after checking its checksum."""
    if hashlib.sha256(data).hexdigest() != blob.sha256:
        raise RuntimeError(f'binary file {blob.sha256}: the download does not match its checksum')
    partial = blob.path.with_suffix('.part')
    partial.write_bytes(data)
    partial.replace(blob.path)


def lfs_url() -> str:
    """The LFS API address of the `origin` remote (an SSH address is turned into its HTTPS form)."""
    remote = subprocess.run(['git', 'config', '--get', 'remote.origin.url'], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.strip()
    if remote.startswith('git@'):
        host, path = remote[4:].split(':', 1)
        remote = f'https://{host}/{path}'
    if not remote.endswith('.git'):
        remote += '.git'
    return remote + '/info/lfs/objects/batch'


def add(project_binaries: Path, entry: str, file: Path) -> Blob:
    """Lists `file` as the map entry `entry` in a project's binaries.json and puts it into the cache.

    Args:
        project_binaries: The project's binaries.json.
        entry: The file's path inside the map, with / as separator (e.g. war3mapImported/Hero.mdx).
        file: The file on disk.

    Returns:
        The blob as listed.
    """
    data = file.read_bytes()
    blob = Blob(hashlib.sha256(data).hexdigest(), len(data))
    CACHE.mkdir(parents=True, exist_ok=True)
    store(data, blob)
    listed = json.loads(project_binaries.read_text(encoding='utf-8'))
    listed[entry.replace('\\', '/')] = {'sha256': blob.sha256, 'size': blob.size}
    project_binaries.write_text(json.dumps(listed, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    return blob


def upload(blobs: list[Blob]) -> list[Blob]:
    """Uploads the blobs the release store lacks (a Gitea release: blob_upload_url in ff.local.json, the release's
    asset API, with the token from blob_token_file). Returns the uploaded ones.

    Raises:
        RuntimeError: No upload address is set, or a blob is not in the cache.
    """
    url = setting('blob_upload_url', 'FF_BLOB_UPLOAD_URL')
    token_file = setting('blob_token_file', 'FF_BLOB_TOKEN_FILE')
    if not url or not token_file:
        raise RuntimeError('uploading needs blob_upload_url and blob_token_file in ff.local.json (maintainers only)')
    token = Path(token_file).expanduser().read_text(encoding='utf-8').strip()
    uploaded = []
    for blob in blobs:
        if download(setting('blob_url', 'FF_BLOB_URL').format(sha256=blob.sha256), blob, check_only=True):
            continue
        if not blob.path.is_file():
            raise RuntimeError(f'{blob.sha256} is not in the cache; ff blobs add it first')
        boundary = 'ff-' + blob.sha256[:16]
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="attachment"; filename="{blob.sha256}"\r\n'
                'Content-Type: application/octet-stream\r\n\r\n').encode() + blob.path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
        request = urllib.request.Request(f'{url}?name={blob.sha256}', body, method='POST', headers={
            'Authorization': f'token {token}', 'Content-Type': f'multipart/form-data; boundary={boundary}'})
        with urllib.request.urlopen(request):
            uploaded.append(blob)
    return uploaded
