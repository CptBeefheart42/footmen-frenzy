"""The e2e client: where it clicks (positions in WC3's 4:3 UI area, at any window size), the memory cap of the
programs it starts, and how it reads the game's memory."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.e2e.client import Client, scoped, ui_point


class UiPointTest(unittest.TestCase):

    def test_the_measured_window_gives_back_the_measured_pixels(self):
        # The trade scenario's Allies menu was measured in a 1402x824 window: gold icon 883,170, Accept 612,626.
        self.assertEqual(ui_point(1402, 824, 0.6657, 0.2063), (883, 170))
        self.assertEqual(ui_point(1402, 824, 0.419, 0.7597), (612, 626))

    def test_a_4_3_window_is_all_ui_area(self):
        self.assertEqual(ui_point(1024, 768, 0.0, 0.0), (0, 0))
        self.assertEqual(ui_point(1024, 768, 0.5, 0.5), (512, 384))
        self.assertEqual(ui_point(1024, 768, 1.0, 1.0), (1024, 768))

    def test_a_wide_window_adds_margins_left_and_right(self):
        # 1920x1080: the UI area is 1440 wide, starting 240 px in.
        self.assertEqual(ui_point(1920, 1080, 0.0, 0.0), (240, 0))
        self.assertEqual(ui_point(1920, 1080, 1.0, 0.5), (1680, 540))

    def test_the_centre_stays_the_centre(self):
        # A dialog button in the middle (the host's game-type dialog) lands in the middle of any window.
        for w, h in ((1402, 824), (1024, 768), (1920, 1080), (2560, 1080)):
            with self.subTest(size=(w, h)):
                self.assertEqual(ui_point(w, h, 0.5, 0.478)[0], w // 2)



class ScopedTest(unittest.TestCase):

    CMD = ["/proton", "run", "Battle.net.exe"]

    def test_the_program_runs_in_a_capped_scope(self):
        self.assertEqual(scoped(self.CMD, "9G", "/usr/bin/systemd-run"),
                         ["/usr/bin/systemd-run", "--user", "--scope", "--quiet", "--collect", "-p", "MemoryMax=9G",
                          "--", *self.CMD])

    def test_no_cap_asked_or_no_systemd_runs_it_as_it_is(self):
        self.assertEqual(scoped(self.CMD, "0", "/usr/bin/systemd-run"), self.CMD)
        self.assertEqual(scoped(self.CMD, "", "/usr/bin/systemd-run"), self.CMD)
        with mock.patch("tests.e2e.client.shutil.which", return_value=None):
            self.assertEqual(scoped(self.CMD, "9G"), self.CMD)


class RssTest(unittest.TestCase):

    def setUp(self):
        self.proc = Path(tempfile.mkdtemp())

    def status(self, pid, text):
        (self.proc / str(pid)).mkdir()
        (self.proc / str(pid) / "status").write_text(text)

    def test_reads_the_resident_memory(self):
        self.status(42, "Name:\tWarcraft III.exe\nVmPeak:\t 9000000 kB\nVmRSS:\t 4351232 kB\nThreads:\t80\n")
        self.assertEqual(Client.rss_kb(42, self.proc), 4351232)

    def test_a_process_that_is_gone_has_none(self):
        self.assertIsNone(Client.rss_kb(43, self.proc))

    def test_a_process_without_memory_has_none(self):  # a zombie's status has no VmRSS line
        self.status(44, "Name:\tWarcraft III.exe\nState:\tZ (zombie)\n")
        self.assertIsNone(Client.rss_kb(44, self.proc))


if __name__ == "__main__":
    unittest.main()
