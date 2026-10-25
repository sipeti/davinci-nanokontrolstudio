"""Offline checks for the bounded two-worker supervisor."""
from pathlib import Path
import sys
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
