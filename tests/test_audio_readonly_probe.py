"""Offline tests for the strictly read-only Resolve audio discovery probe."""

import ast
import contextlib
import io
import runpy
import unittest
from pathlib import Path


PROBE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "scene2_audio_readonly_probe.py"


class AudioProbeSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PROBE_PATH.read_text(encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cls.exports = runpy.run_path(str(PROBE_PATH))
        cls.output = out.getvalue()

    def test_safe_when_resolve_absent(self):
        self.assertIn("SCENE2_AUDIO_READONLY_PROBE=START", self.output)
        self.assertIn("No changes made.", self.output)

    def test_no_mutation_calls(self):
        tree = ast.parse(self.source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertFalse(
                    node.func.attr.startswith(("Set", "Delete", "Insert", "Append")),
                    "Probe has an unexpected timeline mutation call",
                )
        # Dynamic method names passed through the wrapper are read-only.
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "call" and len(node.args) >= 2:
                    name = node.args[1]
                    if isinstance(name, ast.Constant):
                        self.assertTrue(str(name.value).startswith("Get"))

    def test_timecode_conversion_requires_safe_format(self):
        f = self.exports["frame_from_timecode"]
        self.assertEqual(f("01:00:00:00", 25), 90000)
        self.assertEqual(f("01:00:00:00", 50), 180000)
        self.assertEqual(f("00:01:02:24", 25), 1574)
        self.assertIsNone(f("01:00:00;00", 30))
        self.assertIsNone(f("00:00:00:25", 25))
        self.assertIsNone(f("00:60:00:00", 25))
        self.assertIsNone(f("random", 25))
        self.assertIsNone(f("01:00:00:00", 29.97))


if __name__ == "__main__":
    unittest.main()
