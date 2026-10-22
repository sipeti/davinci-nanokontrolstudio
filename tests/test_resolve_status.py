"""Tests for the read-only Resolve Studio scripting probe (no Resolve installed)."""
import contextlib
import importlib.util
import io
import json
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "resolve_status.py"
spec = importlib.util.spec_from_file_location("resolve_status", MODULE_PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class Timeline:
    def GetName(self): return "ATEM ISO duplicate"
    def GetCurrentTimecode(self): return "01:02:03:04"


class Project:
    def GetName(self): return "test project"
    def GetCurrentTimeline(self): return Timeline()


class Manager:
    def GetCurrentProject(self): return Project()


class Resolve:
    def GetCurrentPage(self): return "edit"
    def GetProjectManager(self): return Manager()


class ResolveStatusTests(unittest.TestCase):
    def test_read_only_snapshot(self):
        api = types.SimpleNamespace(scriptapp=lambda name: Resolve())
        self.assertEqual(probe.snapshot(api), {
            "ok": True, "page": "edit", "project": "test project",
            "timeline": "ATEM ISO duplicate", "timecode": "01:02:03:04"})
        self.assertFalse(any(name.startswith("Set") for name in dir(probe)))
        
    def test_not_connected_fails_closed(self):
        api = types.SimpleNamespace(scriptapp=lambda name: None)
        self.assertEqual(probe.snapshot(api), {"ok": False, "error": "not_connected"})

    def test_main_returns_valid_json(self):
        api = types.SimpleNamespace(scriptapp=lambda name: Resolve())
        out = io.StringIO()
        with patch.dict(sys.modules, {"DaVinciResolveScript": api}):
            with contextlib.redirect_stdout(out):
                code = probe.main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["page"], "edit")

    def test_main_handles_disconnected(self):
        api = types.SimpleNamespace(scriptapp=lambda name: None)
        out = io.StringIO()
        with patch.dict(sys.modules, {"DaVinciResolveScript": api}):
            with contextlib.redirect_stdout(out):
                code = probe.main()
        self.assertNotEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["error"], "not_connected")


if __name__ == "__main__":
    unittest.main()
