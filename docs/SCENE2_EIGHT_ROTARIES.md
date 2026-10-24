# Scene 2: eight clip gain rotary controls, research preview

**Not installed, not production-ready. Do not merge or run install.command.**
This proposal stacks on the single-use write/restore experiments (#7 -> #8 -> #9 -> #10).
Those demonstrated physical A4 pickup, a readback-verified A4 MIDI
write and immediate restoration; this multi-knob session is a NEW stage of
testing and is not yet validated on the operator's actual Resolve.

## Exact mapping

- Scene 2 input MIDI callback channel **1**.
- Absolute rotaries **CC13..20** map to **A1..A8** (respectively).
- Target is the **one TimelineItem clip at the playhead** of that audio track.
- Scene 2 sliders are still **disabled** (not Fairlight mixer volume).
- MUTE/SOLO buttons are **not track controls**; 16 hardware LED pulses were
  visually verified separately in Draft PR #11, but this is not Resolve
  authoritative mixer MUTE/SOLO feedback.
- Scene 1 JOG/SHUTTLE stays on the already working main driver; the separate
  Scene 1 absolute shuttle-fader rearm fix is Draft PR #12.

Each strip independently requires physical pickup before any setter; on
scene change, idle longer than 2 s, external volume change, clip/identity
change, loss of authority, or moved project/timeline/playhead the controller
will rearm, block, or halt. One setter is allowed only after matching a fresh
readback. The requested single-change delta cannot exceed **1.2 dB**; a
rapid knob sweep beyond this fails closed. No continuous interpolation or
automated gain keyframe handling is available.

## Quick start: default read-only dry run

Use only the existing test project's Edit page, with Resolve and Hammerspoon
running. No files in the working checkout are changed.

In macOS Terminal:

~~~sh
cd ~/Projects/davinci-nanokontrolstudio || exit 1
git fetch origin
mkdir -p /tmp/nk-scene2-eight
git archive origin/research/scene2-eight-rotary-clip-gain \
  scripts/scene2_midi_bridge_probe.lua \
  scripts/scene2_live_pickup_readonly.py \
  scripts/scene2_audio_roundtrip_probe.py \
  scripts/scene2_soft_takeover.py \
  scripts/scene2_clip_gain_8rotary.py | tar -x -C /tmp/nk-scene2-eight
~~~

In Hammerspoon Console, restart the *passive* MIDI capture:

~~~lua
dofile("/tmp/nk-scene2-eight/scripts/scene2_midi_bridge_probe.lua")
~~~

In **macOS Terminal** (not the Resolve Py3 console), while the logger runs:

~~~sh
PYTHONPATH="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules" \
/opt/homebrew/bin/python3 \
/tmp/nk-scene2-eight/scripts/scene2_clip_gain_8rotary.py --seconds 60
~~~

Turn Scene 2 rotary 4 slowly past pickup; try other rotaries if that audio
track has exactly one ordinary clip at the stopped timeline playhead.
Expected: A4 PICKUP_PENDING, A4 PICKUP=PASS,
A4 SIMULATED_GAIN=...; WRITES=0. Missing tracks or overlapping clips
report DISABLED and never write.

## Separately authorized test-copy write session

**Danger: this mode intentionally changes clip gains and does NOT
restore normal successful edits.** It is a prototype editing session,
unlike the earlier one-shot test that restored the original value.
Only use a **disposable backed-up test project**, with playback STOPPED and
a simple timeline **without clip gain automation/keyframes**.
The Resolve API currently cannot reliably detect that latter condition;
the operator must verify it in the UI. Do not edit the project while the
script is active, except using the Korg. The script has an 8-write cap.

Use the same prepare and logger commands above, then, only if all these
conditions are met, run the following command:

~~~sh
PYTHONPATH="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules" \
/opt/homebrew/bin/python3 \
/tmp/nk-scene2-eight/scripts/scene2_clip_gain_8rotary.py \
--seconds 60 --write-test-copy \
--expected-project "YOUR EXACT TEST COPY PROJECT NAME" \
--confirmed-no-automation \
--max-writes 8 \
--consent "YES, THIS IS A BACKED-UP TEST PROJECT"
~~~

Replace the placeholder with the exact local name of your own disposable
copy. The program checks the **exact name of the active Resolve project**.
Do not include private production project titles in public GitHub notes.

The first MIDI touch on every strip does nothing; turn through its pickup
point and then move slightly to adjust the value. Each actual write must
be verified by Resolve's API. It halts after eight successful writes, or
immediately on project/timeline/playhead shift or an unverified setter.
When a setter fails after changing gain, it attempts to restore that clip's
previous value. If this fails, a CRITICAL error includes the previous dB:
restore manually in Inspector and stop all tests.

Before and after a write test, use Inspector to verify the relevant gain
values. A successful test session does not revert the changes automatically:
discard the disposable project copy afterward if you want the original
project preserved. This is not a background daemon; it exits by itself.

In Hammerspoon Console, clean up the passive logger afterward:

~~~lua
if nkScene2LiveStop then nkScene2LiveStop() end
~~~

A normal PASS of the one-shot roundtrip is not a safety certification
for this multi-knob session. Do not enable this on production projects.
No new 28-step calibration, Korg Editor changes, controller reload,
main merge or track-fader mapping is required.


## Physical failure and next diagnostic (2026-10-24)

The first real operator trials of this new eight-knob script **did not
demonstrate pickup or any gain writes**. The passive and consented runs both
printed repeated SCENE_CHANGED=RESET. The latter eventually stopped with
MIDI backlog; there were no A1..A8 WRITE_READBACK=PASS lines.

Root cause in the research script: the passive Hammerspoon MIDI logger
deliberately records CCs from channels other than Scene 2. The early eight-
rotary poller treated every such event as a scene change, cleared the whole
poll including Scene 2 samples, and accumulated raw foreign-channel traffic
toward the 80-event limit. The other-channel source itself is still unknown:
real Scene 1 activity, wrong physical scene, or a duplicate/echo must be
distinguished from the local capture before enabling gain writing.

The update compacts channel traffic before the Resolve API poll. Other-scene
traffic generates one diagnostic reset, not a flood of log lines. In
**test-copy write mode, any other-channel event halts the entire session**,
rather than rearming and possibly writing amid conflicting scene signals.
Scene 2 streams are bounded to max 80 raw rotary events per poll; mixed
scene batches are discarded. All eight rotaries still require independent
fresh pickup. The general fail-closed safety boundaries have not been relaxed.

Before trying any more writes, run a READ-ONLY local MIDI log channel summary
in macOS Terminal (the logger's capture file must still be present):

~~~sh
python3 - <<'PY'
from collections import Counter
from pathlib import Path
source = Path.home() / "Library/Caches/nk-scene2-live-midi.csv"
c = Counter()
with source.open("r", encoding="ascii", errors="replace") as stream:
    for line in stream:
        bits = line.strip().split(",")
        if len(bits) != 3:
            continue
        try:
            ch, cc, value = (int(x) for x in bits)
        except ValueError:
            continue
        c[(ch, cc)] += 1
print("MIDI_LOG_ROWS", sum(c.values()))
for (ch, cc), amount in sorted(c.items()):
    print("CHANNEL", ch, "CC", cc, "COUNT", amount)
PY
~~~

This only reads a local event log. It does not print clip or project names,
and never calls any Resolve API or MIDI output. If most events show channel 0,
check that the Korg is physically in Scene 2 before a passive test; do not
silently remap input channel 0 to gain, because Scene 1 uses channel 0 for
transport and editing.

**After diagnosis:** redo the read-only 8-rotary run first, confirm real
Scene 2 channel=1 CC13..20 and successful independent pickup on more than
one strip, then consider a new explicitly approved test-copy write. Do not
reuse the stale /tmp version after GitHub changes; export the files again.


## 2026-10-24 second real dry-run: overactive raw MIDI guard

The operator refreshed the research branch and ran the multi-rotary controller
in read-only mode. The script printed:
- A1 PICKUP_PENDING; DB=0.000; NEAR_CC=70; WRITES=0
- SCENE2_8ROTARY=BLOCKED; excessive Scene2 MIDI rate; no blind writes

This is not a channel-routing failure. At least one valid ch1/CC13
(Scene 2 knob 1) reached the Resolve A1 clip. The failure was caused by
the prototype's 80-event-per-Resolve-poll raw MIDI cap. It incorrectly
treated **every MIDI packet**, even an identical repeated CC value, as a
distinct physical movement, and applied that bound even in read-only mode.
Actual transient rate and the number of duplicates in this specific run
are not known from the terminal output alone.

Fix on Draft PR #13:
- Raw CC packet count and **distinct physical CC-value changes** are
  counted separately. A run of repeated identical values is compacted
  and cannot trip the physical-movement limit.
- The original first+last per knob event accumulator remains bounded:
  at most two buffered CC samples per rotary for each poll.
- In **READ_ONLY** mode, a burst of >80 distinct CC-value changes only
  prints one MIDI_BURST=COALESCED diagnostic; it never aborts or writes.
  Some very rapid sweeps may miss the pickup point after coalescing,
  so make a slower small movement near NEAR_CC if pickup stays pending.
- In **WRITE TEST COPY** mode, >80 distinct CC changes in one poll still
  HALTS the entire writing session before processing that burst, with
  no blind gain writes. All prior per-clip readback and stale-context
  safety checks remain.
- Unit tests exercise 2,000 duplicate CC packets in a write-enabled
  test with no setters, 120 distinct CC steps in read-only mode without
  abortion, and 120 distinct CC steps in write mode causing HALT without
  setters.

**Next hardware acceptance:** refresh the local /tmp copy of the
8-rotary script and start a new passive Hammerspoon capture (the logger
uses a fresh CSV). First run READ_ONLY for two knobs on tracks with one
clip at the stopped playhead. Do not run the write-test-copy command until
PICKUP and SIMULATED_GAIN succeed for both rotaries without conflicts.
