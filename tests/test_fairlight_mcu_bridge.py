"""Hardware-free Mackie MCU translator regression and fail-closed checks."""
import pathlib
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import fairlight_mcu_bridge as mcu


def host(kind, **values):
    return SimpleNamespace(type=kind, **values)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self.leds = []
        self.t = 100.0
        self.bridge = mcu.Bridge(
            lambda cmd, **kw: self.sent.append((cmd, kw)),
            lambda cc, val: self.leds.append((cc, val)),
            write=True, clock=lambda: self.t,
        )

    def host_fader(self, track, cc_value):
        pos = mcu.physical_to_mcu(cc_value)
        self.bridge.host(host("pitchwheel", channel=track-1, pitch=pos-8192))

    def test_fader_requires_host_feedback_then_real_pickup_before_writes(self):
        self.assertEqual(self.bridge.physical_event(1,2,60),
                         "FADER_WAIT_FOR_FAIRLIGHT_POSITION")
        self.assertEqual(self.sent, [])
        self.host_fader(1,60)
        self.assertEqual(self.bridge.physical_event(1,2,60),"FADER_PICKUP_PENDING")
        self.assertEqual(self.bridge.physical_event(1,2,61),"FADER_PICKUP_PASS")
        self.assertEqual(self.sent, [])
        self.assertEqual(self.bridge.physical_event(1,2,62),"MCU_FADER_SENT")
        self.assertEqual(self.sent[0][0],"pitchwheel")
        self.assertEqual(self.sent[0][1],{
            "channel":0, "pitch":mcu.physical_to_mcu(62)-8192})
        self.assertEqual(self.bridge.physical_event(1,2,63),"FADER_WAIT_ACK")
        self.assertEqual(len(self.sent),1)
        self.host_fader(1,62)
        # The CC63 physical event was deliberately dropped while waiting
        # for host ACK. A *new* physical change is required after ACK.
        self.assertEqual(self.bridge.physical_event(1,2,64),"MCU_FADER_SENT")
        self.assertEqual(len(self.sent),2)

    def test_each_of_eight_tracks_uses_separate_mcu_pitch_channel(self):
        for strip in range(1,9):
            self.host_fader(strip,40)
            cc = strip+1
            self.bridge.physical_event(1,cc,40)
            self.assertEqual(self.bridge.physical_event(1,cc,41),
                             "FADER_PICKUP_PASS")
            self.assertEqual(self.bridge.physical_event(1,cc,42),"MCU_FADER_SENT")
            self.host_fader(strip,42)
        channels=[x[1]["channel"] for x in self.sent]
        self.assertEqual(channels,list(range(8)))

    def test_host_external_fader_move_disarms_physical_pickup(self):
        self.host_fader(1,60)
        self.bridge.physical_event(1,2,60)
        self.bridge.physical_event(1,2,61)
        self.host_fader(1,92)
        self.assertFalse(self.bridge.engaged[0])
        self.assertEqual(self.bridge.physical_event(1,2,63),"FADER_PICKUP_PENDING")
        self.assertEqual(self.sent, [])

    def test_large_fader_jump_rearms_without_sending(self):
        self.host_fader(1,60)
        self.bridge.physical_event(1,2,60)
        self.bridge.physical_event(1,2,61)
        self.assertEqual(self.bridge.physical_event(1,2,90),"FADER_JUMP_REARM")
        self.assertEqual(self.sent, [])

    def test_ack_timeout_blocks_and_requires_new_pickup(self):
        self.host_fader(1,60)
        self.bridge.physical_event(1,2,60)
        self.bridge.physical_event(1,2,61)
        self.bridge.physical_event(1,2,62)
        self.t += 0.8
        self.assertEqual(self.bridge.physical_event(1,2,63),
                         "FADER_ACK_TIMEOUT_REARM")
        self.assertEqual(len(self.sent),1)
        self.assertFalse(self.bridge.engaged[0])

    def test_host_feedback_mismatch_rearms(self):
        self.host_fader(1,60)
        self.bridge.physical_event(1,2,60)
        self.bridge.physical_event(1,2,61)
        self.bridge.physical_event(1,2,62)
        self.host_fader(1,90)
        self.assertEqual(self.bridge.pending[0],None)
        self.assertFalse(self.bridge.engaged[0])
        self.assertEqual(len(self.sent),1)

    def test_mute_solo_are_note_messages_and_only_host_lights_led(self):
        self.assertEqual(self.bridge.physical_event(1,21,127),
                         "BUTTON_WAIT_FOR_FAIRLIGHT_LED")
        self.assertEqual(self.sent,[])
        self.assertEqual(self.leds,[])
        self.bridge.host(host("note_on",channel=0,note=16,velocity=127))
        self.assertEqual(self.leds,[(21,127)])
        self.assertEqual(self.bridge.physical_event(1,21,127),"MCU_BUTTON_SENT")
        self.assertEqual(self.sent[-1],("note_on",
                                       {"channel":0,"note":16,"velocity":127}))
        self.assertEqual(self.leds,[(21,127)])
        self.assertEqual(self.bridge.physical_event(1,21,127),"BUTTON_DUPLICATE")
        self.assertEqual(self.bridge.physical_event(1,21,0),"MCU_BUTTON_SENT")
        self.assertEqual(self.sent[-1],("note_off",
                                       {"channel":0,"note":16,"velocity":0}))
        self.assertEqual(self.leds,[(21,127)])
        self.bridge.host(host("note_off",channel=0,note=16,velocity=0))
        self.assertEqual(self.leds[-1],(21,0))

    def test_korg_solo_cc32_skipped_in_mapping_and_all_other_8_solos(self):
        self.assertEqual(mcu.SOLO_CC,(29,30,31,33,34,35,36,37))
        self.assertEqual(self.bridge.physical_event(1,32,127),"IGNORED")
        for strip,cc in enumerate(mcu.SOLO_CC):
            self.bridge.host(host("note_on",channel=0,note=8+strip,velocity=127))
            self.assertEqual(self.leds[-1],(cc,127))
            self.assertEqual(self.bridge.physical_event(1,cc,127),"MCU_BUTTON_SENT")
            self.assertEqual(self.sent[-1][1]["note"],8+strip)

    def test_cross_scene_invalidates_host_feedback_and_all_pickups(self):
        self.host_fader(1,60)
        self.bridge.host(host("note_on",channel=0,note=16,velocity=0))
        self.bridge.physical_event(1,2,60)
        self.bridge.physical_event(1,2,61)
        self.assertEqual(self.bridge.physical_event(0,2,61),"SCENE_REARM")
        self.assertEqual(self.bridge.physical_event(1,2,61),
                         "FADER_WAIT_FOR_FAIRLIGHT_POSITION")
        self.assertEqual(self.bridge.physical_event(1,21,127),
                         "BUTTON_WAIT_FOR_FAIRLIGHT_LED")
        self.assertEqual(self.sent,[])

    def test_readonly_never_sends_even_when_pickup_and_host_state_known(self):
        b = mcu.Bridge(lambda *args,**kw:self.sent.append((args,kw)),
                       lambda cc,v:self.leds.append((cc,v)),
                       write=False)
        b.host(host("pitchwheel",channel=0,pitch=mcu.physical_to_mcu(60)-8192))
        b.physical_event(1,2,60)
        b.physical_event(1,2,61)
        self.assertEqual(b.physical_event(1,2,62),"MCU_FADER_PREVIEW")
        b.host(host("note_on",channel=0,note=16,velocity=0))
        self.assertEqual(b.physical_event(1,21,127),"MCU_BUTTON_PREVIEW")
        self.assertEqual(self.sent,[])

    def test_invalid_host_feedback_never_becomes_authority(self):
        self.bridge.host(host("note_on",channel=9,note=16,velocity=127))
        self.bridge.host(host("note_on",channel=0,note=41,velocity=127))
        self.bridge.host(host("pitchwheel",channel=8,pitch=0))
        self.bridge.host(host("pitchwheel",channel=0,pitch=99999))
        self.assertEqual(self.bridge.known_buttons,{})
        self.assertEqual(self.bridge.host_faders,[None]*8)

    def test_event_parsing_never_replays_stale_or_foreign_data(self):
        now=1800000000000
        self.assertEqual(mcu.parse_event("%d,M,1,21,127"%(now-100),now),
                         ("M",1,21,127))
        self.assertEqual(mcu.parse_event("%d,H,0,0,1"%now,now),
                         ("H",0,0,1))
        for line in (
            "not-mcu-data",
            "%d,M,1,2,64"%(now-1001),
            "%d,M,1,2,64"%(now+1),
            "%d,M,1,2,129"%now,
            "%d,M,16,2,64"%now,
            "%d,H,0,0,127"%now,
            "%d,C,1,16,95"%now,
        ):
            self.assertIsNone(mcu.parse_event(line,now),line)

    def test_physical_cc_to_mcu_14bit_values(self):
        self.assertEqual(mcu.physical_to_mcu(0),0)
        self.assertEqual(mcu.physical_to_mcu(127),16383)
        self.assertGreater(mcu.physical_to_mcu(64),8192)
        for v in (0,127,64,96):
            self.assertEqual(mcu.physical_to_mcu(v),round(v*16383/127))


if __name__ == "__main__":
    unittest.main()
