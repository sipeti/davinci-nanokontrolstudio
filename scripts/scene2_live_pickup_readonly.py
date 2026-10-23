#!/usr/bin/env python3
"""One short, passive hardware-to-Resolve Scene 2 pickup acceptance test.

Run externally using the proven ResolvePython environment, NOT inside Resolve's
interactive Python Console. Never calls setters, MIDI output or keyboard APIs.
Hammerspoon writes local MIDI events; this process only reads those events and
the authoritative Resolve clip volume. WRITE_INTENT is displayed, never applied.
"""
import argparse
import math
import re
import sys
import time
from pathlib import Path

from scene2_soft_takeover import SoftTakeover, gain_for_cc

EVENT_FILE = Path.home() / "Library" / "Caches" / "nk-scene2-live-midi.csv"


class Blocked(Exception):
    pass


def get(obj, method, *args):
    if obj is None:
        raise Blocked("missing API object")
    fn = getattr(obj, method, None)
    if not callable(fn):
        raise Blocked(method + " unavailable")
    try:
        result = fn(*args)
    except Exception as exc:
        raise Blocked(method + " failed: " + type(exc).__name__) from exc
    if result is None:
        raise Blocked(method + " returned nothing")
    return result


def number(value):
    if isinstance(value, bool):
        raise Blocked("invalid numeric readback")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise Blocked("numeric readback unavailable") from exc
    if not math.isfinite(result):
        raise Blocked("nonfinite numeric readback")
    return result


def tc_frame(tc, fps):
    if not isinstance(tc, str) or not re.fullmatch(r"\d{2}:\d{2}:\d{2}:\d{2}", tc):
        raise Blocked("unsupported timecode")
    h, m, s, f = map(int, tc.split(":"))
    if m >= 60 or s >= 60 or f >= fps:
        raise Blocked("invalid timecode")
    return ((h * 3600 + m * 60 + s) * fps) + f


def snapshot(app, track):
    """Return (stable clip identity, real dB), or fail closed. Read-only."""
    pm = get(app, "GetProjectManager")
    project = get(pm, "GetCurrentProject")
    timeline = get(project, "GetCurrentTimeline")
    project_id = get(project, "GetUniqueId")
    timeline_id = get(timeline, "GetUniqueId")
    if not all(isinstance(x, str) and x for x in (project_id, timeline_id)):
        raise Blocked("project/timeline identity unavailable")
    settings = get(timeline, "GetSettings")
    if not isinstance(settings, dict):
        raise Blocked("timeline settings unavailable")
    fps_raw = number(settings.get("timelineFrameRate"))
    if not fps_raw.is_integer() or not 1 <= fps_raw <= 120:
        raise Blocked("unsupported timeline frame rate")
    fps = int(fps_raw)
    first = number(get(timeline, "GetStartFrame"))
    if first != tc_frame(get(timeline, "GetStartTimecode"), fps):
        raise Blocked("frame origin mismatch")
    playhead = tc_frame(get(timeline, "GetCurrentTimecode"), fps)
    track_count = get(timeline, "GetTrackCount", "audio")
    if type(track_count) is not int or not 1 <= track <= track_count:
        raise Blocked("audio track unavailable")
    items = get(timeline, "GetItemListInTrack", "audio", track)
    if not isinstance(items, (tuple, list)):
        raise Blocked("audio item list unavailable")
    matches = []
    for item in items:
        start, end = number(get(item, "GetStart")), number(get(item, "GetEnd"))
        if start <= playhead < end:
            matches.append((item, start, end))
    if len(matches) != 1:
        raise Blocked("expected exactly one playhead clip, got " + str(len(matches)))
    item, start, end = matches[0]
    if get(item, "GetType") != "audio":
        raise Blocked("not a plain audio item")
    item_id = get(item, "GetUniqueId")
    if not isinstance(item_id, str) or not item_id:
        raise Blocked("clip identity unavailable")
    props = get(item, "GetProperties")
    if not isinstance(props, dict) or props.get("AudioVolumeEnabled") is not True:
        raise Blocked("clip audio volume disabled")
    db = number(props.get("AudioVolume"))
    if not -100 <= db <= 30:
        raise Blocked("gain outside supported range")
    return (project_id, timeline_id, track, item_id, start, end), db


def parse_event(line):
    try:
        parts = line.strip().split(",")
        if len(parts) != 3:
            return None
        ch, cc, val = [int(p) for p in parts]
        if ch < 0 or ch > 15 or cc < 0 or cc > 127 or val < 0 or val > 127:
            return None
        return ch, cc, val
    except (ValueError, TypeError):
        return None


