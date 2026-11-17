"""Reading and rewriting Preload files."""
import tempfile
import unittest
from pathlib import Path

from tests.common.preload import read_rows, rewrite_rows
from tests.tooling.fixtures import SAMPLE


class PreloadTest(unittest.TestCase):

    def test_missing_file_reads_as_none(self):
        self.assertIsNone(read_rows(Path("/nonexistent/ff_result.txt")))

    def test_rewrite_keeps_the_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "ff_result.txt"
            f.write_text(SAMPLE.read_text())
            rewrite_rows(f, lambda r: None if r.startswith("gameend,") else r.replace("Alpha", "Zulu"))
            rows = read_rows(f)
            text = f.read_text()
        self.assertEqual(len(rows), len(read_rows(SAMPLE)) - 1)
        self.assertFalse(any(r.startswith("gameend,") for r in rows))
        self.assertIn("1:Zulu#1111", rows[2])
        self.assertIn("call PreloadEnd( 0.0 )", text)


if __name__ == "__main__":
    unittest.main()
