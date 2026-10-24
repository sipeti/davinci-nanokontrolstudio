#!/usr/bin/env python3
"""Finite, opt-in Scene2 Assignable -> Fairlight MCU bench controller.

One existing Hammerspoon hardware owner, two distinct IAC ports, host-only
LED authority. Default NO output. No auto-start or production deployment.
MIDI strip8 is blocked by default because it may be the main Bus 1.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
import fcntl
import pathlib
import time

from fairlight_mcu_bridge import (
    Bridge, CONSENT, FEEDBACK, FADER_PICKUP_TOLERANCE, FADER_STEP_LIMIT,
    MAX_MESSAGES_PER_POLL, SOLO_CC, SOURCE, _NullOutput, parse_event,
    physical_to_mcu,
)

MAX_SECONDS = 180
MAX_MESSAGES = 1200
FADER_PERIOD = 0.03
TOUCH_HOLD = 0.5
BUTTON_HOLD = 0.08
HOST_INITIAL_AGE = 10.0
HEARTBEAT_TIMEOUT = 2.0
MIDI_LOCK = pathlib.Path.home() / "Library/Caches/nk-fairlight-live.lock"


class LiveMixer:
    """A bounded Fairlight MCU state machine with soft pickup and MIDI key-up."""

    def __init__(self, send, led, *, write=False, allow_strip8=False,
                 clock=time.monotonic):
        self.send = send
        self.write = write
        self.clock = clock
        self.allow_strip8 = allow_strip8
        self.host_state = Bridge(lambda *args, **kw: None, led, clock=clock)
        self.engaged = [False] * 8
        self.physical = [None] * 8
        self.last_sent_position = [None] * 8
        self.last_sent_at = [float("-inf")] * 8
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
        if not release and self.sent >= MAX_MESSAGES:
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

    def rearm(self):
        self.release_all()
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
        if 2 <= cc <= 9:
            strip = cc - 2
            if strip == 7 and not self.allow_strip8:
                return "BUS1_STRIP8_LOCKED"
            goal = physical_to_mcu(value)
            old = self.physical[strip]
            self.physical[strip] = goal
            host = self.host_state.host_faders[strip]
            host_at = self.host_state.host_fader_time[strip]
            if host is None or host_at is None:
                self.blocked += 1
                return "FADER_WAIT_HOST"
            if not self.engaged[strip]:
                if self.clock() - host_at > HOST_INITIAL_AGE:
                    self.blocked += 1
                    return "FADER_HOST_STALE"
                if (old is not None and old != goal and
                        abs(goal - host) <= FADER_PICKUP_TOLERANCE):
                    self.engaged[strip] = True
                    return "FADER_PICKUP_PASS"
                return "FADER_PICKUP_PENDING"
            if goal == old:
                return "FADER_DUPLICATE"
            if abs(goal - old) > FADER_STEP_LIMIT:
                self.engaged[strip] = False
                self._release_touch(strip)
                return "FADER_JUMP_REARM"
            if (strip not in self.touches and
                    self.last_sent_position[strip] is None and
                    abs(goal - host) > FADER_PICKUP_TOLERANCE):
                self.engaged[strip] = False
                return "FADER_DESYNC_REARM"
            if (strip not in self.touches and
                    self.last_sent_position[strip] is not None and
                    abs(goal - self.last_sent_position[strip]) >
                    FADER_STEP_LIMIT):
                self.engaged[strip] = False
                return "FADER_GESTURE_REARM"
            if self.clock() - self.last_sent_at[strip] < FADER_PERIOD:
                return "FADER_RATE_COALESCED"
            if not self.write:
                return "FADER_LIVE_PREVIEW"
            try:
                if strip not in self.touches:
                    self._send("note_on", channel=0,
                               note=104 + strip, velocity=127)
                    self.touches[strip] = self.clock() + TOUCH_HOLD
                self._send("pitchwheel", channel=strip, pitch=goal - 8192)
                self.last_sent_position[strip] = goal
                self.last_sent_at[strip] = self.clock()
                self.touches[strip] = self.clock() + TOUCH_HOLD
                self.sent_faders += 1
                return "FADER_LIVE_SENT"
            except BaseException:
                self.release_all()
                raise

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
            self._send("note_on", channel=0, note=note, velocity=127)
            self.keys[note] = self.clock() + BUTTON_HOLD
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
    p.add_argument("--enable-output", action="store_true")
    p.add_argument("--enable-strip8-bus1", action="store_true",
                   help="EXPLICIT option: strip8 follows CURRENT Fairlight bank; not fixed master")
    p.add_argument("--consent")
    args = p.parse_args()
    if not 1 <= args.seconds <= MAX_SECONDS:
        p.error("bench session must last 1..180 seconds")
    if args.enable_output and args.consent != CONSENT:
        p.error("backed-up disposable Fairlight test project consent required")
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

        mixer = LiveMixer(send, led, write=args.enable_output,
                          allow_strip8=args.enable_strip8_bus1)
        started = time.monotonic()
        last_h = None
        last_feedback_h = float("-inf")
        ready = False
        counters = Counter()
        printed = set()
        print("MCU_LIVE=START; mode=%s; duration=%ds; "
              "strip8=%s; no auto-start" %
              ("BENCH_OUTPUT" if args.enable_output else "READ_ONLY",
               args.seconds, "explicitly_enabled" if args.enable_strip8_bus1
               else "LOCKED"), flush=True)
        try:
            while time.monotonic() - started < args.seconds:
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
                            mixer.rearm()
                        ready = bool(value)
                    elif kind == "R":
                        ready = False
                        mixer.rearm()
                    elif kind == "M" and ready:
                        result = mixer.physical_event(ch, cc, value)
                        counters[result] += 1
                        marker = (cc, result)
                        if (result in ("FADER_PICKUP_PASS", "BUTTON_LIVE_SENT",
                                      "BUS1_STRIP8_LOCKED") or
                                (marker not in printed and
                                 result not in ("FADER_RATE_COALESCED",
                                                "BUTTON_RELEASED",
                                                "FADER_DUPLICATE"))):
                            print("MCU_LIVE %s CC=%d value=%d" %
                                  (result, cc, value), flush=True)
                        printed.add(marker)
                mixer.tick()
                if last_h is None and now - started > 3:
                    raise RuntimeError("no Hammerspoon heartbeat")
                if last_h is not None and now - last_h > HEARTBEAT_TIMEOUT:
                    raise RuntimeError("lost Hammerspoon heartbeat")
                time.sleep(.01)
        except KeyboardInterrupt:
            print("MCU_LIVE=STOP; Ctrl+C", flush=True)
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
        return return_code


if __name__ == "__main__":
    raise SystemExit(main())
