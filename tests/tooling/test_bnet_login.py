"""The Battle.net login's credentials file handling."""
import os
import tempfile
import unittest
from pathlib import Path

from tests.e2e import bnet_login


class EnvFileTest(unittest.TestCase):

    def test_parse_env(self):
        text = ('# test account\n'
                'export FF_E2E_BNET_EMAIL="tester@example.org"\n'
                "  FF_E2E_BNET_PASSWORD='p=a#ss'  \n"
                'NOT A LINE\n')
        self.assertEqual(bnet_login.parse_env(text),
                         {"FF_E2E_BNET_EMAIL": "tester@example.org", "FF_E2E_BNET_PASSWORD": "p=a#ss"})

    def write(self, tmp, text, mode):
        f = Path(tmp) / "e2e-bnet.env"
        f.write_text(text)
        os.chmod(f, mode)
        return f

    def test_creds_from_a_private_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.write(tmp, "FF_E2E_BNET_EMAIL=a@b.c\nFF_E2E_BNET_PASSWORD=x\n", 0o600)
            self.assertEqual(bnet_login.creds(f), ("a@b.c", "x"))

    def test_refuses_a_file_others_can_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.write(tmp, "FF_E2E_BNET_EMAIL=a@b.c\nFF_E2E_BNET_PASSWORD=x\n", 0o644)
            with self.assertRaises(SystemExit) as e:
                bnet_login.creds(f)
        self.assertIn("readable by others", str(e.exception))

    def test_refuses_missing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = self.write(tmp, "FF_E2E_BNET_EMAIL=a@b.c\n", 0o600)
            with self.assertRaises(SystemExit):
                bnet_login.creds(f)


if __name__ == "__main__":
    unittest.main()
