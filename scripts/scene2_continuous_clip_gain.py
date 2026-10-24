#!/usr/bin/env python3
"""Long-running, opt-in Scene 2 rotary -> Resolve *clip* AudioVolume bridge.

Default READ_ONLY. Writable mode is restricted to an explicitly named,
backed-up disposable test project without gain keyframes/automation.
Hammerspoon's existing MIDI callback is the sole input owner; its optional
Scene 2 bridge publishes timestamped local input events and 0.5 s heartbeats.
This script never claims to change Fairlight MIXER track faders or mute/solo.
"""
import argparse
import pathlib
import sys
import time

import scene2_audio_roundtrip_probe as api
from scene2_clip_gain_8rotary import (
    CONSENT, Controller, MidiPoll, process_poll, snapshot,
)

EVENT_PATH = pathlib.Path.home() / "Library/Caches/nk-scene2-controller-events.csv"
POLL_SECONDS = 0.20
HEARTBEAT_TIMEOUT = 2.5
STARTUP_TIMEOUT = 5.0
MAX_INPUT_AGE_MS = 1200
MAX_BATCH_LINES = 2048
IDLE_REARM_SECONDS = 20.0


def parse_bridge_row(line, now_ms):
    """Reject stale/future/malformed events, not just unsupported CCs."""
    parts = line.strip().split(",")
    if len(parts) != 5:
        return None
    ts, kind, ch, cc, val = parts
    try:
        ts, ch, cc, val = int(ts), int(ch), int(cc), int(val)
    except ValueError:
        return None
    if kind not in ("H", "C", "R"):
        return None
    if not 0 <= now_ms - ts <= MAX_INPUT_AGE_MS:
        return None
    if kind == "H":
        return ("H", val) if ch == 0 and cc == 0 and val in (0, 1) else None
    if kind == "R":
        return ("R", ch, cc, val) if 0 <= ch <= 15 else None
    if not (0 <= ch <= 15 and 0 <= cc <= 127 and 0 <= val <= 127):
        return None
    return ("C", ch, cc, val)


class ContinuousController(Controller):
    """Retain the proven setter/readback, but rearm on clip/playhead/scene.

    The one-shot Controller correctly HALTS on an unexpected playhead move.
    A persistent editing session must instead forget *all* pickup positions,
    then demand a new physical crossing at the new location. It must never
    reuse a pre-switch A4/A5 physical position or inferred gain.
    """
    def __init__(self, app, *, write=False, expected_project=None,
                 confirmation=None, automation_confirmed=False,
                 max_writes=256, now=time.monotonic):
        super().__init__(
            app, write=write, expected_project=expected_project,
            confirmation=confirmation,
            automation_confirmed=automation_confirmed,
            max_writes=max_writes, max_writes_limit=256, now=now,
        )
        self.pause_reason = None

    def rearm(self, reason):
        self.engine.reset()
        self.last_event = None
        self.session = None
        if self.pause_reason != reason:
            print("SCENE2_CONTINUOUS=REARM; %s; verified_writes=%d" %
                  (reason, self.writes), flush=True)
        self.pause_reason = reason

    def handle(self, channel, cc, value):
        if self.halted:
            return "HALTED"
        if channel != 1:
            self.rearm("different MIDI scene")
            return "RESET"
        if not 13 <= cc <= 20:
            return "IGNORED"
        now = self.now()
        if (self.last_event is not None and
                now - self.last_event > IDLE_REARM_SECONDS):
            self.rearm("inactive for 20 seconds")
        if self.session is not None:
            # Read context *before* delegating to the original setter gate.
            # That gate obtains an independent fresh snapshot and checks
            # everything again at the exact setter call.
            try:
                fresh, _, session = snapshot(self.app, cc - 12)
            except api.ProbeBlocked:
                self.engine.reject(cc - 12)
                return super().handle(channel, cc, value)
            if self.write and fresh["project"] != self.expected_project:
                return self._halt("project is not exact approved test copy")
            if session != self.session:
                self.rearm("project/timeline/playhead changed")
        # Parent's short 2s *research* rearm is too aggressive for actual
        # editing; we have already implemented a separate 20s safe timeout.
        self.last_event = self.now()
        self.pause_reason = None
        return super().handle(channel, cc, value)


