#!/usr/bin/env python3
"""Scene 2 CC13..20 -> A1..A8 playhead-clip AudioVolume, guarded research.

Default: read-only pickup and simulated gain intent. Optional test-copy
writing is bounded, per-strip, explicitly consented and readback-verified.
This is NOT a mixer fader, MUTE/SOLO, or production controller.
"""
import argparse
import sys
import time

import scene2_audio_roundtrip_probe as api
from scene2_live_pickup_readonly import EVENT_FILE, parse_event
from scene2_soft_takeover import SoftTakeover, gain_for_cc

CONSENT = "YES, THIS IS A BACKED-UP TEST PROJECT"
COPY_WORDS = ("test", "copy", "backup", "qa", "teszt", "masolat", "másolat")

IDLE_RESET_SECONDS = 2.0
POLL_SECONDS = 0.20


def approved_copy(project_name, confirmation, automation_confirmed):
    return (
        isinstance(project_name, str)
        and project_name.strip() != ""
        and any(word in project_name.casefold() for word in COPY_WORDS)
        and confirmation == CONSENT
        and automation_confirmed is True
    )


def snapshot(app, track):
    api.resolve = app
    snap = api._snapshot(track)
    key = snap["key"]
    identity = (key[0], key[1], key[4], key[7], key[8], key[9])
    # A session is bound to project, timeline, FPS, and a STOPPED playhead.
    session = (key[0], key[1], key[5], key[6])
    return snap, identity, session


class Controller:
    def __init__(self, app, write=False, expected_project=None,
                 confirmation=None, automation_confirmed=False, max_writes=8,
                 now=time.monotonic, max_writes_limit=16,
                 allow_unlimited=False):
        self.app = app
        self.write = write
        self.expected_project = expected_project
        self.max_writes = max_writes
        self.now = now
        self.engine = SoftTakeover()
        self.session = None
        self.last_event = None
        self.writes = 0
        self.halted = False
        self.reported = set()
        self.other_scene_active = False
        self.high_rate_reported = False
        if write and not approved_copy(expected_project, confirmation,
                                       automation_confirmed):
            raise ValueError("a backed-up exact test project, consent and no-automation confirmation are mandatory")
        if (type(max_writes_limit) is not int or
                max_writes_limit not in (16, 256)):
            raise ValueError("max_writes_limit must be 16 or 256")
        unlimited = (allow_unlimited is True and max_writes == 0 and
                     max_writes_limit == 256 and write)
        if type(max_writes) is not int or not (
                1 <= max_writes <= max_writes_limit or unlimited):
            raise ValueError("max_writes must be 1..%d, or 0 in explicit "
                             "continuous writable mode" % max_writes_limit)

    def _halt(self, reason):
        self.halted = True
        self.engine.reset()
        print("SCENE2_8ROTARY=HALTED; %s; STOP ALL WRITES" % reason, flush=True)
        return "HALTED"

    def _write(self, track, before, identity, requested):
        item = before["item"]
        original = before["db"]
        if (type(requested) not in (float, int)
                or not gain_for_cc(0) <= requested <= gain_for_cc(127)
                or abs(requested - original) <= 0.055):
            self.engine.reject(track)
            print("A%d WRITE=BLOCKED; invalid absolute gain target or no change" %
                  track, flush=True)
            return "BLOCKED"
        # The fresh setter-bound snapshot must match EVERYTHING including
        # original volume and playhead frame; no stale MIDI target may write.
        try:
            stable, stable_identity, stable_session = snapshot(self.app, track)
            if (stable["key"] != before["key"] or stable_identity != identity
                    or stable_session != self.session
                    or stable["project"] != self.expected_project):
                self.engine.reject(track)
                return self._halt("context changed before setter")
        except api.ProbeBlocked:
            return self._halt("unavailable setter-bound readback")
        try:
            setter_result = item.SetProperties({"AudioVolume": requested})
            after, after_identity, after_session = snapshot(self.app, track)
            if (setter_result is not True or after_identity != identity
                    or after_session != self.session
                    or after["key"][:-1] != stable["key"][:-1]
                    or not api._close(after["db"], requested)):
                raise api.ProbeBlocked("setter/readback mismatch")
            if not self.engine.confirm(track, identity, after["db"], True):
                raise api.ProbeBlocked("pickup confirmation mismatch")
            self.writes += 1
            print("A%d AUDIO_WRITE_READBACK=PASS; %.3f -> %.3f dB; WRITES=%d/%s" %
                  (track, original, after["db"], self.writes,
                   "UNLIMITED" if self.max_writes == 0 else str(self.max_writes)),
                  flush=True)
            if self.max_writes and self.writes >= self.max_writes:
                return self._halt("session write cap reached")
            return "WRITTEN"
        except Exception as exc:
            # A failing setter may nevertheless have applied the value:
            # attempt restoration of the specifically captured clip.
            try:
                restored = item.SetProperties({"AudioVolume": original})
                check, check_identity, check_session = snapshot(self.app, track)
                restored = (restored is True and check_identity == identity
                            and check_session == self.session
                            and api._close(check["db"], original))
            except Exception:
                restored = False
            print("A%d AUDIO_WRITE=FAIL; %s; ROLLBACK_VERIFIED=%s; ORIGINAL_DB=%.3f" %
                  (track, type(exc).__name__, restored, original), flush=True)
            if not restored:
                print("CRITICAL: restore A%d clip manually to %.3f dB in Inspector" %
                      (track, original), flush=True)
            return self._halt("setter or readback failure")

    def handle(self, channel, cc, value, *, preloaded=None):
        if self.halted:
            return "HALTED"
        if channel != 1:
            self.engine.reset()
            self.last_event = None
            if self.write:
                return self._halt("non-Scene-2 MIDI channel %d CC%d detected" %
                                  (channel, cc))
            if not self.other_scene_active:
                print("OTHER_SCENE_INPUT=RESET; channel=%d CC%d; WRITES=0" %
                      (channel, cc), flush=True)
            self.other_scene_active = True
            return "RESET"
        if not 13 <= cc <= 20:
            return "IGNORED"
        self.other_scene_active = False
        track = cc - 12
        now = self.now()
        if self.last_event is not None and now - self.last_event > IDLE_RESET_SECONDS:
            self.engine.reset()  # silent hardware Scene switches also rearm
            print("MIDI_IDLE=REARM; no stale pickup retained", flush=True)
        self.last_event = now
        try:
            before, identity, session = (
                preloaded if preloaded is not None
                else snapshot(self.app, track))
        except api.ProbeBlocked as exc:
            self.engine.reject(track)
            label = (track, str(exc))
            if label not in self.reported:
                self.reported.add(label)
                print("A%d DISABLED; %s; WRITES=0" % (track, exc), flush=True)
            return "DISABLED"
        if self.write and before["project"] != self.expected_project:
            return self._halt("project is not the exact approved test copy")
        if self.session is None:
            self.session = session
        elif self.session != session:
            # In write mode a moved playhead, project or timeline ends
            # the entire test session. Read-only mode may rearm on change.
            if self.write:
                return self._halt("project, timeline or playhead moved")
            self.engine.reset()
            self.session = session
            print("CONTEXT_CHANGED=RESET; WRITES=0", flush=True)
        decision = self.engine.feed(channel, cc, value, identity,
                                    before["db"], True)
        if decision.state == "PICKUP_PENDING":
            label = ("PICKUP", track, identity, round(before["db"], 2))
            if label not in self.reported:
                self.reported.add(label)
                nearest = min(range(128),
                              key=lambda val: abs(gain_for_cc(val) - before["db"]))
                print("A%d PICKUP_PENDING; DB=%.3f; NEAR_CC=%d; WRITES=0" %
                      (track, before["db"], nearest), flush=True)
        elif decision.state == "ENGAGED" and decision.reason == "pickup; no write":
            print("A%d PICKUP=PASS; CC=%d; WRITES=0" % (track, value), flush=True)
        elif decision.state == "WRITE_INTENT":
            if not self.write:
                print("A%d SIMULATED_GAIN=%.3f; WRITES=0" %
                      (track, decision.proposed_db), flush=True)
                self.engine.reject(track)
                return "SIMULATED"
            return self._write(track, before, identity, decision.proposed_db)
        elif decision.state == "DISABLED":
            print("A%d DISABLED; %s; WRITES=0" %
                  (track, decision.reason), flush=True)
        return decision.state


