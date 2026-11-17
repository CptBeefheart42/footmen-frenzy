"""The e2e checker's file checks on a run built from the result sample, and its negative controls: the same
mutations as tests/e2e/selftest.py must make the right check fail. Needs no WC3 client."""
import tempfile
import unittest

from tests.common.preload import rewrite_rows
from tests.e2e import check_e2e, selftest
from tests.tooling.fixtures import make_run, preload_file


def second_place_tie(d):
    """The sample has two sides: its second place becomes a second first place."""
    rewrite_rows(selftest.result_file(d), lambda r: r.replace("placement,2,", "placement,1,", 1))


def failed_names(run):
    return [r.name for r in run.failed]


class FileChecksTest(unittest.TestCase):

    def check(self, bot=False, mutate=None):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_run(tmp, bot=bot)
            if mutate:
                mutate(d)
            run = check_e2e.Run(d)
            res = check_e2e.check_files(run, bot, need_end=True)
        return run, res

    def test_sample_passes(self):
        run, res = self.check()
        self.assertEqual(failed_names(run), [])
        self.assertEqual(res.winner, "team1")

    def test_sample_passes_on_a_bot_client(self):
        run, _ = self.check(bot=True)
        self.assertEqual(failed_names(run), [])
        self.assertEqual(run.killlog.owners["Delta#4444"].unit_died, 90)

    def test_mutations_fail_for_the_right_reason(self):
        cases = [(selftest.drop_gameend, "gameend written once"),
                 (second_place_tie, "placements 1..N, no ties"),
                 (selftest.lose_second_stats_row, "stats,3: every key, integers"),
                 (selftest.wrong_token, "result files written")]
        for mutate, expect in cases:
            with self.subTest(mutation=mutate.__name__):
                run, _ = self.check(mutate=mutate)
                self.assertIn(expect, failed_names(run))

    def test_short_killlog_row_fails(self):
        run, _ = self.check(bot=True, mutate=selftest.short_killlog_row)
        self.assertIn("kill log owner rows: 5 fields, integers", failed_names(run))

    def test_malformed_result_fails_instead_of_crashing(self):
        def bad_slot(d):
            rewrite_rows(selftest.result_file(d), lambda r: r.replace("use,2,", "use,x,", 1))
        run, res = self.check(mutate=bad_slot)
        self.assertIsNone(res)
        self.assertIn("result file parses", failed_names(run))

    def test_scenario_stopping_early_must_not_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = check_e2e.Run(make_run(tmp))
            check_e2e.check_files(run, False, need_end=False)
        self.assertIn("no game end (the scenario stops early)", failed_names(run))


class HelpersTest(unittest.TestCase):

    def test_flaky_split(self):
        single, repeated = check_e2e.flaky_split([("A", "A/1"), ("B", "B/1"), ("B", "B/3")])
        self.assertEqual(single, ["A/1"])
        self.assertEqual(repeated, ["B/1", "B/3"])

    def test_skill_exceptions_file_parses(self):
        exc = check_e2e.load_skill_exceptions()
        self.assertTrue(exc)
        self.assertTrue(all(len(e) == 3 for e in exc))


if __name__ == "__main__":
    unittest.main()


def kill_credit_rows(lost_case=None):
    """ff_e2e records of a kill_credit run in which every case's kill counts, except `lost_case` (as before the
    kill-credit hooks: the engine names no killer, nothing is counted, no XP)."""
    rows = ["e2e,scenario=kill_credit,local=0,bot=0,file=ff_result.txt,token="]
    hk = 0
    for n in check_e2e.KC_CASES:
        lost = n == lost_case
        before = f"uk1=0,hk1={hk},ud1=0,hd1=0,uk4=0,hk4=0,ud4=0,hd4={hk}"
        rows.append(f"kc,case={n},when=0,{before},gold1=500,xp=0")
        rows.append(f"cast,case={n},order=1")
        rows.append(f"death,case={n},victim=4,vtype=H005,killer=" + ("none" if lost else "1,kalive=1,ktype=h01K"))
        rows.append(f"end,case={n},died=1,secs=1.0")
        hk += 0 if lost else 1
        rows.append(f"kc,case={n},when=1,uk1=0,hk1={hk},ud1=0,hd1=0,uk4=0,hk4=0,ud4=0,hd4={hk},gold1=500,"
                    f"xp={0 if lost else 100}")
    return rows + ["END"]


class KillCreditTest(unittest.TestCase):

    def check(self, rows):
        with tempfile.TemporaryDirectory() as tmp:
            d = make_run(tmp)
            (d / "ff_e2e.txt").write_text(preload_file(rows))
            run = check_e2e.Run(d)
            check_e2e.check_kill_credit(run, False)
        return [n for n in failed_names(run) if n.startswith("case ")]

    def test_every_kill_counted_passes(self):
        self.assertEqual(self.check(kill_credit_rows()), [])

    def test_a_lost_kill_fails_its_case(self):
        failed = self.check(kill_credit_rows(lost_case=2))
        self.assertTrue(failed)
        self.assertTrue(all(n.startswith("case 2 ") for n in failed), failed)
        self.assertEqual(len(failed), 3)    # killer, counters, XP
