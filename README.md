# Korg nanoKONTROL Studio for DaVinci Resolve 21

A lightweight, keyboard-driven MIDI control surface for **DaVinci Resolve 21 on macOS**, implemented in **Hammerspoon/Lua**. Use the Korg nanoKONTROL Studio to jog through frames, shuttle playback, navigate edits, trigger common editing shortcuts, and see transport status on the controller LEDs.

**Tested on real hardware:** nanoKONTROL Studio in USB / Assignable Mode, DaVinci Resolve Studio 21, and Hammerspoon. The script does **not** emulate Mackie Control/HUI and does **not** require Resolve's scripting API.

[Full button, CC, knob and fader mapping](docs/CONTROL_MAP.md)

## What works

- **Scene 1 — editing:** frame-by-frame JOG; edit-point trim; Cut/Edit page shortcuts; camera-number keys; In/Out, split and navigation shortcuts.
- **JOG / SHUTTLE:** CYCLE changes modes. In SHUTTLE, one wheel pulse moves one signed speed step from −4 to +4. Rapid pulses are batched for 45 ms to avoid restarting J/K/L on every event.
- **Transport:** STOP, PLAY, REW, FF, return to start and previous/next edit work across **all five scenes** when they use the configured CCs and MIDI channels.
- **Shared speed state:** STOP = 0; normal forward = +1; FF = +2; reverse = −1. FF → PLAY or FF → one wheel tick left returns to +1. A second PLAY at normal speed pauses.
- **Fader 1:** center-zero SHUTTLE (−4…+4). It must first pass through the center (CC values 60–68) to become active, preventing sudden playback on startup.
- **External LEDs:** persistent PLAY / STOP / REW / FF indicators, plus the CYCLE mode LED. Momentary feedback on other known buttons; scene switching restores shared LED state. The five shared status CCs are sent on both the previously verified Scene 1 route and a separate Scene 2 output route. **Scene 2 also requires External LED Mode written to the device.**
- **Keyboard cooperation:** when Resolve is frontmost, physical Space/J/K/L presses are observed without being blocked. Hammerspoon-generated keystrokes are not counted a second time.
- **One guided 28-step setup** stores a complete MIDI mapping only after all steps succeed. Subsequent script updates do not require relearning.

**Current scope:** Only Scene 1 has editing actions, JOG wheel and Fader 1 mappings. Scenes 2–5 share the transport/navigation strip; their other controls are intentionally unassigned. The Scene 2–5 wheel configurations in the analyzed Korg setup use a different Continuous/CC86 mode and are **not** interchangeable with the Scene 1 Sign Magnitude jog.

## Requirements

