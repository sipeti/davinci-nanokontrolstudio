#!/usr/bin/env python3
"""Opt-in, bounded Scene2 Assignable CC -> Fairlight MCU MIDI translator.

Source: existing Hammerspoon callback's five-column CSV (no second Korg
listener). Destination: a *separate*, explicitly named IAC output port;
return path: a separate IAC input port carrying actual Fairlight feedback.
Default mode is OBSERVE ONLY, with zero MIDI output.

MCU MIDI protocol (not clip gain): pitch bend ch0..7 = 8 mixer faders,
note 0x08..0x0F = solo and 0x10..0x17 = mute. Position/status MUST first
come from Fairlight; no MIDI write or invented Korg LED state without it.
Physical Scene2 map CC2..9, CC21..28, CC29..36 is a CANDIDATE pending
a physical Assignable-mode capture; verify before enabling output.
"""
import argparse
import math
import pathlib
import sys
import time

SOURCE = pathlib.Path.home() / "Library/Caches/nk-scene2-controller-events.csv"
FEEDBACK = pathlib.Path.home() / "Library/Caches/nk-fairlight-mcu-feedback.csv"
CONSENT = "I CONFIRMED A BACKED-UP DISPOSABLE FAIRLIGHT PROJECT"
MAX_AGE_MS = 1000
HEARTBEAT_TIMEOUT = 2.0
MAX_MESSAGES_PER_POLL = 512
FADER_PICKUP_TOLERANCE = 270   # ~2 of 127 Korg CC positions
FADER_STEP_LIMIT = 1400        # ~10 physical CC positions
ACK_TOLERANCE = 140
ACK_TIMEOUT = 0.75

def parse_event(line, now_ms):
    parts = line.strip().split(",")
    if len(parts) != 5:
        return None
    try:
        timestamp, ch, cc, value = map(int, (parts[0], parts[2], parts[3], parts[4]))
    except ValueError:
        return None
    kind = parts[1]
    if (kind not in ("H", "R", "M") or
        timestamp > now_ms or now_ms - timestamp > MAX_AGE_MS or
        not (0 <= ch <= 15 and 0 <= cc <= 127 and 0 <= value <= 127)):
        return None
    if kind == "H" and (ch,cc,value) not in ((0,0,0),(0,0,1)):
        return None
    return kind, ch, cc, value


def physical_to_mcu(value):
    if type(value) is not int or not 0 <= value <= 127:
        raise ValueError("Korg physical fader must be 0..127")
    return round(value * 16383 / 127)


