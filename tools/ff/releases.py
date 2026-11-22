"""What a release is: each map's version, its fingerprint and the release notes with their manifest.

A map numbered on its own (project.json `release.own_version`, e.g. Solo 1.8) carries `<base>-<rebuild>`: a new
base starts at -1, the same base counts up when the map changed since the previous release and stays when it didn't.
Whether it changed is decided by its fingerprint: the SHA-256 of a build stamped with a placeholder version, so the
version itself doesn't count as a change (the build is reproducible). The previous release's versions and fingerprints
come from the manifest in its notes (`<!-- ff-release-manifest v1 {...} -->`), as the forge's API lists it.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

MANIFEST = re.compile(r'<!-- ff-release-manifest v1 (\{.*?\}) -->')
PLACEHOLDER = 'FPSTAMP'
COLOUR = re.compile(r'\|c[0-9a-fA-F]{8}|\|r')


@dataclass(frozen=True)
class ReleasedMap:
    """One map of a release.

    Attributes:
        version: The map's version, e.g. 7.9.9X-rc1 or 1.8-2.
        file: The map's file name.
        title: The map name in the lobby (colour codes included).
        author: The map's author.
        fingerprint: The SHA-256 of its placeholder build, for maps numbered on their own; empty otherwise.
    """
    version: str
    file: str
    title: str
    author: str = ''
    fingerprint: str = ''


def previous_manifest(releases: list[dict], tag: str) -> dict:
    """The manifest of the newest published release other than `tag` that has one; {} when none has.

    Args:
        releases: The forge's release list (GET /releases), any order.
        tag: The tag being released, which a rerun may already have published.
    """
    published = [r for r in releases if not r.get('draft') and r.get('tag_name') != tag]
    for release in sorted(published, key=lambda r: r.get('created_at') or '', reverse=True):
        found = MANIFEST.search(release.get('body') or '')
        if found:
            try:
                return json.loads(found.group(1))
            except json.JSONDecodeError:
                continue
    return {}


def own_version(base: str, previous: str, changed: bool) -> str:
    """The next `<base>-<rebuild>` of a map numbered on its own.

    Args:
        base: The map's base version (project.json `release.own_version`).
        previous: Its version in the previous release; empty when it had none.
        changed: Whether its fingerprint differs from the previous release's.

    Raises:
        ValueError: The previous release has a newer base.
    """
    prev_base, _, prev_rebuild = previous.rpartition('-')
    if not previous or not prev_rebuild.isdigit():
        return f'{base}-1'
    if prev_base == base:
        return previous if not changed else f'{base}-{int(prev_rebuild) + 1}'
    if _version_key(prev_base) > _version_key(base):
        raise ValueError(f'the base version {base} is older than the released {previous}')
    return f'{base}-1'


def _version_key(version: str) -> list:
    return [int(part) if part.isdigit() else part for part in re.split(r'[.-]', version)]


def fingerprint(path: Path) -> str:
    """The fingerprint of a placeholder build."""
    return 'fpv1:' + hashlib.sha256(path.read_bytes()).hexdigest()


def notes(tag: str, archive: str, maps: dict[str, ReleasedMap], text: str = '') -> str:
    """The release notes: what to download, a table of the maps, optional text and the manifest.

    Args:
        tag: The release's tag.
        archive: The file name of the map zip.
        maps: The released maps by project name.
        text: The release's own "What's new" text (Markdown), if any.
    """
    rows = [f'| {COLOUR.sub("", m.title)} | {m.version} | {m.file} | {m.author} |' for m in maps.values()]
    manifest = json.dumps({'maps': {name: asdict(m) for name, m in maps.items()}}, separators=(',', ':'))
    parts = [f'## Footmen Frenzy {tag}', f'Download **{archive}** and put the maps in `Documents/Warcraft III/Maps`.',
             '| Map | Version | File | Author |\n|---|---|---|---|\n' + '\n'.join(rows)]
    if text.strip():
        parts.append(text.strip())
    parts.append(f'<!-- ff-release-manifest v1 {manifest} -->')
    return '\n\n'.join(parts) + '\n'
