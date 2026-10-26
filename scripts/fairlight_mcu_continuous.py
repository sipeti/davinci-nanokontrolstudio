#!/usr/bin/env python3
"""Scene 2 Assignable -> Fairlight MCU mixer worker.

One Hammerspoon Korg owner, two distinct IAC ports, host-only LED
authority. Default NO output; continuous operation requires explicit
operator opt-in. MIDI strip 8 remains blocked (potential Bus 1).
"""
import argparse
from collections import Counter
from contextlib import ExitStack
import fcntl
import pathlib
import time

from fairlight_mcu_bridge import (
    Bridge, CONSENT, FEEDBACK, FADER_PICKUP_TOLERANCE,
    FADER_CC_TO_STRIP, MAX_MESSAGES_PER_POLL, SOLO_CC, SOURCE,
    _NullOutput, parse_event,
    physical_to_mcu,
)

MAX_SECONDS = 180
MAX_MESSAGES = 1200
# A physical absolute MIDI fader does NOT need smoothing or coalescing.
# After safe host-position pickup, every changed CC is immediately mapped
# to the matching MCU pitchwheel; the 500ms TOUCH timer is independent.
TOUCH_HOLD = 0.5
BUTTON_HOLD = 0.08
# Resolve transmits mixer faders at project load / bank refresh, NOT every
# 10 seconds. The per-session host snapshot remains authoritative until a
# newer actual host pitchwheel or a genuine MIDI session invalidation.
# Focusing another app or changing Korg Scene re-arms physical pickup only.
HEARTBEAT_TIMEOUT = 2.0
MIDI_LOCK = pathlib.Path.home() / "Library/Caches/nk-fairlight-live.lock"

# MIDI universal identity request previously CAPTURED from Resolve:
# F0 7E 00 06 01 F7. Earlier bridge ignored the recurring request (~1/s).
# Respond with a standard, narrowly scoped Universal Identity Reply for
# the Mackie Control emulator (manufacturer 00 00 66, family 14 00).
# Identity reply does NOT read/move a fader or imply host fader authority.
# This remains strictly optional and requires the disposable-project
# MIDI-output consent; verify whether Resolve sends pitchwheel afterward.
MCU_ID_REQUEST = (0x7E, 0x00, 0x06, 0x01)
MCU_ID_REPLY = (
    0x7E, 0x00, 0x06, 0x02,       # universal identity response
    0x00, 0x00, 0x66,             # Mackie manufacturer id
    0x14, 0x00,                   # Mackie Control family
    0x00, 0x00,                   # member
    0x01, 0x00, 0x00, 0x00,       # revision 1.0.0.0
)
MAX_IDENTITY_REPLIES = 3
MIN_IDENTITY_REPLY_PERIOD = 1.0

# MCU proprietary connection negotiation is DISTINCT from MIDI Universal
# Identity Reply. A real Mackie/Logic Control surface announces itself with
# host-connection Query 0x01, and may receive a challenge Response 0x02.
# Verify reply before emitting Confirmation 0x03. Never assume this makes
# any mixer fader value authoritative: only actual host pitchwheel does.
MCU_SESSION_HEADER = (0x00, 0x00, 0x66, 0x14)
MCU_SESSION_SERIAL = tuple(b"NKST001")  # stable 7-byte test-surface serial
MCU_SESSION_CHALLENGE = (0x1D, 0x26, 0x37, 0x4B)
MCU_SESSION_QUERY = (
    MCU_SESSION_HEADER + (0x01,) + MCU_SESSION_SERIAL +
    MCU_SESSION_CHALLENGE
)
MCU_SESSION_CONFIRM = MCU_SESSION_HEADER + (0x03,) + MCU_SESSION_SERIAL


def mcu_connection_response(challenge):
    """Logic Control / Mackie host challenge-response, four 7-bit bytes."""
    if len(challenge) != 4 or any(
            type(x) is not int or not 0 <= x <= 127 for x in challenge):
        raise ValueError("MCU challenge must contain exactly four MIDI data bytes")
    a, b, c, d = challenge
    return (
        (a + (b ^ 0x0A) - d) & 0x7F,
        ((c >> 4) ^ (a + d)) & 0x7F,
        ((d - (c << 2)) ^ (a | b)) & 0x7F,
        (b - c + (0xF0 ^ (d << 4))) & 0x7F,
    )