def monitor(controller, *, event_path=EVENT_PATH, seconds=0,
            clock=time.monotonic, wall=time.time, sleep=time.sleep):
    if not event_path.is_file():
        print("SCENE2_CONTINUOUS=BLOCKED; enable integrated Hammerspoon bridge; "
              "VERIFIED_WRITES=0", flush=True)
        return 1
    with event_path.open("r", encoding="ascii", errors="replace") as stream:
        # Previous bridge events are NOT commands for a new Python session.
        stream.seek(0, 2)
        initial = event_path.stat()
        started = clock()
        last_heartbeat = None
        ready = False
        pending = MidiPoll()
        next_poll = started
        end_at = started + seconds if seconds else None
        print("SCENE2_CONTINUOUS=START; mode=%s; CC13..20=A1..A8; "
              "max_writes=%d; stopped_playhead_required=True" %
              ("TEST_COPY_WRITE" if controller.write else "READ_ONLY",
               controller.max_writes if controller.write else 0), flush=True)
        try:
            while end_at is None or clock() < end_at:
                try:
                    current = event_path.stat()
                    if ((current.st_dev, current.st_ino) !=
                            (initial.st_dev, initial.st_ino) or
                            current.st_size < stream.tell()):
                        print("SCENE2_CONTINUOUS=BLOCKED; bridge restarted; "
                              "stop and rearm explicitly", flush=True)
                        return 1
                    lines = []
                    for _ in range(MAX_BATCH_LINES):
                        line = stream.readline()
                        if not line:
                            break
                        lines.append(line)
                    if len(lines) >= MAX_BATCH_LINES:
                        print("SCENE2_CONTINUOUS=BLOCKED; MIDI input flood; "
                              "STOP ALL WRITES", flush=True)
                        return 1
                except OSError:
                    print("SCENE2_CONTINUOUS=BLOCKED; bridge file missing",
                          flush=True)
                    return 1
                saw_reset = False
                for line in lines:
                    event = parse_bridge_row(line, int(wall() * 1000))
                    if event is None:
                        continue
                    if event[0] == "H":
                        last_heartbeat = clock()
                        if event[1] == 0:
                            if ready:
                                controller.rearm("Resolve not frontmost / bridge paused")
                            ready = False
                            saw_reset = True
                        else:
                            ready = True
                    elif event[0] == "R":
                        saw_reset = True
                        controller.rearm("other Korg scene selected")
                    elif event[0] == "C" and ready and not saw_reset:
                        _, ch, cc, value = event
                        pending.add("%d,%d,%d" % (ch, cc, value))
                if saw_reset:
                    pending = MidiPoll()  # no same-poll writes across scene/focus
                if (last_heartbeat is None and clock() - started > STARTUP_TIMEOUT):
                    print("SCENE2_CONTINUOUS=BLOCKED; no bridge heartbeat",
                          flush=True)
                    return 1
                if (last_heartbeat is not None and
                        clock() - last_heartbeat > HEARTBEAT_TIMEOUT):
                    controller.rearm("MIDI bridge heartbeat lost")
                    print("SCENE2_CONTINUOUS=BLOCKED; stale heartbeat; "
                          "STOP ALL WRITES", flush=True)
                    return 1
                if clock() >= next_poll:
                    next_poll = clock() + POLL_SECONDS
                    if ready and (pending.events or pending.foreign is not None):
                        if process_poll(controller, pending) == "HALTED":
                            print("SCENE2_CONTINUOUS=STOPPED; VERIFIED_WRITES=%d" %
                                  controller.writes, flush=True)
                            return 0 if (controller.writes ==
                                         controller.max_writes) else 1
                        pending = MidiPoll()
                    elif not ready:
                        pending = MidiPoll()
                sleep(0.04)
        except KeyboardInterrupt:
            print("SCENE2_CONTINUOUS=STOPPED; Ctrl+C; VERIFIED_WRITES=%d" %
                  controller.writes, flush=True)
            return 0
    print("SCENE2_CONTINUOUS=COMPLETE; VERIFIED_WRITES=%d" %
          controller.writes, flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Continuous Scene 2 clip gain; READ_ONLY by default")
    parser.add_argument("--seconds", type=int, default=0,
                        help="0 = until Ctrl+C; otherwise 5..3600")
    parser.add_argument("--write-test-copy", action="store_true")
    parser.add_argument("--expected-project")
    parser.add_argument("--confirmed-no-automation", action="store_true")
    parser.add_argument("--consent")
    parser.add_argument("--max-writes", type=int, default=256,
                        help="1..256 verified edits across all eight knobs")
    args = parser.parse_args()
    if args.seconds != 0 and not 5 <= args.seconds <= 3600:
        parser.error("--seconds must be 0 or 5..3600")
    if not 1 <= args.max_writes <= 256:
        parser.error("--max-writes must be 1..256")
    try:
        import DaVinciResolveScript as dvr
        app = dvr.scriptapp("Resolve")
    except (ImportError, OSError):
        print("SCENE2_CONTINUOUS=BLOCKED; Resolve Python unavailable; WRITES=0")
        return 1
    if app is None:
        print("SCENE2_CONTINUOUS=BLOCKED; Resolve not running; WRITES=0")
        return 1
    try:
        controller = ContinuousController(
            app, write=args.write_test_copy,
            expected_project=args.expected_project,
            confirmation=args.consent,
            automation_confirmed=args.confirmed_no_automation,
            max_writes=args.max_writes,
        )
    except ValueError as exc:
        print("SCENE2_CONTINUOUS=BLOCKED; %s; WRITES=0" % exc)
        return 1
    return monitor(controller, seconds=args.seconds)


if __name__ == "__main__":
    sys.exit(main())
