"""Check Witch Doctor's playable ward kit in both league maps."""
from pathlib import Path
import re
import unittest


PROJECTS = Path(__file__).resolve().parents[1] / 'projects'


def records(path):
    """Read the fields used by the ward tests from the editable object export."""
    result = {}
    for line in path.read_text(encoding='utf-8').splitlines():
        header = re.fullmatch(r'\[(\w+)(?: : \w+)?\]', line)
        if header:
            fields = result.setdefault(header[1], {})
        else:
            cell = re.match(r'^(\w+(?:\.\d+\.\d+)?) (?:int|unreal|string) = ("[^"]*"|[^ ]+)', line)
            if cell:
                fields[cell[1]] = cell[2].strip('"')
    return result


class WitchDoctorTest(unittest.TestCase):
    """Follow each spell rank to its actual summons, healing aura and displayed stats."""

    def test_wards(self):
        for project in (PROJECTS/'799x', PROJECTS/'solo'):
            with self.subTest(project=project):
                objects = project / 'objects'
                units = records(objects/'war3map.w3u.txt')
                unit_skin = records(objects/'war3mapSkin.w3u.txt')
                abilities = records(objects/'war3map.w3a.txt')
                skin = records(objects/'war3mapSkin.w3a.txt')
                heal, serpent, sentry, ultimate = units['H04Y']['uhab'].split(',')
                self.assertEqual(ultimate, 'ANtm')
                for slot, code in enumerate((serpent, sentry, heal)):
                    spell, button = abilities[code], skin[code]
                    self.assertEqual(spell['alev.0.0'], '6')
                    self.assertEqual(button['ahky.0.0'], 'ZXC'[slot])
                    self.assertEqual(button['arhk.0.0'], 'QWE'[slot])
                    self.assertEqual((button['abpx.0.0'], button['abpy.0.0']), (str(slot), '2'))
                    self.assertEqual((button['arpx.0.0'], button['arpy.0.0']), (str(slot), '0'))
                    for rank in range(1, 7):
                        tip = button[f'aub1.{rank}.0']
                        self.assertIn('Duration: '+spell[f'adur.{rank}.0']+' seconds', tip)
                        self.assertIn('Cooldown: '+spell[f'acdn.{rank}.0']+' seconds', tip)
                        if code == heal:
                            ward = spell[f'hwdu.{rank}.0']
                            aura = units[ward]['uabi']
                            self.assertEqual(unit_skin[ward]['uabs'], aura)
                            self.assertEqual(abilities[aura]['Oar2.1.2'], '1')
                            self.assertEqual(abilities[aura]['aare.1.0'], '500')
                            rate = float(abilities[aura]['Oar1.1.1']) * 100
                            self.assertAlmostEqual(rate, (1, 1.5, 3, 3.8, 4.5, 5)[rank-1])
                            self.assertIn(f'|cff86e99d{rate:g}%|r', tip)
                        elif code == sentry:
                            ward = spell[f'hwdu.{rank}.0']
                            self.assertEqual(int(units[ward]['uhpm']), (50, 100, 125, 175, 200, 250)[rank-1])
                            self.assertIn('Adt1', units[ward]['uabi'].split(','))
                        else:
                            unit = units[spell[f'Hwe1.{rank}.0']]
                            base = int(unit['ua1b'])
                            # The stock level-one Serpent Ward rolls one three-sided die.
                            dice = int(unit.get('ua1d', '1'))
                            sides = int(unit.get('ua1s', '3'))
                            self.assertIn(f'|cffff8979{base+dice}-{base+dice*sides}|r', tip)
                            self.assertIn('Summons '+spell[f'Hwe2.{rank}.1']+' ', tip)