class Bridge:
    """Pure state machine; send(type, fields) and led(cc, state) are injected."""

    def __init__(self, send, led, *, write=False, clock=time.monotonic):
        self.send = send
        self.led = led
        self.write = write
        self.clock = clock
        self.host_faders = [None] * 8
        self.physical = [None] * 8
        self.engaged = [False] * 8
        self.pending = [None] * 8
        self.known_buttons = {}
        self.pressed = {}
        self.sent = 0
        self.blocked = 0

    def rearm(self):
        self.physical = [None] * 8
        self.engaged = [False] * 8
        self.pending = [None] * 8
        self.known_buttons = {}
        self.pressed = {}
        self.host_faders = [None] * 8

    def host(self, message):
        """Host-to-controller is the *only* authority for LED/fader state."""
        kind = getattr(message, "type", "")
        if kind == "pitchwheel":
            channel = getattr(message, "channel", -1)
            pitch = getattr(message, "pitch", None)
            if type(channel) is not int or not 0 <= channel < 8:
                return
            if type(pitch) is not int or not -8192 <= pitch <= 8191:
                return
            value = pitch + 8192
            expected = self.pending[channel]
            if expected is not None:
                if abs(expected[0] - value) <= ACK_TOLERANCE:
                    self.pending[channel] = None
                else:
                    self.engaged[channel] = False
                    self.pending[channel] = None
            elif (self.engaged[channel] and self.host_faders[channel] is not None
                  and abs(value - self.host_faders[channel]) > FADER_PICKUP_TOLERANCE):
                self.engaged[channel] = False
            self.host_faders[channel] = value
        elif kind in ("note_on", "note_off"):
            channel = getattr(message, "channel", -1)
            note = getattr(message, "note", -1)
            velocity = getattr(message, "velocity", 0)
            if channel != 0 or type(note) is not int or not (
                    8 <= note <= 23) or type(velocity) is not int:
                return
            if not 0 <= velocity <= 127:
                return
            on = kind == "note_on" and velocity > 0
            cc = (note - 8 + 29) if note < 16 else (note - 16 + 21)
            self.known_buttons[cc] = on
            self.led(cc, 127 if on else 0)

    def physical_event(self, ch, cc, value):
        if ch != 1:
            self.rearm()
            return "SCENE_REARM"
        if type(value) is not int or not 0 <= value <= 127:
            return "INVALID"
        if 2 <= cc <= 9:
            strip = cc - 2
            goal = physical_to_mcu(value)
            old = self.physical[strip]
            self.physical[strip] = goal
            host = self.host_faders[strip]
            if host is None:
                self.blocked += 1
                return "FADER_WAIT_FOR_FAIRLIGHT_POSITION"
            if self.pending[strip] is not None:
                if self.clock() - self.pending[strip][1] > ACK_TIMEOUT:
                    self.engaged[strip] = False
                    self.pending[strip] = None
                    return "FADER_ACK_TIMEOUT_REARM"
                return "FADER_WAIT_ACK"
            if not self.engaged[strip]:
                crossed = old is not None and min(old, goal) <= host <= max(old, goal)
                close = abs(goal - host) <= FADER_PICKUP_TOLERANCE
                if old is not None and (crossed or close):
                    self.engaged[strip] = True
                    return "FADER_PICKUP_PASS"
                return "FADER_PICKUP_PENDING"
            if old == goal:
                return "FADER_NO_CHANGE"
            if abs(goal - host) > FADER_STEP_LIMIT or abs(goal - old) > FADER_STEP_LIMIT:
                self.engaged[strip] = False
                return "FADER_JUMP_REARM"
            # First outgoing fader value is only after authoritative host
            # position, explicit physical pickup, and limited movement.
            self.pending[strip] = goal, self.clock()
            if self.write:
                self.send("pitchwheel", channel=strip, pitch=goal - 8192)
                self.sent += 1
                return "MCU_FADER_SENT"
            self.pending[strip] = None
            self.engaged[strip] = False
            return "MCU_FADER_PREVIEW"
        if 21 <= cc <= 28 or 29 <= cc <= 36:
            if value not in (0, 127):
                return "BUTTON_IGNORED"
            if cc not in self.known_buttons:
                self.blocked += 1
                return "BUTTON_WAIT_FOR_FAIRLIGHT_LED"
            pressed = value == 127
            if self.pressed.get(cc, False) == pressed:
                return "BUTTON_DUPLICATE"
            self.pressed[cc] = pressed
            note = (16 + cc - 21) if cc <= 28 else (8 + cc - 29)
            if self.write:
                self.send("note_on" if pressed else "note_off",
                          channel=0, note=note, velocity=127 if pressed else 0)
                self.sent += 1
                return "MCU_BUTTON_SENT"
            return "MCU_BUTTON_PREVIEW"
        return "IGNORED"


