# User guide — Korg nanoKONTROL Studio + Resolve 21

## Everyday use

1. Log in to macOS. Hammerspoon starts from the login setting you configured.
2. Open DaVinci Resolve Studio 21. The controller automatically connects
   once Resolve is ready and frontmost. No manual project name, prompt or
   "enable" action is required.
3. Select Korg **Scene 1** for editing or **Scene 2** for Fairlight.
4. Use SELECT 7 / SELECT 8 on Scene 2 to switch between the two
   eight-channel banks if the Resolve project has the corresponding tracks.
5. NK JOG displays the active bank, with SELECT LED feedback.
   **Restart Controller** is available for maintenance.

With Resolve closed, Hammerspoon's MIDI/LED/event listeners remain
lightweight and idle with respect to audio editing. No Fairlight/clip
Python worker should be running without Resolve.

## Scene 1 and shared controls

Scene 1 retains the original 28 calibrated shortcuts, JOG, SHUTTLE and
transport. The large REC (CC81) sends Cmd+Z. MARKER SET (CC55) selects
the edit point with V; hold it and turn JOG to trim; MARKER LEFT/RIGHT
(CC56/57) send comma/period. These editing keys and the transport/JOG
are shared across all five Korg scenes.

The 28-step wizard is a **first-time or genuine remapping** operation,
not an update procedure. Never recalibrate merely to install a release.

## Scene 2: mixer and clip gain

| Physical input | Action |
|---|---|
| Sliders 1–8 | Current Fairlight MCU mixer bank faders |
| Rotary knobs 1–8 | Per-clip AudioVolume on the corresponding eight audio tracks |
| MUTE/SOLO 1–8 | Current MCU bank channels, with Resolve-authoritative LEDs |
| SELECT 7 | Request the first eight-strip bank (A1–A8 in the test project) |
| SELECT 8 | Request the second eight-strip bank (A9–A16 in the test project) |

The factory Korg slider CCs are **2, 3, 4, 5, 6, 8, 9, 12**.
Do not change them to a consecutive CC sequence. Sliders use 14-bit MCU
pitch messages, independent TOUCH handling and **soft pickup** against
real Fairlight host-position feedback. A physical fader must cross the
current on-screen position before it takes control.

Rotaries CC13–20 address the clip at the **stopped playhead** on A1–A8
or, in the second bank, A9–A16. Fully left maps to −100 dB, center
to 0 dB, fully right to +30 dB. They use soft pickup and verified
AudioVolume write/readback, not Fairlight mixer fader movement.
An empty/unsupported clip, a changed timeline or a mismatched project
prevents that clip write.

**Do not adjust clip gain during playback, scrubbing or recording** and
avoid clip gain keyframes/automation: the low-latency Resolve API cannot
authoritatively prove all of those conditions.

## Bank and LED feedback

After SELECT 7/8, the menu briefly shows **SYNCING**. Only after the
MCU worker receives eight real fader-position updates from Resolve does
it show an active bank and illuminate the corresponding SELECT LED.
While the new bank is not confirmed, old-bank mixer/clip writes are held
and former MUTE/SOLO LEDs are cleared. All eight faders require a new
physical pickup after a successful bank switch.

In the physically accepted 16-audio-track project, bank changes
A1–A8 → A9–A16 → A1–A8, corresponding clip writes and SELECT LEDs
worked. This does **not** guarantee channel names in a different Resolve
project, because MCU MIDI does not carry trustworthy track identities.

**Return to confirmed A1–A8 before changing Resolve projects or
restarting Hammerspoon.** On projects with fewer tracks, the eighth
MCU slot may address Bus 1.

## Restart, updates and diagnostics

The main NK JOG menu contains only:

- Korg connection / calibration status
- Fairlight running state and active bank
- **Restart Controller** (a full Hammerspoon configuration reload after
  the existing Python workers have exited)
- **Service & Diagnostics**, containing exceptional actions only

Bank paging is on by default. Normal use never requires manual session
start, project approval or a pause. A service-only pause is temporary
and resets automatically after Hammerspoon restarts. LED feedback,
channel-eight override, full-controller disable and calibration are
available for troubleshooting, not as everyday decisions.

For a new source snapshot, use `sh ./update.command`. The updater
sends a local pause event to Hammerspoon, waits for the worker processes
to stop, installs a reversible backup-first update, verifies the files,
then asks Hammerspoon to restart. An earlier version needs a one-time
manual pause/install/reload to gain those updater hooks; see
[Installation and updates](INSTALL.md).

## Diagnostic log

```sh
tail -n 60 "$HOME/Library/Logs/nk-scene2-session.log"
sh ./doctor.command
```

Typical messages include `FADER_WAIT_HOST` (Resolve feedback is needed),
`FADER_PICKUP_PENDING` / `FADER_PICKUP_PASS`,
`A9 AUDIO_WRITE_READBACK=PASS`, and `MCU_LIVE_BANK=ACTIVE`.
The doctor is read-only and does not edit any Resolve project.

Other known limits: uncommon/drop-frame timecode clip gain paths,
automation/keyframes, and untested Scene 3–5 LED output routes.
