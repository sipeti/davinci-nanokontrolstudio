#!/usr/bin/env python3
"""Long-running, opt-in Scene 2 rotary -> Resolve *clip* AudioVolume bridge.

Default READ_ONLY. Writable mode needs an explicitly named project,
a confirmed backup, stopped playback and no gain keyframes/automation.
Non-test projects require a separate per-session opt-in.
Hammerspoon's existing MIDI callback is the sole input owner; its optional
Scene 2 bridge publishes timestamped local input events and 0.5 s heartbeats.
This script never claims to change Fairlight MIXER track faders or mute/solo.
"""
import argparse
import fcntl
import pathlib
import sys
import time

import scene2_audio_roundtrip_probe as api
from scene2_clip_gain_8rotary import (
    CONSENT, NAMED_CONSENT, Controller, MidiPoll, process_poll, snapshot,
)
from fairlight_mcu_bridge import FEEDBACK

EVENT_PATH = pathlib.Path.home() / "Library/Caches/nk-scene2-controller-events.csv"
LIVE_LOCK = pathlib.Path.home() / "Library/Caches/nk-scene2-clip-live.lock"
POLL_SECONDS = 0.20
FAST_POLL_SECONDS = 0.02
FAST_IDLE_SLEEP_SECONDS = 0.005
HEARTBEAT_TIMEOUT = 2.5
STARTUP_TIMEOUT = 5.0
MAX_INPUT_AGE_MS = 1200
MAX_BATCH_LINES = 2048
IDLE_REARM_SECONDS = 20.0
BANK_FEEDBACK_MAX_AGE_MS = 1600