- macOS with [Hammerspoon](https://www.hammerspoon.org/) installed.
- DaVinci Resolve 21 (tested with the Studio edition).
- Korg nanoKONTROL Studio, connected over USB in **Assignable Mode**.
- [KORG KONTROL Editor](https://www.korg.com/us/support/download/software/0/552/1355/) for configuring and writing the controller's scenes.
- Hammerspoon **Accessibility** permission; **Input Monitoring** may also be necessary for observing physical Space/J/K/L.
- A Resolve keyboard shortcut layout compatible with the commands below. Custom shortcuts may need adjustment.

For a public installation, you can clone the repository:

~~~sh
git clone https://github.com/sipeti/davinci-nanokontrolstudio.git
cd davinci-nanokontrolstudio
sh ./install.command
~~~

The installer copies `nanokontrol_resolve21.lua` into `~/.hammerspoon/`, adds `require("nanokontrol_resolve21")` to `~/.hammerspoon/init.lua` if needed, and backs up files before overwriting them. In Hammerspoon, choose **Reload Config**.

## Configure the Korg

1. Set the Korg's power switch to **Standby**.
2. Hold **SCENE + CYCLE** while powering it on in **USB** mode to select Assignable Mode.
3. In KORG KONTROL Editor, configure the following settings:

   | Setting | Required value |
   | --- | --- |
   | Global Controller Mode | Assignable |
   | Scene 1 / Global MIDI Channel | 1 |
   | Scene 1 / JOG type | **Sign Magnitude** |
   | Scene 1 / JOG acceleration | **Const** |
   | Scene 1 / JOG CC | **82** |
   | Scene 1 / Slider 1 (leftmost fader) | **CC 2** |
   | Scene 1 / Buttons | CC / Momentary; ON **127**, OFF **0** |
   | Scene 1 / Common / LED Mode | **External** |

4. Use **Communication → Write Scene Data** to send the scene to the **physical controller**. If you changed global settings, also use **Write Global Data**.
5. Select **Scene 1** for the setup wizard. Leave KORG KONTROL Editor closed while controlling Resolve.

**Important:** What the editor displays is not proof of what is stored on the device. The Scene Data write step is essential. In particular, the Scene 1 wheel must transmit **CC82, Sign Magnitude**, not the Continuous **CC86** used in the other scene configurations.

**Do not factory-reset the Korg as a routine installation step.** Save its existing Scene Set and Global Data before changing settings. See the [official nanoKONTROL Studio owner's manual](https://cdn.korg.com/us/support/download/files/d66996c95d7d55be1aa119b8fbb88e71.pdf) if an actual factory reset is necessary.

## Run the 28-step setup

The script automatically offers setup when it finds the device but has no valid saved mapping. You can also start it from the Hammerspoon **NK** menu: `TELJES UJRABETANITAS (28 lepes)` (*Full relearn, 28 steps*).

**Note:** The current version's Hammerspoon menu and wizard prompts are still in Hungarian; the documentation is in English. The prompts identify the physical control to operate, and the complete English order is below.

| Steps | Action on the Korg |
| --- | --- |
| 1–2 | Turn **JOG clockwise**, then **counterclockwise** |
| 3–14 | Press and release: CYCLE, RETURN TO ZERO, REW, FF, STOP, PLAY, large REC (Undo), TRACK ◀, TRACK ▶, MARKER SET, MARKER ◀, MARKER ▶ |
| 15–18 | MUTE 1–4 |
| 19–22 | MUTE 5–8 |
| 23–27 | SELECT 1–5 |
| 28 | Move **Slider/Fader 1** fully down, then fully up |

For each button, **press and release** to advance. The final step accepts only **CC2 on the wheel's MIDI channel**, over a sufficiently wide range (low ≤15 and high ≥112). The wizard checks JOG direction using CC82: values **1–64 clockwise** and **65–127 counterclockwise**.

A cancelled or incomplete calibration **does not overwrite** the last successful mapping. Existing completed calibration is retained when updating the Lua file.

## Everyday operation

| Control | Behavior |
| --- | --- |
| JOG | One frame per tick (JOG mode) |
| MARKER SET + JOG | Select edit point and nudge ±1 frame |
| CYCLE | JOG ↔ SHUTTLE; switches mode and stops transport |
| SHUTTLE wheel | One tick = one signed speed step, −4…+4 |
| Slider/Fader 1 | Center-zero shuttle; center 60–68 = STOP |
| PLAY | From STOP: normal +1; from +1: pause; from reverse or fast forward: normalize to +1 |
| FF | Jump directly to **+2**; PLAY and FF LEDs light |
| REW | Jump to **−1**; PLAY and REW LEDs light |
| STOP | Stop and illuminate the STOP LED |

**Examples:** STOP → FF (+2) → PLAY (+1) → PLAY (pause). Or STOP → FF (+2) → one SHUTTLE tick left (+1). STOP → REW (−1) → one tick right (STOP).

**Lighting reflects observed requests, not Resolve's actual transport state.** An on-screen mouse click, a customized shortcut, or playback already running when the script loads may not be tracked. A Hammerspoon event tap watches the unmodified physical Space/J/K/L keys only while Resolve is frontmost; it lets them pass through.

LED Mode **External** must be written separately for every scene in which you want to see the feedback. The five shared status LEDs (PLAY, STOP, REW, FF, CYCLE) are re-sent every 0.5 seconds, because a physical SCENE change can clear the device's visible LED state without a MIDI event. Scene 1 keeps the hardware-verified output `channel=0`; Scene 2 also receives the same five status CCs on `channel=1` (pending physical verification). **This does not change transport playback and does not poll Resolve.**

See the [complete Scene 1 mapping](docs/CONTROL_MAP.md) for the remaining buttons and MIDI CC values.

## Troubleshooting and field notes

These are practical hardware findings, not a development history:

- **Setup stuck at JOG step 1 or 2:** check Sign Magnitude **CC82** and physically **Write Scene Data**. Receiving **CC86** means the wheel is not in the required Scene 1 mode.
- **Wrong first fader:** the leftmost **slider is CC2**; the leftmost **rotary knob is CC13**. Step 28 requires the slider's near-full travel.
- **Scene 1 → Scene 2 makes transport LEDs go dark:** The Korg turns off LEDs when changing scenes; the second scene's LED mode must also be **External**. In KORG KONTROL Editor, select **Scene 2**, open its **Common → LED Mode** setting, choose **External**, then use **Communication → Write Scene Data**. Do not change the Scene 1 JOG configuration or run the 28-step relearn. Close the editor and test with Resolve frontmost: start PLAY in Scene 1, change to Scene 2 and check whether PLAY relights within 0.5 seconds.
- **Scene 2 still dark after enabling External:** leave Scene 2 selected and run `require("nanokontrol_resolve21").ledProbe()` in Hammerspoon Console. Watch the **MUTE 1** LED: the first 1.5-second test uses output `channel=1`, the second uses `channel=0`. Report **first / second / neither** and the `[NK LED PROBE]` lines. No Resolve shortcuts or firmware changes are made by the probe.
- **No External LEDs on Scene 1:** first verify Scene 1 LED Mode and Write Scene Data. On the tested Korg, Hammerspoon's MIDI **output** `sendCommand(channel=0)` succeeded physically; `channel=1` returned success but did not light the **Scene 1** LED. This is why the original output 0 remains untouched. Incoming physical MIDI channel 1 appears as **channel 0** in callbacks; do not confuse the two APIs.
- **Test the output directly:** in **Hammerspoon → Console**, run `require("nanokontrol_resolve21").ledProbe()`. Watch MUTE 1: it briefly tests output channel 1, then output channel 0, and sends OFF for both. The Console logs `[NK LED PROBE]`.
- **Physical keyboard not reflected in LEDs:** check macOS Accessibility/Input Monitoring permissions and reload Hammerspoon. The keyboard watcher does not consume these keys.
- **First playback after launch:** transport status starts unknown; there is no direct Resolve play-state query. Pressing a transport key establishes the script's local estimate.
- **Other scene controls not working:** only transport/navigation is shared today. Scene 2–5 editing, gain, track mute and rotary control are not implemented.

For setup diagnostics, the Hammerspoon Console logs every incoming MIDI event **only during the 28-step wizard**. Normal editing does not spam the Console with raw MIDI events.

## Tests and contributions

A deterministic hardware-free Lua test exercises calibration, transport, LED output, keyboard interception protection and multi-scene behavior:

~~~sh
luac5.4 -p nanokontrol_resolve21.lua tests/clean_controller.lua
lua5.4 tests/clean_controller.lua
~~~

GitHub Actions runs this on pull requests and on `main`. A green simulated test does not replace final verification on real Korg hardware and a disposable Resolve timeline. Contributions and reports with exact hardware mode, incoming CC/channel, macOS version and test steps are particularly helpful.

The current program intentionally keeps a small scope: no MIDI/HUI emulation, no Resolve scripting, and no unverified Scene 2 audio-mixing functionality.