class MidiPoll:
    """Bounded, fail-closed event accumulator between Resolve API polls.

    Capture first and last MIDI positions per Scene 2 knob to preserve
    a pickup crossing, but never infer motion from discarded intermediate
    samples. Any event from a different MIDI channel invalidates the whole
    batch; an active write test HALTS instead of trying to pick up again.
    A torrent of foreign-channel events cannot exhaust the queue.
    """
    MAX_ROTARY_EVENTS = 80

    def __init__(self):
        self.events = {}
        self.foreign = None
        self.foreign_count = 0
        self.raw_rotary_count = 0
        # Only *changed* physical CC positions count towards the safety
        # movement limit. Korg may repeat the same CC value at high rates.
        self.rotary_count = 0
        self.last_value = {}

    def add(self, line):
        event = parse_event(line)
        if event is None:
            return
        ch, cc, _ = event
        if ch != 1:
            self.foreign = event
            self.foreign_count += 1
            self.events.clear()
        elif 13 <= cc <= 20 and self.foreign is None:
            self.raw_rotary_count += 1
            if self.last_value.get(cc) == event:
                return  # duplicate packet cannot cause a physical CC step
            self.last_value[cc] = event
            self.rotary_count += 1
            samples = self.events.setdefault(cc, [])
            if len(samples) < 2:
                samples.append(event)
            else:
                samples[-1] = event

    def take(self, *, engaged_ccs=()):
        foreign, count = self.foreign, self.rotary_count
        # Retain first+last for soft pickup, but once a knob is ENGAGED
        # only its LAST actual physical CC is relevant. Old intermediate
        # values would cause redundant slow Resolve setters and lag.
        # A conflicting scene still discards the entire batch.
        events = [] if foreign is not None else [
            event for cc, pair in self.events.items()
            for event in (pair[-1:] if cc in engaged_ccs else pair)
        ]
        self.__init__()
        return foreign, count, events


