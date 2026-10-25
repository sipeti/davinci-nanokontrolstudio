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
then another fresh snapshot and immediate readback. After verified pickup,
every changed absolute CC maps directly to clip gain (existing -100..+30 dB
range) without an artificial per-event 1.2 dB cap. Crossing the host gain
in a fast physical movement can commit the final CC immediately. No
interpolated gain, stale replay or queued writes. A failed setter
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

## Fairlight native MIDI mixer: verified protocol, separate workstream

**Architecture verified by published documentation, NOT yet locally
tested** on this operator's current Resolve/Korg installation (2026-10-24).

- The DaVinci Resolve 21 manual documents **Use MIDI Audio Console** under
  Preferences > System > Control Panels, with **HUI or MCU**, MIDI Input
  and MIDI Output selections. These protocols support actual Fairlight
  mixer **track faders, MUTE, SOLO, PAN** and transport.
  https://docs.imaster.org/davinci-resolve-21-manual/part-2-setup-and-workflows/ch.-4-system-and-user-preferences
  https://docs.imaster.org/davinci-resolve-21-manual/part-13-fairlight/ch.-177-mixing-in-the-fairlight-page
- The Korg nanoKONTROL Studio owner's manual specifies its hardware
  **Pro Tools/HUI** mode: hold **SCENE + REW** while switching it on.
  Korg Assignable mode uses **SCENE + CYCLE** at power on. The mode is
  persistent and GLOBAL to the controller, not a per-scene mapping.
  https://www.korg.com/us/support/download/product/0/552/
  https://support.korg.co.uk/en-US/using-the-nanokontrol-studio-with-logic-in-assignable-mode-405741
- A Korg user independently reported working faders, mute, solo and
  LED feedback with Fairlight and Korg in Pro Tools/HUI mode:
  https://forum.blackmagicdesign.com/viewtopic.php?p=1074485&t=192108
  This community report is not a guarantee for this installation.

Therefore do NOT claim direct HUI can coexist with current Scene1 JOG
and Scene2 clip gain while the Korg remains in Assignable mode.
Do NOT set Resolve's MIDI Audio Console input/output to the physical
Korg while the current Hammerspoon handler is active: shared input
and bidirectional LED feedback could conflict.

**Low-risk hardware proof option (operator action, no automatic change):**
1. Record the existing Resolve Control Panels settings and back up
   Korg KONTROL Editor/global assignments.
2. Quit Hammerspoon COMPLETELY (not just pause its MIDI menu),
   stop any Python gain worker, use a disposable Resolve test project.
3. Switch off Korg. Hold SCENE+REW while powering on to enter HUI.
4. In Resolve Preferences > System > Control Panels, enable Use MIDI
   Audio Console, select HUI and nanoKONTROL Studio MIDI IN/OUT.
   Restart Resolve if the surface does not initialize.
5. On the FAIRLIGHT page of the test copy, try one real TRACK mixer
   fader and MUTE/SOLO, then change the corresponding mixer UI state
   and check the Korg LED follows the software (authoritative feedback).
6. To return: disable the MIDI Audio Console setting; switch Korg
   back to Assignable (power on with SCENE+CYCLE), then start Hammerspoon.
   Check Scene1 JOG/SHUTTLE and the stored 28/28 setup again.

**Preferred eventual hybrid** (only after direct HUI proof):
Keep the physical Korg in its existing Assignable mode and preserve ONE
Hammerspoon hardware MIDI callback. Scene1 keys/transport stay with the
working Hammerspoon controller, Scene2 rotary CC13..20 remain clip-volume
API targets. Scene2 linear faders/mute/solo would be translated to an
MCU/HUI **virtual MIDI port** (macOS IAC Driver) selected as Fairlight's
MIDI Audio Console input/output. The translator MUST also accept Fairlight
feedback for authoritative mute/solo LEDs and mixer state; HUI may
require active handshake/keepalive, and 7-bit physical controls need
careful pickup/14-bit protocol handling. An IAC MIDI bus alone does not
implement HUI/MCU semantics. This is RESEARCH, not a working bridge.

**Do not** substitute SetTrackEnable for mixer MUTE, set LEDs solely
from physical presses, or merge/install this capability until direct
hardware verification and independent bidirectional offline tests pass.

Known current live Hammerspoon entrypoint from operator:
~/.hammerspoon/init.lua contains only require("nanokontrol_resolve21"),
and its active module is ~/.hammerspoon/nanokontrol_resolve21.lua.
The existing backup files are retained. DO NOT overwrite the active
controller yet or create another hs.midi listener.
