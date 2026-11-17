"""The probe verdict on a small probe file and the committed known deviations."""
import unittest

from tests.e2e import check_probe
from tests.tooling.fixtures import PROBE_EXPECT

LANES = ["BZ lane1 L1 lost_14s: hwtw=0 hfoo=33 hfoo=33",
         "BZ lane2 L4 lost_14s: hwtw=0 hfoo=115 hfoo=115",
         "BZ lane3 L6 lost_14s: hwtw=0 hfoo=155 hfoo=155",
         "BZ lane4 L2 lost_14s: hfoo=42 hgry=38 Hpal=28",
         "BZ lane5 L5 lost_14s: hfoo=130 hgry=126 Hpal=94",
         "BZ lane6 L6 lost_14s: hfoo=155 hgry=151 Hpal=113",
         "BZ lane1 L1 buildingDamage(Hbz4)=0.000"]


def probe(*extra, lanes=LANES):
    return ["FF 3.0 probe v3 | 120 cells", "S fill zero=0 default=0 other=0 noabil=0 unreadable=0", *lanes, *extra,
            "END"]


class ProbeTest(unittest.TestCase):

    def setUp(self):
        self.exp = check_probe.Expectations.load(PROBE_EXPECT)

    def test_expectations_file(self):
        self.assertTrue(self.exp.readbacks)

    def test_good_run_passes(self):
        checks, n = check_probe.judge(probe(), self.exp)
        self.assertEqual([r.name for r in checks.failed], [])
        self.assertEqual(n, 0)

    def test_blizzard_level_without_damage_fails(self):
        lanes = [line.replace("hfoo=130 hgry=126 Hpal=94", "hfoo=0 hgry=0 Hpal=0") for line in LANES]
        checks, _ = check_probe.judge(probe(lanes=lanes), self.exp)
        self.assertTrue(any("hit nothing" in r.name for r in checks.failed))

    def test_building_damage_fails(self):
        checks, _ = check_probe.judge(probe("BZ lane2 L4 buildingDamage(Hbz4)=25.0"), self.exp)
        self.assertTrue(any("AHbz map fix missing" in r.name for r in checks.failed))

    def test_new_readback_deviation_fails(self):
        rows = probe("R XXXX abcd L5 stored=1 read=0")
        rows[1] = "S fill zero=1 default=0 other=0 noabil=0 unreadable=0"
        checks, _ = check_probe.judge(rows, self.exp)
        self.assertIn("new readback deviation: XXXX abcd L5", [r.name for r in checks.failed])


if __name__ == "__main__":
    unittest.main()
