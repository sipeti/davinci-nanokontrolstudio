# Installation and MIDI routing

**v1.5 development preview:** macOS + DaVinci Resolve Studio 21 + Korg nanoKONTROL Studio in USB Assignable Mode. A Hammerspoon timer starts Scene 2 automatically when Resolve is ready; it is not a separate login daemon. Scene 2 PAUSE/RESUME remains available in NK JOG. Auto mode requires a physical test before merging into main; the accepted release remains v1.4.0.

## 1. Prerequisites

- Install Hammerspoon and grant **Accessibility** and, when needed, **Input Monitoring** in System Settings.
- Install Homebrew Python 3.10+ (Apple Silicon default /opt/homebrew/bin/python3); the setup selects /usr/local/bin/python3 on Intel when appropriate.
- Install DaVinci Resolve Studio 21 and ensure its Developer/Scripting/Modules directory exists.
- Install KORG KONTROL Editor, back up your Korg Scene Set, and power the nanoKONTROL Studio on in **Assignable Mode** (hold SCENE + CYCLE when powering on). **Do not switch the whole device to Pro Tools/HUI mode.**

Scene 1's 28-step learned binding remains in Hammerspoon hs.settings. First-time users follow the existing [control map](CONTROL_MAP.md); returning users must not rerun the wizard merely to install Scene 2.

## 2. Korg Scene 2 configuration

**Optional bank-paging Draft only:** SELECT7/8 already use CC52/53 in the
factory layout. No Korg hardware rewrite is needed. NK JOG → Beallitasok
→ Bank lapozas enables the two-bank preview for A1–A8 / A9–A16.
Use only with 16 real audio tracks; return to the first bank before
changing projects or stopping the preview. Normal v1.5 does not
enable this mode.

Use **Global MIDI Channel 2** for Scene 2 (Hammerspoon input channel 1). The tested mapping is:

| Physical controls | MIDI CC |
| --- | --- |
| Eight rotary knobs | 13–20, in order |
| Eight sliders/faders | **2, 3, 4, 5, 6, 8, 9, 12** — factory Korg assignments on all Scenes. Slider 8 (CC12) is ON by default; controls A8 in the tested eight-track project, but may control **Bus1** in another MCU bank. NK JOG offers an OFF switch |
| MUTE 1–8 | 21–28 |
| SOLO 1–8 | 29, 30, 31, 33, 34, 35, 36, 37 |
| Scene 2 JOG wheel | **CC82 / Sign Magnitude / Const** |
| Transport | Same physical CC assignments as Scene 1 |
| LED Mode | **External** |

**Do not rewrite the Korg's factory slider CCs to a consecutive range.** The software follows the actual factory mapping shown in KORG KONTROL Editor in all five Scenes. **Communication → Write Scene Data** is only needed when you intentionally change a hardware assignment (such as wheel CC82, LED Mode External or shared MARKER buttons). Keep Scene 1's mapping and 28-step calibration intact.

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

Finish with **Hammerspoon → Reload Config**. With Resolve ready and frontmost, the worker starts silently; the NK JOG menu lets you pause/resume it. The 28/28 learned mapping stays stored; do not press the relearn command unless the physical Scene 1 CC layout itself has changed. First validate this development branch in a duplicated project.

## 5. Start a session

1. Use **sh ./doctor.command** (read-only) to inspect dependencies and the two IAC buses.
2. In Resolve, **back up the current project**, STOP playback and scrubbing, and ensure the targeted audio clips have no gain keyframes or gain automation.
3. Hammerspoon → **Reload Config**; Scene 2 workers start in the background when Resolve is ready and frontmost.
4. Use the Korg scenes normally. No project name, consent dialog or manual START is needed. Clip knobs follow the active project; the mixer uses the **unchanged, hardware-accepted v1.4 MCU worker** with its original host-feedback soft pickup.
5. **Optional:** use **NK JOG → Beallitasok → Scene 2: AUTOMATIKUS / SZUNET** only when you need to pause or resume; it is not a startup gate. **Beallitasok → 8. MCU csatorna BE/KI** is enabled by default and can disable the eighth fader plus MUTE8/SOLO8 when the eighth MCU bank slot belongs to Bus1. The setting is session-local; Hammerspoon reload restores eight enabled strips. Session logs: ~/Library/Logs/nk-scene2-session.log.
6. For v1.5 physical acceptance, verify the mixer faders, MUTE/SOLO and LED feedback work just like v1.4, then try Scene 1/2 switching and clip gain on two disposable projects.

**Technical limits:** The clip-gain worker validates active project/timeline/clip identity at each setter and checks AudioVolume by readback. No extra cross-worker context gate is applied to the proven v1.4 MCU path; Fairlight host MIDI is still the authority for mixer pickup. Low-latency mode cannot reliably detect gain automation or running playback, so do not alter clip gain with automation or while scrubbing. MCU strip 8 is active by default after the A8 physical test; it always follows the eighth slot of the **current Resolve bank**, which may be Bus1 in some projects. NK JOG can disable it without affecting strips 1–7. No Korg CC change is required.

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
