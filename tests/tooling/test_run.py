"""The e2e runner's reading of the map's input requests (the phase file's WAIT rows)."""
import unittest

from tests.e2e.run import Wait


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


if __name__ == "__main__":
    unittest.main()