def main():
    parser = argparse.ArgumentParser(description="Fairlight MCU bridge, observe-only by default")
    parser.add_argument("--list-midi-ports", action="store_true")
    parser.add_argument("--input-port", help="IAC port with Fairlight MCU output (feedback)")
    parser.add_argument("--output-port", help="IAC port wired to Resolve MCU input")
    parser.add_argument("--seconds", type=int, default=60, help="0 = until Ctrl+C")
    parser.add_argument("--enable-output", action="store_true")
    parser.add_argument("--consent")
    args = parser.parse_args()
    if args.seconds < 0 or args.seconds > 3600:
        parser.error("--seconds must be 0..3600")
    if args.enable_output and args.consent != CONSENT:
        parser.error("Explicit disposable-project consent required for MIDI writes")
    try:
        import mido
    except ImportError:
        print("MCU=BLOCKED; install mido + python-rtmidi in a local venv")
        return 1
    if args.list_midi_ports:
        print("MCU_INPUT_PORTS=", mido.get_input_names())
        print("MCU_OUTPUT_PORTS=", mido.get_output_names())
        return 0
    if not args.input_port or not args.output_port or args.input_port == args.output_port:
        parser.error("Two DISTINCT explicit IAC port names are required")
    if args.input_port not in mido.get_input_names():
        print("MCU=BLOCKED; feedback port not found", flush=True)
        return 1
    if args.output_port not in mido.get_output_names():
        print("MCU=BLOCKED; Resolve input port not found", flush=True)
        return 1
    if not SOURCE.is_file():
        print("MCU=BLOCKED; enable Scene2 Hammerspoon bridge first", flush=True)
        return 1

    count = 0
    with mido.open_input(args.input_port) as from_resolve, (
        mido.open_output(args.output_port) if args.enable_output else
        _NullOutput()
    ) as to_resolve, SOURCE.open("r", encoding="ascii") as events, (
        FEEDBACK.open("w", encoding="ascii")
    ) as feedback:
        events.seek(0, 2)
        source_stat = SOURCE.stat()
        def emit(kind, **kw):
            to_resolve.send(mido.Message(kind, **kw))
        def led(cc, value):
            feedback.write("%d,L,%d,%d\n" % (int(time.time()*1000), cc, value))
            feedback.flush()
        bridge = Bridge(emit, led, write=args.enable_output)
        started = time.monotonic()
        last_h = None
        last_heartbeat_out = 0
        ready = False
        print("MCU=START; mode=%s; 8 strip MCU; source Hammerspoon Scene2" %
              ("DISPOSABLE_WRITE" if args.enable_output else "READ_ONLY"), flush=True)
        try:
            while args.seconds == 0 or time.monotonic()-started < args.seconds:
                now = time.monotonic()
                if (now-last_heartbeat_out >= .5):
                    feedback.write("%d,H,0,1\n" % int(time.time()*1000))
                    feedback.flush()
                    last_heartbeat_out = now
                stat = SOURCE.stat()
                if ((stat.st_dev,stat.st_ino)!=(source_stat.st_dev,source_stat.st_ino)
                        or stat.st_size < events.tell()):
                    print("MCU=HALT; input bridge replaced", flush=True)
                    return 1
                for message in from_resolve.iter_pending():
                    bridge.host(message)
                lines = [events.readline() for _ in range(MAX_MESSAGES_PER_POLL)]
                lines = [line for line in lines if line]
                if len(lines) == MAX_MESSAGES_PER_POLL:
                    print("MCU=HALT; MIDI burst overflow",flush=True)
                    return 1
                for line in lines:
                    event = parse_event(line, int(time.time()*1000))
                    if event is None:
                        continue
                    kind,ch,cc,value = event
                    if kind == "H":
                        last_h = now
                        if not value:
                            ready = False
                            bridge.rearm()
                        else:
                            ready = True
                    elif kind == "R":
                        ready = False
                        bridge.rearm()
                    elif kind == "M" and ready:
                        result = bridge.physical_event(ch,cc,value)
                        if result not in ("IGNORED", "BUTTON_DUPLICATE", "FADER_NO_CHANGE"):
                            count += 1
                            if count <= 80 or count % 200 == 0:
                                print("MCU %s CH=%d CC=%d value=%d" %
                                      (result,ch,cc,value), flush=True)
                if last_h is None and now-started > 3:
                    print("MCU=HALT; no Hammerspoon heartbeat",flush=True)
                    return 1
                if last_h is not None and now-last_h > HEARTBEAT_TIMEOUT:
                    print("MCU=HALT; lost Hammerspoon heartbeat",flush=True)
                    return 1
                time.sleep(.02)
        except KeyboardInterrupt:
            print("MCU=STOP; Ctrl+C; TX=%d" % bridge.sent,flush=True)
        finally:
            feedback.write("%d,H,0,0\n" % int(time.time()*1000))
            feedback.flush()
        print("MCU=COMPLETE; output_messages=%d; blocked_events=%d" %
              (bridge.sent, bridge.blocked),flush=True)
    return 0


class _NullOutput:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def send(self, message):
        raise RuntimeError("observe-only mode must never send a MIDI command")


if __name__ == "__main__":
    sys.exit(main())
