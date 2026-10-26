"""Offline acceptance for the persistent Scene 2 clip-gain worker."""
import contextlib
import io
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from test_scene2_clip_gain_8rotary import Timeline8
from test_audio_roundtrip_probe import Item
from test_audio_roundtrip_probe import Project, Resolve
import scene2_continuous_clip_gain as worker
import scene2_clip_gain_8rotary as driver
from scene2_clip_gain_8rotary import CONSENT


class FakeClock:
    def __init__(self, path):
        self.t = 100.0
        self.w = 1800000000.0
        self.path = path
        self.commands = []
        self.scheduled = []

    def add(self, elapsed, kind, ch=0, cc=0, value=0):
        self.scheduled.append((100.0 + elapsed, kind, ch, cc, value))
        self.scheduled.sort()

    def monotonic(self):
        return self.t

    def wall(self):
        return self.w

    def sleep(self, delay):
        self.t += delay
        self.w += delay
        while self.scheduled and self.scheduled[0][0] <= self.t:
            _, kind, ch, cc, value = self.scheduled.pop(0)
            line = "%d,%s,%d,%d,%d\n" % (
                int(self.w * 1000), kind, ch, cc, value)
            with self.path.open("a") as f:
                f.write(line)


class Timeline16(Timeline8):
    def __init__(self):
        super().__init__()
        for track in range(9, 17):
            item = Item()
            item.uid = "clip-A%d" % track
            item.volume = -10.0
            self.track_items[track] = item

    def GetTrackCount(self, kind):
        return 16 if kind == "audio" else 0


