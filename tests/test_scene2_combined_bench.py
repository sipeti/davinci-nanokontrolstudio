"""Offline checks for the bounded two-worker supervisor."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import scene2_combined_bench as bench


class CombinedTest(unittest.TestCase):
    def test_readonly_commands_do_not_enable_any_setter(self):
        a = bench.parser().parse_args(["--seconds", "60"])
        specs = bench.commands(a, Path("/test/scripts"))
        self.assertEqual([s[0] for s in specs], ["MCU", "CLIP"])
        self.assertNotIn("--enable-output", specs[0][1])
        self.assertNotIn("--write-test-copy", specs[1][1])
        self.assertEqual(specs[0][1][-2:], ["--seconds", "60"])

    def test_writer_consent_is_forwarded_only_when_explicit(self):
        a = bench.parser().parse_args([
            "--write-test-copy", "--expected-project", "hajoagyu_261022 testing",
            "--confirmed-backup", "--confirmed-no-automation",
            "--max-clip-writes", "6"])
        specs = bench.commands(a, Path("/test/scripts"))
        self.assertIn("--enable-output", specs[0][1])
        self.assertIn(bench.MCU_CONSENT, specs[0][1])
        self.assertIn("--confirmed-no-automation", specs[1][1])
        self.assertIn("hajoagyu_261022 testing", specs[1][1])
        self.assertEqual(specs[1][1][specs[1][1].index("--max-writes") + 1], "6")

    def test_continuous_command_has_both_workers_uncapped(self):
        a = bench.parser().parse_args([
            "--run-until-stopped", "--write-test-copy",
            "--expected-project", "hajoagyu_261022 testing",
            "--confirmed-backup", "--confirmed-no-automation"])
        a.seconds = 0
        a.max_clip_writes = 0
        specs = bench.commands(a, Path("/test/scripts"))
        self.assertIn("--continuous", specs[0][1])
        self.assertEqual(specs[0][1][specs[0][1].index("--seconds")+1], "0")
        self.assertIn("--unlimited-writes", specs[1][1])
        self.assertNotIn("--max-writes", specs[1][1])

    def test_low_latency_is_forwarded_only_to_clip_worker(self):
        a = bench.parser().parse_args(["--seconds", "60", "--low-latency"])
        specs = bench.commands(a, Path("/test/scripts"))
        self.assertIn("--low-latency", specs[1][1])
        self.assertNotIn("--low-latency", specs[0][1])
        self.assertNotIn("--enable-output", specs[0][1])

    def test_named_project_authorization_forwarding_requires_opt_in(self):
        a = bench.parser().parse_args([
            "--write-approved-project", "--allow-named-project",
            "--expected-project", "Real Production Project",
            "--confirmed-backup", "--confirmed-no-automation",
            "--run-until-stopped", "--low-latency"])
        a.seconds = 0
        a.max_clip_writes = 0
        specs = bench.commands(a, Path("/test/scripts"))
        self.assertIn("--allow-named-project", specs[1][1])
        self.assertIn(bench.NAMED_CONSENT, specs[1][1])
        self.assertIn("--write-approved-project", specs[1][1])
        self.assertNotIn("--allow-named-project", specs[0][1])
        with self.assertRaises(SystemExit):
            bench.main(["--allow-named-project", "--seconds", "60"])

    def test_auto_run_preserves_the_exact_v14_mcu_command(self):
        with tempfile.TemporaryDirectory() as temp:
            events = Path(temp) / "events.csv"
            events.write_text("fresh")
            with mock.patch.object(bench, "EVENTS", events), \
                 mock.patch.object(bench, "supervise", return_value=0) as run:
                result = bench.main([
                    "--auto-run", "--mcu-python", sys.executable,
                    "--resolve-python", sys.executable])
            self.assertEqual(result, 0)
            auto_specs = run.call_args.args[0]
            self.assertEqual([name for name, _, _ in auto_specs], ["MCU", "CLIP"])
            mcu, clip = auto_specs

            # The v1.5 auto-run must launch the identical working MCU
            # command as the already accepted v1.4 manual writing mode.
            manual = bench.parser().parse_args([
                "--run-until-stopped", "--write-test-copy",
                "--expected-project", "testing",
                "--confirmed-backup", "--confirmed-no-automation",
                "--max-clip-writes", "0",
                "--mcu-python", sys.executable,
                "--resolve-python", sys.executable])
            manual.seconds = 0
            manual_specs = bench.commands(
                manual, Path(__file__).resolve().parents[1] / "scripts")
            self.assertEqual(mcu, manual_specs[0])
            self.assertIsNone(mcu[2])
            self.assertNotIn("--auto-context-guard", mcu[1])
            self.assertNotIn("--init-mcu-session", mcu[1])
            self.assertIn("--enable-output", mcu[1])
            self.assertIn("--low-latency", clip[1])
            self.assertIn("--follow-active-project", clip[1])
            self.assertIn("--unlimited-writes", clip[1])
            self.assertNotIn("--expected-project", clip[1])

    def test_v15_only_reinterprets_factory_fader_cc_not_mcu_protocol(self):
        from fairlight_mcu_bridge import FADER_CCS, FADER_CC_TO_STRIP, SOLO_CC
        from fairlight_mcu_continuous import TOUCH_HOLD, BUTTON_HOLD
        self.assertEqual(FADER_CCS, (2, 3, 4, 5, 6, 8, 9, 12))
        self.assertEqual(tuple(FADER_CC_TO_STRIP.values()), tuple(range(8)))
        self.assertEqual(SOLO_CC, (29, 30, 31, 33, 34, 35, 36, 37))
        self.assertEqual(TOUCH_HOLD, .5)
        self.assertEqual(BUTTON_HOLD, .08)

    def test_auto_run_rejects_incompatible_manual_controls(self):
        with self.assertRaises(SystemExit) as error:
            bench.main(["--auto-run", "--expected-project", "wrong"])
        self.assertEqual(error.exception.code, 2)

    def test_missing_write_confirmation_is_rejected_before_start(self):
        with self.assertRaises(SystemExit) as exc:
            bench.main(["--write-test-copy", "--expected-project", "testing"])
        self.assertEqual(exc.exception.code, 2)

    def test_startup_requires_fresh_bridge_log(self):
        with mock.patch.object(bench, "EVENTS", Path("/does/not/exist.csv")):
            with self.assertRaises(SystemExit) as exc:
                bench.main(["--seconds", "15"])
        self.assertEqual(exc.exception.code, 2)

    def test_clip_write_cap_completion_does_not_kill_mcu_worker(self):
        class Dummy:
            def __init__(self, states):
                self.states = iter(states)
                self.code = None
                self.pid = 123
                self.poll_count = 0
            def poll(self):
                self.poll_count += 1
                self.code = next(self.states, self.code)
                return self.code
        mcu = Dummy([None, None, 0])
        clip = Dummy([0])
        with mock.patch.object(bench.subprocess, "Popen", side_effect=[mcu, clip]):
            with mock.patch.object(bench.time, "sleep"):
                self.assertEqual(bench.supervise([
                    ("MCU", ["cmd"], None), ("CLIP", ["cmd"], {})]), 0)
        self.assertGreaterEqual(mcu.poll_count, 3)


if __name__ == "__main__":
    unittest.main()
