"""Anonymous project epoch is fresh, session-bound and invalidates MCU pickup."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from scene2_project_context import (
    ContextPublisher, ContextGate, context_identity, parse_context, read_context,
)

RUN = "0123456789abcdef"
OTHER_RUN = "fedcba9876543210"


class Mixer:
    def __init__(self):
        self.invalidations = 0
    def rearm(self, *, invalidate_host=False):
        self.invalidations += int(invalidate_host)


class Timeline:
    def GetUniqueId(self): return "timeline-1"


class Project:
    def GetCurrentTimeline(self): return Timeline()
    def GetUniqueId(self): return "project-1"


class App:
    def __init__(self): self.current = Project()
    def GetProjectManager(self): return self
    def GetCurrentProject(self): return self.current


class ContextTests(unittest.TestCase):
    def test_context_identity(self):
        app = App()
        self.assertEqual(context_identity(app), ("project-1", "timeline-1"))
        app.current = None
        self.assertIsNone(context_identity(app))

    def test_parse_rejects_invalid_stale_other_run(self):
        row = "1700000000000,%s,2,1\n" % RUN
        self.assertEqual(parse_context(row, RUN, 1700000000000), (2, True))
        self.assertIsNone(parse_context(row, OTHER_RUN, 1700000000000))
        self.assertIsNone(parse_context(row, RUN, 1700000002000))
        self.assertIsNone(parse_context(row, RUN, 1699999999999))
        self.assertIsNone(parse_context("junk", RUN, 1700000000000))

    def test_epoch_change_rearms_mcu(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "context.csv"
            current = [1700000000.0]
            pub = ContextPublisher(RUN, path=path, wall=lambda: current[0])
            gate = ContextGate(RUN, path=path)
            mix = Mixer()
            self.assertFalse(gate.check(mix, 1700000000000))
            self.assertEqual(mix.invalidations, 0)
            self.assertEqual(pub.publish(("p1", "t1")), (1, True))
            self.assertTrue(gate.check(mix, 1700000000000))
            self.assertEqual(mix.invalidations, 0)
            current[0] += .5
            self.assertEqual(pub.publish(("p1", "t1")), (1, True))
            self.assertTrue(gate.check(mix, 1700000000500))
            current[0] += .5
            self.assertEqual(pub.publish(("p2", "t1")), (2, True))
            self.assertTrue(gate.check(mix, 1700000001000))
            self.assertEqual(mix.invalidations, 1)
            current[0] += .5
            self.assertEqual(pub.publish(None), (3, False))
            self.assertFalse(gate.check(mix, 1700000001500))
            self.assertEqual(mix.invalidations, 2)
            current[0] += .5
            self.assertEqual(pub.publish(("p2", "t2")), (4, True))
            self.assertTrue(gate.check(mix, 1700000002000))
            self.assertEqual(mix.invalidations, 3)
            self.assertNotIn("p2", path.read_text())  # no IDs on disk
            self.assertNotIn("t2", path.read_text())

    def test_stale_worker_blocks_and_cannot_reuse_faders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "context.csv"
            pub = ContextPublisher(RUN, path=path, wall=lambda: 1700000000.0)
            gate = ContextGate(RUN, path=path)
            mix = Mixer()
            pub.publish(("p1", "t1"))
            self.assertTrue(gate.check(mix, 1700000000000))
            self.assertFalse(gate.check(mix, 1700000004000))
            self.assertEqual(mix.invalidations, 1)
            self.assertFalse(gate.check(mix, 1700000004000))
            self.assertEqual(mix.invalidations, 1)
            self.assertIsNone(read_context(path, OTHER_RUN, 1700000000000))


if __name__ == "__main__":
    unittest.main()
