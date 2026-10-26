#!/usr/bin/env python3
"""One-clip, explicitly armed AudioVolume round-trip in Resolve 21.1.

Run in Resolve's Py3 console, in a BACKED-UP TEST PROJECT only.
Import/exec does not write. Preview never writes. The single authorized
test makes one +0.5 dB change and immediately restores the original dB.
It does not control the Korg, mixer faders, or track mute.
"""

import math
import re
import secrets
import time

_CONSENT = "YES, THIS IS A BACKED-UP TEST PROJECT"
_ARMED = None
_DB_MIN, _DB_MAX = -100.0, 30.0


class ProbeBlocked(Exception):
    pass


def _get(obj, method, *args):
    if obj is None:
        raise ProbeBlocked("missing API object for " + method)
    try:
        result = getattr(obj, method)(*args)
    except Exception as exc:
        raise ProbeBlocked(method + " failed: " + type(exc).__name__) from exc
    if result is None:
        raise ProbeBlocked(method + " returned no value")
    return result


def _number(value):
    if isinstance(value, bool):
        raise ProbeBlocked("boolean is not a volume or frame number")
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ProbeBlocked("numeric readback unavailable") from exc
    if not math.isfinite(value):
        raise ProbeBlocked("nonfinite readback")
    return value


def _timecode_frames(tc, fps):
    if not isinstance(tc, str) or not re.fullmatch(r"\d{2}:\d{2}:\d{2}:\d{2}", tc):
        raise ProbeBlocked("unsupported timecode; non-drop integer-fps only")
    hh, mm, ss, ff = [int(v) for v in tc.split(":")]
    if mm > 59 or ss > 59 or ff >= fps:
        raise ProbeBlocked("invalid timecode")
    return ((hh * 3600 + mm * 60 + ss) * fps) + ff


def _resolve_app():
    app = globals().get("resolve")
    if app is None:
        try:
            import DaVinciResolveScript as dvr
            app = dvr.scriptapp("Resolve")
        except (ImportError, OSError) as exc:
            raise ProbeBlocked("Resolve Python scripting unavailable") from exc
    if app is None:
        raise ProbeBlocked("no Resolve connection")
    return app


def _snapshot(track):
    if type(track) is not int or not 1 <= track <= 16:
        raise ProbeBlocked("track must be an integer from 1 to 16")
    manager = _get(_resolve_app(), "GetProjectManager")
    project = _get(manager, "GetCurrentProject")
    timeline = _get(project, "GetCurrentTimeline")
    project_name, project_id = _get(project, "GetName"), _get(project, "GetUniqueId")
    timeline_name, timeline_id = _get(timeline, "GetName"), _get(timeline, "GetUniqueId")
    if not all(isinstance(x, str) and x for x in
               (project_name, project_id, timeline_name, timeline_id)):
        raise ProbeBlocked("project/timeline identity unavailable")

    settings = _get(timeline, "GetSettings")
    if not isinstance(settings, dict):
        raise ProbeBlocked("timeline settings unavailable")
    raw_fps = _number(settings.get("timelineFrameRate"))
    if not raw_fps.is_integer() or not 1 <= raw_fps <= 120:
        raise ProbeBlocked("non-integer timeline FPS")
    fps = int(raw_fps)
    start_tc = _get(timeline, "GetStartTimecode")
    playhead_tc = _get(timeline, "GetCurrentTimecode")
    start_frame = _number(_get(timeline, "GetStartFrame"))
    if start_frame != _timecode_frames(start_tc, fps):
        raise ProbeBlocked("timeline frame/timecode origin mismatch")
    frame = _timecode_frames(playhead_tc, fps)

    tracks = _get(timeline, "GetTrackCount", "audio")
    if type(tracks) is not int or tracks < track:
        raise ProbeBlocked("requested audio track does not exist")
    items = _get(timeline, "GetItemListInTrack", "audio", track)
    if not isinstance(items, (list, tuple)):
        raise ProbeBlocked("audio track clip list unavailable")
    matches = []
    for item in items:
        begin, end = _number(_get(item, "GetStart")), _number(_get(item, "GetEnd"))
        if begin <= frame < end:
            matches.append((item, begin, end))
    if len(matches) != 1:
        raise ProbeBlocked("A%d: %d clips at playhead; require exactly one"
                           % (track, len(matches)))
    item, begin, end = matches[0]
    if _get(item, "GetType") != "audio":
        raise ProbeBlocked("playhead item is not a plain audio item")
    item_id = _get(item, "GetUniqueId")
    if not isinstance(item_id, str) or not item_id:
        raise ProbeBlocked("no stable clip identity")
    props = _get(item, "GetProperties")
    if not isinstance(props, dict) or props.get("AudioVolumeEnabled") is not True:
        raise ProbeBlocked("AudioVolume is not enabled or properties missing")
    db = _number(props.get("AudioVolume"))
    if not _DB_MIN <= db <= _DB_MAX:
        raise ProbeBlocked("AudioVolume outside documented dB range")
    # Only local values, not clip filenames or media payloads. Stable IDs
    # are compared internally and never printed.
    key = (project_id, timeline_id, project_name, timeline_name,
           track, fps, frame, item_id, begin, end, db)
    return {"key": key, "item": item, "db": db, "track": track,
            "project": project_name, "timeline": timeline_name}


