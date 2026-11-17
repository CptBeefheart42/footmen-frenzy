"""The skills scenario's data generator: JASS literals, map fixes, level counts, orders and chunking."""
import tempfile
import unittest
from pathlib import Path

from tests.common.paths import REPO
from tests.e2e import gen_skills
from tests.tooling.fixtures import E2E_OVERRIDES

MAP_FIXES = REPO / "data" / "object_overrides.csv"
ORDERS = REPO / "tests" / "e2e" / "ability_orders.csv"


def object_data():
    """A dump with Blizzard (AHbz), a Channel copy and the e2e Raze ability."""
    data = gen_skills.ObjectData()
    data.heroes = {"Hamg": ["AHbz", "A0CH"], "Hpal": ["AHbz", "E2Ra"]}
    data.base = {"AHbz": "AHbz", "A0CH": "ANcl", "E2Ra": "ACtb"}
    data.cells["AHbz"] = {("Hbz4", 5): ("Unreal", "25"), ("amcs", 1): ("Int", "75"), ("acdn", 1): ("Unreal", "6")}
    data.cells["A0CH"] = {("Ncl6", 1): ("String", "thunderbolt"), ("alev", 0): ("Int", "3")}
    data.cells["E2Ra"] = {}
    return data


class LiteralsTest(unittest.TestCase):

    def test_jreal(self):
        self.assertEqual(gen_skills.jreal("5"), "5.0")
        self.assertEqual(gen_skills.jreal(0.25), "0.25")
        self.assertEqual(gen_skills.jreal(1e-7), "0.000000")

    def test_jstr(self):
        self.assertEqual(gen_skills.jstr('a"b\\c'), '"a\\"b\\\\c"')


class ObjectDataTest(unittest.TestCase):

    def test_map_fixes_apply(self):
        data = object_data()
        data.apply_overrides(MAP_FIXES)
        self.assertEqual(data.cells["AHbz"][("Hbz4", 5)][1], "0", "Blizzard never damages buildings")

    def test_e2e_overrides_apply_keep_commas_and_skip_new_rows(self):
        data = object_data()
        data.apply_overrides(E2E_OVERRIDES)
        self.assertEqual(data.cells["E2Ra"][("atar", 1)][1],
                         "air,ground,structure,enemies,neutral,vulnerable,invulnerable")
        self.assertNotIn(("<new>", 0), data.cells["E2Ra"])

    def test_unset_removes_a_cell(self):
        data = object_data()
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "fix.csv"
            f.write_text("# a comment\nAHbz,amcs,1,0,Int,<unset>\n")
            data.apply_overrides(f)
        self.assertNotIn(("amcs", 1), data.cells["AHbz"])

    def test_levels_and_owners(self):
        data = object_data()
        self.assertEqual(data.levels("A0CH"), 3)
        self.assertEqual(data.levels("AHbz"), 5)
        self.assertEqual(data.skill_owners()["AHbz"], "Hamg")

    def test_channel_is_ordered_by_its_base_order_id(self):
        orders = gen_skills.load_orders([ORDERS])
        data = object_data()
        self.assertEqual(data.order("A0CH", orders), ("thunderbolt", ""))
        self.assertEqual(data.order("AHbz", orders)[0], "blizzard")


class EmitTest(unittest.TestCase):

    def test_expectation_and_calls(self):
        data = object_data()
        calls, n, exp = gen_skills.skill_calls(data, "AHbz", "Hamg", gen_skills.load_orders([ORDERS]))
        self.assertEqual(calls[0], "call FF_SK_Abil('AHbz', 'Hamg', 5, \"blizzard\", \"\")")
        self.assertEqual(n, 3)
        self.assertEqual(exp["lv"][1], {"amcs": 75, "acdn": 6.0, "atar": None})

    def test_chunks(self):
        text, n = gen_skills.emit_jass(["call X()"] * (gen_skills.CHUNK + 1), ["AHbz"], 1, [], 10, "0.5 0.5")
        self.assertEqual(n, 2)
        self.assertIn("function FF_SK_Data1 takes nothing returns nothing", text)
        self.assertIn("    elseif i == 1 then", text)
        self.assertIn('    return "0.5 0.5"', text)


if __name__ == "__main__":
    unittest.main()
