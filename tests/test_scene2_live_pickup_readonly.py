"""Offline safety and input-parsing checks for the passive live bridge."""
import importlib.util
from pathlib import Path
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "scripts"))
spec = importlib.util.spec_from_file_location(
    "scene2_live_pickup_readonly", BASE / "scripts" / "scene2_live_pickup_readonly.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeItem:
    def GetStart(self): return 90000
    def GetEnd(self): return 90100
    def GetType(self): return "audio"
    def GetUniqueId(self): return "unique-clip"
    def GetProperties(self):
        return {"AudioVolume": 9.0, "AudioVolumeEnabled": True}


class FakeTimeline:
    def __init__(self):
        self.items = [FakeItem()]
        self.fps = "25"
    def GetUniqueId(self): return "unique-timeline"
    def GetSettings(self): return {"timelineFrameRate": self.fps}
    def GetStartFrame(self): return 90000
    def GetStartTimecode(self): return "01:00:00:00"
    def GetCurrentTimecode(self): return "01:00:01:00"
    def GetTrackCount(self, kind): return 4 if kind == "audio" else 0
    def GetItemListInTrack(self, kind, track):
        return self.items if kind == "audio" and track == 4 else []


class FakeProject:
    def __init__(self): self.timeline = FakeTimeline()
    def GetUniqueId(self): return "unique-project"
    def GetCurrentTimeline(self): return self.timeline


class FakeManager:
    def __init__(self): self.project = FakeProject()
    def GetCurrentProject(self): return self.project


class FakeResolve:
    def __init__(self): self.manager = FakeManager()
    def GetProjectManager(self): return self.manager


class PassiveLiveBridgeTest(unittest.TestCase):
    def test_no_volume_setter_or_midi_output_in_bridge(self):
        source = (BASE / "scripts" / "scene2_live_pickup_readonly.py").read_text()
        lua = (BASE / "scripts" / "scene2_midi_bridge_probe.lua").read_text()
        self.assertNotIn("SetProperties(", source)
        self.assertNotIn(":sendCommand(", lua)
        self.assertNotIn("keyStroke(", lua)

    def test_read_only_snapshot(self):
        app = FakeResolve()
        identity, db = module.snapshot(app, 4)
        self.assertEqual(identity, ("unique-project", "unique-timeline", 4,
                                    "unique-clip", 90000.0, 90100.0))
        self.assertEqual(db, 9.0)

    def test_ambiguous_clip_blocks(self):
        app = FakeResolve()
        app.manager.project.timeline.items.append(FakeItem())
        with self.assertRaises(module.Blocked):
            module.snapshot(app, 4)

    def test_fractional_fps_blocks(self):
        app = FakeResolve()
        app.manager.project.timeline.fps = "29.97"
        with self.assertRaises(module.Blocked):
            module.snapshot(app, 4)

    def test_midi_validation(self):
        self.assertEqual(module.parse_event("1,16,91\n"), (1, 16, 91))
        self.assertEqual(module.parse_event("0,13,127\n"), (0, 13, 127))
        self.assertIsNone(module.parse_event("1,16,128"))
        self.assertIsNone(module.parse_event("1,16;91"))
        self.assertIsNone(module.parse_event("# passive MIDI"))
        self.assertIsNone(module.parse_event("999,16,91"))


if __name__ == "__main__":
    unittest.main()