MCU_EXPECTED_HOST_REPLY = (
    MCU_SESSION_HEADER + (0x02,) + MCU_SESSION_SERIAL +
    mcu_connection_response(MCU_SESSION_CHALLENGE)
)


def mcu_connection_reply_for(message):
    """Recognize ONLY the exact host response to OUR bounded device query."""
    if (getattr(message, "type", None) == "sysex" and
            tuple(getattr(message, "data", ())) == MCU_EXPECTED_HOST_REPLY):
        return MCU_SESSION_CONFIRM
    return None


def sysex_message_kind(message):
    """Report MIDI SysEx *kind*, never log project/track-name payloads."""
    if getattr(message, "type", None) != "sysex":
        return None
    payload = tuple(getattr(message, "data", ()))
    if payload == MCU_ID_REQUEST:
        return "universal_identity_request"
    if payload == MCU_EXPECTED_HOST_REPLY:
        return "mcu_valid_connection_reply"
    if payload[:5] == MCU_SESSION_HEADER + (0x02,):
        return "mcu_other_connection_reply"
    if payload == MCU_SESSION_HEADER + (0x00,):
        return "mcu_device_query"
    if payload[:4] == MCU_SESSION_HEADER and len(payload) >= 5:
        return "mcu_command_%02x" % payload[4]
    if payload[:2] == (0x7E, 0x00):
        return "universal_other"
    return "other"


def physical_mixer_write_authorized(enable_output, handshake_only):
    """The MIDI port can send a protocol handshake but NO mixer commands."""
    return bool(enable_output and not handshake_only)


def mcu_identity_reply_for(message):
    """Return fixed MCU identity payload ONLY for exact observed request."""
    if (getattr(message, "type", None) == "sysex"
            and tuple(getattr(message, "data", ())) == MCU_ID_REQUEST):
        return MCU_ID_REPLY
    return None


