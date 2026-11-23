"""Tests of the ff command's building blocks (tools/ff) with real files.

Run with `python -m unittest discover -s tests` from the repository root.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'ff'))

import blobs  # noqa: E402
import leaks  # noqa: E402
import build  # noqa: E402
import lookup  # noqa: E402
from install import install  # noqa: E402
from repo import ROOT as REPO, projects  # noqa: E402


class ProjectsTest(unittest.TestCase):
    """ff knows every map under projects/ and its starting map."""

    def test_both_maps_with_their_starting_map(self):
        found = projects()
        self.assertEqual(list(found), ['799x', 'solo'])
        self.assertEqual(found['799x'].family, '799X')
        self.assertEqual(found['solo'].family, 'Solo Foots')
        for project in found.values():
            self.assertTrue(project.start_name.endswith('.w3x'), project.name)
            # a map file starts with its own header or directly with the MPQ archive's
            self.assertIn(project.base.read_bytes()[:4], (b'HM3W', b'MPQ\x1a'), f'{project.name}: base.w3x is a map')


class BinariesTest(unittest.TestCase):
    """Binary files are listed by checksum and released; the starting maps are the only ones committed."""

    def test_every_listed_binary_has_a_checksum_and_size(self):
        for project in projects().values():
            listed = json.loads(project.binaries.read_text())
            self.assertGreater(len(listed), 1000, project.name)
            for name, blob in listed.items():
                self.assertRegex(blob['sha256'], '^[0-9a-f]{64}$', name)
                self.assertGreater(blob['size'], 0, name)
                self.assertFalse((project.src / name).exists(), f'{name} is both listed and in src/')
            object_files = {p.name.removesuffix('.txt') for p in project.objects.glob('*.txt')}
            self.assertEqual(len(object_files), 14, project.name)
            self.assertEqual(object_files & set(listed), set(), 'object data is text, never a listed binary')

    def test_the_starting_maps_are_the_only_binary_files(self):
        tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=REPO, capture_output=True, check=True).stdout
        binary = []
        for name in filter(None, tracked.decode().split('\0')):
            data = (REPO / name).read_bytes()
            try:
                data.decode('utf-8')
            except UnicodeDecodeError:
                binary.append(name)
                continue
            if b'\0' in data:
                binary.append(name)
        starting_maps = sorted(str(p.base.relative_to(REPO)) for p in projects().values())
        self.assertEqual(sorted(binary), starting_maps, 'other binary files belong in a release, listed in binaries.json')

    def test_lfs_address_is_http(self):
        self.assertTrue(blobs.lfs_url().startswith(('https://', 'http://')))
        self.assertTrue(blobs.lfs_url().endswith('.git/info/lfs/objects/batch'))


class LookupTest(unittest.TestCase):
    """The MPQ hashes match the format's published constants."""

    def test_table_keys(self):
        self.assertEqual(lookup.hash_string('(hash table)', 3), 0xC3AF3770)
        self.assertEqual(lookup.hash_string('(block table)', 3), 0xEC83B3A3)


class SettingsTest(unittest.TestCase):
    """project.json settings reach the map script as constants."""

    def test_799x_settings_become_constants(self):
        text = build.settings_addon(projects()['799x'])
        self.assertIn('constant integer FF_CFG_POOLING_PUB_OPEN_S = 230', text)
        self.assertIn('constant integer FF_CFG_POOLING_PRO_OPEN_S = 0', text)
        self.assertIn('constant boolean FF_CFG_MODES_4K = false', text)
        self.assertTrue(text.splitlines()[1] == 'globals' and text.rstrip().endswith('endglobals'))

    def test_every_setting_the_script_uses_is_set(self):
        project = projects()['799x']
        used = set(re.findall(r'\bFF_CFG_\w+', (project.src / 'war3map.j').read_text(encoding='utf-8', errors='replace')))
        defined = set(re.findall(r'constant \w+ (FF_CFG_\w+)', build.settings_addon(project)))
        self.assertEqual(used - defined, set())


