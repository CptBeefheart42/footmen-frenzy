"""Object-data cells stored with their field's type: the rule, the fix, and both maps."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'ff'))

import objecttypes  # noqa: E402
from repo import projects  # noqa: E402


class RuleTest(unittest.TestCase):
    """Which stored types are wrong for a field, from the game's metadata."""

    def setUp(self):
        self.types = objecttypes.field_types()

    def test_decimal_fields(self):
        self.assertEqual(self.types[('ability', 'acdn')], 'unreal')
        self.assertEqual(objecttypes.expected(self.types, 'ability', 'acdn', 'real'), 'unreal')
        self.assertIsNone(objecttypes.expected(self.types, 'ability', 'acdn', 'unreal'))
        self.assertEqual(objecttypes.expected(self.types, 'unit', 'usca', 'unreal'), 'real')

    def test_other_fields_are_not_judged_unless_decimal(self):
        self.assertIsNone(objecttypes.expected(self.types, 'unit', 'uhot', 'string'))
        self.assertIsNone(objecttypes.expected(self.types, 'ability', 'ZZZZ', 'real'))


class FixTest(unittest.TestCase):
    """The fix rewrites the type only, keeps the value and the comment column."""

    def test_fix_a_text_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            objects = Path(tmp) / 'objects'
            objects.mkdir()
            text = ('[ADk1 : ANcl]\nend = new\n'
                    'acdn.1.0 real = 10                      # Cooldown\n'
                    'aran.1.0 unreal = 1600                  # Cast Range\n')
            (objects / 'war3map.w3a.txt').write_text(text, encoding='utf-8')
            self.assertEqual([(m[2], m[3], m[4]) for m in objecttypes.mismatches(objects)], [('acdn', 'real', 'unreal')])
            self.assertEqual(objecttypes.fix(objects), 1)
            self.assertEqual(objecttypes.mismatches(objects), [])
            fixed = (objects / 'war3map.w3a.txt').read_text(encoding='utf-8').splitlines()
        self.assertEqual(fixed[2], 'acdn.1.0 unreal = 10                    # Cooldown')
        self.assertEqual(fixed[2].index('#'), fixed[3].index('#'))


class MapsTest(unittest.TestCase):
    """Both maps store every cell with its field's type."""

    def test_no_wrong_types(self):
        for name, project in projects().items():
            self.assertEqual(objecttypes.mismatches(project.objects)[:5], [], name)


if __name__ == '__main__':
    unittest.main()