def read_bank_feedback(path, now_ms):
    """Last fresh MCU-generated bank status from the existing LED CSV."""
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 2048))
            data = f.read()
    except OSError:
        return None
    if size > 2048:
        data = data.partition(b"\n")[2]
    for row in reversed(data.splitlines()):
        parts = row.split(b",")
        if len(parts) != 4 or parts[1] != b"B":
            continue
        try:
            stamp, bank, status = int(parts[0]), int(parts[2]), int(parts[3])
        except ValueError:
            continue
        if (0 <= now_ms - stamp <= BANK_FEEDBACK_MAX_AGE_MS
                and bank in (0, 1) and status in (0, 1, 2)):
            return bank, status
    return None


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
    if kind not in ("H", "C", "R", "B"):
        return None
    if not 0 <= now_ms - ts <= MAX_INPUT_AGE_MS:
        return None
    if kind == "H":
        return ("H", val) if ch == 0 and cc == 0 and val in (0, 1) else None
    if kind == "R":
        return ("R", ch, cc, val) if 0 <= ch <= 15 else None
    if kind == "B":
        return ("B", cc) if ch == 1 and cc in (52, 53) and val == 127 else None
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
                 max_writes=256, now=time.monotonic,
                 stability_wait=time.sleep, low_latency=False,
                 allow_named_project=False, follow_active_project=False,
                 follow_mcu_bank=False):
        super().__init__(
            app, write=write, expected_project=expected_project,
            confirmation=confirmation,
            automation_confirmed=automation_confirmed,
            max_writes=max_writes, max_writes_limit=256, now=now,
            allow_unlimited=(max_writes == 0),
            allow_named_project=allow_named_project,
            follow_active_project=follow_active_project,
        )
        self.pause_reason = None
        self.stability_wait = stability_wait
        self.low_latency = bool(low_latency)
        self.follow_mcu_bank = bool(follow_mcu_bank)
        self.bank_index = 0
        self.track_offset = 0
        self.bank_ready = not self.follow_mcu_bank
        self.bank_request_target = None

    def update_bank(self, state):
        """Disarm each rotary on every bank change or unknown host bank."""
        bank, status = state if state is not None else (self.bank_index, 2)
        ready = status == 1
        # Never re-enable an old bank from a still-fresh MCU heartbeat
        # while a new SELECT7/8 command has not been acknowledged.
        if ready and self.bank_request_target is not None:
            if bank != self.bank_request_target:
                return False
            self.bank_request_target = None
        if bank != self.bank_index or ready != self.bank_ready:
            self.rearm("MCU bank %d status %d" % (bank + 1, status))
            self.bank_index = bank
            self.track_offset = bank * 8
            self.bank_ready = ready
            print("SCENE2_BANK=%s; A%d-A%d" %
                  ("ACTIVE" if ready else "WAIT_HOST",
                   1 + self.track_offset, 8 + self.track_offset),
                  flush=True)
            return True
        return False

    def _write(self, track, before, identity, requested):
        if self.follow_mcu_bank:
            state = read_bank_feedback(FEEDBACK, int(time.time() * 1000))
            if state != (self.bank_index, 1) or not self.bank_ready:
                self.rearm("bank changed immediately before setter")
                self.bank_ready = False
                return "BLOCKED"
        # Normal mode retains the 120ms independent stationary-playhead
        # observation. Explicit low-latency test mode omits that timer and
        # extra full snapshot, but NEVER bypasses the inherited setter-bound
        # fresh snapshot, project/clip/frame validation or post-setter readback.
        # Fast mode is restricted by the existing test-copy consent gate.
        if not self.low_latency:
            self.stability_wait(0.12)
            try:
                fresh, fresh_identity, fresh_session = snapshot(self.app, track)
            except api.ProbeBlocked:
                return self._halt("playhead/clip unavailable in stability window")
            if (fresh["key"] != before["key"] or
                    fresh_identity != identity or
                    fresh_session != self.session):
                self.engine.reject(track)
                return self._halt("playhead/clip/gain moved during stability window")
        return super()._write(track, before, identity, requested)

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
        if not self.bank_ready:
            return "BANK_WAIT_HOST"
        if channel != 1:
            self.rearm("different MIDI scene")
            return "RESET"
        if not 13 <= cc <= 20:
            return "IGNORED"
        now = self.now()
        if (self.last_event is not None and
                now - self.last_event > IDLE_REARM_SECONDS):
            self.rearm("inactive for 20 seconds")
        start = time.perf_counter()
        # Reuse this authoritative snapshot in the parent's feed: the old
        # version queried the SAME full project/track/clip twice per CC.
        # A fresh, separate snapshot still runs IMMEDIATELY before each
        # actual setter and again after it, inside the inherited _write().
        try:
            track = cc - 12 + self.track_offset
            current = snapshot(self.app, track)
        except api.ProbeBlocked:
            track = cc - 12 + self.track_offset
            self.engine.reject(track)
            return super().handle(channel, cc, value)
        snapshot_ms = (time.perf_counter() - start) * 1000.0
        fresh, _, session = current
        if self.follow_active_project:
            # A project/timeline change always drops the previous pickup.
            # The first CC in the new project can arm only, never reuse
            # the old clip or position. The setter checks a fresh snapshot
            # immediately before writing, including the project identity.
            if self.session is not None and session != self.session:
                self.rearm("project/timeline/playhead changed")
            self.expected_project = fresh["project"]
        else:
            if self.write and fresh["project"] != self.expected_project:
                return self._halt("project is not exact approved test copy")
            if self.session is not None and session != self.session:
                self.rearm("project/timeline/playhead changed")
        # Parent's 2s research idle reset is superseded by our 20s timer.
        self.last_event = self.now()
        self.pause_reason = None
        result = super().handle(channel, cc, value, preloaded=current)
        if self.low_latency and self.write and self.writes and self.writes % 10 == 0 and result == "WRITTEN":
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            print("SCENE2_FAST_TIMING=handler_ms:%.1f,pre_snapshot_ms:%.1f,writes:%d" %
                  (elapsed_ms, snapshot_ms, self.writes), flush=True)
        return result


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
        next_bank_check = started
        poll_seconds = FAST_POLL_SECONDS if controller.low_latency else POLL_SECONDS
        idle_sleep = FAST_IDLE_SLEEP_SECONDS if controller.low_latency else 0.04
        end_at = started + seconds if seconds else None
        print("SCENE2_CONTINUOUS=START; mode=%s; CC13..20=A1..A8; "
              "max_writes=%d; poll_ms=%d; low_latency=%s; "
              "stopped_playhead_required=True" %
              ("TEST_COPY_WRITE" if controller.write else "READ_ONLY",
               controller.max_writes if controller.write else 0,
               int(poll_seconds * 1000), controller.low_latency), flush=True)
        try:
            while end_at is None or clock() < end_at:
                if controller.follow_mcu_bank and clock() >= next_bank_check:
                    next_bank_check = clock() + 0.10
                    if controller.update_bank(
                        read_bank_feedback(FEEDBACK, int(wall() * 1000))):
                        pending = MidiPoll()
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
                    elif event[0] == "B" and controller.follow_mcu_bank:
                        # Hard fence *before* the MCU's asynchronous host ACK.
                        saw_reset = True
                        controller.bank_request_target = 0 if event[1] == 52 else 1
                        controller.update_bank((controller.bank_index, 0))
                    elif (event[0] == "C" and ready and not saw_reset
                          and controller.bank_ready):
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
                    next_poll = clock() + poll_seconds
                    if ready and (pending.events or pending.foreign is not None):
                        if process_poll(controller, pending) == "HALTED":
                            print("SCENE2_CONTINUOUS=STOPPED; VERIFIED_WRITES=%d" %
                                  controller.writes, flush=True)
                            return 0 if (controller.max_writes != 0 and
                                         controller.writes ==
                                         controller.max_writes) else 1
                        pending = MidiPoll()
                    elif not ready:
                        pending = MidiPoll()
                sleep(idle_sleep)
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
    parser.add_argument("--write-approved-project", "--write-test-copy",
                        dest="write_test_copy", action="store_true")
    parser.add_argument("--allow-named-project", action="store_true",
                        help="explicit per-session authorization for a "
                             "backed-up non-test project")
    parser.add_argument("--follow-active-project", action="store_true",
                        help="normal product mode: auto-follow Resolve project; "
                             "fresh pickup and setter-bound identity checks")
    parser.add_argument("--follow-mcu-bank", action="store_true",
                        help="align knobs with confirmed MCU bank 1 or 2")
    parser.add_argument("--low-latency", action="store_true",
                        help="test mode: 20ms event polling; skip the 120ms "
                             "extra wait but keep setter-bound snapshots")
    parser.add_argument("--expected-project")
    parser.add_argument("--confirmed-no-automation", action="store_true")
    parser.add_argument("--consent")
    parser.add_argument("--max-writes", type=int, default=256,
                        help="1..256 verified edits across all eight knobs")
    parser.add_argument("--unlimited-writes", action="store_true",
                        help="Requires --seconds 0 and explicit test-copy consent")
    args = parser.parse_args()
    if args.seconds != 0 and not 5 <= args.seconds <= 3600:
        parser.error("--seconds must be 0 or 5..3600")
    if args.allow_named_project and not args.write_test_copy:
        parser.error("--allow-named-project needs --write-approved-project")
    if args.follow_active_project and (args.write_test_copy or
                                      args.allow_named_project or
                                      args.expected_project):
        parser.error("--follow-active-project cannot be mixed with "
                     "manual project/consent flags")
    if args.follow_mcu_bank and not args.follow_active_project:
        parser.error("--follow-mcu-bank requires --follow-active-project")
    if args.unlimited_writes:
        if not (args.write_test_copy or args.follow_active_project) or args.seconds != 0:
            parser.error("unlimited writes require a continuous writable mode")
        args.max_writes = 0
    elif not 1 <= args.max_writes <= 256:
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
            app, write=(args.write_test_copy or args.follow_active_project),
            expected_project=args.expected_project,
            confirmation=args.consent,
            automation_confirmed=args.confirmed_no_automation,
            max_writes=args.max_writes,
            low_latency=args.low_latency,
            allow_named_project=args.allow_named_project,
            follow_active_project=args.follow_active_project,
            follow_mcu_bank=args.follow_mcu_bank,
        )
    except ValueError as exc:
        print("SCENE2_CONTINUOUS=BLOCKED; %s; WRITES=0" % exc)
        return 1
    # One clip worker at a time, even if the combined menu and a terminal
    # attempt to start separate sessions. MCU retains its own IAC lock.
    try:
        with LIVE_LOCK.open("w") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("SCENE2_CONTINUOUS=BLOCKED; another clip worker is running; WRITES=0")
                return 1
            return monitor(controller, seconds=args.seconds)
    except OSError as exc:
        print("SCENE2_CONTINUOUS=BLOCKED; clip lock unavailable: %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
