#!/usr/bin/env python3
"""Opt-in, bounded Scene2 Assignable CC -> Fairlight MCU MIDI translator.

Source: existing Hammerspoon callback's five-column CSV (no second Korg
listener). Destination: a *separate*, explicitly named IAC output port;
return path: a separate IAC input port carrying actual Fairlight feedback.
Default mode is OBSERVE ONLY, with zero MIDI output.

MCU MIDI protocol (not clip gain): pitch bend ch0..7 = 8 mixer faders,
note 0x08..0x0F = solo and 0x10..0x17 = mute. Position/status MUST first
come from Fairlight; no MIDI write or invented Korg LED state without it.
Physical Scene2 faders use the observed Korg factory Assignable-mode CC map:
CC2,3,4,5,6,8,9,12 (not consecutive CC2..9). Mixer buttons unchanged.
"""
import argparse
from collections import Counter
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
# Fairlight requires a short fader TOUCH hold after the MIDI position.
# A working nanoKONTROL2 -> Fairlight translator uses 500 ms after motion.
ONE_SHOT_TOUCH_HOLD_SECONDS = 0.5
# Momentary MCU button tap uses host state, never hardware input LED echo.
ONE_SHOT_BUTTON_HOLD_SECONDS = 0.08
ONE_SHOT_BUTTONS = {"mute1": (21, 16), "solo1": (29, 8)}
# Korg/Scene1 CC32 is deliberately skipped (MIDI bank-select LSB).
# This eight-button pattern is in the verified existing Scene1 LED map;
# it must still be confirmed physically on Scene2 before MCU output.
SOLO_CC = (29, 30, 31, 33, 34, 35, 36, 37)
# Korg Kontrol Editor: same factory slider CC values in Scenes 1..5.
# Only Scene 2 (MIDI channel 1) routes these to the Fairlight MCU worker.
FADER_CCS = (2, 3, 4, 5, 6, 8, 9, 12)
FADER_CC_TO_STRIP = {cc: strip for strip, cc in enumerate(FADER_CCS)}

def parse_event(line, now_ms):
    parts = line.strip().split(",")
    if len(parts) != 5:
        return None
    try:
        timestamp, ch, cc, value = map(int, (parts[0], parts[2], parts[3], parts[4]))
    except ValueError:
        return None
    kind = parts[1]
    if (kind not in ("H", "R", "M", "B") or
        timestamp > now_ms or now_ms - timestamp > MAX_AGE_MS or
        not (0 <= ch <= 15 and 0 <= cc <= 127 and 0 <= value <= 127)):
        return None
    if kind == "H" and (ch,cc,value) not in ((0,0,0),(0,0,1)):
        return None
    if kind == "B" and not (ch == 1 and cc in (52,53)
                            and value in (0,127)):
        return None
    return kind, ch, cc, value


def physical_to_mcu(value):
    if type(value) is not int or not 0 <= value <= 127:
        raise ValueError("Korg physical fader must be 0..127")
    return round(value * 16383 / 127)


def classify_host_event(message):
    """Observability only; never interpret unexpected MIDI as fader state.

    This helper does NOT establish protocol authority. The original
    Bridge.host() remains the only MCU fader/button validator.
    """
    kind = getattr(message, "type", "")
    channel = getattr(message, "channel", None)
    if kind == "pitchwheel" and type(channel) is int and 0 <= channel < 8:
        pitch = getattr(message, "pitch", None)
        if type(pitch) is int and -8192 <= pitch <= 8191:
            return ("FADER", channel, pitch)
    if kind in ("note_on", "note_off") and channel == 0:
        note = getattr(message, "note", None)
        velocity = getattr(message, "velocity", None)
        if type(note) is int and 8 <= note <= 23 and (
                type(velocity) is int and 0 <= velocity <= 127):
            return ("MIXER_NOTE", note, velocity if kind == "note_on" else 0)
    if kind == "sysex":
        return ("SYSEX", 0, 0)
    return None


