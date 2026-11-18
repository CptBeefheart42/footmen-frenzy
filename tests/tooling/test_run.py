"""The e2e runner: its reading of the map's input requests (the phase file's WAIT rows), and how it tells a map that
crashes or runs out of memory while loading from one that is still loading."""
import unittest
from pathlib import Path
from unittest import mock

from tests.e2e import run
from tests.e2e.run import EXIT_LOAD_CRASH, Wait, load_problem


class WaitTest(unittest.TestCase):

    def test_requests(self):
        self.assertEqual(Wait.parse("WAIT 3 chat -zoom 3500"), Wait("3", "chat", "-zoom 3500"))
        self.assertEqual(Wait.parse("WAIT 7 key F"), Wait("7", "key", "F"))
        self.assertEqual(Wait.parse("WAIT 0 click 0.5 0.478"), Wait("0", "click", "0.5 0.478"))
        self.assertEqual(Wait.parse("WAIT 4 seq key F11; wait 1.5; shot; tap 0.62 0.4; key Escape"),
                         Wait("4", "seq", "key F11; wait 1.5; shot; tap 0.62 0.4; key Escape"))

    def test_invalid_rows(self):
        for row in ("GO", "WAIT x chat hi", "WAIT 1 click here", "WAIT 1 key two keys", "WAIT 1 jump",
                    "WAIT 1 seq tap here", "WAIT 1 seq key F11; rm -rf /", "WAIT 1 seq "):
            with self.subTest(row=row):
                self.assertIsNone(Wait.parse(row))



class LoadProblemTest(unittest.TestCase):
    GB = 2**20  # kB

    def test_a_load_that_stays_under_the_limit_may_go_on(self):
        self.assertIsNone(load_problem(int(4.4 * self.GB), 7 * self.GB))  # the main map's measured peak

    def test_a_load_over_the_limit_has_failed(self):
        self.assertIn("8.3 GB", load_problem(int(8.3 * self.GB), 7 * self.GB))  # the setless-object map

    def test_a_game_that_exited_has_failed(self):
        self.assertEqual(load_problem(None, 7 * self.GB), "WC3 exited while the map loaded")


class FakeClient:
    """A client whose game reports a fixed memory reading; records how often the game was launched and closed."""

    def __init__(self, rss_kb):
        self.rss = rss_kb
        self.closed = 0
        self.data = Path("/nonexistent")

    def wc3_rss_kb(self):
        return self.rss

    def close_wc3(self):
        self.closed += 1

    def close_bnet(self):
        pass

    def set_args(self, args):
        pass

    def start_bnet(self):
        pass

    def press(self, win, *keys):
        pass

    def screenshot(self, win, path):
        pass


class LaunchTest(unittest.TestCase):

    def launch(self, client, started=lambda: False):
        with mock.patch.object(run, "open_game_window", return_value=7) as opened, \
                mock.patch.object(run, "start_from_menu") as menu, \
                mock.patch.object(run, "game_started", side_effect=lambda c, p: started()), \
                mock.patch.object(run.time, "sleep"), mock.patch.object(run, "log"):
            try:
                got = run.launch(client, Path("m.w3x"), Path("/tmp"), [], "FF e2e main ffa")
            except SystemExit as e:
                got = e.code
            self.assertTrue(all(call.args[2] == "FF e2e main ffa" for call in menu.call_args_list))
            return got, opened.call_count

    def test_a_map_that_runs_out_of_memory_stops_at_once(self):
        c = FakeClient(9 * 2**20)
        self.assertEqual(self.launch(c), (EXIT_LOAD_CRASH, 1))  # no second attempt
        self.assertEqual(c.closed, 1)

    def test_a_game_that_exits_while_loading_stops_at_once(self):
        self.assertEqual(self.launch(FakeClient(None)), (EXIT_LOAD_CRASH, 1))

    def test_a_map_that_loads_gives_the_window(self):
        polls = iter([False, False, True])
        self.assertEqual(self.launch(FakeClient(4 * 2**20), lambda: next(polls)), (7, 1))

    def test_a_plain_load_hang_is_tried_again(self):
        code, launches = self.launch(FakeClient(4 * 2**20))
        self.assertEqual(launches, run.LAUNCH_ATTEMPTS)
        self.assertIn("did not start", code)



class ScreenTest(unittest.TestCase):
    """The colours were sampled from screenshots of the 3.0.1 client."""

    MAIN_MENU = [(0, 49, 50)] * 4
    LOGIN = [(0, 40, 92), (0, 59, 111), (0, 37, 82)]
    CONNECTING = [(21, 19, 17), (22, 20, 18), (34, 32, 30)]
    CREATE_GAME = [(43, 42, 42), (46, 42, 40), (46, 43, 41), (51, 46, 44)]

    def test_the_main_menu(self):
        self.assertTrue(run.is_main_menu(self.MAIN_MENU))
        for other in (self.LOGIN, self.CONNECTING, self.CREATE_GAME, [None] * 4):
            self.assertFalse(run.is_main_menu(other))

    def test_the_game_s_own_login(self):
        self.assertTrue(run.is_login(self.LOGIN))
        for other in (self.MAIN_MENU[:3], self.CONNECTING, [None] * 3):
            self.assertFalse(run.is_login(other))

    def test_menu_points_scale_with_the_window(self):
        c = mock.Mock()
        c.geometry.return_value = {"WIDTH": "2804", "HEIGHT": "1648"}
        self.assertEqual(run.menu_px(c, 1, (1125, 338)), (2250, 676))
        c.geometry.return_value = {"WIDTH": "1402", "HEIGHT": "824"}
        self.assertEqual(run.menu_px(c, 1, (1125, 338)), (1125, 338))


if __name__ == "__main__":
    unittest.main()
