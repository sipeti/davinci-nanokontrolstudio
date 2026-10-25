# Installation and MIDI routing

**Target:** macOS + DaVinci Resolve Studio 21 + Korg nanoKONTROL Studio in USB Assignable Mode. The package installs no daemons or background tasks; manual menu START remains necessary. The original user-tested setup was Apple Silicon and Resolve 21.1.

## 1. Prerequisites

- Install Hammerspoon and grant **Accessibility** and, when needed, **Input Monitoring** in System Settings.
- Install Homebrew Python 3.10+ (Apple Silicon default /opt/homebrew/bin/python3); the setup selects /usr/local/bin/python3 on Intel when appropriate.
- Install DaVinci Resolve Studio 21 and ensure its Developer/Scripting/Modules directory exists.
- Install KORG KONTROL Editor, back up your Korg Scene Set, and power the nanoKONTROL Studio on in **Assignable Mode** (hold SCENE + CYCLE when powering on). **Do not switch the whole device to Pro Tools/HUI mode.**

Scene 1's 28-step learned binding remains in Hammerspoon hs.settings. First-time users follow the existing [control map](CONTROL_MAP.md); returning users must not rerun the wizard merely to install Scene 2.

## 2. Korg Scene 2 configuration

Use **Global MIDI Channel 2** for Scene 2 (Hammerspoon input channel 1). The tested mapping is:

| Physical controls | MIDI CC |
| --- | --- |
| Eight rotary knobs | 13–20, in order |
| Eight sliders/faders | 2, 3, 4, 5, 6, 8, 9, 12 (observed hardware configuration; bus strip 8 locked) |
| MUTE 1–8 | 21–28 |
| SOLO 1–8 | 29, 30, 31, 33, 34, 35, 36, 37 |
| Scene 2 JOG wheel | **CC82 / Sign Magnitude / Const** |
| Transport | Same physical CC assignments as Scene 1 |
| LED Mode | **External** |

**Communication → Write Scene Data** is required after each changed Korg scene. KORG KONTROL Editor merely displaying a value does not prove the physical controller received it. Keep Scene 1's mapping and firmware settings intact.

## 3. Two virtual macOS IAC MIDI buses

Open **Audio MIDI Setup → Window → Show MIDI Studio → IAC Driver**; enable **Device is online** and create these two distinct buses:

| IAC bus | Data direction |
| --- | --- |
| **NK FL To Resolve** | Python MCU commands → Resolve MIDI Input |
| **NK FL From Resolve** | Resolve MCU feedback → Python MCU Input |

In **Resolve Preferences → System → Control Panels**, enable the MIDI Audio Console and select an **MCU-compatible** controller. MIDI Input should be **NK FL To Resolve**; MIDI Output should be **NK FL From Resolve**. Save and restart Resolve if necessary. Do not select the physical Korg MIDI port in the Resolve console: Hammerspoon is its sole input owner.

On some macOS systems the port names shown by MIDI libraries include the prefix **IAC Driver**. This release expects exactly **IAC Driver NK FL To Resolve** and **IAC Driver NK FL From Resolve**. The doctor displays whether those names exist.

## 4. Install

Download/clone the repository and run from the repository root:

~~~sh
sh ./install.command --dry-run
sh ./install.command
~~~

If a different existing Hammerspoon controller/menu is detected, installation stops rather than overwriting it silently. Review your local modifications, then deliberately invoke **sh ./install.command --force**. Existing Lua files, init.lua and previous runtime scripts are copied into a timestamped backup under ~/Library/Application Support/NK Scene2/backups/.

The installer uses pinned mido/python-rtmidi from requirements-scene2.txt, in a persistent venv under ~/Library/Application Support/NK Scene2/venv/. No global Python package install. It writes the selected Python path so the START menu works on Apple Silicon or Intel. The old /tmp/nk-mcu-venv is not required.

Finish with **Hammerspoon → Reload Config**. The menu will not start audio workers automatically. The 28/28 learned mapping stays stored; do not press the relearn command unless the physical Scene 1 CC layout itself has changed.

## 5. Start a session

1. Use **sh ./doctor.command** (read-only) to inspect dependencies and the two IAC buses.
2. In Resolve, **back up the current project**, STOP playback and scrubbing, and ensure the targeted audio clips have no gain keyframes or gain automation.
3. Hammerspoon → **NK JOG → Scene 2: START**.
4. Enter the **exact** current Resolve project name (the previous name is suggested on later starts).
5. Read and confirm the project-backup/playback/automation warning. Selecting Cancel performs no audio write.
6. Work with Scene 2 sliders, MUTE/SOLO and clip knobs. The log is ~/Library/Logs/nk-scene2-session.log.
7. Stop with **NK JOG → Scene 2: STOP** before switching Resolve projects or quitting.

**Safety:** a name match and a click are not a substitute for an actual backup. The API cannot authoritatively detect all clip gain automation or verify stopped playback in the low-latency mode. The code does check exact project identity, timeline/playhead/clip identity and the AudioVolume value before each change; it verifies each setter with a fresh readback. Failed setters attempt restoration and halt writes. Mixer strip 8 remains locked.

## 6. Uninstall / rollback

~~~sh
sh ./uninstall.command
~~~

Stop the session first. The uninstaller checks installed-file hashes, refuses to overwrite anything edited since installation, and restores the immediately preceding files. Backups, the isolated venv and Korg hs.settings remain intact. Reload Hammerspoon afterwards. This is **last-install rollback**, not a factory reset.

## Diagnostics

- **No menu:** verify ~/.hammerspoon/init.lua contains the single require("nanokontrol_resolve21") entry; reload Hammerspoon.
- **No MIDI from Resolve:** inspect IAC names, Resolve MCU MIDI Input/Output assignments and restart Resolve after editing Control Panels settings.
- **Knobs not writing:** check foreground Resolve, stopped playhead, a unique plain audio clip at the playhead and fresh rotary pickup. 29.97/drop-frame or unsupported timeline timecode is intentionally rejected.
- **Mixer faders unresponsive:** open/reselect the Resolve MCU controller to refresh host pitch-wheel positions. Faders must receive host feedback before physical pickup.
- **MUTE/SOLO LED state:** LED Mode must be External on the physical Korg. Host-return MIDI is authoritative; a button press alone does not guarantee an LED state.
- **Unexpected stop:** read ~/Library/Logs/nk-scene2-session.log and the Hammerspoon Console. Never launch a second terminal copy of the Scene 2 worker while the menu session is running.
