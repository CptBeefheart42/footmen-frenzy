"""Tests of the ff command's building blocks (tools/ff) with real files.

Run with `python -m unittest discover -s tests` from the repository root.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'ff'))

import lfs  # noqa: E402
from install import install, sha256  # noqa: E402
from repo import projects  # noqa: E402


class ProjectsTest(unittest.TestCase):
    """ff knows every map under projects/."""

    def test_both_maps_with_their_starting_map(self):
        found = projects()
        self.assertEqual(list(found), ['799x', 'solo'])
        self.assertEqual(found['799x'].family, '799X')
        self.assertEqual(found['solo'].family, 'Solo Foots')
        for project in found.values():
            self.assertTrue(project.start_map.is_file(), project.start_map)


class LfsTest(unittest.TestCase):
    """Pointer files are recognised; real files are left alone."""

    def test_starting_map_pointer_names_the_checksum_in_project_json(self):
        for project in projects().values():
            pointer = lfs.read_pointer(project.start_map)
            if pointer is None:  # a clone with git-lfs holds the real map
                self.assertEqual(sha256(project.start_map), project.sha256)
            else:
                self.assertEqual(pointer.oid, project.sha256)
                self.assertGreater(pointer.size, 1_000_000)

    def test_map_script_is_not_a_pointer(self):
        self.assertIsNone(lfs.read_pointer(projects()['solo'].src / 'war3map.j'))

    def test_https_address_of_an_ssh_remote(self):
        self.assertTrue(lfs.lfs_url().startswith('https://'))
        self.assertTrue(lfs.lfs_url().endswith('.git/info/lfs/objects/batch'))


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
