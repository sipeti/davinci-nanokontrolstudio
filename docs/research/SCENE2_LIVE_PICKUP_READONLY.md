# One live Scene 2 pickup test (NO audio writes)

This is an optional, disposable **A4 / rotary 4** end-to-end experiment.
It requires the user-proven external ResolvePython installation, Hammerspoon,
the Korg in Scene 2, and a **copied test project** with exactly one ordinary A4
audio clip at the stationary playhead. No audio keyframes; stop playback.
The script **does not contain a gain setter**. The faders stay disabled.

The working main controller, the existing 28-step binding, and install.command
are untouched. This test uses a separate passive MIDI object and one local event
log file in ~/Library/Caches.

## Safely extract just the test files (no git branch switch or install)

In Terminal:

~~~sh
cd ~/Projects/davinci-nanokontrolstudio || exit
git fetch origin
mkdir -p /tmp/nk-scene2-live
git archive origin/research/scene2-soft-takeover-offline \
  scripts/scene2_midi_bridge_probe.lua \
  scripts/scene2_live_pickup_readonly.py \
  scripts/scene2_soft_takeover.py | tar -x -C /tmp/nk-scene2-live
~~~

In **Hammerspoon Console** (one-time logger start):

~~~lua
dofile("/tmp/nk-scene2-live/scripts/scene2_midi_bridge_probe.lua")
~~~

Leave Hammerspoon open. In **Terminal**, in the already-working ResolvePython
environment (run **externally**, not inside Resolve Console):

~~~sh
ResolvePython /tmp/nk-scene2-live/scripts/scene2_live_pickup_readonly.py --track 4 --seconds 45
~~~

Turn **Scene 2 rotary 4** slowly through the printed PICKUP_NEAR_CC region
and move it a little further. This is only a simulated write intent.
Expected output:

~~~text
SCENE2_LIVE_PICKUP=START; A4; ...; WRITES=0
A4 PICKUP_PENDING; ...; WRITES=0
A4 PICKUP=PASS; ...; WRITES=0
A4 SIMULATED_INTENT_DB=...; NOT_APPLIED; WRITES=0
SCENE2_LIVE_PICKUP=PASS; WRITES=0; ...
~~~

End the logger in **Hammerspoon Console**:

~~~lua
if nkScene2LiveStop then nkScene2LiveStop() end
~~~

The logger also self-stops after two minutes. This test reads Resolve at most
five times a second when MIDI messages arrive, rather than one API call per
hardware message. On missing authority, changing target, ambiguous clip,
scene switch or large gain jump it fails closed. No setter is ever invoked.

**Important:** A successful test proves passive pickup only. It does not prove
automatic writing, external-change handling under all automation modes,
project safety during simultaneous edits, or actual mixer fader control. Do not
connect MIDI WRITE_INTENT to the existing writable round-trip test.
