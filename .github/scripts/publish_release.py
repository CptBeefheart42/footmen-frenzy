"""Publishes build/release/ as a release of this repository on the forge (Gitea's API), called by release.yml.

    publish_release.py <api> <tag> <commit>      the token in the environment variable TOKEN

The release gets the notes `ff release` wrote (notes.md), is a prerelease when its tag has `-rc`, and carries every zip
of build/release/ (the maps, the wiki). A rerun of the same tag updates that release and replaces its zips instead of
failing on the existing one.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

FOLDER = Path('build/release')


def call(method: str, url: str, token: str, body: bytes | None = None, kind: str = 'application/json'):
    """One API request; returns the decoded JSON answer (None for an empty one)."""
    request = urllib.request.Request(url, body, method=method, headers={'Authorization': f'token {token}',
                                                                        'Content-Type': kind})
    with urllib.request.urlopen(request, timeout=300) as answer:
        data = answer.read()
    return json.loads(data) if data else None


def existing(api: str, tag: str, token: str) -> dict | None:
    """The release of `tag`, if a previous run created it."""
    try:
        return call('GET', f'{api}/releases/tags/{tag}', token)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def upload(api: str, release_id: int, path: Path, token: str) -> None:
    """Attaches one file to the release."""
    boundary = uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="attachment"; filename="{path.name}"\r\n'
            'Content-Type: application/zip\r\n\r\n').encode() + path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
    call('POST', f'{api}/releases/{release_id}/assets?name={path.name}', token, body,
         f'multipart/form-data; boundary={boundary}')


def main(api: str, tag: str, commit: str) -> int:
    """Creates or updates the release of `tag` and uploads its zips."""
    token = os.environ['TOKEN']
    fields = {'tag_name': tag, 'name': tag, 'body': (FOLDER / 'notes.md').read_text(encoding='utf-8'),
              'prerelease': '-rc' in tag, 'target_commitish': commit}
    release = existing(api, tag, token)
    if release is None:
        release = call('POST', f'{api}/releases', token, json.dumps(fields).encode())
    else:
        call('PATCH', f'{api}/releases/{release["id"]}', token, json.dumps(fields).encode())
    zips = sorted(FOLDER.glob('*.zip'))
    for asset in release.get('assets') or []:
        if asset['name'] in {z.name for z in zips}:
            call('DELETE', f'{api}/releases/{release["id"]}/assets/{asset["id"]}', token)
    for path in zips:
        upload(api, release['id'], path, token)
        print(f'published {path.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
