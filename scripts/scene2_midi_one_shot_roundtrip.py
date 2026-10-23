#!/usr/bin/env python3
"""One-shot Korg Scene 2 A4 MIDI gain round-trip; opt-in, disposable copy only.

Default: passive live pickup + simulated intent, zero writes.
--write-once: after physical pickup, write ONE bounded A4 clip gain,
verify it, and immediately restore the ORIGINAL gain with another verification.
Never installs a controller, changes MIDI output, faders, or main Lua.
"""
import argparse
import sys
import time

import scene2_audio_roundtrip_probe as api
from scene2_live_pickup_readonly import EVENT_FILE, parse_event
from scene2_soft_takeover import SoftTakeover, gain_for_cc

TRACK = 4
CC = 16
CONSENT = "YES, THIS IS A BACKED-UP TEST PROJECT"
COPY_WORDS = ("test", "copy", "backup", "qa", "teszt", "masolat", "másolat")
MAX_TEST_DELTA_DB = 0.6


def _snapshot(app):
    # The previously live-tested round-trip probe provides strict project,
    # timeline, playhead, clip-identity, FPS and gain checks.
    api.resolve = app
    snap = api._snapshot(TRACK)
    key = snap["key"]
    identity = (key[0], key[1], key[4], key[7], key[8], key[9])
    return snap, identity


def _consent_ok(expected_project, consent):
    return (
        isinstance(expected_project, str) and expected_project.strip()
        and any(word in expected_project.casefold() for word in COPY_WORDS)
        and consent == CONSENT
    )


def one_shot_roundtrip(app, expected_key, proposed_db, expected_project=None,
                       consent=None, pause=time.sleep):
    """Single write + immediate restoration. Always fail closed on stale data."""
    if not _consent_ok(expected_project, consent):
        print("MIDI_WRITE=BLOCKED; exact named QA/test copy and consent required; WRITES=0", flush=True)
        return False
    try:
        fresh, _ = _snapshot(app)
        if fresh["key"] != expected_key or fresh["project"] != expected_project:
            print("MIDI_WRITE=BLOCKED; context or gain changed; WRITES=0", flush=True)
            return False
        original = fresh["db"]
        if (type(proposed_db) not in (int, float) or
                not -100 <= proposed_db <= 30 or
                not 0.055 < abs(proposed_db - original) <= MAX_TEST_DELTA_DB):
            print("MIDI_WRITE=BLOCKED; requested step exceeds one-shot safety bound; WRITES=0",
                  flush=True)
            return False
        pause(0.12)
        stable, _ = _snapshot(app)
        if stable["key"] != expected_key or stable["project"] != expected_project:
            print("MIDI_WRITE=BLOCKED; playhead/context moved; WRITES=0", flush=True)
            return False
    except api.ProbeBlocked as exc:
        print("MIDI_WRITE=BLOCKED; %s; WRITES=0" % exc, flush=True)
        return False

    item = stable["item"]
    wrote = False
    restored = False
    print("MIDI_WRITE=ARMED; original=%.3f dB; candidate=%.3f dB" %
          (original, proposed_db), flush=True)
    try:
        result = item.SetProperties({"AudioVolume": proposed_db})
        # Do not accept success on the setter return value alone.
        after, _ = _snapshot(app)
        if (result is not True or after["key"][:-1] != stable["key"][:-1]
                or not api._close(after["db"], proposed_db)):
            raise api.ProbeBlocked("setter/readback/context mismatch")
        wrote = True
        print("MIDI_TEST_WRITE_READBACK=PASS", flush=True)
    except Exception as exc:
        print("MIDI_TEST_WRITE_READBACK=FAIL; %s" % type(exc).__name__, flush=True)
    finally:
        # Even if the first setter claimed failure, it may have applied gain.
        try:
            restore_ok = item.SetProperties({"AudioVolume": original})
            final, _ = _snapshot(app)
            restored = (
                restore_ok is True
                and final["key"][:-1] == stable["key"][:-1]
                and api._close(final["db"], original)
            )
        except Exception:
            restored = False
        print("RESTORE_VERIFIED=%s; ORIGINAL_DB=%.3f" % (restored, original), flush=True)
        if not restored:
            print("CRITICAL: restore A4 clip to %.3f dB manually in Inspector" %
                  original, flush=True)
    passed = wrote and restored
    print("SCENE2_MIDI_ROUNDTRIP=%s" % ("PASS" if passed else "FAIL"), flush=True)
    return passed


