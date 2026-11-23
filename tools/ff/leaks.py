"""Finds personal or private details in the files about to be committed: e-mail addresses, home-folder paths, and the
words a maintainer lists in ff.local.json ("private_words": host names, account names) without putting them into the
repository; and the same in the names and addresses commits carry (author, committer), which a public mirror publishes
as they are."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from repo import ROOT

PATTERNS = [
    # (GitHub's no-reply addresses and the domains reserved for examples are fine)
    (re.compile(r'[A-Za-z0-9._%+-]+@(?!users\.noreply\.github\.com|example\.(?:org|com|net)\b)[A-Za-z0-9-]+\.[A-Za-z]{2,}'),
     'an e-mail address'),
    # (Proton's Windows user, steamuser, is the same on every machine)
    (re.compile(r'(?i)\b[A-Z]:[\\/]+Users[\\/]+(?!steamuser\b)[^\\/\s"]+'), 'a Windows user folder'),
    (re.compile(r'/home/[a-z_][a-z0-9_-]*/'), 'a Linux home folder'),
]
# Files whose matches are data, not personal details (Battle.net names in the bot lists, upstream license texts).
ALLOWED = ('data/', 'projects/', 'shared/')


def private_words() -> list[str]:
    """The maintainer's own private words from ff.local.json."""
    config = ROOT / 'ff.local.json'
    return json.loads(config.read_text(encoding='utf-8')).get('private_words', []) if config.is_file() else []


def scan(files: list[str]) -> list[str]:
    """Returns one line per finding: `<file>:<line>: <what>`.

    Args:
        files: Repository-relative paths to look at.
    """
    words = [w for w in private_words() if w]
    findings = []
    for name in files:
        path = ROOT / name
        if not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for word in words:
                if word.lower() in line.lower():
                    findings.append(f'{name}:{number}: a private word from ff.local.json')
            if name.startswith(ALLOWED):
                continue
            for pattern, what in PATTERNS:
                if pattern.search(line):
                    findings.append(f'{name}:{number}: {what}')
    return findings


def tracked_and_staged() -> list[str]:
    """Every file git tracks or has staged."""
    out = subprocess.run(['git', 'ls-files', '-z', '--cached'], cwd=ROOT, capture_output=True, check=True).stdout
    return [f for f in out.decode().split('\0') if f]


NOREPLY = re.compile(r'<[^<>@]+@users\.noreply\.github\.com>')


def identity_findings(identities: list[str], own: bool = False) -> list[str]:
    """Returns one line per identity (`Name <address>`) that names a private word from ff.local.json.

    Args:
        identities: Authors and committers, as git prints them.
        own: They are the identity this clone commits with, which must also use a GitHub no-reply address.
    """
    words = [w.lower() for w in private_words() if w]
    findings = []
    for identity in identities:
        if any(word in identity.lower() for word in words):
            findings.append(f'{identity.split("<")[0].strip() or identity}: a private word from ff.local.json')
        elif own and not NOREPLY.search(identity):
            findings.append(f'{identity}: not a GitHub no-reply address (user.email)')
    return findings


def own_identities() -> list[str]:
    """The author and committer this clone's next commit would carry (`Name <address>`, without the date)."""
    out = []
    for var in ('GIT_AUTHOR_IDENT', 'GIT_COMMITTER_IDENT'):
        ident = subprocess.run(['git', 'var', var], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        out.append(ident.rsplit('>', 1)[0] + '>' if '>' in ident else ident)
    return out


def pushed_identities(revisions: list[str]) -> list[str]:
    """The authors and committers of the commits `git rev-list <revisions>` lists (e.g. `<old>..<new>`)."""
    out = subprocess.run(['git', 'log', '--format=%an <%ae>%n%cn <%ce>', *revisions], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return sorted({line for line in out.splitlines() if line})