def monitor(app, track, seconds, event_file=EVENT_FILE):
    if not event_file.is_file():
        print("SCENE2_LIVE_PICKUP=BLOCKED; start Hammerspoon logger first; WRITES=0")
        return 1
    knob_cc = 12 + track
    engine = SoftTakeover()
    read_count = 0
    moved = False
    pickup = False
    last_block = None
    last_identity = None
    try:
        identity, db = snapshot(app, track)
        target_cc = min(range(128), key=lambda cc: abs(gain_for_cc(cc) - db))
        print("SCENE2_LIVE_PICKUP=START; A%d; OBSERVED_DB=%.3f; CC%d; PICKUP_NEAR_CC=%d; WRITES=0"
              % (track, db, knob_cc, target_cc), flush=True)
    except Blocked as exc:
        print("SCENE2_LIVE_PICKUP=BLOCKED; " + str(exc) + "; WRITES=0")
        return 1
    # Skip stale events written before the external test started.
    with event_file.open("r", encoding="ascii", errors="replace") as stream:
        stream.seek(0, 2)
        deadline = time.monotonic() + seconds
        next_read = time.monotonic()
        pending = []
        while time.monotonic() < deadline:
            for line in stream.readlines():
                event = parse_event(line)
                if event is not None:
                    pending.append(event)
            if len(pending) > 1024:
                engine.reset()
                pending = []
                print("MIDI_BACKLOG=BLOCKED; pickup reset; WRITES=0", flush=True)
            now = time.monotonic()
            if not pending or now < next_read:
                time.sleep(0.04)
                continue
            next_read = now + 0.20  # throttle Resolve API reads to at most 5 Hz
            try:
                identity, db = snapshot(app, track)
                read_count += 1
                last_block = None
                if last_identity is not None and last_identity != identity:
                    engine.reset()
                    print("CLIP_OR_TIMELINE_CHANGED=RESET; WRITES=0", flush=True)
                last_identity = identity
            except Blocked as exc:
                engine.reset()
                if last_block != str(exc):
                    print("NO_TRUSTED_TARGET=%s; WRITES=0" % exc, flush=True)
                    last_block = str(exc)
                pending.clear()
                continue
            batch, pending = pending, []
            for ch, cc, val in batch:
                if ch != 1:
                    engine.reset()
                    print("SCENE_CHANGE=RESET; WRITES=0", flush=True)
                    continue
                if cc != knob_cc:
                    continue
                moved = True
                decision = engine.feed(ch, cc, val, identity, db, True)
                if decision.state == "PICKUP_PENDING" and engine.state(track) == "PICKUP_PENDING":
                    if not getattr(monitor, "_pending_printed", False):
                        print("A%d PICKUP_PENDING; CC=%d; CURRENT_DB=%.3f; WRITES=0" %
                              (track, val, db), flush=True)
                        monitor._pending_printed = True
                elif decision.state == "ENGAGED" and decision.reason == "pickup; no write":
                    pickup = True
                    print("A%d PICKUP=PASS; CC=%d; WRITES=0" % (track, val), flush=True)
                elif decision.state == "WRITE_INTENT":
                    print("A%d SIMULATED_INTENT_DB=%.3f; NOT_APPLIED; WRITES=0" %
                          (track, decision.proposed_db), flush=True)
                    engine.reject(track)
                    print("SCENE2_LIVE_PICKUP=PASS; WRITES=0; API_READS=%d" %
                          read_count, flush=True)
                    return 0
                elif decision.state == "DISABLED":
                    print("A%d DISABLED=%s; WRITES=0" % (track, decision.reason), flush=True)
                    monitor._pending_printed = False
        print("SCENE2_LIVE_PICKUP=%s; PICKUP=%s; MIDI=%s; WRITES=0; API_READS=%d" %
              ("PARTIAL" if moved else "NO_MIDI", pickup, moved, read_count), flush=True)
        return 2
    # No setters exist anywhere in this module.


def main():
    p = argparse.ArgumentParser(description="Passive Scene 2 live pickup test; never writes gain")
    p.add_argument("--track", type=int, default=4, choices=range(1, 9))
    p.add_argument("--seconds", type=int, default=45)
    args = p.parse_args()
    if not 5 <= args.seconds <= 120:
        p.error("--seconds must be 5..120")
    try:
        import DaVinciResolveScript as dvr
        app = dvr.scriptapp("Resolve")
    except (ImportError, OSError) as exc:
        print("SCENE2_LIVE_PICKUP=BLOCKED; ResolvePython unavailable; WRITES=0")
        return 1
    if app is None:
        print("SCENE2_LIVE_PICKUP=BLOCKED; no Resolve connection; WRITES=0")
        return 1
    return monitor(app, args.track, args.seconds)


if __name__ == "__main__":
    sys.exit(main())