class LiveMixer:
    """A bounded Fairlight MCU state machine with soft pickup and MIDI key-up."""

    def __init__(self, send, led, *, write=False, allow_strip8=False,
                 packet_cap=MAX_MESSAGES, clock=time.monotonic):
        self.send = send
        self.write = write
        self.clock = clock
        self.allow_strip8 = allow_strip8
        self.packet_cap = packet_cap
        self.host_state = Bridge(lambda *args, **kw: None, led, clock=clock)
        self.engaged = [False] * 8
        self.physical = [None] * 8
        self.last_sent_position = [None] * 8
        self.touches = {}       # strip index -> release time
        self.keys = {}          # MCU note -> release time
        self.physical_down = set()
        self.sent = 0           # total MIDI packets, including releases
        self.sent_faders = 0
        self.sent_buttons = 0
        self.blocked = 0

    def host(self, message):
        if getattr(message, "type", None) == "pitchwheel":
            strip = getattr(message, "channel", -1)
            pitch = getattr(message, "pitch", None)
            if (type(strip) is int and 0 <= strip < 8 and
                    type(pitch) is int and -8192 <= pitch <= 8191 and
                    strip not in self.touches and self.engaged[strip] and
                    self.last_sent_position[strip] is not None and
                    abs(pitch + 8192 - self.last_sent_position[strip]) >
                    FADER_PICKUP_TOLERANCE):
                # External mixer changes revoke soft takeover.
                self.engaged[strip] = False
        self.host_state.host(message)

    def _send(self, kind, *, release=False, **kw):
        if not self.write:
            raise RuntimeError("READ_ONLY must never transmit MIDI")
        if not release and self.packet_cap is not None and self.sent >= self.packet_cap:
            raise RuntimeError("MIDI_OUTPUT_CAP_REACHED")
        self.send(kind, **kw)
        self.sent += 1

    def _release_touch(self, strip):
        if strip not in self.touches:
            return
        try:
            self._send("note_on", release=True, channel=0,
                       note=104 + strip, velocity=0)
        finally:
            self.touches.pop(strip, None)

    def _release_key(self, note):
        if note not in self.keys:
            return
        try:
            self._send("note_off", release=True, channel=0,
                       note=note, velocity=0)
        finally:
            self.keys.pop(note, None)

    def _send_fader(self, strip, goal):
        """Forward one changed physical CC as MCU pitchwheel with TOUCH.

        Called only after physical movement acquired the host position.
        Mark TOUCH active before transmitting for fail-safe release.
        """
        try:
            if strip not in self.touches:
                self.touches[strip] = self.clock() + TOUCH_HOLD
                self._send("note_on", channel=0,
                           note=104 + strip, velocity=127)
            self._send("pitchwheel", channel=strip, pitch=goal - 8192)
            self.last_sent_position[strip] = goal
            self.touches[strip] = self.clock() + TOUCH_HOLD
            self.sent_faders += 1
        except BaseException:
            self.release_all()
            raise

    def tick(self):
        now = self.clock()
        for strip, deadline in tuple(self.touches.items()):
            if now >= deadline:
                self._release_touch(strip)
        for note, deadline in tuple(self.keys.items()):
            if now >= deadline:
                self._release_key(note)

    def release_all(self):
        failures = []
        for strip in tuple(self.touches):
            try:
                self._release_touch(strip)
            except Exception as exc:
                failures.append(("touch", strip, str(exc)))
        for note in tuple(self.keys):
            try:
                self._release_key(note)
            except Exception as exc:
                failures.append(("button", note, str(exc)))
        if failures:
            raise RuntimeError("MCU_RELEASE_FAILED: %r; restart Resolve" %
                               failures)

    def rearm(self, *, invalidate_host=False):
        """Disarm physical Korg controls without destroying live MCU snapshot.

        Fader pitchwheel arrives only on Resolve project open or mixer
        changes. Hammerspoon H=0/R events are *not* evidence that a new
        Resolve project or MCU bank was loaded. Reset physical pickup, but
        keep the last real host positions received on this open IAC port.
        A genuine port/session change may explicitly invalidate the cache.
        """
        self.release_all()
        if invalidate_host:
            self.host_state.rearm()
        self.engaged = [False] * 8
        self.physical = [None] * 8
        self.last_sent_position = [None] * 8
        self.physical_down.clear()

    def physical_event(self, ch, cc, value):
        if ch != 1:
            self.rearm()
            return "SCENE_REARM"
        if type(cc) is not int or type(value) is not int or not 0 <= value <= 127:
            return "INVALID"
        if cc in FADER_CC_TO_STRIP:
            strip = FADER_CC_TO_STRIP[cc]
            if strip == 7 and not self.allow_strip8:
                return "BUS1_STRIP8_LOCKED"
            goal = physical_to_mcu(value)
            old = self.physical[strip]
            self.physical[strip] = goal
            host = self.host_state.host_faders[strip]
            if host is None:
                self.blocked += 1
                return "FADER_WAIT_HOST"
            if not self.engaged[strip]:
                # A non-motorized absolute Korg fader can skip the exact
                # target while moving fast. If consecutive ACTUAL physical
                # samples straddle the last authoritative Fairlight value,
                # the handoff happened even if neither sample is within
                # the usual ~2-CC tolerance. Requires genuine physical
                # movement and a real host MCU pitchwheel snapshot.
                crossed = (old is not None and old != goal and
                           min(old, goal) <= host <= max(old, goal))
                close = abs(goal - host) <= FADER_PICKUP_TOLERANCE
                if old is not None and old != goal and (crossed or close):
                    self.engaged[strip] = True
                    if crossed and not close:
                        # Example: host=65, Korg physical 20 -> 80.
                        # If 80 is the final sample, merely "arming" would
                        # strand Fairlight at 65 until another CC arrived.
                        # The explicit overshoot is now the user's physical
                        # requested gain; send it immediately when writable.
                        if self.write:
                            self._send_fader(strip, goal)
                            return "FADER_PICKUP_CROSS_SENT"
                        return "FADER_PICKUP_PASS"
                    return "FADER_PICKUP_PASS"
                return "FADER_PICKUP_PENDING"
            if goal == old:
                return "FADER_DUPLICATE"
            # After legitimate soft takeover, actual physical movement is
            # authoritative: pass every changed 0..127 CC to MCU without
            # arbitrary 30ms coalescing or fast-motion auto-disarm.
            if not self.write:
                return "FADER_LIVE_PREVIEW"
            self._send_fader(strip, goal)
            return "FADER_LIVE_SENT"

        if 21 <= cc <= 28:
            strip, note = cc - 21, 16 + cc - 21
        elif cc in SOLO_CC:
            strip, note = SOLO_CC.index(cc), 8 + SOLO_CC.index(cc)
        else:
            return "IGNORED"
        if strip == 7 and not self.allow_strip8:
            return "BUS1_STRIP8_LOCKED"
        if value not in (0, 127):
            return "BUTTON_INVALID_VALUE"
        if value == 0:
            self.physical_down.discard(cc)
            return "BUTTON_RELEASED"
        if cc in self.physical_down:
            return "BUTTON_DUPLICATE"
        self.physical_down.add(cc)
        if not self.write:
            return "BUTTON_LIVE_PREVIEW"
        try:
            # Mark key held BEFORE sending, so even a partial send failure
            # reaches the fail-safe key-up path.
            self.keys[note] = self.clock() + BUTTON_HOLD
            self._send("note_on", channel=0, note=note, velocity=127)
            self.sent_buttons += 1
            return "BUTTON_LIVE_SENT"
        except BaseException:
            self.release_all()
            raise