class LeaksTest(unittest.TestCase):
    """Personal details are found before they are committed; generic test values are not."""

    def test_findings(self):
        with tempfile.TemporaryDirectory() as work:
            file = Path(work) / 'notes.md'
            at, users, home = '@', 'Users', '/home/'   # assembled, so this file itself holds no finding
            file.write_text(f'mail me at someone{at}private-mail.net\nC:\\{users}\\Someone\\Documents\n{home}someone/src\n'
                            f'tester{at}example.org, C:\\{users.lower()}\\steamuser\\Documents, 1+x{at}users.noreply.github.com\n')
            found = [f.split(': ', 1)[1] for f in leaks.scan([str(file)])]
        self.assertEqual(found, ['an e-mail address', 'a Windows user folder', 'a Linux home folder'])

    def test_repository_is_clean(self):
        self.assertEqual(leaks.scan(leaks.tracked_and_staged()), [])

    def test_identities_naming_a_private_word_are_refused(self):
        at = '@'
        noreply = f'Some One <1+someone{at}users.noreply.github.com>'
        with unittest.mock.patch.object(leaks, 'private_words', return_value=['secretname']):
            found = leaks.identity_findings([noreply, f'SecretName <x{at}mail.example>', f'Other <secretname{at}x.org>'])
            self.assertEqual(found, ['SecretName: a private word from ff.local.json',
                                     'Other: a private word from ff.local.json'])
            # the clone's own identity must be a GitHub no-reply address; a contributor's commits keep theirs
            self.assertEqual(leaks.identity_findings([f'Other <other{at}mail.example>']), [])
            self.assertEqual(len(leaks.identity_findings([f'Other <other{at}mail.example>'], own=True)), 1)
            self.assertEqual(leaks.identity_findings([noreply], own=True), [])

    def test_identities_of_the_commits_to_push(self):
        found = leaks.pushed_identities(['-1', 'HEAD'])
        self.assertTrue(found and all(re.fullmatch(r'.+ <[^<>]+>', line) for line in found), found)
        self.assertEqual(leaks.identity_findings(found), [])


class InstallTest(unittest.TestCase):
    """One active test map per family; earlier ones are archived, nothing is lost."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'Warcraft III' / 'Maps'
        self.root.mkdir(parents=True)
        self.builds = Path(self.temp.name) / 'builds'
        self.builds.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def built(self, name: str, content: bytes) -> Path:
        path = self.builds / name
        path.write_bytes(content)
        return path

    def test_second_install_archives_the_first(self):
        install(self.built('Solo v1.w3x', b'one'), 'Solo Foots', self.root)
        installed = install(self.built('Solo v2.w3x', b'two'), 'Solo Foots', self.root)

        self.assertEqual(installed, self.root / 'Tests' / 'Solo Foots' / 'Solo v2.w3x')
        self.assertEqual(sorted(p.name for p in (self.root / 'Tests' / 'Solo Foots').glob('*.w3x')), ['Solo v2.w3x'])
        self.assertEqual(sorted(p.name for p in (self.root / 'Solo Foots').glob('*.w3x')), ['Solo v2.w3x'])
        archived = list((self.root / 'Tests' / 'Solo Foots' / 'Test Archives').rglob('*.w3x'))
        self.assertEqual([p.read_bytes() for p in archived], [b'one'])
        self.assertEqual([p.read_bytes() for p in (self.root / 'Archive' / 'Solo Foots').rglob('*.w3x')], [b'one'])

    def test_reinstalling_the_same_map_changes_nothing(self):
        install(self.built('Solo v1.w3x', b'one'), 'Solo Foots', self.root)
        install(self.built('Solo v1.w3x', b'one'), 'Solo Foots', self.root)
        self.assertFalse((self.root / 'Tests' / 'Solo Foots' / 'Test Archives').exists())

    def test_live_maps_folder_is_never_touched(self):
        live = self.root / 'Foots' / 'Solo Foots'
        live.mkdir(parents=True)
        (live / 'Live.w3x').write_bytes(b'live')
        install(self.built('Solo v1.w3x', b'one'), 'Solo Foots', self.root)
        self.assertEqual([p.name for p in live.iterdir()], ['Live.w3x'])

    def test_staging_leaves_nothing_behind(self):
        install(self.built('Solo v1.w3x', b'one'), 'Solo Foots', self.root)
        self.assertEqual(list((self.root.parent / 'Map Install Staging').iterdir()), [])


if __name__ == '__main__':
    unittest.main()
