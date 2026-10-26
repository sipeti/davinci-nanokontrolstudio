# Release notes

## 1.6.0-rc1 — English UI and restart/update workflow (hardware verification pending)

- Runs from Hammerspoon's normal macOS login launch; no new daemon or
  permission prompt. When Resolve is absent, the two Python workers stop.
- Turns on the **hardware-accepted two-bank SELECT7/8 paging by default**,
  with host-confirmed A1–A8/A9–A16 status and LED feedback.
- Makes the optional Scene 2 pause **temporary** rather than a persistent
  shutdown state across reboots or Hammerspoon reloads.
- Adds **Restart Controller** to NK JOG. It waits for the Python workers
  to exit before restarting the Hammerspoon Lua controller. The bank
  must be confirmed A1–A8 at restart time.
- Adds `update.command` to stop, back up, install, verify, and request
  restart from a checked-out source snapshot, without new background
  services or automatic Git downloads.
- Uses English for menu labels, setup prompts, toasts and operator-facing
  log messages; moves infrequent controls to Service & Diagnostics.
- Corrects stale documentation and version metadata. No change to the
  proven mixer pitchwheel, MUTE/SOLO, pickup protocol or Korg factory CCs.

The 2026-10-26 macOS operator log confirms two successful installs, read-only
doctor checks (Python 3.15, MIDI packages and both IAC buses), and a subsequent
`update.command` that reported `NK_UPDATE=PASS` and requested a Hammerspoon
restart. A restart request is not proof of a successful post-reload session:
live A1–A8/A9–A16 banking and Resolve quit/reopen still need operator
confirmation before a final 1.6.0 tag. All copied runtime modules are now
checked against the installer manifest, and dry-run remains usable while
the controller is active.

## 1.5 — accepted on hardware (merged PRs #17 and #18)

- Automatic Scene 2 worker start while Resolve is ready; no manual
  project-name confirmation, and no separate login daemon.
- Korg factory slider CCs **2,3,4,5,6,8,9,12** correctly drive the eight
  physical Fairlight mixer slots in the tested project. The eighth
  slider was observed moving A8 with Bus1 unchanged.
- Eight independent clip-gain rotaries A1–A8, shared editing/transport
  across all five Assignable scenes and Resolve-authoritative LEDs.
- Two-bank SELECT7/8 paging A1–A8 ↔ A9–A16, with eight host fader
  feedback positions required before declaring the new bank active.
  Hardware acceptance included successful A11–A16 write/readback and
  SELECT indicator lights.
- Return to bank A1–A8 before restarting or changing projects, as MCU
  feedback does not identify each Resolve track by name.

## 1.4.0 — original Scene 1 / Scene 2 integration (historical)

## Shipped features

- Preserves the hardware-accepted Scene 1 edit/JOG/SHUTTLE/transport behavior and 28/28 saved calibration.
- Adds the tested Scene 2 Fairlight MCU IAC mixer: sliders 1–7, MUTE/SOLO and host-authoritative LED feedback.
- Adds clip-level CC13–20 gain on A1–A8, absolute **−100/0/+30 dB** taper with soft takeover; explicit 20 ms low-latency processing and fresh setter/readback.
- Adds per-session exact Resolve project selection and explicit confirmation for named projects. There is no automatic worker startup.
- Adds an isolated Python MIDI environment, reversible macOS installer/uninstaller, read-only doctor, docs and regression tests.
- Keeps mixer strip 8 locked to avoid inadvertently manipulating Bus 1.

## Hardware validation (2026-10-25)

The operator accepted physical Scene 1/2 switching, MUTE/SOLO and low-latency knob response on a Mac running Resolve 21. A documented test generated **189 successful AudioVolume writes**, **1373 MCU fader messages**, **six MUTE/SOLO presses** and clean Ctrl+C process shutdown. A later menu session reported **336 verified writes**. This establishes the observed rig only, not a guarantee for other OS/Resolve versions.

## Safety and limitations

- Playback must be stopped, with a backed-up project and no clip gain automation/keyframes; the Resolve scripting API cannot authoritatively verify these user prerequisites. The 120 ms stationary-gate is intentionally omitted in low-latency mode.
- Clip gain uses a unique plain audio clip at the playhead and supports non-drop, integer-FPS timeline timecode. No unsupported clip silently gets adjusted.
- Bus 1 (mixer strip 8) intentionally locked; no PAN mapping; Scene 3–5 LED routes not yet hardware-approved.
- Requires two manually configured IAC Driver buses and Resolve's MCU-compatible MIDI Audio Console; no user data or source media uploaded.
- Pinned Python MIDI packages tested on the accepted rig. Other macOS/Python variants require their own validation.
- This repository does not yet include a distribution license or a notarized .app; release packaging is a source-based macOS installer.

## Research history

Earlier Draft PRs #7–#15 are retained in GitHub history for hardware findings and offline safety tests. Their research-only commands should not be treated as release instructions; use [INSTALL.md](INSTALL.md) instead.
