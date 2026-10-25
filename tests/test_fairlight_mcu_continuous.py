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
        # Same clock tick, no artificial throttling: both physical
        # positions must be sent immediately (not coalesced/dropped).
        self.assertEqual(self.b.physical_event(1,2,63),"FADER_LIVE_SENT")
        self.assertEqual(self.b.physical_event(1,2,64),"FADER_LIVE_SENT")
        self.assertEqual(self.calls[-1],
                         ("pitchwheel",{"channel":0,
                           "pitch":mcu.physical_to_mcu(64)-8192}))
        self.assertEqual(len(self.calls),4)
        self.now += .49
        self.b.tick()
        self.assertEqual(len(self.calls),4)
        self.now += .02
        self.b.tick()
        self.assertEqual(self.calls[-1],
                         ("note_on",{"channel":0,"note":104,"velocity":0}))
        self.assertEqual(self.b.sent_faders,3)
        self.assertEqual(self.b.touches,{})

    def test_all_changed_physical_cc_are_immediately_sent_even_same_clock(self):
        self.fader_host(0,60)
        self.assertEqual(self.b.physical_event(1,2,60),"FADER_PICKUP_PENDING")
        self.assertEqual(self.b.physical_event(1,2,61),"FADER_PICKUP_PASS")
        for value in (62,63,64,70,78,90,100,117,127):
            self.assertEqual(self.b.physical_event(1,2,value),
                             "FADER_LIVE_SENT")
        sent = [data["pitch"] for kind,data in self.calls
                if kind=="pitchwheel"]
        self.assertEqual(sent,
                         [mcu.physical_to_mcu(v)-8192
                          for v in (62,63,64,70,78,90,100,117,127)])
        self.assertEqual(self.b.sent_faders,9)
        self.assertTrue(self.b.engaged[0])
        self.assertEqual(self.calls[0],
                         ("note_on",{"channel":0,"note":104,"velocity":127}))
        self.assertEqual(len([x for x in self.calls
                              if x[0]=="note_on" and x[1]["velocity"]==127]),1)

    def test_fast_top_and_bottom_ends_are_sent_without_tick_flush(self):
        # Actual user problem: the fader could stop halfway during fast
        # physical movement. Once host pickup succeeds, fast direction
        # changes and BOTH physical endpoints are legitimate requests.
        self.fader_host(0,60)
        self.fader_host(1,60)
        for cc in (2,3):
            self.assertEqual(self.b.physical_event(1,cc,60),
                             "FADER_PICKUP_PENDING")
            self.assertEqual(self.b.physical_event(1,cc,61),
                             "FADER_PICKUP_PASS")
        for cc,values in ((2,(70,100,127)),(3,(50,10,0))):
            for value in values:
                self.assertEqual(self.b.physical_event(1,cc,value),
                                 "FADER_LIVE_SENT")
        sent = {channel: [] for channel in (0,1)}
        for kind,data in self.calls:
            if kind=="pitchwheel":
                sent[data["channel"]].append(data["pitch"])
        self.assertEqual(sent[0][-1],mcu.physical_to_mcu(127)-8192)
        self.assertEqual(sent[1][-1],mcu.physical_to_mcu(0)-8192)
        self.assertEqual(len(sent[0]),3)
        self.assertEqual(len(sent[1]),3)
        self.assertEqual(self.b.sent_faders,6)
        self.assertEqual(set(self.b.touches),{0,1})
        self.now += .51
        self.b.tick()
        self.assertEqual(self.b.touches,{})

    def test_duplicate_cc_does_not_send_and_tick_never_invents_positions(self):
        self.fader_host(0,60)
        self.b.physical_event(1,2,60)
        self.b.physical_event(1,2,61)
        self.assertEqual(self.b.physical_event(1,2,62),"FADER_LIVE_SENT")
        self.assertEqual(self.b.physical_event(1,2,62),"FADER_DUPLICATE")
        self.assertEqual(self.b.sent_faders,1)
        self.now += .1
        self.b.tick()
        self.assertEqual(self.b.sent_faders,1)
        self.assertEqual(len([1 for kind,data in self.calls
                              if kind=="pitchwheel"]),1)

    def test_scene_or_focus_rearm_releases_and_prevents_unauthorized_write(self):
        self.fader_host(0,60)
        self.b.physical_event(1,2,60)
        self.b.physical_event(1,2,61)
        self.b.physical_event(1,2,62)
        self.assertEqual(self.b.sent_faders,1)
        self.b.rearm()
        self.assertEqual(self.b.touches,{})
        self.assertEqual(self.b.engaged,[False]*8)
        self.assertEqual(self.b.host_state.host_faders[0],
                         mcu.physical_to_mcu(60))
        self.assertEqual(self.b.physical_event(1,2,127),
                         "FADER_PICKUP_PENDING")
        self.now += .5
        self.b.tick()
        self.assertEqual(self.b.sent_faders,1)
        self.assertEqual(self.calls[-1],
                         ("note_on",{"channel":0,"note":104,"velocity":0}))

    def test_touch_hold_resets_after_each_real_fader_move(self):
        self.fader_host(0,60)
        self.b.physical_event(1,2,60)
        self.b.physical_event(1,2,61)
        self.b.physical_event(1,2,62)
        self.now += .4
        self.b.physical_event(1,2,100)
        self.now += .2
        self.b.tick()
        self.assertIn(0,self.b.touches)
        self.now += .31
        self.b.tick()
        self.assertNotIn(0,self.b.touches)
        self.assertEqual(self.b.sent_faders,2)

    def test_fader_partial_press_failure_still_releases_touch(self):
        calls=[]
        def fail(kind,**kw):
            calls.append((kind,kw))
            if kind=="note_on" and kw.get("note")==104 and kw.get("velocity")==127:
                raise OSError("touch-start failure")
        b=live.LiveMixer(fail,lambda cc,val:None,write=True,
                         clock=lambda:self.now)
        b.host(msg("pitchwheel",channel=0,pitch=mcu.physical_to_mcu(60)-8192))
        b.physical_event(1,2,60)
        b.physical_event(1,2,61)
        with self.assertRaisesRegex(OSError,"touch-start failure"):
            b.physical_event(1,2,62)
        self.assertEqual(calls[-1],
                         ("note_on",{"channel":0,"note":104,"velocity":0}))
        self.assertEqual(b.touches,{})
        self.assertEqual(b.sent_faders,0)

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
        self.assertEqual(
            self.b.host_state.host_faders[0],mcu.physical_to_mcu(60),
            "A Korg Scene change does not erase actual Fairlight host state")
        self.assertEqual(self.b.physical_event(1,2,64),"FADER_PICKUP_PENDING")

    def test_project_open_snapshot_survives_focus_loss_h0_and_korg_scene_r(self):
        # Regression for actual Resolve logs: all eight host pitchwheels
        # arrived at project open, but later H=0/R called Bridge.rearm()
        # and erased them. Never destroy genuine MIDI feedback on a
        # physical-source rearm.
        for strip in range(8):
            self.fader_host(strip,60)
        self.b.host(msg("note_on",channel=0,note=16,velocity=127))
        self.b.rearm()  # Hammerspoon focus lost / Scene2 R
        self.assertEqual(
            self.b.host_state.host_faders,
            [mcu.physical_to_mcu(60)]*8)
        self.assertEqual(self.b.host_state.known_buttons[21],True)
        self.assertEqual(self.b.engaged,[False]*8)
        self.assertEqual(self.b.physical_event(1,2,60),"FADER_PICKUP_PENDING")
        self.assertEqual(self.b.physical_event(1,2,61),"FADER_PICKUP_PASS")
        self.assertEqual(self.b.physical_event(1,2,62),"FADER_LIVE_SENT")
        self.assertEqual(self.b.sent_faders,1)

    def test_fresh_project_open_positions_override_prior_live_snapshot(self):
        self.fader_host(0,60)
        self.b.rearm()  # physical focus reset, keep same-port host state
        self.fader_host(0,90)  # new Resolve project sends current position
        self.assertEqual(self.b.host_state.host_faders[0],
                         mcu.physical_to_mcu(90))
        self.assertEqual(self.b.physical_event(1,2,60),"FADER_PICKUP_PENDING")
        self.assertEqual(self.b.physical_event(1,2,61),"FADER_PICKUP_PENDING")
        self.assertEqual(self.b.physical_event(1,2,90),"FADER_PICKUP_PASS")
        self.assertEqual(self.b.physical_event(1,2,91),"FADER_LIVE_SENT")
        self.assertEqual(self.b.sent_faders,1)

    def test_project_open_snapshot_does_not_expire_after_ten_seconds(self):
        # MCU host initial state is not sent periodically. A recorded
        # position is trustworthy while this *same connected session* runs.
        self.fader_host(0,60)
        self.now += 60.0
        self.assertEqual(self.b.physical_event(1,2,60),"FADER_PICKUP_PENDING")
        self.assertEqual(self.b.physical_event(1,2,61),"FADER_PICKUP_PASS")
        self.assertEqual(self.b.physical_event(1,2,62),"FADER_LIVE_SENT")
        self.assertEqual(self.b.sent_faders,1)

    def test_explicit_host_invalidation_requires_new_real_pitchwheel(self):
        self.fader_host(0,60)
        self.b.rearm(invalidate_host=True)
        self.assertEqual(self.b.host_state.host_faders,[None]*8)
        self.assertEqual(self.b.physical_event(1,2,60),"FADER_WAIT_HOST")
        self.assertEqual(self.b.sent_faders,0)
        self.assertEqual(self.calls,[])
        self.fader_host(0,60)
        self.assertEqual(self.b.physical_event(1,2,61),"FADER_PICKUP_PASS")
        self.assertEqual(self.b.physical_event(1,2,62),"FADER_LIVE_SENT")

    def test_crossed_pickup_sends_last_physical_position(self):
        self.fader_host(0,65)
        for value in (20,30,40,50,60):
            self.assertEqual(self.b.physical_event(1,2,value),
                             "FADER_PICKUP_PENDING")
        self.assertEqual(self.calls,[])
        self.assertEqual(self.b.physical_event(1,2,80),
                         "FADER_PICKUP_CROSS_SENT")
        self.assertTrue(self.b.engaged[0])
        self.assertEqual(self.b.sent_faders,1)
        self.assertEqual(self.calls[-1],
                         ("pitchwheel",{"channel":0,
                             "pitch":mcu.physical_to_mcu(80)-8192}))
        self.assertEqual(self.b.physical_event(1,2,127),"FADER_LIVE_SENT")

    def test_reverse_crossed_pickup_sends_without_extra_cc(self):
        self.fader_host(0,65)
        self.assertEqual(self.b.physical_event(1,2,110),"FADER_PICKUP_PENDING")
        self.assertEqual(self.b.physical_event(1,2,30),
                         "FADER_PICKUP_CROSS_SENT")
        self.assertEqual(self.b.sent_faders,1)
        self.assertEqual(self.calls[-1],
                         ("pitchwheel",{"channel":0,
                             "pitch":mcu.physical_to_mcu(30)-8192}))

    def test_crossed_pickup_requires_real_host(self):
        self.assertEqual(self.b.physical_event(1,2,20),"FADER_WAIT_HOST")
        self.assertEqual(self.b.physical_event(1,2,80),"FADER_WAIT_HOST")
        self.assertEqual(self.calls,[])
        self.fader_host(0,65)
        self.b.rearm()
        self.assertEqual(self.b.physical_event(1,2,80),"FADER_PICKUP_PENDING")

    def test_read_only_crossed_pickup_sends_nothing(self):
        sent=[]
        b=live.LiveMixer(lambda kind,**kw:sent.append((kind,kw)),
                         lambda cc,v:None,write=False,clock=lambda:self.now)
        b.host(msg("pitchwheel",channel=0,
                   pitch=mcu.physical_to_mcu(65)-8192))
        b.physical_event(1,2,20)
        self.assertEqual(b.physical_event(1,2,80),"FADER_PICKUP_PASS")
        self.assertEqual(sent,[])

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

    def test_large_physical_jump_during_owned_touch_does_not_rearm(self):
        self.fader_host(0,60)
        self.b.physical_event(1,2,60)
        self.b.physical_event(1,2,61)
        self.b.physical_event(1,2,62)
        self.assertEqual(self.b.physical_event(1,2,110),"FADER_LIVE_SENT")
        self.assertEqual(self.b.physical_event(1,2,127),"FADER_LIVE_SENT")
        self.assertTrue(self.b.engaged[0])
        self.assertEqual(self.b.sent_faders,3)
        self.assertIn(0,self.b.touches)

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

    def test_handshake_only_hard_blocks_physical_mixer_output(self):
        self.assertFalse(live.physical_mixer_write_authorized(True, True))
        self.assertFalse(live.physical_mixer_write_authorized(False, True))
        self.assertFalse(live.physical_mixer_write_authorized(False, False))
        self.assertTrue(live.physical_mixer_write_authorized(True, False))
        sent=[]
        b=live.LiveMixer(
            lambda kind, **kw:sent.append((kind,kw)),
            lambda cc,value:None,
            write=live.physical_mixer_write_authorized(True, True),
            clock=lambda:self.now)
        b.host(msg("pitchwheel", channel=0,
                   pitch=mcu.physical_to_mcu(60)-8192))
        b.host(msg("note_on",channel=0,note=16,velocity=0))
        b.physical_event(1,2,60)
        self.assertEqual(b.physical_event(1,2,61),"FADER_PICKUP_PASS")
        self.assertEqual(b.physical_event(1,2,62),"FADER_LIVE_PREVIEW")
        self.assertEqual(b.physical_event(1,21,127),"BUTTON_LIVE_PREVIEW")
        b.tick()
        b.release_all()
        self.assertEqual(sent,[])

    def test_mcu_proprietary_startup_handshake_has_exact_sequence(self):
        self.assertEqual(live.MCU_SESSION_HEADER,(0,0,102,20))
        self.assertEqual(live.MCU_SESSION_QUERY[:5],(0,0,102,20,1))
        self.assertEqual(live.MCU_SESSION_CONFIRM[:5],(0,0,102,20,3))
        self.assertEqual(len(live.MCU_SESSION_QUERY),16)
        self.assertEqual(len(live.MCU_SESSION_CONFIRM),12)
        self.assertTrue(all(0<=x<=127 for x in live.MCU_SESSION_QUERY))
        self.assertEqual(
            live.mcu_connection_reply_for(msg("sysex",
                   data=live.MCU_EXPECTED_HOST_REPLY)),
            live.MCU_SESSION_CONFIRM)
        self.assertEqual(live.sysex_message_kind(
            msg("sysex",data=live.MCU_EXPECTED_HOST_REPLY)),
            "mcu_valid_connection_reply")

    def test_mcu_connection_rejects_foreign_serial_wrong_challenge(self):
        data=list(live.MCU_EXPECTED_HOST_REPLY)
        data[6]^=1
        self.assertIsNone(live.mcu_connection_reply_for(
            msg("sysex",data=tuple(data))))
        data=list(live.MCU_EXPECTED_HOST_REPLY)
        data[-1]^=1
        self.assertIsNone(live.mcu_connection_reply_for(
            msg("sysex",data=tuple(data))))
        self.assertIsNone(live.mcu_connection_reply_for(
            msg("sysex",data=live.MCU_SESSION_QUERY)))
        self.assertIsNone(live.mcu_connection_reply_for(
            msg("sysex",data=(0,0,102,20,2))))
        self.assertEqual(live.sysex_message_kind(
            msg("sysex",data=tuple(data))),
            "mcu_other_connection_reply")

    def test_mcu_session_does_not_guess_gain_or_invent_leds(self):
        self.assertEqual(self.b.physical_event(1,2,60),"FADER_WAIT_HOST")
        self.b.host(msg("sysex",data=live.MCU_SESSION_QUERY))
        self.b.host(msg("sysex",data=live.MCU_EXPECTED_HOST_REPLY))
        self.b.host(msg("sysex",data=live.MCU_SESSION_CONFIRM))
        self.assertEqual(self.b.host_state.host_faders,[None]*8)
        self.assertEqual(self.b.host_state.known_buttons,{})
        self.assertEqual(self.b.physical_event(1,2,61),"FADER_WAIT_HOST")
        self.assertEqual(self.b.sent,0)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.leds,[])

    def test_sysex_diagnostics_do_not_echo_track_names(self):
        text=b"PRIVATE_AUDIO_TRACK_123"
        self.assertEqual(live.sysex_message_kind(
            msg("sysex",data=(0,0,102,20,0x12,*text))),
            "mcu_command_12")
        self.assertEqual(live.sysex_message_kind(
            msg("sysex",data=(126,0,6,1))),
            "universal_identity_request")
        self.assertEqual(live.sysex_message_kind(
            msg("sysex",data=(0,0,102,20,0))),
            "mcu_device_query")
        self.assertEqual(live.sysex_message_kind(
            msg("sysex",data=(2,3,4))),"other")

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
        # Physical 63 -> 60 crosses the real host position, so pickup
        # legitimately arms NOW; without the real pitchwheel it could not.
        self.assertEqual(self.b.physical_event(1,2,60),"FADER_PICKUP_PASS")
        self.assertEqual(self.b.physical_event(1,2,61),"FADER_LIVE_SENT")
        self.assertEqual(self.b.sent_faders,1)

    def test_production_has_no_implicit_unbounded_midi_authorization(self):
        self.assertEqual(live.MAX_SECONDS,180)
        self.assertLessEqual(live.MAX_MESSAGES,1500)
        self.assertFalse(self.b.allow_strip8)
        self.assertFalse(live.LiveMixer(lambda *a, **kw:None,
                                         lambda *a, **kw:None).write)


if __name__ == "__main__":
    unittest.main()
