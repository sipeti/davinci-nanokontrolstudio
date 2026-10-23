# Control map — Korg nanoKONTROL Studio / DaVinci Resolve 21

This document describes the **current implemented mapping**, not potential future mappings. The Lua controller works in **Korg Assignable Mode**, sends Resolve keyboard shortcuts, and saves its Scene 1 bindings through a 28-step learn wizard. The CC numbers below match the tested Korg scene configuration; if you reconfigure the hardware, the stored learned bindings are authoritative.

[Installation, configuration, troubleshooting and tests](../README.md)

## MIDI channels and scenes

| Scene | Incoming MIDI channel reported by Hammerspoon | Available actions |
| --- | ---: | --- |
| 1 | 0 | Full Scene 1 editing mapping, JOG, Slider 1 SHUTTLE, shared transport |
| 2 | 1 | Shared transport and navigation only |
| 3 | 2 | Shared transport and navigation only |
| 4 | 3 | Shared transport and navigation only |
| 5 | 4 | Shared transport and navigation only |

The five Korg scene configurations share the **same transport CC numbers** but use successive MIDI channels. SCENE switching is performed on the controller itself. The Lua controller does not need a MIDI scene-change event to restore the common transport LEDs.

The Scene 1 wheel is **CC82 / Sign Magnitude / Const**, with clockwise values 1–64 and counterclockwise values 65–127. The other scenes in the tested configuration use a **Continuous / CC86** wheel; they are **not** yet mapped to Scene 1 JOG/SHUTTLE. No gain, mute, fader or knob functionality has been implemented for Scene 2–5.

**MIDI channel gotcha:** Scene 1 configured as MIDI channel 1 appears as incoming `channel=0` in Hammerspoon. For LED **output**, the tested device requires `sendCommand(channel=0)` (the all-channel send option). Sending output with `channel=1` was accepted by the API but did not light the hardware LED.

## JOG, SHUTTLE and slider

| Physical control | Scene 1 CC | Current action |
| --- | --- | --- |
| Main JOG wheel | 82 | In JOG mode: one frame right/left per MIDI pulse |
| Main JOG wheel, CYCLE = SHUTTLE | 82 | One pulse = one signed speed step, limited to −4…+4 |
| Hold MARKER SET + JOG | 55 held, then 82 | Enter edit-point selection (`V`) and nudge with `,` / `.` |
| Slider/Fader 1 (leftmost **slider**) | 2 | Center-zero SHUTTLE; center CC60–68 = STOP; requires center to arm |
| CYCLE | 54 | Toggle JOG / SHUTTLE; stop transport while changing modes |

SHUTTLE wheel changes are batched over **45 ms** to combine closely spaced MIDI pulses. The shared signed gear is used by the wheel, the FF/REW transport buttons, and normalizing playback with PLAY. Slider 1 has its own physical pickup/center arming rule.

### Signed playback speeds and LEDs

| Requested gear | Shortcuts sent for SHUTTLE | Illuminated transport LEDs |
| ---: | --- | --- |
| −4 … −2 | `K` followed by 2–4 × `J` | PLAY + REW |
| −1 | `K, J` | PLAY + REW |
| 0 | `K` | STOP |
| +1 | `K, L` | PLAY only |
| +2 … +4 | `K` followed by 2–4 × `L` | PLAY + FF |

**Key transitions currently implemented:**

- STOP → **FF button**: +2 (`K, L, L`); FF and PLAY LEDs remain on after release.
- FF +2 → **PLAY button**: +1 (`K, L`); FF goes off, PLAY stays on.
- FF +2 → **one wheel tick left** in SHUTTLE: +1, same LED result.
- PLAY +1 → **PLAY again**: `Space` pause/stop. STOP LED comes on.
- STOP → **REW button**: −1 (`K, J`); PLAY and REW LEDs on.
- REW −1 → **one wheel tick right** in SHUTTLE: 0 (STOP).
- REW −1 → **PLAY button**: forward +1 (`K, L`).

The **FF button always selects +2**; it does not increase the gear every time it is pressed. The **REW button always selects −1**. A physical Space/J/K/L key used while Resolve is frontmost is observed for local status tracking; the key event is not swallowed. Lua-generated key events are guarded against being counted a second time.

The software tracks **requested/observed commands**, not the actual Resolve transport API state. Mouse-driven playback changes and already-running playback at Hammerspoon startup may leave the LEDs out of sync.

## Shared transport and navigation buttons (Scenes 1–5)

