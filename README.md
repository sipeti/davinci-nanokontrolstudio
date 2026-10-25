# Korg nanoKONTROL Studio for DaVinci Resolve 21

A macOS MIDI controller for **DaVinci Resolve Studio 21** using a **Korg nanoKONTROL Studio** in Assignable Mode, Hammerspoon and two small Python workers. Scene 1 handles editing; Scene 2 combines real Fairlight mixer control with per-clip audio gain. Scenes 3–5 retain the shared transport and JOG/SHUTTLE behavior.

**Physical acceptance:** tested on a Mac with Resolve Studio 21 and nanoKONTROL Studio, including Scene 1 ↔ Scene 2 changes, 189 low-latency clip-gain edits, 1373 Fairlight fader messages and MIDI/LED return. Other Mac/Resolve/Korg combinations still need validation.

## Features

- **Scene 1:** the proven 28-step-learned editing shortcuts, frame JOG, SHUTTLE and transport LEDs. Existing calibration is preserved on upgrade.
- **Scene 2, sliders 1–7:** actual Fairlight track mixer levels, with host-aware soft pickup. **Slider 8 is deliberately locked** to protect potential Bus 1.
- **Scene 2, rotary knobs 1–8:** clip AudioVolume on A1–A8 at the stopped playhead. Full left **−100 dB**, physical center **0 dB**, full right **+30 dB**. Soft pickup avoids unintended initial jumps. Uses the 20 ms low-latency input cycle.
- **Scene 2, MUTE and SOLO:** actual Fairlight mute/solo via MCU over two virtual IAC MIDI ports; LEDs follow Resolve's response, not the button press.
- **All scenes:** shared JOG / SHUTTLE wheel and transport/navigation where mapped. One Hammerspoon physical MIDI input owner; no competing HUI mode on the Korg.
- **One-click session:** NK JOG menu START/STOP, with per-session project selection, explicit confirmation and session logs.

Scene 2 changes real mixer and clip gain values. **Backup your project and STOP playback/scrubbing before turning any clip knob.** Gain automation/keyframes are not supported. The low-latency mode cannot itself prove that playback is stopped. Never enable a direct Korg HUI console in Resolve while Hammerspoon owns the Korg input.

## Install or upgrade

Requirements: macOS, Homebrew Python 3.10+, Hammerspoon (Accessibility permission), Resolve Studio 21 with the scripting modules, Korg nanoKONTROL Studio, and KORG KONTROL Editor. Network access is needed for first-time MIDI Python dependency installation.

~~~sh
git clone https://github.com/sipeti/davinci-nanokontrolstudio.git
cd davinci-nanokontrolstudio
sh ./install.command --dry-run
sh ./install.command
~~~

The installer creates a backup, installs the Lua controller/helpers in ~/.hammerspoon, installs runtime scripts under ~/Library/Application Support/NK Scene2/, pins the MIDI Python dependencies and adds the Hammerspoon require line only when missing. **It never rewrites the Korg or re-runs Scene 1's 28-step calibration.**

If upgrading from a previously installed experimental Scene 2 controller, review your local modifications, then run **sh ./install.command --force**. It still saves the exact previous files first. Finish with **Hammerspoon → Reload Config**.

**Required one-time MIDI hardware setup:** Scene 2 Assignable, the expected CC numbers, External LED Mode, and two IAC Driver buses connecting Python MCU to the Resolve MIDI Audio Console. Details and diagrams of the routing are in [Installation and MIDI setup](docs/INSTALL.md).

## Daily use

1. In Resolve, open the project you want to control and create/verify a project backup.
2. Keep playback stopped; disable/remove clip volume keyframes and automation on targets.
3. Hammerspoon → **NK JOG → Scene 2: START**.
4. Enter the **exact** Resolve project name and explicitly confirm the safety conditions.
5. Select physical **Scene 2**. Mixer sliders and the clip rotary knobs are now independent.
6. Stop from **NK JOG → Scene 2: STOP** before leaving or changing to another project.

The session is not a login service and does not auto-start at boot. If the project/clip context or Resolve focus changes, pickup is rearmed or writes are refused. Python logs: ~/Library/Logs/nk-scene2-session.log. Hammerspoon logs are available in its Console.

## Uninstall / restore

~~~sh
sh ./uninstall.command
~~~

The uninstall command verifies that installed files were not subsequently edited, then restores the **immediately preceding** copies of Hammerspoon files and init.lua. It retains backups, the Python venv and the stored Korg calibration. It never resets hardware settings. A prior experimental install may therefore be restored instead of producing an empty Hammerspoon configuration.

~~~sh
sh ./doctor.command
~~~

The doctor only reads files, Python availability and MIDI port names; it does not send MIDI or edit Resolve.

## Documentation

- [Installation and IAC routing](docs/INSTALL.md)
- [Scene 1 / Scene 2 user guide](docs/USER_GUIDE.md)
- [Complete physical control map](docs/CONTROL_MAP.md)
- [Release notes and known limitations](docs/RELEASE_NOTES.md)
- [Historical protocol tests and research](docs/RESEARCH_HISTORY.md)

## Development

The full offline regression suite runs on GitHub Actions (Lua 5.4 and Python). To run locally:

~~~sh
python3 -m unittest discover -s tests -p 'test_*.py'
lua5.4 tests/clean_controller.lua
lua5.4 tests/test_scene2_session_menu.lua
~~~

Native Lua tests use mock hardware; the real MIDI/Resolve acceptance is a separate manual test. A release is not a promise of compatibility with every future Resolve update. The repository currently has **no explicit redistributable software license**; licensing is a separate owner decision.
