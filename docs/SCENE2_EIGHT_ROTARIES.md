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
