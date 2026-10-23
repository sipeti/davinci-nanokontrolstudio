#!/usr/bin/env python3
"""Read-only DaVinci Resolve 21.1 Scene 2 audio capabilities probe.

This file contains NO calls to Set*, no timeline modifications, no media names,
and no external network requests. Run inside Resolve's Python Console.
"""

import math
import re


def call(obj, name, *args):
    """Read-only, documented Resolve getters only; failures return None."""
    if obj is None:
        return None
    try:
        return getattr(obj, name)(*args)
    except Exception as exc:
        print("READ_FAILED %s: %s" % (name, type(exc).__name__))
        return None


def frame_from_timecode(timecode, rate):
    """Accept only integer-frame-rate, non-drop timecode; never guess on DF."""
    if not isinstance(timecode, str) or not isinstance(rate, int) or rate <= 0:
        return None
    if not re.fullmatch(r"\d{2}:\d{2}:\d{2}:\d{2}", timecode):
        return None
    h, m, s, f = (int(part) for part in timecode.split(":"))
    if m >= 60 or s >= 60 or f >= rate:
        return None
    return ((h * 3600 + m * 60 + s) * rate) + f


def finite_float(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def main():
    print("SCENE2_AUDIO_READONLY_PROBE=START")
    app = globals().get("resolve")
    if app is None:
        try:
            import DaVinciResolveScript as dvr
            app = dvr.scriptapp("Resolve")
        except (ImportError, OSError):
            app = None
    if app is None:
        print("BLOCKED: no Resolve scripting connection. No changes made.")
        return

    project_manager = call(app, "GetProjectManager")
    project = call(project_manager, "GetCurrentProject")
    timeline = call(project, "GetCurrentTimeline")
    if timeline is None:
        print("BLOCKED: no active timeline. No changes made.")
        return

    # The script inspects ONLY the API methods available. It never calls any
    # mixer setter and never simulates keyboard/mouse actions.
    available = set(dir(timeline))
    mixer_methods = sorted(
        name for name in available
        if ("Volume" in name or "Fader" in name or "Mixer" in name
            or "Gain" in name) and name.startswith(("Get", "Set"))
    )
    print("MIXER_METHOD_NAMES=%s" % (", ".join(mixer_methods) or "none"))

    tc = call(timeline, "GetCurrentTimecode")
    start_tc = call(timeline, "GetStartTimecode")
    start_frame = finite_float(call(timeline, "GetStartFrame"))
    settings = call(timeline, "GetSettings")
    rate_raw = settings.get("timelineFrameRate") if isinstance(settings, dict) else None
    rate_number = finite_float(rate_raw)
    fps = int(rate_number) if rate_number is not None and rate_number.is_integer() else None
    if fps is not None and not 1 <= fps <= 120:
        fps = None
    expected_start = frame_from_timecode(start_tc, fps)
    playhead_frame = frame_from_timecode(tc, fps)
    if expected_start is None or start_frame is None or expected_start != start_frame:
        playhead_frame = None  # unsafe to guess timeline frame origin
    print("TIMELINE_FPS=%s START_TC=%s PLAYHEAD_TC=%s" % (rate_raw, start_tc, tc))
    print("PLAYHEAD_FRAME=%s" % (playhead_frame if playhead_frame is not None
                                 else "UNVERIFIED (timecode/fps convention)"))

    tracks = call(timeline, "GetTrackCount", "audio")
    if not isinstance(tracks, int) or tracks < 0:
        print("BLOCKED: audio track count unavailable. No changes made.")
        return
    for idx in range(1, min(tracks, 8) + 1):
        items = call(timeline, "GetItemListInTrack", "audio", idx)
        if not isinstance(items, (list, tuple)):
            print("A%d: clip list unavailable; NO TARGET" % idx)
            continue
        matches = []
        if playhead_frame is not None:
            for item in items:
                a = finite_float(call(item, "GetStart"))
                b = finite_float(call(item, "GetEnd"))
                if a is not None and b is not None and a <= playhead_frame < b:
                    matches.append(item)
        if len(matches) != 1:
            print("A%d: clips=%d candidates=%d; NO UNIQUE TARGET" %
                  (idx, len(items), len(matches)))
            continue
        props = call(matches[0], "GetProperties")
        if not isinstance(props, dict):
            print("A%d: API properties unavailable; NO WRITABLE TARGET" % idx)
            continue
        db = finite_float(props.get("AudioVolume"))
        enabled = props.get("AudioVolumeEnabled")
        if db is None or not isinstance(enabled, bool):
            print("A%d: AudioVolume readback incomplete; NO WRITABLE TARGET" % idx)
            continue
        unique_id = call(matches[0], "GetUniqueId")
        has_stable_id = isinstance(unique_id, str) and len(unique_id) > 0
        print("A%d: clips=%d playhead_clip=unique AudioVolume_dB=%s enabled=%s item_id=%s" %
              (idx, len(items), db, enabled,
               "available" if has_stable_id else "MISSING"))

    print("SCENE2_AUDIO_READONLY_PROBE=COMPLETE; WRITES=0")


main()
