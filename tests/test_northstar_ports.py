"""Check standalone map inputs without downloading a map or launching Warcraft III."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

PORTS = Path(__file__).resolve().parents[1] / "projects" / "ports" / "northstar"
sys.path.insert(0, str(PORTS))
from port import Port, checked_base
import hotkeys


class NorthStarPortTest(unittest.TestCase):
    """Validate the source layout, control bindings, and starting-map checksum gate."""

    def test_project_inputs(self):
        for name in ("799x", "solo", "ffa"):
            with self.subTest(project=name):
                meta = json.loads((PORTS / name / "project.json").read_bytes())
                start = meta["start_map"]
                project = Port(name, meta["map_type"], start["name"])
                self.assertRegex(start["sha256"], r"^[0-9a-f]{64}$")
                assets = json.loads(project.binaries.read_bytes())
                objects = {p.stem for p in project.objects.glob("*.txt")}
                text = {p.relative_to(project.src).as_posix()
                        for p in project.src.rglob("*") if p.is_file()}
                self.assertEqual(len(objects), 14)
                self.assertIn("war3map.j", text)
                self.assertFalse(set(assets) & (objects | text))
                self.assertEqual(hotkeys.differences(project), [])

    def test_local_starting_map_must_match(self):
        project = Port("ffa", "FFA Foots", "map.w3x")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "map.w3x"
            cache = Path(temp) / "cache.w3x"
            path.write_bytes(b"local test input")
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(checked_base(project, sha, path, cache), path.resolve())
            path.write_bytes(b"wrong version")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                checked_base(project, sha, path, cache)
            self.assertFalse(cache.exists())
