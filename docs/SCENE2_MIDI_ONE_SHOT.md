# Scene 2 A4 — one physical MIDI write + immediate restore (TEST COPY ONLY)

**Release status: research / Draft; never installed.** This is the next gate
after the verified user-side passive pickup test on 2026-10-24
(PICKUP=PASS, simulated intent, WRITES=0; 248 passive MIDI events).

This experiment writes **one** bounded A4 clip AudioVolume value only after
physical knob 4 pickup and explicit authorization, checks the Resolve API
readback, and **immediately restores the original gain**. It does NOT provide
permanent MIDI control. Do not test with live production or a timeline that has
clip gain keyframes or automation. Stop playback. Save a disposable project copy
with a name including TEST, COPY, BACKUP, QA, teszt or másolat.

## Prepare without branch switching or installation

In macOS Terminal:

~~~sh
cd ~/Projects/davinci-nanokontrolstudio || exit 1
git fetch origin
mkdir -p /tmp/nk-scene2-one-shot
git archive origin/research/scene2-midi-one-shot-roundtrip \
  scripts/scene2_midi_bridge_probe.lua \
  scripts/scene2_live_pickup_readonly.py \
  scripts/scene2_audio_roundtrip_probe.py \
  scripts/scene2_soft_takeover.py \
  scripts/scene2_midi_one_shot_roundtrip.py | tar -x -C /tmp/nk-scene2-one-shot
~~~

Do NOT use install.command, switch local branches, or reload the main Lua driver.

In Hammerspoon Console, start the **passive** MIDI logger:

~~~lua
dofile("/tmp/nk-scene2-one-shot/scripts/scene2_midi_bridge_probe.lua")
~~~

The logger automatically stops after two minutes and only writes a cache
CSV of MIDI events. A restart clears that event file.

## Default no-write rehearsal (optional)

In **macOS Terminal**, not the Resolve Py3 console:

~~~sh
PYTHONPATH="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules" \
/opt/homebrew/bin/python3 \
/tmp/nk-scene2-one-shot/scripts/scene2_midi_one_shot_roundtrip.py \
--seconds 45
~~~

Turn Scene 2 physical rotary **4** slowly through the printed
PICKUP_NEAR_CC target, then slightly further. Output:
A4 PICKUP=PASS, A4 INTENT_DB=..., SCENE2_MIDI_ROUNDTRIP=PASS;
SIMULATED_ONLY; WRITES=0.

## Explicit disposable-copy write/restore acceptance

Only if the project is a **backed-up disposable test copy**, the playhead is
stationary over exactly one ordinary **A4** audio clip, and the Inspector gain
is noted and has **no keyframes/automation**:

1. Restart the Hammerspoon passive logger if necessary.
2. Copy the **exact active test-copy project name** from Resolve.
3. Run the following command with its placeholder replaced by that name.
   Typing the consent phrase is an intentional authorization for this one run.

~~~sh
PYTHONPATH="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules" \
/opt/homebrew/bin/python3 \
/tmp/nk-scene2-one-shot/scripts/scene2_midi_one_shot_roundtrip.py \
--seconds 45 \
--write-once \
--expected-project "YOUR EXACT TEST COPY PROJECT NAME" \
--consent "YES, THIS IS A BACKED-UP TEST PROJECT"
~~~

Turn physical Scene 2 rotary 4 slowly through pickup and just one small MIDI
step further. Only the **first** eligible WRITE_INTENT is considered.
The target must stay unchanged, and the delta must exceed 0.055 dB but be
no more than **0.6 dB**. All context IDs, frames, clip bounds, original gain,
and project name are rechecked twice before any setter call.

Expected:
~~~text
A4 PICKUP=PASS; ...; WRITES=0
MIDI_WRITE=ARMED; ...
MIDI_TEST_WRITE_READBACK=PASS
RESTORE_VERIFIED=True
SCENE2_MIDI_ROUNDTRIP=PASS
~~~

Visually confirm in Resolve Inspector that A4 is still at its exact original
gain. In any FAIL, BLOCKED or RESTORE_VERIFIED=False case, do not retry blindly;
inspect the clip and manually restore ORIGINAL_DB if needed. In case of a crash,
recover from the test-project backup.

Stop only the passive logger in Hammerspoon:
~~~lua
if nkScene2LiveStop then nkScene2LiveStop() end
~~~

**Safety boundary:** This is NOT a general MIDI volume controller. It neither
enables live MIDI setters nor changes Scene 1, JOG/SHUTTLE, LEDs, track faders,
mute/solo, bindings or main. A full control loop requires separate safety
tests for external edits, scene switching without detectable MIDI, gap/overlap,
linked clips, automation and disconnect handling.
