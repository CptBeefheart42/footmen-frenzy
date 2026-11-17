"""Staging an e2e build: the client added to the map's real hosting-bot list."""
import unittest

from tests.e2e import stage
from tests.tooling.fixtures import COMMON_J


class AddBotTest(unittest.TestCase):

    def test_bot_is_accepted_first_and_the_list_is_kept(self):
        text = COMMON_J.read_text()
        staged = stage.add_bot(text, "(E2E)Tester#100000")
        self.assertEqual(staged.count('FF_EndsWith(name, "(E2E)Tester#100000")'), 1)
        head = staged.split(stage.BOT_FUNC, 1)[1].splitlines()
        self.assertEqual(head[0], '    if name != null and FF_EndsWith(name, "(E2E)Tester#100000") then')
        self.assertEqual(staged.replace("\n".join(head[:3]) + "\n", "", 1), text, "nothing else changes")

    def test_refuses_an_ambiguous_list(self):
        with self.assertRaises(ValueError):
            stage.add_bot(stage.BOT_FUNC * 2, "A#1")

    def test_valid_bot(self):
        self.assertTrue(stage.valid_bot("(E2E)Tester#100000"))
        self.assertTrue(stage.valid_bot("Local Player"))
        self.assertFalse(stage.valid_bot("no tag"))
        self.assertFalse(stage.valid_bot('evil"#1'))

    def test_client_name_addon(self):
        self.assertIn('return ""', stage.client_name_addon("Local Player"))
        self.assertIn('return "A#1"', stage.client_name_addon("A#1"))


if __name__ == "__main__":
    unittest.main()
