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
