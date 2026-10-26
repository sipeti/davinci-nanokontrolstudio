# nanoKONTROL Studio for DaVinci Resolve

A Korg nanoKONTROL Studio controller for **DaVinci Resolve Studio 21 on macOS**.
Hammerspoon owns the physical Korg MIDI connection. Two Python workers handle
Fairlight MCU faders/MUTE/SOLO and clip gain. The Korg stays in **Assignable
Mode**, not HUI mode.

> **1.6.0 release candidate.** The accepted 16-channel controller is
> preserved; the restart/update workflow has CI coverage and a successful
> macOS install/update-request log. Post-reload hardware verification remains
> pending. Historical research is preserved.

## Daily operation

- **Log in:** Hammerspoon starts with macOS if you enabled its normal
  *Launch at Login* setting. No extra LaunchAgent or daemon is installed.
- **Resolve absent:** Hammerspoon continues lightweight MIDI, keyboard and
  LED event handling, but the Fairlight and clip-gain Python workers do not
  start. There are no Resolve audio writes.
- **Resolve ready and frontmost:** the two workers start automatically.
  There is no project-name prompt or manual permission gate.
- **Scene 1:** editing, transport, JOG and SHUTTLE, with preserved 28/28
  one-time calibration.
- **Scene 2:** eight physical sliders control the current Fairlight MCU
  bank; eight knobs control the corresponding clips at the stopped playhead;
  MUTE/SOLO follow the MCU. Soft pickup prevents initial jumps.
- **Bank navigation:** Scene 2 SELECT 7/8 select A1–A8 and A9–A16 in the
  hardware-tested 16-audio-track project. The bank display and SELECT LEDs
  confirm a fresh Resolve MCU fader-bank response. Other track layouts may
  include Bus 1 in an MCU slot.
- **Restart:** NK JOG → **Restart Controller** stops the current workers,
  waits for them to exit, and reloads Hammerspoon. Return to confirmed
  **A1–A8** before restarting or changing Resolve projects.

The main NK JOG menu shows device/calibration status, the active Fairlight
bank, **Restart Controller**, and **Service & Diagnostics**. Legacy
bank/LED/pause controls remain under Service for troubleshooting; they are
not necessary for ordinary use. Manual pause is temporary and does not
disable the next macOS login.

## Installation and updating

Requires Hammerspoon with Accessibility permission, DaVinci Resolve Studio 21,
Homebrew Python 3.10+, Korg KONTROL Editor, and two IAC Driver MIDI buses. For
port routing and first-time physical configuration see [Install](docs/INSTALL.md).

```sh
git clone https://github.com/sipeti/davinci-nanokontrolstudio.git
cd davinci-nanokontrolstudio
sh ./install.command --dry-run
sh ./install.command
sh ./doctor.command
```

The installer saves the previous Lua files, init.lua and runtime scripts
before overwriting. It never rewrites Korg Scene Data or erases the 28-step
Hammerspoon calibration.

**Future upgrades after the new controller is installed:** fetch a clean
source snapshot, then run `sh ./update.command`. It pauses the running
Python workers, waits for shutdown, runs the existing backed-up installer,
checks the installed file contents and requests a Hammerspoon restart.
It does **not** automatically fetch new code or install a background service.

```sh
git fetch origin main
TMP=$(mktemp -d /tmp/nk-release.XXXXXX)
git archive FETCH_HEAD | tar -x -C "$TMP"
cd "$TMP"
sh ./update.command
```

**One-time upgrade from earlier v1.5:** the older installed controller
does not yet recognize the updater command. Use NK JOG → Settings/Service →
Pause Scene 2, run `sh ./install.command --force` from the new snapshot,
then choose **Hammerspoon → Reload Config**. After that, the updater works
without a manual pause. For a failed update, the existing backups remain
available; `sh ./uninstall.command` restores the preceding installation
when files are unchanged.

## Important boundaries

Clip AudioVolume may range from **−100 to +30 dB**. Stop playback,
scrubbing and recording before adjusting clips, and do not use unsupported
gain automation. Low-latency mode cannot reliably prove playback has
stopped. Keep **A1–A8** selected before changing projects or restarting,
because MCU bank MIDI does not identify tracks by name. The eighth mixer
strip might address Bus 1 on a project with fewer than eight audio tracks.

The Korg's original fader CCs are **2, 3, 4, 5, 6, 8, 9, 12**. Do not
renumber them in KORG KONTROL Editor. One-time JOG/LED assignments and
IAC/Resolve Control Panels MIDI routing remain necessary.

## Documentation

- [Installation, MIDI routing and updates](docs/INSTALL.md)
- [Daily controls and troubleshooting](docs/USER_GUIDE.md)
- [Exact hardware control map](docs/CONTROL_MAP.md)
- [Release notes](docs/RELEASE_NOTES.md)
- [Preserved hardware research](docs/RESEARCH_HISTORY.md)

`sh ./doctor.command` is read-only. The offline Lua/Python regression
suite runs in GitHub Actions. Physical tests validate the author's rig, not
every macOS/Resolve/Korg combination. This repository currently has no
explicit redistributable software license.
