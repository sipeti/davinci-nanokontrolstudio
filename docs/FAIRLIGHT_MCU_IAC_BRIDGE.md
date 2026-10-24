# Fairlight: Scene2 Assignable -> MCU/IAC (Draft PR #15)

**Status: offline-proven protocol prototype, physical hybrid not yet validated.**
The operator physically verified Korg nanoKONTROL Studio's **direct Pro
Tools/HUI** setup against Resolve 21 Fairlight on 24 October 2026:
real fader, mixer MUTE/SOLO and LED-return **all PASS**. PAN/BALANCE
worked partially and became disabled around range limits: **do not map
PAN**. The direct HUI success is not proof of this new MCU/IAC bridge.

## Target: no more MIDI mode switching in day-to-day use

- Physical nanoKONTROL in existing **Assignable** mode; Hammerspoon
  owns its Korg input ONCE. Scene1 edit/JOG/SHUTTLE and shared transport
  unchanged.
- Scene2 rotary CC13..20 -> the existing independent **audio CLIP gain**
  Python controller (Draft PR #14). No rotary MCU pan.
- Scene2 physical linear faders -> *actual* Fairlight mixer TRACK faders.
  Scene2 physical MUTE/SOLO -> mixer MUTE/SOLO.
- Hammerspoon only exposes hardware Scene2 events (CCs) on the existing
  passive file bridge. **Python mido/python-rtmidi** converts these to
  MCU messages on two distinct macOS IAC virtual ports.
- The return channel from Resolve's MCU output is authoritative:
  MCU pitch-bend = current 14-bit mixer fader position, MCU note LED
  feedback = current MUTE/SOLO state. Only host feedback can set Korg
  Scene2 MUTE/SOLO LEDs (not a physical key echo).

## Candidate Korg Scene2 Assignable CC map — READ FIRST

The current Scene1 hardware configuration already confirms:
- Physical Scene1 Slider1: CC2.
- Physical Scene1 MUTE1..8: CC21..28.
- The Scene1 LED registry reserves SOLO1..8:
  **CC29, CC30, CC31, CC33, CC34, CC35, CC36, CC37**, skipping CC32.
- Scene2 rotary CC13..20, Hammerspoon zero-based input channel 1,
  verified in previous Scene2 physical tests.

**The complete slider/solo physical mapping on Assignable Scene2 is
a candidate until the user captures these buttons on Scene2.**
The converter fails closed for unknown CCs and is READ_ONLY by default.
The Korg's global Pro Tools/HUI operating mode must be switched back
to Assignable before the candidate physical map can be used.

MCU protocol maps (supported by Resolve 21 Fairlight):
- Faders 1..8 -> 14-bit MIDI pitchbend on channels 0..7 (mido zero-based).
- SOLO1..8 -> MCU note 0x08..0x0F, channel 0.
- MUTE1..8 -> MCU note 0x10..0x17, channel 0.
- Host note feedback is the ONLY LED authority.
- Every fader needs genuine host pitch position feedback and fresh
  physical pickup first. Movement/step limits and host ACK are mandatory.
  No host feedback means **no fader write**, not an inferred 0 dB.

## Step 1: Return from the successful direct HUI test

1. Record the currently working Resolve HUI MIDI settings (screenshot).
2. In Resolve Preferences > System > Control Panels, disable the
   direct physical-Korg MIDI Audio Console and Save.
3. Quit Hammerspoon if open. Turn Korg off, hold SCENE+CYCLE while
   powering it on -> **Assignable** mode.
4. Relaunch Hammerspoon only after switching mode, verify Scene1 JOG.
   The current Hammerspoon init.lua loads ONLY
   require("nanokontrol_resolve21"). Its hs.settings 28/28 calibration
   must remain untouched; DO NOT rerun the 28-step wizard.

## Step 2: Two macOS IAC ports

Audio MIDI Setup.app > Window > Show MIDI Studio > IAC Driver:
enable **Device is online**, then create TWO buses:
- **NK FL To Resolve** (Python MCU output -> Resolve MIDI Input)
- **NK FL From Resolve** (Resolve MIDI Output -> Python MCU feedback input)

The IAC buses are for MCU protocol ONLY. The original Korg MIDI port
stays exclusively owned by Hammerspoon; never select the physical Korg
as Resolve's direct MIDI audio console at the same time.

Create isolated Python venv (no system Python package modifications):

~~~sh
/opt/homebrew/bin/python3 -m venv /tmp/nk-mcu-venv
/tmp/nk-mcu-venv/bin/python3 -m pip install mido python-rtmidi
~~~

List the EXACT MIDI names seen by mido (OS names vary):

~~~sh
/tmp/nk-mcu-venv/bin/python3 \
  /tmp/nk-scene2-mcu/scripts/fairlight_mcu_bridge.py \
  --list-midi-ports
~~~

In Resolve Preferences > System > Control Panels, enable
Use MIDI Audio Console, select **MCU compatible**, MIDI Input =
the IAC bus **To Resolve**, MIDI Output = IAC bus **From Resolve**;
Save and restart Resolve once. These are distinct from Korg physical
MIDI endpoints.

## Step 3: Review and install only the tested Hammerspoon controller

**Not automated by Draft PR.** Current user setup is:
- ~/.hammerspoon/init.lua -> require("nanokontrol_resolve21")
- ~/.hammerspoon/nanokontrol_resolve21.lua is the sole live controller
- Multiple existing dated backup files; leave them intact.

After checking final CI, prepare *only temporary* staged code:

~~~sh
cd ~/Projects/davinci-nanokontrolstudio || exit 1
git fetch origin
mkdir -p /tmp/nk-scene2-mcu
git archive origin/feature/scene2-mcu-fairlight-bridge \
  nanokontrol_resolve21.lua \
  scene2_clip_gain_bridge.lua \
  scripts/fairlight_mcu_bridge.py \
  | tar -x -C /tmp/nk-scene2-mcu
~~~

Backup current controller and review diff before any installation:

~~~sh
cp -p "$HOME/.hammerspoon/nanokontrol_resolve21.lua" \
  "$HOME/.hammerspoon/nanokontrol_resolve21.lua.pre-mcu.$(date +%Y%m%d-%H%M%S)"
diff -u "$HOME/.hammerspoon/nanokontrol_resolve21.lua" \
  /tmp/nk-scene2-mcu/nanokontrol_resolve21.lua || true
~~~

Only after approving that diff, replace the ONE loaded controller
and place the helper in ~/.hammerspoon, leaving init.lua unchanged:

~~~sh
cp /tmp/nk-scene2-mcu/nanokontrol_resolve21.lua \
  "$HOME/.hammerspoon/nanokontrol_resolve21.lua"
cp /tmp/nk-scene2-mcu/scene2_clip_gain_bridge.lua \
  "$HOME/.hammerspoon/scene2_clip_gain_bridge.lua"
~~~

Reload Hammerspoon ONCE (do not load a second copy through the Console).
Check exactly one NK JOG menu. The Scene2 bridge is OFF by default.
Switch it ON from NK JOG only for controlled testing, then start Python.

## Step 4: First physical MCU bridge test (NO MIDI sends)

With Resolve open on a backed-up disposable Fairlight test project,
foreground and playback stopped; IAC configured, bridge ON in Hammerspoon,
run an observe-only session. Substitute the exact names from
--list-midi-ports; this is deliberately not a blindly copy-pasteable
command with guessed port names:

~~~sh
/tmp/nk-mcu-venv/bin/python3 \
  /tmp/nk-scene2-mcu/scripts/fairlight_mcu_bridge.py \
  --input-port "EXACT IAC FROM RESOLVE PORT FROM LIST" \
  --output-port "EXACT IAC TO RESOLVE PORT FROM LIST" \
  --seconds 60
~~~

Move **Scene2 slider1** and press/release **MUTE1** then **SOLO1**.
The log should see MCU FADER_PICKUP_PENDING/PASS and
MCU_BUTTON_PREVIEW if the actual candidate Scene2 CC map matches.
**READ_ONLY never calls mido.send**, even after pickup.

If output says WAIT_FOR_FAIRLIGHT_POSITION or
WAIT_FOR_FAIRLIGHT_LED, the MCU host feedback is not initialized/visible.
**Do not bypass the guard.** Check IAC direction and protocol choice.
The physical MIDI knob PAN in HUI mode is out of scope.

## Step 5: Actual MCU writes on disposable copy only (not yet approved)

After read-only captures and exact map confirmation:
- Keep the same distinct IAC input/output names and test project.
- Use --enable-output and the explicit string:
  --consent "I CONFIRMED A BACKED-UP DISPOSABLE FAIRLIGHT PROJECT"
- Move only one mixer fader after pickup, inspect the **track mixer fader**
  in Resolve, then try one MUTE/SOLO and observe both directions of LED.
- Unexpected fader jump, track-bank mismatch, missing LED/state feedback
  or lost heartbeat => STOP and revert to READ_ONLY immediately.

There is NO continuous production deployment and NO main merge.
The fader reports are absolute 7-bit physical CC scaled to MCU 14-bit;
this is a non-motor Korg and requires soft pickup, unlike a motorized MCU.

## Physical hardware acceptance (24 October 2026)

**A1 FADER PHYSICALLY MOVED**: the operator observed the Fairlight A1 mixer
fader visibly respond to a *single* Korg Scene2 Slider1 movement through
Hammerspoon -> Python -> IAC MCU -> Resolve. MCU TOUCH note104, channel0
pitchwheel, and RELEASE were emitted once on backed-up disposable
`hajoagyu_261022 testing`. MIDI host feedback returned a *nonmatching*
value; this is NOT an authoritative acknowledgment, but visual motion is
authoritative evidence that the control path works. Do not repeat the A1
one-shot just to get a matching MIDI echo.

The later 500ms touch-hold Python revision was installed into the operator's
temporary test location (`FAIRLIGHT_TOUCH_500MS=READY`), but has NOT yet been
physically tested; do not claim validation for that timing.

**MUTE/SOLO READ_ONLY PASS**: host MCU note16 (MUTE1) and note8 (SOLO1)
feedback; physical Scene2 CC21/CC29 input; and Python
`MCU_BUTTON_PREVIEW` were independently observed. The actual physical
MUTE/SOLO output command is NOT yet proven.

### Next finite test: one MCU A1 MUTE or SOLO button

Draft supports `--one-shot-button mute1` or `--one-shot-button solo1`
**instead of** the fader test. Both are mutually exclusive, and the
default stays READ_ONLY. Write mode requires explicit consent, a
saved/disposable project, and a finite <=60s session. Only the explicitly
selected Scene2 physical key may cause MIDI output: MUTE1 = CC21/note16,
SOLO1 = CC29/note8. The program refuses all faders and other buttons.
Before sending, it requires an actual Fairlight LED note for the selected
button received less than 10s ago. One valid key press sends note_on (127),
then one note_off (0) after 80ms; the release also runs during cleanup.
No repeats even if the Korg reports more input. Only a changed note from
Fairlight verifies the new mixer state.

For the first MUTE1 trial, with Korg Assignable/Scene2 and Hammerspoon's
Scene2 bridge already ON, open the operator's backed-up test project,
stop playback and disable automation write. Run:

~~~sh
/tmp/nk-mcu-venv/bin/python3 \
  /tmp/nk-scene2-mcu/scripts/fairlight_mcu_bridge.py \
  --input-port "IAC Driver NK FL From Resolve" \
  --output-port "IAC Driver NK FL To Resolve" \
  --seconds 45 \
  --one-shot-button mute1 \
  --enable-output \
  --consent "I CONFIRMED A BACKED-UP DISPOSABLE FAIRLIGHT PROJECT"
~~~

Then *without switching focus back to Terminal*, use the **Fairlight
UI** A1 MUTE control to toggle ON then OFF (so the mixer ends unmuted and
a fresh note16 feedback is established); immediately press the physical
**Korg Scene2 MUTE1** once. Let the script stop. Visually check whether
A1 MUTE engaged; the MCU host may fail to echo the button even if it acted.
Use the UI to restore the previous mute status after the test. Do not
restart the one-shot on unexpected state/track changes. A separate SOLO1
trial changes only the CLI flag to `--one-shot-button solo1`, requires
a fresh note8 from clicking the on-screen A1 SOLO first, and should only
be attempted after MUTE1 acceptance.

During a finite one-shot process the LED return can briefly illuminate
the physical Scene2 LED; the script intentionally emits a false heartbeat
on exit and clears it. **Persistent host-authoritative LED state requires
a later continuously running bridge**, not a one-shot test.

## Scene2 continuous mixer: one finite bench session (Draft only)

**Already physically proved, and NOT requiring further isolated measurements:**
Korg Scene2 physical fader1 -> Fairlight A1 moves visibly; Korg Scene2
MUTE1 CC21 / SOLO1 CC29 -> Fairlight actual note16/note8 state transitions
with host feedback acknowledgments. The operator also observed the physical
Korg MUTE1 LED flash once during the built-in LED probe, while one-shot
MUTE/SOLO trials did not leave it lit.

**Why LED could not stay lit:** one-shot Python exits immediately after an
ACK and writes feedback heartbeat H=0, so Hammerspoon clears its LED cache.
The original Scene2 Lua callback used only output MIDI channel 1; earlier
physical Korg tests had confirmed that a broadcast (channel 0) can light
the MUTE1 LED. The 2026-10-25 integrated 90s physical bench confirmed that
MUTE/SOLO commands work but **neither hardware LED lit**. A subsequent
read of the actual source revealed the live script logged outgoing buttons
but **did not log any incoming host MIDI note/LED events**, so there was
not yet enough evidence to tell missing Fairlight feedback from dropped
Korg output. The current Draft sends the SAME host-authoritative CC state
on both possible Korg output routes (0 and 1), gated by physical Scene2
ownership, and logs one sparse `[NK SCENE2 LED TX]` per CC state change;
it also logs `[NK SCENE2 LED RX]` when Fairlight note feedback was actually
parsed. LEDs are reasserted every 500ms while the host heartbeat is live,
cleared on stop/focus loss, and blanked on first Scene1/3/4/5 CC *before*
revoking Scene2 ownership (cached Fairlight host state is retained for
restoration when Scene2 comes back). This is an offline-tested fix, not yet
a physical LED acceptance.

The new continuous Python script also reports
`MCU_LIVE_HOST_RX`, `MCU_LIVE_HOST_FADERS`, and
`MCU_LIVE_HOST_LED_EVENTS` at shutdown. Previously each single MIDI
movement of locked strip8 CC9 generated a full `BUS1_STRIP8_LOCKED`
line, burying useful observations; it now prints that status once per CC
and summarizes the totals. Because Korg SCENE selection is silent, the
current scene can only be known after its first physical CC input.

### MCU startup identity response (opt-in, no gain write)

The October 25 integrated run **PHYSICALLY PASSED Korg MUTE/SOLO LEDs**,
but faders remain blocked: actual host MIDI input contained
`note_on:25,sysex:69,pitchwheel:0`. In an earlier raw Fairlight-to-IAC
capture, repeated SysEx payload was exactly `(126,0,6,1)`, the MIDI
Universal Identity Request (`F0 7E 00 06 01 F7`). The current
software-only Mackie bridge did not answer it. An MCU device may need
to identify itself before the host sends the initial motor fader
positions; this is a **hypothesis, not yet a validated Resolve-21
behavior**. Do NOT bypass soft pickup or supply invented gain values.

To isolate that hypothesis in the *existing single integrated bench*,
the continuous script now has an **explicit opt-in**
`--reply-mcu-identity`. It is only accepted with
`--enable-output` and the exact disposable-project consent already
required for mixer testing. It matches ONLY the previously captured
identity request payload `7E 00 06 01` (device ID 00), and replies
with the standard MCU manufacturer/family identity payload a maximum
of **three times**, spaced at least 1 second apart. Other SysEx is
ignored. The reply is neither a fader motion nor authoritative position.
No other MIDI initialization, bank change, motor move or gain write
is synthesized. READ_ONLY with no flag continues to transmit ZERO MIDI.
No autostart or update to the Korg Scene1 settings.

For a test copy of `hajoagyu_261022 testing` with playback stopped,
MIDI control configured for MCU, and the Hammerspoon Scene2 bridge
explicitly ON **after the most recent `hs.reload()`**, add one flag to
the already functioning 60s continuous command:

```sh
  --reply-mcu-identity
```

Observe `MCU_LIVE_IDENTITY=requests:N,replies:M,mode:enabled`
and `MCU_LIVE_HOST_FADERS=strip1:N,...` at finish. If identity reply
elicits valid MCU `pitchwheel` feedback, physical Korg fader must
still cross that actual feedback value before any mixer MIDI write.
If no pitchwheel is received, **STOP automatic fader enablement**;
this experiment did not establish bootstrapping. Moving the *Fairlight
on-screen* fader while the process runs can seed an actual position
(as demonstrated in prior one-shot acceptance), but that is a manual
workaround rather than a clean MCU boot protocol. Do not claim
continuous fader setup is complete in either case until observed.

**Host initial faders:** the same continuous bench showed
`FADER_WAIT_HOST` on faders 1..7 and no observed physical pickup.
The script refuses to guess mixer gain positions; it will not move a
fader until a real MCU pitchwheel position has been received for that
strip. A Fairlight on-screen fader movement during the active run can
seed this state. No automated initial-state MCU query has been verified.

The separate opt-in script
\`scripts/fairlight_mcu_continuous.py\` is a bounded (max 180-second)
single-owner **bench** controller using the same existing Hammerspoon
event CSV and both IAC ports. Normal launch is READ_ONLY; MIDI writes
require \`--enable-output\` plus the pre-existing disposable project consent.
There is **no production autostart, no merge to main, and no permanently
enabled global Korg/Resolve hook**. It is tested in CI but **has not yet
received physical continuous-mode acceptance**.

In the current screenshot the Fairlight mixer shows **7 audio tracks and
Bus 1 at strip 8**. The 8th hardware strip MAY work as Bus1 for this
specific MCU bank; it is **not a persistent/pinned master mapping**.
DaVinci supports moving the MCU bank to other channels and masters.
Therefore CC9 fader8, CC28 MUTE8, and CC37 SOLO8 are BLOCKED by default.
The deliberate \`--enable-strip8-bus1\` option unlocks strip8 **only for
the currently open, manually confirmed mapping**, not across projects.

Test project only, transport stopped, audio outputs safe, automation write
disabled, original Hammerspoon Scene2 bridge ON, and the new Lua route
deployed with a guard/backups. Use ONE live MIDI process; do not run any
one-shot or separate read-only Python bridge at the same time.

~~~
/tmp/nk-mcu-venv/bin/python3 \
  /tmp/nk-scene2-mcu/scripts/fairlight_mcu_continuous.py \
  --input-port "IAC Driver NK FL From Resolve" \
  --output-port "IAC Driver NK FL To Resolve" \
  --seconds 90 \
  --enable-output \
  --consent "I CONFIRMED A BACKED-UP DISPOSABLE FAIRLIGHT PROJECT"
~~~

The script sends:
- Soft-pickup physical Scene2 CC2..8 -> MCU 14-bit pitchbend strips1..7,
  with touch note104..110, coalesced at ~30Hz and released 500ms after
  motion; no blind fader jumps without initial real host position.
- Physical Scene2 MUTE CC21..27 -> MCU notes16..22; physical SOLO CC29,
  30,31,33..36 -> MCU notes8..14. Each press emits ONE momentary key
  down and scheduled key up (80ms), while host MIDI note feedback alone
  decides LED state. No physical-button LED echo or guessed state.
- On focus loss, scene change, MIDI failure, SIGINT, host heartbeat loss,
  or 90s auto-stop, best-effort MCU releases and H=0 LED clearing.

The 8th strip is deliberately unused during the first integrated bench.
Do not infer that Bus1 will always be hardware channel8 in other projects.
A separate MCU hardware Master Fader is a ninth pitch channel/note112
and is NOT emulated by this 8-fader Korg mapping.

**Next gate is a single integrated live bench acceptance**, not another
round of one-button calibration: confirm A1 fader works continuously,
MUTE1/SOLO1 both switch Fairlight, and their hardware LEDs reflect host
state for as long as the bridge is running. Do not claim pass before
the operator sees it; leave Draft until then.

## Source refs

- Blackmagic Resolve 21 manual: third-party HUI/MCU consoles:
  https://docs.imaster.org/davinci-resolve-21-manual/part-13-fairlight/ch.-177-mixing-in-the-fairlight-page
- Hammerspoon MIDI output and zero-based input channels:
  https://www.hammerspoon.org/docs/hs.midi.html
- Mackie Control note, fader pitchbend and LED feedback:
  https://github.com/NicoG60/TouchMCU/blob/main/doc/mackie_control_protocol.md
- Hammerspoon IAC MIDI driver workaround:
  https://github.com/Hammerspoon/hammerspoon/discussions/3379

**Rollback:** disable Resolve MIDI Audio Console, quit/stop Python,
turn OFF NK Scene2 bridge in Hammerspoon, restore the timestamped
pre-mcu nanokontrol_resolve21.lua backup and restart Hammerspoon ONCE.
The Korg remains in Assignable mode, no Korg scene data was changed.
