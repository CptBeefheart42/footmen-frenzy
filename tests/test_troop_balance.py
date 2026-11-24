"""Check projectile speeds, Kodo starting stats and both Ghoul weapons."""
from pathlib import Path
import re
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'ff'))
from objectdata import read


class TroopBalanceTest(unittest.TestCase):
    def test_unit_stats_and_spawn_cooldowns(self):
        for family in ('799x', 'solo'):
            with self.subTest(family=family):
                project = ROOT / 'projects' / family
                units = {row.code: {cell.field: cell.value for cell in row.cells}
                         for row in read(project / 'objects/war3map.w3u.txt')}
                for unit, speed in [('uban', 1600), ('earc', 1750), ('ngh2', 1700), ('o019', 1300)]:
                    self.assertEqual(units[unit]['ua1z'], speed)
                self.assertEqual((units['o019']['udef'], units['o019']['uhpm']), (0, 725))
                self.assertEqual(struct.pack('<f', units['ugho']['ua1c']), struct.pack('<f', 1.1 / 1.05))
                self.assertEqual(struct.pack('<f', units['ugho']['ua2c']), struct.pack('<f', 1.0 / 1.05))
                script = (project / 'src/war3map.j').read_text(encoding='utf-8')
                slots = re.findall(r"set udg_spawn_unit\[(\d+)\]\s*=\s*'ugho'", script)
                self.assertEqual(len(slots), 2)
                for slot in slots:
                    value = re.search(rf'set udg_unit_att_CD\[{slot}\]\s*=\s*([\d.]+)', script)
                    self.assertEqual(struct.pack('<f', float(value[1])), struct.pack('<f', units['ugho']['ua1c']))