class Bridge:
    """Pure state machine; send(type, fields) and led(cc, state) are injected."""

    def __init__(self, send, led, *, write=False, clock=time.monotonic,
                 fader1_one_shot=False, one_shot_button=None):
        if one_shot_button is not None and one_shot_button not in ONE_SHOT_BUTTONS:
            raise ValueError("unsupported one-shot mixer button")
        if fader1_one_shot and one_shot_button:
            raise ValueError("one-shot fader and button trials are exclusive")
        self.send = send
        self.led = led
        self.write = write
        self.clock = clock
        self.fader1_one_shot = fader1_one_shot
        self.one_shot_button = one_shot_button
        self.ack_received = 0
        self.ack_mismatch = 0
        self.host_after_command = 0
        self.host_faders = [None] * 8
        self.host_fader_time = [None] * 8
        self.physical = [None] * 8
        self.engaged = [False] * 8
        self.pending = [None] * 8
        self.known_buttons = {}
        self.button_host_time = {}
        self.pressed = {}
        self.one_button_pressed = False
        self.one_button_release_at = None
        self.one_button_initial = None
        self.one_button_expected = None
        self.one_button_observed = False
        self.sent = 0
        self.blocked = 0
        self.touch_active = False
        self.touch_release_at = None
        self.one_shot_host_before = None
        self.one_shot_target = None

    def release_touch(self, *, force=False):
        """Release the A1 MCU touch only once, on time or on shutdown/fault."""
        if not self.touch_active:
            return False
        if (not force and self.touch_release_at is not None
                and self.clock() < self.touch_release_at):
            return False
        try:
            self.send("note_on", channel=0, note=104, velocity=0)
        finally:
            self.touch_active = False
            self.touch_release_at = None
        return True

    def release_one_button(self, *, force=False):
        """Release an MCU one-shot mixer key exactly once; no second press."""
        if not self.one_button_pressed:
            return False
        if (not force and self.one_button_release_at is not None
                and self.clock() < self.one_button_release_at):
            return False
        _, note = ONE_SHOT_BUTTONS[self.one_shot_button]
        try:
            self.send("note_off", channel=0, note=note, velocity=0)
        finally:
            self.one_button_pressed = False
            self.one_button_release_at = None
        return True

    def rearm(self):
        # Focus/scene reset must not leave the MCU fader touched or a key down.
        self.release_touch(force=True)
        self.release_one_button(force=True)
        self.physical = [None] * 8
        self.engaged = [False] * 8
        self.pending = [None] * 8
        self.known_buttons = {}
        self.button_host_time = {}
        self.pressed = {}
        self.host_faders = [None] * 8
        self.host_fader_time = [None] * 8

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
                self.host_after_command += 1
                if abs(expected[0] - value) <= ACK_TOLERANCE:
                    self.ack_received += 1
                    self.pending[channel] = None
                else:
                    self.ack_mismatch += 1
                    self.engaged[channel] = False
                    # Intermediate host feedback (or a queued earlier
                    # update) is NOT authoritative rejection of the
                    # one-shot command. Keep listening through touch hold.
                    # No further send is possible: self.sent stays 1.
                    if not self.fader1_one_shot:
                        self.pending[channel] = None
            elif (self.engaged[channel] and self.host_faders[channel] is not None
                  and abs(value - self.host_faders[channel]) > FADER_PICKUP_TOLERANCE):
                self.engaged[channel] = False
            self.host_faders[channel] = value
            self.host_fader_time[channel] = self.clock()
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
            cc = SOLO_CC[note - 8] if note < 16 else (note - 16 + 21)
            self.known_buttons[cc] = on
            self.button_host_time[cc] = self.clock()
            if self.one_shot_button and self.sent == 1:
                selected_cc, _ = ONE_SHOT_BUTTONS[self.one_shot_button]
                if cc == selected_cc and on == self.one_button_expected:
                    self.one_button_observed = True
            self.led(cc, 127 if on else 0)

    def physical_event(self, ch, cc, value):
        if ch != 1:
            self.rearm()
            return "SCENE_REARM"
        if type(value) is not int or not 0 <= value <= 127:
            return "INVALID"
        if self.one_shot_button:
            chosen_cc, note = ONE_SHOT_BUTTONS[self.one_shot_button]
            if cc != chosen_cc:
                return "ONE_SHOT_BUTTON_ONLY"
            if self.sent >= 1:
                return "ONE_SHOT_ALREADY_SENT"
            if value != 127:
                return "ONE_SHOT_WAIT_PRESS"
            last = self.button_host_time.get(chosen_cc)
            if last is None or self.clock() - last > 10.0:
                self.blocked += 1
                return "BUTTON_HOST_STATE_STALE"
            before = self.known_buttons.get(chosen_cc)
            if before is None:
                self.blocked += 1
                return "BUTTON_WAIT_FOR_FAIRLIGHT_LED"
            self.one_button_initial = before
            self.one_button_expected = not before
            if self.write:
                # Exactly one host-known toggle. The physical release
                # cannot send another MIDI command; timer releases the
                # momentary MCU key once even if Korg sends extra CCs.
                self.one_button_pressed = True
                try:
                    self.send("note_on", channel=0, note=note, velocity=127)
                    self.sent += 1
                    self.one_button_release_at = (
                        self.clock() + ONE_SHOT_BUTTON_HOLD_SECONDS)
                except BaseException:
                    self.release_one_button(force=True)
                    raise
                return "MCU_BUTTON_ONE_SHOT_SENT"
            return "MCU_BUTTON_ONE_SHOT_PREVIEW"
        # Explicit physical acceptance: all other Scene2 sliders and buttons
        # are blocked, even if the operator accidentally presses them.
        if self.fader1_one_shot and cc != 2:
            return "ONE_SHOT_FADER1_ONLY"
        if self.fader1_one_shot and self.sent >= 1:
            return "ONE_SHOT_ALREADY_SENT"
        if cc in FADER_CC_TO_STRIP:
            strip = FADER_CC_TO_STRIP[cc]
            goal = physical_to_mcu(value)
            old = self.physical[strip]
            self.physical[strip] = goal
            host = self.host_faders[strip]
            if self.fader1_one_shot:
                last = self.host_fader_time[strip]
                if last is None or self.clock() - last > 10.0:
                    self.engaged[strip] = False
                    self.host_faders[strip] = None
                    self.host_fader_time[strip] = None
                    return "FADER_HOST_FEEDBACK_STALE_REARM"
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
                # A duplicate or stale CC must NEVER arm a mixer fader.
                # Physical movement is mandatory after authoritative host
                # state becomes known (even when positions happen to match).
                if old is not None and old != goal and (crossed or close):
                    self.engaged[strip] = True
                    return "FADER_PICKUP_PASS"
                return "FADER_PICKUP_PENDING"
            if old == goal:
                return "FADER_NO_CHANGE"
            if abs(goal - host) > FADER_STEP_LIMIT or abs(goal - old) > FADER_STEP_LIMIT:
                self.engaged[strip] = False
                return "FADER_JUMP_REARM"
            # First physical acceptance is additionally limited to ~2 Korg
            # steps from BOTH last host position and last physical position.
            if self.fader1_one_shot and (
                    abs(goal - host) > FADER_PICKUP_TOLERANCE or
                    abs(goal - old) > FADER_PICKUP_TOLERANCE):
                self.engaged[strip] = False
                return "ONE_SHOT_STEP_REARM"
            # First outgoing fader value is only after authoritative host
            # position, explicit physical pickup, and limited movement.
            self.pending[strip] = goal, self.clock()
            if self.write:
                if self.fader1_one_shot:
                    # Real MCU touch-sensitive faders signal the start and
                    # end of a gesture. Fairlight's proven Korg translators
                    # hold TOUCH for ~500 ms following the last fader move.
                    # Emit exactly ONE position, keep touch briefly held,
                    # and send release from the bounded main loop; failures
                    # force an immediate release in this exception path.
                    self.one_shot_host_before = host
                    self.one_shot_target = goal
                    try:
                        self.send("note_on", channel=0, note=104, velocity=127)
                        self.touch_active = True
                        self.send("pitchwheel", channel=0, pitch=goal - 8192)
                        self.sent += 1
                        self.touch_release_at = (
                            self.clock() + ONE_SHOT_TOUCH_HOLD_SECONDS)
                    except BaseException:
                        self.release_touch(force=True)
                        raise
                    return "MCU_FADER_TOUCH_SENT"
                self.send("pitchwheel", channel=strip, pitch=goal - 8192)
                self.sent += 1
                return "MCU_FADER_SENT"
            self.pending[strip] = None
            self.engaged[strip] = False
            return "MCU_FADER_PREVIEW"
        if 21 <= cc <= 28 or cc in SOLO_CC:
            if value not in (0, 127):
                return "BUTTON_IGNORED"
            if cc not in self.known_buttons:
                self.blocked += 1
                return "BUTTON_WAIT_FOR_FAIRLIGHT_LED"
            pressed = value == 127
            if self.pressed.get(cc, False) == pressed:
                return "BUTTON_DUPLICATE"
            self.pressed[cc] = pressed
            note = (16 + cc - 21) if cc <= 28 else (8 + SOLO_CC.index(cc))
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
    parser.add_argument("--one-shot-fader1-test", action="store_true",
                        help="single A1 fader adjustment, no other strips/buttons")
    parser.add_argument("--one-shot-button", choices=tuple(ONE_SHOT_BUTTONS),
                        help="one A1 MUTE or SOLO press/release, not fader")
    parser.add_argument("--consent")
    args = parser.parse_args()
    if args.seconds < 0 or args.seconds > 3600:
        parser.error("--seconds must be 0..3600")
    if args.enable_output and args.consent != CONSENT:
        parser.error("Explicit disposable-project consent required for MIDI writes")
    if args.one_shot_fader1_test and args.one_shot_button:
        parser.error("Choose fader1 OR one button, not both")
    any_trial = args.one_shot_fader1_test or bool(args.one_shot_button)
    if args.enable_output and not any_trial:
        parser.error("MIDI writes require --one-shot-fader1-test OR "
                     "--one-shot-button; unbounded output disabled in Draft")
    if any_trial and not args.enable_output:
        parser.error("Any one-shot trial requires --enable-output")
    if any_trial and (args.seconds == 0 or args.seconds > 60):
        parser.error("One-shot hardware trial must finish within 60 seconds")
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
        bridge = Bridge(emit, led, write=args.enable_output,
                        fader1_one_shot=args.one_shot_fader1_test,
                        one_shot_button=args.one_shot_button)
        started = time.monotonic()
        one_shot_sent_at = None
        one_button_sent_at = None
        last_h = None
        last_heartbeat_out = 0
        ready = False
        rx_counts = Counter()
        physical_counts = Counter()
        host_fader_seen = set()
        host_button_seen = set()
        printed_statuses = set()
        source_resets = Counter()
        print("MCU=START; mode=%s; 8 strip MCU; source Hammerspoon Scene2" %
              ("DISPOSABLE_WRITE" if args.enable_output else "READ_ONLY"), flush=True)
        if args.one_shot_button:
            cc, note = ONE_SHOT_BUTTONS[args.one_shot_button]
            print("MCU_BUTTON_ONE_SHOT_ARMED=%s; physical CC%d -> "
                  "MCU note%d; one 80ms press/release only; "
                  "all other controls BLOCKED; fresh Fairlight LED needed" %
                  (args.one_shot_button, cc, note), flush=True)
        if args.one_shot_fader1_test:
            print("MCU_ONE_SHOT_ARMED=one A1 adjustment ONLY: "
                  "note_on(104,127) + pitchbend(ch0) + 500ms held touch "
                  "+ note_on(104,0); "
                  "no other mixer strips/buttons, no retries; "
                  "Verify STOPPED playback, NO AUTOMATION and disposable project",
                  flush=True)
        else:
            print("MCU_DIAG=ACTIVE; first move Fairlight UI fader and MUTE/SOLO "
                  "while this process runs; then move Korg Scene2 fader/button; "
                  "READ_ONLY never transmits", flush=True)
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
                    rx_counts[message.type] += 1
                    info = classify_host_event(message)
                    if info and info[0] == "FADER" and info[1] not in host_fader_seen:
                        host_fader_seen.add(info[1])
                        print("MCU_RX_FADER=PASS; channel=%d; pitch=%d; "
                              "received while bridge running" %
                              (info[1], info[2]), flush=True)
                    elif info and info[0] == "MIXER_NOTE" and (
                            info[1] not in host_button_seen):
                        host_button_seen.add(info[1])
                        print("MCU_RX_BUTTON=PASS; note=%d; velocity=%d" %
                              (info[1], info[2]), flush=True)
                    elif info and info[0] == "SYSEX" and rx_counts["sysex"] == 1:
                        print("MCU_RX_SYSEX=OBSERVED; no fader authority implied",
                              flush=True)
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
                            if ready:
                                source_resets["focus"] += 1
                                print("MCU_SOURCE=FOCUS_LOST; host fader pickup "
                                      "cleared; switch back to Resolve and move "
                                      "UI fader again", flush=True)
                            ready = False
                            bridge.rearm()
                        else:
                            if not ready:
                                print("MCU_SOURCE=RESOLVE_READY; wait for fresh "
                                      "on-screen Fairlight fader feedback",
                                      flush=True)
                            ready = True
                    elif kind == "R":
                        source_resets["scene"] += 1
                        print("MCU_SOURCE=SCENE_CHANGED; physical channel=%d; "
                              "host fader pickup cleared" % ch, flush=True)
                        ready = False
                        bridge.rearm()
                    elif kind == "M" and ready:
                        result = bridge.physical_event(ch,cc,value)
                        physical_counts[result] += 1
                        if result not in ("IGNORED", "BUTTON_DUPLICATE", "FADER_NO_CHANGE"):
                            count += 1
                            # Show each distinct fader state once per strip,
                            # and EACH button transition. Old first-80 limit
                            # concealed real MUTE/SOLO activity under CC flood.
                            display_key = (cc, result)
                            display = (result.startswith("BUTTON_") or
                                       result.startswith("MCU_BUTTON_") or
                                       display_key not in printed_statuses)
                            printed_statuses.add(display_key)
                            if display:
                                print("MCU %s CH=%d CC=%d value=%d" %
                                      (result,ch,cc,value), flush=True)
                # Scheduled RELEASEs are independent of further Korg events.
                # Finalizer releases on Ctrl+C, focus loss and exceptions.
                bridge.release_touch()
                bridge.release_one_button()
                if args.one_shot_button and bridge.sent > 0:
                    if one_button_sent_at is None:
                        one_button_sent_at = now
                        print("MCU_BUTTON_ONE_SHOT_SENT=%s; before=%s; "
                              "expected_after=%s" %
                              (args.one_shot_button,
                               bridge.one_button_initial,
                               bridge.one_button_expected), flush=True)
                    if not bridge.one_button_pressed and bridge.one_button_observed:
                        print("MCU_BUTTON_ONE_SHOT=HOST_STATE_CHANGED_PASS; "
                              "host note changed; inspect LED and Fairlight UI",
                              flush=True)
                        break
                    if now - one_button_sent_at > 1.5:
                        print("MCU_BUTTON_ONE_SHOT=NO_MATCHING_HOST_FEEDBACK; "
                              "may have changed without echoed note; inspect "
                              "Fairlight UI before any retry", flush=True)
                        break
                if args.one_shot_fader1_test and bridge.sent > 0:
                    if one_shot_sent_at is None:
                        one_shot_sent_at = now
                        print("MCU_ONE_SHOT_SEND=host_before:%.1f,goal:%.1f; "
                              "touch held %.0fms" %
                              (bridge.one_shot_host_before * 127 / 16383,
                               bridge.one_shot_target * 127 / 16383,
                               ONE_SHOT_TOUCH_HOLD_SECONDS * 1000),
                              flush=True)
                    if bridge.ack_received > 0 and not bridge.touch_active:
                        print("MCU_ONE_SHOT=HOST_ACK_PASS; "
                              "A1 target echoed, touch safely released",
                              flush=True)
                        break
                    # Do not treat the FIRST nonmatching MCU feedback as
                    # rejection; a delayed/queued intermediate position
                    # might arrive before the eventual target position.
                    if now-one_shot_sent_at > 1.5:
                        if bridge.host_after_command == 0:
                            print("MCU_ONE_SHOT=NO_POST_SEND_FADER_FEEDBACK; "
                                  "STOP; MCU does not necessarily echo "
                                  "hardware fader movements; inspect mixer "
                                  "A1 visually", flush=True)
                        else:
                            print("MCU_ONE_SHOT=NO_MATCHING_HOST_ACK; "
                                  "STOP; inspect mixer A1 visually", flush=True)
                        break
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
            # Guaranteed best-effort MCU TOUCH release when stopped by
            # focus loss, Ctrl+C, source replacement or other exception.
            try:
                if bridge.release_touch(force=True):
                    print("MCU_ONE_SHOT=FORCED_TOUCH_RELEASE", flush=True)
            except Exception as exc:
                print("MCU_ONE_SHOT=TOUCH_RELEASE_FAILED; restart Resolve "
                      "before further MIDI writes; error=%s" % exc,
                      flush=True)
            try:
                if bridge.release_one_button(force=True):
                    print("MCU_BUTTON_ONE_SHOT=FORCED_KEY_RELEASE", flush=True)
            except Exception as exc:
                print("MCU_BUTTON_ONE_SHOT=KEY_RELEASE_FAILED; restart Resolve "
                      "before further MIDI writes; error=%s" % exc,
                      flush=True)
            feedback.write("%d,H,0,0\n" % int(time.time()*1000))
            feedback.flush()
        print("MCU=COMPLETE; fader_adjustments=%d; blocked_events=%d; "
              "post_send_pitchwheel_rx=%d; nonmatching_host_updates=%d" %
              (bridge.sent, bridge.blocked, bridge.host_after_command,
               bridge.ack_mismatch), flush=True)
        if bridge.one_shot_target is not None:
            current = bridge.host_faders[0]
            print("MCU_ONE_SHOT_POSITIONS=before:%.1f,target:%.1f,last_rx:%s" %
                  (bridge.one_shot_host_before * 127 / 16383,
                   bridge.one_shot_target * 127 / 16383,
                   "unknown" if current is None else "%.1f" %
                   (current * 127 / 16383)), flush=True)
        if bridge.one_shot_button and bridge.sent == 1:
            selected_cc, _ = ONE_SHOT_BUTTONS[bridge.one_shot_button]
            print("MCU_BUTTON_ONE_SHOT_RESULT=%s; before:%s; expected:%s; "
                  "last_host:%s; fresh_host_confirmed:%s" %
                  (bridge.one_shot_button,
                   bridge.one_button_initial,
                   bridge.one_button_expected,
                   bridge.known_buttons.get(selected_cc),
                   bridge.one_button_observed), flush=True)
        print("MCU_DIAG_HOST_RX=" +
              ",".join("%s:%d" % (k,rx_counts[k])
                       for k in sorted(rx_counts)), flush=True)
        print("MCU_DIAG_PHYSICAL=" +
              ",".join("%s:%d" % (k,physical_counts[k])
                       for k in sorted(physical_counts)), flush=True)
        print("MCU_DIAG_RESETS=focus:%d,scene:%d; "
              "CURRENT_HOST_FADERS=%s; CURRENT_KNOWN_BUTTONS=%s" %
              (source_resets["focus"], source_resets["scene"],
               [None if x is None else round(x/16383*127, 1)
                for x in bridge.host_faders],
               sorted(bridge.known_buttons)), flush=True)
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