def main():
    p = argparse.ArgumentParser(description="Fairlight test-only MCU continuous bridge")
    p.add_argument("--input-port", required=True)
    p.add_argument("--output-port", required=True)
    p.add_argument("--seconds", type=int, default=90)
    p.add_argument("--continuous", action="store_true",
                   help="explicit Ctrl+C session; disables bench packet cap")
    p.add_argument("--enable-output", action="store_true")
    p.add_argument("--reply-mcu-identity", action="store_true",
                   help="experimental MIDI Universal Identity Reply; alone did NOT seed host faders")
    p.add_argument("--init-mcu-session", action="store_true",
                   help="experimental MCU host connection handshake")
    p.add_argument("--handshake-only", action="store_true",
                   help="hard fence ALL physical fader/MUTE/SOLO writes during MCU connection trial")
    p.add_argument("--enable-strip8-bus1", action="store_true",
                   help="EXPLICIT option: strip8 follows CURRENT Fairlight bank; not fixed master")
    p.add_argument("--consent")
    args = p.parse_args()
    if args.continuous:
        if args.seconds != 0:
            p.error("--continuous requires --seconds 0")
    elif not 1 <= args.seconds <= MAX_SECONDS:
        p.error("bench session must last 1..180 seconds")
    if args.enable_output and args.consent != CONSENT:
        p.error("backed-up disposable Fairlight test project consent required")
    if args.reply_mcu_identity and not args.enable_output:
        p.error("MCU identity replies need --enable-output and disposable consent")
    if args.init_mcu_session and not args.enable_output:
        p.error("MCU session handshake needs --enable-output and disposable consent")
    if args.handshake_only and not args.init_mcu_session:
        p.error("--handshake-only requires --init-mcu-session")
    if args.handshake_only and args.reply_mcu_identity:
        p.error("One handshake protocol at a time; disable --reply-mcu-identity")
    if args.handshake_only and args.enable_strip8_bus1:
        p.error("Bus1 enabling is forbidden in MCU handshake-only trial")
    if args.enable_strip8_bus1 and not args.enable_output:
        p.error("strip8 is blocked unless explicit output trial is enabled")
    if args.input_port == args.output_port:
        p.error("IAC MIDI input and output must be different")
    try:
        import mido
    except ImportError:
        print("MCU_LIVE=BLOCKED; install mido and python-rtmidi", flush=True)
        return 1
    if args.input_port not in mido.get_input_names() or (
            args.output_port not in mido.get_output_names()):
        print("MCU_LIVE=BLOCKED; requested IAC ports unavailable", flush=True)
        return 1
    if not SOURCE.is_file():
        print("MCU_LIVE=BLOCKED; enable the Hammerspoon Scene2 bridge",
              flush=True)
        return 1

    with ExitStack() as stack:
        lock = stack.enter_context(MIDI_LOCK.open("w"))
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("MCU_LIVE=BLOCKED; already running a live bridge",
                  flush=True)
            return 1
        receive = stack.enter_context(mido.open_input(args.input_port))
        output = stack.enter_context(
            mido.open_output(args.output_port) if args.enable_output
            else _NullOutput())
        events = stack.enter_context(SOURCE.open("r", encoding="ascii"))
        feedback = stack.enter_context(FEEDBACK.open("w", encoding="ascii"))
        events.seek(0, 2)
        initial = SOURCE.stat()

        def send(kind, **kw):
            output.send(mido.Message(kind, **kw))

        def led(cc, value):
            feedback.write("%d,L,%d,%d\n" %
                           (int(time.time() * 1000), cc, value))
            feedback.flush()
            host_led_events[cc] += 1
            if host_led_last.get(cc) != value:
                host_led_last[cc] = value
                print("MCU_LIVE_HOST_LED=cc:%d state:%s; "
                      "host-authoritative; feedback file updated" %
                      (cc, "ON" if value == 127 else "OFF"), flush=True)

        mixer = LiveMixer(
            send, led,
            write=physical_mixer_write_authorized(
                args.enable_output, args.handshake_only),
            allow_strip8=args.enable_strip8_bus1,
            packet_cap=None if args.continuous else MAX_MESSAGES)
        started = time.monotonic()
        last_h = None
        last_feedback_h = float("-inf")
        ready = False
        counters = Counter()
        host_rx = Counter()
        host_fader_channels = Counter()
        id_requests = 0
        id_replies = 0
        last_id_reply = float("-inf")
        sysex_types = Counter()
        session_query_sent = False
        session_reply_seen = False
        session_confirm_sent = False
        host_led_events = Counter()
        host_led_last = {}
        printed = set()
        soft_rearms = Counter()
        print("MCU_LIVE=START; mode=%s; duration=%s; "
              "strip8=%s; no auto-start" %
              ("HANDSHAKE_ONLY" if args.handshake_only
               else "BENCH_OUTPUT" if args.enable_output else "READ_ONLY",
               "until Ctrl+C" if args.continuous else str(args.seconds) + "s",
               "explicitly_enabled" if args.enable_strip8_bus1
               else "LOCKED"), flush=True)
        try:
            if args.init_mcu_session:
                # Initial virtual-controller power-on/connection query.
                # This handshake alone MUST NEVER arm a physical fader.
                output.send(mido.Message("sysex", data=MCU_SESSION_QUERY))
                session_query_sent = True
                print("MCU_LIVE_SESSION=QUERY_SENT; "
                      "awaiting host challenge reply; no mixer write",
                      flush=True)
            while args.continuous or time.monotonic() - started < args.seconds:
                now = time.monotonic()
                if now - last_feedback_h >= 0.5:
                    feedback.write("%d,H,0,1\n" %
                                   int(time.time() * 1000))
                    feedback.flush()
                    last_feedback_h = now
                stat = SOURCE.stat()
                if ((stat.st_dev, stat.st_ino) !=
                        (initial.st_dev, initial.st_ino) or
                        stat.st_size < events.tell()):
                    raise RuntimeError("Hammerspoon input logger replaced")
                for msg in receive.iter_pending():
                    host_rx[msg.type] += 1
                    if msg.type == "sysex":
                        sysex_types[sysex_message_kind(msg)] += 1
                        if args.init_mcu_session:
                            confirm = mcu_connection_reply_for(msg)
                            if confirm is not None and not session_confirm_sent:
                                session_reply_seen = True
                                output.send(mido.Message("sysex", data=confirm))
                                session_confirm_sent = True
                                print("MCU_LIVE_SESSION=CONFIRMED; "
                                      "actual Fairlight fader state still needed",
                                      flush=True)
                    identity = mcu_identity_reply_for(msg)
                    if identity is not None:
                        id_requests += 1
                        if (args.reply_mcu_identity and
                                id_replies < MAX_IDENTITY_REPLIES and
                                now - last_id_reply >= MIN_IDENTITY_REPLY_PERIOD):
                            # This is a device identity declaration, NOT a
                            # mixer control or a permission to skip pickup.
                            output.send(mido.Message("sysex", data=identity))
                            id_replies += 1
                            last_id_reply = now
                            print("MCU_LIVE_IDENTITY_REPLY=sent:%d/%d; "
                                  "host faders still require actual pitchwheel" %
                                  (id_replies,MAX_IDENTITY_REPLIES),flush=True)
                    if (msg.type == "pitchwheel" and
                            0 <= msg.channel < 8):
                        host_fader_channels[msg.channel + 1] += 1
                        if host_fader_channels[msg.channel + 1] == 1:
                            print("MCU_LIVE_HOST_FADER_SEEDED=strip:%d; "
                                  "actual MCU pitchwheel received" %
                                  (msg.channel + 1), flush=True)
                    mixer.host(msg)
                for _ in range(MAX_MESSAGES_PER_POLL):
                    line = events.readline()
                    if not line:
                        break
                    item = parse_event(line, int(time.time() * 1000))
                    if not item:
                        continue
                    kind, ch, cc, value = item
                    if kind == "H":
                        last_h = now
                        if ready and value == 0:
                            mixer.rearm()  # soft, keep Fairlight snapshot
                            soft_rearms["focus_lost"] += 1
                        ready = bool(value)
                    elif kind == "R":
                        ready = False
                        mixer.rearm()      # Korg Scene change != MCU bank change
                        soft_rearms["korg_scene"] += 1
                    elif kind == "M" and ready:
                        if args.handshake_only:
                            # Double fence: LiveMixer.write=False as well.
                            # No physical CC is allowed to modify Fairlight
                            # while testing MCU initialization.
                            counters["MIXER_OUTPUT_FENCED"] += 1
                            continue
                        result = mixer.physical_event(ch, cc, value)
                        counters[result] += 1
                        marker = (cc, result)
                        if (result in ("FADER_PICKUP_PASS", "FADER_PICKUP_CROSS_SENT",
                                       "BUTTON_LIVE_SENT") or
                                (marker not in printed and
                                 result not in ("FADER_LIVE_SENT",
                                                "BUTTON_RELEASED",
                                                "FADER_DUPLICATE"))):
                            print("MCU_LIVE %s CC=%d value=%d" %
                                  (result, cc, value), flush=True)
                        printed.add(marker)
                mixer.tick()
                if last_h is None and now - started > 3:
                    raise RuntimeError(
                        "no Hammerspoon heartbeat: launch Hammerspoon, then "
                        "NK JOG > Scene 2 clip gain MIDI bridge: BE "
                        "(re-enable after hs.reload)")
                if last_h is not None and now - last_h > HEARTBEAT_TIMEOUT:
                    raise RuntimeError("lost Hammerspoon heartbeat")
                time.sleep(.01)
        except KeyboardInterrupt:
            print("MCU_LIVE=STOP; Ctrl+C", flush=True)
            return_code = 0
        except Exception as exc:
            print("MCU_LIVE=HALT; %s" % exc, flush=True)
            return_code = 1
        else:
            return_code = 0
        finally:
            try:
                mixer.release_all()
            except Exception as exc:
                print("MCU_LIVE=RELEASE_FAILED; %s; restart Resolve" % exc,
                      flush=True)
                return_code = 1
            feedback.write("%d,H,0,0\n" % int(time.time() * 1000))
            feedback.flush()
            print("MCU_LIVE=COMPLETE; fader_positions=%d; "
                  "button_presses=%d; midi_packets=%d; blocked=%d" %
                  (mixer.sent_faders, mixer.sent_buttons,
                   mixer.sent, mixer.blocked), flush=True)
            print("MCU_LIVE_STATUSES=" +
                  ",".join("%s:%d" % (k, counters[k])
                           for k in sorted(counters)), flush=True)
            print("MCU_LIVE_SOFT_REARMS=" +
                  ",".join("%s:%d" % (k, soft_rearms[k])
                           for k in sorted(soft_rearms)), flush=True)
            print("MCU_LIVE_HOST_SNAPSHOT_PRESENT=" +
                  ",".join(str(i+1) for i,value in
                           enumerate(mixer.host_state.host_faders)
                           if value is not None), flush=True)
            print("MCU_LIVE_HOST_RX=" +
                  ",".join("%s:%d" % (k,host_rx[k])
                           for k in sorted(host_rx)), flush=True)
            print("MCU_LIVE_IDENTITY=requests:%d,replies:%d,mode:%s" %
                  (id_requests,id_replies,
                   "enabled" if args.reply_mcu_identity else "disabled"),
                  flush=True)
            print("MCU_LIVE_SESSION=query:%s,reply:%s,confirmed:%s,mode:%s" %
                  (session_query_sent,session_reply_seen,
                   session_confirm_sent,
                   "enabled" if args.init_mcu_session else "disabled"),
                  flush=True)
            print("MCU_LIVE_SYSEX_TYPES=" +
                  ",".join("%s:%d" % (key,sysex_types[key])
                           for key in sorted(sysex_types)), flush=True)
            print("MCU_LIVE_HOST_FADERS=" +
                  ",".join("strip%d:%d" % (k,host_fader_channels[k])
                           for k in sorted(host_fader_channels)), flush=True)
            print("MCU_LIVE_HOST_LED_EVENTS=" +
                  ",".join("cc%d:%d" % (k,host_led_events[k])
                           for k in sorted(host_led_events)), flush=True)
            if not host_led_events:
                print("MCU_LIVE_LED=NO_FAIRLIGHT_NOTE_FEEDBACK; "
                      "no trustworthy Korg LED state received", flush=True)
            if not host_fader_channels:
                print("MCU_LIVE_FADER=NO_HOST_FADER_POSITIONS; "
                      "soft-pickup must stay blocked", flush=True)
        return return_code


if __name__ == "__main__":
    raise SystemExit(main())
