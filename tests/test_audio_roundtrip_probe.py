"""Offline safety checks: Scene 2 audio round-trip never writes by default."""
import contextlib
import importlib.util
import io
import pathlib
import unittest


PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "scene2_audio_roundtrip_probe.py"


class Item:
    def __init__(self):
        self.volume = 9.0
        self.enabled = True
        self.uid = "audio-item-4"
        self.calls = []

    def GetStart(self): return 90100
    def GetEnd(self): return 90200
    def GetType(self): return "audio"
    def GetUniqueId(self): return self.uid
    def GetProperties(self):
        return {"AudioVolume": self.volume,
                "AudioVolumeEnabled": self.enabled}
    def SetProperties(self, props):
        self.calls.append(dict(props))
        self.volume = props["AudioVolume"]
        return True


class Timeline:
    def __init__(self, item):
        self.item = item
        self.uid = "timeline-uid"
        self.fps = "25.0"
        self.tc = "01:00:05:00"
        self.items = [item]

    def GetUniqueId(self): return self.uid
    def GetName(self): return "Audio QA timeline"
    def GetSettings(self): return {"timelineFrameRate": self.fps}
    def GetStartTimecode(self): return "01:00:00:00"
    def GetStartFrame(self): return 90000
    def GetCurrentTimecode(self): return self.tc
    def GetTrackCount(self, kind): return 4 if kind == "audio" else 0
    def GetItemListInTrack(self, kind, index):
        return self.items if kind == "audio" and index == 4 else []


class Project:
    def __init__(self, timeline):
        self.timeline = timeline
        self.uid = "project-uid"

    def GetCurrentTimeline(self): return self.timeline
    def GetUniqueId(self): return self.uid
    def GetName(self): return "Audio QA backup"


class Manager:
    def __init__(self, project): self.project = project
    def GetCurrentProject(self): return self.project


class Resolve:
    def __init__(self, project): self.manager = Manager(project)
    def GetProjectManager(self): return self.manager


class RoundtripSafetyTest(unittest.TestCase):
    def setUp(self):
        self.item = Item()
        self.timeline = Timeline(self.item)
        self.project = Project(self.timeline)
        self.app = Resolve(self.project)
        spec = importlib.util.spec_from_file_location("scene2_roundtrip_test", PATH)
        self.mod = importlib.util.module_from_spec(spec)
        with contextlib.redirect_stdout(io.StringIO()) as self.load_output:
            spec.loader.exec_module(self.mod)
        self.mod.resolve = self.app
        self.output = io.StringIO()

    def preview(self):
        with contextlib.redirect_stdout(self.output):
            return self.mod.scene2_preview(4)

    def try_roundtrip(self, token=None, confirmation=None, expected_project=None):
        arm = self.mod._ARMED
        with contextlib.redirect_stdout(self.output):
            return self.mod.scene2_roundtrip(
                token=token if token is not None else arm["token"],
                expected_project=expected_project if expected_project is not None
                    else "Audio QA backup",
                confirmation=confirmation if confirmation is not None
                    else self.mod._CONSENT)

    def test_import_and_preview_are_read_only(self):
        self.assertIn("WRITES=0", self.load_output.getvalue())
        self.assertTrue(self.preview())
        self.assertEqual(self.item.calls, [])
        self.assertEqual(self.item.volume, 9.0)

    def test_requires_fresh_exact_consent(self):
        self.assertTrue(self.preview())
        self.assertFalse(self.try_roundtrip(token="wrong"))
        self.assertEqual(self.item.calls, [])
        self.assertFalse(self.try_roundtrip(token="wrong"))  # consumed
        self.assertEqual(self.item.calls, [])

    def test_project_name_required(self):
        self.assertTrue(self.preview())
        self.assertFalse(self.try_roundtrip(expected_project="wrong"))
        self.assertEqual(self.item.calls, [])

    def test_successful_roundtrip_restores_original(self):
        self.assertTrue(self.preview())
        self.assertTrue(self.try_roundtrip())
        self.assertEqual(len(self.item.calls), 2)
        self.assertEqual(self.item.calls[0]["AudioVolume"], 9.5)
        self.assertEqual(self.item.calls[1]["AudioVolume"], 9.0)
        self.assertEqual(self.item.volume, 9.0)
        self.assertIn("SCENE2_ROUNDTRIP=PASS", self.output.getvalue())
        self.assertIsNone(self.mod._ARMED)

    def test_external_gain_change_blocks_write(self):
        self.assertTrue(self.preview())
        self.item.volume = 8.75
        self.assertFalse(self.try_roundtrip())
        self.assertEqual(self.item.calls, [])

    def test_project_timeline_and_clip_switch_block_write(self):
        for attr, owner, new_value in (
            ("uid", self.project, "project-other"),
            ("uid", self.timeline, "timeline-other"),
            ("uid", self.item, "clip-other"),
        ):
            previous = getattr(owner, attr)
            self.assertTrue(self.preview())
            setattr(owner, attr, new_value)
            self.assertFalse(self.try_roundtrip())
            self.assertEqual(self.item.calls, [])
            setattr(owner, attr, previous)

    def test_playhead_or_disabled_audio_blocks(self):
        self.assertTrue(self.preview())
        self.timeline.tc = "01:00:05:01"
        self.assertFalse(self.try_roundtrip())
        self.assertEqual(self.item.calls, [])
        self.timeline.tc = "01:00:05:00"
        self.item.enabled = False
        self.assertFalse(self.preview())

    def test_unsafe_frame_rate_and_overlapping_items_block(self):
        self.timeline.fps = "29.97"
        self.assertFalse(self.preview())
        self.assertEqual(self.item.calls, [])
        self.timeline.fps = "25"
        self.timeline.items.append(Item())
        self.assertFalse(self.preview())
        self.assertEqual(self.item.calls, [])

    def test_restoration_failure_is_explicit(self):
        initial = self.item.SetProperties

        def fail_restore(props):
            if props["AudioVolume"] == 9.0:
                self.item.calls.append(dict(props))
                return False
            return initial(props)

        self.item.SetProperties = fail_restore
        self.assertTrue(self.preview())
        self.assertFalse(self.try_roundtrip())
        self.assertEqual(self.item.volume, 9.5)
        self.assertIn("RESTORE_VERIFIED=False", self.output.getvalue())
        self.assertIn("CRITICAL", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
