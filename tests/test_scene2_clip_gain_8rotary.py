"""Eight physical Scene 2 rotary -> one clip per audio track, write-gated."""
import contextlib
import io
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from test_audio_roundtrip_probe import Item, Project, Resolve, Timeline
from scene2_soft_takeover import gain_for_cc
import scene2_clip_gain_8rotary as driver


class Timeline8(Timeline):
    def __init__(self):
        self.track_items = {}
        for track in range(1, 9):
            item = Item()
            item.uid = "clip-A%d" % track
            item.volume = 12.0 if track == 4 else -10.0
            self.track_items[track] = item
        super().__init__(self.track_items[4])

    def GetTrackCount(self, kind):
        return 8 if kind == "audio" else 0

    def GetItemListInTrack(self, kind, track):
        return [self.track_items[track]] if kind == "audio" else []


class EightRotaryTest(unittest.TestCase):
    def setUp(self):
        self.timeline = Timeline8()
        self.project = Project(self.timeline)
        self.app = Resolve(self.project)
        self.clock = 100
        self.output = io.StringIO()

    def controller(self, write=False, max_writes=8,
                   expected_project="Audio QA backup", consent=driver.CONSENT,
                   automation_confirmed=True):
        return driver.Controller(
            self.app, write=write, expected_project=expected_project,
            confirmation=consent, automation_confirmed=automation_confirmed,
            max_writes=max_writes, now=lambda: self.clock
        )

    def feed(self, controller, ch, cc, value):
        with contextlib.redirect_stdout(self.output):
            return controller.handle(ch, cc, value)

    def pickup_a4(self, c):
        self.assertEqual(self.feed(c, 1, 16, 90), "PICKUP_PENDING")
        self.assertEqual(self.feed(c, 1, 16, 98), "ENGAGED")

    def test_default_read_only_is_safe_even_with_valid_pickup(self):
        c = self.controller(write=False)
        self.pickup_a4(c)
        self.assertEqual(self.feed(c, 1, 16, 97), "SIMULATED")
        self.assertEqual(self.timeline.track_items[4].calls, [])
        self.assertIn("SIMULATED_GAIN=11.811", self.output.getvalue())

    def test_real_writes_require_explicit_test_copy_and_no_automation(self):
        for name, phrase, no_auto in [
            ("Production", driver.CONSENT, True),
            ("Audio QA backup", "not confirmed", True),
            ("Audio QA backup", driver.CONSENT, False),
            (None, driver.CONSENT, True),
        ]:
            with self.assertRaises(ValueError):
                self.controller(write=True, expected_project=name,
                                consent=phrase, automation_confirmed=no_auto)

    def test_a4_hardware_pickup_then_two_verified_writes_to_same_clip(self):
        c = self.controller(write=True, max_writes=2)
        item = self.timeline.track_items[4]
        self.pickup_a4(c)
        self.assertEqual(self.feed(c, 1, 16, 97), "WRITTEN")
        self.assertAlmostEqual(item.volume, gain_for_cc(97))
        self.assertEqual(self.feed(c, 1, 16, 96), "HALTED")
        self.assertEqual(len(item.calls), 2)
        self.assertAlmostEqual(item.calls[1]["AudioVolume"], gain_for_cc(96))
        self.assertEqual(c.writes, 2)
        self.assertTrue(c.halted)

    def test_eight_independent_strips_and_no_fader_actions(self):
        c = self.controller(write=True)
        self.assertEqual(self.feed(c, 1, 16, 90), "PICKUP_PENDING")
        self.assertEqual(self.feed(c, 1, 17, 1), "PICKUP_PENDING")
        self.assertEqual(self.feed(c, 1, 16, 98), "ENGAGED")
        self.assertEqual(self.feed(c, 1, 17, 48), "ENGAGED")
        self.assertEqual(self.feed(c, 1, 17, 47), "WRITTEN")
        self.assertEqual(len(self.timeline.track_items[5].calls), 1)
        self.assertEqual(len(self.timeline.track_items[4].calls), 0)
        self.assertEqual(self.feed(c, 1, 16, 97), "WRITTEN")
        self.assertEqual(len(self.timeline.track_items[4].calls), 1)
        self.assertEqual(c.writes, 2)
        self.assertEqual(self.feed(c, 1, 2, 127), "IGNORED")
        self.assertEqual(c.writes, 2)

    def test_missing_a8_does_not_write_anything(self):
        c = self.controller(write=True)
        self.timeline.track_items[8].GetProperties = lambda: None
        self.assertEqual(self.feed(c, 1, 20, 40), "DISABLED")
        self.assertEqual(self.timeline.track_items[8].calls, [])
        self.assertEqual(self.feed(c, 1, 16, 90), "PICKUP_PENDING")

    def test_scene_change_requires_new_pickup_and_no_stale_writes(self):
        c = self.controller(write=True)
        self.pickup_a4(c)
        self.assertEqual(self.feed(c, 0, 82, 1), "RESET")
        item = self.timeline.track_items[4]
        self.assertEqual(self.feed(c, 1, 16, 97), "PICKUP_PENDING")
        self.assertEqual(item.calls, [])
        self.assertEqual(self.feed(c, 1, 16, 98), "ENGAGED")
        self.assertEqual(item.calls, [])

    def test_idle_gap_rearms_without_writing(self):
        c = self.controller(write=True)
        self.pickup_a4(c)
        self.clock += 2.1
        self.assertEqual(self.feed(c, 1, 16, 97), "PICKUP_PENDING")
        self.assertEqual(self.timeline.track_items[4].calls, [])

    def test_external_edit_rearms_without_overwriting(self):
        c = self.controller(write=True)
        self.pickup_a4(c)
        self.timeline.track_items[4].volume = 5.0
        self.assertEqual(self.feed(c, 1, 16, 97), "PICKUP_PENDING")
        self.assertEqual(self.timeline.track_items[4].calls, [])

    def test_project_timeline_or_playhead_move_halts_write_mode(self):
        for owner, field, value in (
            (self.project, "uid", "different-project"),
            (self.timeline, "uid", "different-timeline"),
            (self.timeline, "tc", "01:00:05:01"),
        ):
            c = self.controller(write=True)
            self.assertEqual(self.feed(c, 1, 16, 90), "PICKUP_PENDING")
            old = getattr(owner, field)
            setattr(owner, field, value)
            self.assertEqual(self.feed(c, 1, 16, 98), "HALTED")
            self.assertEqual(self.timeline.track_items[4].calls, [])
            setattr(owner, field, old)

    def test_wrong_project_name_halts_even_before_pickup(self):
        c = self.controller(write=True, expected_project="Wrong QA backup")
        self.assertEqual(self.feed(c, 1, 16, 90), "HALTED")
        self.assertEqual(self.timeline.track_items[4].calls, [])

    def test_setter_failure_rolls_back_and_halts(self):
        c = self.controller(write=True)
        item = self.timeline.track_items[4]
        old = item.SetProperties

        def write_and_reject(props):
            result = old(props)
            return False if props["AudioVolume"] != 12.0 else result

        item.SetProperties = write_and_reject
        self.pickup_a4(c)
        self.assertEqual(self.feed(c, 1, 16, 97), "HALTED")
        self.assertEqual(item.volume, 12.0)
        self.assertEqual(len(item.calls), 2)
        self.assertIn("ROLLBACK_VERIFIED=True", self.output.getvalue())

    def test_intentional_success_does_not_restore_itself(self):
        c = self.controller(write=True)
        item = self.timeline.track_items[4]
        old = item.SetProperties

        def no_restore(props):
            if props["AudioVolume"] == 12.0:
                return False
            return old(props)

        item.SetProperties = no_restore
        self.pickup_a4(c)
        self.assertEqual(self.feed(c, 1, 16, 97), "WRITTEN")
        # A successful intentional edit should remain until the operator
        # changes it or discards the disposable test project.
        self.assertEqual(len(item.calls), 1)
        self.assertEqual(item.volume, gain_for_cc(97))

    def test_failed_rollback_is_critical_and_halts_session(self):
        c = self.controller(write=True)
        item = self.timeline.track_items[4]
        old = item.SetProperties

        def partial_failure(props):
            if props["AudioVolume"] == 12.0:
                return False  # refuse attempted rollback
            old(props)         # change gain but report failure
            return False

        item.SetProperties = partial_failure
        self.pickup_a4(c)
        self.assertEqual(self.feed(c, 1, 16, 97), "HALTED")
        self.assertAlmostEqual(item.volume, gain_for_cc(97))
        self.assertEqual(c.writes, 0)
        self.assertTrue(c.halted)
        self.assertIn("ROLLBACK_VERIFIED=False", self.output.getvalue())
        self.assertIn("CRITICAL", self.output.getvalue())

    def test_each_cc_maps_to_matching_audio_track(self):
        c = self.controller(write=False)
        for track in range(1, 9):
            cc = track + 12
            self.assertEqual(self.feed(c, 1, cc, 0), "PICKUP_PENDING")
            self.assertEqual(c.engine.state(track), "PICKUP_PENDING")
            self.assertEqual(self.timeline.track_items[track].calls, [])



if __name__ == "__main__":
    unittest.main()