def process_poll(controller, pending):
    """One bounded MIDI batch. No Resolve setter outside Controller._write.

    Read-only probes must *not* fail simply due to fast/duplicate MIDI input.
    The buffered representation remains first+last only, so extreme bursts
    may miss the pickup point: slow down rather than infer a hidden crossing.
    Writable test-copy sessions keep a strict changed-CC rate guard.
    """
    if pending.rotary_count > pending.MAX_ROTARY_EVENTS:
        if controller.write:
            print("MIDI_RATE=BLOCKED; raw=%d; changed=%d; limit=%d; "
                  "VERIFIED_WRITES=%d" %
                  (pending.raw_rotary_count, pending.rotary_count,
                   pending.MAX_ROTARY_EVENTS, controller.writes), flush=True)
            controller._halt("excessive Scene 2 knob movement")
            return "HALTED"
        if not controller.high_rate_reported:
            print("MIDI_BURST=COALESCED; raw=%d; changed=%d; "
                  "READ_ONLY; WRITES=0; slow down near pickup" %
                  (pending.raw_rotary_count, pending.rotary_count), flush=True)
            controller.high_rate_reported = True
    engaged_ccs = {
        cc for cc in pending.events
        if controller.engine.state(cc - 12) == "ENGAGED"
    }
    foreign, _, events = pending.take(engaged_ccs=engaged_ccs)
    if foreign is not None:
        if controller.handle(*foreign) == "HALTED":
            return "HALTED"
        return "CONTINUE"
    for event in events:
        if controller.handle(*event) == "HALTED":
            return "HALTED"
    return "CONTINUE"


def monitor(controller, seconds, event_file=EVENT_FILE):
    if not event_file.is_file():
        print("SCENE2_8ROTARY=BLOCKED; start the passive MIDI logger; WRITES=0")
        return 1
    print("SCENE2_8ROTARY=START; mode=%s; CC13..20=A1..A8; max_writes=%d" %
          ("TEST_COPY_WRITE" if controller.write else "READ_ONLY",
           controller.max_writes if controller.write else 0), flush=True)
    with event_file.open("r", encoding="ascii", errors="replace") as stream:
        stream.seek(0, 2)
        deadline = time.monotonic() + seconds
        next_poll = time.monotonic()
        pending = MidiPoll()
        while time.monotonic() < deadline:
            # A logger restart may truncate the CSV while the old file is
            # still open. Do not merge old/new sessions.
            try:
                if event_file.stat().st_size < stream.tell():
                    controller.engine.reset()
                    print("SCENE2_8ROTARY=BLOCKED; MIDI logger restarted",
                          flush=True)
                    return 1
                for line in stream.readlines():
                    pending.add(line)
            except OSError:
                print("SCENE2_8ROTARY=BLOCKED; MIDI logger file missing",
                      flush=True)
                return 1
            # The rate guard belongs to the write decision, not to raw
            # CSV ingestion: duplicates are common and read-only probes
            # should remain observable even under very dense MIDI input.
            if (not pending.events and pending.foreign is None) or (
                    time.monotonic() < next_poll):
                time.sleep(0.04)
                continue
            next_poll = time.monotonic() + POLL_SECONDS
            if process_poll(controller, pending) == "HALTED":
                print("SCENE2_8ROTARY=STOPPED; VERIFIED_WRITES=%d" %
                      controller.writes, flush=True)
                return 1 if controller.writes < controller.max_writes else 0
    print("SCENE2_8ROTARY=COMPLETE; mode=%s; VERIFIED_WRITES=%d" %
          ("TEST_COPY" if controller.write else "READ_ONLY", controller.writes),
          flush=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description="Scene 2 eight-rotary clip gain research")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--write-test-copy", action="store_true")
    parser.add_argument("--expected-project")
    parser.add_argument("--consent")
    parser.add_argument("--confirmed-no-automation", action="store_true")
    parser.add_argument("--max-writes", type=int, default=8)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 90:
        parser.error("--seconds must be 5..90 (MIDI logger stops after 2 min)")
    try:
        import DaVinciResolveScript as dvr
        app = dvr.scriptapp("Resolve")
    except (ImportError, OSError):
        print("SCENE2_8ROTARY=BLOCKED; Resolve scripting unavailable; WRITES=0")
        return 1
    if app is None:
        print("SCENE2_8ROTARY=BLOCKED; Resolve not running; WRITES=0")
        return 1
    try:
        c = Controller(app, write=args.write_test_copy,
                       expected_project=args.expected_project,
                       confirmation=args.consent,
                       automation_confirmed=args.confirmed_no_automation,
                       max_writes=args.max_writes)
    except ValueError as exc:
        print("SCENE2_8ROTARY=BLOCKED; %s; WRITES=0" % exc)
        return 1
    return monitor(c, seconds=args.seconds)


if __name__ == "__main__":
    sys.exit(main())
