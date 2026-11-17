"""The result file model on the committed sample (docs/ff_result-sample.txt) and the kill log model."""
import unittest

from tests.common.ffresult import STATS_KEYS, FFResultFile, FormatError, KillLog, StatsRow
from tests.common.preload import read_rows
from tests.tooling.fixtures import KILLLOG_ROWS, SAMPLE


class SampleFileTest(unittest.TestCase):
    """The sample is the contract's example: it must parse into a complete, finished game."""

    @classmethod
    def setUpClass(cls):
        cls.rows = read_rows(SAMPLE)
        cls.res = FFResultFile.parse(cls.rows)

    def test_format_first_gameend_last(self):
        self.assertEqual(self.rows[0], "format,2")
        self.assertTrue(self.rows[-1].startswith("gameend,"))
        self.assertEqual(self.res.result_kinds[-1], "gameend")

    def test_roster_and_merged_stats(self):
        self.assertEqual(sorted(self.res.roster), [1, 2, 3, 4, 5, 6])
        self.assertEqual(self.res.roster[1], "Alpha#1111")
        for slot in self.res.roster:
            with self.subTest(slot=slot):
                missing = [k for k in STATS_KEYS if self.res.stat(slot, k) is None]
                self.assertEqual(missing, [], "both stats rows of the slot must be merged")

    def test_states_and_leaver(self):
        self.assertEqual([self.res.stats[s].state for s in range(1, 7)], ["alive"] * 3 + ["out", "left", "out"])
        self.assertEqual(self.res.stats[5].values["left_t"], "21:47")

    def test_outcome(self):
        self.assertEqual(self.res.winner, "team1")
        self.assertEqual(self.res.placement_sides, ["team1", "team2"])
        self.assertEqual(self.res.places, [1, 2])
        self.assertEqual([e.subject for e in self.res.events_of("out")], ["5", "4", "6"])

    def test_usage_rows_of_a_slot_are_summed_up(self):
        items = self.res.use[(1, "item")]
        self.assertEqual(items["rde3"], 2)
        self.assertEqual(items["clfm"], 1, "the second use,1,item row continues the first")
        self.assertEqual(self.res.skills[(2, "H008")][:2], ["AHhb", "AHds"])

    def test_events_and_other_rows(self):
        picks = [(e.subject,) + e.extra for e in self.res.events_of("pick")]
        self.assertIn(("4", "O004", "repick"), picks)
        self.assertEqual(len(self.res.other_rows("koth")), 2)
        self.assertEqual(self.res.unknown, [])


class ModelTest(unittest.TestCase):
    """Edge cases of the model."""

    def test_a_later_write_replaces_the_stats_row(self):
        old = StatsRow(1, {"t": "01:00", "given": "5", "recv": "1"})
        self.assertEqual(old.merge(StatsRow(1, {"t": "01:30", "given": "7"})).values, {"t": "01:30", "given": "7"})
        self.assertEqual(old.merge(StatsRow(1, {"t": "01:00", "mined": "3"})).values["recv"], "1")

    def test_malformed_rows_raise_format_error(self):
        for row in ("roster,x:Alpha#1111", "stats,one,t=00:01", "use,1,item,ratc=many", "skills,1"):
            with self.subTest(row=row), self.assertRaises(FormatError):
                FFResultFile.parse(["format,2", row])

    def test_unknown_records_are_kept(self):
        res = FFResultFile.parse(["format,2", "brandnew,1"])
        self.assertEqual(res.unknown, ["brandnew,1"])


class KillLogTest(unittest.TestCase):
    """The kill log model."""

    def test_parse(self):
        log = KillLog.parse(KILLLOG_ROWS)
        self.assertEqual(log.owners["(Paladin) Alpha#1111"].hero, 2)
        self.assertEqual(log.bad_owner_rows, [])
        self.assertEqual(log.bad_feed_rows, [])

    def test_short_rows_are_reported(self):
        log = KillLog.parse(KILLLOG_ROWS[:1] + ["Alpha#1111,1,2,3", "herokill,1,2"])
        self.assertEqual(log.bad_owner_rows, ["Alpha#1111,1,2,3"])
        self.assertEqual(log.bad_feed_rows, ["herokill,1,2"])
        self.assertEqual(log.owners, {})


if __name__ == "__main__":
    unittest.main()
