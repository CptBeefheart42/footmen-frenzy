"""Where the e2e runner clicks: positions in WC3's 4:3 UI area, at any window size."""
import unittest

from tests.e2e.client import ui_point


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


if __name__ == "__main__":
    unittest.main()
