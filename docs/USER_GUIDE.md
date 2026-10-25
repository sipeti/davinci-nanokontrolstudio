# User guide: editing Scene 1 and audio Scene 2

The Korg must stay in **Assignable Mode**. A hardware SCENE switch does not restart the Python workers or erase Scene 1 calibration. **JOG/SHUTTLE, transport, large REC/Undo (CC81) and MARKER CC55–57 work across all five scenes** if the wheels use CC82 Sign Magnitude / Const and the buttons retain their Scene 1 CC assignments. Holding MARKER SET makes JOG trim within that same scene; release or a scene switch clears the modifier. **Write Scene Data** after configuring each Korg scene.

## Scene 1: editing

Scene 1 continues to use the existing 28-step-learned mappings: frame-accurate JOG, edit-point selection/trim, In/Out, split, page selection and keyboard transport. Its leftmost slider is a center-zero SHUTTLE, *not* an audio fader. Returning from Scene 2 requires that slider to pass through its neutral range before it can command playback again.

Hammerspoon observes human Space/J/K/L keys while Resolve is frontmost to keep its transport LEDs coherent. These LEDs reflect the last observed command, not an authoritative Resolve playback-state query.

## Scene 2: Fairlight mixer

**Sliders/faders 1–7** adjust the respective Fairlight mixer strips using 14-bit MCU pitch messages over IAC. Each slider uses **soft pickup**: it must cross the host's currently reported position before taking control, preventing unexpected jumps. Slider 8 is locked because it may address Bus 1.

**MUTE 1–8** and **SOLO 1–8** send MCU notes. LEDs represent the status that Resolve sends back, not a physical button echo. Button presses only work in the physical Scene 2 with the input bridge enabled.

## Scene 2: per-clip gain

**Knobs 1–8** adjust **AudioVolume on an individual audio clip** on tracks A1–A8 underneath the **stopped playhead**. They do not move the Fairlight mixer fader and do not adjust PAN.

| Absolute rotary position | Clip gain |
| --- | ---: |
| Fully left (CC0) | **−100.000 dB** |
| One CC left of center (CC63) | −0.500 dB |
| Physical center (CC64) | **0.000 dB** |
| One CC right of center (CC65) | +0.273 dB |
| Fully right (CC127) | **+30.000 dB** |

The mapping is deliberately non-linear: the middle is finer. Each knob first uses a soft pickup of the **current clip gain**; then rapid physical movements map to the newest CC rather than replaying stale intermediate samples. The app checks the exact project, clip, playhead and current gain before writing and immediately reads the new gain back.

Scene changes, foreground loss, playhead moves, clip changes or an external gain edit discard pickup and require new physical movement. A3 with no clip at the playhead correctly refuses editing; this is not an error.

### Project authorization

In v1.5, Hammerspoon starts Scene 2 automatically while Resolve is active. No project name or confirmation dialog is needed. The rotary worker follows the current Resolve project and validates the clip at every write. The **mixer retains exactly the working v1.4 Fairlight MCU implementation**: no project token, additional gate, or new MIDI handshake.

**No automatic playback gate exists in low-latency mode.** Do not touch clip knobs during playback, scrubbing, recording or automation. A +30 dB clip change is large: use headphones/monitor levels carefully in a stopped test copy first.

### Stop, logs and troubleshooting

Use **NK JOG → Scene 2: SZÜNET** to pause automatic operation, and **FOLYTATÁS** to resume. The parent process releases MCU TOUCH and buttons during shutdown; Hammerspoon starts the workers quietly when Resolve is ready.

Logs: ~/Library/Logs/nk-scene2-session.log. To inspect the latest events safely:

~~~sh
tail -n 60 "$HOME/Library/Logs/nk-scene2-session.log"
~~~

Typical messages: PICKUP_PENDING (waiting for a real crossing), PICKUP=PASS (armed), AUDIO_WRITE_READBACK=PASS (actual clip setter verified), REARM (focus/scene/playhead changed) and BUS1_STRIP8_LOCKED (deliberate safety lock). The diagnostic command **sh ./doctor.command** does not send MIDI or alter projects.

**Known limitations:** non-integer/drop-frame timecode is not supported by the clip-gain snapshot parser; clip gain automation is unverified by API; the eighth MCU mixer strip is locked; no PAN/REC implementation for Scene 2. Scenes 3–5 share transport and the four REC/MARKER editing keys; their external LED output routes still need physical verification.