def monitor(app, seconds=45, write_once=False, expected_project=None,
            consent=None, event_file=EVENT_FILE, pause=time.sleep):
    if write_once and not _consent_ok(expected_project, consent):
        print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; explicit named test copy + consent required; WRITES=0")
        return 1
    if not event_file.is_file():
        print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; start passive Hammerspoon logger; WRITES=0")
        return 1
    try:
        initial, identity = _snapshot(app)
        if write_once and initial["project"] != expected_project:
            print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; project mismatch; WRITES=0")
            return 1
    except api.ProbeBlocked as exc:
        print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; %s; WRITES=0" % exc)
        return 1
    cc_target = min(range(128), key=lambda val: abs(gain_for_cc(val) - initial["db"]))
    print("SCENE2_MIDI_ROUNDTRIP=START; mode=%s; A4; ORIGINAL_DB=%.3f; PICKUP_NEAR_CC=%d; WRITES=%s" %
          ("WRITE_ONCE_AND_RESTORE" if write_once else "READ_ONLY",
           initial["db"], cc_target, "MAX_2" if write_once else "0"), flush=True)
    if write_once:
        print("STOP PLAYBACK; ONLY A BACKED-UP TEST COPY WITHOUT GAIN KEYFRAMES", flush=True)
    engine = SoftTakeover()
    saw_pickup = False
    reads = 0
    with event_file.open("r", encoding="ascii", errors="replace") as stream:
        stream.seek(0, 2)  # ignore all events before this process started
        deadline = time.monotonic() + seconds
        next_read = time.monotonic()
        pending = []
        while time.monotonic() < deadline:
            for line in stream.readlines():
                event = parse_event(line)
                if event is not None:
                    pending.append(event)
            if len(pending) > 1024:
                print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; MIDI backlog; WRITES=0", flush=True)
                return 1
            now = time.monotonic()
            if not pending or now < next_read:
                pause(0.04)
                continue
            next_read = now + 0.20
            try:
                observed, current_identity = _snapshot(app)
                reads += 1
            except api.ProbeBlocked as exc:
                print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; %s; WRITES=0" % exc, flush=True)
                return 1
            if observed["key"] != initial["key"] or current_identity != identity:
                print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; clip/time/volume changed; WRITES=0",
                      flush=True)
                return 1
            batch, pending = pending, []
            for ch, cc, val in batch:
                if ch != 1:
                    engine.reset()
                    print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; scene change; WRITES=0", flush=True)
                    return 1
                if cc != CC:
                    continue
                decision = engine.feed(ch, cc, val, identity, observed["db"], True)
                if decision.state == "PICKUP_PENDING":
                    continue
                if decision.state == "ENGAGED" and decision.reason == "pickup; no write":
                    saw_pickup = True
                    print("A4 PICKUP=PASS; CC=%d; WRITES=0" % val, flush=True)
                elif decision.state == "WRITE_INTENT":
                    if not saw_pickup:
                        print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; pickup missing; WRITES=0",
                              flush=True)
                        return 1
                    print("A4 INTENT_DB=%.3f; WRITES=%s" %
                          (decision.proposed_db, "MAX_2" if write_once else "0"), flush=True)
                    if not write_once:
                        print("SCENE2_MIDI_ROUNDTRIP=PASS; SIMULATED_ONLY; WRITES=0; API_READS=%d" %
                              reads, flush=True)
                        return 0
                    return 0 if one_shot_roundtrip(
                        app, initial["key"], decision.proposed_db,
                        expected_project=expected_project, consent=consent, pause=pause
                    ) else 1
                elif decision.state == "DISABLED":
                    print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; %s; WRITES=0" %
                          decision.reason, flush=True)
                    return 1
        print("SCENE2_MIDI_ROUNDTRIP=INCOMPLETE; PICKUP=%s; WRITES=0" %
              saw_pickup, flush=True)
        return 2


def main():
    parser = argparse.ArgumentParser(description="Scene 2 A4 MIDI one-shot gain round-trip")
    parser.add_argument("--seconds", type=int, default=45)
    parser.add_argument("--write-once", action="store_true",
                        help="one bounded A4 gain write and immediate original restore")
    parser.add_argument("--expected-project", default=None)
    parser.add_argument("--consent", default=None)
    args = parser.parse_args()
    if not 5 <= args.seconds <= 120:
        parser.error("--seconds must be 5..120")
    try:
        import DaVinciResolveScript as dvr
        app = dvr.scriptapp("Resolve")
    except (ImportError, OSError):
        print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; external Resolve API unavailable; WRITES=0")
        return 1
    if app is None:
        print("SCENE2_MIDI_ROUNDTRIP=BLOCKED; no Resolve connection; WRITES=0")
        return 1
    return monitor(app, seconds=args.seconds, write_once=args.write_once,
                   expected_project=args.expected_project, consent=args.consent)


if __name__ == "__main__":
    sys.exit(main())
