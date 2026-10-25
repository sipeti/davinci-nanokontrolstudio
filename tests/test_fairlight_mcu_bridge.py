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

    def test_fader1_one_shot_rejects_other_faders_and_buttons(self):
        sent=[]
        clock=[200.0]
        b=mcu.Bridge(
            lambda kind,**kw:sent.append((kind,kw)),
            lambda cc,value:None,
            write=True, clock=lambda:clock[0], fader1_one_shot=True)
        b.host(host("pitchwheel",channel=0,
                    pitch=mcu.physical_to_mcu(60)-8192))
        self.assertEqual(b.physical_event(1,3,61), "ONE_SHOT_FADER1_ONLY")
        self.assertEqual(b.physical_event(1,21,127), "ONE_SHOT_FADER1_ONLY")
        self.assertEqual(b.physical_event(1,29,127), "ONE_SHOT_FADER1_ONLY")
        self.assertEqual(b.physical_event(1,2,60),"FADER_PICKUP_PENDING")
        self.assertEqual(b.physical_event(1,2,61),"FADER_PICKUP_PASS")
        self.assertEqual(b.physical_event(1,2,62),"MCU_FADER_TOUCH_SENT")
        self.assertEqual(sent, [
            ("note_on", {"channel":0,"note":104,"velocity":127}),
            ("pitchwheel",{"channel":0,
                           "pitch":mcu.physical_to_mcu(62)-8192}),
        ])
        self.assertTrue(b.touch_active)
        self.assertFalse(b.release_touch(), "touch must remain held for 500ms")
        clock[0]+=0.49
        self.assertFalse(b.release_touch(), "not yet 500ms")
        self.assertEqual(b.physical_event(1,2,63), "ONE_SHOT_ALREADY_SENT")
        self.assertEqual(b.physical_event(1,21,127),"ONE_SHOT_FADER1_ONLY")
        b.host(host("pitchwheel",channel=0,
                    pitch=mcu.physical_to_mcu(62)-8192))
        self.assertEqual(b.ack_received,1)
        self.assertEqual(b.ack_mismatch,0)
        self.assertEqual(b.host_after_command,1)
        clock[0]+=0.02
        self.assertTrue(b.release_touch(), "release only after 500ms")
        self.assertFalse(b.release_touch(), "release must not be duplicated")
        self.assertEqual(sent[2], ("note_on",{"channel":0,"note":104,"velocity":0}))
        self.assertEqual(len(sent), 3)
        self.assertEqual(b.sent, 1, "one fader adjustment despite 3 MIDI packets")

    def test_fader1_one_shot_needs_recent_real_host_position(self):
        sent=[]
        clock=[200.0]
        b=mcu.Bridge(
            lambda kind,**kw:sent.append((kind,kw)),
            lambda cc,value:None,
            write=True,clock=lambda:clock[0],fader1_one_shot=True)
        self.assertEqual(b.physical_event(1,2,60),
                         "FADER_HOST_FEEDBACK_STALE_REARM")
        b.host(host("pitchwheel",channel=0,
                    pitch=mcu.physical_to_mcu(60)-8192))
        clock[0]+=10.1
        self.assertEqual(b.physical_event(1,2,60),
                         "FADER_HOST_FEEDBACK_STALE_REARM")
        self.assertEqual(sent,[])
        b.host(host("pitchwheel",channel=0,
                    pitch=mcu.physical_to_mcu(60)-8192))
        self.assertEqual(b.physical_event(1,2,60),"FADER_PICKUP_PENDING")
        self.assertEqual(b.physical_event(1,2,61),"FADER_PICKUP_PASS")
        self.assertEqual(b.physical_event(1,2,66),"ONE_SHOT_STEP_REARM")
        self.assertEqual(sent,[])

    def test_fader1_one_shot_ack_mismatch_is_never_success(self):
        sent=[]
        b=mcu.Bridge(lambda kind,**kw:sent.append((kind,kw)),
                     lambda cc,value:None, write=True,
                     fader1_one_shot=True)
        b.host(host("pitchwheel",channel=0,
                    pitch=mcu.physical_to_mcu(60)-8192))
        b.physical_event(1,2,60)
        b.physical_event(1,2,61)
        b.physical_event(1,2,62)
        b.host(host("pitchwheel",channel=0,
                    pitch=mcu.physical_to_mcu(110)-8192))
        self.assertEqual(b.ack_mismatch,1)
        self.assertEqual(b.ack_received,0)
        self.assertFalse(b.engaged[0])
        self.assertIsNotNone(b.pending[0],
                             "one-shot must observe subsequent host updates")
        self.assertEqual(b.physical_event(1,2,65),"ONE_SHOT_ALREADY_SENT")
        self.assertEqual(len(sent),2)
        # A later matching feedback can still validate the command, while
        # the hard cap prevents any extra physical fader send.
        b.host(host("pitchwheel",channel=0,
                    pitch=mcu.physical_to_mcu(62)-8192))
        self.assertEqual(b.ack_received,1)
        self.assertEqual(b.ack_mismatch,1)
        self.assertEqual(b.sent,1)
        self.assertTrue(b.release_touch(force=True))
        self.assertEqual(sent[2], ("note_on", {"channel":0,"note":104,
                                               "velocity":0}))

    def test_touch_releases_on_focus_or_scene_rearm_without_resending(self):
        sent=[]
        b=mcu.Bridge(lambda kind,**kw:sent.append((kind,kw)),
                     lambda cc,value:None,write=True,fader1_one_shot=True)
        b.host(host("pitchwheel",channel=0,
                    pitch=mcu.physical_to_mcu(60)-8192))
        b.physical_event(1,2,60)
        b.physical_event(1,2,61)
        b.physical_event(1,2,62)
        self.assertTrue(b.touch_active)
        b.rearm()
        self.assertFalse(b.touch_active)
        self.assertEqual(len(sent),3)
        self.assertEqual(sent[2],("note_on",
                                  {"channel":0,"note":104,"velocity":0}))
        self.assertEqual(b.physical_event(1,2,63),"ONE_SHOT_ALREADY_SENT")
        self.assertEqual(b.sent,1)

    def test_touch_release_is_sent_even_if_pitchbend_send_fails(self):
        sent=[]
        def fail_pitch(kind,**kw):
            sent.append((kind,kw))
            if kind == "pitchwheel":
                raise IOError("simulated port failure")
        b=mcu.Bridge(fail_pitch,lambda cc,v:None,write=True,
                     fader1_one_shot=True)
        b.host(host("pitchwheel",channel=0,
                    pitch=mcu.physical_to_mcu(60)-8192))
        b.physical_event(1,2,60)
        b.physical_event(1,2,61)
        with self.assertRaisesRegex(IOError, "simulated port failure"):
            b.physical_event(1,2,62)
        self.assertEqual(sent, [
            ("note_on", {"channel":0,"note":104,"velocity":127}),
            ("pitchwheel", {"channel":0,
                            "pitch":mcu.physical_to_mcu(62)-8192}),
            ("note_on", {"channel":0,"note":104,"velocity":0}),
        ])
        self.assertEqual(b.sent,0)

    def test_unmodified_read_only_fader_preview_sends_no_touch_packets(self):
        sent=[]
        b=mcu.Bridge(lambda kind,**kw:sent.append((kind,kw)),
                     lambda cc,v:None,write=False)
        b.host(host("pitchwheel",channel=0,
                    pitch=mcu.physical_to_mcu(60)-8192))
        b.physical_event(1,2,60)
        b.physical_event(1,2,61)
        self.assertEqual(b.physical_event(1,2,62),"MCU_FADER_PREVIEW")
        self.assertEqual(sent,[])

    def test_mute1_one_shot_requires_fresh_real_host_state(self):
        calls=[]
        t=[200.0]
        b=mcu.Bridge(lambda kind, **kw:calls.append((kind,kw)),
                     lambda cc,value:None,
                     write=True,clock=lambda:t[0],
                     one_shot_button="mute1")
        self.assertEqual(b.physical_event(1,21,127),
                         "BUTTON_HOST_STATE_STALE")
        self.assertEqual(calls, [])
        b.host(host("note_on",channel=0,note=16,velocity=0))
        t[0]+=10.1
        self.assertEqual(b.physical_event(1,21,127),
                         "BUTTON_HOST_STATE_STALE")
        self.assertEqual(calls, [])

    def test_mute1_one_shot_exact_one_press_release_and_led_change(self):
        calls=[]
        leds=[]
        t=[200.0]
        b=mcu.Bridge(lambda kind, **kw:calls.append((kind,kw)),
                     lambda cc,value:leds.append((cc,value)),
                     write=True,clock=lambda:t[0],
                     one_shot_button="mute1")
        b.host(host("note_on",channel=0,note=16,velocity=0))
        self.assertEqual(b.physical_event(1,2,64),"ONE_SHOT_BUTTON_ONLY")
        self.assertEqual(b.physical_event(1,29,127),"ONE_SHOT_BUTTON_ONLY")
        self.assertEqual(b.physical_event(1,21,0),"ONE_SHOT_WAIT_PRESS")
        self.assertEqual(b.physical_event(1,21,127),
                         "MCU_BUTTON_ONE_SHOT_SENT")
        self.assertEqual(calls,[
            ("note_on",{"channel":0,"note":16,"velocity":127})])
        self.assertEqual(b.sent,1)
        self.assertTrue(b.one_button_pressed)
        self.assertFalse(b.release_one_button())
        self.assertEqual(b.physical_event(1,21,0),"ONE_SHOT_ALREADY_SENT")
        self.assertEqual(b.physical_event(1,21,127),"ONE_SHOT_ALREADY_SENT")
        t[0]+=0.07
        self.assertFalse(b.release_one_button())
        t[0]+=0.02
        self.assertTrue(b.release_one_button())
        self.assertFalse(b.release_one_button())
        self.assertEqual(calls,[
            ("note_on",{"channel":0,"note":16,"velocity":127}),
            ("note_off",{"channel":0,"note":16,"velocity":0})])
        b.host(host("note_on",channel=0,note=16,velocity=127))
        self.assertEqual(leds[-1],(21,127))
        self.assertTrue(b.one_button_observed)
        self.assertEqual(b.one_button_initial,False)
        self.assertEqual(b.one_button_expected,True)
        self.assertEqual(b.sent,1)

    def test_solo1_one_shot_only_emits_note8_and_observes_state(self):
        calls=[]
        b=mcu.Bridge(lambda kind, **kw:calls.append((kind,kw)),
                     lambda cc,value:None,
                     write=True,one_shot_button="solo1")
        b.host(host("note_on",channel=0,note=8,velocity=127))
        self.assertEqual(b.physical_event(1,21,127),"ONE_SHOT_BUTTON_ONLY")
        self.assertEqual(b.physical_event(1,29,127),
                         "MCU_BUTTON_ONE_SHOT_SENT")
        self.assertEqual(b.one_button_initial,True)
        self.assertEqual(b.one_button_expected,False)
        self.assertEqual(b.physical_event(1,29,0),"ONE_SHOT_ALREADY_SENT")
        self.assertTrue(b.release_one_button(force=True))
        self.assertEqual(calls,[
            ("note_on",{"channel":0,"note":8,"velocity":127}),
            ("note_off",{"channel":0,"note":8,"velocity":0})])
        b.host(host("note_on",channel=0,note=8,velocity=0))
        self.assertTrue(b.one_button_observed)

    def test_mute1_one_shot_releases_on_focus_scene_rearm(self):
        calls=[]
        b=mcu.Bridge(lambda kind, **kw:calls.append((kind,kw)),
                     lambda cc,value:None,write=True,
                     one_shot_button="mute1")
        b.host(host("note_on",channel=0,note=16,velocity=0))
        self.assertEqual(b.physical_event(1,21,127),
                         "MCU_BUTTON_ONE_SHOT_SENT")
        self.assertEqual(b.physical_event(0,2,64),"SCENE_REARM")
        self.assertEqual(calls[-1],("note_off",
                                   {"channel":0,"note":16,"velocity":0}))
        self.assertFalse(b.one_button_pressed)
        self.assertEqual(b.sent,1)
        self.assertEqual(b.physical_event(1,21,127),"ONE_SHOT_ALREADY_SENT")

    def test_mute1_one_shot_releases_after_send_error(self):
        calls=[]
        def fail_press(kind,**kw):
            calls.append((kind,kw))
            if kind == "note_on" and kw.get("velocity") == 127:
                raise IOError("injected MIDI write fault")
        b=mcu.Bridge(fail_press,lambda cc,v:None,
                     write=True,one_shot_button="mute1")
        b.host(host("note_on",channel=0,note=16,velocity=0))
        with self.assertRaisesRegex(IOError,"injected MIDI write fault"):
            b.physical_event(1,21,127)
        self.assertFalse(b.one_button_pressed)
        self.assertEqual(calls,[
            ("note_on",{"channel":0,"note":16,"velocity":127}),
            ("note_off",{"channel":0,"note":16,"velocity":0})])

    def test_host_diagnostics_classify_only_valid_mcu_fader_and_notes(self):
        self.assertEqual(
            mcu.classify_host_event(host("pitchwheel", channel=0,
                                         pitch=-7904)),
            ("FADER", 0, -7904))
        self.assertEqual(
            mcu.classify_host_event(host("note_on", channel=0,
                                         note=16, velocity=127)),
            ("MIXER_NOTE", 16, 127))
        self.assertEqual(
            mcu.classify_host_event(host("note_off", channel=0,
                                         note=8, velocity=44)),
            ("MIXER_NOTE", 8, 0))
        self.assertEqual(
            mcu.classify_host_event(host("sysex", data=(126, 0, 6, 1))),
            ("SYSEX", 0, 0))
        for message in (
            host("control_change", channel=0, control=12, value=14),
            host("control_change", channel=0, control=44, value=5),
            host("pitchwheel", channel=8, pitch=0),
            host("pitchwheel", channel=0, pitch=9000),
            host("note_on", channel=0, note=0, velocity=0),
            host("note_on", channel=1, note=16, velocity=127),
            host("note_on", channel=0, note=16, velocity=200),
        ):
            self.assertIsNone(mcu.classify_host_event(message))
        self.assertEqual(self.sent, [])
        self.assertEqual(self.leds, [])
    
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
