"""The hotkey list: reading the text object data, the clashes, and that the committed lists match the maps."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools' / 'ff'))

import hotkeys  # noqa: E402
from repo import projects  # noqa: E402


class ReadObjectsTest(unittest.TestCase):
    """Level-0 cells of a text object file, strings unescaped."""

    def test_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'war3map.w3a.txt'
            path.write_text('# ability data\nformat v3\n\n[A001 : AHbz]\nend = new\n'
                            'ahky.0.0 string = "Q"                # Hotkey - Normal\n'
                            'abpx.0.0 int = 2\n'
                            'acdn.1.0 unreal = 12.5 @0\n'
                            'atp1.0.0 string = "a \\"b\\", c\\nd"\n'
                            '[hfoo]\nend = base\nuhot string = "F"\n', encoding='utf-8')
            objects = hotkeys.read_objects(path)
        self.assertEqual(objects['A001'], {'ahky': 'Q', 'abpx': '2', 'atp1': 'a "b", c\nd'})
        self.assertEqual(objects['hfoo'], {'uhot': 'F'})


class ClashTest(unittest.TestCase):
    """Two or more abilities on one button or hotkey of a unit's command card."""

    def test_only_shared_places(self):
        self.assertEqual(hotkeys.clashes('h001', 'key', {'A001': 'Q', 'A002': 'Q', 'A003': 'W'}),
                         ['C,h001,key,Q,A001 A002'])


class CommittedListsTest(unittest.TestCase):
    """Each map's hotkeys.csv matches its object data, and a dropped hotkey shows up."""

    def test_lists_match_the_maps(self):
        for name, project in projects().items():
            self.assertEqual(hotkeys.differences(project), [], name)

    def test_a_lost_hotkey_is_reported(self):
        project = projects()['799x']
        rows = hotkeys.list_file(project).read_text(encoding='utf-8').splitlines()
        hotkey = next(r for r in rows if ',ahky,' in r)
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / 'hotkeys.csv'
            changed.write_text('\n'.join(r for r in rows if r != hotkey) + '\nA,ZZZZ,ahky,Q\n', encoding='utf-8')
            self.assertEqual(hotkeys.differences(project, changed), ['- A,ZZZZ,ahky,Q', f'+ {hotkey}'])


if __name__ == '__main__':
    unittest.main()
