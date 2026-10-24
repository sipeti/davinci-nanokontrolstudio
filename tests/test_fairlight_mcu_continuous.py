"""Offline, hardware-free tests for opt-in Scene2 Fairlight live MCU mode."""
import pathlib
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import fairlight_mcu_bridge as mcu
import fairlight_mcu_continuous as live


def msg(kind, **kwargs):
    return SimpleNamespace(type=kind, **kwargs)


class LiveMixerTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.calls = []
        self.leds = []
        self.b = live.LiveMixer(
            lambda kind, **kw:self.calls.append((kind, kw)),
            lambda cc, val:self.leds.append((cc, val)),
            write=True, clock=lambda:self.now)

    def fader_host(self, index, value):
        self.b.host(msg("pitchwheel", channel=index,
                        pitch=mcu.physical_to_mcu(value) - 8192))

    def test_first_fader_requires_real_host_pickup_and_timed_touch_release(self):
        self.assertEqual(self.b.physical_event(1,2,60), "FADER_WAIT_HOST")
        self.assertEqual(self.calls, [])
        self.fader_host(0,60)
        self.assertEqual(self.b.physical_event(1,2,60), "FADER_PICKUP_PENDING")
        self.assertEqual(self.b.physical_event(1,2,61), "FADER_PICKUP_PASS")
        self.assertEqual(self.b.physical_event(1,2,62), "FADER_LIVE_SENT")
        self.assertEqual(self.calls, [
            ("note_on",{"channel":0,"note":104,"velocity":127}),
            ("pitchwheel",{"channel":0,
                           "pitch":mcu.physical_to_mcu(62) - 8192}),
        ])
        self.assertEqual(self.b.sent_faders,1)
        self.assertEqual(self.b.physical_event(1,2,63),"FADER_RATE_COALESCED")
        self.now += .04
        self.assertEqual(self.b.physical_event(1,2,64),"FADER_LIVE_SENT")
        self.assertEqual(self.calls[-1][0],"pitchwheel")
        self.assertEqual(len(self.calls),3)
        self.now += .49
        self.b.tick()
        self.assertEqual(len(self.calls),3)
        self.now += .02
        self.b.tick()
        self.assertEqual(self.calls[-1],
                         ("note_on",{"channel":0,"note":104,"velocity":0}))
        self.assertEqual(self.b.sent_faders,2)
        self.assertEqual(self.b.touches,{})

    def test_all_seven_audio_faders_use_mcu_pitch_and_touch_channels(self):
        for strip in range(7):
            self.fader_host(strip,60)
            cc=strip+2
            self.b.physical_event(1,cc,60)
            self.assertEqual(self.b.physical_event(1,cc,61),"FADER_PICKUP_PASS")
            self.assertEqual(self.b.physical_event(1,cc,62),"FADER_LIVE_SENT")
        self.assertEqual(
            [x[1]["channel"] for x in self.calls if x[0]=="pitchwheel"],
            list(range(7)))
        self.assertEqual(
            [x[1]["note"] for x in self.calls
             if x[0]=="note_on" and x[1]["velocity"]==127],
            list(range(104,111)))
        self.assertEqual(self.b.sent_faders,7)
        self.now += .51
        self.b.tick()
        self.assertEqual(self.b.touches,{})

    def test_strip8_bus_guard_blocks_fader_mute_and_solo(self):
        self.assertEqual(self.b.physical_event(1,9,64),"BUS1_STRIP8_LOCKED")
        self.assertEqual(self.b.physical_event(1,28,127),"BUS1_STRIP8_LOCKED")
        self.assertEqual(self.b.physical_event(1,37,127),"BUS1_STRIP8_LOCKED")
        self.assertEqual(self.calls,[])
        self.assertEqual(self.b.sent,0)
        # Explicit opt-in permits the CURRENT eighth MCU bank strip only,
        # without suggesting that it is a permanently pinned master bus.
        self.b.allow_strip8=True
        self.fader_host(7,60)
        self.b.physical_event(1,9,60)
        self.assertEqual(self.b.physical_event(1,9,61),"FADER_PICKUP_PASS")
        self.assertEqual(self.b.physical_event(1,9,62),"FADER_LIVE_SENT")
        self.assertEqual(self.calls[0],
                         ("note_on",{"channel":0,"note":111,"velocity":127}))
        self.assertEqual(self.calls[1][1]["channel"],7)
        self.assertEqual(self.b.physical_event(1,28,127),"BUTTON_LIVE_SENT")
        self.assertEqual(self.calls[-1],
                         ("note_on",{"channel":0,"note":23,"velocity":127}))

    def test_mute_and_solo_host_led_authoritative_and_button_release_once(self):
        # Physical CC is NEVER itself a trusted LED state.
        self.assertEqual(self.b.physical_event(1,21,127),"BUTTON_LIVE_SENT")
        self.assertEqual(self.leds,[])
        self.assertEqual(self.b.physical_event(1,21,127),"BUTTON_DUPLICATE")
        self.assertEqual(self.b.physical_event(1,29,127),"BUTTON_LIVE_SENT")
        self.assertEqual(self.calls,[
            ("note_on",{"channel":0,"note":16,"velocity":127}),
            ("note_on",{"channel":0,"note":8,"velocity":127}),
        ])
        self.now += .09
        self.b.tick()
        self.assertEqual(self.calls[-2:],[
            ("note_off",{"channel":0,"note":16,"velocity":0}),
            ("note_off",{"channel":0,"note":8,"velocity":0}),
        ])
        self.b.host(msg("note_on",channel=0,note=16,velocity=127))
        self.b.host(msg("note_on",channel=0,note=8,velocity=127))
        self.assertEqual(self.leds[-2:],[(21,127),(29,127)])
        self.assertEqual(self.b.physical_event(1,21,0),"BUTTON_RELEASED")
        self.assertEqual(self.b.physical_event(1,29,0),"BUTTON_RELEASED")
        self.assertEqual(self.b.physical_event(1,21,127),"BUTTON_LIVE_SENT")
        self.assertEqual(self.b.sent_buttons,3)

    def test_scene_change_immediately_releases_touch_and_button(self):
        self.fader_host(0,60)
        self.b.physical_event(1,2,60)
        self.b.physical_event(1,2,61)
        self.b.physical_event(1,2,62)
        self.b.physical_event(1,21,127)
        self.assertEqual(len(self.b.touches),1)
        self.assertEqual(len(self.b.keys),1)
        self.assertEqual(self.b.physical_event(0,2,60),"SCENE_REARM")
        self.assertEqual(self.b.touches,{})
        self.assertEqual(self.b.keys,{})
        self.assertEqual(self.calls[-2:],[
            ("note_on",{"channel":0,"note":104,"velocity":0}),
            ("note_off",{"channel":0,"note":16,"velocity":0}),
        ])
        self.assertEqual(self.b.host_state.host_faders,[None]*8)
        self.assertEqual(self.b.physical_event(1,2,64),"FADER_WAIT_HOST")

    def test_external_mixer_move_disarms_previous_pickup(self):
        self.fader_host(0,60)
        self.b.physical_event(1,2,60)
        self.b.physical_event(1,2,61)
        self.b.physical_event(1,2,62)
        self.now+=.51
        self.b.tick()
        self.fader_host(0,90)
        self.assertFalse(self.b.engaged[0])
        self.assertEqual(self.b.physical_event(1,2,63),"FADER_PICKUP_PENDING")

    def test_fast_unsafe_cc_jump_is_rearmed_without_extra_midi(self):
        self.fader_host(0,60)
        self.b.physical_event(1,2,60)
        self.b.physical_event(1,2,61)
        self.b.physical_event(1,2,62)
        self.assertEqual(self.b.physical_event(1,2,110),"FADER_JUMP_REARM")
        self.assertFalse(self.b.engaged[0])
        self.assertEqual(self.b.sent_faders,1)
        self.assertEqual(self.b.touches,{})

    def test_read_only_never_transmits_but_host_led_is_observed(self):
        sent=[]
        led=[]
        b=live.LiveMixer(lambda kind,**kw:sent.append((kind,kw)),
                         lambda cc,val:led.append((cc,val)),
                         write=False, clock=lambda:self.now)
        b.host(msg("note_on",channel=0,note=16,velocity=127))
        self.assertEqual(led,[(21,127)])
        b.host(msg("pitchwheel",channel=0,
                   pitch=mcu.physical_to_mcu(60)-8192))
        b.physical_event(1,2,60)
        b.physical_event(1,2,61)
        self.assertEqual(b.physical_event(1,2,62),"FADER_LIVE_PREVIEW")
        self.assertEqual(b.physical_event(1,21,127),"BUTTON_LIVE_PREVIEW")
        b.tick()
        b.release_all()
        self.assertEqual(sent,[])

    def test_releases_key_after_partial_send_failure(self):
        sent=[]
        def fail_on_press(kind,**kw):
            sent.append((kind,kw))
            if kind=="note_on" and kw.get("note")==16:
                raise OSError("injected write failure")
        b=live.LiveMixer(fail_on_press,lambda cc,v:None,
                         write=True, clock=lambda:self.now)
        with self.assertRaisesRegex(OSError,"injected write failure"):
            b.physical_event(1,21,127)
        self.assertEqual(sent,[
            ("note_on",{"channel":0,"note":16,"velocity":127}),
            ("note_off",{"channel":0,"note":16,"velocity":0}),
        ])
        self.assertEqual(b.keys,{})

    def test_exact_fairlight_identity_request_has_bounded_mcu_reply_payload(self):
        request=msg("sysex",data=(126,0,6,1))
        reply=live.mcu_identity_reply_for(request)
        self.assertEqual(reply,live.MCU_ID_REPLY)
        self.assertEqual(reply[:4],(126,0,6,2))
        self.assertEqual(reply[4:7],(0,0,102))
        self.assertEqual(reply[7:9],(20,0))
        self.assertEqual(len(reply),15)
        self.assertTrue(all(isinstance(x,int) and 0<=x<=127 for x in reply))
        self.assertEqual(live.MAX_IDENTITY_REPLIES,3)

    def test_foreign_non_identity_sysex_is_not_answered(self):
        for message in [
            msg("sysex",data=(126,127,6,1)),
            msg("sysex",data=(126,0,6,2)),
            msg("sysex",data=(0,0,102,20,0)),
            msg("sysex",data=()),
            msg("note_on",channel=0,note=0,velocity=0),
        ]:
            self.assertIsNone(live.mcu_identity_reply_for(message))
        self.assertEqual(self.calls,[])
        self.assertEqual(self.b.sent,0)

    def test_identity_reply_is_not_host_fader_authority_or_physical_write(self):
        identity=live.mcu_identity_reply_for(
            msg("sysex",data=(126,0,6,1)))
        self.assertIsNotNone(identity)
        self.b.host(msg("sysex",data=identity))
        self.assertEqual(self.b.host_state.host_faders,[None]*8)
        self.assertEqual(self.b.physical_event(1,2,60),"FADER_WAIT_HOST")
        self.assertEqual(self.b.sent,0)
        self.assertEqual(self.calls,[])

    def test_real_host_fader_after_identity_must_still_cross_pickup(self):
        self.b.host(msg("sysex",data=live.MCU_ID_REPLY))
        self.assertEqual(self.b.physical_event(1,2,63),"FADER_WAIT_HOST")
        self.fader_host(0,60)
        self.assertEqual(self.b.physical_event(1,2,60),"FADER_PICKUP_PENDING")
        self.assertEqual(self.b.physical_event(1,2,61),"FADER_PICKUP_PASS")
        self.assertEqual(self.b.physical_event(1,2,62),"FADER_LIVE_SENT")
        self.assertEqual(self.b.sent_faders,1)

    def test_production_has_no_implicit_unbounded_midi_authorization(self):
        self.assertEqual(live.MAX_SECONDS,180)
        self.assertLessEqual(live.MAX_MESSAGES,1500)
        self.assertFalse(self.b.allow_strip8)
        self.assertFalse(live.LiveMixer(lambda *a, **kw:None,
                                         lambda *a, **kw:None).write)


if __name__ == "__main__":
    unittest.main()
