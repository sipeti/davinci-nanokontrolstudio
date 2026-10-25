# Control map — Korg nanoKONTROL Studio / DaVinci Resolve 21

This document describes the **current implemented mapping**, not potential future mappings. The Lua controller works in **Korg Assignable Mode**, sends Resolve keyboard shortcuts, and saves its Scene 1 bindings through a 28-step learn wizard. The CC numbers below match the tested Korg scene configuration; if you reconfigure the hardware, the stored learned bindings are authoritative.

[Installation, configuration, troubleshooting and tests](../README.md)

## MIDI channels and scenes

| Scene | Incoming MIDI channel reported by Hammerspoon | Available actions |
| --- | ---: | --- |
| 1 | 0 | Scene 1 editing + JOG/SHUTTLE + Slider 1 + transport |
| 2 | 1 | **Fairlight mixer sliders 1–8, MUTE/SOLO and A1–A8 clip gain knobs** + shared JOG/transport |
| 3 | 2 | **JOG/SHUTTLE wheel** (after CC82 configuration) + shared transport |
| 4 | 3 | **JOG/SHUTTLE wheel** (after CC82 configuration) + shared transport |
| 5 | 4 | **JOG/SHUTTLE wheel** (after CC82 configuration) + shared transport |

The five Korg scene configurations share the **same transport CC numbers** but use successive MIDI channels. SCENE switching is performed on the controller itself. The Lua controller does not need a MIDI scene-change event to restore the common transport LEDs.

**All five scenes use one JOG/SHUTTLE decoder** when their wheels send **CC82 / Sign Magnitude / Const**, with clockwise values 1–64 and counterclockwise values 65–127 on their respective MIDI channels. Scenes 2–5 in the earlier Korg setup used **Continuous / CC86**; this signal is **deliberately ignored** until the hardware is reconfigured and written. A one-time `[NK JOG]` Console warning identifies old CC86 scenes. The 28-step calibration is still Scene 1-only, and other scene wheels reuse its learned CC82 mapping. Scenes 3–5 have no additional gain, mixer mute, marker trim, fader or rotary mappings.

**MIDI channels:** Korg Scenes 1–5 must retain their corresponding Global MIDI Channels **1–5** (incoming Hammerspoon callback channels **0–4**). Each Jog Wheel's MIDI Channel should be **Global**. LED output 0 lights Scene 1 and output 1 lights Scene 2 (both verified on the actual device); shared status CCs also go to outputs **2–4** for Scenes 3–5, pending physical testing.

## JOG, SHUTTLE and slider

| Physical control | CC | Current action |
| --- | --- | --- |
| Main JOG wheel, **Scenes 1–5** | **82** | In JOG mode: one frame right/left per MIDI pulse; keeps the last known PLAY/STOP/REW/FF status LEDs intact |
| Main JOG wheel, **Scenes 1–5**, CYCLE = SHUTTLE | **82** | One pulse = one **shared** signed speed step, limited to −4…+4 |
| Hold MARKER SET + JOG, **all Scenes 1–5** | 55 held, then 82 | Enter edit-point selection (`V`) and nudge with `,` / `.` |
| Slider/Fader 1, **Scene 1 only** | 2 | Center-zero SHUTTLE; center CC60–68 = STOP; requires center to arm |
| CYCLE, **Scenes 1–5** | 54 | Toggle the shared JOG/SHUTTLE mode; stop while changing modes |

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

From v1.5, these editing controls are **shared across Scenes 1–5** (configure the same CC in every Korg Scene and use Write Scene Data):

| Button (Scenes 1–5) | CC | Shortcut / action |
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

This table describes **Scene 1**, where only slider 1 is assigned. **Experimental Scene 2 bank buttons:** SELECT7 (physical CC52) requests
MCU Bank Left (note 46), SELECT8 (physical CC53) requests MCU Bank Right
(note 47). The two supported banks are A1–A8 and A9–A16. The NK JOG
status and SELECT7/8 LEDs reflect the received MCU host-fader refresh,
not merely the physical press. The clip-gain rotaries follow only an
acknowledged bank. Requires an explicitly enabled preview; see
[User guide](USER_GUIDE.md).

**Scene 2:** the factory physical slider CCs **2, 3, 4, 5, 6, 8, 9, 12** map to MCU mixer strips 1–8 respectively; the 8th MCU strip (physical CC12) was physically verified as A8 in the eight-audio-track project and is enabled by default. In other Resolve banks it may instead be Bus1, so the NK JOG menu allows disabling the eighth strip (including MUTE8/SOLO8). CC7 is unused, not slider 6. CC13–CC20 adjust clip gain on audio tracks A1–A8 at a STOPPED playhead. Physical MUTE CC21–28 and SOLO CC29,30,31,33,34,35,36,37 drive Fairlight MCU notes, with host-authoritative LED feedback. The Scene 2 knobs have CC0=−100 dB, CC64=0 dB and CC127=+30 dB. See [Scene 2 user guide](USER_GUIDE.md).

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

The five shared status LEDs are refreshed every **0.5 seconds**, including after a hardware-only SCENE change, on output channels **0–4** for the shared CCs only. Scene 1-only editing buttons continue to use output 0. **Every scene needs LED Mode = External and Communication → Write Scene Data** to illuminate its transport LEDs. Scene 1 and Scene 2 were confirmed on hardware; Scene 3–5 LED outputs require a physical test. The Lua cannot alter the Korg's scene firmware settings.

When the transport state is unknown (e.g. after a configuration reload) the transport LEDs remain off rather than claiming Resolve is stopped. The **LED feedback ON/OFF** item in the Hammerspoon NK menu blanks all 44 known Scene 1 button LEDs **and** the five shared transport/mode LEDs for each of Scenes 2–5.

For Scene 2 LED troubleshooting, `require("nanokontrol_resolve21").ledProbe()` compares output channels 1 and 0 on MUTE 1 without controlling Resolve. Output channels for Scene 3–5 still need physical confirmation.

## Updating or relearning

The 28-step Scene 1 wizard stores its bindings only on successful completion; these are preserved across `install.command` upgrades. Do **not** relearn merely because the Lua file or these documents change.

If you only change Scene 2–5 wheels from CC86 Continuous to **CC82 Sign Magnitude**, **Write Scene Data separately for each changed scene** but **do not rerun Scene 1 learn**. Only if you change the CC of a Scene 1 learned control should you rerun the complete 28-step learn. No incomplete mapping is saved. See the [README setup section](../README.md#run-the-28-step-setup).
