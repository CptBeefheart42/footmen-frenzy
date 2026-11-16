"""Tests of tools/shared_code.py against the four maps' real scripts.

Run with `python -m unittest discover -s tests` from the repository root.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import shared_code  # noqa: E402
from shared_code import PROJECTS, SharedCodeError, assemble, extract, functions_of, script_path  # noqa: E402


def scripts() -> dict:
    """Reads the editable script of every map."""
    return {p: script_path(p).read_bytes() for p in PROJECTS}


class AssembleTest(unittest.TestCase):
    """The build gets a complete script for every map."""

    def test_every_map_assembles_without_markers(self):
        for project, script in scripts().items():
            with self.subTest(project=project):
                complete = assemble(script)
                self.assertNotIn(b'//! shared ', complete)
                self.assertEqual(complete.count(b'function FF_ConfigRead takes'), 1)
                self.assertEqual(complete.count(b'constant string FF_ConfigFile'), 1)

    def test_shared_globals_stay_inside_the_globals_block(self):
        complete = assemble(script_path('799x').read_bytes())
        globals_end = complete.index(b'\nendglobals')
        self.assertLess(complete.index(b'constant string FF_ConfigFile'), globals_end)

    def test_missing_shared_file_is_reported(self):
        with self.assertRaisesRegex(SharedCodeError, 'missing shared file'):
            assemble(b'globals\r\nendglobals\r\n//! shared nothing/here.j\r\n')


class ExtractTest(unittest.TestCase):
    """Extracting code never changes what a map's complete script is."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.shared = Path(self.temp.name) / 'shared'
        for module in (shared_code.SHARED).iterdir():
            if module.is_dir():
                target = self.shared / module.name
                target.mkdir(parents=True)
                for file in module.iterdir():
                    (target / file.name).write_bytes(file.read_bytes())

    def tearDown(self):
        self.temp.cleanup()

    def test_identical_function_moves_and_assembles_to_the_same_bytes(self):
        originals = scripts()
        edited = extract('tf-alive', ['TFP_TF_Alive'], [], originals, self.shared)
        for project in PROJECTS:
            with self.subTest(project=project):
                self.assertIn(b'//! shared tf-alive/functions.j', edited[project])
                self.assertNotIn(b'function TFP_TF_Alive takes', edited[project])
                self.assertEqual(assemble(edited[project], self.shared), assemble(originals[project], self.shared))
        self.assertTrue((self.shared / 'tf-alive' / 'functions.j').read_bytes().startswith(b'function TFP_TF_Alive'))

    def test_function_that_differs_between_maps_is_refused(self):
        with self.assertRaisesRegex(SharedCodeError, 'functions differ'):
            extract('architect', ['Trig_HERO_Architect_Recruit_Actions'], [], scripts(), self.shared)
        self.assertFalse((self.shared / 'architect').exists())

    def test_functions_that_are_spread_out_are_refused(self):
        with self.assertRaisesRegex(SharedCodeError, 'not next to each other'):
            extract('apart', ['TFP_TF_Alive', 'MU_Heal'], [], scripts(), self.shared)

    def test_existing_module_is_not_overwritten(self):
        with self.assertRaisesRegex(SharedCodeError, 'already exists'):
            extract('ff-config', ['TFP_TF_Alive'], [], scripts(), self.shared)


class ModulesTest(unittest.TestCase):
    """Agents can see which maps a shared change reaches."""

    def test_ff_config_is_used_by_every_map(self):
        users = shared_code.modules()
        self.assertEqual(users['ff-config/functions.j'], list(PROJECTS))
        self.assertEqual(users['ff-config/globals.j'], list(PROJECTS))


class DuplicatesTest(unittest.TestCase):
    """The copy count only goes down."""

    def test_baseline_matches_the_maps(self):
        baseline = json.loads(shared_code.BASELINE.read_text())
        self.assertEqual(shared_code.duplicates(), baseline)

    def test_shared_code_is_not_counted_as_a_copy(self):
        for project in PROJECTS:
            self.assertNotIn(b'FF_ConfigRead', functions_of(script_path(project).read_bytes()))


if __name__ == '__main__':
    unittest.main()
