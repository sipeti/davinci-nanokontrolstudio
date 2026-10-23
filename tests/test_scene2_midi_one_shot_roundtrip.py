"""Offline tests: physical MIDI can authorize exactly one bounded gain test."""
import contextlib
import io
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from test_audio_roundtrip_probe import Item, Timeline, Project, Resolve
import scene2_midi_one_shot_roundtrip as driver


class OneShotTest(unittest.TestCase):
    def setUp(self):
        self.item = Item()
        self.timeline = Timeline(self.item)
        self.project = Project(self.timeline)
        self.app = Resolve(self.project)
        self.saved, _ = driver._snapshot(self.app)
        self.output = io.StringIO()

    def write(self, desired=9.158, expected_project="Audio QA backup",
              consent=driver.CONSENT, expected_key=None):
        with contextlib.redirect_stdout(self.output):
            return driver.one_shot_roundtrip(
                self.app,
                expected_key if expected_key is not None else self.saved["key"],
                desired,
                expected_project=expected_project,
                consent=consent,
                pause=lambda _: None,
            )

    def test_success_writes_once_and_restores_original(self):
        self.assertTrue(self.write())
        self.assertEqual(self.item.calls,
                         [{"AudioVolume": 9.158}, {"AudioVolume": 9.0}])
        self.assertEqual(self.item.volume, 9.0)
        self.assertIn("MIDI_TEST_WRITE_READBACK=PASS", self.output.getvalue())
        self.assertIn("RESTORE_VERIFIED=True", self.output.getvalue())
        self.assertIn("SCENE2_MIDI_ROUNDTRIP=PASS", self.output.getvalue())

    def test_skipped_cc_intent_is_clamped_to_half_db(self):
        # Real Scene 2 rotary 4 generated a valid +0.695 dB intent at +12 dB.
        self.item.volume = 12.0
        self.saved, _ = driver._snapshot(self.app)
        self.assertTrue(self.write(desired=12.695))
        self.assertEqual(self.item.calls, [
            {"AudioVolume": 12.5}, {"AudioVolume": 12.0}])
        self.assertEqual(self.item.volume, 12.0)
        self.assertIn("bounded_test=12.500 dB", self.output.getvalue())
        self.assertIn("RESTORE_VERIFIED=True", self.output.getvalue())

    def test_clamps_negative_and_preserves_direction(self):
        self.assertTrue(self.write(desired=8.305))
        self.assertEqual(self.item.calls, [
            {"AudioVolume": 8.5}, {"AudioVolume": 9.0}])
        self.assertEqual(self.item.volume, 9.0)

    def test_midi_intent_exceeding_pickup_limit_blocks_without_writes(self):
        self.assertFalse(self.write(desired=10.201))
        self.assertEqual(self.item.calls, [])
        self.assertIn("WRITES=0", self.output.getvalue())

    def test_missing_or_wrong_consent_blocks_all_writes(self):
        for supplied in (None, "YES", "NOT A BACKUP"):
            self.assertFalse(self.write(consent=supplied))
            self.assertEqual(self.item.calls, [])

    def test_exact_project_and_obvious_test_copy_required(self):
        self.assertFalse(self.write(expected_project="wrong QA backup"))
        self.assertEqual(self.item.calls, [])
        self.project.GetName = lambda: "Real Production"
        self.saved, _ = driver._snapshot(self.app)
        self.assertFalse(self.write(expected_project="Real Production"))
        self.assertEqual(self.item.calls, [])

    def test_external_gain_change_blocks(self):
        self.item.volume = 10.0
        self.assertFalse(self.write())
        self.assertEqual(self.item.calls, [])

    def test_clip_timeline_project_and_playhead_changes_block(self):
        for owner, attr, value in (
            (self.item, "uid", "other-clip"),
            (self.timeline, "uid", "other-timeline"),
            (self.project, "uid", "other-project"),
            (self.timeline, "tc", "01:00:05:01"),
        ):
            original = getattr(owner, attr)
            setattr(owner, attr, value)
            self.assertFalse(self.write())
            self.assertEqual(self.item.calls, [])
            setattr(owner, attr, original)

    def test_bad_step_or_disabled_audio_blocks(self):
        for desired in (9.01, 10.21, 120, -110, float("nan")):
            self.assertFalse(self.write(desired=desired))
            self.assertEqual(self.item.calls, [])
        self.item.enabled = False
        self.assertFalse(self.write())
        self.assertEqual(self.item.calls, [])

    def test_context_change_during_settling_blocks(self):
        def move_playhead(_):
            self.timeline.tc = "01:00:05:02"
        with contextlib.redirect_stdout(self.output):
            result = driver.one_shot_roundtrip(
                self.app, self.saved["key"], 9.158,
                expected_project="Audio QA backup", consent=driver.CONSENT,
                pause=move_playhead,
            )
        self.assertFalse(result)
        self.assertEqual(self.item.calls, [])

    def test_setter_claims_failure_but_restoration_still_runs(self):
        original = self.item.SetProperties

        def applied_but_false(props):
            result = original(props)
            if props["AudioVolume"] != 9.0:
                return False
            return result
        self.item.SetProperties = applied_but_false
        self.assertFalse(self.write())
        self.assertEqual(self.item.volume, 9.0)
        self.assertIn("MIDI_TEST_WRITE_READBACK=FAIL", self.output.getvalue())
        self.assertIn("RESTORE_VERIFIED=True", self.output.getvalue())

    def test_failed_restoration_is_critical(self):
        original = self.item.SetProperties

        def fail_restore(props):
            if props["AudioVolume"] == 9.0:
                self.item.calls.append(dict(props))
                return False
            return original(props)
        self.item.SetProperties = fail_restore
        self.assertFalse(self.write())
        self.assertEqual(self.item.volume, 9.158)
        self.assertIn("RESTORE_VERIFIED=False", self.output.getvalue())
        self.assertIn("CRITICAL", self.output.getvalue())

    def test_one_shot_is_opt_in_and_uses_only_a4(self):
        self.assertEqual(driver.TRACK, 4)
        self.assertEqual(driver.CC, 16)
        self.assertFalse(driver._consent_ok(None, None))
        self.assertFalse(driver._consent_ok("Production", driver.CONSENT))


if __name__ == "__main__":
    unittest.main()
