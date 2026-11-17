"""The contract checks against docs/result-contract.md and, where a checkout exists, the bot's own parser."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.common.ffresult import STATS_KEYS, FFResultFile
from tests.common.paths import REPO
from tests.common.preload import read_rows, rewrite_rows
from tests.simulation import contract
from tests.tooling.fixtures import CONTRACT, SAMPLE

BOT = Path(os.environ.get("FF_EFL_BOT", REPO.parent / "efl-bot-2.0"))


def sim_out(tmp, mutate=None):
    """A simulation out dir holding the sample as main/sample/ff_result.txt, optionally doctored."""
    d = Path(tmp) / "main" / "sample"
    d.mkdir(parents=True)
    shutil.copy2(SAMPLE, d / "ff_result.txt")
    if mutate:
        rewrite_rows(d / "ff_result.txt", mutate)
    return Path(tmp)


class DocKeysTest(unittest.TestCase):

    def test_documented_stats_keys_are_the_checked_ones(self):
        stats, modes = contract.doc_keys(CONTRACT)
        self.assertEqual(stats - {"state", "left_t"}, set(STATS_KEYS))
        self.assertIn("koth", modes)
        self.assertIn("nopool", modes)

    def test_sample_matches_the_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            checks = contract.check_doc_keys(sim_out(tmp))
        self.assertEqual([r.name for r in checks.results], ["contract-doc main/sample"])
        self.assertEqual(checks.failed, [])

    def test_undocumented_key_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = sim_out(tmp, lambda r: r + ",secret=1" if r.startswith("stats,1,") else r)
            checks = contract.check_doc_keys(out)
        self.assertEqual(len(checks.failed), 1)
        self.assertIn("secret", checks.failed[0].detail)

    def test_missing_documented_key_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = sim_out(tmp, lambda r: r.replace(",food=48", "") if r.startswith("stats,1,") else r)
            checks = contract.check_doc_keys(out)
        self.assertIn("food", checks.failed[0].detail)

    def test_malformed_row_fails_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = sim_out(tmp, lambda r: r.replace("stats,2,", "stats,two,", 1))
            checks = contract.check_doc_keys(out)
        self.assertIn("malformed row", checks.failed[0].detail)


@unittest.skipUnless(contract.load_parser(BOT), f"no efl-bot checkout at {BOT}")
class BotParserTest(unittest.TestCase):
    """The sample through the bot's real parser (skipped where no checkout exists, e.g. in CI)."""

    def test_sample_loses_nothing(self):
        parser = contract.load_parser(BOT)
        mine = FFResultFile.parse(read_rows(SAMPLE))
        self.assertEqual(contract.lost_values(mine, parser.parse(SAMPLE.read_text())), [])

    def test_a_changed_value_is_reported(self):
        parser = contract.load_parser(BOT)
        mine = FFResultFile.parse(read_rows(SAMPLE))
        mine.stats[1].values["food"] = "49"
        self.assertTrue(any("stats,1 food" in p for p in contract.lost_values(mine, parser.parse(SAMPLE.read_text()))))


if __name__ == "__main__":
    unittest.main()