class ContinuousTest(unittest.TestCase):
    def setUp(self):
        self.timeline = Timeline8()
        self.project = Project(self.timeline)
        self.app = Resolve(self.project)
        self.now = 100.0
        self.output = io.StringIO()

    def controller(self, write=False, max_writes=256):
        return worker.ContinuousController(
            self.app, write=write, max_writes=max_writes,
            expected_project="Audio QA backup",
            confirmation=CONSENT,
            automation_confirmed=True,
            now=lambda: self.now,
        )

    def feed(self, controller, ch, cc, value):
        with contextlib.redirect_stdout(self.output):
            return controller.handle(ch, cc, value)

    def test_bank2_rotary_retargets_A9_through_A16_only_after_ack(self):
        timeline = Timeline16()
        app = Resolve(Project(timeline))
        c = worker.ContinuousController(
            app, write=True, max_writes=0, low_latency=True,
            follow_active_project=True, follow_mcu_bank=True,
            now=lambda: self.now)
        self.assertFalse(c.bank_ready)
        self.assertEqual(c.handle(1, 16, 100), "BANK_WAIT_HOST")
        self.assertFalse(any(item.calls for item in timeline.track_items.values()))
        self.assertTrue(c.update_bank((0, 1)))
        self.assertEqual(c.handle(1, 16, 100), "PICKUP_PENDING")
        c.bank_request_target = 1
        self.assertTrue(c.update_bank((0, 0)))
        self.assertFalse(c.bank_ready)
        self.assertEqual(c.handle(1, 16, 108), "BANK_WAIT_HOST")
        self.assertFalse(c.update_bank((0, 1)), "old bank ACK ignored")
        self.assertTrue(c.update_bank((1, 1)))
        self.assertEqual(c.track_offset, 8)
        self.assertEqual(c.handle(1, 16, 100), "PICKUP_PENDING")
        self.assertEqual(c.handle(1, 16, 108), "PICKUP_PENDING")
        before, identity, session = driver.snapshot(app, 12)
        c.session = session
        with mock.patch.object(worker, "FEEDBACK", pathlib.Path("/no-bank-file")):
            self.assertEqual(c._write(12, before, identity, -9.0), "BLOCKED")
        self.assertEqual(timeline.track_items[12].calls, [])
        self.assertEqual(timeline.track_items[4].calls, [])
        self.assertEqual(c.bank_index, 1)

    def test_bank_feedback_parser_rejects_stale_wrong_and_partial_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "feedback.csv"
            now_ms = 1800000000000
            p.write_text("%d,H,0,1\n%d,B,1,0\n%d,B,1,1\n" %
                         (now_ms, now_ms, now_ms))
            self.assertEqual(worker.read_bank_feedback(p, now_ms), (1, 1))
            self.assertIsNone(worker.read_bank_feedback(p, now_ms + 2000))
            p.write_text("%d,B,2,1\n" % now_ms)
            self.assertIsNone(worker.read_bank_feedback(p, now_ms))

    def test_readonly_default_no_setters(self):
        c = self.controller()
        self.assertEqual(self.feed(c, 1, 16, 100), "PICKUP_PENDING")
        self.assertEqual(self.feed(c, 1, 16, 108), "ENGAGED")
        self.assertEqual(self.feed(c, 1, 16, 107), "SIMULATED")
        self.assertFalse(self.timeline.track_items[4].calls)

    def test_low_latency_writes_without_timer_and_still_checks_result(self):
        def forbidden_delay(_seconds):
            raise AssertionError("low-latency should not sleep 120ms")
        c = worker.ContinuousController(
            self.app, write=True, max_writes=0,
            expected_project="Audio QA backup",
            confirmation=CONSENT, automation_confirmed=True,
            now=lambda: self.now, stability_wait=forbidden_delay,
            low_latency=True)
        self.assertEqual(self.feed(c, 1, 16, 100), "PICKUP_PENDING")
        self.assertEqual(self.feed(c, 1, 16, 108), "ENGAGED")
        self.assertEqual(self.feed(c, 1, 16, 107), "WRITTEN")
        self.assertEqual(c.writes, 1)
        self.assertAlmostEqual(self.timeline.track_items[4].volume, 11.727)

    def test_low_latency_blocks_project_playhead_change_at_setter_gate(self):
        c = worker.ContinuousController(
            self.app, write=True, max_writes=0,
            expected_project="Audio QA backup",
            confirmation=CONSENT, automation_confirmed=True,
            now=lambda: self.now, low_latency=True)
        self.feed(c, 1, 16, 100)
        self.feed(c, 1, 16, 108)
        original = driver.snapshot
        def move_just_before_setter(app, track):
            self.timeline.tc = "01:00:05:01"
            return original(app, track)
        with mock.patch.object(driver, "snapshot", side_effect=move_just_before_setter):
            result = self.feed(c, 1, 16, 107)
        self.assertEqual(result, "HALTED")
        self.assertEqual(c.writes, 0)
        self.assertEqual(self.timeline.track_items[4].calls, [])

    def test_auto_project_follows_change_without_reusing_pickup(self):
        c = worker.ContinuousController(
            self.app, write=True, max_writes=0, low_latency=True,
            follow_active_project=True, now=lambda: self.now)
        self.assertEqual(self.feed(c, 1, 16, 100), "PICKUP_PENDING")
        self.assertEqual(self.feed(c, 1, 16, 108), "ENGAGED")
        self.assertEqual(self.feed(c, 1, 16, 107), "WRITTEN")
        old_writes = c.writes
        self.project.uid = "other-project-uid"
        self.project.GetName = lambda: "Another production project"
        self.timeline.track_items[4].volume = 0.0
        self.assertEqual(self.feed(c, 1, 16, 108), "PICKUP_PENDING")
        self.assertEqual(c.expected_project, "Another production project")
        self.assertEqual(c.writes, old_writes)
        self.assertEqual(self.feed(c, 1, 16, 127), "PICKUP_PENDING")
        self.assertEqual(self.feed(c, 1, 16, 64), "ENGAGED")
        self.assertEqual(self.feed(c, 1, 16, 65), "WRITTEN")
        self.assertEqual(c.writes, old_writes + 1)
        self.assertAlmostEqual(self.timeline.track_items[4].volume, 0.273)

    def test_auto_project_does_not_bypass_pre_setter_identity_check(self):
        c = worker.ContinuousController(
            self.app, write=True, max_writes=0, low_latency=True,
            follow_active_project=True, now=lambda: self.now)
        self.feed(c, 1, 16, 100)
        self.feed(c, 1, 16, 108)
        original = driver.snapshot
        def switch_before_setter(app, track):
            self.project.uid = "changed-at-setter"
            return original(app, track)
        with mock.patch.object(driver, "snapshot", side_effect=switch_before_setter):
            self.assertEqual(self.feed(c, 1, 16, 107), "HALTED")
        self.assertEqual(c.writes, 0)

    def test_unlimited_test_copy_writes_repeatedly(self):
        c = self.controller(write=True, max_writes=0)
        self.assertEqual(self.feed(c, 1, 16, 100), "PICKUP_PENDING")
        self.assertEqual(self.feed(c, 1, 16, 108), "ENGAGED")
        self.assertEqual(self.feed(c, 1, 16, 107), "WRITTEN")
        self.assertEqual(self.feed(c, 1, 16, 106), "WRITTEN")
        self.assertFalse(c.halted)
        self.assertEqual(c.writes, 2)
        with self.assertRaises(ValueError):
            self.controller(write=False, max_writes=0)

    def test_256_writes_allowed_only_by_explicit_continuous_constructor(self):
        c = self.controller(write=True, max_writes=256)
        self.assertEqual(c.max_writes, 256)
        self.assertFalse(c.halted)
        with self.assertRaises(ValueError):
            self.controller(write=True, max_writes=257)
        with self.assertRaises(ValueError):
            worker.ContinuousController(
                self.app, write=True, expected_project="Audio QA backup",
                automation_confirmed=False, confirmation=CONSENT)

    def test_verified_write_remains_applied_after_good_cc(self):
        c = self.controller(write=True)
        self.assertEqual(self.feed(c, 1, 16, 100), "PICKUP_PENDING")
        self.assertEqual(self.feed(c, 1, 16, 108), "ENGAGED")
        self.assertEqual(self.feed(c, 1, 16, 107), "WRITTEN")
        self.assertAlmostEqual(self.timeline.track_items[4].volume, 11.727)
        self.assertEqual(c.writes, 1)

    def test_scene_switch_and_return_requires_fresh_pickup(self):
        c = self.controller(write=True)
        self.feed(c, 1, 16, 100)
        self.feed(c, 1, 16, 108)
        self.assertEqual(self.feed(c, 0, 16, 45), "RESET")
        self.assertEqual(self.feed(c, 1, 16, 107), "PICKUP_PENDING")
        self.assertEqual(c.writes, 0)
        self.assertEqual(self.feed(c, 1, 16, 108), "ENGAGED")
        self.assertFalse(self.timeline.track_items[4].calls)

    def test_playhead_move_rearms_without_stale_write(self):
        c = self.controller(write=True)
        self.feed(c, 1, 16, 100)
        self.feed(c, 1, 16, 108)
        self.timeline.tc = "01:00:05:01"
        self.assertEqual(self.feed(c, 1, 16, 107), "PICKUP_PENDING")
        self.assertEqual(c.writes, 0)
        self.assertFalse(self.timeline.track_items[4].calls)

    def test_clip_switch_rearms_and_external_edit_rearms(self):
        c = self.controller(write=True)
        self.feed(c, 1, 16, 100)
        self.feed(c, 1, 16, 108)
        self.timeline.track_items[4].uid = "another-a4-clip"
        self.assertEqual(self.feed(c, 1, 16, 107), "PICKUP_PENDING")
        self.assertEqual(c.writes, 0)
        self.timeline.track_items[4].volume = 5.0
        self.assertEqual(self.feed(c, 1, 16, 106), "PICKUP_PENDING")
        self.assertFalse(self.timeline.track_items[4].calls)

    def test_idle_2_seconds_does_not_rearm_but_20_seconds_does(self):
        c = self.controller(write=True)
        self.feed(c, 1, 16, 100)
        self.now += 2.5
        self.assertEqual(self.feed(c, 1, 16, 108), "ENGAGED")
        self.now += 20.1
        self.assertEqual(self.feed(c, 1, 16, 107), "PICKUP_PENDING")
        self.assertFalse(self.timeline.track_items[4].calls)

    def test_wrong_project_fails_closed_on_new_target(self):
        c = self.controller(write=True)
        self.feed(c, 1, 16, 100)
        self.project.uid = "switched-to-other-project"
        self.project.GetName = lambda: "PRODUCTION"
        self.assertEqual(self.feed(c, 1, 16, 108), "HALTED")
        self.assertFalse(self.timeline.track_items[4].calls)

    def test_playhead_move_during_120ms_write_stability_gate_blocks_setter(self):
        def move_playhead(_seconds):
            self.timeline.tc = "01:00:05:01"
        c = worker.ContinuousController(
            self.app, write=True, max_writes=1,
            expected_project="Audio QA backup",
            confirmation=CONSENT, automation_confirmed=True,
            now=lambda: self.now, stability_wait=move_playhead)
        self.assertEqual(self.feed(c, 1, 16, 100), "PICKUP_PENDING")
        self.assertEqual(self.feed(c, 1, 16, 108), "ENGAGED")
        self.assertEqual(self.feed(c, 1, 16, 107), "HALTED")
        self.assertEqual(c.writes, 0)
        self.assertFalse(self.timeline.track_items[4].calls)
        self.assertIn("during stability window", self.output.getvalue())

    def test_clip_gain_external_edit_during_stability_gate_blocks_setter(self):
        def external_adjust(_seconds):
            self.timeline.track_items[4].volume = 9.0
        c = worker.ContinuousController(
            self.app, write=True, max_writes=1,
            expected_project="Audio QA backup",
            confirmation=CONSENT, automation_confirmed=True,
            now=lambda: self.now, stability_wait=external_adjust)
        self.feed(c, 1, 16, 100)
        self.feed(c, 1, 16, 108)
        self.assertEqual(self.feed(c, 1, 16, 107), "HALTED")
        self.assertEqual(c.writes, 0)
        self.assertFalse(self.timeline.track_items[4].calls)

    def test_heartbeat_and_event_timestamp_validation(self):
        now = 1800000000000
        valid = worker.parse_bridge_row("%d,C,1,16,97" % (now - 300), now)
        self.assertEqual(valid, ("C", 1, 16, 97))
        self.assertEqual(worker.parse_bridge_row("%d,H,0,0,1" % now, now),
                         ("H", 1))
        self.assertEqual(worker.parse_bridge_row("%d,R,0,16,0" % now, now),
                         ("R", 0, 16, 0))
        for row in (
            "%d,C,1,16,97" % (now - 2000),
            "%d,C,1,16,97" % (now + 1),
            "%d,C,1,16,128" % now,
            "%d,C,0,999,97" % now,
            "%d,H,0,0,2" % now,
            "%d,H,1,0,1" % now,
            "not,valid,midi",
            "%d,C,1,16,nan" % now,
        ):
            self.assertIsNone(worker.parse_bridge_row(row, now), row)

    def stream(self, *, write=False, max_writes=256, scene_reset=False,
               focus_loss=False):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "events.csv"
            path.write_text("# ts_ms,kind,channel,cc,value\n")
            clock = FakeClock(path)
            clock.add(.04, "H", 0, 0, 1)
            clock.add(.08, "C", 1, 16, 100)
            clock.add(.28, "C", 1, 16, 108)
            if scene_reset:
                clock.add(.40, "R", 0, 16, 15)
            if focus_loss:
                clock.add(.40, "H", 0, 0, 0)
            clock.add(.56, "C", 1, 16, 107)
            clock.add(.60, "H", 0, 0, 1)
            c = worker.ContinuousController(
                self.app, write=write, max_writes=max_writes,
                expected_project="Audio QA backup",
                confirmation=CONSENT, automation_confirmed=True,
                now=clock.monotonic)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = worker.monitor(c, event_path=path, seconds=.9,
                    clock=clock.monotonic, wall=clock.wall, sleep=clock.sleep)
            return code, c, output.getvalue()

    def test_integrated_tail_readonly_pickup_and_simulated_intent(self):
        code, c, logs = self.stream()
        self.assertEqual(code, 0, logs)
        self.assertIn("A4 PICKUP=PASS", logs)
        self.assertIn("A4 SIMULATED_GAIN=", logs)
        self.assertEqual(c.writes, 0)
        self.assertFalse(self.timeline.track_items[4].calls)

    def test_integrated_tail_guarded_testcopy_setter_ack(self):
        code, c, logs = self.stream(write=True, max_writes=1)
        self.assertEqual(code, 0, logs)
        self.assertIn("A4 AUDIO_WRITE_READBACK=PASS", logs)
        self.assertEqual(c.writes, 1)
        self.assertAlmostEqual(self.timeline.track_items[4].volume, 11.727)

    def test_switching_scene_prevents_pending_write_intent(self):
        code, c, logs = self.stream(write=True, max_writes=1,
                                   scene_reset=True)
        self.assertEqual(code, 0, logs)
        self.assertEqual(c.writes, 0, logs)
        self.assertIn("REARM; other Korg scene selected", logs)
        self.assertFalse(self.timeline.track_items[4].calls)

    def test_focus_loss_prevents_pending_write_intent(self):
        code, c, logs = self.stream(write=True, max_writes=1,
                                   focus_loss=True)
        self.assertEqual(code, 0, logs)
        self.assertEqual(c.writes, 0, logs)
        self.assertIn("REARM; Resolve not frontmost", logs)
        self.assertFalse(self.timeline.track_items[4].calls)

    def test_missing_heartbeat_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "events.csv"
            path.write_text("# no live bridge\n")
            clock = FakeClock(path)
            c = self.controller(write=True)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = worker.monitor(c, event_path=path, seconds=6,
                    clock=clock.monotonic, wall=clock.wall, sleep=clock.sleep)
            self.assertEqual(code, 1)
            self.assertIn("no bridge heartbeat", out.getvalue())
            self.assertEqual(c.writes, 0)


if __name__ == "__main__":
    unittest.main()
