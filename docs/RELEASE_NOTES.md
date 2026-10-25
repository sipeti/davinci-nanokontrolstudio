# Release notes — v1.4.0 (Scene 1 + Scene 2 integration)

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
