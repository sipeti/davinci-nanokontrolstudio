import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
from scene2_soft_takeover import SoftTakeover, gain_for_cc

I = ('project', 'timeline', 4, 'clip', 100, 200)
G = gain_for_cc(91)


class TestPickup(unittest.TestCase):
    def setUp(self):
        self.e = SoftTakeover()

    def feed(self, v, identity=I, db=G, ok=True):
        return self.e.feed(1, 16, v, identity, db, ok)

    def engage(self):
        self.assertEqual(self.feed(30).state, 'PICKUP_PENDING')
        self.assertEqual(self.feed(91).state, 'ENGAGED')

    def test_first_touch_has_no_write(self):
        self.assertEqual(self.feed(91).state, 'PICKUP_PENDING')
        self.assertEqual(self.feed(91).state, 'PICKUP_PENDING')
        self.assertEqual(self.feed(90).state, 'ENGAGED')

    def test_skipped_midi_values_cross_target_and_propose_last_gain(self):
        self.assertEqual(self.feed(97, db=9.0).state, 'PICKUP_PENDING')
        result = self.feed(102, db=9.0)
        self.assertEqual(result.state, 'WRITE_INTENT')
        self.assertEqual(result.proposed_db, gain_for_cc(102))

    def test_fast_full_sweep_crosses_and_proposes_last_gain(self):
        self.assertEqual(self.feed(10, db=9.0).state, 'PICKUP_PENDING')
        result = self.feed(120, db=9.0)
        self.assertEqual(result.state, 'WRITE_INTENT')
        self.assertEqual(result.proposed_db, gain_for_cc(120))
        self.assertEqual(self.e.state(4), 'AWAIT_ACK')
        self.assertFalse(self.e.confirm(4, I, G, True))

    def test_intent_needs_verified_ack(self):
        self.engage()
        intent = self.feed(92)
        self.assertEqual(intent.state, 'WRITE_INTENT')
        self.assertEqual(intent.proposed_db, gain_for_cc(92))
        self.assertTrue(self.e.confirm(4, I, intent.proposed_db, True))
        self.assertEqual(self.e.state(4), 'ENGAGED')

    def test_scene_switch_and_gain_edit_invalidate(self):
        self.engage()
        self.assertEqual(self.feed(92, db=G + 2).state, 'PICKUP_PENDING')
        self.engage()
        self.e.feed(0, 16, 90)
        self.assertEqual(self.e.state(4), 'DISABLED')

    def test_clip_change_rearms(self):
        self.engage()
        other = ('project', 'timeline', 4, 'other', 100, 200)
        self.assertEqual(self.feed(92, identity=other).state, 'PICKUP_PENDING')

    def test_missing_authority_or_bad_readback(self):
        self.assertEqual(self.feed(91, ok=False).state, 'DISABLED')
        self.engage()
        self.feed(92)
        self.assertFalse(self.e.confirm(4, I, G, True))
        self.assertEqual(self.e.state(4), 'DISABLED')

    def test_unacknowledged_intent_disables(self):
        self.engage()
        self.assertEqual(self.feed(92).state, 'WRITE_INTENT')
        self.assertEqual(self.feed(93).state, 'DISABLED')

    def test_fast_move_after_pickup_uses_absolute_cc(self):
        self.engage()
        result = self.feed(120)
        self.assertEqual(result.state, 'WRITE_INTENT')
        self.assertEqual(result.proposed_db, gain_for_cc(120))
        self.assertTrue(self.e.confirm(4, I, result.proposed_db, True))
        self.assertEqual(self.e.state(4), 'ENGAGED')

    def test_gain_map(self):
        values = [gain_for_cc(i) for i in range(128)]
        self.assertEqual((values[0], values[64], values[-1]), (-100, 0, 30))
        self.assertEqual(values, sorted(values))
        self.assertLess(values[63], 0)
        self.assertGreater(values[65], 0)
        self.assertAlmostEqual(values[63], -0.5)
        self.assertAlmostEqual(values[65], 0.273)

    def test_full_existing_clip_range_can_be_picked_up(self):
        self.assertEqual(self.feed(126, db=30.0).state, 'PICKUP_PENDING')
        self.assertEqual(self.feed(127, db=30.0).state, 'ENGAGED')
        self.e.reset()
        self.assertEqual(self.feed(1, db=-100.0).state, 'PICKUP_PENDING')
        self.assertEqual(self.feed(0, db=-100.0).state, 'ENGAGED')


if __name__ == '__main__':
    unittest.main()
