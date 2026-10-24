# Scene 2 continuous clip gain (Draft PR #14)

**Status: research / not installed / DO NOT MERGE into main automatically.**
Stacks on eight-rotary hardware research Draft PR #13. A4 and A5 have
five operator-verified AudioVolume SetProperties/readback writes between them.
Full A1-A8, continuous operation and menu integration need fresh hardware
acceptance before deployment.

## Contract

Korg nanoKONTROL Studio Assignable Scene 2 (input MIDI channel 1),
rotaries CC13-20 -> one audio CLIP at stopped playhead on A1-A8.
Per-strip physical pickup before any write. New clip, out-of-band
gain, changed project/timeline/playhead, focus loss or scene switch must
REARM. Idle gap >20s also rearms. One setter step <=1.2 dB, and the playhead, clip and current
gain must remain stable over a real 120ms observation before the setter;
then another fresh snapshot and immediate readback. A failed setter
triggers restoration attempt and HALT (a failed pre-setter stability
gate halts without attempting a write).
No gain automation/keyframes. No fader or mixer manipulation.

**Not Fairlight track mixer gain, mute, solo, nor authoritative LEDs.**
SetTrackEnable is NOT equivalent to Fairlight mixer MUTE and cannot be
used as a substitute. Linear faders stay reserved for actual mixer tracks.

## Input bridge (single MIDI callback owner)

Optional helper scene2_clip_gain_bridge.lua is loaded by the updated
nanokontrol_resolve21.lua *only* when it exists in hs.configdir.
It opens no extra hs.midi.new device and never sends MIDI or edits Resolve.
An NK JOG menu entry is OFF by default and must be explicitly enabled.
It writes timestamped CC data, scene reset and 0.5s foreground heartbeat
to ~/Library/Caches/nk-scene2-controller-events.csv.

The Python reader starts at EOF to prevent replay. It rejects input
older than 1.2s/future dated, detects lost heartbeat (>2.5s), log
restart/replacement, >2048 rows per poll and excessive changed CC steps.
Scene and focus transitions clear *all* pickup positions. Resolve remains
the required foreground application while using the scene gain bridge.

## DO NOT install on the working Hammerspoon without review

Identify the live ~/.hammerspoon/init.lua entrypoint and the loaded
nanokontrol_resolve21.lua path first. Back up the current files. Loading
two copies of the controller would create duplicate MIDI owners and is
forbidden. Once reviewed, deploy the Draft #14 controller **instead of**
the previous installed controller, place the helper in hs.configdir and
reload once. The 28/28 hs.settings calibration remains unchanged.
Keep the optional Scene 2 bridge OFF until ready to test.

## Copy Python files to a temporary test directory

~~~sh
cd ~/Projects/davinci-nanokontrolstudio || exit 1
git fetch origin
mkdir -p /tmp/nk-scene2-continuous
git archive origin/feature/scene2-continuous-clip-gain \
  scripts/scene2_audio_roundtrip_probe.py \
  scripts/scene2_live_pickup_readonly.py \
  scripts/scene2_soft_takeover.py \
  scripts/scene2_clip_gain_8rotary.py \
  scripts/scene2_continuous_clip_gain.py \
  | tar -x -C /tmp/nk-scene2-continuous
~~~

After integrated menu bridge explicitly ON, Korg physically Scene 2,
Resolve frontmost on Edit page, playback STOPPED and disposable clean
audio clips at A4 and A5 under the playhead, run READ_ONLY:

~~~sh
PYTHONPATH="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules" \
/opt/homebrew/bin/python3 \
  /tmp/nk-scene2-continuous/scripts/scene2_continuous_clip_gain.py \
  --seconds 90
~~~

Expect per-strip PICKUP_PENDING -> PICKUP=PASS -> SIMULATED_GAIN,
plus SCENE2_CONTINUOUS=COMPLETE; VERIFIED_WRITES=0. Verify separately:
playhead switch -> new pickup; physical Scene1 and back -> new pickup;
focus change and back -> fresh pickup. User must report hardware results.
No source media names or stable IDs are written to the MIDI CSV.

Duration is optional; --seconds 0 (default) runs until Ctrl+C.
The bridge stays enabled until explicitly toggled OFF; it never launches
the Python process. The read-only mode never performs a Resolve setter.

## Test-copy writing only after integrated READ_ONLY physical PASS

For a manually BACKED-UP, disposable test project only; no gain keyframes
or Fairlight automation (the API cannot authoritatively verify this).
Actual consent is explicit, and the project name must match exactly.

~~~sh
PYTHONPATH="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules" \
/opt/homebrew/bin/python3 \
  /tmp/nk-scene2-continuous/scripts/scene2_continuous_clip_gain.py \
  --seconds 90 \
  --write-test-copy \
  --expected-project "YOUR BACKED-UP TEST COPY NAME" \
  --confirmed-no-automation \
  --max-writes 2 \
  --consent "YES, THIS IS A BACKED-UP TEST PROJECT"
~~~

Success persists; no automatic rollback on successful edits. The
--max-writes cap covers the entire session (1..256), not each knob.
A failure attempts restoration and HALTS; inspect the clip manually.
Never assume a successful write was restored. NO production writes,
startup services, launches or main merges are approved by this Draft.

## Mixer/fader/mute/solo roadmap: independent research gate

Resolve 21 public scripting catalogs expose audio-track enable/lock,
but do not provide a proven read/write API for true Fairlight mixer
fader gain or SOLO. Evaluate supported control-surface protocols such
as HUI/Mackie and verify state readback before any physical-fader,
MUTE/SOLO or status-LED mapping. Do not infer mixer state from MIDI
button presses or call track enable a mixer MUTE.