def _db_read(item):
    props = _get(item, "GetProperties")
    if not isinstance(props, dict) or props.get("AudioVolumeEnabled") is not True:
        raise ProbeBlocked("AudioVolume no longer readable/enabled")
    return _number(props.get("AudioVolume"))


def _close(a, b):
    return abs(a - b) <= 0.055


def scene2_preview(track=4):
    """Read-only arming stage; prints local project/timeline and token."""
    global _ARMED
    _ARMED = None
    try:
        snapshot = _snapshot(track)
    except ProbeBlocked as exc:
        print("SCENE2_ROUNDTRIP=BLOCKED; WRITES=0; REASON=" + str(exc))
        return False
    token = secrets.token_hex(4)
    _ARMED = {"snapshot": snapshot["key"], "token": token, "track": track}
    print("SCENE2_ROUNDTRIP=PREVIEW_ONLY; WRITES=0")
    print("PROJECT=%r TIMELINE=%r" % (snapshot["project"], snapshot["timeline"]))
    print("TRACK=A%d ORIGINAL_DB=%.3f CANDIDATE_DB=%.3f" %
          (track, snapshot["db"], _candidate(snapshot["db"])))
    print("Only on a STOPPED, BACKED-UP, DISPOSABLE test project, no gain keyframes:")
    print("scene2_roundtrip(token=%r, expected_project=%r, confirmation=%r)" %
          (token, snapshot["project"], _CONSENT))
    return True


def _candidate(db):
    return round(db + (0.5 if db <= _DB_MAX - 0.5 else -0.5), 3)


def scene2_roundtrip(token=None, expected_project=None, confirmation=None):
    """One guarded +0.5 dB test; always attempt restoration after a write."""
    global _ARMED
    arm = _ARMED
    _ARMED = None   # one-shot: cannot replay an old authorization
    if (arm is None or token != arm["token"] or
            confirmation != _CONSENT or
            expected_project != arm["snapshot"][2]):
        print("SCENE2_ROUNDTRIP=BLOCKED; WRITES=0; consent/context invalid")
        return False
    try:
        fresh = _snapshot(arm["track"])
    except ProbeBlocked as exc:
        print("SCENE2_ROUNDTRIP=BLOCKED; WRITES=0; " + str(exc))
        return False
    if fresh["key"] != arm["snapshot"]:
        print("SCENE2_ROUNDTRIP=BLOCKED; WRITES=0; target/context/dB changed")
        return False
    # A silent UI pause is not enough: refuse if the playhead advances.
    time.sleep(0.15)
    try:
        stable = _snapshot(arm["track"])
    except ProbeBlocked as exc:
        print("SCENE2_ROUNDTRIP=BLOCKED; WRITES=0; " + str(exc))
        return False
    if stable["key"] != arm["snapshot"]:
        print("SCENE2_ROUNDTRIP=BLOCKED; WRITES=0; playhead/context moved")
        return False

    item, original = stable["item"], stable["db"]
    test_db = _candidate(original)
    if not _DB_MIN <= test_db <= _DB_MAX:
        print("SCENE2_ROUNDTRIP=BLOCKED; WRITES=0; invalid test dB")
        return False

    print("SCENE2_ROUNDTRIP=ARMED; ORIGINAL_DB=%.3f TEST_DB=%.3f" %
          (original, test_db))
    print("BACKUP REQUIRED; do not close Resolve if RESTORE_VERIFIED is false.")
    attempted = False
    wrote_and_verified = False
    restored = False
    try:
        attempted = True
        result = item.SetProperties({"AudioVolume": test_db})
        if result is not True:
            raise ProbeBlocked("test setter rejected AudioVolume")
        if not _close(_db_read(item), test_db):
            raise ProbeBlocked("test write was not confirmed by readback")
        wrote_and_verified = True
        print("TEST_WRITE_READBACK=PASS")
    except Exception as exc:
        print("TEST_WRITE_READBACK=FAIL; REASON=" + type(exc).__name__)
    finally:
        if attempted:
            # The captured item is still the exact clip selected at preview;
            # Restore even if the test write claimed failure/raised.
            try:
                restore_result = item.SetProperties({"AudioVolume": original})
                restored = restore_result is True and _close(_db_read(item), original)
            except Exception:
                restored = False
        print("RESTORE_VERIFIED=%s; ORIGINAL_DB=%.3f" % (restored, original))
        if not restored:
            print("CRITICAL: verify/restore %.3f dB manually in the Inspector" %
                  original)
    passed = wrote_and_verified and restored
    print("SCENE2_ROUNDTRIP=%s" % ("PASS" if passed else "FAIL"))
    return passed


print("SCENE2_AUDIO_ROUNDTRIP=LOADED; WRITES=0")
print("Run scene2_preview(4) to inspect/arm a disposable A4 test clip.")