| Korg button | CC | Resolve shortcut / action |
| --- | ---: | --- |
| CYCLE | 54 | Switch JOG ↔ SHUTTLE; stop |
| RETURN TO ZERO | 62 | `Cmd+Left` — return to timeline start |
| REW | 58 | `K, J` — reverse at −1 |
| FF | 59 | `K, L, L` — forward at +2 |
| STOP | 63 | `K` — stop |
| PLAY | 80 | STOP → `Space` (+1); +1 → `Space` (pause); other moving gears → `K, L` (+1) |
| TRACK ◀ | 60 | `Up` — previous edit |
| TRACK ▶ | 61 | `Down` — next edit |

The following Scene 1 marker buttons are **not** global across the other scenes:

| Scene 1 button | CC | Shortcut / action |
| --- | ---: | --- |
| Large transport REC | 81 | `Cmd+Z` — Undo |
| MARKER SET | 55 | `V` edit-point selection; hold for JOG trim |
| MARKER ◀ | 56 | `,` — trim left |
| MARKER ▶ | 57 | `.` — trim right |

## Scene 1 — eight channel strips

The printed Korg **MUTE** button names below are *physical labels*, not Resolve track mute functions in Scene 1.

| Strip | MUTE (CC21–28) | SOLO CC (unassigned) | REC CC (unassigned) | SELECT (CC46–53) |
| ---: | --- | ---: | ---: | --- |
| 1 | CC21 → keyboard `1` (CAM 1) | 29 | 38 | CC46 → Cut page |
| 2 | CC22 → keyboard `2` (CAM 2) | 30 | 39 | CC47 → Edit page |
| 3 | CC23 → keyboard `3` (CAM 3) | 31 | 40 | CC48 → `T` (Trim tool) |
| 4 | CC24 → keyboard `4` (CAM 4) | 33 | 41 | CC49 → `A` (Selection tool) |
| 5 | CC25 → `I` (In point) | 34 | 42 | CC50 → Deselect (`Cmd+Shift+A`), then Split (`Cmd+B`) |
| 6 | CC26 → `O` (Out point) | 35 | 43 | CC51 → unassigned |
| 7 | CC27 → `Alt+X` (Clear In/Out) | 36 | 44 | CC52 → unassigned |
| 8 | CC28 → `Esc` | 37 | 45 | CC53 → unassigned |

CAM 1–4 sends the **number keys** only; camera selection depends on the appropriate Resolve Cut/Sync Bin context and keyboard mapping. This is not a Resolve API multicam switch or Source Overwrite operation. Cut/Edit page selection uses Resolve's application menu, not an arbitrary keystroke. The Split action operates on whatever unlocked/enabled tracks and selection Resolve currently allows.

SOLO 1–8, strip REC 1–8 and SELECT 6–8 do **not** invoke an editing action today. With External LED feedback enabled, their physical press/release still lights the corresponding LED momentarily.

## Rotary knobs and sliders

| Strip | Rotary knob (CC) | Slider/fader (CC) |
| ---: | --- | --- |
| 1 | 13 — unassigned | **2 — SHUTTLE** |
| 2 | 14 — unassigned | 3 — unassigned |
| 3 | 15 — unassigned | 4 — unassigned |
| 4 | 16 — unassigned | 5 — unassigned |
| 5 | 17 — unassigned | 6 — unassigned |
| 6 | 18 — unassigned | 8 — unassigned |
| 7 | 19 — unassigned | 9 — unassigned |
| 8 | 20 — unassigned | 12 — unassigned |

Unassigned controls may still send MIDI data to Hammerspoon; the current Lua simply does not associate them with a Resolve action. **There is no Scene 2 gain control or actual track mute implementation yet.**

## Persistent LED feedback

In KORG KONTROL Editor, enable **LED Mode = External** and **Write Scene Data** for each scene that should display the transport LEDs.

| LED | When it is on |
| --- | --- |
| PLAY / CC80 | Any known moving transport state (+1…+4 or −1…−4) |
| STOP / CC63 | Known stopped state (gear 0) |
| REW / CC58 | Reverse playback (−1…−4), together with PLAY |
| FF / CC59 | Accelerated forward playback (+2…+4), together with PLAY |
| CYCLE / CC54 | SHUTTLE mode selected |
| Other configured buttons | While physically pressed; off on release |

The status LEDs are refreshed every **0.5 seconds**, including after a hardware-only SCENE change. When the state is unknown (for example, just after a configuration reload) the four transport LEDs are left off rather than claiming Resolve is stopped. The **LED feedback ON/OFF** item in the Hammerspoon NK menu can blank all 44 known Scene 1 button LEDs.

## Updating or relearning

The 28-step Scene 1 wizard stores its bindings only on successful completion; these are preserved across `install.command` upgrades. Do **not** relearn merely because the Lua file or these documents change.

If a CC mapping was deliberately changed in KORG KONTROL Editor, **Write Scene Data**, then run the complete relearn. No half-learned mapping is saved. See the [README setup section](../README.md#run-the-28-step-setup).
